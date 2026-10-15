import argparse
import copy
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
import pytest


MODULE = Path(__file__).parents[1] / "modules/teastore/execution/performance_campaign.py"
SPEC = importlib.util.spec_from_file_location("performance_campaign", MODULE)
performance_campaign = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(performance_campaign)
COLLECTOR_MODULE = (
    Path(__file__).parents[1] / "modules/teastore/collectors/kieker_native.py"
)
COLLECTOR_SPEC = importlib.util.spec_from_file_location(
    "kieker_native_boundary", COLLECTOR_MODULE
)
kieker_native = importlib.util.module_from_spec(COLLECTOR_SPEC)
assert COLLECTOR_SPEC.loader
COLLECTOR_SPEC.loader.exec_module(kieker_native)


def valid_collector_stats(**updates):
    value = {
        "messages": 2,
        "containers_ok": 2,
        "containers_bad": 0,
        "records_ok": 4,
        "records_bad": 0,
        "record_parse_success_ratio": 1.0,
        "container_parse_success_ratio": 1.0,
        "acknowledgement_mode": "manual",
        "runtime_host_map_loaded": True,
        "correlation": {
            "events": 4,
            "parentResolution": {"root": 4},
            "serviceAttribution": {"runtime-host-and-signature-agree": 4},
            "eventsWithCorrelationErrors": 0,
            "eventsWithUnwovenRootParent": 0,
            "eventsWithProbeOrphanRoot": 0,
            "eventsWithCorrelationWarnings": 0,
            "eventsWithServiceAttributionErrors": 0,
            "traceCompleteness": {
                "traces": 4,
                "tracesWithEoiGaps": 0,
                "missingEoiCount": 0,
                "tracesNotStartingAtZero": 0,
            },
        },
    }
    value.update(updates)
    return value


