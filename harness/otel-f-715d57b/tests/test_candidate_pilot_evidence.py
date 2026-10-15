import hashlib
import importlib.util
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _nested_secret_log(layers: int) -> str:
    value = '{"password":"planted-not-a-real-secret"}'
    for _ in range(layers):
        value = json.dumps(value)
    return "normal-log-prefix " + value + "\n"


MODULE = Path(__file__).parents[1] / "modules/teastore/validation/candidate_pilot.py"
SPEC = importlib.util.spec_from_file_location("candidate_pilot", MODULE)
candidate_pilot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(candidate_pilot)

CAMPAIGN_MODULE = Path(__file__).parents[1] / "modules/teastore/execution/performance_campaign.py"
CAMPAIGN_SPEC = importlib.util.spec_from_file_location("candidate_evidence_performance_campaign", CAMPAIGN_MODULE)
performance_campaign = importlib.util.module_from_spec(CAMPAIGN_SPEC)
assert CAMPAIGN_SPEC.loader
CAMPAIGN_SPEC.loader.exec_module(performance_campaign)

WITNESS_MODULE = Path(__file__).parents[1] / "modules/teastore/witness/extract_app_witness.py"
WITNESS_SPEC = importlib.util.spec_from_file_location(
    "candidate_evidence_app_witness", WITNESS_MODULE)
app_witness = importlib.util.module_from_spec(WITNESS_SPEC)
assert WITNESS_SPEC.loader
WITNESS_SPEC.loader.exec_module(app_witness)

RESOURCE_MODULE = Path(__file__).parents[1] / "modules/teastore/collectors/performance_probe_v3.py"
RESOURCE_SPEC = importlib.util.spec_from_file_location(
    "candidate_evidence_resource_probe", RESOURCE_MODULE)
resource_probe = importlib.util.module_from_spec(RESOURCE_SPEC)
assert RESOURCE_SPEC.loader
RESOURCE_SPEC.loader.exec_module(resource_probe)

NATIVE_TOKEN_MODULE = (
    Path(__file__).parents[1]
    / "modules/teastore/witness/extract_native_token_correlation.py"
)
NATIVE_TOKEN_SPEC = importlib.util.spec_from_file_location(
    "candidate_evidence_native_token", NATIVE_TOKEN_MODULE)
native_token = importlib.util.module_from_spec(NATIVE_TOKEN_SPEC)
assert NATIVE_TOKEN_SPEC.loader
NATIVE_TOKEN_SPEC.loader.exec_module(native_token)

KIEKER_MODULE = (
    Path(__file__).parents[1] / "modules/teastore/collectors/kieker_native.py"
)
KIEKER_SPEC = importlib.util.spec_from_file_location(
    "candidate_evidence_kieker_native", KIEKER_MODULE)
kieker_native = importlib.util.module_from_spec(KIEKER_SPEC)
assert KIEKER_SPEC.loader
KIEKER_SPEC.loader.exec_module(kieker_native)


BASE = datetime(2026, 8, 29, 0, 0, tzinfo=timezone.utc)
WARMUP = BASE
MEASUREMENT = BASE + timedelta(seconds=120)
END = MEASUREMENT + timedelta(seconds=600)
BARRIER = "barrier-" + "a" * 32


def _time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()


def _canonical_sha256(value) -> str:
    encoded = json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, values):
    path.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in values), encoding="utf-8")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _rehash(root: Path):
    receipt = _load(root / "receipt.json")
    receipt["artifacts"] = {
        name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
        for name in (*candidate_pilot.REQUIRED_FILES[1:], "intervention.json")
        if (root / name).is_file()
    }
    _write_json(root / "receipt.json", receipt)


def _reextract_native_token(root: Path):
    (root / "native-token-correlation.json").unlink(missing_ok=True)
    (root / "native-token-correlation-extraction.json").unlink(missing_ok=True)
    native_token.extract(
        auth_log=root / "auth.log",
        journey_ledger=root / "journey-ledger.jsonl",
        traces=root / "traces.json",
        run_receipt=root / "receipt.json",
        service_log_capture_receipt=root / "service-log-capture.json",
        output=root / "native-token-correlation.json",
        extraction_receipt=root / "native-token-correlation-extraction.json",
    )


def _effect_intervention(regime: str):
    scenario = candidate_pilot.SCENARIOS[regime]
    onset = MEASUREMENT + timedelta(seconds=180)
    offset = onset + timedelta(seconds=150)
    onset_vector = ["docker", "pause" if scenario == "auth-freeze" else "stop", "target"]
    recovery_vector = ["docker", "unpause" if scenario == "auth-freeze" else "start", "target"]
    onset_result = {"command": onset_vector, "returnCode": 0, "stdout": "", "stderr": ""}
    recovery_result = {"command": recovery_vector, "returnCode": 0, "stdout": "", "stderr": ""}
    base = {
        "schemaVersion": 3,
        "scenario": scenario,
        "service": "auth" if scenario == "auth-freeze" else "persistence",
        "independentOfKieker": True,
        "intervalLabel": "intervention-exposure",
        "functionalOutage": None,
        "measurementBarrier": {
            "id": BARRIER,
            "wall": _time(MEASUREMENT),
            "scheduledOnsetSeconds": 180,
            "scheduledOnsetWall": _time(onset),
        },
        "targetContainerId": "c" * 64,
        "targetImage": {
            "containerId": "c" * 64,
            "declaredImage": "teastore-auth:latest",
            "containerImageId": "sha256:" + "d" * 64,
            "imageInspectId": "sha256:" + "d" * 64,
            "repoDigests": ["teastore-auth@sha256:" + "e" * 64],
        },
        "commandVector": onset_vector,
        "commandResult": onset_result,
        "recoveryAction": {
            "commandVector": recovery_vector,
            "commandResult": recovery_result,
        },
        "actualOnsetWall": _time(onset),
        "actualOffsetWall": _time(offset),
        "actualOnsetMonotonicOffsetSeconds": 180.0,
        "actualOffsetMonotonicOffsetSeconds": 330.0,
        "readiness": {
            "predicate": "teastore-ready",
            "observedAtWall": _time(offset),
            "observedAtMonotonicOffsetSeconds": 330.0,
            "successful": True,
        },
        "requestedHoldSeconds": 150,
        "manifested": True,
        "recovered": True,
        "outageHeld": True,
        "successful": True,
        "error": None,
        "sameTargetIdentity": True,
        "interventionThreadJoined": True,
        "laterInterventionMutationObserved": False,
        "operational": {
            "controllerStartedAt": _time(MEASUREMENT),
            "controllerEndedAt": _time(offset + timedelta(seconds=1)),
            "commandResults": [onset_result, recovery_result],
            "actualHoldSeconds": 150.0,
            "continuousTargetStateProven": False,
        },
    }
    if scenario == "auth-freeze":
        base.update({
            "preState": {"exists": True, "running": True, "paused": False},
            "postState": {"exists": True, "running": True, "paused": False},
            "duringStateSamples": [
                {"phase": "manifested", "observedAtWall": _time(onset),
                 "observedAtMonotonicOffsetSeconds": 180.0,
                 "state": {"exists": True, "running": True, "paused": True}},
                {"phase": "hold-midpoint", "observedAtWall": _time(onset + timedelta(seconds=75)),
                 "observedAtMonotonicOffsetSeconds": 255.0,
                 "state": {"exists": True, "running": True, "paused": True}},
                {"phase": "hold-end", "observedAtWall": _time(offset),
                 "observedAtMonotonicOffsetSeconds": 330.0,
                 "state": {"exists": True, "running": True, "paused": True}},
            ],
        })
    else:
        base.update({
            "preState": {"exists": True, "running": True, "paused": False},
            "postState": {"exists": True, "running": True, "paused": False},
            "duringStateSamples": [
                {"phase": "manifested", "observedAtWall": _time(onset),
                 "observedAtMonotonicOffsetSeconds": 180.0,
                 "state": {"exists": True, "running": False, "paused": False}},
                {"phase": "hold-midpoint", "observedAtWall": _time(onset + timedelta(seconds=75)),
                 "observedAtMonotonicOffsetSeconds": 255.0,
                 "state": {"exists": True, "running": False, "paused": False}},
                {"phase": "hold-end", "observedAtWall": _time(offset),
                 "observedAtMonotonicOffsetSeconds": 330.0,
                 "state": {"exists": True, "running": False, "paused": False}},
            ],
        })
    return base


