import importlib.util
import math
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


workload = load("hotel_workload", "modules/hotel-reservation/workload/fixed_search.py")
fault = load("hotel_fault", "modules/hotel-reservation/faults/compose_pause.py")


def test_search_url_is_deterministic_and_uses_audited_route():
    assert workload.search_url("http://host:5000/", 3) == workload.search_url("http://host:5000", 3)
    assert workload.search_url("http://host:5000", 3).startswith("http://host:5000/hotels?")
    assert "inDate=2015-04-12" in workload.search_url("http://host:5000", 3)


def test_workload_parameters_reject_nonfinite_and_boolean_values():
    workload.validate(1.0, 10.0, 4, 5.0)
    for arguments in ((math.inf, 10, 4, 5), (1, math.nan, 4, 5), (1, 10, True, 5), (1, 10, 4, 0)):
        with pytest.raises(ValueError):
            workload.validate(*arguments)


def test_pause_fault_proves_outage_and_recovers(monkeypatch, tmp_path: Path):
    states = iter(({"exists": True, "running": True, "paused": False},
                   {"exists": True, "running": True, "paused": True},
                   {"exists": True, "running": True, "paused": False}))
    monkeypatch.setattr(fault, "container_state", lambda *_args, **_kwargs: next(states))
    availability = iter((True, False))
    monkeypatch.setattr(fault, "route_available", lambda *_args: next(availability))
    monkeypatch.setattr(fault, "wait_recovered", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(fault.time, "sleep", lambda _seconds: None)
    # began, applied (pause observed, before the during-probe), clock after the
    # 5 s during-probe (hold = 15 - 5), reverting (before the unpause command),
    # unpaused, ready, ended: the probe's duration is inside the hold, not added
    # to it (D21).
    monotonic = iter((0.0, 0.05, 5.0, 15.0, 15.02, 15.1, 15.2))
    monkeypatch.setattr(fault.time, "monotonic", lambda: next(monotonic))
    environments = []
    def record(args, check=True, env=None):
        environments.append(env)
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(fault, "command", record)
    compose_env = {"HR_FRONTEND_PORT": "35005", "HR_JAEGER_QUERY_PORT": "36685",
                   "HR_SOURCE_SHA256": "a" * 64}
    receipt = fault.inject(tmp_path, "project", "search-pause", 1, 15,
                           "http://host/hotels", tmp_path / "receipt.json", env=compose_env)
    assert receipt["manifested"] is True
    assert receipt["recovered"] is True
    assert receipt["successful"] is True
    assert receipt["preRouteAvailable"] is True
    assert receipt["preState"]["paused"] is False
    assert receipt["faultKind"] == "pause"
    # LMT+S detection window: both edges strictly inside the fault.
    assert receipt["startedMonotonic"] <= receipt["appliedMonotonic"] == 0.05
    assert receipt["appliedMonotonic"] < receipt["revertingMonotonic"] == 15.0
    assert receipt["revertingMonotonic"] <= receipt["unpausedAtMonotonic"] == 15.02
    assert receipt["actualOutageSeconds"] == 15.02
    assert environments and all(value == compose_env for value in environments)


def test_pause_fault_rejects_missing_compose_environment(tmp_path: Path):
    with pytest.raises(ValueError, match="HR_JAEGER_QUERY_PORT"):
        fault.inject(tmp_path, "project", "search-pause", 1, 15,
                     "http://host/hotels", tmp_path / "receipt.json",
                     env={"HR_FRONTEND_PORT": "35005", "HR_SOURCE_SHA256": "a" * 64})


def test_candidate_fault_waits_for_absolute_onset_but_records_plan_offset(
    monkeypatch, tmp_path: Path,
):
    current = [40.0]
    states = iter((
        {"exists": True, "running": True, "paused": False},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": False},
    ))
    availability = iter((True, False))
    monkeypatch.setattr(fault, "container_state", lambda *_args, **_kwargs: next(states))
    monkeypatch.setattr(fault, "route_available", lambda *_args: next(availability))
    monkeypatch.setattr(fault, "wait_recovered", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(fault.time, "monotonic", lambda: current[0])
    monkeypatch.setattr(fault.time, "sleep", lambda seconds: current.__setitem__(0, current[0] + seconds))
    monkeypatch.setattr(
        fault, "command",
        lambda args, check=True, env=None: subprocess.CompletedProcess(args, 0, "", ""),
    )
    compose_env = {
        "HR_FRONTEND_PORT": "35005", "HR_JAEGER_QUERY_PORT": "36685",
        "HR_SOURCE_SHA256": "a" * 64,
    }
    receipt = fault.inject(
        tmp_path, "project", "reservation-pause", 45, 15,
        "http://host/hotels", tmp_path / "absolute-receipt.json",
        env=compose_env, scheduled_at_seconds=45, start_at_monotonic=45.0,
    )
    assert receipt["scheduledAtSeconds"] == 45
    assert receipt["startedMonotonic"] == 45.0
    assert receipt["successful"] is True


def test_pause_fault_finally_attempts_recovery(monkeypatch, tmp_path: Path):
    calls = []
    monkeypatch.setattr(fault.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(fault.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(fault, "container_state",
                        lambda *_args, **_kwargs: {"exists": True, "running": True, "paused": True})
    monkeypatch.setattr(fault, "route_available", lambda *_args: (_ for _ in ()).throw(RuntimeError("probe")))
    monkeypatch.setattr(fault, "wait_recovered", lambda *_args, **_kwargs: True)
    def record(args, check=True, env=None):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(fault, "command", record)
    compose_env = {"HR_FRONTEND_PORT": "35005", "HR_JAEGER_QUERY_PORT": "36685",
                   "HR_SOURCE_SHA256": "a" * 64}
    receipt = fault.inject(tmp_path, "project", "reservation-pause", 0, 1,
                           "http://host/hotels", tmp_path / "receipt.json", env=compose_env)
    assert receipt["successful"] is False
    assert receipt["error"].startswith("RuntimeError")
    assert any("unpause" in command for command in calls)
