import argparse
import importlib.util
import json
import subprocess
from pathlib import Path


MODULE = Path(__file__).parents[1] / "modules/teastore/execution/performance_campaign.py"
SPEC = importlib.util.spec_from_file_location("performance_campaign", MODULE)
performance_campaign = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(performance_campaign)


def test_collector_stats_parses_success_path_regression():
    value = performance_campaign.collector_stats('prefix {"records_bad": 0, "record_parse_success_ratio": 1.0} suffix')
    assert value["records_bad"] == 0


def test_intervention_proves_manifestation_duration_and_recovery(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    monkeypatch.setattr(performance_campaign, "service_container", lambda _posture, service: f"container-{service}")
    states = iter((
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": False},
    ))
    monkeypatch.setattr(performance_campaign, "container_state", lambda _container: next(states))
    monkeypatch.setattr(performance_campaign, "wait_ready", lambda: None)
    monotonic = iter((0.0, 30.0))
    monkeypatch.setattr(performance_campaign.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(performance_campaign.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(performance_campaign, "command", lambda _args, check=False:
                        subprocess.CompletedProcess(_args, 0, "", ""))
    receipt = performance_campaign.inject_fault("auth-freeze", 240, 30, tmp_path)
    assert receipt["manifested"] is True
    assert receipt["outageHeld"] is True
    assert receipt["recovered"] is True
    assert receipt["successful"] is True
    assert json.loads((tmp_path / "intervention.json").read_text())["successful"] is True


def test_intervention_exception_becomes_failed_receipt(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    monkeypatch.setattr(performance_campaign, "service_container",
                        lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(performance_campaign.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(performance_campaign, "command", lambda *_args, **_kwargs:
                        (_ for _ in ()).throw(RuntimeError("boom")))
    receipt = performance_campaign.inject_fault("auth-freeze", 1, 1, tmp_path)
    assert receipt["successful"] is False
    assert "RuntimeError" in receipt["error"]
    assert (tmp_path / "intervention.json").exists()


def test_complete_configuration_records_provenance(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".local/compiled/teastore").mkdir(parents=True)
    (tmp_path / ".local/compiled/teastore/manifest.json").write_text("{}")
    (tmp_path / "modules/teastore/goals").mkdir(parents=True)
    (tmp_path / "modules/teastore/goals/fault-qualification.json").write_text("{}")
    args = argparse.Namespace(seed=7, blocks=3, warmup=10, duration=100, rate=0.5,
                              concurrency=4, fault="auth-freeze", fault_at=20, outage=10,
                              framework_commit="a" * 40, sut_commit="b" * 40,
                              selection_id="fault-qualification")
    result = performance_campaign.campaign_configuration(args, ("selected", "full"))
    assert result["selectionId"] == "fault-qualification"
    assert result["frameworkCommit"] == "a" * 40
    assert result["activationManifestSha256"]
    assert result["selectionSourceSha256"]
    assert result["composeProject"] == "obst-test"


def test_project_namespace_is_explicit_and_restricted(monkeypatch):
    monkeypatch.delenv("OBSPLACEMENT_COMPOSE_PROJECT", raising=False)
    try:
        performance_campaign.project_name()
    except ValueError:
        pass
    else:
        raise AssertionError("missing project namespace must fail closed")
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "../foreign")
    try:
        performance_campaign.project_name()
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe project namespace must fail closed")


def test_campaign_requires_full_source_commits(monkeypatch):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    args = argparse.Namespace(
        postures="none,selected,full", blocks=1, warmup=0, duration=10,
        concurrency=1, rate=1.0, fault="none", fault_at=240, outage=30,
        framework_commit="abc1234", sut_commit="b" * 40,
    )
    try:
        performance_campaign.validate_parameters(args)
    except ValueError as exc:
        assert "full 40-character" in str(exc)
    else:
        raise AssertionError("abbreviated framework provenance must fail closed")


def test_existing_receipt_must_match_immutable_schedule(tmp_path: Path):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({
        "runId": "b01-full", "posture": "full",
        "source": {"frameworkCommit": "wrong", "sutCommit": "sut", "selectionId": "auth",
                   "selectionSourceSha256": "selection", "activationManifestSha256": None},
    }))
    configuration = {"frameworkCommit": "framework", "sutCommit": "sut", "selectionId": "auth",
                     "selectionSourceSha256": "selection", "activationManifestSha256": "manifest"}
    try:
        performance_campaign.validate_existing_receipt(path, "b01-full", "full", configuration)
    except RuntimeError as exc:
        assert "frameworkCommit" in str(exc)
    else:
        raise AssertionError("stale receipt must not be silently resumed")
