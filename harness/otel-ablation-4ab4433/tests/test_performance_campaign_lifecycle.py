import argparse
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
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
            "eventsWithCorrelationWarnings": 0,
            "eventsWithServiceAttributionErrors": 0,
            "traceCompleteness": {
                "traces": 4,
                "tracesWithEoiGaps": 0,
                "missingEoiCount": 0,
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


def queue_state_fixture(messages, consumers, container_id="e" * 64):
    stdout = f"kieker\t{messages}\t{consumers}\n"
    command = ["docker", "exec", container_id, "rabbitmqctl", "list_queues",
               "-q", "name", "messages", "consumers"]
    return {
        "containerId": container_id, "messages": messages, "consumers": consumers,
        "query": {"command": command, "returnCode": 0, "stdout": stdout, "stderr": ""},
    }


def queue_proof_fixture():
    container_id = "e" * 64
    return {
        "schemaVersion": 1, "composeProject": "obst-test",
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
    blockers = performance_campaign.collector_process_blockers(
        0, None, parsed, None,
    )
    assert any("parent correlation errors" in blocker for blocker in blockers)
    assert performance_campaign.collector_event_blockers(events, parsed) == []


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
    ):
        proof = queue_proof_fixture()
        mutation(proof)
        try:
            performance_campaign.validate_queue_proof(proof)
        except RuntimeError as exc:
            assert diagnostic in str(exc)
        else:
            raise AssertionError("planted RabbitMQ replay/exclusivity defect was accepted")


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
    children_path = tmp_path / "child-processes.json"
    children_path.write_text(json.dumps({"collector": collector}, sort_keys=True) + "\n")
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
        "processes": {"workload": {"returnCode": 0}, "collector": collector},
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

    receipt["processes"]["performanceProbe"] = {"joined": True, "returnCode": 0}
    path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    try:
        performance_campaign.validate_existing_receipt(
            path, "b01-full", "full", configuration)
    except RuntimeError as exc:
        assert "performanceProbe" in str(exc)
    else:
        raise AssertionError("effect receipt exposed a performance-probe child")