def _resource_evidence():
    services = ["auth", "image", "persistence", "recommender", "webui"]
    identities = {
        service: f"{index + 1:064x}" for index, service in enumerate(services)
    }
    start = MEASUREMENT.timestamp()
    samples = []
    for slot in range(120):
        scheduled = start + slot * 5.0
        rows = [
            {
                "service": service,
                "containerId": identities[service],
                "name": f"candidate-{service}-1",
                "cpuPercent": 1.0,
                "memoryBytes": 100.0,
            }
            for service in services
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
        "contract": resource_probe.CONTRACT,
        "barrierId": BARRIER,
        "requestedStartAtEpoch": start,
        "nominalStartAtEpoch": start,
        "nominalEndAtEpoch": END.timestamp(),
        "measurementDurationSeconds": 600.0,
        "collectorStartedAtEpoch": start - 5.0,
        "collectorEndedAtEpoch": END.timestamp() + 0.1,
        "clock": {
            "semantics": resource_probe.CLOCK_SEMANTICS,
            "anchorWallEpoch": start - 5.0,
            "anchorMonotonicSeconds": 1000.0,
            "barrierMonotonicSeconds": 1005.0,
            "collectorStartedMonotonicOffsetSeconds": -5.0,
            "collectorEndedMonotonicOffsetSeconds": 600.1,
        },
        "sampling": {
            "semantics": resource_probe.SAMPLING_SEMANTICS,
            "intervalSeconds": 5.0,
            "commandTimeoutSeconds": 4.0,
            "expectedSlots": 120,
            "completedSlots": 120,
            "missedSlots": [],
            "maximumStartLatenessSeconds": 1.0,
        },
        "excludedServices": ["db", "rabbitmq", "registry"],
        "requiredServices": services,
        "containerIdentity": identities,
        "samples": samples,
        "applicationCpuSeconds": 30.0,
        "applicationMemoryPeakBytes": 500.0,
        "hostCpuSeconds": 1.0,
        "hostCpuScope": resource_probe.HOST_CPU_SCOPE,
        "hostCpuAccounting": {
            "tickRateHz": 100,
            "start": {
                "totalTicks": 100_000,
                "idleTicks": 50_000,
                "monotonicOffsetSeconds": 0.0,
            },
            "end": {
                "totalTicks": 160_000,
                "idleTicks": 109_900,
                "monotonicOffsetSeconds": 600.0,
            },
            "busyTicks": 100,
        },
    }


def _native_cell_evidence(root: Path, posture: str):
    services = sorted(kieker_native.CANONICAL_RUNTIME_SERVICES)
    runtime_images = {
        "schemaVersion": 1,
        "services": {
            service: {"containerId": f"{index + 1:x}" * 64}
            for index, service in enumerate(services)
        },
    }
    _write_json(root / "runtime-images.json", runtime_images)
    spool_path = root / "kieker-amqp.spool"
    spool = kieker_native.KiekerBodySpool(spool_path)
    bodies = []
    if posture != "none":
        for index in range(90):
            started = MEASUREMENT + timedelta(seconds=index * (600 / 90))
            tin = int(started.timestamp() * 1_000_000_000)
            raw = kieker_native.build_fixture([
                {
                    "class_name": kieker_native.OER_CLASS,
                    "operationSignature": (
                        "public boolean tools.descartes.teastore.auth.Auth.login()"
                    ),
                    "sessionId": "candidate-fixture", "traceId": 10_000 + index,
                    "tin": tin + 100_000_000, "tout": tin + 150_000_000,
                    "hostname": "auth", "eoi": 0, "ess": 0,
                },
                {
                    "class_name": kieker_native.OER_CLASS,
                    "operationSignature": (
                        "public void tools.descartes.teastore.persistence.Persistence.find()"
                    ),
                    "sessionId": "candidate-fixture", "traceId": 10_000 + index,
                    "tin": tin + 200_000_000, "tout": tin + 250_000_000,
                    "hostname": "persistence", "eoi": 1, "ess": 1,
                },
            ])
            identity = {
                "schemaVersion": 1,
                "method": {
                    "consumerTag": "candidate", "deliveryTag": index + 1,
                    "redelivered": False, "exchange": "", "routingKey": "kieker",
                },
                "properties": {
                    "content_type": None, "content_encoding": None, "headers": {},
                    "delivery_mode": 2, "priority": 0, "correlation_id": None,
                    "reply_to": None, "expiration": None,
                    "message_id": f"candidate-{index:03d}", "timestamp": None,
                    "type": "kieker", "user_id": None, "app_id": "teastore",
                    "cluster_id": None,
                },
            }
            spool.append_delivery(raw, identity)
            bodies.append(raw)
    spool.seal()
    runtime_aliases = kieker_native.load_runtime_host_service_map(
        root / "runtime-images.json"
    )
    configuration, configuration_sha256 = (
        kieker_native.frozen_attribution_configuration(runtime_aliases)
    )
    traces, summary, counts = kieker_native.replay_spooled_events(
        spool_path,
        re.compile(kieker_native.DEFAULT_SERVICE_REGEX),
        kieker_native.DEFAULT_SERVICE_MAP,
        configuration["effectiveHostAliases"],
    )
    collector = kieker_native.KiekerNativeCollector(
        runtime_images_path=root / "runtime-images.json"
    )
    for raw in bodies:
        collector.n_messages += 1
        collector.handle_body(raw)
    collector._spool_report = summary
    stats = collector.stats()
    assert collector.correlated_events() == traces
    assert {field: stats[field] for field in counts} == counts
    return traces, stats, summary, configuration_sha256


def _spool_identity(index: int) -> dict:
    return {
        "schemaVersion": 1,
        "method": {
            "consumerTag": "candidate", "deliveryTag": index + 1,
            "redelivered": False, "exchange": "", "routingKey": "kieker",
        },
        "properties": {
            "content_type": None, "content_encoding": None, "headers": {},
            "delivery_mode": 2, "priority": 0, "correlation_id": None,
            "reply_to": None, "expiration": None,
            "message_id": f"candidate-{index:03d}", "timestamp": None,
            "type": "kieker", "user_id": None, "app_id": "teastore",
            "cluster_id": None,
        },
    }


