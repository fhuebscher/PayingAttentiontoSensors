import importlib.util
import json
import math
import subprocess
import sys
import threading
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


materialize = load("hotel_materialize", "modules/hotel-reservation/materialize.py")
campaign = load("hotel_campaign", "modules/hotel-reservation/execution/campaign.py")
smoke = load("hotel_smoke", "modules/hotel-reservation/execution/smoke.py")
selection = load("selection", "src/obsplacement/selection.py")


def test_materialization_is_clean_pinned_and_content_addressed(tmp_path: Path):
    proof = materialize.materialize(tmp_path / "source")
    assert proof["upstreamCommit"] == materialize.pinned_commit()
    assert proof["sourceCheckoutClean"] is True
    assert len(proof["upstreamTree"]) == 40
    assert (tmp_path / "source/docker-compose.yml").is_file()
    original = (tmp_path / "source/docker-compose.yml").read_text()
    generated = (tmp_path / "source/docker-compose.obsplacement.yml").read_text()
    assert "container_name: 'hotel_reserv_review'" in original
    assert "container_name:" not in generated
    assert "127.0.0.1:${HR_FRONTEND_PORT:?set HR_FRONTEND_PORT}:5000" in generated
    assert "127.0.0.1:${HR_JAEGER_QUERY_PORT:?set HR_JAEGER_QUERY_PORT}:16686" in generated
    assert '"8300:8300"' not in generated
    assert proof["generatedComposeSha256"]
    assert proof["upstreamContentSha256"] != proof["materializedSourceSha256"]
    assert materialize.tree_sha256(tmp_path / "source") == proof["materializedSourceSha256"]
    assert json.loads((tmp_path / "source/.obsplacement-materialized").read_text()) == proof


def test_materializer_refuses_unowned_existing_target(tmp_path: Path):
    target = tmp_path / "not-ours"
    target.mkdir()
    (target / "keep.txt").write_text("user data")
    with pytest.raises(RuntimeError, match="non-materialized"):
        materialize.materialize(target)
    assert (target / "keep.txt").read_text() == "user data"


def test_materializer_refuses_targets_inside_pinned_checkout():
    with pytest.raises(RuntimeError, match="unsafe materialization target"):
        materialize.safe_target(materialize.UPSTREAM / "hotelReservation/generated")


def test_isolation_transform_fails_closed_on_upstream_drift():
    with pytest.raises(RuntimeError, match="review container_name"):
        materialize.isolated_compose("services: {}\n")


def test_stock_selection_exposes_path_wide_coupling():
    catalog = json.loads((ROOT / "modules/hotel-reservation/activation/catalog.json").read_text())
    compiled = selection.compile_selection(catalog, ["span:search:/search.Search/Nearby"])
    assert compiled["independentlyControllable"] is False
    assert compiled["selectedActivationGroups"] == ["stock-root-trace-sampling"]
    assert len(compiled["expectedLogicalSensors"]) == 6


def parameters(**updates):
    values = {"blocks": 3, "seed": 7, "warmup_seconds": 30.0,
              "measurement_seconds": 120.0, "requests_per_second": 10.0,
              "concurrency": 8, "postures": ("sample-zero", "full"),
              "scenario": "hotel-search", "fault": "search-pause",
              "fault_at_seconds": 45.0, "outage_seconds": 15.0,
              "base_url": "http://localhost:5000"}
    values.update(updates)
    return campaign.CampaignParameters(**values)


def test_campaign_parameters_fail_closed_before_schedule_generation():
    parameters().validate()
    for value in (
        parameters(requests_per_second=math.inf),
        parameters(postures=("full", "sample-zero")),
        parameters(fault_at_seconds=110, outage_seconds=10),
        parameters(concurrency=True),
        parameters(scenario="unreviewed"),
    ):
        with pytest.raises(ValueError):
            value.validate()


