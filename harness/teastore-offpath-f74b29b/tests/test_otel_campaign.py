import argparse
import importlib.util
import json
import math
import subprocess
import threading
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "modules/otel-demo/execution/campaign.py"
SPEC = importlib.util.spec_from_file_location("otel_campaign", MODULE)
campaign = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(campaign)
ANALYZER = Path(__file__).parents[1] / "modules/otel-demo/analyze.py"
ANALYZER_SPEC = importlib.util.spec_from_file_location("otel_analyzer", ANALYZER)
analyzer = importlib.util.module_from_spec(ANALYZER_SPEC)
ANALYZER_SPEC.loader.exec_module(analyzer)


def arguments(**updates):
    campaign.PROJECT = "obsplacement-otel-test"
    values = {"postures": "source-off,full", "blocks": 3, "duration": 120,
              "warmup": 30, "rate": 1.0, "concurrency": 4,
              "fault_at": 45, "outage": 15, "seed": 7,
              "url": "http://localhost:8080/api/recommendations"}
    values.update(updates)
    return argparse.Namespace(**values)


def test_campaign_parameters_accept_bounded_recovery_window():
    assert campaign.validate(arguments()) == ("source-off", "full")


def test_campaign_rejects_duplicate_postures_and_unfinished_recovery():
    try:
        campaign.validate(arguments(postures="full,full"))
        assert False
    except ValueError:
        pass


def test_campaign_rejects_unsafe_compose_project(monkeypatch):
    args = arguments()
    monkeypatch.setattr(campaign, "PROJECT", "../../shared")
    with pytest.raises(ValueError, match="Compose project"):
        campaign.validate(args)
    try:
        campaign.validate(arguments(rate=math.inf))
        assert False
    except ValueError:
        pass


def test_campaign_rejects_unbounded_work_and_boolean_integers():
    for values in (
            {"blocks": 101}, {"blocks": True}, {"concurrency": 1025},
            {"duration": 1000, "rate": 1001}, {"warmup": 86401},
            {"seed": -1}, {"url": "file:///tmp/workload"}):
        with pytest.raises(ValueError):
            campaign.validate(arguments(**values))
    try:
        campaign.validate(arguments(fault_at=110, outage=10))
        assert False
    except ValueError:
        pass


def test_source_off_environment_selects_all_three_guards(tmp_path):
    config = tmp_path / "src/frontendproxy/envoy.no-tracing.tmpl.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("static_resources: {}\n")
    (tmp_path / ".source.sha256").write_text("a" * 64 + "\n")
    env = campaign.posture_env("source-off", tmp_path)
    assert env["OTEL_PLACEMENT_DISABLED"] == "true"
    assert env["OTEL_PLACEMENT_ENABLED"] == "false"
    assert env["OTEL_ENVOY_CONFIG"].endswith("envoy.no-tracing.tmpl.yaml")
    assert env["OTEL_COLLECTOR_CONFIG"].endswith("otelcol-placement.yml")
    assert env["OTEL_IMAGE_TAG"] == "1.12.0-" + "a" * 16


def test_cpu_percent_parses_docker_stats_value():
    assert campaign.cpu_percent("12.34%") == 12.34


def test_trace_export_stats_counts_batches_and_spans():
    log = ('TracesExporter {"resource spans": 2, "spans": 12}\n'
           'MetricsExporter {"data points": 7}\n'
           'TracesExporter {"resource spans": 1, "spans": 3}\n')
    assert campaign.trace_export_stats(log) == {"batches": 2, "spans": 15}


def test_upstream_sha_falls_back_to_source_lock(monkeypatch, tmp_path):
    (tmp_path / "modules/otel-demo").mkdir(parents=True)
    (tmp_path / "modules/otel-demo/source.lock").write_text("commit: " + "a" * 40 + "\n")
    monkeypatch.setattr(campaign, "ROOT", tmp_path)
    assert campaign.upstream_sha() == "a" * 40


