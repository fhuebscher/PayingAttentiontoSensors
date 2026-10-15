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
            collector.correlator.flush()
            assert returned_batches[0][0]["parent_span_id"] is None
            assert returned_batches[0][0]["parent_resolution"] == "missing"
            assert returned_batches[0][0]["correlation_errors"] == [
                "missing-parent-at-depth-3"
            ]

    # This is the important object-identity guarantee for poll-style callers:
    # an event returned while its ancestors were absent is repaired in place
    # by the next flush.
    collector.correlator.flush()
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
    correlator.flush()
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
    correlator.flush()
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
    correlator.flush()
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


def _f_adh_071_trace_records(*, include_witness_collision: bool) -> list[dict]:
    """Build the F-ADH-071 collision shape: a normal root and a normal sibling
    call, then (when ``include_witness_collision``) a caller-side witness
    execution that reuses the eoi the remote callee lands on next, at the same
    ess -- exactly the shape produced when the framework's own witness helper
    is accidentally AspectJ-woven and consumes a caller-side eoi slot invisible
    to trace propagation. Two descendants sit directly beneath the collision
    depth so poisoning of their parent can be observed.
    """
    records = [
        _parsed_record(eoi=0, ess=0, tin=1_000),
        _parsed_record(
            eoi=1, ess=1, hostname="persistence", tin=1_100,
            operationSignature=(
                "public void tools.descartes.teastore.persistence."
                "PersistenceProvider.load()"
            ),
        ),
    ]
    if include_witness_collision:
        records.append(_parsed_record(
            eoi=2, ess=1, hostname="webui", tin=1_150,
            operationSignature=(
                "public void modules.teastore.witness.CorrelationWitness.mark()"
            ),
        ))
    records.append(_parsed_record(
        eoi=2, ess=1, hostname="auth", tin=1_200,
        operationSignature=(
            "public void tools.descartes.teastore.auth.Login.login()"
        ),
    ))
    records.append(_parsed_record(eoi=3, ess=2, hostname="auth", tin=1_300))
    records.append(_parsed_record(eoi=4, ess=2, hostname="auth", tin=1_400))
    return records


def test_witness_eoi_collision_still_flags_conflict_and_poisons_descendants():
    """F-ADH-071: a caller-side witness execution that is accidentally woven
    consumes an eoi slot invisible to trace propagation, so the remote callee
    lands on an already-used (traceId, eoi) at the same ess. The correlator
    must keep flagging this rather than silently absorbing one of the two
    events, and every descendant directly beneath the poisoned depth must come
    back ambiguous instead of quietly inheriting a wrong parent."""
    correlator = kieker.NativeTraceCorrelator(
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        {"webui": "webui", "auth": "auth"},
    )
    correlator.add_records(
        _f_adh_071_trace_records(include_witness_collision=True), "a" * 40,
    )
    correlator.flush()

    by_eoi: dict[int, list[dict]] = {}
    for event in correlator.events:
        by_eoi.setdefault(event["eoi"], []).append(event)

    colliding = by_eoi[2]
    assert len(colliding) == 2
    assert all(event["parent_span_id"] is None for event in colliding)
    assert all(event["parent_resolution"] == "ambiguous" for event in colliding)
    assert all(
        event["correlation_errors"] == ["conflicting-native-identity"]
        for event in colliding
    )

    descendants = by_eoi[3] + by_eoi[4]
    assert len(descendants) == 2
    assert all(event["parent_span_id"] is None for event in descendants)
    assert all(event["parent_resolution"] == "ambiguous" for event in descendants)
    assert all(
        event["correlation_errors"] == ["ambiguous-parent-native-identity"]
        for event in descendants
    )

    report = correlator.finalize_report()
    assert report["events"] == 6
    assert report["parentResolution"] == {
        "ambiguous": 4, "resolved": 1, "root": 1,
    }
    assert report["eventsWithCorrelationErrors"] == 4
    assert report["eventsWithCorrelationWarnings"] == 0