def test_schedule_is_balanced_deterministic_and_immutable(tmp_path: Path):
    values = parameters()
    proof = {"upstreamCommit": "a" * 40, "upstreamTree": "b" * 40,
             "materializedSourceSha256": "c" * 64, "sourceCheckoutClean": True}
    config = campaign.configuration(values, proof, "framework")
    assert config["evidenceLabelCeiling"] == "smoke-validation"
    rows = campaign.schedule(values)
    assert rows == campaign.schedule(values)
    assert len(rows) == 6
    assert all({row["posture"] for row in rows if row["block"] == block} == set(campaign.POSTURES)
               for block in range(1, 4))
    target = tmp_path / "schedule.json"
    payload = campaign.write_schedule(target, config, rows)
    campaign.write_schedule(target, config, rows)
    assert payload == {"configuration": config, "runs": rows}
    changed = json.loads(json.dumps(config))
    changed["parameters"]["seed"] = 8
    with pytest.raises(RuntimeError, match="refusing to change"):
        campaign.write_schedule(target, changed, rows)


def test_lifecycle_rejects_skips_and_failed_receipts():
    lifecycle = campaign.Lifecycle()
    with pytest.raises(RuntimeError, match="invalid lifecycle"):
        lifecycle.advance(campaign.State.DEPLOYED, {"successful": True})
    assert lifecycle.state == campaign.State.UNKNOWN
    assert lifecycle.advance(campaign.State.INVENTORIED, {"successful": True}) == campaign.State.INVENTORIED
    with pytest.raises(RuntimeError, match="failed lifecycle"):
        lifecycle.advance(campaign.State.QUARANTINED, {"successful": False})
    assert lifecycle.state == campaign.State.FAILED


def test_smoke_contract_accepts_only_fresh_isolated_namespace(tmp_path: Path):
    source = tmp_path / "source"
    proof = materialize.materialize(source)
    assert smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                          35004, 36684, 1, 20, 4, 5, 3) == proof
    with pytest.raises(ValueError, match="namespace"):
        smoke.validate(source, tmp_path / "result", "hotel", 35004, 36684, 1, 20, 4, 5, 3)
    with pytest.raises(ValueError, match="distinct"):
        smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                       35004, 35004, 1, 20, 4, 5, 3)
    with pytest.raises(ValueError, match="blocks"):
        smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                       35004, 36684, 1, 20, 4, 5, 3, blocks=0)
    with pytest.raises(ValueError, match="seed"):
        smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                       35004, 36684, 1, 20, 4, 5, 3, seed=True)
    with pytest.raises(ValueError, match="warmup"):
        smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                       35004, 36684, 1, 20, 4, 5, 3, warmup=0)


def test_smoke_run_identity_is_bound_to_posture(monkeypatch, tmp_path):
    build = {"materializedSourceSha256": "a" * 64,
             "imageId": "sha256:" + "b" * 64}
    with pytest.raises(ValueError, match="run ID"):
        smoke.run_posture(tmp_path, tmp_path / "source", "obsplacement-hotel-test01",
                          "full", 35004, 36684, 1, 20, 4, 5, 3,
                          "obsplacement/hotel-reservation:test", build,
                          run_id="b01-sample-zero", block=1)
    with pytest.raises(ValueError, match="block"):
        smoke.run_posture(tmp_path, tmp_path / "source", "obsplacement-hotel-test01",
                          "full", 35004, 36684, 1, 20, 4, 5, 3,
                          "obsplacement/hotel-reservation:test", build,
                          run_id="b01-full", block=0)


