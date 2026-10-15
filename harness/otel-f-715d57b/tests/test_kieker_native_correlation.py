import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/teastore/collectors/kieker_native.py"
SPEC = importlib.util.spec_from_file_location("kieker_native_collector", MODULE)
kieker = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(kieker)
FIXTURE = json.loads(
    (ROOT / "tests/fixtures/teastore-native-cross-message.json").read_text()
)


def _wire_record(record, **overrides):
    value = {
        "class_name": kieker.OER_CLASS,
        "loggingTimestamp": 0,
        **record,
    }
    value.update(overrides)
    return value


def _parsed_record(**overrides):
    value = {
        "_ok": True,
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
    value.update(overrides)
    return value


def test_cross_message_parentage_is_repaired_globally_in_native_order():
    host_map = kieker.runtime_host_service_map(FIXTURE["runtimeImages"])
    collector = kieker.KiekerNativeCollector(host_service_map=host_map)

    returned_batches = []
    for index, message in enumerate(FIXTURE["arrivalMessages"]):
        body = kieker.build_fixture(
            [_wire_record(record) for record in message["records"]]
        )
        returned_batches.append(collector.handle_body(body))
        if index == 0:
            assert returned_batches[0][0]["parent_span_id"] is None
            assert returned_batches[0][0]["parent_resolution"] == "missing"
            assert returned_batches[0][0]["correlation_errors"] == [
                "missing-parent-at-depth-3"
            ]

    # This is the important object-identity guarantee for poll-style callers:
    # an event returned while its ancestors were absent is repaired in place.
    descendant = returned_batches[0][0]
    assert descendant["eoi"] == 4
    assert descendant["parent_resolution"] == "resolved"
    assert descendant["parent_span_id"] == "1554867771349664037:3"

    events = collector.correlated_events()
    by_eoi = {event["eoi"]: event for event in events}
    assert [by_eoi[eoi]["parent_span_id"] for eoi in range(5)] == [
        "",
        "1554867771349664037:0",
        "1554867771349664037:1",
        "1554867771349664037:2",
        "1554867771349664037:3",
    ]
    assert {event["parent_resolution"] for event in events} == {
        "root",
        "resolved",
    }


def test_runtime_host_is_authoritative_and_signature_parser_ignores_return_type():
    host_map = kieker.runtime_host_service_map(FIXTURE["runtimeImages"])
    collector = kieker.KiekerNativeCollector(host_service_map=host_map)
    webui_message = FIXTURE["arrivalMessages"][2]
    events = collector.handle_body(
        kieker.build_fixture(
            [_wire_record(record) for record in webui_message["records"]]
        )
    )
    shared_client = next(event for event in events if event["eoi"] == 1)

    # Planted historical defect: the first TeaStore package in the signature is
    # the entities return type. It must not turn a webui execution into persistence.
    assert shared_client["service"] == "webui"
    assert shared_client["signature_package"] == "registryclient"
    assert shared_client["signature_service"] == "registry"
    assert shared_client["runtime_host_service"] == "webui"
    assert shared_client["service_attribution_status"] == (
        "runtime-host-overrides-shared-signature"
    )
    assert shared_client["service_attribution_errors"] == []


def test_actual_auth_signature_is_not_mislabeled_by_entities_return_type():
    signature = (
        "public tools.descartes.teastore.entities.message.SessionBlob "
        "tools.descartes.teastore.auth.security.ShaSecurityProvider.secure("
        "tools.descartes.teastore.entities.message.SessionBlob)"
    )
    events = kieker.records_to_events(
        [_parsed_record(operationSignature=signature, hostname="unmapped")],
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        "a" * 40,
        host_service_map={},
    )
    assert events[0]["service"] == "auth"
    assert events[0]["signature_package"] == "auth"
    assert events[0]["service_attribution_status"] == "declaring-signature-fallback"
    assert events[0]["service_attribution_errors"] == ["runtime-host-unmapped"]


def test_shared_declaring_package_without_runtime_map_stays_unknown():
    signature = (
        "public static tools.descartes.teastore.entities.message.SessionBlob "
        "tools.descartes.teastore.registryclient.rest.LoadBalancedStoreOperations.login()"
    )
    event = kieker.records_to_events(
        [_parsed_record(operationSignature=signature, hostname="unmapped")],
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        "b" * 40,
        host_service_map={},
    )[0]
    assert event["service"] == "unknown"
    assert event["service_attribution_status"] == "ambiguous-shared-signature"
    assert event["service_attribution_errors"] == [
        "shared-declaring-package-without-runtime-host-map"
    ]


def test_missing_cross_message_parent_is_explicit_until_ancestor_arrives():
    correlator = kieker.NativeTraceCorrelator(
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        {"auth-host": "auth"},
    )
    child = correlator.add_records(
        [_parsed_record(eoi=2, ess=2, hostname="auth-host")], "c" * 40
    )[0]
    assert child["parent_span_id"] is None
    assert child["parent_resolution"] == "missing"
    assert child["correlation_errors"] == ["missing-parent-at-depth-1"]

    correlator.add_records(
        [
            _parsed_record(eoi=0, ess=0, hostname="auth-host"),
            _parsed_record(eoi=1, ess=1, hostname="auth-host", tin=1_100),
        ],
        "d" * 40,
    )
    assert child["parent_span_id"] == "42:1"
    assert child["parent_resolution"] == "resolved"
    assert child["correlation_errors"] == []


def test_conflicting_native_identity_makes_child_parent_ambiguous():
    correlator = kieker.NativeTraceCorrelator(
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        {"webui": "webui", "auth": "auth"},
    )
    correlator.add_records(
        [
            _parsed_record(eoi=0, ess=0),
            _parsed_record(eoi=1, ess=1, hostname="webui", tin=1_100),
        ],
        "e" * 40,
    )
    events = correlator.add_records(
        [
            _parsed_record(
                eoi=1,
                ess=1,
                hostname="auth",
                tin=1_200,
                operationSignature=(
                    "public void tools.descartes.teastore.auth.Login.login()"
                ),
            ),
            _parsed_record(eoi=2, ess=2, hostname="auth", tin=1_300),
        ],
        "f" * 40,
    )
    child = next(event for event in events if event["eoi"] == 2)
    assert child["parent_span_id"] is None
    assert child["parent_resolution"] == "ambiguous"
    assert child["correlation_errors"] == ["ambiguous-parent-native-identity"]
    conflicting = [
        event for event in correlator.events if event["eoi"] == 1
    ]
    assert len(conflicting) == 2
    assert all(event["parent_resolution"] == "ambiguous" for event in conflicting)
    assert all(
        event["correlation_errors"] == ["conflicting-native-identity"]
        for event in conflicting
    )


def test_runtime_map_rejects_container_prefix_collision():
    planted = {
        "schemaVersion": 1,
        "services": {
            "auth": {"containerId": "a" * 64},
            "persistence": {"containerId": "a" * 12 + "b" * 52},
        }
    }
    with pytest.raises(kieker.ServiceAttributionError, match="alias collision"):
        kieker.runtime_host_service_map(planted)


def test_runtime_proof_path_binds_full_and_short_container_identity(tmp_path):
    proof = tmp_path / "runtime-images.json"
    proof.write_text(json.dumps(FIXTURE["runtimeImages"]) + "\n")
    collector = kieker.KiekerNativeCollector(runtime_images_path=proof)
    auth_id = FIXTURE["runtimeImages"]["services"]["auth"]["containerId"]
    assert collector.host_service_map[auth_id] == "auth"
    assert collector.host_service_map[auth_id[:12]] == "auth"
    assert collector.stats()["runtime_host_map_loaded"] is True


def test_runtime_proof_rejects_duplicate_service_key(tmp_path):
    proof = tmp_path / "runtime-images.json"
    proof.write_text(
        '{"schemaVersion":1,"services":{'
        '"auth":{"containerId":"' + "a" * 64 + '"},'
        '"auth":{"containerId":"' + "b" * 64 + '"}'
        '}}\n'
    )

    with pytest.raises(kieker.ServiceAttributionError, match="duplicate JSON key"):
        kieker.load_runtime_host_service_map(proof)


def test_duplicate_native_identity_is_retained_and_flagged_for_replay_review():
    correlator = kieker.NativeTraceCorrelator(
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        {"webui": "webui"},
    )
    record = _parsed_record()
    correlator.add_records([record], "1" * 40)
    correlator.add_records([dict(record)], "2" * 40)
    assert len(correlator.events) == 2
    assert all(event["native_identity_occurrences"] == 2
               for event in correlator.events)
    assert all(event["native_identity_message_bodies"] == 2
               for event in correlator.events)
    assert all(event["correlation_warnings"] == [
        "duplicate-native-identity-observation"
    ] for event in correlator.events)
    report = correlator.finalize_report()
    assert report["events"] == 2
    assert report["eventsWithCorrelationWarnings"] == 2


def test_injected_host_map_rejects_ghost_service():
    with pytest.raises(kieker.ServiceAttributionError, match="not canonical"):
        kieker.KiekerNativeCollector(host_service_map={"auth-host": "ghost-service"})


def test_terminal_report_exposes_native_eoi_gap_even_when_parent_resolves():
    correlator = kieker.NativeTraceCorrelator(
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        {"webui": "webui"},
    )
    events = correlator.add_records(
        [
            _parsed_record(eoi=0, ess=0),
            _parsed_record(eoi=2, ess=1, tin=1_100),
        ],
        "3" * 40,
    )
    assert events[1]["parent_resolution"] == "resolved"
    assert events[1]["correlation_errors"] == []
    assert correlator.finalize_report()["traceCompleteness"] == {
        "traces": 1,
        "tracesWithEoiGaps": 1,
        "missingEoiCount": 1,
    }


def test_cli_fails_without_writing_output_for_planted_invalid_event(tmp_path):
    output = tmp_path / "must-not-exist.json"
    driver = f"""
import importlib.util
import sys

module_path = {str(MODULE)!r}
spec = importlib.util.spec_from_file_location("kieker_native_cli", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def planted_invalid_event(self, **kwargs):
    return [{{"timestamp": 1.0}}]

module.KiekerNativeCollector.consume = planted_invalid_event
sys.argv = [module_path, "--duration", "0", "--output", sys.argv[1],
            "--spool", sys.argv[2]]
raise SystemExit(module.main())
"""
    spool = tmp_path / "invalid-event.spool"
    result = subprocess.run(
        [sys.executable, "-c", driver, str(output), str(spool)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "schema validation failed:" in result.stderr
    assert not output.exists()
