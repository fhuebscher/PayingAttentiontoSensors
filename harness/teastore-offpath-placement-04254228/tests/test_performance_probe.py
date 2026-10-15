import importlib.util
import subprocess
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/collectors/performance_probe.py"
SPEC = importlib.util.spec_from_file_location("performance_probe", MODULE)
performance_probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(performance_probe)


def test_memory_units():
    assert performance_probe.bytes_value("1KiB / 2GiB") == 1024
    assert performance_probe.bytes_value("1.5MiB / 2GiB") == 1.5 * 1024**2


def _completed(args: list[str], stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args, 0, stdout, "")


def test_required_application_container_set_is_not_silently_zero(monkeypatch):
    monkeypatch.setattr(
        performance_probe.subprocess, "run",
        lambda args, **_kwargs: _completed(args, "") if args[:2] == ["docker", "ps"]
        else _completed(args),
    )
    with pytest.raises(RuntimeError, match="no containers found"):
        performance_probe.docker_sample("obst-test", set(), {"auth"})


def test_required_application_container_set_rejects_missing_service(monkeypatch):
    def fake_run(args, **_kwargs):
        if args[:2] == ["docker", "ps"]:
            return _completed(args, "a" * 64 + "\n")
        if args[:2] == ["docker", "inspect"]:
            return _completed(args, "auth\n")
        raise AssertionError(args)

    monkeypatch.setattr(performance_probe.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match=r"missing=\['persistence'\]"):
        performance_probe.docker_sample(
            "obst-test", set(), {"auth", "persistence"})


def test_shared_barrier_rejects_stale_or_nonfinite_time(monkeypatch):
    monkeypatch.setattr(performance_probe.time, "time", lambda: 100.0)
    with pytest.raises(ValueError, match="already more than one second"):
        performance_probe.sample("obst-test", 1, 1, start_at_epoch=98.0)
    with pytest.raises(ValueError, match="finite"):
        performance_probe.sample("obst-test", 1, 1, start_at_epoch=float("nan"))
    with pytest.raises(ValueError, match="bounded controller-generated"):
        performance_probe.sample("obst-test", 1, 1, barrier_id="../../wrong")