def test_smoke_completion_rejects_tampered_or_stale_receipts(tmp_path):
    image_id = "sha256:" + "b" * 64
    source_digest = "a" * 64
    build = {"imageId": image_id, "materializedSourceSha256": source_digest}
    schedule = {
        "configuration": {
            "schemaVersion": 1, "evidenceLabelCeiling": "smoke-validation",
            "parameters": {"requests_per_second": 1, "measurement_seconds": 2},
            "runtime": {"buildProof": build},
        },
        "runs": [
            {"runId": "b01-full", "block": 1, "posture": "full"},
            {"runId": "b01-sample-zero", "block": 1, "posture": "sample-zero"},
        ],
    }
    (tmp_path / "schedule.json").write_text(json.dumps(schedule, indent=2, sort_keys=True) + "\n")
    proof = {
        "scheduleSha256": smoke.sha256(tmp_path / "schedule.json"),
        "configurationSha256": smoke.json_sha256(schedule["configuration"]),
        "buildImageId": image_id,
        "materializedSourceSha256": source_digest,
    }
    images = [{"service": service, "imageId": image_id} for service in smoke.APP_SERVICES]
    full_posture = {"requested": "full", "expectedSampleRatio": "1",
                    "sourceWorkDisabled": False,
                    "services": {service: "1" for service in smoke.APP_SERVICES}}
    off_posture = {"requested": "sample-zero", "expectedSampleRatio": "0",
                   "sourceWorkDisabled": False,
                   "services": {service: "0" for service in smoke.APP_SERVICES}}
    aggregate = {"offered": 2, "completed": 2, "failed": 0, "bytesReceived": 10}
    full = {"runId": "b01-full", "block": 1, "posture": "full",
            "campaignProof": proof, "functionalVerdict": "pass",
            "intervention": {"successful": True}, "visibility": {"verdict": "pass"},
            "telemetry": {"spanCount": 6}, "workload": aggregate,
            "buildProof": build, "postureProof": full_posture, "images": images}
    off = {"runId": "b01-sample-zero", "block": 1, "posture": "sample-zero",
           "campaignProof": proof, "functionalVerdict": "pass", "intervention": None,
           "visibility": None, "telemetry": {"spanCount": 0}, "workload": aggregate,
           "buildProof": build, "postureProof": off_posture, "images": images}
    for run_id, receipt in (("b01-full", full), ("b01-sample-zero", off)):
        (tmp_path / run_id).mkdir()
        (tmp_path / run_id / "receipt.json").write_text(json.dumps(receipt))
        (tmp_path / run_id / "workload.json").write_text(json.dumps(
            {**aggregate, "requests": [{"sequence": 0}, {"sequence": 1}]}))
    hygiene = {"protectedProjectUnchanged": True,
               "projectResources": {"containers": [], "networks": [], "volumes": []}}
    assert smoke.validate_completed_campaign(tmp_path, schedule, proof, hygiene)["successful"]
    off["campaignProof"] = {**proof, "scheduleSha256": "0" * 64}
    (tmp_path / "b01-sample-zero/receipt.json").write_text(json.dumps(off))
    blocked = smoke.validate_completed_campaign(tmp_path, schedule, proof, hygiene)
    assert not blocked["successful"]
    assert {error["kind"] for error in blocked["errors"]} == {"campaign-proof-mismatch"}
    off["campaignProof"] = proof
    off["workload"] = {"offered": 0, "completed": 0, "failed": 0, "bytesReceived": 0}
    (tmp_path / "b01-sample-zero/receipt.json").write_text(json.dumps(off))
    (tmp_path / "b01-sample-zero/workload.json").write_text(json.dumps(
        {**off["workload"], "requests": []}))
    blocked = smoke.validate_completed_campaign(tmp_path, schedule, proof, hygiene)
    assert {error["kind"] for error in blocked["errors"]} == {"workload-denominator-mismatch"}


def test_smoke_recomputes_materialized_tree_and_bounds_work(tmp_path: Path):
    source = tmp_path / "source"
    materialize.materialize(source)
    smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                   35004, 36684, 1, 20, 4, 5, 3)
    (source / "services/frontend/server.go").write_text("drift\n")
    with pytest.raises(ValueError, match="tree digest"):
        smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                       35004, 36684, 1, 20, 4, 5, 3)
    with pytest.raises(ValueError):
        smoke.validate(source, tmp_path / "result", "obsplacement-hotel-test01",
                       35004, 36684, 10000, 101, 4, 5, 3)


def test_smoke_requires_exact_loopback_port_inventory():
    images = [
        {"service": "frontend", "publishedPorts": {"5000/tcp": [
            {"HostIp": "127.0.0.1", "HostPort": "35004"}]}},
        {"service": "jaeger", "publishedPorts": {"16686/tcp": [
            {"HostIp": "127.0.0.1", "HostPort": "36684"}]}},
    ]
    smoke.validate_published_ports(images, 35004, 36684)
    images[0]["publishedPorts"]["5000/tcp"][0]["HostIp"] = "0.0.0.0"
    with pytest.raises(RuntimeError, match="published-port isolation"):
        smoke.validate_published_ports(images, 35004, 36684)