def _plant_malformed_spool_body(root: Path) -> None:
    spool_path = root / "kieker-amqp.spool"
    bodies, _ = kieker_native.replay_kieker_spool(spool_path)
    spool_path.unlink()
    spool = kieker_native.KiekerBodySpool(spool_path)
    for index, raw in enumerate([*bodies, b"planted-not-a-kieker-container"]):
        spool.append_delivery(raw, _spool_identity(index))
    spool.seal()
    runtime_aliases = kieker_native.load_runtime_host_service_map(
        root / "runtime-images.json"
    )
    configuration, configuration_sha256 = (
        kieker_native.frozen_attribution_configuration(runtime_aliases)
    )
    replayed, summary, counts = kieker_native.replay_spooled_events(
        spool_path,
        re.compile(kieker_native.DEFAULT_SERVICE_REGEX),
        kieker_native.DEFAULT_SERVICE_MAP,
        configuration["effectiveHostAliases"],
    )
    receipt = _load(root / "receipt.json")
    stats = receipt["telemetry"]["collectorStats"]
    stats.update(counts)
    records = counts["records_ok"] + counts["records_bad"]
    containers = counts["containers_ok"] + counts["containers_bad"]
    stats["record_parse_success_ratio"] = counts["records_ok"] / records if records else 0.0
    stats["container_parse_success_ratio"] = (
        counts["containers_ok"] / containers if containers else 0.0
    )
    stats["spool"] = summary
    stats["attribution_configuration"] = configuration
    stats["attribution_configuration_sha256"] = configuration_sha256
    receipt["telemetry"]["spool"] = summary
    receipt["source"]["spoolSha256"] = hashlib.sha256(
        spool_path.read_bytes()
    ).hexdigest()
    receipt["source"]["collectorAttributionConfigurationSha256"] = (
        configuration_sha256
    )
    assert replayed == _load(root / "traces.json")
    _write_json(root / "receipt.json", receipt)
    _rehash(root)