def test_run_uses_prebuilt_images_and_tears_down_when_start_fails(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    calls = []

    def fake_command(argv, **kwargs):
        calls.append(argv)
        if "up" in argv:
            raise RuntimeError("synthetic start failure")
        return type("Result", (), {"stdout": "", "stderr": "", "returncode": 0})()

    monkeypatch.setattr(campaign, "posture_env", lambda *_args: {})
    monkeypatch.setattr(campaign, "command", fake_command)
    args = argparse.Namespace(source=source)
    with pytest.raises(RuntimeError, match="synthetic start failure"):
        campaign.run_one(tmp_path / "campaign", "b01-full", "full", args,
                         {"images": {}}, {"materializedSourceSha256": "a" * 64})

    flattened = [item for call in calls for item in call]
    assert "build" not in flattened
    up = next(call for call in calls if "up" in call)
    assert "--no-build" in up
    assert sum("down" in call for call in calls) == 1


def test_materialized_source_proof_recomputes_tree_digest(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.txt").write_text("guarded\n")
    (source / ".obsplacement-materialized").write_text(json.dumps({"upstreamSha": "a" * 40}))
    digest = campaign.tree_sha256(source)
    (source / ".source.sha256").write_text(digest + "\n")
    monkeypatch.setattr(campaign, "upstream_sha", lambda: "a" * 40)
    assert campaign.materialized_source_proof(source)["materializedSourceSha256"] == digest
    (source / "app.txt").write_text("drifted\n")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        campaign.materialized_source_proof(source)


def test_campaign_builds_target_images_once_and_reuses_exact_ids(monkeypatch, tmp_path):
    calls = []
    services = {name: {"image": f"example/{name}:pinned"}
                for name in campaign.BUILD_SERVICES}

    def fake_command(argv, **kwargs):
        calls.append(argv)
        if "--format" in argv and "json" in argv and "config" in argv:
            stdout = json.dumps({"services": services})
        elif argv[:3] == ["docker", "image", "inspect"]:
            stdout = json.dumps([{"Id": "sha256:" + "d" * 64, "RepoDigests": []}])
        else:
            stdout = ""
        if kwargs.get("output") is not None:
            kwargs["output"].write_text(stdout)
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(campaign, "command", fake_command)
    proof = {"materializedSourceSha256": "a" * 64}
    first = campaign.build_once(tmp_path, tmp_path / "source", {}, proof)
    second = campaign.build_once(tmp_path, tmp_path / "source", {}, proof)
    assert first == second
    assert first["buildCount"] == 1
    assert sum("build" in call for call in calls) == 1


def test_exception_cancels_fault_worker_before_teardown(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    finished = threading.Event()
    down_after_finished = []

    def fake_command(argv, **_kwargs):
        if "workload.py" in " ".join(argv):
            raise RuntimeError("synthetic workload failure")
        if "down" in argv:
            down_after_finished.append(finished.is_set())
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_sampler(_source, _env, stop, output, interval=2.0):
        stop.wait(5)
        output.write_text(json.dumps({"summary": {}}))

    def fake_fault(_source, _env, _fault_at, _outage, _url, cancel, output):
        cancel.wait(5)
        finished.set()
        value = {"successful": False, "error": "cancelled"}
        output.write_text(json.dumps(value))
        return value

    monkeypatch.setattr(campaign, "project_resources",
                        lambda: {"containers": [], "networks": [], "volumes": []})
    monkeypatch.setattr(campaign, "posture_env", lambda *_args: {})
    monkeypatch.setattr(campaign, "command", fake_command)
    monkeypatch.setattr(campaign, "wait_ready", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(campaign, "posture_proof", lambda *_args: {"services": {}})
    monkeypatch.setattr(campaign, "sample_resources", fake_sampler)
    monkeypatch.setattr(campaign, "inject_fault", fake_fault)
    args = argparse.Namespace(source=source, url="http://localhost/", warmup=0,
                              rate=1.0, concurrency=1, duration=2, fault_at=1, outage=1)
    with pytest.raises(RuntimeError, match="synthetic workload failure"):
        campaign.run_one(tmp_path / "campaign", "b01-full", "full", args,
                         {"images": {}}, {"materializedSourceSha256": "a" * 64})
    assert finished.is_set()
    assert down_after_finished == [True]


def test_analyzer_never_promotes_the_legacy_source_off_control(tmp_path):
    for posture, p50, p95, cpu, spans in (
            ("full", 12.0, 20.0, 3.0, 10),
            ("source-off", 10.0, 18.0, 2.0, 2)):
        run = tmp_path / f"b01-{posture}"
        run.mkdir(parents=True)
        (run / "receipt.json").write_text(json.dumps({
            "runId": f"b01-{posture}", "latencyMs": {"p50": p50, "p95": p95},
            "resources": {"frontend": {"meanCpuPercent": cpu}},
            "workload": {"offered": 2, "completed": 2, "failed": 0},
            "intervention": {"successful": True},
        }))
        (run / "otelcol.log").write_text(
            f'TracesExporter {{"resource spans": 1, "spans": {spans}}}\n')
    report = analyzer.analyze(tmp_path)
    assert report["verdict"] == "noncanonical-control-smoke"
    assert "not proven" in report["qualification"]