def test_same_trace_without_witness_collision_correlates_cleanly():
    """F-ADH-071 negative control: the identical trace shape minus the
    caller-side witness execution must correlate with zero correlation errors
    and every parent resolved, proving the flags above come from the eoi
    collision itself and not merely from this trace's depth/branching shape."""
    correlator = kieker.NativeTraceCorrelator(
        kieker.re.compile(kieker.DEFAULT_SERVICE_REGEX),
        kieker.DEFAULT_SERVICE_MAP,
        {"webui": "webui", "auth": "auth"},
    )
    correlator.add_records(
        _f_adh_071_trace_records(include_witness_collision=False), "b" * 40,
    )
    correlator.flush()

    assert len(correlator.events) == 5
    assert all(event["correlation_errors"] == [] for event in correlator.events)
    assert all(event["correlation_warnings"] == [] for event in correlator.events)
    assert {event["parent_resolution"] for event in correlator.events} == {
        "root", "resolved",
    }

    report = correlator.finalize_report()
    assert report["events"] == 5
    assert report["parentResolution"] == {"resolved": 4, "root": 1}
    assert report["eventsWithCorrelationErrors"] == 0
    assert report["eventsWithCorrelationWarnings"] == 0
    assert report["traceCompleteness"] == {
        "traces": 1, "tracesWithEoiGaps": 0, "missingEoiCount": 0,
        "tracesNotStartingAtZero": 0,
    }


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
    correlator.flush()
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


def test_count_unwoven_root_parents_counts_only_sole_depth0():
    events = [
        {"correlation_errors": ["missing-parent-at-depth-0"]},                 # unwoven root
        {"correlation_errors": ["missing-parent-at-depth-1"]},                 # genuine (deeper)
        {"correlation_errors": ["missing-parent-at-depth-0",                   # genuine (co-occurs)
                                "conflicting-native-identity"]},
        {"correlation_errors": []},                                            # clean
        {"correlation_errors": None},                                          # clean
    ]
    assert kieker.count_unwoven_root_parents(events) == 1


def test_entry_point_woven_detects_trace_root_group():
    assert kieker.entry_point_woven(
        ["aspectj:auth", "aspectj:persistence", "manual:registry-client"]) is False
    assert kieker.entry_point_woven(["aspectj:webui", "aspectj:auth"]) is True
    assert kieker.entry_point_woven([]) is False
    # An unknown closure stays strict so the gate never silently relaxes.
    assert kieker.entry_point_woven(None) is True


