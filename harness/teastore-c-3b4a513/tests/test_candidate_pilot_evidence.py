import hashlib
import importlib.util
import json
import math
import re
import struct
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
WARMUP_END = WARMUP + timedelta(seconds=120)
WARMUP_SETTLED = WARMUP + timedelta(seconds=115)
MEASUREMENT = WARMUP_END + timedelta(seconds=20)
END = MEASUREMENT + timedelta(seconds=600)
BARRIER = "barrier-" + "a" * 32


def _write_operational_proofs(root: Path, posture: str) -> None:
    catalog_path = Path(__file__).parents[1] / "modules/teastore/activation/catalog.json"
    goal_path = Path(__file__).parents[1] / "modules/teastore/goals/fault-qualification.json"
    catalog = _load(catalog_path)
    compiler = candidate_pilot._selection_compiler()
    selection_ids = {
        "selected": "fault-qualification", "full": "catalog-all", "none": "catalog-empty",
    }
    requested = (
        sorted(_load(goal_path)["logicalSensors"]) if posture == "selected"
        else sorted(row["id"] for row in catalog["logicalSensors"]) if posture == "full"
        else []
    )
    compiled = compiler.compile_selection(catalog, requested)
    catalog_groups = sorted(row["id"] for row in catalog["activationGroups"])
    required = list(compiled["selectedActivationGroups"])
    aop_sha = hashlib.sha256(compiler.render_aop(compiled).encode()).hexdigest()
    configuration = f"kieker.monitoring.enabled={'false' if posture == 'none' else 'true'}"
    services = {
        service: {"aopSha256": aop_sha, "configuration": configuration,
                  "writerInitializationFailed": False}
        for service in ("auth", "image", "persistence", "recommender", "webui")
    }
    _write_json(root / "posture-proof.json", {
        "schemaVersion": 3, "requested": posture,
        "catalogId": catalog["id"],
        "catalogSha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "selectionId": selection_ids[posture],
        "goalLogicalSensors": requested,
        "closureGroups": required, "requiredGroups": required,
        "forbiddenGroups": sorted(set(catalog_groups) - set(required)),
        "aopSha256": aop_sha,
        "manifestSha256": hashlib.sha256(
            (json.dumps(compiled, indent=2, sort_keys=True) + "\n").encode()).hexdigest(),
        "monitoringEnabled": posture != "none",
        "services": services,
    })
    container = "f" * 64
    def state(messages: int, consumers: int) -> dict:
        argv = ["docker", "exec", container, "rabbitmqctl", "list_queues",
                "-q", "name", "messages", "consumers"]
        stdout = f"kieker\t{messages}\t{consumers}\n"
        return {"containerId": container, "messages": messages, "consumers": consumers,
                "query": {"command": argv, "returnCode": 0, "stdout": stdout, "stderr": ""}}
    purge_argv = ["docker", "exec", container, "rabbitmqctl", "purge_queue", "kieker"]
    _write_json(root / "queue-proof.json", {
        "schemaVersion": 2, "composeProject": "teastore_candidate_fixture",
        "broker": {
            "schemaVersion": 2,
            "queries": {
                name: {"command": ["docker", "exec", container, "rabbitmqctl", name],
                       "returnCode": 0, "stdout": "", "stderr": ""}
                for name in ("heartbeat", "queueArguments", "connections")
            },
            "heartbeatSeconds": 0,
            "queueArguments": 'kieker\t[{"x-max-length",50000},{"x-overflow","reject-publish"}]',
            "connections": [
                {"user": "admin", "peerHost": "172.18.0.5",
                 "timeoutSeconds": timeout,
                 "clientProperties": '[{"product","RabbitMQ"},{"platform","Java"}]'}
                for timeout in (0, 900, 900, 900, 900, 900)
            ],
            "connectionTimeouts": [0, 900, 900, 900, 900, 900],
        },
        "purge": {"before": state(0, 0),
                  "command": {"command": purge_argv, "returnCode": 0,
                              "stdout": "Purging queue 'kieker'\n", "stderr": ""},
                  "after": state(0, 0)},
        "measurement": {"before": state(0, 0), "consumerAtStart": state(0, 1),
                        "after": state(0, 0),
                        "depthSamples": [
                            {"monotonicOffsetSeconds": float(offset), "messages": 12,
                             "consumers": 1}
                            for offset in range(0, 600, 5)
                        ]},
    })


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
        posture_proof=root / "posture-proof.json",
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