def make_run(
    root: Path,
    *,
    regime: str = "no-fault-cost",
    posture: str = "selected",
    block: int = 1,
):
    root.mkdir(parents=True)
    barrier = BARRIER
    journeys = []
    opportunities = []
    witnesses = []
    traces = []
    for index in range(90):
        offset = index * (600 / 90)
        started = MEASUREMENT + timedelta(seconds=offset)
        ended = started + timedelta(seconds=1)
        journey_id = f"journey-{index:032x}"
        opportunity_id = f"{candidate_pilot.POPULATION}:{index:06d}"
        token = journey_id
        allocated = _time(WARMUP + timedelta(seconds=1))
        scheduled_at = _time(MEASUREMENT + timedelta(seconds=offset))
        opportunities.append({
            "sequence": index,
            "journeyId": journey_id,
            "opportunityId": opportunity_id,
            "opaqueToken": token,
            "tokenAllocatedAt": allocated,
            "scheduledAt": scheduled_at,
            "scheduledMonotonicOffsetSeconds": offset,
        })
        request_specs = [
            ("login", "login-action", "/loginAction", 0.0, 0.2),
            ("browse-home", "home", "/", 0.3, 0.5),
            ("return-home", "home", "/", 0.6, 1.0),
        ]
        requests = [{
            "sequence": request_index,
            "step": step,
            "routeId": route,
            "target": target,
            "actualStartMonotonic": offset + request_start,
            "actualEndMonotonic": offset + request_end,
            "startedAt": _time(started + timedelta(seconds=request_start)),
            "endedAt": _time(started + timedelta(seconds=request_end)),
            "latencyMs": (request_end - request_start) * 1000,
            "statusCode": 200,
            "outcome": "succeeded",
            "error": None,
        } for request_index, (step, route, target, request_start, request_end) in enumerate(request_specs)]
        journeys.append({
            "sequence": index,
            "journeyId": journey_id,
            "opportunityId": opportunity_id,
            "opaqueToken": token,
            "tokenAllocatedAt": allocated,
            "scheduledAt": scheduled_at,
            "scheduledMonotonicOffsetSeconds": offset,
            "actualStartMonotonic": offset,
            "actualEndMonotonic": 1.0 + offset,
            "startedAt": _time(started),
            "endedAt": _time(ended),
            "barrierId": barrier,
            "expectedPath": candidate_pilot.EXPECTED_PATH,
            "requests": requests,
            "requestCount": len(requests),
            "outcome": "succeeded",
            "errors": [],
            "terminalSettled": True,
            "endedAfterNominalWindow": False,
        })
        witnesses.append({
            "schema": "teastore.app-witness",
            "schemaVersion": 1,
            "journeyId": journey_id,
            "opportunityId": opportunity_id,
            "opaqueToken": token,
            "source": "application-side",
            "independentOfKieker": True,
            "observedAt": _time(started + timedelta(milliseconds=200)),
            "authObservedAtUtc": _time(started + timedelta(milliseconds=100)),
            "persistenceObservedAtUtc": _time(started + timedelta(milliseconds=200)),
            "authTraversed": True,
            "persistenceTraversed": True,
            "executedPath": ["auth", "persistence"],
        })
        if posture != "none":
            trace_id = str(10_000 + index)
            delivery_id = f"delivery-{index:03d}"
            message_hash = _sha1(f"message-{index}")
            common = {
                "trace_id": trace_id,
                "kieker_trace_id": int(trace_id),
                "source": "kieker_native",
                "message_delivery_id": delivery_id,
                "message_sha1": message_hash,
                "correlation_errors": [],
                "correlation_warnings": [],
                "native_identity_occurrences": 1,
                "native_identity_message_bodies": 1,
                "service_attribution_errors": [],
            }
            traces.extend([
                common | {
                    "span_id": f"{trace_id}:0",
                    "parent_span_id": "",
                    "parent_resolution": "root",
                    "operation": "auth",
                    "service": "auth",
                    "runtime_host_service": "auth",
                    "service_attribution_status": "runtime-host-and-signature-agree",
                    "nativeTimestamp": _time(started + timedelta(milliseconds=100)),
                    "signature_sha1": _sha1("auth-signature"),
                },
                common | {
                    "span_id": f"{trace_id}:1",
                    "parent_span_id": f"{trace_id}:0",
                    "parent_resolution": "resolved",
                    "operation": "persistence",
                    "service": "persistence",
                    "runtime_host_service": "persistence",
                    "service_attribution_status": "runtime-host-and-signature-agree",
                    "nativeTimestamp": _time(started + timedelta(milliseconds=200)),
                    "signature_sha1": _sha1("persistence-signature"),
                },
            ])
    traces, collector_stats, spool_summary, attribution_sha256 = (
        _native_cell_evidence(root, posture)
    )
    intervention = None if regime == "no-fault-cost" else _effect_intervention(regime)
    plan = {
        "artifactType": "teastore-expected-opportunity-plan",
        "schemaVersion": 1,
        "workloadId": candidate_pilot.POPULATION,
        "barrierId": barrier,
        "controllerStartedAt": _time(WARMUP),
        "barrierAt": _time(MEASUREMENT),
        "clock": {"wallClock": "UTC", "monotonicValues": "seconds-relative-to-barrier"},
        "schedule": {"kind": "fixed-open-loop", "journeysPerSecond": 0.15,
                     "durationSeconds": 600, "offered": 90},
        "expectedPath": candidate_pilot.EXPECTED_PATH,
        "tokenContract": candidate_pilot.TOKEN_CONTRACT,
        "opportunities": opportunities,
    }
    plan_sha = _canonical_sha256(plan)
    previous = "0" * 64
    ledger_records = []
    for record_sequence, journey in enumerate(journeys):
        record = {
            "artifactType": "teastore-journey-ledger-record",
            "schemaVersion": 1,
            "recordType": "journey-terminal",
            "recordSequence": record_sequence,
            "previousRecordSha256": previous,
            "recordSha256": None,
            "planSha256": plan_sha,
            "workloadId": candidate_pilot.POPULATION,
        } | journey
        without_self = {key: value for key, value in record.items() if key != "recordSha256"}
        record["recordSha256"] = _canonical_sha256(without_self)
        previous = record["recordSha256"]
        ledger_records.append(record)
    reconciliation = {
        "artifactType": "teastore-journey-ledger-record",
        "schemaVersion": 1,
        "recordType": "reconciliation",
        "recordSequence": 90,
        "previousRecordSha256": previous,
        "recordSha256": None,
        "planSha256": plan_sha,
        "workloadId": candidate_pilot.POPULATION,
        "barrierId": barrier,
        "state": "completed",
        "terminalReason": None,
        "expectedJourneys": 90,
        "terminalJourneys": 90,
        "terminalJourneyIdsSha256": _canonical_sha256(sorted(row["journeyId"] for row in journeys)),
        "terminalOpportunityIdsSha256": _canonical_sha256(sorted(row["opportunityId"] for row in journeys)),
        "finalizedAt": _time(END),
        "terminalSettled": True,
    }
    reconciliation["recordSha256"] = _canonical_sha256({
        key: value for key, value in reconciliation.items() if key != "recordSha256"
    })
    ledger_records.append(reconciliation)
    resources = _resource_evidence()
    _write_json(root / "resources.json", resources)
    resource_sha256 = hashlib.sha256((root / "resources.json").read_bytes()).hexdigest()
    receipt = {
        "schemaVersion": 2,
        "contract": candidate_pilot.CONTRACT,
        "studyEpoch": candidate_pilot.STUDY_EPOCH,
        "population": candidate_pilot.POPULATION,
        "selectionId": "fault-qualification" if posture == "selected" else None,
        "source": {
            "sutCommit": candidate_pilot.SUT_COMMIT,
            "frameworkCommit": "a" * 40,
            "frameworkDirty": False,
            "host": "fb14srv5",
            "exclusiveLease": True,
            "imageDigests": {"teastore-auth": "teastore-auth@sha256:" + "b" * 64},
            "spoolSha256": hashlib.sha256(
                (root / "kieker-amqp.spool").read_bytes()
            ).hexdigest(),
            "runtimeImagesSha256": hashlib.sha256(
                (root / "runtime-images.json").read_bytes()
            ).hexdigest(),
            "collectorAttributionConfigurationSha256": attribution_sha256,
        },
        "run": {"runId": f"{regime}-b{block}-{posture}", "regime": regime,
                "block": block, "posture": posture, "attempt": 1},
        "analysisKind": "cost" if regime == "no-fault-cost" else "effect",
        "resourceUse": "cost-proxy" if regime == "no-fault-cost" else "diagnostic-only",
        "window": {
            "warmupStartedAt": _time(WARMUP),
            "measurementStartedAt": _time(MEASUREMENT),
            "measurementEndedAt": _time(END),
            "warmupStartMonotonic": 0.0,
            "measurementStartMonotonic": 120.0,
            "measurementEndMonotonic": 720.0,
            "sharedBarrierId": barrier,
        },
        "workload": {"offered": 90, "successful": 90, "failed": 0, "timedOut": 0, "requests": 270},
        "latencyMs": {"denominator": "successful-journeys", "count": 90,
                      "p50": 1000.0, "p95": 1000.0, "p99": 1000.0, "mean": 1000.0},
        "resources": {
            "applicationCpuSeconds": 30.0,
            "applicationMemoryPeakBytes": 500.0,
            "hostCpuSeconds": 1.0,
            "contract": resource_probe.CONTRACT,
            "artifactSha256": resource_sha256,
            "nominalStartAtEpoch": MEASUREMENT.timestamp(),
            "nominalEndAtEpoch": END.timestamp(),
            "measurementDurationSeconds": 600.0,
            "samplingIntervalSeconds": 5.0,
            "offeredJourneys": 90,
            "applicationCpuSecondsPerOfferedJourney": 30.0 / 90,
        } if regime == "no-fault-cost" else None,
        "intervention": intervention,
        "telemetry": {
            "collectorStats": collector_stats,
            "spool": spool_summary,
        },
    }
    capture = {
        "complete": True,
        "settled": True,
        "hashReconciled": True,
        "queuePurgedBefore": True,
        "queueMessagesAtBarrier": 0,
        "exclusiveCollector": True,
        "foreignWriters": 0,
        "unjoinedChildren": 0,
        "rawRecords": len(traces),
        "measurementRecords": len(traces),
        "uniqueNativeTraces": len({str(row["kieker_trace_id"]) for row in traces}),
        "uniqueSignatures": len({row["signature_sha1"] for row in traces}),
        "uniqueMessageBodies": len({row["message_sha1"] for row in traces}),
        "redeliveredMessageSha1": [],
    }
    _write_json(root / "journey-ledger.plan.json", plan)
    _write_jsonl(root / "journey-ledger.jsonl", ledger_records)
    for service in ("auth", "persistence"):
        source_rows = [
            {
                "schema": app_witness.OBSERVATION_SCHEMA,
                "schemaVersion": 1,
                "observedAtUtc": row[f"{service}ObservedAtUtc"],
                "journeyId": row["opaqueToken"],
                "service": service,
                "event": app_witness.SERVICES[service],
            }
            for row in witnesses
        ]
        app_lines = "".join(
                app_witness.MARKER + json.dumps(row, sort_keys=True) + "\n"
                for row in source_rows
            )
        bridge_lines = ""
        if service == "auth" and posture != "none":
            bridge_lines = "".join(
                native_token.MARKER + json.dumps({
                    "token": row["opaqueToken"],
                    "nativeTraceId": str(10_000 + index),
                    "service": "auth",
                }, separators=(",", ":")) + "\n"
                for index, row in enumerate(witnesses)
            )
        (root / f"{service}.log").write_text(
            app_lines + bridge_lines, encoding="utf-8")
    _write_jsonl(root / "app-witness.jsonl", witnesses)
    witness_phase_counts = (
        {"measurement": 90}
        if regime == "no-fault-cost"
        else {"before": 27, "during": 23, "after": 40}
    )
    scored = 90 if regime == "no-fault-cost" else 67
    extraction = {
        "schema": "teastore.app-witness-extraction-receipt",
        "schemaVersion": 1,
        "status": "complete",
        "sourceCommit": candidate_pilot.SUT_COMMIT,
        "regime": regime,
        "measurementWindow": {
            "startedAt": _time(MEASUREMENT), "endedAt": _time(END),
        },
        "counts": {
            "ledgerOpportunities": 90,
            "requiredScoredOpportunities": scored,
            "completeWitnessPaths": 90,
            "partialOptionalObservations": 0,
            "authObservations": 90,
            "persistenceObservations": 90,
            "phases": witness_phase_counts,
        },
        "inputs": {
            "authLogSha256": hashlib.sha256((root / "auth.log").read_bytes()).hexdigest(),
            "persistenceLogSha256": hashlib.sha256((root / "persistence.log").read_bytes()).hexdigest(),
            "journeyLedgerSha256": hashlib.sha256((root / "journey-ledger.jsonl").read_bytes()).hexdigest(),
            "journeyPlanSha256": hashlib.sha256((root / "journey-ledger.plan.json").read_bytes()).hexdigest(),
        },
        "journeyLedgerValidation": {
            "verdict": "pass",
            "planSha256": plan_sha,
            "lastRecordSha256": reconciliation["recordSha256"],
            "terminalJourneys": 90,
            "state": "completed",
        },
        "appWitnessSha256": hashlib.sha256((root / "app-witness.jsonl").read_bytes()).hexdigest(),
    }
    _write_json(root / "app-witness-extraction.json", extraction)
    _write_json(root / "traces.json", traces)
    _write_json(root / "capture-terminal.json", capture)
    if intervention is not None:
        _write_json(root / "intervention.json", intervention)
    _write_json(root / "receipt.json", receipt)
    service_log_capture = {
        "schema": "teastore.service-log-capture-receipt",
        "schemaVersion": 1,
        "status": "complete",
        "runId": receipt["run"]["runId"],
        "service": "auth",
        "containerId": "a" * 64,
        "source": "docker-container-stdout-stderr",
        "measurementWindow": {
            "startedAt": _time(MEASUREMENT), "endedAt": _time(END),
        },
        "capturedLog": {
            "scope": "measurement-window",
            "path": "auth.log",
            "sha256": hashlib.sha256((root / "auth.log").read_bytes()).hexdigest(),
            "complete": True,
        },
        "logParameters": {
            "name": "LOG_PARAMETERS",
            "inspectionSource": "container-config-env",
            "state": "absent",
            "rawValue": None,
            "parameterLoggingEnabled": False,
        },
    }
    _write_json(root / "service-log-capture.json", service_log_capture)
    native_token.extract(
        auth_log=root / "auth.log",
        journey_ledger=root / "journey-ledger.jsonl",
        traces=root / "traces.json",
        run_receipt=root / "receipt.json",
        service_log_capture_receipt=root / "service-log-capture.json",
        output=root / "native-token-correlation.json",
        extraction_receipt=root / "native-token-correlation-extraction.json",
    )
    _rehash(root)
    return root