def clean_resource_proof(project="obst-test"):
    label = f"label=com.docker.compose.project={project}"
    commands = {
        "containers": ["docker", "ps", "-aq", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
    }
    return {
        "project": project,
        "queries": {kind: {"command": command, "returnCode": 0, "stdout": "", "stderr": ""}
                    for kind, command in commands.items()},
        "queryPassed": True,
        "containers": [], "networks": [], "volumes": [],
    }


def runtime_image_fixture(project="obst-test"):
    services = {}
    for index, service in enumerate(performance_campaign.RUNTIME_SERVICES, start=1):
        digit = f"{index:x}"
        container_id = digit * 64
        image_id = f"sha256:{digit * 64}"
        declared = performance_campaign.EXPECTED_RUNTIME_IMAGES[service]
        repository = performance_campaign.EXPECTED_RUNTIME_REPOSITORIES[service]
        services[service] = {
            "containerId": container_id,
            "declaredImage": declared,
            "containerImageId": image_id,
            "imageInspectId": image_id,
            "repoDigests": [f"{repository}@sha256:{digit * 64}"],
            "composeProjectLabel": project,
            "composeServiceLabel": service,
            "queries": {
                "containerInspect": {
                    "command": ["docker", "inspect", "--format",
                                performance_campaign.CONTAINER_IMAGE_INSPECT_FORMAT,
                                container_id],
                    "returnCode": 0,
                    "stdout": (f"{container_id}\t{image_id}\t{declared}\t"
                               f"{project}\t{service}\n"),
                    "stderr": "",
                },
                "imageInspect": {
                    "command": ["docker", "image", "inspect", "--format",
                                performance_campaign.IMAGE_INSPECT_FORMAT, declared],
                    "returnCode": 0,
                    "stdout": (f"{image_id}\t"
                               f"{json.dumps([f'{repository}@sha256:{digit * 64}'])}\n"),
                    "stderr": "",
                },
            },
        }
    return {
        "schemaVersion": 1, "capturedAt": "2026-08-28T00:00:00+00:00",
        "composeProject": project, "services": services,
    }


def test_expected_runtime_images_match_compose_contract():
    root = Path(__file__).parents[1]
    base = yaml.safe_load((
        root / "modules/teastore/deployment/compose/docker-compose_kieker.yaml"
    ).read_text())
    broker = yaml.safe_load((
        root / "modules/teastore/deployment/compose/docker-compose_rabbitmq.yaml"
    ).read_text())
    observed = {
        service: row["image"]
        for service, row in {**base["services"], **broker["services"]}.items()
    }
    assert observed == performance_campaign.EXPECTED_RUNTIME_IMAGES


def test_direct_run_one_is_construction_blocked_before_artifacts_or_commands(
        tmp_path, monkeypatch):
    calls: list[str] = []

    def planted_resources():
        calls.append("project-resources")
        return clean_resource_proof()

    def planted_command(*_args, **_kwargs):
        calls.append("command")
        raise RuntimeError("planted external command")

    monkeypatch.setattr(performance_campaign, "project_resources", planted_resources)
    monkeypatch.setattr(performance_campaign, "command", planted_command)
    root = tmp_path / "direct-run"
    with pytest.raises(RuntimeError, match="construction blocked"):
        performance_campaign.run_one(
            root, "b01-none", "none", argparse.Namespace(fault="none"),
        )
    assert calls == []
    assert not root.exists()


def test_cli_main_is_construction_blocked_before_output_schedule_or_docker(
        tmp_path, monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        performance_campaign, "project_resources",
        lambda: calls.append("project-resources"),
    )
    monkeypatch.setattr(
        performance_campaign.Path, "mkdir",
        lambda *_args, **_kwargs: calls.append("mkdir"),
    )
    monkeypatch.setattr(
        performance_campaign.Path, "write_text",
        lambda *_args, **_kwargs: calls.append("write-text"),
    )
    monkeypatch.setattr(
        sys, "argv", [
            "performance_campaign.py",
            "--output", str(tmp_path / "never-created"),
            "--framework-commit", "a" * 40,
            "--sut-reference-commit", "b" * 40,
            "--descriptor-id", "candidate",
            "--descriptor-sha256", "c" * 64,
            "--evidence-label", "smoke-validation",
        ],
    )
    with pytest.raises(RuntimeError, match="construction blocked"):
        performance_campaign.main()
    assert calls == []
    assert not (tmp_path / "never-created").exists()


@pytest.mark.parametrize(
    ("environment", "expected_state"),
    [(["JAVA_HOME=/opt/java"], "absent"), (["LOG_PARAMETERS=false"], "false")],
)
def test_candidate_service_log_capture_uses_exact_measurement_argv_and_env_proof(
    tmp_path, monkeypatch, environment, expected_state,
):
    runtime_images = runtime_image_fixture()
    calls: list[list[str]] = []

    def fake_command(argv, **_kwargs):
        calls.append(list(argv))
        if argv[:2] == ["docker", "logs"]:
            service = "auth" if argv[-1] == "2" * 64 else "persistence"
            return subprocess.CompletedProcess(argv, 0, f"{service}-bounded\n", "")
        assert argv[:3] == ["docker", "inspect", "--format"]
        return subprocess.CompletedProcess(argv, 0, json.dumps(environment) + "\n", "")

    monkeypatch.setattr(performance_campaign, "command", fake_command)
    proof = performance_campaign.capture_candidate_service_logs(
        tmp_path,
        runtime_images,
        measurement_started_at="2026-08-30T02:00:00+00:00",
        measurement_ended_at="2026-08-30T02:10:00+00:00",
    )
    assert calls[:2] == [
        ["docker", "logs", "--since", "2026-08-30T02:00:00+00:00",
         "--until", "2026-08-30T02:10:00+00:00", "2" * 64],
        ["docker", "logs", "--since", "2026-08-30T02:00:00+00:00",
         "--until", "2026-08-30T02:10:00+00:00", "3" * 64],
    ]
    assert proof["logParameters"]["state"] == expected_state
    assert proof["logParameters"]["parameterLoggingEnabled"] is False
    assert (tmp_path / "candidate-auth.log").read_text() == "auth-bounded\n"
    assert (tmp_path / "candidate-persistence.log").read_text() == "persistence-bounded\n"


def test_candidate_service_log_capture_watches_enabled_parameter_logging(
    tmp_path, monkeypatch,
):
    def fake_command(argv, **_kwargs):
        if argv[:2] == ["docker", "logs"]:
            return subprocess.CompletedProcess(argv, 0, "bounded\n", "")
        return subprocess.CompletedProcess(
            argv, 0, json.dumps(["LOG_PARAMETERS=true"]) + "\n", "",
        )

    monkeypatch.setattr(performance_campaign, "command", fake_command)
    with pytest.raises(RuntimeError, match="not exactly false"):
        performance_campaign.capture_candidate_service_logs(
            tmp_path,
            runtime_image_fixture(),
            measurement_started_at="2026-08-30T02:00:00+00:00",
            measurement_ended_at="2026-08-30T02:10:00+00:00",
        )


@pytest.mark.parametrize("payload", ('{"state":1,"state":2}', '{"state":NaN}'))
def test_candidate_intermediate_json_rejects_duplicate_keys_and_nonfinite_values(
    tmp_path, payload,
):
    path = tmp_path / "planted.json"
    path.write_text(payload)
    with pytest.raises(RuntimeError):
        performance_campaign._candidate_json(path, "planted candidate input")


def queue_state_fixture(messages, consumers, container_id="e" * 64):
    stdout = f"kieker\t{messages}\t{consumers}\n"
    command = ["docker", "exec", container_id, "rabbitmqctl", "list_queues",
               "-q", "name", "messages", "consumers"]
    return {
        "containerId": container_id, "messages": messages, "consumers": consumers,
        "query": {"command": command, "returnCode": 0, "stdout": stdout, "stderr": ""},
    }


BROKER_CLIENT_PROPERTIES = '[{"product","RabbitMQ"},{"platform","Java"}]'


def broker_connection_fixture(timeout, peer="172.18.0.5"):
    return {"user": "admin", "peerHost": peer, "timeoutSeconds": timeout,
            "clientProperties": BROKER_CLIENT_PROPERTIES}


def broker_proof_fixture(container_id="e" * 64, timeouts=(0, 900, 900, 900, 900, 900)):
    """Observed shape of rabbitmq:3-management de912cbb (verified 2026-09-05).

    The 0 is the pika collector (heartbeat=None accepts the broker's 0); the 900s
    are the Java writers, which cannot request 0 and so request 900 instead.
    """
    def query(argv, stdout):
        return {"command": argv, "returnCode": 0, "stdout": stdout, "stderr": ""}
    base = ["docker", "exec", container_id, "rabbitmqctl"]
    connections = [broker_connection_fixture(timeout) for timeout in timeouts]
    rows = "".join(
        f"admin\t{row['peerHost']}\t{row['timeoutSeconds']}\t{BROKER_CLIENT_PROPERTIES}\n"
        for row in connections
    )
    return {
        "schemaVersion": 2,
        "queries": {
            "heartbeat": query(base + ["eval", "application:get_env(rabbit, heartbeat)."],
                               "{ok,0}\n"),
            "queueArguments": query(base + ["list_queues", "-q", "name", "arguments"],
                                    'kieker\t[{"x-max-length",50000},'
                                    '{"x-overflow","reject-publish"}]\n'),
            "connections": query(
                base + ["list_connections", "-q",
                        *performance_campaign.BROKER_CONNECTION_FIELDS],
                "\t".join(performance_campaign.BROKER_CONNECTION_FIELDS) + "\n" + rows),
        },
        "heartbeatSeconds": 0,
        "queueArguments": 'kieker\t[{"x-max-length",50000},{"x-overflow","reject-publish"}]',
        "connections": connections,
        "connectionTimeouts": [row["timeoutSeconds"] for row in connections],
    }


def queue_proof_fixture():
    container_id = "e" * 64
    return {
        "schemaVersion": 2, "composeProject": "obst-test",
        "broker": broker_proof_fixture(container_id),
        "purge": {
            "before": queue_state_fixture(7, 0, container_id),
            "command": {
                "command": ["docker", "exec", container_id, "rabbitmqctl",
                            "purge_queue", "kieker"],
                "returnCode": 0, "stdout": "Purging queue 'kieker'\n", "stderr": "",
            },
            "after": queue_state_fixture(0, 0, container_id),
        },
        "measurement": {
            "before": queue_state_fixture(0, 0, container_id),
            "consumerAtStart": queue_state_fixture(0, 1, container_id),
            "after": queue_state_fixture(0, 0, container_id),
            "depthSamples": [
                {"monotonicOffsetSeconds": float(offset), "messages": 12, "consumers": 1}
                for offset in range(0, 600, 5)
            ],
        },
    }


def test_collector_barrier_acknowledgement_brackets_the_exact_queue_query(monkeypatch):
    events = []
    wall_times = iter(("2026-08-28T17:00:00.250000+00:00",
                       "2026-08-28T17:00:00.750000+00:00"))
    monotonic_times = iter((500.25, 500.75))
    state = queue_state_fixture(0, 1)

    def fake_now():
        events.append("wall")
        return next(wall_times)

    def fake_monotonic():
        events.append("monotonic")
        return next(monotonic_times)

    def fake_queue_state(posture):
        events.append(f"queue:{posture}")
        return state

    monkeypatch.setattr(performance_campaign, "now", fake_now)
    monkeypatch.setattr(performance_campaign.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(performance_campaign, "queue_state", fake_queue_state)

    acknowledgement = performance_campaign.collector_barrier_acknowledgement(
        "full", 500.0)

    assert events == ["wall", "monotonic", "queue:full", "wall", "monotonic"]
    assert acknowledgement == {
        "queryStartedAtWall": "2026-08-28T17:00:00.250000+00:00",
        "queryStartedMonotonicOffsetSeconds": 0.25,
        "queryCompletedAtWall": "2026-08-28T17:00:00.750000+00:00",
        "queryCompletedMonotonicOffsetSeconds": 0.75,
        "queueState": state,
    }
    assert "observedAt" not in acknowledgement


def test_measurement_barrier_lead_covers_bounded_probe_inventory_queries():
    assert performance_campaign.RESOURCE_INTERVAL_SECONDS == 5.0
    assert performance_campaign.RESOURCE_COMMAND_TIMEOUT_SECONDS == 4.0
    assert performance_campaign.RESOURCE_MAXIMUM_START_LATENESS_SECONDS == 1.0
    assert performance_campaign.MEASUREMENT_BARRIER_LEAD_SECONDS >= (
        2 * performance_campaign.RESOURCE_COMMAND_TIMEOUT_SECONDS + 5.0
    )


def test_cost_and_effect_runs_have_disjoint_resource_claim_surfaces(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    barrier = "barrier-" + "a" * 32
    cost = performance_campaign.analysis_contract("none")
    effect = performance_campaign.analysis_contract("auth-freeze")
    assert cost == {
        "analysisKind": "cost", "resourceUse": "cost-proxy",
        "usesPerformanceProbe": True,
    }
    assert effect == {
        "analysisKind": "effect", "resourceUse": "diagnostic-only",
        "usesPerformanceProbe": False,
    }
    assert performance_campaign.measurement_participants("none") == [
        "workload", "performance-probe", "collector"]
    assert performance_campaign.measurement_participants("auth-freeze") == [
        "workload", "collector", "intervention-controller"]
    assert performance_campaign.performance_probe_command(
        "auth-freeze", tmp_path, 60, 1000.0, barrier) is None
    cost_command = performance_campaign.performance_probe_command(
        "none", tmp_path, 60, 1000.0, barrier)
    assert cost_command is not None
    assert "modules/teastore/collectors/performance_probe_v3.py" in cost_command
    assert str(tmp_path / "resources.json") in cost_command


def test_system_probe_runs_in_every_cell_outside_the_barrier(monkeypatch, tmp_path):
    """sys lineage: one command for cost and fault cells; never a barrier participant."""
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    command = performance_campaign.system_probe_command(tmp_path, 600, 1000.0)
    assert command[:3] == ["/usr/bin/python3", "-I", "modules/teastore/collectors/system_probe.py"]
    options = dict(zip(command[3::2], command[4::2]))
    assert options["--project"] == "obst-test"
    assert options["--interval"] == "5.0" and options["--duration"] == "600"
    assert options["--start-at-epoch"] == "1000.0"
    assert options["--output"] == str(tmp_path / "system-samples.json")
    assert [command[i + 1] for i, value in enumerate(command) if value == "--require-service"] == list(
        performance_campaign.APP_SERVICES)
    assert (Path(__file__).parents[1] / command[2]).is_file()
    for fault in ("none", "auth-freeze", "persistence-crash"):
        assert not any("system" in name
                       for name in performance_campaign.measurement_participants(fault))
    assert "system-samples.json" in performance_campaign.CANDIDATE_COMMON_ARTIFACTS


def test_collector_stats_parses_success_path_regression():
    expected = valid_collector_stats()
    value = performance_campaign.collector_stats(f"prefix {json.dumps(expected, indent=2)} suffix")
    assert value == expected
    assert value["records_bad"] == 0


def test_collector_stats_requires_exactly_one_complete_summary():
    expected = valid_collector_stats()
    for stderr, diagnostic in (
        ("no summary", "found 0"),
        (f"{json.dumps(expected)}\n{json.dumps(expected)}", "found 2"),
        (json.dumps({key: value for key, value in expected.items() if key != "messages"}), "missing"),
    ):
        try:
            performance_campaign.collector_stats(stderr)
        except RuntimeError as exc:
            assert diagnostic in str(exc)
        else:
            raise AssertionError("incomplete or ambiguous collector output must fail closed")


def test_collector_stats_rejects_inconsistent_ratios():
    value = valid_collector_stats(records_bad=1, record_parse_success_ratio=1.0)
    try:
        performance_campaign.collector_stats(json.dumps(value))
    except RuntimeError as exc:
        assert "disagrees" in str(exc)
    else:
        raise AssertionError("a flattering ratio that disagrees with raw counts must be rejected")


def test_collector_invocation_overrides_ambient_auto_ack_and_gate_rejects_forgery():
    environment = performance_campaign.collector_subprocess_environment({
        "RABBITMQ_AUTO_ACK": "true",
        "SUT_TRACE_SERVICE_REGEX": "a^",
        "SUT_TRACE_SERVICE_MAP": '{"webui":"auth"}',
        "SUT_TRACE_HOST_SERVICE_MAP": '{"attacker":"auth"}',
        "PATH": os.environ["PATH"],
    })
    assert environment["SUT_TRACE_SERVICE_REGEX"] == (
        performance_campaign.COLLECTOR_FROZEN_SERVICE_REGEX
    )
    assert json.loads(environment["SUT_TRACE_SERVICE_MAP"]) == (
        performance_campaign.COLLECTOR_FROZEN_SERVICE_MAP
    )
    assert "SUT_TRACE_HOST_SERVICE_MAP" not in environment
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from collectors.kieker_native import KiekerNativeCollector; "
                "print(KiekerNativeCollector().stats()['acknowledgement_mode'])"
            ),
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "manual"

    forged = performance_campaign.collector_stats(json.dumps(
        valid_collector_stats(acknowledgement_mode="automatic")
    ))
    assert any(
        "acknowledgement mode was not manual" in blocker
        for blocker in performance_campaign.collector_process_blockers(
            0, None, forged, None,
        )
    )


@pytest.mark.parametrize("variable,value", [
    ("SUT_TRACE_SERVICE_REGEX", "a^"),
    ("SUT_TRACE_SERVICE_MAP", '{"store":"persistence"}'),
    ("SUT_TRACE_HOST_SERVICE_MAP", '{"attacker":"auth"}'),
])
def test_collector_direct_invocation_rejects_ambient_attribution_injection(
    monkeypatch, variable, value,
):
    monkeypatch.setenv(variable, value)
    with pytest.raises(kieker_native.ServiceAttributionError):
        kieker_native.KiekerNativeCollector()


@pytest.mark.parametrize("defect", ["digest", "regex"])
def test_candidate_collector_stats_reject_attribution_digest_or_content_drift(defect):
    stats = kieker_native.KiekerNativeCollector().stats()
    if defect == "digest":
        stats["attribution_configuration_sha256"] = "0" * 64
    else:
        stats["attribution_configuration"]["serviceRegex"] = "a^"
        stats["attribution_configuration_sha256"] = hashlib.sha256(
            json.dumps(
                stats["attribution_configuration"], sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    with pytest.raises(RuntimeError, match="attribution configuration"):
        performance_campaign.collector_stats(
            json.dumps(stats), require_attribution_binding=True,
        )


def test_real_collector_boundary_blocks_planted_missing_parent(tmp_path):
    runtime = tmp_path / "runtime-images.json"
    runtime.write_text(json.dumps({
        "schemaVersion": 1,
        "services": {"webui": {"containerId": "a" * 64}},
    }) + "\n")
    collector = kieker_native.KiekerNativeCollector(runtime_images_path=runtime)
    body = kieker_native.build_fixture([{
        "class_name": kieker_native.OER_CLASS,
        "operationSignature": (
            "public void tools.descartes.teastore.webui.Home.render()"
        ),
        "sessionId": "fixture",
        "traceId": 42,
        "tin": 1_000,
        "tout": 2_000,
        "hostname": "a" * 12,
        "eoi": 2,
        "ess": 1,
    }])
    events = collector.handle_body(body)
    parsed = performance_campaign.collector_stats(json.dumps(collector.stats()))
    # A missing root under the default (entry point assumed woven) still blocks,
    # now via the precise message that distinguishes it from a genuine error.
    blockers = performance_campaign.collector_process_blockers(
        0, None, parsed, None,
    )
    assert any("missing native trace roots" in blocker for blocker in blockers)
    assert not any("parent correlation errors" in blocker for blocker in blockers)
    assert performance_campaign.collector_event_blockers(events, parsed) == []


def test_missing_root_is_accepted_only_when_entry_point_is_unwoven(tmp_path):
    """F-ADH-064: a lone missing depth-0 parent is expected when the trace-root
    sensor is not woven, but a genuine correlation error still blocks there."""
    runtime = tmp_path / "runtime-images.json"
    runtime.write_text(json.dumps({
        "schemaVersion": 1,
        "services": {"webui": {"containerId": "a" * 64}},
    }) + "\n")

    def stats_for(eoi, ess):
        collector = kieker_native.KiekerNativeCollector(runtime_images_path=runtime)
        collector.handle_body(kieker_native.build_fixture([{
            "class_name": kieker_native.OER_CLASS,
            "operationSignature": (
                "public void tools.descartes.teastore.webui.Home.render()"
            ),
            "sessionId": "fixture", "traceId": 42, "tin": 1_000, "tout": 2_000,
            "hostname": "a" * 12, "eoi": eoi, "ess": ess,
        }]))
        return performance_campaign.collector_stats(json.dumps(collector.stats()))

    # Depth-0 missing root, posture forbids the entry point -> accepted.
    unwoven = performance_campaign.collector_process_blockers(
        0, None, stats_for(2, 1), None, entry_point_woven=False)
    assert not any("parent correlation errors" in b for b in unwoven)
    assert not any("missing native trace roots" in b for b in unwoven)

    # Same event, entry point woven -> a missing root is real loss and blocks.
    woven = performance_campaign.collector_process_blockers(
        0, None, stats_for(2, 1), None, entry_point_woven=True)
    assert any("missing native trace roots" in b for b in woven)

    # A deeper missing parent is a genuine error and blocks even when the entry
    # point is unwoven.
    genuine = performance_campaign.collector_process_blockers(
        0, None, stats_for(3, 2), None, entry_point_woven=False)
    assert any("parent correlation errors" in b for b in genuine)


def _single_native_oer_body():
    return kieker_native.build_fixture([{
        "class_name": kieker_native.OER_CLASS,
        "operationSignature": (
            "public void tools.descartes.teastore.webui.Home.render()"
        ),
        "sessionId": "fixture",
        "traceId": 42,
        "tin": 1_000,
        "tout": 2_000,
        "hostname": "webui",
        "eoi": 0,
        "ess": 0,
    }])


@pytest.mark.parametrize("class_name", [
    "attacker.shadow.OperationExecutionRecord",
    "attacker.shadow.OperationExecutionWithParametersRecord",
])
def test_native_parser_rejects_suffix_lookalike_record_classes(class_name):
    raw = kieker_native.build_fixture([{
        "class_name": class_name,
        "operationSignature": (
            "public void tools.descartes.teastore.webui.Home.render()"
        ),
        "sessionId": "fixture", "traceId": 42,
        "tin": 1_000, "tout": 2_000, "hostname": "webui",
        "eoi": 0, "ess": 0,
    }])
    with pytest.raises(kieker_native.ContainerParseError, match="unconsumed"):
        kieker_native.parse_container(raw)
    collector = kieker_native.KiekerNativeCollector()
    assert collector.handle_body(raw) == []
    assert collector.n_containers_bad == 1
    assert collector.n_records_bad == 0


def test_real_boundary_blocks_unconsumed_native_record_bytes():
    valid = _single_native_oer_body()
    records_length = struct.unpack_from(">i", valid, len(valid) - 4)[0]
    records_end = 8 + records_length
    valid_plus_tail = (
        valid[:records_end] + b"\x00" + valid[records_end:-4]
        + struct.pack(">i", records_length + 1)
    )
    short_only = (
        struct.pack(">ii", kieker_native.CONTAINER_IDENTIFIER,
                    kieker_native.FORMAT_IDENTIFIER)
        + b"\x00" + b"\x00" + struct.pack(">i", 1)
    )

    for planted in (valid_plus_tail, short_only):
        collector = kieker_native.KiekerNativeCollector()
        assert collector.handle_body(planted) == []
        stats = performance_campaign.collector_stats(
            json.dumps(collector.stats())
        )
        assert stats["containers_ok"] == 0
        assert stats["containers_bad"] == 1
        assert stats["records_ok"] == 0
        assert any(
            "container parse failures" in blocker
            for blocker in performance_campaign.collector_process_blockers(
                0, None, stats, None,
            )
        )


def test_native_parser_rejects_other_noncanonical_lengths_and_registry_data():
    valid = _single_native_oer_body()
    records_length = struct.unpack_from(">i", valid, len(valid) - 4)[0]
    records_end = 8 + records_length
    negative_length = valid[:-4] + struct.pack(">i", -1)
    registry_tail = valid[:-4] + b"\x00" + valid[-4:]
    invalid_utf8_registry = (
        struct.pack(">ii", kieker_native.CONTAINER_IDENTIFIER,
                    kieker_native.FORMAT_IDENTIFIER)
        + b"\x01\x01\xff" + struct.pack(">i", 0)
    )

    for planted in (negative_length, registry_tail, invalid_utf8_registry):
        try:
            kieker_native.parse_container(planted)
        except kieker_native.ContainerParseError:
            pass
        else:
            raise AssertionError("noncanonical container must fail")

    out_of_range_string = bytearray(valid)
    struct.pack_into(">i", out_of_range_string, 20, 999)
    try:
        kieker_native.parse_container(bytes(out_of_range_string))
    except kieker_native.ContainerParseError as exc:
        assert "unconsumed records-region bytes" in str(exc)
    else:
        raise AssertionError("out-of-range registry id must fail")


def test_native_parser_rejects_negative_string_array_length():
    body = kieker_native.build_fixture([{
        "class_name": kieker_native.OEWPR_CLASS,
        "operationSignature": (
            "public void tools.descartes.teastore.webui.Home.render()"
        ),
        "sessionId": "fixture",
        "traceId": 42,
        "tin": 1_000,
        "tout": 2_000,
        "hostname": "webui",
        "eoi": 0,
        "ess": 0,
        "parameterTypes": [],
        "parameterValues": [],
        "returnType": "void",
        "returnValue": "",
    }])
    planted = bytearray(body)
    struct.pack_into(">i", planted, 64, -1)
    try:
        kieker_native.parse_container(bytes(planted))
    except kieker_native.ContainerParseError as exc:
        assert "unconsumed records-region bytes" in str(exc)
    else:
        raise AssertionError("negative string-array length must fail")


def test_real_boundary_blocks_reversed_native_timing_and_no_trace_sentinel():
    for field, value, diagnostic in (
        ("tout", 999, "native tout precedes tin"),
        ("traceId", -1, "no-trace sentinel"),
    ):
        record = {
            "class_name": kieker_native.OER_CLASS,
            "operationSignature": (
                "public void tools.descartes.teastore.webui.Home.render()"
            ),
            "sessionId": "fixture",
            "traceId": 42,
            "tin": 1_000,
            "tout": 2_000,
            "hostname": "webui",
            "eoi": 0,
            "ess": 0,
        }
        record[field] = value
        collector = kieker_native.KiekerNativeCollector()
        assert collector.handle_body(kieker_native.build_fixture([record])) == []
        stats = performance_campaign.collector_stats(
            json.dumps(collector.stats())
        )
        assert stats["records_ok"] == 0
        assert stats["records_bad"] == 1
        assert any(
            "record parse failures" in blocker
            for blocker in performance_campaign.collector_process_blockers(
                0, None, stats, None,
            )
        )
        parsed = kieker_native.parse_container(
            kieker_native.build_fixture([record])
        )
        assert diagnostic in parsed[0]["_err"]


def test_collector_and_probe_failures_are_blockers():
    blockers = performance_campaign.collector_process_blockers(
        7, 9, valid_collector_stats(), None)
    assert "collector process failed with return code 7" in blockers
    assert "performance probe failed with return code 9" in blockers
    parse_blockers = performance_campaign.collector_process_blockers(
        0, 0, valid_collector_stats(containers_bad=1,
                                    container_parse_success_ratio=2 / 3), None)
    assert any("container parse failures" in item for item in parse_blockers)


def test_effect_smoke_allows_one_bad_record_but_never_a_bad_container():
    one_bad_record = valid_collector_stats(
        records_bad=1, record_parse_success_ratio=4 / 5,
    )
    assert performance_campaign.collector_process_blockers(
        0, None, one_bad_record, None, effect_contract=True,
    ) == []

    assert any(
        "record parse failures" in item
        for item in performance_campaign.collector_process_blockers(
            0, None,
            valid_collector_stats(
                records_bad=2, record_parse_success_ratio=4 / 6,
            ),
            None,
            effect_contract=True,
        )
    )
    assert any(
        "container parse failures" in item
        for item in performance_campaign.collector_process_blockers(
            0, None,
            valid_collector_stats(
                containers_bad=1, container_parse_success_ratio=2 / 3,
            ),
            None,
            effect_contract=True,
        )
    )
    assert any(
        "record parse failures" in item
        for item in performance_campaign.collector_process_blockers(
            0, 0, one_bad_record, None,
        )
    )


def test_workload_return_code_is_regime_and_terminal_outcome_specific():
    for fault, failed, timed_out, expected in (
        ("none", 0, 0, 0),
        ("none", 1, 0, 2),
        ("none", 0, 1, 2),
        ("persistence-crash", 0, 0, 0),
        ("persistence-crash", 1, 0, 2),
        ("auth-freeze", 0, 1, 2),
    ):
        assert performance_campaign.expected_workload_return_code(
            fault, {"failed": failed, "timedOut": timed_out},
        ) == expected

    effect = {"offered": 90, "failed": 6, "timedOut": 0}
    assert performance_campaign.workload_process_blockers(
        "persistence-crash", effect, 2,
    ) == []
    blockers = performance_campaign.workload_process_blockers(
        "persistence-crash", effect, 0,
    )
    assert any("return code differs" in item for item in blockers)

    cost = {"offered": 90, "failed": 0, "timedOut": 1}
    blockers = performance_campaign.workload_process_blockers("none", cost, 2)
    assert any("timed out" in item for item in blockers)
    assert not any("return code differs" in item for item in blockers)


def test_deliberately_absent_effect_probe_is_not_a_process_blocker():
    assert performance_campaign.collector_process_blockers(
        0, None, valid_collector_stats(), None) == []


def test_runtime_images_capture_exact_started_image_identity(monkeypatch):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    fixture = runtime_image_fixture()
    by_container = {
        item["containerId"]: (service, item)
        for service, item in fixture["services"].items()
    }
    by_declared = {item["declaredImage"]: item for item in fixture["services"].values()}
    monkeypatch.setattr(
        performance_campaign, "service_container",
        lambda _posture, service: fixture["services"][service]["containerId"])

    def fake_command(args, **_kwargs):
        if args[:2] == ["docker", "inspect"]:
            service, item = by_container[args[-1]]
            value = (f"{item['containerId']}\t{item['containerImageId']}\t"
                     f"{item['declaredImage']}\tobst-test\t{service}\n")
        elif args[:3] == ["docker", "image", "inspect"]:
            item = by_declared[args[-1]]
            value = f"{item['imageInspectId']}\t{json.dumps(item['repoDigests'])}\n"
        else:
            raise AssertionError(f"unexpected image proof command: {args}")
        return subprocess.CompletedProcess(args, 0, value, "")

    monkeypatch.setattr(performance_campaign, "command", fake_command)
    proof = performance_campaign.runtime_image_proof("full")
    performance_campaign.validate_runtime_images(proof)
    assert set(proof["services"]) == set(performance_campaign.RUNTIME_SERVICES)
    assert all(item["containerImageId"] == item["imageInspectId"]
               for item in proof["services"].values())
    assert all(item["repoDigests"] for item in proof["services"].values())


def test_runtime_image_proof_rejects_planted_identity_defects(monkeypatch):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    for mutation, diagnostic in (
        (lambda proof: proof["services"]["webui"].update(imageInspectId="sha256:" + "f" * 64),
         "image IDs disagree"),
        (lambda proof: proof["services"]["auth"].update(repoDigests=[]),
         "repository digests are incomplete"),
        (lambda proof: proof["services"].pop("db"), "service set differs"),
    ):
        proof = runtime_image_fixture()
        mutation(proof)
        try:
            performance_campaign.validate_runtime_images(proof)
        except RuntimeError as exc:
            assert diagnostic in str(exc)
        else:
            raise AssertionError("planted runtime-image identity defect was accepted")


def test_candidate_runtime_image_proof_accepts_local_ids_and_watches_substitution(
    monkeypatch,
):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    proof = runtime_image_fixture()
    expected = {}
    for service, item in proof["services"].items():
        item["repoDigests"] = []
        item["queries"]["imageInspect"]["stdout"] = (
            f"{item['imageInspectId']}\tnull\n"
        )
        expected[service] = f"candidate/{service}@{item['containerImageId']}"
    performance_campaign.validate_runtime_images(
        proof, expected_content_references=expected,
    )
    defect = dict(expected)
    defect["auth"] = "candidate/auth@sha256:" + "0" * 64
    with pytest.raises(RuntimeError, match="target-built image ID differs for auth"):
        performance_campaign.validate_runtime_images(
            proof, expected_content_references=defect,
        )


def test_runtime_image_proof_rejects_self_consistent_unexpected_image(monkeypatch):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    proof = runtime_image_fixture()
    item = proof["services"]["auth"]
    unexpected = "attacker.example/teastore-auth:test"
    digest = f"attacker.example/teastore-auth@sha256:{'a' * 64}"
    item["declaredImage"] = unexpected
    item["repoDigests"] = [digest]
    item["queries"]["containerInspect"]["stdout"] = (
        f"{item['containerId']}\t{item['containerImageId']}\t{unexpected}\t"
        "obst-test\tauth\n"
    )
    item["queries"]["imageInspect"]["command"][-1] = unexpected
    item["queries"]["imageInspect"]["stdout"] = (
        f"{item['imageInspectId']}\t{json.dumps([digest])}\n"
    )
    try:
        performance_campaign.validate_runtime_images(proof)
    except RuntimeError as exc:
        assert "deployment contract" in str(exc)
    else:
        raise AssertionError("self-consistent unexpected runtime image was accepted")


def test_queue_proof_rejects_planted_replay_and_exclusivity_defects(monkeypatch):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    performance_campaign.validate_queue_proof(queue_proof_fixture())
    for mutation, diagnostic in (
        (lambda proof: proof["measurement"].update(
            after=queue_state_fixture(3, 0)), "conditions were not proven"),
        (lambda proof: proof["measurement"].update(
            consumerAtStart=queue_state_fixture(0, 2)), "conditions were not proven"),
        (lambda proof: proof["purge"]["after"]["query"].update(
            stdout="kieker\t9\t0\n"), "disagrees with normalized counts"),
        # F-ADH-073: the campaign #6 loss mechanism, in three plants.
        (lambda proof: proof["broker"].update(heartbeatSeconds=None),
         "broker heartbeat is not disabled"),
        (lambda proof: proof["broker"].update(
            connections=[broker_connection_fixture(0),
                         broker_connection_fixture(60, peer="172.18.0.9"),
                         broker_connection_fixture(0)],
            connectionTimeouts=[0, 60, 0]),
         "172.18.0.9 negotiated 60s"),
        (lambda proof: proof["broker"].update(
            queueArguments='kieker\t[{"x-max-length",50000}]'),
         "overflow policy differs"),
        (lambda proof: proof["broker"].update(connections=[], connectionTimeouts=[]),
         "no AMQP connections"),
        # A mid-window burst that drains before the closing sample is invisible
        # to boundary states alone.
        (lambda proof: proof["measurement"]["depthSamples"].append(
            {"monotonicOffsetSeconds": 301.0, "messages": 30_000, "consumers": 1}),
         "reached 30000 of 50000"),
        (lambda proof: proof["measurement"].update(depthSamples=[]),
         "not sampled across the measurement window"),
        (lambda proof: proof["measurement"]["depthSamples"].append(
            {"monotonicOffsetSeconds": 301.0, "messages": 3, "consumers": 2}),
         "exclusivity lapsed mid-window"),
    ):
        proof = queue_proof_fixture()
        mutation(proof)
        try:
            performance_campaign.validate_queue_proof(proof)
        except RuntimeError as exc:
            assert diagnostic in str(exc)
        else:
            raise AssertionError("planted RabbitMQ replay/exclusivity defect was accepted")


def test_broker_heartbeat_floor_admits_only_pauses_that_outlive_the_fault():
    """F-ADH-075: 0 or >= the fault-pause floor passes; 60 (Kieker's silent
    DEFAULT_HEARTBEAT substitution for the heartbeat=0 sentinel) must not."""
    floor = performance_campaign.BROKER_HEARTBEAT_FLOOR_SECONDS
    assert floor >= performance_campaign.CANDIDATE_FAULT_OUTAGE_SECONDS

    def blockers(**broker_updates):
        proof = broker_proof_fixture()
        proof.update(broker_updates)
        if "connections" in broker_updates:
            proof["connectionTimeouts"] = [
                row["timeoutSeconds"] for row in proof["connections"]]
        return performance_campaign.broker_proof_blockers(proof)

    # Every connection at 0 -- pika's negotiated value -- is admissible.
    assert blockers(connections=[broker_connection_fixture(0)] * 3) == []
    # 900, what the Compose command override makes the Java writers request.
    assert blockers(connections=[broker_connection_fixture(t) for t in (0, 900, 900)]) == []
    assert blockers(connections=[broker_connection_fixture(floor)]) == []
    # 60 is the exact value that aborted campaign #7 at cell 1.
    offending = blockers(
        connections=[broker_connection_fixture(0),
                     broker_connection_fixture(60, peer="172.18.0.9")])
    assert len(offending) == 1
    assert f"{floor}s fault-pause floor" in offending[0]
    assert "172.18.0.9 negotiated 60s" in offending[0]
    # A value that survives the ifne-0 sentinel but still dies inside the pause.
    assert blockers(connections=[broker_connection_fixture(floor - 1)])
    assert blockers(connections=[]) == [
        "broker reported no AMQP connections at the barrier"]
    assert blockers(queueArguments='kieker\t[{"x-max-length",50000}]') == [
        "kieker queue overflow policy differs"]
    assert blockers(heartbeatSeconds=60) == ["broker heartbeat is not disabled"]


def test_broker_connection_rows_are_parsed_and_unparsable_rows_fail_closed():
    """Verbatim `rabbitmqctl -q list_connections user peer_host timeout
    client_properties` output from rabbitmq:3-management on fb14srv5."""
    stdout = (
        "user\tpeer_host\ttimeout\tclient_properties\n"
        'admin\t172.18.0.2\t900\t[{"product","RabbitMQ"},{"version","5.13.0"},'
        '{"platform","Java"}]\n'
    )
    assert performance_campaign.parse_broker_connections(stdout) == [{
        "user": "admin", "peerHost": "172.18.0.2", "timeoutSeconds": 900,
        "clientProperties": '[{"product","RabbitMQ"},{"version","5.13.0"},'
                            '{"platform","Java"}]',
    }]
    with pytest.raises(RuntimeError, match="malformed rabbitmqctl connection row"):
        performance_campaign.parse_broker_connections("admin\t172.18.0.2\tnone\t[]\n")


class FakeChild:
    def __init__(self, outcomes):
        self.pid = 4242
        self.args = ["python3", "child.py"]
        self.returncode = None
        self.outcomes = iter(outcomes)
        self.terminated = False
        self.killed = False
        self.waited = False

    def communicate(self, timeout):
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        if self.killed:
            self.returncode = -9
        elif self.terminated:
            self.returncode = -15
        else:
            self.returncode = 0
        return outcome

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout):
        self.waited = True
        if self.returncode is None:
            self.returncode = -9
        return self.returncode

    def poll(self):
        return self.returncode


def test_child_timeout_escalates_to_kill_and_is_joined():
    child = FakeChild([
        subprocess.TimeoutExpired(["python3", "child.py"], 1),
        subprocess.TimeoutExpired(["python3", "child.py"], 10),
        ("partial-out", "partial-err"),
    ])
    stdout, stderr, proof = performance_campaign.join_child_process(child, 1)
    assert (stdout, stderr) == ("partial-out", "partial-err")
    assert proof["timedOut"] is True
    assert proof["terminateSent"] is True
    assert proof["killSent"] is True
    assert proof["joined"] is True and proof["returnCode"] == -9


def test_child_communication_exception_terminates_and_is_joined():
    child = FakeChild([RuntimeError("pipe broke"), ("", "diagnostic")])
    stdout, stderr, proof = performance_campaign.join_child_process(child, 1)
    assert (stdout, stderr) == ("", "diagnostic")
    assert "pipe broke" in proof["communicationError"]
    assert proof["terminateSent"] is True
    assert proof["killSent"] is False
    assert proof["joined"] is True and proof["returnCode"] == -15
    assert proof["noProgressTimeoutSeconds"] is None


def test_watchdog_kills_stalled_child_before_the_hard_cap(tmp_path):
    heartbeat = tmp_path / "kieker-amqp.spool.heartbeat"
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    started = time.monotonic()
    stdout, stderr, proof = performance_campaign.join_child_process(
        child, 30, heartbeat_path=heartbeat, no_progress_timeout=0.5)
    assert time.monotonic() - started < 15
    assert proof["timedOut"] is True
    assert "no heartbeat progress for 0.5s" in proof["communicationError"]
    assert proof["terminateSent"] is True
    assert proof["joined"] is True and proof["returnCode"] != 0
    assert proof["noProgressTimeoutSeconds"] == 0.5


def test_watchdog_tolerates_slow_child_that_keeps_beating(tmp_path):
    heartbeat = tmp_path / "kieker-amqp.spool.heartbeat"
    script = (
        "import pathlib, sys, time\n"
        "beat = pathlib.Path(sys.argv[1])\n"
        "for _ in range(10):\n"
        "    beat.touch()\n"
        "    time.sleep(0.25)\n"
        "print('done')\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(heartbeat)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr, proof = performance_campaign.join_child_process(
        child, 30, heartbeat_path=heartbeat, no_progress_timeout=1.0)
    assert stdout.strip() == "done"
    assert proof["timedOut"] is False
    assert proof["communicationError"] is None
    assert proof["terminateSent"] is False and proof["killSent"] is False
    assert proof["joined"] is True and proof["returnCode"] == 0
    assert proof["noProgressTimeoutSeconds"] == 1.0


def _fault_image(container_id: str) -> dict:
    return {
        "containerId": container_id,
        "declaredImage": "descartesresearch/teastore-auth:latest",
        "containerImageId": "sha256:" + "1" * 64,
        "imageInspectId": "sha256:" + "1" * 64,
        "repoDigests": ["descartesresearch/teastore-auth@sha256:" + "2" * 64],
    }


def _fault_kwargs(container_id: str, *, barrier_monotonic: float = 0.0) -> dict:
    return {
        "measurement_barrier_epoch": 1_800_000_000.0,
        "measurement_barrier_monotonic": barrier_monotonic,
        "measurement_barrier_id": "barrier-" + "a" * 32,
        "target_image": _fault_image(container_id),
    }


def test_intervention_proves_manifestation_duration_and_recovery(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    container_id = "a" * 64
    monkeypatch.setattr(performance_campaign, "service_container",
                        lambda _posture, _service: container_id)
    states = iter((
        {"exists": True, "running": True, "paused": False},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": False},
    ))
    monkeypatch.setattr(performance_campaign, "container_state", lambda _container: next(states))
    monkeypatch.setattr(performance_campaign, "wait_ready", lambda: None)
    monotonic = iter((0.0, 0.0, 0.0, 15.0, 30.0, 31.0))
    monkeypatch.setattr(performance_campaign.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(performance_campaign.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(performance_campaign, "command", lambda _args, check=False:
                        subprocess.CompletedProcess(_args, 0, "", ""))
    receipt = performance_campaign.inject_fault(
        "auth-freeze", 240, 30, tmp_path, **_fault_kwargs(container_id))
    performance_campaign.bind_intervention_thread(receipt, tmp_path, joined=True)
    assert receipt["manifested"] is True
    assert receipt["outageHeld"] is True
    assert receipt["recovered"] is True
    assert receipt["successful"] is True
    assert receipt["sameTargetIdentity"] is True
    assert receipt["operational"]["continuousTargetStateProven"] is False
    assert receipt["readiness"]["observedAtMonotonicOffsetSeconds"] == 31.0
    assert [row["phase"] for row in receipt["duringStateSamples"]] == [
        "manifested", "hold-midpoint", "hold-end"]
    assert json.loads((tmp_path / "intervention.json").read_text())["successful"] is True


def test_intervention_exception_becomes_failed_receipt(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    monkeypatch.setattr(performance_campaign, "service_container",
                        lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(performance_campaign.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(performance_campaign.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(performance_campaign, "command", lambda *_args, **_kwargs:
                        (_ for _ in ()).throw(RuntimeError("boom")))
    receipt = performance_campaign.inject_fault(
        "auth-freeze", 1, 1, tmp_path, **_fault_kwargs("a" * 64))
    assert receipt["successful"] is False
    assert "RuntimeError" in receipt["error"]
    assert (tmp_path / "intervention.json").exists()


def test_intervention_rejects_unready_prestate(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    container_id = "a" * 64
    monkeypatch.setattr(performance_campaign, "service_container",
                        lambda _posture, _service: container_id)
    monkeypatch.setattr(performance_campaign, "container_state", lambda _container: {
        "exists": True, "running": False, "paused": False})
    monkeypatch.setattr(performance_campaign.time, "monotonic", lambda: 0.0)
    receipt = performance_campaign.inject_fault(
        "persistence-crash", 0, 1, tmp_path, **_fault_kwargs(container_id))
    assert receipt["successful"] is False
    assert "not ready before intervention" in receipt["error"]
    assert receipt["operational"]["commandResults"] == []


def test_intervention_rejects_state_loss_and_target_replacement(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    targets = iter(("a" * 64, "b" * 64))
    monkeypatch.setattr(performance_campaign, "service_container",
                        lambda _posture, _service: next(targets))
    states = iter((
        {"exists": True, "running": True, "paused": False},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": False},  # planted mid-hold loss
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": False},
    ))
    monkeypatch.setattr(performance_campaign, "container_state", lambda _container: next(states))
    monkeypatch.setattr(performance_campaign, "wait_ready", lambda: None)
    monkeypatch.setattr(performance_campaign.time, "sleep", lambda _seconds: None)
    monotonic = iter((0.0, 0.0, 0.0, 0.5, 1.0, 2.0))
    monkeypatch.setattr(performance_campaign.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(performance_campaign, "command", lambda args, check=False:
                        subprocess.CompletedProcess(args, 0, "", ""))
    receipt = performance_campaign.inject_fault(
        "auth-freeze", 0, 1, tmp_path, **_fault_kwargs("a" * 64))
    assert receipt["manifested"] is False
    assert receipt["sameTargetIdentity"] is False
    assert receipt["successful"] is False


def test_fault_controller_rejects_a_missed_shared_barrier(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    container_id = "a" * 64
    monkeypatch.setattr(performance_campaign, "service_container",
                        lambda _posture, _service: container_id)
    monkeypatch.setattr(performance_campaign, "container_state", lambda _container: {
        "exists": True, "running": True, "paused": False})
    monkeypatch.setattr(performance_campaign.time, "monotonic", lambda: 100.0)
    receipt = performance_campaign.inject_fault(
        "auth-freeze", 0, 1, tmp_path,
        **_fault_kwargs(container_id, barrier_monotonic=90.0))
    assert receipt["successful"] is False
    assert "missed the shared measurement barrier" in receipt["error"]


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
                              framework_commit="a" * 40,
                              sut_reference_commit="b" * 40,
                              selection_id="fault-qualification",
                              descriptor_id="teastore-diagnostic-smoke-v1",
                              descriptor_sha256="c" * 64,
                              evidence_label="smoke-validation")
    result = performance_campaign.campaign_configuration(args, ("selected", "full"))
    assert result["selectionId"] == "fault-qualification"
    assert result["frameworkCommit"] == "a" * 40
    assert result["sutReferenceCommit"] == "b" * 40
    assert result["activationManifestSha256"]
    assert result["selectionSourceSha256"]
    assert result["composeProject"] == "obst-test"
    assert result["descriptorId"] == "teastore-diagnostic-smoke-v1"
    assert result["descriptorSha256"] == "c" * 64
    assert result["evidenceLabel"] == "smoke-validation"
    assert result["collectorDurationSeconds"] == 130
    assert result["collectorInactivityTimeoutSeconds"] == 10


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
        framework_commit="abc1234", sut_reference_commit="b" * 40,
        descriptor_id="teastore-diagnostic-smoke-v1", descriptor_sha256="c" * 64,
        evidence_label="smoke-validation",
    )
    try:
        performance_campaign.validate_parameters(args)
    except ValueError as exc:
        assert "full 40-character" in str(exc)
    else:
        raise AssertionError("abbreviated framework provenance must fail closed")


def test_project_absence_proof_fails_closed_on_query_error(monkeypatch):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    calls = 0

    def fake_command(args, **_kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 17 if calls == 2 else 0, "", "query failed")

    monkeypatch.setattr(performance_campaign, "command", fake_command)
    proof = performance_campaign.project_resources()
    assert proof["queryPassed"] is False
    assert proof["queries"]["networks"]["returnCode"] == 17
    assert performance_campaign.resources_clean(proof) is False


def test_dirty_teardown_rewrites_receipt_as_noncanonical(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    receipt = {
        "posture": "full",
        "canonicality": {"label": "smoke-validation", "blockers": []},
    }
    down = {
        "schemaVersion": 1,
        "command": performance_campaign.compose("full", "down", "-v", "--remove-orphans"),
        "returnCode": 0, "stdout": "", "stderr": "",
    }
    dirty = clean_resource_proof()
    dirty["containers"] = ["still-running"]
    performance_campaign.bind_teardown(receipt, down, dirty, tmp_path, "smoke-validation")
    stored = json.loads((tmp_path / "receipt.json").read_text())
    assert stored["teardown"]["projectClean"] is False
    assert stored["canonicality"]["label"] == "noncanonical"
    assert "compose project teardown incomplete" in stored["canonicality"]["blockers"]


def test_existing_receipt_must_match_immutable_schedule(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({
        "runId": "b01-full", "posture": "full",
        "source": {"frameworkCommit": "wrong", "sutReferenceCommit": "sut",
                   "selectionId": "auth",
                   "selectionSourceSha256": "selection", "activationManifestSha256": None,
                   "descriptorId": "descriptor", "descriptorSha256": "d" * 64,
                   "evidenceLabel": "smoke-validation"},
        "canonicality": {"label": "smoke-validation", "blockers": []},
        "teardown": {"projectClean": True,
                     "downCommand": {"command": performance_campaign.compose(
                         "full", "down", "-v", "--remove-orphans"), "returnCode": 0},
                     "projectResources": clean_resource_proof()},
    }))
    configuration = {"frameworkCommit": "framework", "sutReferenceCommit": "sut",
                     "selectionId": "auth",
                     "selectionSourceSha256": "selection", "activationManifestSha256": "manifest",
                     "descriptorId": "descriptor", "descriptorSha256": "d" * 64,
                     "evidenceLabel": "smoke-validation"}
    try:
        performance_campaign.validate_existing_receipt(path, "b01-full", "full", configuration)
    except RuntimeError as exc:
        assert "frameworkCommit" in str(exc)
    else:
        raise AssertionError("stale receipt must not be silently resumed")


def test_existing_receipt_rejects_descriptor_substitution(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({
        "runId": "b01-full", "posture": "full",
        "source": {
            "frameworkCommit": "framework", "sutReferenceCommit": "sut",
            "selectionId": "auth",
            "selectionSourceSha256": "selection", "activationManifestSha256": None,
            "descriptorId": "descriptor", "descriptorSha256": "a" * 64,
            "evidenceLabel": "smoke-validation",
        },
        "canonicality": {"label": "smoke-validation", "blockers": []},
        "teardown": {
            "projectClean": True,
            "downCommand": {
                "command": performance_campaign.compose(
                    "full", "down", "-v", "--remove-orphans"),
                "returnCode": 0,
            },
            "projectResources": clean_resource_proof(),
        },
    }))
    configuration = {
        "frameworkCommit": "framework", "sutReferenceCommit": "sut",
        "selectionId": "auth",
        "selectionSourceSha256": "selection", "activationManifestSha256": "manifest",
        "descriptorId": "descriptor", "descriptorSha256": "b" * 64,
        "evidenceLabel": "smoke-validation",
    }
    try:
        performance_campaign.validate_existing_receipt(
            path, "b01-full", "full", configuration)
    except RuntimeError as exc:
        assert "descriptorSha256" in str(exc)
    else:
        raise AssertionError("a receipt from different descriptor bytes must not be resumed")


def test_existing_receipt_rejects_runtime_image_proof_substitution(monkeypatch,
                                                                   tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    runtime_path = tmp_path / "runtime-images.json"
    runtime_path.write_text(json.dumps(runtime_image_fixture(), sort_keys=True) + "\n")
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({
        "runId": "b01-full", "posture": "full",
        "source": {
            "frameworkCommit": "framework", "sutReferenceCommit": "sut",
            "selectionId": "auth", "selectionSourceSha256": "selection",
            "activationManifestSha256": None, "descriptorId": "descriptor",
            "descriptorSha256": "a" * 64, "evidenceLabel": "smoke-validation",
            "runtimeImagesSha256": "f" * 64,
        },
        "canonicality": {"label": "smoke-validation", "blockers": []},
        "teardown": {
            "projectClean": True,
            "downCommand": {
                "command": performance_campaign.compose(
                    "full", "down", "-v", "--remove-orphans"),
                "returnCode": 0,
            },
            "projectResources": clean_resource_proof(),
        },
    }))
    configuration = {
        "frameworkCommit": "framework", "sutReferenceCommit": "sut",
        "selectionId": "auth", "selectionSourceSha256": "selection",
        "activationManifestSha256": "manifest", "descriptorId": "descriptor",
        "descriptorSha256": "a" * 64, "evidenceLabel": "smoke-validation",
    }
    try:
        performance_campaign.validate_existing_receipt(
            path, "b01-full", "full", configuration)
    except RuntimeError as exc:
        assert "runtimeImagesSha256" in str(exc)
    else:
        raise AssertionError("a receipt bound to different runtime-image bytes was resumed")


def test_existing_effect_receipt_requires_collector_child_but_no_probe(monkeypatch,
                                                                       tmp_path: Path):
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-test")
    runtime_path = tmp_path / "runtime-images.json"
    runtime_path.write_text(json.dumps(runtime_image_fixture(), sort_keys=True) + "\n")
    queue_path = tmp_path / "queue-proof.json"
    queue_path.write_text(json.dumps(queue_proof_fixture(), sort_keys=True) + "\n")
    collector = {"joined": True, "returnCode": 0}
    system_probe = {"joined": True, "returnCode": 0}  # sys lineage: every cell
    children_path = tmp_path / "child-processes.json"
    children_path.write_text(json.dumps(
        {"collector": collector, "systemProbe": system_probe}, sort_keys=True) + "\n")
    configuration = {
        "frameworkCommit": "framework", "sutReferenceCommit": "sut",
        "selectionId": "auth", "selectionSourceSha256": "selection",
        "activationManifestSha256": "manifest", "descriptorId": "descriptor",
        "descriptorSha256": "a" * 64, "evidenceLabel": "smoke-validation",
        "fault": "auth-freeze",
    }
    receipt = {
        "runId": "b01-full", "posture": "full", "analysisKind": "effect",
        "resourceUse": "diagnostic-only", "resources": None,
        "source": {
            "frameworkCommit": "framework", "sutReferenceCommit": "sut",
            "selectionId": "auth", "selectionSourceSha256": "selection",
            "activationManifestSha256": None, "descriptorId": "descriptor",
            "descriptorSha256": "a" * 64, "evidenceLabel": "smoke-validation",
            "runtimeImagesSha256": performance_campaign.sha256(runtime_path),
            "queueProofSha256": performance_campaign.sha256(queue_path),
            "childProcessesSha256": performance_campaign.sha256(children_path),
        },
        "queue": {"proofSha256": performance_campaign.sha256(queue_path)},
        "processes": {"workload": {"returnCode": 0}, "collector": collector,
                      "systemProbe": system_probe},
        "canonicality": {"label": "smoke-validation", "blockers": []},
        "teardown": {
            "projectClean": True,
            "downCommand": {
                "command": performance_campaign.compose(
                    "full", "down", "-v", "--remove-orphans"),
                "returnCode": 0,
            },
            "projectResources": clean_resource_proof(),
        },
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    performance_campaign.validate_existing_receipt(
        path, "b01-full", "full", configuration)

    without_system = copy.deepcopy(receipt)
    del without_system["processes"]["systemProbe"]
    path.write_text(json.dumps(without_system, sort_keys=True) + "\n")
    with pytest.raises(RuntimeError, match="childProcesses"):
        performance_campaign.validate_existing_receipt(
            path, "b01-full", "full", configuration)
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n")

    receipt["processes"]["performanceProbe"] = {"joined": True, "returnCode": 0}
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    try:
        performance_campaign.validate_existing_receipt(
            path, "b01-full", "full", configuration)
    except RuntimeError as exc:
        assert "performanceProbe" in str(exc)
    else:
        raise AssertionError("effect receipt exposed a performance-probe child")


# --- F-ADH-074 exposure tolerance -------------------------------------------
# Timestamps are campaign #6's real auth-freeze cell.
C6_ONSET = "2026-09-04T06:01:31.824179+00:00"
C6_OFFSET = "2026-09-04T06:04:02.015639+00:00"
C6_READINESS = "2026-09-04T06:04:02.527193+00:00"


def c6_intervention(successful=True):
    return {
        "successful": successful,
        "actualOnsetWall": C6_ONSET,
        "actualOffsetWall": C6_OFFSET,
        "readiness": {"observedAtWall": C6_READINESS},
    }


def exposure_event(timestamp, eoi, *, trace="t1", errors=None, logged=None):
    return {"timestamp": timestamp, "collector_timestamp": timestamp if logged is None else logged,
            "eoi": eoi, "kieker_trace_id": trace, "correlation_errors": errors or []}


def c6_bounds():
    window = performance_campaign.exposure_window(c6_intervention(), "auth-freeze")
    return window["startEpoch"], window["endEpoch"]


def test_exposure_window_needs_a_proven_bounded_intervention():
    window = performance_campaign.exposure_window(c6_intervention(), "auth-freeze")
    assert abs(window["settleSeconds"] - 0.511554) < 1e-5
    assert window["marginSeconds"] == 0.0
    # No fault, an unproven intervention, or a missing readiness gives no window.
    assert performance_campaign.exposure_window(c6_intervention(), "none") is None
    assert performance_campaign.exposure_window(c6_intervention(False), "auth-freeze") is None
    assert performance_campaign.exposure_window(None, "auth-freeze") is None
    absurd = c6_intervention()
    absurd["readiness"] = {"observedAtWall": "2026-09-04T06:05:02.527193+00:00"}  # 60 s settle
    assert performance_campaign.exposure_window(absurd, "auth-freeze") is None


# --- F-ADH-085 the window starts at the scheduled onset --------------------
# Timestamps are TeaStore #12's aborted auth-freeze b01 full cell: the pause
# command was issued at the scheduled onset and the "manifested" inspect that
# stamps actualOnsetWall came 254 ms later; five auth executions logged 13 ms
# before that sample were counted residual and aborted the campaign.
C12_SCHEDULED = "2026-09-12T16:30:46.982759+00:00"
C12_ONSET = "2026-09-12T16:30:47.237090+00:00"
C12_OFFSET = "2026-09-12T16:33:17.376763+00:00"
C12_READINESS = "2026-09-12T16:33:17.864613+00:00"


def c12_intervention(scheduled=C12_SCHEDULED):
    return {
        "successful": True,
        "actualOnsetWall": C12_ONSET,
        "actualOffsetWall": C12_OFFSET,
        "readiness": {"observedAtWall": C12_READINESS},
        "measurementBarrier": {"scheduledOnsetWall": scheduled},
    }


def test_exposure_window_starts_at_the_scheduled_onset_when_retained():
    window = performance_campaign.exposure_window(c12_intervention(), "auth-freeze")
    onset = datetime.fromisoformat(C12_ONSET).timestamp()
    assert window["startEpoch"] == datetime.fromisoformat(C12_SCHEDULED).timestamp()
    assert abs(onset - window["startEpoch"] - 0.254331) < 1e-5
    assert set(window) == {"startEpoch", "endEpoch", "settleSeconds", "marginSeconds"}
    # The five events that aborted #12 sit inside the command span and are tolerated.
    logged = onset - 0.013
    events = [exposure_event(logged, 7 + i, errors=["conflicting-native-identity"])
              for i in range(5)]
    tolerance = performance_campaign.exposure_tolerance(
        events, c12_intervention(), fault="auth-freeze")
    assert tolerance["toleratedCorrelationErrorEvents"] == 5
    assert tolerance["residualCorrelationErrorEvents"] == 0
    # Before the scheduled onset nothing is excused.
    early = [exposure_event(window["startEpoch"] - 0.001, 7,
                            errors=["conflicting-native-identity"])]
    tolerance = performance_campaign.exposure_tolerance(
        early, c12_intervention(), fault="auth-freeze")
    assert tolerance["residualCorrelationErrorEvents"] == 1
    # Fixtures without a barrier (campaign #6 shape) keep the strict sample.
    assert c6_bounds()[0] == datetime.fromisoformat(C6_ONSET).timestamp()
    # An absent, unreadable, later, or implausibly early scheduled onset keeps it too.
    for bad in (None, "not-a-time", C12_OFFSET, "2026-09-12T16:29:47.237090+00:00"):
        window = performance_campaign.exposure_window(c12_intervention(bad), "auth-freeze")
        assert window["startEpoch"] == onset, bad


def test_in_window_gap_bounded_by_an_enclosing_record_is_tolerated():
    low, high = c6_bounds()
    events = [exposure_event(low + 5, 0, logged=high - 1), exposure_event(low + 10, 4)]
    result = performance_campaign.exposure_tolerance(
        events, c6_intervention(), fault="auth-freeze")
    assert result["applied"] is True
    assert result["toleratedMissingEoiCount"] == 3
    assert result["toleratedEoiGapTraces"] == 1
    assert result["residualMissingEoiCount"] == 0
    assert performance_campaign.collector_process_blockers(
        0, 0, eoi_gap_stats(traces=1, gaps=1, missing=3), None, tolerance=result) == []


def test_campaign_six_post_recovery_loss_still_blocks():
    """The acceptance criterion for the tolerance.

    Campaign #6's auth connection was closed by the broker on a missed
    heartbeat mid-pause and the records were lost *after* recovery, ~5.2 s past
    the intervention's end against a 0.51 s settle. That is a pipeline defect,
    not a fault signature, and it must keep blocking -- otherwise the tolerance
    is too loose. The cause is fixed producer-side by F-ADH-073.
    """
    low, high = c6_bounds()
    events = [exposure_event(low + 5, 0, logged=high - 1), exposure_event(high + 6, 4)]
    result = performance_campaign.exposure_tolerance(
        events, c6_intervention(), fault="auth-freeze")
    assert result["toleratedMissingEoiCount"] == 0
    assert result["residualMissingEoiCount"] == 3
    assert result["residualEoiGapTraces"] == 1
    blockers = performance_campaign.collector_process_blockers(
        0, 0, eoi_gap_stats(traces=1, gaps=1, missing=3), None, tolerance=result)
    assert any("EOI completeness gaps" in blocker for blocker in blockers)


def test_correlation_errors_are_tolerated_only_inside_the_window():
    low, _ = c6_bounds()
    inside = performance_campaign.exposure_tolerance(
        [exposure_event(low + 10, 0, errors=["conflicting-native-identity"])],
        c6_intervention(), fault="auth-freeze")
    assert (inside["toleratedCorrelationErrorEvents"], inside["residualCorrelationErrorEvents"]) == (1, 0)
    before = performance_campaign.exposure_tolerance(
        [exposure_event(low - 1, 0, errors=["conflicting-native-identity"])],
        c6_intervention(), fault="auth-freeze")
    assert (before["toleratedCorrelationErrorEvents"], before["residualCorrelationErrorEvents"]) == (0, 1)
    # F-ADH-076: the child-side consequence of a conflicting parent is the same
    # loss and is tolerated in-window (campaign #7 aborted on 3 of these).
    child = performance_campaign.exposure_tolerance(
        [exposure_event(low + 26, 0, errors=["ambiguous-parent-native-identity"])],
        c6_intervention(), fault="auth-freeze")
    assert (child["toleratedCorrelationErrorEvents"], child["residualCorrelationErrorEvents"]) == (1, 0)
    # An error outside the tolerable class is never excused, even in-window.
    other = performance_campaign.exposure_tolerance(
        [exposure_event(low + 10, 0, errors=["runtime-host-signature-conflict"])],
        c6_intervention(), fault="auth-freeze")
    assert other["residualCorrelationErrorEvents"] == 1


def test_no_fault_cell_can_never_carry_a_tolerance():
    low, _ = c6_bounds()
    result = performance_campaign.exposure_tolerance(
        [exposure_event(low + 10, 0, errors=["conflicting-native-identity"])],
        c6_intervention(), fault="none")
    assert result["applied"] is False
    assert all(value == 0 for key, value in result.items()
               if key.startswith(("tolerated", "residual")))
    # A forged tolerance on a no-fault cell is itself a blocker.
    forged = dict(result, toleratedCorrelationErrorEvents=7)
    blockers = performance_campaign.collector_process_blockers(
        0, 0, None, None, tolerance=forged)
    assert any("without a proven intervention" in blocker for blocker in blockers)


def eoi_gap_stats(*, traces: int, gaps: int, missing: int) -> dict:
    """Minimal collector stats carrying only an EOI-gap shape."""
    return {
        "acknowledgement_mode": "manual", "runtime_host_map_loaded": True,
        "records_bad": 0, "containers_bad": 0,
        "correlation": {
            "events": 10, "eventsWithCorrelationErrors": 0,
            "eventsWithUnwovenRootParent": 0, "eventsWithProbeOrphanRoot": 0,
            "eventsWithCorrelationWarnings": 0,
            "eventsWithServiceAttributionErrors": 0,
            "traceCompleteness": {"traces": traces, "tracesWithEoiGaps": gaps,
                                  "missingEoiCount": missing, "tracesNotStartingAtZero": 0},
        },
    }


def test_readiness_probe_orphans_do_not_count_as_lost_roots(tmp_path):
    """F-ADH-083: the harness's readiness probe starts a parentless trace after a
    fault recovery inside the retained status-page caller's window; with the
    entry point woven it is counted, not blocked. The same shape under a
    workload operation, without an enclosing caller, or on cost evidence still
    blocks."""
    runtime = tmp_path / "runtime-images.json"
    runtime.write_text(json.dumps({
        "schemaVersion": 1,
        "services": {"recommender": {"containerId": "a" * 64},
                     "webui": {"containerId": "b" * 64}},
    }) + "\n")
    webui = "public void tools.descartes.teastore.webui.servlet.StatusServlet.{}()"
    caller = [
        {"class_name": kieker_native.OER_CLASS,
         "operationSignature": webui.format("handleGETRequest"),
         "sessionId": "<no-session-id>", "traceId": 41, "tin": 500, "tout": 3_000,
         "hostname": "b" * 12, "eoi": 0, "ess": 0},
        {"class_name": kieker_native.OER_CLASS,
         "operationSignature": webui.format("isRecommenderFinished"),
         "sessionId": "<no-session-id>", "traceId": 41, "tin": 900, "tout": 2_500,
         "hostname": "b" * 12, "eoi": 1, "ess": 1},
    ]

    def stats_for(signature, hostname, *, with_caller=True):
        collector = kieker_native.KiekerNativeCollector(runtime_images_path=runtime)
        collector.handle_body(kieker_native.build_fixture((caller if with_caller else []) + [
            {"class_name": kieker_native.OER_CLASS, "operationSignature": signature,
             "sessionId": "<no-session-id>", "traceId": 42, "tin": 1_000, "tout": 2_000,
             "hostname": hostname, "eoi": 1, "ess": 1},
            {"class_name": kieker_native.OER_CLASS,
             "operationSignature": ("public boolean tools.descartes.teastore.recommender"
                                    ".servlet.TrainingSynchronizer.isReady()"),
             "sessionId": "<no-session-id>", "traceId": 42, "tin": 1_100, "tout": 1_900,
             "hostname": hostname, "eoi": 2, "ess": 2},
        ]))
        return performance_campaign.collector_stats(json.dumps(collector.stats()))

    train = ("public javax.ws.rs.core.Response tools.descartes.teastore.recommender.rest"
             ".TrainEndpoint.isReady()")
    probe = stats_for(train, "a" * 12)
    assert probe["correlation"]["eventsWithUnwovenRootParent"] == 1
    assert probe["correlation"]["eventsWithProbeOrphanRoot"] == 1
    woven = performance_campaign.collector_process_blockers(
        0, None, probe, None, effect_contract=True, entry_point_woven=True)
    assert not any("missing native trace roots" in b for b in woven)
    assert not any("parent correlation errors" in b for b in woven)

    # Same shape on cost evidence: the probe never runs inside a cost window.
    cost = performance_campaign.collector_process_blockers(
        0, None, probe, None, effect_contract=False, entry_point_woven=True)
    assert any("readiness-probe orphans on cost evidence" in b for b in cost)

    # Without the enclosing status-page caller the root was LOST, not never minted.
    orphaned = stats_for(train, "a" * 12, with_caller=False)
    assert orphaned["correlation"]["eventsWithProbeOrphanRoot"] == 0
    assert any("missing native trace roots" in b for b in
               performance_campaign.collector_process_blockers(
                   0, None, orphaned, None, effect_contract=True, entry_point_woven=True))

    workload = stats_for(
        "public void tools.descartes.teastore.webui.Home.render()", "b" * 12)
    assert workload["correlation"]["eventsWithProbeOrphanRoot"] == 0
    assert any("missing native trace roots" in b for b in
               performance_campaign.collector_process_blockers(
                   0, None, workload, None, effect_contract=True, entry_point_woven=True))


def metadata_container(*, hostname: str, logging_timestamp: int,
                       class_name: str = "kieker.common.record.misc.KiekerMetadataRecord",
                       ) -> bytes:
    """One AMQP body shaped exactly like a Kieker controller startup banner.

    Byte-for-byte the shape retained in campaign #10 cell 19: a single record
    whose class the execution-record parser refuses, so the whole container is
    rejected with ``N unconsumed records-region bytes`` and NOTHING measurable
    is discarded with it.
    """
    registry = [class_name, "1.15-SNAPSHOT", "KIEKER", hostname, "NANOSECONDS"]
    records = bytearray()
    records.extend(struct.pack(">i", 0))                       # classId -> registry[0]
    records.extend(struct.pack(">q", logging_timestamp))
    records.extend(struct.pack(">i", 1))                       # version
    records.extend(struct.pack(">i", 2))                       # controllerName
    records.extend(struct.pack(">i", 3))                       # hostname
    records.extend(struct.pack(">i", 1))                       # experimentId
    records.extend(b"\x00")                                    # debugMode
    records.extend(struct.pack(">q", 0))                       # timeOffset
    records.extend(struct.pack(">i", 4))                       # timeUnit
    records.extend(struct.pack(">q", 0))                       # numberOfRecords
    body = bytearray(struct.pack(">ii", kieker_native.CONTAINER_IDENTIFIER,
                                 kieker_native.FORMAT_IDENTIFIER))
    body.extend(records)
    body.extend(kieker_native._encode_varint(len(registry)))
    for entry in registry:
        raw = entry.encode("utf-8")
        body.extend(kieker_native._encode_varint(len(raw)))
        body.extend(raw)
    body.extend(struct.pack(">i", len(records)))
    return bytes(body)


CRASH_INTERVENTION = {
    "successful": True,
    "service": "persistence",
    "targetContainerId": "640b7c0a2577" + "0" * 52,
    "actualOnsetWall": "2026-09-06T11:17:28.493637+00:00",
    "actualOffsetWall": "2026-09-06T11:19:58.698174+00:00",
    "readiness": {"observedAtWall": "2026-09-06T11:20:09.828891+00:00",
                  "successful": True},
}
CRASH_BANNER_NS = 1_788_693_604_746_414_240          # 11:20:04.746Z, inside the window


def test_restart_banner_container_is_anonymous_without_a_diagnostic():
    """F-ADH-084 root cause: the rejected banner leaves containers_bad=1 with
    records_bad=0 and no way to tell which container, when, or what was lost."""
    collector = kieker_native.KiekerNativeCollector()
    assert collector.handle_body(
        metadata_container(hostname="640b7c0a2577",
                           logging_timestamp=CRASH_BANNER_NS)) == []
    stats = collector.stats()
    # records_bad stays 0 because parse_container discards the whole container
    # before the unhandled record can be counted: the loss is invisible to every
    # record-level counter and the rejection carries no identity at all.
    assert (stats["containers_bad"], stats["records_bad"]) == (1, 0)
    assert stats["container_parse_success_ratio"] == 0.0

    body = metadata_container(hostname="640b7c0a2577", logging_timestamp=CRASH_BANNER_NS)
    diagnostic = kieker_native.container_parse_diagnostic(body, sequence=1399)
    assert diagnostic["error"] == "37 unconsumed records-region bytes"
    assert diagnostic["recordClasses"] == [
        "kieker.common.record.misc.KiekerMetadataRecord"]
    assert diagnostic["parsedExecutionRecords"] == 0
    assert diagnostic["loggingTimestampNs"] == CRASH_BANNER_NS
    assert diagnostic["registryContainerIds"] == ["640b7c0a2577"]
    assert diagnostic["sequence"] == 1399
    assert diagnostic["bodySha256"] == hashlib.sha256(body).hexdigest()


def test_restart_banner_is_tolerated_only_inside_its_own_exposure_window():
    """F-ADH-084: the fault's own restart banner is netted out; every other
    shape of the same counter still blocks, and cost cells never tolerate."""
    diagnostic = kieker_native.container_parse_diagnostic(
        metadata_container(hostname="640b7c0a2577", logging_timestamp=CRASH_BANNER_NS),
        sequence=1399)
    stats = valid_collector_stats(
        messages=3, containers_ok=2, containers_bad=1,
        container_parse_success_ratio=2 / 3)

    def blockers(fault, failures, intervention=CRASH_INTERVENTION):
        tolerance = performance_campaign.exposure_tolerance(
            [], intervention, fault=fault, container_failures=failures)
        return tolerance, performance_campaign.collector_process_blockers(
            0, 0, stats, None, effect_contract=fault != "none", tolerance=tolerance)

    tolerance, clean = blockers("persistence-crash", [diagnostic])
    assert tolerance["toleratedContainerParseFailures"] == 1
    assert tolerance["residualContainerParseFailures"] == 0
    # Reported, not hidden: the receipt keeps the whole diagnostic.
    assert tolerance["containerParseFailures"] == [diagnostic]
    assert not any("container parse" in blocker for blocker in clean)

    # The cost arm carries no intervention, so the identical rejection blocks.
    cost_tolerance, cost = blockers("none", [diagnostic], intervention=None)
    assert cost_tolerance["toleratedContainerParseFailures"] == 0
    assert cost_tolerance["residualContainerParseFailures"] == 1
    assert "collector container parse failures: 1 containers" in cost

    variants = {
        "another container": dict(diagnostic, registryContainerIds=["e4ce1d98d411"]),
        "before the window": dict(diagnostic, loggingTimestampNs=1_788_693_400_000_000_000),
        "after the window": dict(diagnostic, loggingTimestampNs=1_788_693_700_000_000_000),
        "no timestamp": dict(diagnostic, loggingTimestampNs=None),
        "no container id": dict(diagnostic, registryContainerIds=[]),
        "an execution record went with it": dict(diagnostic, parsedExecutionRecords=1),
        "an execution record class": dict(diagnostic, recordClasses=[
            kieker_native.OER_CLASS]),
        "nothing readable": dict(diagnostic, recordClasses=[]),
    }
    for label, variant in variants.items():
        residual_tolerance, residual = blockers("persistence-crash", [variant])
        assert residual_tolerance["toleratedContainerParseFailures"] == 0, label
        assert residual_tolerance["residualContainerParseFailures"] == 1, label
        assert "collector container parse failures: 1 containers" in residual, label

    # An undescribed rejection is never netted out, however benign the rest look.
    _, unaccounted = blockers("persistence-crash", [])
    assert any("do not account for every rejection" in b for b in unaccounted)
    assert "collector container parse failures: 1 containers" in unaccounted


def test_restart_banner_outside_the_target_still_blocks_end_to_end(tmp_path):
    """The diagnostic is re-derived from spool bytes, so the tolerance cannot be
    claimed for a banner the intervention did not cause."""
    spool_path = tmp_path / "kieker-amqp.spool"
    spool = kieker_native.KiekerBodySpool(spool_path)

    class _Method:
        consumer_tag = "ctag"
        redelivered = False
        exchange = ""
        routing_key = "kieker"

        def __init__(self, tag):
            self.delivery_tag = tag

    bodies = [
        metadata_container(hostname="640b7c0a2577", logging_timestamp=CRASH_BANNER_NS),
        metadata_container(hostname="e4ce1d98d411", logging_timestamp=CRASH_BANNER_NS),
    ]
    for tag, body in enumerate(bodies, start=1):
        spool.append_delivery(
            body, kieker_native.amqp_delivery_identity(_Method(tag), None))
    spool.seal()

    failures = kieker_native.spool_container_parse_diagnostics(spool_path)
    assert [failure["registryContainerIds"] for failure in failures] == [
        ["640b7c0a2577"], ["e4ce1d98d411"]]
    tolerance = performance_campaign.exposure_tolerance(
        [], CRASH_INTERVENTION, fault="persistence-crash", container_failures=failures)
    assert tolerance["toleratedContainerParseFailures"] == 1
    assert tolerance["residualContainerParseFailures"] == 1
    blockers = performance_campaign.collector_process_blockers(
        0, 0, valid_collector_stats(
            messages=4, containers_ok=2, containers_bad=2,
            container_parse_success_ratio=0.5),
        None, effect_contract=True, tolerance=tolerance)
    assert ("collector container parse failures: 1 containers "
            "(1 tolerated inside the exposure window)") in blockers