def _system_samples(regime: str) -> dict:
    """What collectors/system_probe.py writes: 121 rows; persistence is null while stopped."""
    start = MEASUREMENT.timestamp()
    services = candidate_pilot.SYSTEM_REQUIRED_SERVICES
    rows = []
    for index in range(candidate_pilot.SYSTEM_SAMPLE_COUNT):
        row = {
            service: {
                "cpuUsageUsec": 1_000_000 + index * 1000, "memoryCurrent": 1 << 28,
                "rbytes": 0, "wbytes": 4096 * index, "psiCpuSomeTotalUsec": 10 * index,
                "psiMemorySomeTotalUsec": 0, "psiIoSomeTotalUsec": 0,
            }
            for service in services
        }
        if regime == "persistence-crash-effect" and 37 <= index <= 66:
            row["persistence"] = None
        rows.append({
            "epoch": start + index * 5.0, "at": "x", "monotonic": 500.0 + index * 5.0,
            "lateSeconds": 0.002, "services": row,
            "daemons": {"docker.service": 5000 + index, "containerd.service": 7000 + index},
        })
    return {
        "schemaVersion": 1, "kind": candidate_pilot.SYSTEM_SAMPLES_KIND,
        "project": "teastore_candidate_0123456789abcdef", "intervalSeconds": 5.0,
        "durationSeconds": 600.0, "startAtEpoch": start,
        "containers": {service: "c" * 64 for service in services},
        "requiredServices": sorted(services), "requiredMissingAtStart": [], "samples": rows,
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
    plan_schedule_truncated_micros: bool = False,
    plan_schedule_skew_micros: dict[int, int] | None = None,
    token_allocated_at: str | None = None,
    skip_native_token_extraction: bool = False,
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
        allocated = token_allocated_at or _time(WARMUP + timedelta(seconds=1))
        if plan_schedule_truncated_micros:
            # F-ADH-070: the production plan writer truncates fractional-second
            # offsets to whole microseconds, while timedelta arithmetic (used by
            # the validator and by this fixture's default path) rounds them.
            scheduled_at = _time(
                MEASUREMENT + timedelta(microseconds=math.floor(offset * 1e6)))
        else:
            scheduled_at = _time(MEASUREMENT + timedelta(seconds=offset))
        if plan_schedule_skew_micros and index in plan_schedule_skew_micros:
            scheduled_at = _time(
                MEASUREMENT + timedelta(seconds=offset)
                + timedelta(microseconds=plan_schedule_skew_micros[index]))
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
    _write_json(root / "system-samples.json", _system_samples(regime))
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
            "warmupEndedAt": _time(WARMUP_END),
            "warmupSettledAt": _time(WARMUP_SETTLED),
            "warmupDurationSeconds": 120,
            "measurementStartedAt": _time(MEASUREMENT),
            "measurementEndedAt": _time(END),
            "measurementStartMonotonic": 500.0,
            "measurementEndMonotonic": 1100.0,
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
        # F-ADH-074: derived by the producer and re-derived by the validator, so
        # the fixture computes it the same way rather than hardcoding a shape.
        "exposureTolerance": candidate_pilot._queue_checker().exposure_tolerance(
            traces, intervention,
            fault=candidate_pilot.SCENARIOS.get(regime, "none"),
        ),
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
            "unscoredExcludedObservations": 0,
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
    _write_operational_proofs(root, posture)
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
    # The extractor's own ledger validation fail-closes schedule/allocation
    # defects before the pilot ever sees them; the F-ADH-070 negative tests
    # skip it to prove the pilot's plan gate blocks independently.
    if not skip_native_token_extraction:
        native_token.extract(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            posture_proof=root / "posture-proof.json",
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


@pytest.mark.parametrize("plant", ("closure", "purge-consumer", "barrier-collector", "terminal-drain"))
def test_operational_proof_replay_watches_semantic_defects(
    tmp_path: Path, plant: str,
) -> None:
    root = make_run(tmp_path / "run")
    if plant == "closure":
        _mutate_json(root, "posture-proof.json", lambda value: value["closureGroups"].pop())
    elif plant == "purge-consumer":
        _mutate_json(
            root, "queue-proof.json",
            lambda value: value["purge"]["before"].update({"consumers": 1}),
        )
    elif plant == "barrier-collector":
        _mutate_json(
            root, "queue-proof.json",
            lambda value: value["measurement"]["consumerAtStart"].update({"consumers": 2}),
        )
    else:
        _mutate_json(
            root, "queue-proof.json",
            lambda value: value["measurement"]["after"].update({"messages": 1}),
        )
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "posture-and-queue-semantic-replay")


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
    # F-ADH-066: the selected closure omits the trace-root sensor, so the
    # endpoint is keyed on the closure (not on the retained trace shape) and
    # releases trace-level coverage instead of per-request reconstruction.
    assert report["reconstruction"] == {
        "status": "request-root-structurally-absent",
        "eligibleExecutedPaths": 90,
        "reconstructedPaths": 0,
        "fraction": 0.0,
        "traceLevelCoverage": {
            "mappedTraces": 90,
            "tracesWithDirectAuthPersistenceEdge": 90,
            "eligibleJourneysOnTracesWithDirectEdge": 90,
            "journeyFraction": 1.0,
        },
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


def test_shared_window_retains_setup_gap_and_watches_overlap(tmp_path: Path):
    root = make_run(tmp_path / "run")
    report = candidate_pilot.validate_run(root)
    row = next(item for item in report["validationTable"] if item["gate"] == "shared-window")
    assert row["status"] == "pass"
    assert row["observation"]["wallWarmupSeconds"] == 120.0
    assert row["observation"]["setupGapSeconds"] == 20.0

    _mutate_json(
        root,
        "receipt.json",
        lambda value: value["window"].update(
            warmupEndedAt=_time(MEASUREMENT + timedelta(seconds=1)),
        ),
        rehash=False,
    )
    planted = candidate_pilot.validate_run(root)
    assert planted["verdict"] == "blocked"
    assert _failed(planted, "shared-window")


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
    # The exposure window is derived from the intervention, so swapping in a
    # real one must move the tolerance with it (F-ADH-074).
    receipt["exposureTolerance"] = candidate_pilot._queue_checker().exposure_tolerance(
        _load(root / "traces.json"), intervention, fault="auth-freeze",
    )
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


def _rebuild_as_thread_traces(root: Path, *, threads: int = 3, reextract: bool = True):
    """Rebuild native evidence in the real unwoven-entry capture shape (F-ADH-066).

    Without the trace-root sensor each worker thread carries one native trace:
    every auth execution enters at ess=1 because its depth-0 webui parent is
    never woven, its persistence call nests at ess=2, and one trace spans many
    journeys and tokens. All counters, spool bytes, and collector stats are
    reproduced through the real collector so every consistency gate still holds.
    """
    spool_path = root / "kieker-amqp.spool"
    spool_path.unlink()
    spool = kieker_native.KiekerBodySpool(spool_path)
    bodies = []
    next_eoi: dict[int, int] = {}
    for index in range(90):
        started = MEASUREMENT + timedelta(seconds=index * (600 / 90))
        tin = int(started.timestamp() * 1_000_000_000)
        thread = index % threads
        trace_id = 20_000 + thread
        eoi = next_eoi.get(thread, 0)
        next_eoi[thread] = eoi + 2
        raw = kieker_native.build_fixture([
            {
                "class_name": kieker_native.OER_CLASS,
                "operationSignature": (
                    "public boolean tools.descartes.teastore.auth.Auth.login()"
                ),
                "sessionId": "candidate-fixture", "traceId": trace_id,
                "tin": tin + 100_000_000, "tout": tin + 150_000_000,
                "hostname": "auth", "eoi": eoi, "ess": 1,
            },
            {
                "class_name": kieker_native.OER_CLASS,
                "operationSignature": (
                    "public void tools.descartes.teastore.persistence.Persistence.find()"
                ),
                "sessionId": "candidate-fixture", "traceId": trace_id,
                "tin": tin + 200_000_000, "tout": tin + 250_000_000,
                "hostname": "persistence", "eoi": eoi + 1, "ess": 2,
            },
        ])
        spool.append_delivery(raw, _spool_identity(index))
        bodies.append(raw)
    spool.seal()
    runtime_aliases = kieker_native.load_runtime_host_service_map(
        root / "runtime-images.json")
    configuration, configuration_sha256 = (
        kieker_native.frozen_attribution_configuration(runtime_aliases))
    replayed, summary, counts = kieker_native.replay_spooled_events(
        spool_path,
        re.compile(kieker_native.DEFAULT_SERVICE_REGEX),
        kieker_native.DEFAULT_SERVICE_MAP,
        configuration["effectiveHostAliases"],
    )
    collector = kieker_native.KiekerNativeCollector(
        runtime_images_path=root / "runtime-images.json")
    for raw in bodies:
        collector.n_messages += 1
        collector.handle_body(raw)
    collector._spool_report = summary
    stats = collector.stats()
    traces = collector.correlated_events()
    assert traces == replayed
    assert {field: stats[field] for field in counts} == counts
    _write_json(root / "traces.json", traces)
    capture = _load(root / "capture-terminal.json")
    capture.update(
        rawRecords=len(traces),
        measurementRecords=len(traces),
        uniqueNativeTraces=len({str(row["kieker_trace_id"]) for row in traces}),
        uniqueSignatures=len({row["signature_sha1"] for row in traces}),
        uniqueMessageBodies=len({row["message_sha1"] for row in traces}),
    )
    _write_json(root / "capture-terminal.json", capture)
    receipt = _load(root / "receipt.json")
    receipt["source"]["spoolSha256"] = hashlib.sha256(
        spool_path.read_bytes()).hexdigest()
    receipt["source"]["collectorAttributionConfigurationSha256"] = configuration_sha256
    receipt["telemetry"] = {"collectorStats": stats, "spool": summary}
    _write_json(root / "receipt.json", receipt)
    tokens = [
        row["opaqueToken"] for row in _load_jsonl(root / "journey-ledger.jsonl")
        if row.get("recordType") == "journey-terminal"
    ]
    auth_log = root / "auth.log"
    app_lines = [
        line for line in auth_log.read_text(encoding="utf-8").splitlines(keepends=True)
        if not line.startswith(native_token.MARKER)
    ]
    bridge_lines = [
        native_token.MARKER + json.dumps({
            "token": token,
            "nativeTraceId": str(20_000 + index % threads),
            "service": "auth",
        }, separators=(",", ":")) + "\n"
        for index, token in enumerate(tokens)
    ]
    auth_log.write_text("".join(app_lines + bridge_lines), encoding="utf-8")
    auth_sha = hashlib.sha256(auth_log.read_bytes()).hexdigest()
    capture_receipt = _load(root / "service-log-capture.json")
    capture_receipt["capturedLog"]["sha256"] = auth_sha
    _write_json(root / "service-log-capture.json", capture_receipt)
    extraction = _load(root / "app-witness-extraction.json")
    extraction["inputs"]["authLogSha256"] = auth_sha
    _write_json(root / "app-witness-extraction.json", extraction)
    if reextract:
        _reextract_native_token(root)
    _rehash(root)


def test_selected_thread_traces_release_trace_level_coverage(tmp_path: Path):
    root = make_run(tmp_path / "run")
    _rebuild_as_thread_traces(root)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "pass", json.dumps(report["validationTable"], indent=2)
    integrity = next(
        row for row in report["validationTable"]
        if row["gate"] == "native-event-correlation-and-attribution-integrity")
    assert integrity["status"] == "pass"
    assert integrity["observation"]["entryPointWoven"] is False
    assert integrity["observation"]["unwovenRootEvents"] == 90
    detail = report["views"]["path"]["details"][0]
    assert detail["reconstructed"] is False
    assert detail["requestRootReconstruction"] == "structurally-absent"
    assert detail["traceLevelDirectEdge"] is True
    assert report["reconstruction"] == {
        "status": "request-root-structurally-absent",
        "eligibleExecutedPaths": 90,
        "reconstructedPaths": 0,
        "fraction": 0.0,
        "traceLevelCoverage": {
            "mappedTraces": 3,
            "tracesWithDirectAuthPersistenceEdge": 3,
            "eligibleJourneysOnTracesWithDirectEdge": 90,
            "journeyFraction": 1.0,
        },
    }


def test_thread_traces_under_full_closure_still_block_both_gates(tmp_path: Path):
    root = make_run(tmp_path / "run", posture="full")
    # The extractor itself refuses this shape under a woven-entry closure, so
    # the retained correlation artifacts stay stale and must fail replay.
    _rebuild_as_thread_traces(root, reextract=False)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert _failed(report, "native-event-correlation-and-attribution-integrity")
    assert _failed(report, "opaque-token-native-trace-correlation")
    integrity = next(
        row for row in report["validationTable"]
        if row["gate"] == "native-event-correlation-and-attribution-integrity")
    assert integrity["observation"]["entryPointWoven"] is True
    assert integrity["observation"]["unwovenRootEvents"] == 0


PROBE_CALLER_TRACE = 30_000
PROBE_ORPHAN_TRACE = 30_001


def _rebuild_with_probe_orphan(root: Path):
    """Rebuild full-posture native evidence carrying one real F-ADH-083 shape.

    Measured on the retained campaign #9 cell-12 evidence: the WebUI `/status`
    page IS fully traced (`StatusServlet.handleGETRequest` at eoi 0 / ess 0 with
    `StatusServlet.isImageFinished` resolved beneath it), but the cross-service
    readiness call it makes goes through `ServiceLoadBalancer.multicastRESTOperation`
    -> `servers.parallelStream()`, so Kieker's thread-local context is lost on the
    fork-join worker and `ImageProviderEndpoint.isFinished` lands in a brand new
    trace at eoi 1 / ess 1 with no depth-0 record that could ever have existed.
    Its `[tin, tout]` sits inside the retained caller's window, which is conjunct
    (5) and is what separates "never minted a root" from "lost the root".

    Everything is produced through the real spool, replay and collector so the
    hash-bound capture counts and the collector's own correlation summary stay
    self-consistent and no other gate is perturbed.
    """
    spool_path = root / "kieker-amqp.spool"
    spool_path.unlink()
    spool = kieker_native.KiekerBodySpool(spool_path)
    bodies = []
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
        spool.append_delivery(raw, _spool_identity(index))
        bodies.append(raw)
    probe_tin = int((MEASUREMENT + timedelta(seconds=300)).timestamp() * 1_000_000_000)
    probe = kieker_native.build_fixture([
        {
            "class_name": kieker_native.OER_CLASS,
            "operationSignature": (
                "public void tools.descartes.teastore.webui.servlet"
                ".StatusServlet.handleGETRequest()"
            ),
            "sessionId": "<no-session-id>", "traceId": PROBE_CALLER_TRACE,
            "tin": probe_tin, "tout": probe_tin + 40_000_000,
            "hostname": "webui", "eoi": 0, "ess": 0,
        },
        {
            "class_name": kieker_native.OER_CLASS,
            "operationSignature": (
                "public boolean tools.descartes.teastore.webui.servlet"
                ".StatusServlet.isImageFinished()"
            ),
            "sessionId": "<no-session-id>", "traceId": PROBE_CALLER_TRACE,
            "tin": probe_tin + 10_000_000, "tout": probe_tin + 30_000_000,
            "hostname": "webui", "eoi": 1, "ess": 1,
        },
        {
            "class_name": kieker_native.OER_CLASS,
            "operationSignature": (
                "public boolean tools.descartes.teastore.image.rest"
                ".ImageProviderEndpoint.isFinished()"
            ),
            "sessionId": "<no-session-id>", "traceId": PROBE_ORPHAN_TRACE,
            "tin": probe_tin + 20_000_000, "tout": probe_tin + 25_000_000,
            "hostname": "image", "eoi": 1, "ess": 1,
        },
    ])
    spool.append_delivery(probe, _spool_identity(90))
    bodies.append(probe)
    spool.seal()
    runtime_aliases = kieker_native.load_runtime_host_service_map(
        root / "runtime-images.json")
    configuration, configuration_sha256 = (
        kieker_native.frozen_attribution_configuration(runtime_aliases))
    replayed, summary, counts = kieker_native.replay_spooled_events(
        spool_path,
        re.compile(kieker_native.DEFAULT_SERVICE_REGEX),
        kieker_native.DEFAULT_SERVICE_MAP,
        configuration["effectiveHostAliases"],
    )
    collector = kieker_native.KiekerNativeCollector(
        runtime_images_path=root / "runtime-images.json")
    for raw in bodies:
        collector.n_messages += 1
        collector.handle_body(raw)
    collector._spool_report = summary
    stats = collector.stats()
    traces = collector.correlated_events()
    assert traces == replayed
    assert {field: stats[field] for field in counts} == counts
    _write_json(root / "traces.json", traces)
    capture = _load(root / "capture-terminal.json")
    capture.update(
        rawRecords=len(traces),
        measurementRecords=len(traces),
        uniqueNativeTraces=len({str(row["kieker_trace_id"]) for row in traces}),
        uniqueSignatures=len({row["signature_sha1"] for row in traces}),
        uniqueMessageBodies=len({row["message_sha1"] for row in traces}),
    )
    _write_json(root / "capture-terminal.json", capture)
    receipt = _load(root / "receipt.json")
    receipt["source"]["spoolSha256"] = hashlib.sha256(
        spool_path.read_bytes()).hexdigest()
    receipt["source"]["collectorAttributionConfigurationSha256"] = configuration_sha256
    receipt["telemetry"] = {"collectorStats": stats, "spool": summary}
    receipt["exposureTolerance"] = candidate_pilot._queue_checker().exposure_tolerance(
        traces, None, fault="none")
    _write_json(root / "receipt.json", receipt)
    _reextract_native_token(root)
    _rehash(root)
    return traces, stats


def test_probe_orphan_root_is_excused_and_counted_under_a_woven_entry_point(
    tmp_path: Path,
):
    """F-ADH-083: the candidate-path copy of the carve-out, on the real shape.

    The producer gates were replayed against the retained cell-12 evidence, but
    `candidate_pilot`'s own copy (it adds conjunct (6), "no ledger token maps to
    the trace") had no fixture, which the adversarial review of `55d936b` listed
    as finding 5. This is that fixture.
    """
    root = make_run(tmp_path / "run", posture="full")
    traces, stats = _rebuild_with_probe_orphan(root)

    # The planted shape is exactly one orphan root, and it is the only unwoven
    # root in the cell, so the carve-out is what admits it and nothing else.
    orphans = [
        row for row in traces
        if row["operation"] == "ImageProviderEndpoint.isFinished"
    ]
    assert len(orphans) == 1
    assert orphans[0]["service"] == "image"
    assert orphans[0]["eoi"] == 1 and orphans[0]["ess"] == 1
    assert orphans[0]["parent_resolution"] == "missing"
    assert orphans[0]["correlation_errors"] == [
        kieker_native.UNWOVEN_ROOT_PARENT_ERROR]
    assert kieker_native.count_unwoven_root_parents(traces) == 1
    assert kieker_native.count_probe_orphan_roots(traces) == 1
    correlation = stats["correlation"]
    assert correlation["eventsWithCorrelationErrors"] == 1
    assert correlation["eventsWithUnwovenRootParent"] == 1
    assert correlation["eventsWithProbeOrphanRoot"] == 1
    assert correlation["eventsWithCorrelationWarnings"] == 0
    assert correlation["parentResolution"]["missing"] == 1

    report = candidate_pilot.validate_run(root)

    integrity = next(
        row for row in report["validationTable"]
        if row["gate"] == "native-event-correlation-and-attribution-integrity")
    assert integrity["observation"]["entryPointWoven"] is True
    assert integrity["observation"]["probeOrphanRootEvents"] == 1
    assert integrity["observation"]["unwovenRootEvents"] == 0
    assert [row["row"] for row in integrity["observation"]["errors"]] == []
    assert integrity["status"] == "pass"
    assert report["verdict"] == "pass", json.dumps(
        report["validationTable"], indent=2)


def test_probe_orphan_outside_its_status_caller_window_still_blocks(
    tmp_path: Path,
):
    """Conjunct (5) is load-bearing: the same row is loss without an enclosing caller.

    Only the caller's `[tin, tout]` moves, so every count, signature and message
    digest stays identical and the integrity gate is the one that has to notice.
    """
    root = make_run(tmp_path / "run", posture="full")
    _rebuild_with_probe_orphan(root)

    def move_caller_window(rows):
        caller = next(
            row for row in rows
            if row["operation"] == "StatusServlet.isImageFinished")
        orphan = next(
            row for row in rows
            if row["operation"] == "ImageProviderEndpoint.isFinished")
        assert caller["tin"] <= orphan["tin"] <= caller["tout"]
        span = caller["tout"] - caller["tin"]
        caller["tin"] = orphan["tin"] + 1
        caller["tout"] = caller["tin"] + span
    _mutate_json(root, "traces.json", move_caller_window)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert _failed(report, "native-event-correlation-and-attribution-integrity")
    integrity = next(
        row for row in report["validationTable"]
        if row["gate"] == "native-event-correlation-and-attribution-integrity")
    assert integrity["observation"]["probeOrphanRootEvents"] == 0
    assert [row["row"] for row in integrity["observation"]["errors"]] == [
        len(_load(root / "traces.json"))]


@pytest.mark.parametrize(
    ("planted_errors", "planted_resolution"),
    [
        (["missing-parent-at-depth-1"], "missing"),
        (["missing-parent-at-depth-0", "invalid-native-eoi"], "ambiguous"),
    ],
)
def test_deeper_or_mixed_correlation_errors_block_even_when_entry_is_unwoven(
    tmp_path: Path, planted_errors, planted_resolution,
):
    root = make_run(tmp_path / "run")
    _rebuild_as_thread_traces(root)

    def plant(rows):
        target = next(row for row in rows if row["parent_resolution"] == "resolved")
        target.update(
            parent_resolution=planted_resolution,
            correlation_errors=planted_errors,
        )
    _mutate_json(root, "traces.json", plant)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert _failed(report, "native-event-correlation-and-attribution-integrity")


def test_latency_replay_is_bit_identical_to_the_workload_driver_declaration():
    """F-ADH-069: the outcome-and-latency gate compares the driver's declared
    statistics to this validator's replay with exact equality, so the two
    implementations must agree bit-for-bit — algebraically equal interpolation
    forms can differ in the last ulp and abort a cell on valid evidence."""
    import random
    import statistics as statistics_module

    driver_spec = importlib.util.spec_from_file_location(
        "fixed_load_for_latency_parity",
        Path(__file__).parents[1] / "modules/teastore/workload/fixed_load.py",
    )
    fixed_load = importlib.util.module_from_spec(driver_spec)
    assert driver_spec.loader is not None
    driver_spec.loader.exec_module(fixed_load)

    rng = random.Random(0xF069)
    divergence_from_old_formula = 0
    for size in (1, 2, 3, 89, 90, 91, 1350):
        values = [rng.uniform(1.0, 2000.0) for _ in range(size)]
        for quantile in (0.50, 0.95, 0.99):
            declared = fixed_load.percentile(values, quantile)
            replayed = candidate_pilot._percentile(values, quantile)
            assert replayed == declared, (size, quantile)
            ordered = sorted(values)
            position = (len(ordered) - 1) * quantile
            lower, upper = int(position // 1), -(-position // 1)
            if lower != upper:
                old_formula = ordered[int(lower)] + (
                    ordered[int(upper)] - ordered[int(lower)]
                ) * (position - lower)
                divergence_from_old_formula += old_formula != declared
        assert statistics_module.fmean(values) == statistics_module.fmean(values)
    # The regression is only guarded if the retired formula actually diverges
    # somewhere in this corpus; otherwise the parity assertions prove nothing.
    assert divergence_from_old_formula > 0


def test_plan_gate_accepts_producer_truncated_schedule_microseconds(tmp_path: Path):
    """F-ADH-070: the campaign aborted because the plan producer truncates
    fractional-second schedule offsets to microseconds while the validator's
    timedelta arithmetic rounds them (real pair: barrier ...54.413220Z,
    opportunity 1 scheduledAt ...01.079886Z vs expected .079887Z). The plan
    gate must accept the producer's rounding envelope."""
    root = make_run(tmp_path / "run", plan_schedule_truncated_micros=True)
    plan = _load(root / "journey-ledger.plan.json")
    divergent = sum(
        1 for index, row in enumerate(plan["opportunities"])
        if row["scheduledAt"]
        != _time(MEASUREMENT + timedelta(seconds=index * (600 / 90)))
    )
    # The truncation path must actually differ from datetime arithmetic for
    # some opportunities, or these assertions prove nothing.
    assert divergent > 0
    report = candidate_pilot.validate_run(root)
    row = next(
        row for row in report["validationTable"]
        if row["gate"] == "pre-outcome-plan-and-ledger-chain"
    )
    assert row["status"] == "pass", row["observation"]
    assert report["verdict"] == "pass"


def test_plan_gate_still_blocks_schedule_beyond_one_microsecond(tmp_path: Path):
    """The F-ADH-070 tolerance is the driver's one-microsecond envelope, not a
    hole: a three-microsecond schedule deviation must still block. Extraction
    is skipped because the extractor's own ledger validation fail-closes this
    defect first; the pilot must also block it independently."""
    root = make_run(
        tmp_path / "run",
        plan_schedule_skew_micros={1: -3},
        skip_native_token_extraction=True,
    )
    report = candidate_pilot.validate_run(root)
    row = next(
        row for row in report["validationTable"]
        if row["gate"] == "pre-outcome-plan-and-ledger-chain"
    )
    assert row["status"] != "pass"
    assert "opportunity 1 schedule or allocation differs" in json.dumps(row["observation"])
    assert report["verdict"] == "blocked"


@pytest.mark.parametrize(
    "slack_micros,expected_pass",
    [(-500, True), (-2000, False)],
    ids=["half-millisecond-clock-slack", "two-milliseconds-too-early"],
)
def test_token_allocation_clock_slack_mirrors_the_driver(
    tmp_path: Path, slack_micros: int, expected_pass: bool,
):
    """F-ADH-070: token allocation may precede controller start by the workload
    driver's one-millisecond clock slack, and no more. The too-early case skips
    extraction because the extractor's ledger validation fail-closes it first
    (plan.opportunities[0].tokenAllocatedAt precedes controller start); the
    pilot must also block it independently."""
    root = make_run(
        tmp_path / "run",
        token_allocated_at=_time(WARMUP + timedelta(microseconds=slack_micros)),
        skip_native_token_extraction=not expected_pass,
    )
    report = candidate_pilot.validate_run(root)
    row = next(
        row for row in report["validationTable"]
        if row["gate"] == "pre-outcome-plan-and-ledger-chain"
    )
    assert (row["status"] == "pass") is expected_pass, row["observation"]
    assert (report["verdict"] == "pass") is expected_pass


@pytest.mark.parametrize(
    "skew_micros,expected_pass",
    [(1, True), (-1, True), (3, False)],
    ids=["one-micro-late", "one-micro-early", "three-micros"],
)
def test_effect_barrier_onset_wall_tolerates_epoch_float_rounding(
    tmp_path: Path, skew_micros: int, expected_pass: bool,
):
    """F-ADH-070: the producer derives scheduledOnsetWall from epoch-float
    arithmetic (performance_campaign.py) while the validator replays it with
    datetime+timedelta; a one-microsecond rounding difference must pass and a
    three-microsecond deviation must still block."""
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    onset = _time(
        MEASUREMENT + timedelta(seconds=180) + timedelta(microseconds=skew_micros))
    intervention = _load(root / "intervention.json")
    intervention["measurementBarrier"]["scheduledOnsetWall"] = onset
    _write_json(root / "intervention.json", intervention)
    receipt = _load(root / "receipt.json")
    receipt["intervention"]["measurementBarrier"]["scheduledOnsetWall"] = onset
    # F-ADH-085: the exposure window now starts at the scheduled onset, so the
    # producer's tolerance moves with it exactly as it would in a real cell.
    receipt["exposureTolerance"] = candidate_pilot._queue_checker().exposure_tolerance(
        _load(root / "traces.json"), intervention, fault="auth-freeze",
    )
    _write_json(root / "receipt.json", receipt)
    _rehash(root)
    report = candidate_pilot.validate_run(root)
    row = next(
        row for row in report["validationTable"]
        if row["gate"] == "independent-fault-ground-truth"
    )
    assert (row["status"] == "pass") is expected_pass, row["observation"]
    assert (report["verdict"] == "pass") is expected_pass


def test_full_posture_proof_binds_rendered_full_aop(tmp_path: Path) -> None:
    """F-ADH-072: `full` must prove the woven bytes, exactly like `selected`.

    Campaign #6 recorded only kieker.monitoring.enabled for full/none, so a
    full posture realised from the stock in-image aop.xml -- a different
    join-point set than the rendered selected -- passed every gate.
    """
    root = make_run(tmp_path / "run", posture="full")
    assert candidate_pilot.validate_run(root)["verdict"] == "pass"

    _mutate_json(
        root, "posture-proof.json",
        lambda value: value["services"]["auth"].update({"aopSha256": "b" * 64}),
    )
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "posture-and-queue-semantic-replay")


def test_none_posture_proof_binds_empty_rendering(tmp_path: Path) -> None:
    """`none` is the empty selection rendered by the same compiler, not the
    stock file with monitoring switched off."""
    root = make_run(tmp_path / "run", posture="none")
    assert candidate_pilot.validate_run(root)["verdict"] == "pass"

    _mutate_json(
        root, "posture-proof.json",
        lambda value: value.update({"selectionId": "fault-qualification"}),
    )
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "posture-and-queue-semantic-replay")


# --- F-ADH-081 / F-ADH-082: fault-path gates must not reject the fault's own evidence ---


def _rechain_ledger(root: Path, rows, *, reextract: bool = True) -> None:
    """Rewrite the ledger in the given row order with the hash chain the driver would have produced."""
    previous = "0" * 64
    for sequence, row in enumerate(rows):
        row["recordSequence"] = sequence
        row["previousRecordSha256"] = previous
        row.pop("recordSha256", None)
        row["recordSha256"] = _canonical_sha256(row)
        previous = row["recordSha256"]
    _write_jsonl(root / "journey-ledger.jsonl", rows)
    extraction = _load(root / "app-witness-extraction.json")
    extraction["inputs"]["journeyLedgerSha256"] = hashlib.sha256(
        (root / "journey-ledger.jsonl").read_bytes()).hexdigest()
    extraction["journeyLedgerValidation"]["lastRecordSha256"] = rows[-1]["recordSha256"]
    _write_json(root / "app-witness-extraction.json", extraction)
    # The real correlator ran on the campaign #8 cell's swapped ledger without
    # complaint; re-running it here keeps its receipt bound to the new bytes.
    # (A drifted ledger is refused by the correlator's own ledger validation
    # before the validator ever sees it, so drift tests skip the re-run.)
    if reextract:
        _reextract_native_token(root)
    _rehash(root)


def test_ledger_rows_written_in_completion_order_still_bind_by_opportunity_id(tmp_path: Path):
    # F-ADH-081: two journeys timing out together under a fault finish 11 ms
    # apart and land in the ledger swapped relative to the schedule.
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    rows = _load_jsonl(root / "journey-ledger.jsonl")
    rows[27], rows[28] = rows[28], rows[27]
    _rechain_ledger(root, rows)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "pass", json.dumps(report["validationTable"], indent=2)


def test_ledger_row_drifting_from_its_opportunity_still_blocks_after_reorder(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    rows = _load_jsonl(root / "journey-ledger.jsonl")
    rows[27], rows[28] = rows[28], rows[27]
    rows[27]["scheduledMonotonicOffsetSeconds"] += 1.0
    _rechain_ledger(root, rows, reextract=False)
    report = candidate_pilot.validate_run(root)
    assert _failed(report, "pre-outcome-plan-and-ledger-chain")


def _plant_thaw_replay(root: Path, *, journey_index: int) -> None:
    """A thawed upstream retried one request with the same Kieker header: two executions, one identity."""
    traces = _load(root / "traces.json")
    started = (MEASUREMENT + timedelta(seconds=journey_index * (600 / 90))).timestamp()
    original = next(
        event for event in traces
        if event.get("eoi") == 1 and abs(float(event["timestamp"]) - started) < 1.0
    )
    replay = dict(original)
    replay["tin"] = original["tin"] + 1_000_000
    replay["tout"] = original["tout"] + 1_000_000
    for event in (original, replay):
        event["correlation_errors"] = ["conflicting-native-identity"]
        event["parent_resolution"] = "ambiguous"
        event["native_identity_occurrences"] = 2
        event["native_identity_message_bodies"] = 2
    traces.append(replay)
    _write_json(root / "traces.json", traces)
    receipt = _load(root / "receipt.json")
    receipt["exposureTolerance"] = candidate_pilot._queue_checker().exposure_tolerance(
        traces, receipt.get("intervention"),
        fault=candidate_pilot.SCENARIOS.get(receipt["run"]["regime"], "none"),
    )
    _write_json(root / "receipt.json", receipt)
    _rehash(root)


def test_thaw_replay_identities_inside_the_exposure_window_are_counted_not_blocked(tmp_path: Path):
    # F-ADH-082: the repeated identity IS the tolerated error inside the window.
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")
    _plant_thaw_replay(root, journey_index=33)  # 220 s into measurement: inside [180 s, 330 s]
    report = candidate_pilot.validate_run(root)
    rows = {row["gate"]: row for row in report["validationTable"]}
    assert rows["replay-and-duplicate-control"]["status"] == "pass", rows["replay-and-duplicate-control"]
    assert rows["replay-and-duplicate-control"]["observation"]["exposureReplayDuplicateKeys"] == 1
    native = rows["native-event-correlation-and-attribution-integrity"]
    assert native["status"] == "pass", native["observation"]["errors"]
    assert native["observation"]["toleratedExposureEvents"] == 2
    assert rows["exposure-tolerance-binding"]["status"] == "pass", rows["exposure-tolerance-binding"]


@pytest.mark.parametrize(
    "regime, journey_index, reason",
    [
        ("auth-freeze-effect", 5, "before the window opens"),
        ("no-fault-cost", 33, "a cost cell never carries a window"),
    ],
)
def test_repeated_identities_outside_a_proven_exposure_window_still_block(
    tmp_path: Path, regime, journey_index, reason,
):
    root = make_run(tmp_path / "run", regime=regime)
    _plant_thaw_replay(root, journey_index=journey_index)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "blocked"
    assert _failed(report, "replay-and-duplicate-control"), reason
    assert _failed(report, "native-event-correlation-and-attribution-integrity"), reason


def _kieker_metadata_banner(*, hostname: str, logging_timestamp: int) -> bytes:
    """One AMQP body shaped like a Kieker controller restart banner.

    F-ADH-084: the shape retained in campaign #10 cell 19 -- a single
    KiekerMetadataRecord whose class the execution-record parser refuses, so the
    container is rejected whole while records_bad stays 0.
    """
    registry = ["kieker.common.record.misc.KiekerMetadataRecord", "1.15-SNAPSHOT",
                "KIEKER", hostname, "NANOSECONDS"]
    records = bytearray(struct.pack(">i", 0) + struct.pack(">q", logging_timestamp))
    records.extend(struct.pack(">iiii", 1, 2, 3, 1))
    records.extend(b"\x00" + struct.pack(">q", 0) + struct.pack(">i", 4)
                   + struct.pack(">q", 0))
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


def _plant_restart_banner(root: Path, *, hostname: str, seconds_after_onset: float) -> None:
    """Append one restart banner to the spool and re-derive the whole receipt."""
    intervention = _load(root / "intervention.json")
    onset = datetime.fromisoformat(intervention["actualOnsetWall"]).timestamp()
    banner = _kieker_metadata_banner(
        hostname=hostname,
        logging_timestamp=int((onset + seconds_after_onset) * 1e9),
    )
    spool_path = root / "kieker-amqp.spool"
    bodies, _ = kieker_native.replay_kieker_spool(spool_path)
    spool_path.unlink()
    spool = kieker_native.KiekerBodySpool(spool_path)
    for index, raw in enumerate([*bodies, banner]):
        spool.append_delivery(raw, _spool_identity(index))
    spool.seal()

    runtime_aliases = kieker_native.load_runtime_host_service_map(
        root / "runtime-images.json")
    configuration, configuration_sha256 = (
        kieker_native.frozen_attribution_configuration(runtime_aliases))
    replayed, summary, counts = kieker_native.replay_spooled_events(
        spool_path, re.compile(kieker_native.DEFAULT_SERVICE_REGEX),
        kieker_native.DEFAULT_SERVICE_MAP, configuration["effectiveHostAliases"])
    assert counts["containers_bad"] == 1 and counts["records_bad"] == 0
    assert replayed == _load(root / "traces.json")

    receipt = _load(root / "receipt.json")
    stats = receipt["telemetry"]["collectorStats"]
    stats.update(counts)
    records = counts["records_ok"] + counts["records_bad"]
    containers = counts["containers_ok"] + counts["containers_bad"]
    stats["record_parse_success_ratio"] = counts["records_ok"] / records if records else 0.0
    stats["container_parse_success_ratio"] = (
        counts["containers_ok"] / containers if containers else 0.0)
    stats["spool"] = summary
    stats["attribution_configuration"] = configuration
    stats["attribution_configuration_sha256"] = configuration_sha256
    receipt["telemetry"]["spool"] = summary
    receipt["source"]["spoolSha256"] = hashlib.sha256(spool_path.read_bytes()).hexdigest()
    receipt["source"]["collectorAttributionConfigurationSha256"] = configuration_sha256
    receipt["exposureTolerance"] = candidate_pilot._queue_checker().exposure_tolerance(
        replayed, intervention, fault="persistence-crash",
        container_failures=kieker_native.spool_container_parse_diagnostics(spool_path),
    )
    _write_json(root / "receipt.json", receipt)
    _rehash(root)


def test_crash_arm_restart_banner_is_accepted_only_for_the_killed_container(tmp_path: Path):
    """F-ADH-084 end to end: campaign #10 cell 19 aborted on this exact shape."""
    root = make_run(tmp_path / "tolerated", regime="persistence-crash-effect",
                    posture="full")
    _plant_restart_banner(root, hostname="c" * 12, seconds_after_onset=1.0)
    report = candidate_pilot.validate_run(root)
    assert report["verdict"] == "pass", report["blockers"]
    row = next(row for row in report["validationTable"]
               if row["gate"] == "exposure-tolerance-binding")
    recomputed = row["observation"]["recomputed"]
    assert recomputed["toleratedContainerParseFailures"] == 1
    assert recomputed["residualContainerParseFailures"] == 0
    banner = recomputed["containerParseFailures"][0]
    assert banner["recordClasses"] == ["kieker.common.record.misc.KiekerMetadataRecord"]
    assert banner["parsedExecutionRecords"] == 0

    other = make_run(tmp_path / "other-container", regime="persistence-crash-effect",
                     posture="full")
    _plant_restart_banner(other, hostname="a" * 12, seconds_after_onset=1.0)
    assert candidate_pilot.validate_run(other)["verdict"] == "blocked"

    late = make_run(tmp_path / "outside-window", regime="persistence-crash-effect",
                    posture="full")
    _plant_restart_banner(late, hostname="c" * 12, seconds_after_onset=100_000.0)
    assert candidate_pilot.validate_run(late)["verdict"] == "blocked"

    cost = make_run(tmp_path / "cost", regime="no-fault-cost", posture="full")
    spool_path = cost / "kieker-amqp.spool"
    bodies, _ = kieker_native.replay_kieker_spool(spool_path)
    spool_path.unlink()
    spool = kieker_native.KiekerBodySpool(spool_path)
    for index, raw in enumerate([*bodies, _kieker_metadata_banner(
            hostname="c" * 12, logging_timestamp=int(MEASUREMENT.timestamp() * 1e9))]):
        spool.append_delivery(raw, _spool_identity(index))
    spool.seal()
    _rehash(cost)
    assert candidate_pilot.validate_run(cost)["verdict"] == "blocked"


# sys lineage: system-samples.json is required in every cell.
def test_cell_blocks_when_system_samples_are_missing(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="no-fault-cost")
    assert candidate_pilot.validate_run(root)["verdict"] == "pass"
    (root / "system-samples.json").unlink()
    _rehash(root)

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert report["cellStatus"] == "missing-artifact"
    assert _failed(report, "artifact-presence")
    assert _failed(report, "system-samples")


def test_no_fault_cell_blocks_a_null_required_service_even_when_rehashed(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="no-fault-cost")
    _mutate_json(
        root, "system-samples.json",
        lambda value: value["samples"][60]["services"].update({"auth": None}),
    )

    report = candidate_pilot.validate_run(root)

    assert report["verdict"] == "blocked"
    assert report["cellStatus"] == "invalid"
    assert _failed(report, "system-samples")
    assert not _failed(report, "artifact-hash-binding")


def test_crash_cell_allows_null_rows_but_not_at_the_first_sample(tmp_path: Path):
    root = make_run(tmp_path / "run", regime="persistence-crash-effect")
    report = candidate_pilot.validate_run(root)
    row = next(r for r in report["validationTable"] if r["gate"] == "system-samples")
    assert row["status"] == "pass"
    assert row["observation"]["nullSamplesByService"]["persistence"] == 30
    _mutate_json(
        root, "system-samples.json",
        lambda value: value["samples"][0]["services"].update({"persistence": None}),
    )
    assert _failed(candidate_pilot.validate_run(root), "system-samples")


@pytest.mark.parametrize("plant", ("kind", "count", "grid", "start"))
def test_system_samples_shape_defects_block(tmp_path: Path, plant: str):
    root = make_run(tmp_path / "run", regime="auth-freeze-effect")

    def mutate(value):
        if plant == "kind":
            value["kind"] = "hotel-system-samples-v1"
        elif plant == "count":
            value["samples"].pop()
        elif plant == "grid":
            value["samples"][10]["epoch"] += 1.0
        else:
            value["startAtEpoch"] += 5.0

    _mutate_json(root, "system-samples.json", mutate)
    assert _failed(candidate_pilot.validate_run(root), "system-samples")