def _mutate_json(root: Path, name: str, mutate, *, rehash=True):
    value = _load(root / name)
    mutate(value)
    _write_json(root / name, value)
    if rehash:
        _rehash(root)


def _mutate_jsonl(root: Path, name: str, mutate, *, rehash=True):
    value = _load_jsonl(root / name)
    mutate(value)
    _write_jsonl(root / name, value)
    if rehash:
        _rehash(root)


def _failed(report, gate):
    return any(row["gate"] == gate and row["status"] == "fail" for row in report["validationTable"])


def _forge_resource_cpu_and_matching_receipt(root: Path):
    resources = _load(root / "resources.json")
    resources["applicationCpuSeconds"] = 999.0
    _write_json(root / "resources.json", resources)
    receipt = _load(root / "receipt.json")
    receipt["resources"]["applicationCpuSeconds"] = 999.0
    receipt["resources"]["applicationCpuSecondsPerOfferedJourney"] = 999.0 / 90
    _write_json(root / "receipt.json", receipt)
    _rehash(root)


def test_cost_cell_blocks_when_resource_artifact_is_missing(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="no-fault-cost")
    (root / "resources.json").unlink()
    _rehash(root)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert report["cellStatus"] == "missing-artifact"
    assert _failed(report, "artifact-presence")
    assert _failed(report, "resource-cost-evidence")


def test_cost_cell_blocks_when_resource_artifact_is_malformed(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="no-fault-cost")
    (root / "resources.json").write_text('{"schemaVersion":3,"schemaVersion":4}', encoding="utf-8")
    _rehash(root)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert report["cellStatus"] == "missing-artifact"
    assert _failed(report, "resources-parse")
    assert _failed(report, "resource-cost-evidence")


def test_cost_cell_blocks_forged_resource_projection_even_when_rehashed(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="no-fault-cost")
    _forge_resource_cpu_and_matching_receipt(root)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert _failed(report, "resource-cost-evidence")
    row = next(row for row in report["validationTable"] if row["gate"] == "resource-cost-evidence")
    assert row["observation"]["replay"]["verdict"] == "blocked"


def test_effect_cell_supports_claim_without_resource_artifact(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    (root / "resources.json").unlink()
    _rehash(root)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "pass"
    row = next(
        row for row in report["validationTable"]
        if row["gate"] == "resource-effect-claim-boundary"
    )
    assert row["status"] == "pass"
    assert row["observation"] == {
        "analysisKind": "effect",
        "resourceUse": "diagnostic-only",
        "artifactAvailability": "absent",
        "artifactSha256": {"declared": None, "actual": None},
        "parseError": None,
        "resourcesExcludedFromEffectClaims": True,
        "costProjection": None,
        "receiptResourceProjection": {
            "present": True,
            "isNull": True,
            "fields": None,
        },
        "strictResourceReplay": "not-run-for-effect-cell",
    }


def test_effect_cell_supports_claim_when_diagnostic_resources_are_unreadable(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="persistence-crash-effect", posture="full")
    (root / "resources.json").write_text("{not-json\n", encoding="utf-8")
    _rehash(root)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "pass"
    assert not _failed(report, "resources-parse")
    row = next(
        row for row in report["validationTable"]
        if row["gate"] == "resource-effect-claim-boundary"
    )
    assert row["status"] == "pass"
    assert row["observation"]["artifactAvailability"] == "unavailable"
    assert row["observation"]["parseError"]
    assert row["observation"]["resourcesExcludedFromEffectClaims"] is True
    assert row["observation"]["costProjection"] is None


def test_effect_cell_blocks_cost_projection_leaked_into_receipt(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    receipt = _load(root / "receipt.json")
    receipt["resources"] = {
        "applicationCpuSecondsPerOfferedJourney": 30.0 / 90,
    }
    _write_json(root / "receipt.json", receipt)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert _failed(report, "resource-effect-claim-boundary")
    row = next(
        row for row in report["validationTable"]
        if row["gate"] == "resource-effect-claim-boundary"
    )
    assert row["observation"]["resourcesExcludedFromEffectClaims"] is True
    assert row["observation"]["receiptResourceProjection"] == {
        "present": True,
        "isNull": False,
        "fields": ["applicationCpuSecondsPerOfferedJourney"],
    }


def test_selected_run_releases_separate_raw_signature_and_path_views(tmp_path: Path):
    root = make_run(tmp_path / "run")
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "pass"
    assert report["views"]["raw"] == {
        "records": 180,
        "originalNativeTraces": 90,
        "uniqueMessageBodies": 90,
        "diagnosticTailOrOutsideRecords": 0,
    }
    assert report["views"]["signatureWeighted"]["uniqueSignatures"] == 2
    assert report["views"]["signatureWeighted"]["topOperationConcentration"] == 0.5
    assert report["views"]["path"]["expectedOpportunities"] == 90
    assert report["reconstruction"] == {
        "status": "supported", "eligibleExecutedPaths": 90,
        "reconstructedPaths": 90, "fraction": 1.0,
    }


@pytest.mark.parametrize("posture", ["none", "selected"])
def test_candidate_rejects_hash_bound_malformed_spool_body(
    tmp_path: Path, posture: str,
):
    root = make_run(tmp_path / "run", posture=posture)
    _plant_malformed_spool_body(root)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "native-spool-collector-and-attribution-binding")


@pytest.mark.parametrize("field", ["block", "attempt"])
def test_candidate_rejects_boolean_run_identity(tmp_path: Path, field: str):
    root = make_run(tmp_path / "run")
    receipt = _load(root / "receipt.json")
    receipt["run"][field] = True
    _write_json(root / "receipt.json", receipt)
    _rehash(root)
    report = candidate_pilot.validate_run(
        root, expected={"block": 1, "attempt": 1},
    )
    assert report["verdict"] == "blocked"
    assert _failed(report, "frozen-run-identity")
    assert _failed(report, "campaign-run-binding")


def test_candidate_receipt_v1_and_missing_or_trailing_spool_are_rejected(
    tmp_path: Path,
):
    for defect in ("v1", "missing", "trailing"):
        root = make_run(tmp_path / defect)
        if defect == "v1":
            receipt = _load(root / "receipt.json")
            receipt["schemaVersion"] = 1
            _write_json(root / "receipt.json", receipt)
            _rehash(root)
        elif defect == "missing":
            (root / "kieker-amqp.spool").unlink()
            _rehash(root)
        else:
            with (root / "kieker-amqp.spool").open("ab") as stream:
                stream.write(b"planted-trailing")
            receipt = _load(root / "receipt.json")
            receipt["source"]["spoolSha256"] = hashlib.sha256(
                (root / "kieker-amqp.spool").read_bytes()
            ).hexdigest()
            _write_json(root / "receipt.json", receipt)
            _rehash(root)
        assert candidate_pilot.validate_run(root)["verdict"] == "blocked"


def test_candidate_rejects_suffix_lookalike_native_record_class(tmp_path: Path):
    root = make_run(tmp_path / "run")
    traces = _load(root / "traces.json")
    traces[0]["native_record_class"] = "attacker.shadow.OperationExecutionRecord"
    _write_json(root / "traces.json", traces)
    _reextract_native_token(root)
    _rehash(root)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "native-spool-collector-and-attribution-binding")
    assert _failed(report, "native-event-correlation-and-attribution-integrity")