def test_rendered_full_closure_still_weaves_the_trace_root():
    """F-ADH-072 must not silently re-key the F-ADH-062..066 closure gates.

    `full` is now compiled from the catalog rather than mounted from the stock
    aop.xml, so the closure it reports has to keep containing aspectj:webui --
    otherwise entry_point_woven flips and the trace-root rules change meaning.
    """
    root = Path(__file__).parents[1]
    catalog = json.loads((root / "modules/teastore/activation/catalog.json").read_text())
    spec = importlib.util.spec_from_file_location(
        "selection_for_closure", root / "src/obsplacement/selection.py")
    selection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selection)
    full = selection.compile_selection(
        catalog, [row["id"] for row in catalog["logicalSensors"]])
    assert kieker.entry_point_woven(full["selectedActivationGroups"]) is True


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
    correlator.flush()
    assert events[1]["parent_resolution"] == "resolved"
    assert events[1]["correlation_errors"] == []
    assert correlator.finalize_report()["traceCompleteness"] == {
        "traces": 1,
        "tracesWithEoiGaps": 1,
        "missingEoiCount": 1,
        "tracesNotStartingAtZero": 0,
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


def _status_caller(trace_id=5, operation="StatusServlet.isImageFinished", tin=1_000, tout=2_000):
    """The retained webui-side caller whose [tin, tout] encloses the orphan."""
    return [
        {"kieker_trace_id": trace_id, "eoi": 0, "ess": 0, "tin": 500, "tout": 3_000,
         "operation": "StatusServlet.handleGETRequest",
         "parent_resolution": "root", "correlation_errors": []},
        {"kieker_trace_id": trace_id, "eoi": 7, "ess": 1, "tin": tin, "tout": tout,
         "operation": operation, "parent_resolution": "resolved", "correlation_errors": []},
    ]


def _probe_orphan_trace(trace_id, root_operation="TrainEndpoint.isReady", *,
                        with_root=False, tin=1_500):
    """F-ADH-083 shape measured on campaign #9 cell 12: a readiness call that
    started a fresh trace id while carrying eoi=1/ess=1 (parallelStream lost the
    thread-local Kieker context), plus its resolved callee."""
    events = [
        {"kieker_trace_id": trace_id, "eoi": 1, "ess": 1, "tin": tin, "tout": tin + 100,
         "operation": root_operation, "parent_resolution": "missing",
         "correlation_errors": ["missing-parent-at-depth-0"]},
        {"kieker_trace_id": trace_id, "eoi": 2, "ess": 2, "tin": tin + 10, "tout": tin + 90,
         "operation": "TrainingSynchronizer.isReady",
         "parent_resolution": "resolved", "correlation_errors": []},
    ]
    if with_root:
        events.insert(0, {"kieker_trace_id": trace_id, "eoi": 0, "ess": 0, "tin": tin - 50,
                          "tout": tin + 200, "operation": "StatusServlet.handleGETRequest",
                          "parent_resolution": "root", "correlation_errors": []})
    return events


def test_probe_orphan_roots_require_every_conjunct():
    caller = _status_caller()
    # The real shape: counted as a probe orphan AND as an unwoven root.
    events = caller + _probe_orphan_trace(7) + _probe_orphan_trace(
        8, "ImageProviderEndpoint.isFinished")[:1]
    assert kieker.count_unwoven_root_parents(events) == 2
    assert kieker.count_probe_orphan_roots(events) == 2
    assert kieker.probe_orphan_root_indices(events) == frozenset({2, 4})

    # (2) Operation not in the declared set -> still a missing root, not a probe.
    assert kieker.count_probe_orphan_roots(caller + _probe_orphan_trace(7, "Home.render")) == 0
    # (3) A depth-0 record exists in the trace -> a root was lost, not never minted.
    assert kieker.count_probe_orphan_roots(caller + _probe_orphan_trace(7, with_root=True)) == 0
    # (4) A workload execution shares the shallowest depth -> not a pure probe trace.
    mixed = caller + _probe_orphan_trace(7) + [
        {"kieker_trace_id": 7, "eoi": 3, "ess": 1, "tin": 1_600, "tout": 1_700,
         "operation": "Home.render", "parent_resolution": "missing",
         "correlation_errors": ["missing-parent-at-depth-0"]}]
    assert kieker.count_probe_orphan_roots(mixed) == 0
    assert kieker.count_unwoven_root_parents(mixed) == 2
    # (5) Reviewer case A: a genuinely LOST root whose surviving shallowest frame
    # happens to be a probe operation has no enclosing status-page caller.
    assert kieker.count_probe_orphan_roots(_probe_orphan_trace(7)) == 0
    assert kieker.count_probe_orphan_roots(
        _status_caller(tin=5_000, tout=6_000) + _probe_orphan_trace(7)) == 0
    # (1) Any additional error, or a non-missing parent resolution, stays a defect.
    tainted = caller + _probe_orphan_trace(7)
    tainted[2]["correlation_errors"].append("conflicting-native-identity")
    assert kieker.count_probe_orphan_roots(tainted) == 0
    resolved = caller + _probe_orphan_trace(7)
    resolved[2]["parent_resolution"] = "root"
    assert kieker.count_probe_orphan_roots(resolved) == 0
    # Reviewer case E: the persistence readiness endpoint is not declared (it is
    # excluded from weaving and reached same-thread), so it is never excused.
    assert kieker.count_probe_orphan_roots(
        caller + _probe_orphan_trace(7, "DatabaseGenerationEndpoint.isFinshed")) == 0


def test_readiness_probe_set_is_exactly_the_status_page_fan_out():
    """F-ADH-083 preregistration. The candidate-pilot v1 descriptor is frozen by
    candidate_pilot.frozen_descriptor() and cannot be amended in place, so the
    declared set lives here, bound into every receipt by the framework commit.
    Derived from StatusServlet.java in the pinned upstream; change deliberately."""
    assert set(kieker.READINESS_PROBE_OPERATIONS) == {
        "ImageProviderEndpoint.isFinished",
        "TrainEndpoint.isReady",
    }
    assert set(kieker.READINESS_PROBE_CALLERS) == {
        "StatusServlet.isImageFinished",
        "StatusServlet.isRecommenderFinished",
    }
