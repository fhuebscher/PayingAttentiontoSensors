"""The real OTel terminal validator: accepts one exact, complete, lattice-nested
36-cell offpath campaign and is watched failing on every planted defect class, including
the two the adversarial review found in its predecessor (OTEL-RUNTIME-009: empty
correlation accepted; OTEL-RUNTIME-010: wrong workload accepted). Under the frozen
v1 descriptor it still refuses everything, because the refusal is the descriptor's
posture realization, not a hardcoded raise."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("otel_candidate_terminal_runtime_tests", "modules/otel-demo/execution/candidate_runtime.py")
terminal = _load("otel_candidate_terminal_tests", "modules/otel-demo/validation/candidate_terminal.py")
pilot = _load("otel_candidate_terminal_pilot_tests", "modules/otel-demo/execution/candidate_pilot.py")
CATALOG = runtime.posture_catalog()
IMAGE = "sha256:" + "a" * 64
# Offpath timing (faultDesign defaults): onset 45 s, hold 15 s.
FAULT_ONSET = 45.0
FAULT_APPLIED = 45.2
FAULT_REVERTING = 60.1
FAULT_OFFSET = 60.4
ASYNC_SERVICES = ["accountingservice", "frauddetectionservice", "kafka"]


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _package(tmp_path: Path):
    compiled = tmp_path / "compiled"
    pilot.materialize(compiled)
    bindings = runtime.inspect_compiled_plan(compiled)
    binding = runtime.operational_binding(
        bindings,
        framework_commit="a" * 40,
        campaign_id="otelcand-terminal-a",
        repository_bundle_sha256="b" * 64,
        upstream_bundle_sha256="c" * 64,
        expected_materialized_source_sha256="d" * 64,
    )
    images = {service: IMAGE for service in CATALOG["applicationServices"]}
    return runtime.RuntimePackage(
        bindings=bindings,
        gate_plan={"binding": binding}, gate_plan_sha256="1" * 64,
        gate_setup={}, gate_setup_sha256="4" * 64,
        setup_receipt={}, setup_receipt_sha256="5" * 64,
        readiness={"installedBindings": {"materializedSourceSha256": "d" * 64, "imageIds": images, "installedControllerDigests": binding["controllerDigests"]}}, readiness_sha256="2" * 64,
        gate_run={"binding": {"campaignId": binding["campaignId"]}},
        gate_run_sha256="3" * 64,
        validated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )


def _during_fault(sequence: int, effect: bool) -> bool:
    return effect and FAULT_ONSET <= sequence <= FAULT_OFFSET


def _outage(sequence: int, contract: dict) -> bool:
    """Only an entry-point fault fails journeys; an off-path one does not."""
    fault = contract["fault"]
    return _during_fault(sequence, fault["scenario"] is not None) and fault["entryRouteDuringFault"] == "must-be-unavailable"


def _step(name: str, start: float, status: int) -> dict:
    return {
        "name": name, "status": status, "bytes": 100 if status == 200 else 0,
        "startedAtEpoch": start, "endedAtEpoch": start + 0.04,
        "error": None if status == 200 else f"HTTP {status}",
    }


def _request_rows(run_id: str, contract: dict) -> list[dict]:
    rows = []
    for sequence in range(600):
        digest = hashlib.sha256(f"{run_id}\0{sequence}".encode()).hexdigest()
        token = f"opq-{digest[:24]}"
        trace_id = digest[:32]
        span_id = hashlib.sha256((token + "\0span").encode()).hexdigest()[:16]
        if _outage(sequence, contract):
            steps = [_step("add-to-cart", float(sequence), 503)]
            error = "add-to-cart: HTTP 503"
        else:
            steps = [_step("add-to-cart", float(sequence), 200), _step("place-order", sequence + 0.05, 200)]
            error = None
        rows.append({
            "requestToken": token, "originalTraceId": trace_id,
            "traceparent": f"00-{trace_id}-{span_id}-01",
            "scheduledAtEpoch": float(sequence), "startedAtEpoch": float(sequence),
            "endedAtEpoch": sequence + 0.1, "status": steps[-1]["status"],
            "bytes": steps[-1]["bytes"], "error": error, "steps": steps,
        })
    return rows


def _seal(root: Path, required: list[str]) -> None:
    rows = []
    for name in sorted(set(required) - {"content-manifest.json"}):
        payload = (root / name).read_bytes()
        rows.append({"path": name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    _write(root / "content-manifest.json", {"schemaVersion": 1, "algorithm": "sha256", "files": rows})


def _cpu_resources(claim_use: str) -> dict:
    services = CATALOG["costApplicationServices"]
    before_services = {
        service: {"containerId": f"container-{service}", "totalUsageNanoseconds": 1_000_000_000}
        for service in services
    }
    after_services = {
        service: {"containerId": f"container-{service}", "totalUsageNanoseconds": 1_000_000_000 + 12_000_000_000 // len(services)}
        for service in services
    }
    after_services[services[-1]]["totalUsageNanoseconds"] += 12_000_000_000 % len(services)
    return {
        "schemaVersion": 1,
        "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
        "before": {
            "capturedAtStart": "2026-08-30T01:00:00Z", "capturedAtEnd": "2026-08-30T01:00:01Z",
            "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
            "services": before_services,
            "totalNanoseconds": sum(row["totalUsageNanoseconds"] for row in before_services.values()),
        },
        "after": {
            "capturedAtStart": "2026-08-30T01:10:00Z", "capturedAtEnd": "2026-08-30T01:10:01Z",
            "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
            "services": after_services,
            "totalNanoseconds": sum(row["totalUsageNanoseconds"] for row in after_services.values()),
        },
        "applicationCpuSeconds": 12.0,
        "offeredRequests": 600,
        "cpuSecondsPerOfferedRequest": 0.02,
        "claimUse": claim_use,
    }


def _posture_proof(contract: dict) -> dict:
    posture = contract["posture"]["id"]
    active = contract["posture"]["expected"]["activeApplicationServices"]
    services = {}
    loaded = []
    for service in CATALOG["applicationServices"]:
        is_active = service in active
        expected = runtime.expected_service_control(CATALOG, posture, service)
        if expected["probe"] is None:
            observed_control = observed_load = "not-probed"
        else:
            observed_control = expected["expectedControl"]
            observed_load = expected["expectedLoadState"]
            if observed_control == "enabled":
                loaded.append(service)
        services[service] = {
            "containerId": "container-" + service, "imageId": IMAGE,
            "otelSdkDisabled": "false" if is_active else "true",
            "tracesExporter": "otlp" if is_active else "none",
            "metricsExporter": "otlp" if is_active else "none",
            "logsExporter": "otlp" if is_active else "none",
            "expectedActive": is_active,
            "instrumentation": {
                "mechanism": expected["mechanism"],
                "expectedControl": expected["expectedControl"],
                "expectedLoadState": expected["expectedLoadState"],
                "probe": expected["probe"],
                "observedControl": observed_control,
                "observedLoadState": observed_load,
                "evidence": {"entrypoint": None, "cmd": None, "otelPlacementEnabled": "true" if is_active else "false"},
            },
        }
    return {
        "schemaVersion": 2, "posture": posture,
        "expectedActiveApplicationServices": active,
        "observedSignalServices": sorted(set(terminal.TARGET_PATH) & set(active)) if posture != "none" else [],
        "unexpectedSignalServices": [],
        "postureConfigSha256": runtime.posture_config_sha256(contract),
        "renderedComposeConfigSha256": hashlib.sha256(posture.encode()).hexdigest(),
        "services": services, "loadedServices": sorted(loaded), "exact": True,
    }


def _intervention(contract: dict) -> dict:
    fault = contract["fault"]
    barrier = 1000.0
    paused = fault["action"] == "pause"
    return {
        "scenario": fault["scenario"], "service": fault["service"],
        "targetContainerId": f"container-{fault['service']}", "targetImageId": IMAGE,
        "preState": {"Running": True, "Paused": False},
        "duringStateSamples": [{"Running": paused, "Paused": paused}],
        "postState": {"Running": True, "Paused": False},
        "actualOnsetMonotonicOffsetSeconds": FAULT_ONSET,
        "actualOffsetMonotonicOffsetSeconds": FAULT_OFFSET,
        "barrierMonotonic": barrier,
        "appliedMonotonic": barrier + FAULT_APPLIED,
        "revertingMonotonic": barrier + FAULT_REVERTING,
        "appliedMonotonicOffsetSeconds": FAULT_APPLIED,
        "revertingMonotonicOffsetSeconds": FAULT_REVERTING,
        "duringRouteAvailable": fault["entryRouteDuringFault"] != "must-be-unavailable",
        "manifested": True, "recovered": True, "successful": True, "error": None,
    }


def _cell_fixture(root: Path, contract: dict) -> None:
    root.mkdir(parents=True)
    effect = contract["window"]["kind"] != "cost"
    requests = _request_rows(contract["runId"], contract)
    failed = sum(row["error"] is not None for row in requests)
    port = contract["compose"]["ports"]["frontend"]
    ledger = {
        "schemaVersion": 1, "url": f"http://127.0.0.1:{port}{contract['workload']['urlPath']}",
        "tokenNamespace": contract["runId"],
        "ratePerSecond": contract["workload"]["requestsPerSecond"],
        "concurrency": contract["workload"]["concurrency"], "startedAtEpoch": 0.0,
        "endedAtEpoch": 600.5, "offered": 600, "completed": 600 - failed, "failed": failed,
        "requests": requests,
    }
    _write(root / "request-ledger.json", ledger)
    _write(root / "application-witness.json", {
        "schemaVersion": 1, "source": "frontendproxy-json-access-log",
        "offeredTokens": 600, "witnessedTokens": 600,
        "duplicateWitnessTokens": [], "unknownWitnessTokens": [],
        "rows": [
            {"request_token": row["requestToken"], "traceparent": row["traceparent"], "response_code": str(row["status"])}
            for row in requests
        ],
    })
    posture = contract["posture"]["id"]
    enabled = posture != "none"
    active = set(CATALOG["postures"][posture]["activeApplicationServices"])
    path_services = sorted(set(terminal.TARGET_PATH) & active)
    # A completed journey's trace also reaches the order consumers when they
    # are instrumented (async, full).
    trace_services = sorted(set(path_services) | (set(ASYNC_SERVICES) & active))
    rows = []
    for index, row in enumerate(requests):
        if not enabled:
            observed, services, traced = [], [], []
        elif _outage(index, contract):
            observed, services, traced = [row["originalTraceId"]], ["frontendproxy"], ["frontendproxy"]
        else:
            observed, services, traced = [row["originalTraceId"]], path_services, trace_services
        rows.append({
            "requestToken": row["requestToken"], "injectedOriginalTraceId": row["originalTraceId"],
            "observedOriginalTraceIds": observed, "observedPathServices": services,
            "observedTraceServices": traced,
        })
    _write(root / "trace-correlation.json", {
        "schemaVersion": 1, "correlation": "injected-w3c-original-trace-id",
        "crossTraceAssembly": False,
        "observedUniqueTraceIds": 600 if enabled else 0,
        "rows": rows,
    })
    _write(root / "posture-proof.json", _posture_proof(contract))
    pcap = b"pcap candidate fixture\n"
    (root / "telemetry.pcap").write_bytes(pcap)
    _write(root / "telemetry-bytes.json", {
        "schemaVersion": 1, "captureTool": "tshark",
        "filter": "tcp dst port 4317 or tcp dst port 4318",
        "emittedTelemetryBytes": 0 if not enabled else 1000,
        "onWireTelemetryBytes": 0 if not enabled else 1500,
        "retransmissionsExcludedFromEmitted": True,
        "pcapSha256": hashlib.sha256(pcap).hexdigest(),
    })
    # A complete carrier: its first retained debug-exporter record precedes the
    # window start (the fixture ledger starts at epoch 0.0).
    (root / "otelcol.log").write_text(
        "otelcol-1  | 2026-09-24T07:00:00.000Z\tinfo\tservice starting\n"
        "otelcol-1  | StartTimestamp: 1969-12-31 23:00:00 +0000 UTC\n"
        "otelcol-1  | Timestamp: 1969-12-31 23:58:00.000000001 +0000 UTC\n"
        "otelcol-1  | Timestamp: 1970-01-01 00:05:00.5 +0000 UTC\n",
        encoding="utf-8",
    )
    if not effect:
        _write(root / "resources.json", _cpu_resources("cost-proxy"))
    else:
        _write(root / "effect-resources.json", _cpu_resources("diagnostic-only"))
        _write(root / "intervention.json", _intervention(contract))
    _write(root / "cell-cleanup.json", {
        "schemaVersion": 1, "project": contract["compose"]["project"],
        "remainingResources": {"containers": [], "networks": [], "volumes": []},
        "ownedResourcesClean": True, "completedAt": "2026-08-30T01:00:00Z",
    })
    _write(root / "receipt.json", {
        "schemaVersion": 1, "kind": "otel-demo-candidate-cell-receipt-v1",
        "target": contract["target"],
        "runId": contract["runId"], "runKey": contract["runKey"], "state": "valid",
        "result": {"offered": 600, "completed": 600 - failed, "failed": failed},
        "error": None, "promotionAuthorized": False,
    })
    _seal(root, contract["requiredArtifacts"])


def _campaign_fixture(tmp_path: Path):
    package = _package(tmp_path)
    retained = tmp_path / "retained"
    contracts = {}
    for cell in package.bindings.cells:
        contract = runtime.build_cell_contract(package, cell)
        contracts[cell["runId"]] = contract
        _cell_fixture(retained / contract["compiledArtifactRoot"], contract)
    binding = package.gate_plan["binding"]
    gate = next(c for c in contracts.values() if c["workloadPathCheck"]["gatesCampaign"])
    gate_root = retained / gate["compiledArtifactRoot"]
    _write(retained / "workload-path-check.json", terminal._remote().workload_path_check(
        gate, gate_root, json.loads((gate_root / "receipt.json").read_text())
    ))
    _write(retained / "remote-terminal.json", {
        "schemaVersion": 1, "kind": "otel-demo-candidate-remote-terminal-v1",
        "target": {"host": "fb14srv6", "executionUser": "stig", "uid": 1016, "gid": 1016, "supplementalGids": [998]},
        "expectedCells": 36, "attemptedCells": 36, "validCells": 36, "stopped": False,
        "promotionAuthorized": False,
    })
    _write(retained / "host-release.json", {
        "schemaVersion": 1, "kind": "srv6-otel-host-release-v1", "campaignId": binding["campaignId"],
        "systemdUnit": f"{binding['compose']['project']}.service", "leasePath": binding["exclusiveLeasePath"],
        "leaseDescriptor": 3, "leaseHeldUntilControllerExit": True, "composeProject": binding["compose"]["project"],
        "remainingOwnedResources": {"containers": [], "networks": [], "volumes": []},
        "reservedPorts": [18080, 18081, 18082, 18083, 18084], "successor": "online-boutique",
        "successorMustRecheckLeaseAndPorts": True, "readyForSuccessorAfterControllerExit": True,
        "foreignResourcesTouched": [], "completedAt": "2026-08-30T02:00:00Z",
    })
    return package, retained, contracts


def _recondition(root: Path, contract: dict) -> None:
    (root / "content-manifest.json").unlink(missing_ok=True)
    _seal(root, contract["requiredArtifacts"])


@pytest.fixture
def realized(monkeypatch):
    """Lift the descriptor-driven refusal the way a v2 study epoch would: every
    posture implemented. Nothing else about the validator changes."""
    bound = terminal._runtime()
    monkeypatch.setattr(bound, "unsupported_postures", lambda: [])
    monkeypatch.setattr(bound, "admitted_study_epochs", lambda: (bound.STUDY_EPOCH,))
    yield bound


def test_terminal_refuses_while_the_v2_epoch_is_not_admitted_by_the_target_controllers(tmp_path: Path, monkeypatch):
    bound = terminal._runtime()
    monkeypatch.setattr(bound, "admitted_study_epochs", lambda: ())
    package, retained, _ = _campaign_fixture(tmp_path)
    with pytest.raises(terminal.ValidationError, match="not admitted by the installed target controllers"):
        terminal.validate_campaign(package.bindings.root, retained, package)


def test_terminal_refuses_a_descriptor_shape_with_unrealized_postures(tmp_path: Path, monkeypatch):
    bound = terminal._runtime()
    monkeypatch.setattr(bound, "admitted_study_epochs", lambda: (bound.STUDY_EPOCH,))
    monkeypatch.setattr(bound, "unsupported_postures", lambda: ["none", "selected"])
    package, retained, _ = _campaign_fixture(tmp_path)
    with pytest.raises(terminal.ValidationError, match="none and selected are not structurally realizable"):
        terminal.validate_campaign(package.bindings.root, retained, package)


def test_terminal_accepts_a_complete_exact_lattice_nested_campaign(tmp_path: Path, realized):
    package, retained, _ = _campaign_fixture(tmp_path)
    report = terminal.validate_campaign(package.bindings.root, retained, package)
    assert report["verdict"] == "pass" and report["validCells"] == 36
    assert report["workloadPathCheck"]["matchingJourneys"] == report["workloadPathCheck"]["successfulJourneys"] == 600
    assert report["kind"] == "otel-demo-candidate-terminal-validation-v2"
    assert report["promotionAuthorized"] is False and report["canonical"] is False
    lattice = report["postureLattice"]["postures"]
    assert lattice["none"]["loadedServices"] == []
    probed = lambda posture: sorted(
        s for s in CATALOG["postures"][posture]["activeApplicationServices"]
        if CATALOG["serviceInstrumentation"][s]["runtimeProbe"] is not None
    )
    assert lattice["selected"]["loadedServices"] == probed("selected")
    assert "checkoutservice" in lattice["selected"]["loadedServices"]
    assert "recommendationservice" not in lattice["selected"]["loadedServices"]
    assert set(lattice["async"]["loadedServices"]) - set(lattice["selected"]["loadedServices"]) == {
        "accountingservice", "frauddetectionservice", "kafka",
    }
    assert (
        set(lattice["none"]["loadedServices"]) < set(lattice["selected"]["loadedServices"])
        < set(lattice["async"]["loadedServices"]) < set(lattice["full"]["loadedServices"])
    )
    assert len({row["postureConfigSha256"] for row in lattice.values()}) == 4
    assert report["postureLattice"]["rule"] == "none-subset-selected-subset-async-subset-full"
    effect = [row for row in report["cells"] if row["runKey"]["regime"] != "no-fault-cost"]
    assert {row["runKey"]["regime"] for row in effect} == {"fraud-pause-effect", "frontend-pause-effect"}
    assert all(row["correlation"]["phases"]["during-fault"]["requests"] > 0 for row in effect)
    assert all(row["correlation"]["phases"]["pre-fault"]["fullPath"] == row["correlation"]["phases"]["pre-fault"]["requests"] for row in effect if row["posture"]["posture"] != "none")


@pytest.mark.parametrize(
    "plant",
    (
        "missing-witness", "duplicate-request-token", "cross-trace-id",
        "posture-contamination", "wire-under-payload", "pcap-tamper",
        "cpu-denominator", "cpu-counter-delta", "failed-recovery",
        "cleanup-leak", "self-promote",
        # OTEL-RUNTIME-009: correlation removed entirely / dropped for pre-fault requests.
        "empty-correlation", "pre-fault-path-missing", "fault-never-manifested-in-telemetry",
        # OTEL-RUNTIME-010: workload of the wrong shape.
        "wrong-url", "wrong-rate", "wrong-concurrency", "short-window",
        # posture proof v2
        "agent-loaded-in-disabled-posture", "config-digest-drift", "none-posture-signals",
        "load-state-relabelled", "loaded-set-mismatch",
    ),
)
def test_terminal_checker_is_watched_failing_on_planted_cell_defects(tmp_path: Path, plant: str, realized):
    package = _package(tmp_path)
    wants_effect = plant in {"failed-recovery", "fault-never-manifested-in-telemetry"}
    wants_none = plant == "none-posture-signals"
    # Pin the posture rather than "first non-none cell": the v2 epoch is a fresh
    # randomization, so schedule position no longer implies a posture.
    wanted_posture = "none" if wants_none else "selected"
    cell = next(
        candidate for candidate in package.bindings.cells
        if (candidate["runKey"]["regime"] == "frontend-pause-effect") == wants_effect
        and candidate["runKey"]["posture"] == wanted_posture
    )
    contract = runtime.build_cell_contract(package, cell)
    root = tmp_path / "cell"
    _cell_fixture(root, contract)
    if plant == "missing-witness":
        (root / "application-witness.json").unlink()
        with pytest.raises(terminal.ValidationError): terminal.validate_cell(root, contract)
        return
    if plant == "duplicate-request-token":
        ledger = json.loads((root / "request-ledger.json").read_text())
        ledger["requests"][1]["requestToken"] = ledger["requests"][0]["requestToken"]
        _write(root / "request-ledger.json", ledger)
    elif plant == "cross-trace-id":
        value = json.loads((root / "trace-correlation.json").read_text())
        value["rows"][0]["observedOriginalTraceIds"] = ["0" * 32]
        _write(root / "trace-correlation.json", value)
    elif plant == "empty-correlation":
        value = json.loads((root / "trace-correlation.json").read_text())
        for row in value["rows"]:
            row["observedOriginalTraceIds"] = []
            row["observedPathServices"] = []
        value["observedUniqueTraceIds"] = 0
        _write(root / "trace-correlation.json", value)
    elif plant == "pre-fault-path-missing":
        value = json.loads((root / "trace-correlation.json").read_text())
        value["rows"][5]["observedPathServices"] = ["frontendproxy"]
        _write(root / "trace-correlation.json", value)
    elif plant == "fault-never-manifested-in-telemetry":
        # Offpath: telemetry is no longer the manifestation proof (a 15 s pause
        # can leave every journey fully traced); the receipt is. A frontend
        # pause whose entry-route probe stayed up did not manifest.
        value = json.loads((root / "intervention.json").read_text())
        value["duringRouteAvailable"] = True
        _write(root / "intervention.json", value)
    elif plant == "posture-contamination":
        value = json.loads((root / "posture-proof.json").read_text())
        value["unexpectedSignalServices"] = ["adservice"]
        value["exact"] = False
        _write(root / "posture-proof.json", value)
    elif plant == "agent-loaded-in-disabled-posture":
        value = json.loads((root / "posture-proof.json").read_text())
        row = value["services"]["kafka"]["instrumentation"]
        assert row["expectedControl"] == "disabled"
        row["observedControl"] = "enabled"; row["observedLoadState"] = "loaded"
        value["loadedServices"] = sorted(value["loadedServices"] + ["kafka"])
        _write(root / "posture-proof.json", value)
    elif plant == "load-state-relabelled":
        # emailservice is loaded-silenced (never not-loaded) when disabled, and
        # loaded when active, so relabelling to not-loaded is a lie in either
        # posture this fixture can pick -- unlike a source-guarded in-code-SDK
        # service (e.g. checkoutservice), whose disabled load state really is
        # not-loaded now, which would make this specific relabelling a no-op.
        value = json.loads((root / "posture-proof.json").read_text())
        value["services"]["emailservice"]["instrumentation"]["expectedLoadState"] = "not-loaded"
        _write(root / "posture-proof.json", value)
    elif plant == "loaded-set-mismatch":
        value = json.loads((root / "posture-proof.json").read_text())
        value["loadedServices"] = []
        _write(root / "posture-proof.json", value)
    elif plant == "config-digest-drift":
        value = json.loads((root / "posture-proof.json").read_text())
        value["postureConfigSha256"] = "0" * 64
        _write(root / "posture-proof.json", value)
    elif plant == "none-posture-signals":
        value = json.loads((root / "posture-proof.json").read_text())
        value["observedSignalServices"] = ["checkoutservice"]
        _write(root / "posture-proof.json", value)
    elif plant == "wire-under-payload":
        value = json.loads((root / "telemetry-bytes.json").read_text())
        value["onWireTelemetryBytes"] = max(0, value["emittedTelemetryBytes"] - 1)
        _write(root / "telemetry-bytes.json", value)
    elif plant == "pcap-tamper":
        (root / "telemetry.pcap").write_bytes(b"tampered\n")
    elif plant == "cpu-denominator":
        value = json.loads((root / "resources.json").read_text())
        value["offeredRequests"] = 599
        _write(root / "resources.json", value)
    elif plant == "cpu-counter-delta":
        value = json.loads((root / "resources.json").read_text())
        service = CATALOG["costApplicationServices"][0]
        value["after"]["services"][service]["totalUsageNanoseconds"] += 1
        value["after"]["totalNanoseconds"] += 1
        _write(root / "resources.json", value)
    elif plant == "failed-recovery":
        value = json.loads((root / "intervention.json").read_text())
        value["recovered"] = value["successful"] = False
        _write(root / "intervention.json", value)
    elif plant == "cleanup-leak":
        value = json.loads((root / "cell-cleanup.json").read_text())
        value["remainingResources"]["containers"] = ["leak"]
        value["ownedResourcesClean"] = False
        _write(root / "cell-cleanup.json", value)
    elif plant in {"wrong-url", "wrong-rate", "wrong-concurrency", "short-window"}:
        value = json.loads((root / "request-ledger.json").read_text())
        if plant == "wrong-url":
            value["url"] = value["url"].replace("/api/checkout", "/api/cart")
        elif plant == "wrong-rate":
            value["ratePerSecond"] = 2
        elif plant == "wrong-concurrency":
            value["concurrency"] = 1
        else:
            value["endedAtEpoch"] = 300.0
            for row in value["requests"]:
                row["scheduledAtEpoch"] = min(row["scheduledAtEpoch"], 299.0)
        _write(root / "request-ledger.json", value)
    else:
        value = json.loads((root / "receipt.json").read_text())
        value["promotionAuthorized"] = True
        _write(root / "receipt.json", value)
    _recondition(root, contract)
    with pytest.raises(terminal.ValidationError):
        terminal.validate_cell(root, contract)


def test_terminal_rejects_a_partial_retained_tree(tmp_path: Path, realized):
    package = _package(tmp_path)
    retained = tmp_path / "retained"
    contract = runtime.build_cell_contract(package, package.bindings.cells[0])
    _cell_fixture(retained / contract["compiledArtifactRoot"], contract)
    with pytest.raises(terminal.ValidationError, match="absent"):
        terminal.validate_campaign(package.bindings.root, retained, package)


@pytest.mark.parametrize("plant", ("stopped", "lattice-collapsed", "host-not-released", "posture-disagreement"))
def test_terminal_rejects_campaign_level_defects(tmp_path: Path, realized, plant):
    package, retained, contracts = _campaign_fixture(tmp_path)
    if plant == "stopped":
        value = json.loads((retained / "remote-terminal.json").read_text())
        value["stopped"] = True; value["validCells"] = 17
        _write(retained / "remote-terminal.json", value)
    elif plant == "host-not-released":
        value = json.loads((retained / "host-release.json").read_text())
        value["remainingOwnedResources"]["volumes"] = ["leak"]
        _write(retained / "host-release.json", value)
    else:
        # Relabel every selected cell's proof so the observed loaded set equals the
        # full set (lattice collapsed) or one selected cell disagrees with the others.
        targets = [c for c in contracts.values() if c["posture"]["id"] == "selected"]
        if plant == "posture-disagreement":
            targets = targets[:1]
        for contract in targets:
            root = retained / contract["compiledArtifactRoot"]
            value = json.loads((root / "posture-proof.json").read_text())
            for service, row in value["services"].items():
                inst = row["instrumentation"]
                if inst["probe"] is not None and inst["observedControl"] == "disabled":
                    inst["observedControl"] = "enabled"; inst["observedLoadState"] = "loaded"
                    inst["expectedControl"] = "enabled"; inst["expectedLoadState"] = "loaded"
            value["loadedServices"] = sorted(
                s for s, r in value["services"].items() if r["instrumentation"]["observedControl"] == "enabled"
            )
            _write(root / "posture-proof.json", value)
            _recondition(root, contract)
    with pytest.raises(terminal.ValidationError):
        terminal.validate_campaign(package.bindings.root, retained, package)


def test_lattice_check_requires_strict_nesting(realized):
    def proof(posture, loaded):
        return {"posture": {"posture": posture, "loadedServices": loaded, "postureConfigSha256": posture * 16, "renderedComposeConfigSha256": posture * 16, "observedSignalServices": []}}
    probed = lambda posture: sorted(
        s for s in CATALOG["postures"][posture]["activeApplicationServices"]
        if CATALOG["serviceInstrumentation"][s]["runtimeProbe"] is not None
    )
    selected, async_, full = probed("selected"), probed("async"), probed("full")
    reports = [proof("none", []), proof("selected", selected), proof("async", async_), proof("full", full)]
    result = terminal.validate_lattice(reports, CATALOG)
    assert result["postures"]["full"]["loadedServices"] == full
    assert result["postures"]["async"]["loadedServices"] == async_
    with pytest.raises(terminal.ValidationError, match="differ from the catalog closure"):
        terminal.validate_lattice([proof("none", ["kafka"]), proof("selected", selected), proof("async", async_), proof("full", full)], CATALOG)
    with pytest.raises(terminal.ValidationError, match="no valid full cell"):
        terminal.validate_lattice([proof("none", []), proof("selected", selected), proof("async", async_)], CATALOG)
    # Planted: a three-posture campaign (run 3's shape) has no async cell and is refused.
    with pytest.raises(terminal.ValidationError, match="no valid async cell"):
        terminal.validate_lattice([proof("none", []), proof("selected", selected), proof("full", full)], CATALOG)
    # Planted: an async cell that loaded adservice (outside its closure) is refused.
    with pytest.raises(terminal.ValidationError, match="async observed loaded services differ from the catalog closure"):
        terminal.validate_lattice([proof("none", []), proof("selected", selected), proof("async", sorted(async_ + ["adservice"])), proof("full", full)], CATALOG)
    # Planted: async observing selected's set collapses the strict chain.
    with pytest.raises(terminal.ValidationError, match="async observed loaded services differ"):
        terminal.validate_lattice([proof("none", []), proof("selected", selected), proof("async", selected), proof("full", full)], CATALOG)


# --- OTel run-2 fixes, each watched failing (or deliberately accepting) on the
# --- exact shape run 1 produced (replay 2026-09-23, tmp/otel-shakedown-evidence).

RUN2_PLANTS = {
    # plant: (posture, expected rejection substring or None for accept)
    "truncated-carrier": ("selected", "carrier does not cover"),
    "carrier-without-records": ("none", "carrier does not cover"),
    "epoch-zero-then-late-record": ("full", "carrier does not cover"),
    "enabled-witness-parent-rewritten": ("full", None),
    "enabled-witness-trace-id-rewritten": ("selected", "witness traceparent"),
    "enabled-witness-parent-zero": ("selected", "witness traceparent"),
    "none-witness-parent-rewritten": ("none", "witness traceparent"),
    "run1-none-collector-self-telemetry": ("none", None),
    "none-collector-self-telemetry": ("none", None),
    "none-collector-plus-application": ("none", "unexpected signal services"),
    "enabled-collector-self-telemetry": ("selected", None),
    "run1-enabled-collector-and-proxy": ("full", None),
    "enabled-application-outside-posture": ("selected", "unexpected signal services ['adservice']"),
    "enabled-application-outside-posture-with-collector": ("selected", "unexpected signal services ['recommendationservice']"),
    "run1-enabled-proxy-span-name": ("full", None),
    "recorded-unexpected-not-replayable": ("full", "do not replay"),
    "exact-flag-inconsistent": ("selected", "exact flag"),
    # v3 async posture: a signal from a service outside the async closure is
    # refused; the order-path services inside it are accepted.
    "async-application-outside-closure": ("async", "unexpected signal services ['adservice']"),
    "async-order-path-inside-closure": ("async", None),
}


@pytest.mark.parametrize("plant", sorted(RUN2_PLANTS))
def test_run2_fix_plants(tmp_path: Path, plant: str, realized):
    posture, rejection = RUN2_PLANTS[plant]
    package = _package(tmp_path)
    cell = next(
        candidate for candidate in package.bindings.cells
        if candidate["runKey"]["regime"] == "no-fault-cost" and candidate["runKey"]["posture"] == posture
    )
    contract = runtime.build_cell_contract(package, cell)
    root = tmp_path / "cell"
    _cell_fixture(root, contract)
    proof = json.loads((root / "posture-proof.json").read_text())
    if plant == "truncated-carrier":
        # Run 1's shape: the log starts mid-record, its first Timestamp 590 s
        # after the window start, 9 s before the window end.
        (root / "otelcol.log").write_text(
            "otelcol-1  | Data point attributes:\n"
            "otelcol-1  | StartTimestamp: 1969-12-31 23:00:00 +0000 UTC\n"
            "otelcol-1  | Timestamp: 1970-01-01 00:09:50.450767915 +0000 UTC\n", encoding="utf-8")
    elif plant == "carrier-without-records":
        (root / "otelcol.log").write_text("otelcol-1  | 2026-09-24T07:00:00Z info starting\n", encoding="utf-8")
    elif plant == "epoch-zero-then-late-record":
        (root / "otelcol.log").write_text(
            "otelcol-1  | Timestamp: 1970-01-01 00:00:00 +0000 UTC\n"
            "otelcol-1  | Timestamp: 1970-01-01 00:09:50 +0000 UTC\n", encoding="utf-8")
    elif plant.startswith(("enabled-witness", "none-witness")):
        value = json.loads((root / "application-witness.json").read_text())
        for row in value["rows"]:
            version, trace_id, parent, flags = row["traceparent"].split("-")
            if plant.endswith("trace-id-rewritten"):
                trace_id = "f" * 32
            elif plant.endswith("parent-zero"):
                parent = "0" * 16
            else:
                parent = hashlib.sha256(parent.encode()).hexdigest()[:16]
            row["traceparent"] = "-".join((version, trace_id, parent, flags))
        _write(root / "application-witness.json", value)
    elif plant == "run1-none-collector-self-telemetry":
        proof.update(observedSignalServices=["otelcol"], unexpectedSignalServices=["otelcol"], exact=False)
    elif plant == "none-collector-self-telemetry":
        proof.update(observedSignalServices=["otelcol"], unexpectedSignalServices=[], exact=True)
    elif plant == "none-collector-plus-application":
        proof.update(observedSignalServices=["frontend", "otelcol"], unexpectedSignalServices=["frontend"], exact=False)
    elif plant == "enabled-collector-self-telemetry":
        observed = sorted(proof["observedSignalServices"] + ["otelcol"])
        proof.update(observedSignalServices=observed, unexpectedSignalServices=["otelcol"], exact=False)
    elif plant == "run1-enabled-collector-and-proxy":
        # Run 1's exact enabled shape: both spellings the fixes address, at once.
        observed = sorted(["frontend-proxy" if name == "frontendproxy" else name for name in proof["observedSignalServices"]] + ["otelcol"])
        proof.update(observedSignalServices=observed, unexpectedSignalServices=["frontend-proxy", "otelcol"], exact=False)
    elif plant == "async-application-outside-closure":
        observed = sorted(proof["observedSignalServices"] + ["adservice"])
        proof.update(observedSignalServices=observed, unexpectedSignalServices=["adservice"], exact=False)
    elif plant == "async-order-path-inside-closure":
        observed = sorted(set(proof["observedSignalServices"]) | {"frauddetectionservice", "kafka"})
        proof.update(observedSignalServices=observed, unexpectedSignalServices=[], exact=True)
    elif plant == "enabled-application-outside-posture":
        observed = sorted(proof["observedSignalServices"] + ["adservice"])
        proof.update(observedSignalServices=observed, unexpectedSignalServices=["adservice"], exact=False)
    elif plant == "enabled-application-outside-posture-with-collector":
        observed = sorted(proof["observedSignalServices"] + ["recommendationservice", "otelcol"])
        proof.update(observedSignalServices=observed, unexpectedSignalServices=["recommendationservice", "otelcol"], exact=False)
    elif plant == "run1-enabled-proxy-span-name":
        observed = sorted(["frontend-proxy" if name == "frontendproxy" else name for name in proof["observedSignalServices"]])
        proof.update(observedSignalServices=observed, unexpectedSignalServices=["frontend-proxy"], exact=False)
    elif plant == "recorded-unexpected-not-replayable":
        proof.update(unexpectedSignalServices=["adservice-typo"], exact=False)
    elif plant == "exact-flag-inconsistent":
        proof.update(exact=False)
    _write(root / "posture-proof.json", proof)
    _recondition(root, contract)
    if rejection is None:
        report = terminal.validate_cell(root, contract)
        assert report["state"] == "valid" and report["collectorCarrier"]["coversWindow"] is True
    else:
        with pytest.raises(terminal.ValidationError, match=__import__("re").escape(rejection)):
            terminal.validate_cell(root, contract)


# --- offpath (direction (c)): the workload path check and the generic fault ---


def _gate_cell(package, retained: Path):
    contract = next(
        runtime.build_cell_contract(package, cell) for cell in package.bindings.cells
        if runtime.build_cell_contract(package, cell)["workloadPathCheck"]["gatesCampaign"]
    )
    return contract, retained / contract["compiledArtifactRoot"]


def test_cross_module_offpath_constants_agree():
    remote = terminal._remote()
    assert list(pilot.OFFPATH_SYNC_PATH) == list(remote.TARGET_PATH) == terminal.TARGET_PATH
    assert tuple(sorted(pilot.OFFPATH_SYNC_PATH)) == runtime.SELECTED_CLOSURE == pilot.OFFPATH_SELECTED_CLOSURE
    assert tuple(sorted(remote.ASYNC_SERVICES)) == tuple(sorted(pilot.OFFPATH_ASYNC_ADDED_SERVICES))
    assert runtime.ASYNC_CLOSURE == pilot.OFFPATH_ASYNC_CLOSURE
    assert runtime.RUN_COUNT == remote.RUN_COUNT == terminal.EXPECTED_RUNS == pilot.TOTAL_RUNS == 36
    assert runtime.MINIMUM_REMAINING_SECONDS == remote.EXPECTED_MINIMUM_REMAINING_SECONDS
    assert CATALOG["postures"]["selected"]["activeApplicationServices"] == list(runtime.SELECTED_CLOSURE)
    assert CATALOG["postures"]["async"]["activeApplicationServices"] == list(runtime.ASYNC_CLOSURE)
    assert {name: row["service"] for name, row in pilot.OFFPATH_FAULT_SCENARIOS.items()}["fraud-pause"] == "frauddetectionservice"
    assert set(remote.FAULT_ACTIONS) >= {
        row["action"] for row in pilot.OFFPATH_FAULT_SCENARIOS.values() if row["implemented"]
    }


@pytest.mark.parametrize(
    "plant, verdict",
    (
        ("as-built", "pass"),
        ("flagd-missing", "fail"),
        ("extra-service", "fail"),
        ("async-only-extra", "pass"),
        ("cell-invalid", "fail"),
        ("no-successful-journey", "fail"),
    ),
)
def test_workload_path_check_is_watched_passing_and_failing(tmp_path: Path, realized, plant, verdict):
    """Planted defects for the selected literal: the first no-fault full cell's
    traced journeys must equal it (async consumers aside), else fail."""
    package, retained, _ = _campaign_fixture(tmp_path)
    contract, root = _gate_cell(package, retained)
    receipt = json.loads((root / "receipt.json").read_text())
    correlation = json.loads((root / "trace-correlation.json").read_text())
    if plant == "flagd-missing":
        correlation["rows"][7]["observedTraceServices"].remove("flagd")
    elif plant == "extra-service":
        correlation["rows"][7]["observedTraceServices"] = sorted(correlation["rows"][7]["observedTraceServices"] + ["recommendationservice"])
    elif plant == "async-only-extra":
        assert {"kafka", "frauddetectionservice"} <= set(correlation["rows"][7]["observedTraceServices"])
    elif plant == "cell-invalid":
        receipt["state"] = "invalid"
    elif plant == "no-successful-journey":
        ledger = json.loads((root / "request-ledger.json").read_text())
        for row in ledger["requests"]:
            row["error"] = "add-to-cart: HTTP 503"
        _write(root / "request-ledger.json", ledger)
    _write(root / "trace-correlation.json", correlation)
    check = terminal._remote().workload_path_check(contract, root, receipt)
    assert check["verdict"] == verdict, check["observedSynchronousSets"]
    if plant in {"flagd-missing", "extra-service"}:
        assert check["mismatchCount"] == 1 and check["firstMismatches"][0]["requestToken"] == correlation["rows"][7]["requestToken"]


@pytest.mark.parametrize("plant", ("failed-check", "missing-check", "tampered-check"))
def test_terminal_refuses_a_campaign_whose_path_check_failed_or_does_not_replay(tmp_path: Path, realized, plant):
    package, retained, _ = _campaign_fixture(tmp_path)
    path = retained / "workload-path-check.json"
    if plant == "missing-check":
        path.unlink()
    else:
        value = json.loads(path.read_text())
        if plant == "failed-check":
            # A recorded failure that also replays: rewrite the gating cell so it fails.
            contract, root = _gate_cell(package, retained)
            correlation = json.loads((root / "trace-correlation.json").read_text())
            for row in correlation["rows"]:
                if row["observedTraceServices"]:
                    row["observedTraceServices"] = sorted(set(row["observedTraceServices"]) | {"adservice"})
            _write(root / "trace-correlation.json", correlation)
            _recondition(root, contract)
            value = terminal._remote().workload_path_check(contract, root, json.loads((root / "receipt.json").read_text()))
            assert value["verdict"] == "fail"
        else:
            value["matchingJourneys"] += 1
        _write(path, value)
    with pytest.raises(terminal.ValidationError):
        terminal.validate_campaign(package.bindings.root, retained, package)


@pytest.mark.parametrize(
    "plant",
    ("wrong-service", "not-paused", "window-unordered", "barrier-drift", "short-hold",
     "frontend-route-up", "missing-applied", "journey-steps-inconsistent", "order-without-cart"),
)
def test_offpath_fault_and_journey_defects_fail_closed(tmp_path: Path, realized, plant):
    package = _package(tmp_path)
    regime = "frontend-pause-effect" if plant == "frontend-route-up" else "fraud-pause-effect"
    cell = next(c for c in package.bindings.cells if c["runKey"]["regime"] == regime and c["runKey"]["posture"] == "async")
    contract = runtime.build_cell_contract(package, cell)
    root = tmp_path / "cell"
    _cell_fixture(root, contract)
    terminal.validate_cell(root, contract)  # the unplanted cell is valid
    value = json.loads((root / "intervention.json").read_text())
    if plant == "wrong-service":
        value["service"] = "frontend"
    elif plant == "not-paused":
        value["duringStateSamples"] = [{"Running": True, "Paused": False}]
    elif plant == "window-unordered":
        value["appliedMonotonicOffsetSeconds"], value["revertingMonotonicOffsetSeconds"] = FAULT_REVERTING, FAULT_APPLIED
        value["appliedMonotonic"], value["revertingMonotonic"] = 1000.0 + FAULT_REVERTING, 1000.0 + FAULT_APPLIED
    elif plant == "barrier-drift":
        value["appliedMonotonic"] += 0.5
    elif plant == "short-hold":
        value["revertingMonotonicOffsetSeconds"] = FAULT_ONSET + 5
        value["revertingMonotonic"] = 1000.0 + FAULT_ONSET + 5
    elif plant == "frontend-route-up":
        value["duringRouteAvailable"] = True
    elif plant == "missing-applied":
        del value["appliedMonotonic"]
    if plant in {"journey-steps-inconsistent", "order-without-cart"}:
        ledger = json.loads((root / "request-ledger.json").read_text())
        if plant == "journey-steps-inconsistent":
            ledger["requests"][3]["steps"][1]["status"] = 500
        else:
            ledger["requests"][3]["steps"] = ledger["requests"][3]["steps"][:1]
        _write(root / "request-ledger.json", ledger)
    _write(root / "intervention.json", value)
    _recondition(root, contract)
    with pytest.raises(terminal.ValidationError):
        terminal.validate_cell(root, contract)


def test_off_path_fault_cell_with_every_journey_traced_is_valid(tmp_path: Path, realized):
    """The frontend-pause rule 'some during-fault journey lost its path' must
    not be applied to an off-path fault: there, a fully traced window is the
    outcome being measured, not a manifestation failure."""
    package = _package(tmp_path)
    cell = next(c for c in package.bindings.cells if c["runKey"]["regime"] == "fraud-pause-effect" and c["runKey"]["posture"] == "full")
    contract = runtime.build_cell_contract(package, cell)
    root = tmp_path / "cell"
    _cell_fixture(root, contract)
    report = terminal.validate_cell(root, contract)
    phases = report["correlation"]["phases"]
    assert phases["during-fault"]["fullPath"] == phases["during-fault"]["requests"] > 0


def test_frontend_pause_at_a_short_hold_may_leave_every_journey_traced(tmp_path: Path, realized):
    """Review 2026-10-02, finding 1: at the 15 s hold a paused frontend serves
    the stalled requests after unpause inside the step and Envoy timeouts, so
    every during-fault journey can complete with a full trace. The cell is valid
    on its receipt (paused + entry route down), not refused on its telemetry."""
    package = _package(tmp_path)
    cell = next(c for c in package.bindings.cells if c["runKey"]["regime"] == "frontend-pause-effect" and c["runKey"]["posture"] == "selected")
    contract = runtime.build_cell_contract(package, cell)
    root = tmp_path / "cell"
    _cell_fixture(root, contract)
    ledger = json.loads((root / "request-ledger.json").read_text())
    correlation = json.loads((root / "trace-correlation.json").read_text())
    full = sorted(set(terminal.TARGET_PATH) & set(contract["posture"]["expected"]["activeApplicationServices"]))
    for row, trace in zip(ledger["requests"], correlation["rows"]):
        if row["error"] is not None:  # stalled, then served: both steps 200, slow
            start = row["startedAtEpoch"]
            row["steps"] = [_step("add-to-cart", start, 200), _step("place-order", start + 0.05, 200)]
            row.update(status=200, bytes=100, error=None, endedAtEpoch=start + 14.0)
            trace.update(observedPathServices=full, observedTraceServices=full)
    ledger["completed"], ledger["failed"] = 600, 0
    _write(root / "request-ledger.json", ledger)
    _write(root / "trace-correlation.json", correlation)
    receipt = json.loads((root / "receipt.json").read_text())
    receipt["result"] = {"offered": 600, "completed": 600, "failed": 0}
    _write(root / "receipt.json", receipt)
    _recondition(root, contract)
    report = terminal.validate_cell(root, contract)
    phases = report["correlation"]["phases"]
    assert phases["during-fault"]["fullPath"] == phases["during-fault"]["requests"] > 0