def test_actual_witness_extractor_output_crosses_candidate_validator(tmp_path: Path):
    root = make_run(tmp_path / "run")
    expected_witnesses = _load_jsonl(root / "app-witness.jsonl")

    def source_row(row, service):
        return {
            "schema": app_witness.OBSERVATION_SCHEMA,
            "schemaVersion": 1,
            "observedAtUtc": row[f"{service}ObservedAtUtc"],
            "journeyId": row["opaqueToken"],
            "service": service,
            "event": app_witness.SERVICES[service],
        }

    for service in ("auth", "persistence"):
        rows = [source_row(row, service) for row in expected_witnesses]
        bridge_lines = []
        if service == "auth":
            bridge_lines = [
                line + "\n" for line in (root / "auth.log").read_text().splitlines()
                if native_token.MARKER in line
            ]
        (root / f"{service}.log").write_text(
            "".join(
                app_witness.MARKER + json.dumps(row, sort_keys=True) + "\n"
                for row in rows
            ) + "".join(bridge_lines),
            encoding="utf-8",
        )
    (root / "app-witness.jsonl").unlink()
    (root / "app-witness-extraction.json").unlink()
    app_witness.extract(
        auth_log=root / "auth.log",
        persistence_log=root / "persistence.log",
        journey_ledger=root / "journey-ledger.jsonl",
        run_receipt=root / "receipt.json",
        output=root / "app-witness.jsonl",
        extraction_receipt=root / "app-witness-extraction.json",
    )
    capture = _load(root / "service-log-capture.json")
    capture["capturedLog"]["sha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write_json(root / "service-log-capture.json", capture)
    _reextract_native_token(root)
    _rehash(root)

    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "pass"
    assert not _failed(report, "application-witness-extraction")


def test_raw_application_log_replay_watches_hash_consistent_fabrication(tmp_path: Path):
    root = make_run(tmp_path / "run")
    (root / "auth.log").write_text("fabricated non-marker text\n", encoding="utf-8")
    extraction = _load(root / "app-witness-extraction.json")
    extraction["inputs"]["authLogSha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write_json(root / "app-witness-extraction.json", extraction)
    _rehash(root)

    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert _failed(report, "application-source-log-replay")


def test_raw_application_log_replay_rejects_non_marker_secret_text(tmp_path: Path):
    root = make_run(tmp_path / "run")
    with (root / "auth.log").open("a", encoding="utf-8") as stream:
        stream.write("password=planted-not-a-real-secret\n")
    extraction = _load(root / "app-witness-extraction.json")
    extraction["inputs"]["authLogSha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write_json(root / "app-witness-extraction.json", extraction)
    _rehash(root)

    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert _failed(report, "application-source-log-replay")


def test_raw_application_log_replay_rejects_quoted_json_secret_text(tmp_path: Path):
    root = make_run(tmp_path / "run")
    with (root / "auth.log").open("a", encoding="utf-8") as stream:
        stream.write('{"password":"planted-not-a-real-secret"}\n')
    extraction = _load(root / "app-witness-extraction.json")
    extraction["inputs"]["authLogSha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write_json(root / "app-witness-extraction.json", extraction)
    _rehash(root)

    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert _failed(report, "application-source-log-replay")


@pytest.mark.parametrize("planted", [
    '{"pass\\u0077ord":"planted-not-a-real-secret"}\n',
    '{"message":"{\\"password\\":\\"planted-not-a-real-secret\\"}"}\n',
    'prefix {"password"\n : "planted-not-a-real-secret"}\n',
    "normal-log-prefix " + json.dumps(json.dumps(
        '{"pass\\u0077ord":"planted-not-a-real-secret"}')) + "\n",
    _nested_secret_log(10),
    'normal-log-prefix {"pass_word":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"db_password":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"_password_":"planted-not-a-real-secret"}\n',
    'normal-log-prefix {"paßword":"planted-not-a-real-secret"}\n',
])
def test_raw_application_replay_rejects_encoded_or_multiline_secret_text(
        tmp_path: Path, planted: str):
    root = make_run(tmp_path / "run")
    with (root / "auth.log").open("a", encoding="utf-8") as stream:
        stream.write(planted)
    extraction = _load(root / "app-witness-extraction.json")
    extraction["inputs"]["authLogSha256"] = hashlib.sha256(
        (root / "auth.log").read_bytes()).hexdigest()
    _write_json(root / "app-witness-extraction.json", extraction)
    _rehash(root)

    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert _failed(report, "application-source-log-replay")


def test_none_scores_zero_only_with_independent_denominator_and_terminal_empty_capture(tmp_path: Path):
    root = make_run(tmp_path / "run", posture="none")
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "pass"
    assert report["reconstruction"] == {
        "status": "supported", "eligibleExecutedPaths": 90,
        "reconstructedPaths": 0, "fraction": 0.0,
    }
    _mutate_json(root, "capture-terminal.json", lambda value: value.update(settled=False))
    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert report["reconstruction"]["fraction"] is None
    assert _failed(report, "terminal-capture-reconciliation")


def test_expected_opportunities_are_not_assumed_to_have_executed(tmp_path: Path):
    root = make_run(tmp_path / "run")
    def not_executed(rows):
        rows[0].update(executedPath=[], authTraversed=False, persistenceTraversed=False)
    _mutate_jsonl(root, "app-witness.jsonl", not_executed)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert report["views"]["path"]["expectedOpportunities"] == 90
    assert report["reconstruction"]["eligibleExecutedPaths"] is None


def test_missing_witness_is_unsupported_and_never_zero(tmp_path: Path):
    root = make_run(tmp_path / "run", posture="none")
    (root / "app-witness.jsonl").unlink()
    _rehash(root)
    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert report["reconstruction"]["reconstructedPaths"] is None
    assert _failed(report, "app-witness-presence")
    assert _failed(report, "independent-execution-denominator")


def test_missing_token_correlation_is_unsupported_not_observed_failure(tmp_path: Path):
    root = make_run(tmp_path / "run")
    _mutate_json(root, "traces.json", lambda rows: [row.update(opaqueToken="wrong") for row in rows[:2]])
    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert report["reconstruction"]["fraction"] is None
    assert _failed(report, "opaque-token-native-trace-correlation")


def test_mapping_outside_independently_eligible_denominator_is_unsupported(
    monkeypatch, tmp_path: Path,
):
    root = make_run(
        tmp_path / "run", posture="selected", regime="auth-freeze-effect")
    rows = _load(root / "native-token-correlation.json")
    rows.append({
        "mappingId": "f" * 64,
        "token": f"journey-{27:032x}",
        "nativeTraceId": str(10_000 + 27),
        "service": "auth",
    })
    _write_json(root / "native-token-correlation.json", rows)
    _rehash(root)

    class PassingNativeValidator:
        @staticmethod
        def validate_retained(_root):
            return {"outcome": "pass", "blockers": []}

    monkeypatch.setattr(
        candidate_pilot, "_native_token_validator",
        lambda: PassingNativeValidator)
    report = candidate_pilot.validate_run(root)

    assert report["cellStatus"] == "unsupported"
    assert report["reconstruction"]["fraction"] is None
    assert _failed(report, "opaque-token-native-trace-correlation")


def test_unhashable_native_mapping_identity_is_structured_unsupported(
    tmp_path: Path,
):
    root = make_run(tmp_path / "run", posture="selected")
    rows = _load(root / "native-token-correlation.json")
    rows[0]["token"] = ["not", "a", "scalar"]
    _write_json(root / "native-token-correlation.json", rows)
    _rehash(root)

    report = candidate_pilot.validate_run(root)

    assert report["cellStatus"] == "unsupported"
    assert report["reconstruction"]["fraction"] is None
    assert _failed(report, "native-token-correlation-artifact")
    assert _failed(report, "opaque-token-native-trace-correlation")


def test_direct_edge_requires_parent_equality_inside_same_original_trace(tmp_path: Path):
    root = make_run(tmp_path / "run")
    _mutate_json(root, "traces.json", lambda rows: rows[1].update(parent_id="unrelated"))
    _reextract_native_token(root)
    _rehash(root)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "native-spool-collector-and-attribution-binding")


def test_cross_trace_assembly_is_unsupported_not_counted_as_an_edge(tmp_path: Path):
    root = make_run(tmp_path / "run")
    _mutate_json(root, "traces.json", lambda rows: rows[1].update(original_native_trace_id="other-native"))
    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "unsupported"
    assert report["reconstruction"]["fraction"] is None
    assert _failed(report, "opaque-token-native-trace-correlation")


@pytest.mark.parametrize(
    ("gate", "mutation"),
    [
        ("frozen-run-identity", lambda root: _mutate_json(
            root, "receipt.json", lambda value: value.update(population="full-journey"), rehash=False)),
        ("provenance-and-host-lease", lambda root: _mutate_json(
            root, "receipt.json", lambda value: value["source"].update(frameworkDirty=True), rehash=False)),
        ("artifact-hash-binding", lambda root: _mutate_jsonl(
            root, "journey-ledger.jsonl", lambda rows: rows[0].update(errors=[{
                "type": "Planted", "scope": "journey", "requestSequence": None,
            }]), rehash=False)),
        ("pre-outcome-plan-and-ledger-chain", lambda root: _mutate_jsonl(
            root, "journey-ledger.jsonl", lambda rows: rows[0].update(previousRecordSha256="f" * 64))),
        ("shared-window", lambda root: _mutate_json(
            root, "receipt.json", lambda value: value["window"].update(measurementEndMonotonic=719), rehash=False)),
        ("offered-ledger-denominator", lambda root: _mutate_jsonl(
            root, "journey-ledger.jsonl", lambda rows: rows[1].update(journeyId=rows[0]["journeyId"]))),
        ("journey-ledger-integrity", lambda root: _mutate_jsonl(
            root, "journey-ledger.jsonl", lambda rows: rows[0].update(tokenAllocatedAt=rows[0]["endedAt"]))),
        ("outcome-and-latency-denominators", lambda root: _mutate_json(
            root, "receipt.json", lambda value: value["latencyMs"].update(count=89), rehash=False)),
        ("resource-cost-evidence", _forge_resource_cpu_and_matching_receipt),
        ("cost-effect-separation", lambda root: _mutate_json(
            root, "receipt.json", lambda value: value.update(analysisKind="effect"), rehash=False)),
        ("no-fault-workload-context", lambda root: _mutate_jsonl(
            root, "journey-ledger.jsonl", lambda rows: rows[0].update(outcome="failed", errors=[{
                "type": "Planted", "scope": "journey", "requestSequence": None,
            }]))),
        ("native-timestamp-window", lambda root: _mutate_json(
            root, "traces.json", lambda rows: rows[0].update(nativeTimestamp="not-a-timestamp"))),
        ("original-native-trace-provenance", lambda root: _mutate_json(
            root, "traces.json", lambda rows: rows[0].update(source="scraper-generated"))),
        ("replay-and-duplicate-control", lambda root: _mutate_json(
            root, "traces.json", lambda rows: rows.extend([dict(rows[0]), dict(rows[1])]))),
        ("terminal-capture-reconciliation", lambda root: _mutate_json(
            root, "capture-terminal.json", lambda value: value.update(rawRecords=179))),
        ("posture-capture-domain", lambda root: _mutate_json(
            root, "receipt.json", lambda value: value["run"].update(posture="none"), rehash=False)),
        ("independent-execution-denominator", lambda root: _mutate_jsonl(
            root, "app-witness.jsonl", lambda rows: rows[0].update(independentOfKieker=False))),
        ("opaque-token-native-trace-correlation", lambda root: _mutate_json(
            root, "traces.json", lambda rows: rows.__delitem__(slice(0, 2)))),
    ],
)
def test_each_run_gate_watches_a_planted_defect(tmp_path: Path, gate, mutation):
    root = make_run(tmp_path / "run")
    mutation(root)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, gate), json.dumps(report["validationTable"], indent=2)


def test_artifact_presence_watches_deleted_core_artifact(tmp_path: Path):
    root = make_run(tmp_path / "run")
    (root / "traces.json").unlink()
    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "missing-artifact"
    assert _failed(report, "artifact-presence")


@pytest.mark.parametrize(
    ("name", "gate", "status"),
    [
        ("receipt.json", "receipt-parse", "missing-artifact"),
        ("resources.json", "resources-parse", "missing-artifact"),
        ("journey-ledger.plan.json", "plan-parse", "missing-artifact"),
        ("journey-ledger.jsonl", "journeys-parse", "missing-artifact"),
        ("app-witness.jsonl", "witnesses-parse", "unsupported"),
        ("app-witness-extraction.json", "witnessExtraction-parse", "unsupported"),
        ("traces.json", "traces-parse", "missing-artifact"),
        ("capture-terminal.json", "capture-parse", "missing-artifact"),
    ],
)
def test_each_artifact_parser_watches_malformed_bytes(tmp_path: Path, name, gate, status):
    root = make_run(tmp_path / "run")
    (root / name).write_text("{not-json\n", encoding="utf-8")
    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == status
    assert _failed(report, gate)


@pytest.mark.parametrize(
    ("name", "payload", "gate"),
    [
        ("receipt.json", '{"contract":"a","contract":"b"}', "receipt-parse"),
        ("traces.json", '[{"timestamp":NaN}]', "traces-parse"),
        ("app-witness.jsonl", '{"schema":1,"schema":2}\n', "witnesses-parse"),
    ],
)
def test_strict_parsers_watch_duplicate_keys_and_nonfinite_values(tmp_path: Path, name, payload, gate):
    root = make_run(tmp_path / "run")
    (root / name).write_text(payload, encoding="utf-8")
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, gate)


def test_jsonl_parser_watches_truncated_final_record(tmp_path: Path):
    root = make_run(tmp_path / "run")
    ledger = root / "journey-ledger.jsonl"
    ledger.write_bytes(ledger.read_bytes().rstrip(b"\n"))
    report = candidate_pilot.validate_run(root)
    assert report["cellStatus"] == "missing-artifact"
    assert _failed(report, "journeys-parse")


def test_campaign_binding_watches_receipt_self_relabeling(tmp_path: Path):
    root = make_run(tmp_path / "run")
    report = candidate_pilot.validate_run(root, {
        "studyEpoch": candidate_pilot.STUDY_EPOCH,
        "regime": "no-fault-cost", "block": 1, "posture": "full", "attempt": 1,
    })
    assert _failed(report, "campaign-run-binding")


@pytest.mark.parametrize(
    ("gate", "mutation"),
    [
        ("independent-fault-ground-truth", lambda root: _mutate_json(
            root, "receipt.json", lambda value: value["intervention"].update(manifested=False), rehash=False)),
        ("actual-phase-start-floor", lambda root: _mutate_jsonl(
            root, "journey-ledger.jsonl",
            lambda rows: [row.update(actualStartMonotonic=460 + index, startedAt=_time(MEASUREMENT + timedelta(seconds=340 + index)),
                                     actualEndMonotonic=461 + index, endedAt=_time(MEASUREMENT + timedelta(seconds=341 + index)),
                                     requests=[{"route": "login", "startedAt": _time(MEASUREMENT + timedelta(seconds=340 + index)),
                                                "endedAt": _time(MEASUREMENT + timedelta(seconds=341 + index))}])
                          for index, row in enumerate(rows[:10])])),
        ("effect-context", lambda root: _mutate_jsonl(
            root, "journey-ledger.jsonl", lambda rows: rows[0].update(outcome="failed", errors=[{
                "type": "Planted", "scope": "journey", "requestSequence": None,
            }]))),
    ],
)
def test_each_effect_gate_watches_a_planted_defect(tmp_path: Path, gate, mutation):
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    mutation(root)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, gate), json.dumps(report["validationTable"], indent=2)