def test_smoke_builds_once_and_binds_all_application_services(monkeypatch, tmp_path):
    calls = []
    image_id = "sha256:" + "d" * 64
    def fake_command(argv, **_kwargs):
        calls.append(argv)
        output = json.dumps([{"Id": image_id, "RepoDigests": [], "Config": {"Labels": {
            "org.obsplacement.materialized-source-sha256": "a" * 64}}}]) if argv[:3] == ["docker", "image", "inspect"] else ""
        return subprocess.CompletedProcess(argv, 0, output, "")
    monkeypatch.setattr(smoke, "command", fake_command)
    proof = {"materializedSourceSha256": "a" * 64}
    env = smoke.environment("full", 35004, 36684, "obsplacement/hotel-reservation:" + "a" * 16,
                            "a" * 64)
    built = smoke.build_images(tmp_path, "obsplacement-hotel-test01", env, proof, tmp_path / "build.log")
    assert built["imageId"] == image_id
    build_call = next(call for call in calls if "build" in call)
    assert build_call[-2:] == ["build", "frontend"]
    images = [{"service": service, "imageId": image_id} for service in smoke.APP_SERVICES]
    smoke.validate_app_image_binding(images, built)
    images[0]["imageId"] = "sha256:" + "e" * 64
    with pytest.raises(RuntimeError, match="image binding"):
        smoke.validate_app_image_binding(images, built)


def test_hotel_overlay_embeds_materialized_source_label():
    overlay = (ROOT / "modules/hotel-reservation/deployment/compose.observability-placement.yml").read_text()
    assert "org.obsplacement.materialized-source-sha256" in overlay
    assert "${HR_SOURCE_SHA256:?set HR_SOURCE_SHA256}" in overlay


def test_smoke_cancels_fault_worker_before_teardown_on_failure(monkeypatch, tmp_path):
    finished = threading.Event()
    teardown_after_finish = []

    def fake_command(argv, **kwargs):
        if "fixed_search.py" in " ".join(argv):
            duration = argv[argv.index("--duration") + 1]
            if duration == "4":
                raise RuntimeError("synthetic workload failure")
        if "down" in argv:
            teardown_after_finish.append(finished.is_set())
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_inject(_source, _project, _scenario, _fault_at, _outage,
                    _probe, output, cancel, env=None):
        assert env is not None
        cancel.wait(5)
        finished.set()
        result = {"successful": False, "error": "cancelled"}
        output.write_text(json.dumps(result))
        return result

    monkeypatch.setattr(smoke, "command", fake_command)
    monkeypatch.setattr(smoke, "wait_ready", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(smoke, "image_receipt", lambda _project: [])
    monkeypatch.setattr(smoke, "validate_app_image_binding", lambda *_args: None)
    monkeypatch.setattr(smoke, "validate_published_ports", lambda *_args: None)
    monkeypatch.setattr(smoke, "posture_proof", lambda *_args: {"requested": "full"})
    monkeypatch.setattr(smoke, "project_resources",
                        lambda _project: {"containers": [], "networks": [], "volumes": []})
    original_load = smoke.load
    monkeypatch.setattr(smoke, "load", lambda _name, path:
                        SimpleNamespace(inject=fake_inject)
                        if path.name == "compose_pause.py" else original_load(_name, path))
    build = {"materializedSourceSha256": "a" * 64, "imageId": "sha256:" + "b" * 64}
    with pytest.raises(RuntimeError, match="synthetic workload failure"):
        smoke.run_posture(tmp_path, tmp_path / "source", "obsplacement-hotel-test01",
                          "full", 35004, 36684, 1, 4, 1, 1, 1,
                          "obsplacement/hotel-reservation:test", build)
    assert finished.is_set()
    assert teardown_after_finish == [True]