def test_valid_effect_run_uses_actual_phase_starts(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="persistence-crash-effect", posture="full")
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "pass"
    phase_row = next(row for row in report["validationTable"] if row["gate"] == "actual-phase-start-floor")
    assert phase_row["observation"] == {"before": 27, "during": 23, "after": 40}


def test_intervention_artifact_gate_watches_missing_separate_receipt(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    (root / "intervention.json").unlink()
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "intervention-artifact-binding")


def test_actual_fault_generator_schema_crosses_candidate_validator(monkeypatch, tmp_path: Path):
    container_id = "c" * 64
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "obst-evidence")
    monkeypatch.setattr(performance_campaign, "service_container", lambda *_args: container_id)
    states = iter((
        {"exists": True, "running": True, "paused": False},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": True},
        {"exists": True, "running": True, "paused": False},
    ))
    monkeypatch.setattr(performance_campaign, "container_state", lambda _target: next(states))
    monkeypatch.setattr(performance_campaign, "wait_ready", lambda: None)
    monotonic = iter((0.0, 1180.0, 1180.0, 1255.0, 1330.0, 1331.0))
    monkeypatch.setattr(performance_campaign.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(performance_campaign.time, "sleep", lambda _seconds: None)
    wall = iter((
        _time(MEASUREMENT), _time(MEASUREMENT + timedelta(seconds=180)),
        _time(MEASUREMENT + timedelta(seconds=255)), _time(MEASUREMENT + timedelta(seconds=330)),
        _time(MEASUREMENT + timedelta(seconds=331)), _time(MEASUREMENT + timedelta(seconds=332)),
    ))
    monkeypatch.setattr(performance_campaign, "now", lambda: next(wall))
    monkeypatch.setattr(
        performance_campaign, "command",
        lambda args, check=False: subprocess.CompletedProcess(args, 0, "", ""),
    )
    image = {
        "containerId": container_id,
        "declaredImage": "teastore-auth:latest",
        "containerImageId": "sha256:" + "d" * 64,
        "imageInspectId": "sha256:" + "d" * 64,
        "repoDigests": ["teastore-auth@sha256:" + "e" * 64],
    }
    generator_root = tmp_path / "generator"
    generator_root.mkdir()
    intervention = performance_campaign.inject_fault(
        "auth-freeze", 180, 150, generator_root, posture="full",
        measurement_barrier_epoch=MEASUREMENT.timestamp(),
        measurement_barrier_monotonic=1000.0,
        measurement_barrier_id=BARRIER,
        target_image=image,
    )
    performance_campaign.bind_intervention_thread(
        intervention, generator_root, joined=True,
    )
    root = make_run(tmp_path / "run", regime="auth-freeze-effect", posture="full")
    receipt = _load(root / "receipt.json")
    receipt["intervention"] = intervention
    _write_json(root / "receipt.json", receipt)
    _write_json(root / "intervention.json", intervention)
    _rehash(root)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "pass", json.dumps(report["validationTable"], indent=2)


def _manifest():
    digests, schedules = candidate_pilot.recompute_schedule()
    runs = [
        {"studyEpoch": candidate_pilot.STUDY_EPOCH, "regime": regime, "block": block,
         "posture": posture, "attempt": 1, "ordinal": ordinal,
         "path": f"runs/{regime}/b{block:02d}-{ordinal:02d}-{posture}"}
        for regime in candidate_pilot.REGIMES
        for block, row in enumerate(candidate_pilot.EXPECTED_SCHEDULES[regime], 1)
        for ordinal, posture in enumerate(row, 1)
    ]
    return {
        "contract": candidate_pilot.CONTRACT,
        "studyEpoch": candidate_pilot.STUDY_EPOCH,
        "scheduleVersion": "schedule-v1",
        "selectorDigests": digests,
        "schedules": schedules,
        "runs": runs,
    }


def make_campaign(root: Path):
    manifest = _manifest()
    for run in manifest["runs"]:
        make_run(root / run["path"], regime=run["regime"], posture=run["posture"], block=run["block"])
    _write_json(root / "campaign.json", manifest)
    return root


def test_campaign_exact_frozen_population_passes(tmp_path: Path):
    root = make_campaign(tmp_path / "campaign")
    report = candidate_pilot.validate_campaign(root)
    assert report["verdict"] == "pass"
    assert len(report["runReports"]) == 27


def test_campaign_manifest_gate_watches_absent_manifest(tmp_path: Path):
    report = candidate_pilot.validate_campaign(tmp_path)
    assert report["campaignStatus"] == "missing-artifact"
    assert _failed(report, "campaign-manifest")


@pytest.mark.parametrize(
    ("gate", "mutation"),
    [
        ("frozen-schedule-recomputation", lambda manifest: manifest["selectorDigests"].update(
            {"no-fault-cost": "0" * 64})),
        ("scheduled-cell-population", lambda manifest: manifest["runs"].pop()),
        ("separate-regime-artifact-roots", lambda manifest: manifest["runs"][1].update(
            path=manifest["runs"][0]["path"])),
    ],
)
def test_campaign_gates_watch_planted_manifest_defects(tmp_path: Path, gate, mutation):
    root = tmp_path / "campaign"
    root.mkdir()
    manifest = _manifest()
    mutation(manifest)
    _write_json(root / "campaign.json", manifest)
    report = candidate_pilot.validate_campaign(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, gate)


def test_campaign_all_run_gate_watches_one_corrupt_scheduled_cell(tmp_path: Path):
    root = make_campaign(tmp_path / "campaign")
    first = root / _manifest()["runs"][0]["path"]
    _mutate_jsonl(first, "app-witness.jsonl", lambda rows: rows.pop())
    report = candidate_pilot.validate_campaign(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "all-run-evidence")


def test_cli_exit_status_and_machine_readable_validation_table(tmp_path: Path, capsys):
    root = make_run(tmp_path / "run")
    assert candidate_pilot.main([str(root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["validationTable"]
    assert {"observation", "inference", "conclusion"} <= result["validationTable"][0].keys()
    (root / "app-witness.jsonl").unlink()
    assert candidate_pilot.main([str(root)]) == 2
