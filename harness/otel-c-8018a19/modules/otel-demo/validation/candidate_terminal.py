#!/usr/bin/env python3
"""Terminal validator for the exact OTel Demo 36-cell offpath (direction (c)) candidate campaign.

This is the route-bound terminal (``candidate_runtime.CONTROLLER_PATHS
["candidate-terminal"]``). It replays every retained cell against its
compiled contract and the campaign-level artifacts, and it refuses -- through
``candidate_runtime.refuse_unsupported`` -- while the frozen descriptor says any
required posture is not realized, or while the study epoch is not admitted by
the target controllers' ``ADMITTED_STUDY_EPOCHS`` tombstone, so before the v2
epoch is admitted it accepts nothing. The v1 UNSUPPORTED ledger itself is
validated by ``candidate_unsupported.py``
(``CONTROLLER_PATHS["unsupported-disposition"]``).

Findings OTEL-RUNTIME-009 and -010 (the earlier terminal accepted empty trace
correlations and a workload of the wrong shape) are closed here: correlation
is required per scored phase exactly as the descriptor's
``groundTruth.path.faultSpecificTruth`` states, and the request ledger must
carry the frozen URL, rate, concurrency, denominator, and window length.
Every float comparison carries a tolerance; every digest comparison is over
producer-and-validator-shared string formulas.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import re
import stat
import sys
from pathlib import Path
from typing import Any, Mapping, NoReturn


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_PATH = ROOT / "modules/otel-demo/execution/candidate_runtime.py"
EXPECTED_RUNS = 36
# Design order; the observed lattice must be strictly nested in exactly this order.
POSTURES = ("none", "selected", "async", "full")
# The synchronous checkout path (candidate_remote.TARGET_PATH, the runtime's
# SELECTED_CLOSURE); a journey's observed path is this set within its trace.
TARGET_PATH = [
    "frontendproxy", "frontend", "cartservice", "checkoutservice",
    "productcatalogservice", "currencyservice", "shippingservice", "quoteservice",
    "paymentservice", "emailservice", "flagd",
]
JOURNEY_STEPS = ("add-to-cart", "place-order")
# appliedMonotonic - barrierMonotonic must reproduce the recorded offset.
MONOTONIC_TOLERANCE_SECONDS = 1e-6
HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Requests scheduled this close to a fault edge are classified as during-fault
# rather than failing a phase requirement on a boundary race.
FAULT_EDGE_SLACK_SECONDS = 5
# The workload ends when the last request returns; requests time out after 15 s
# and the frontend readiness wait after a pause may add more, so the measured
# window may legitimately run past the frozen length but never fall short.
WINDOW_OVERRUN_TOLERANCE_SECONDS = 120
WINDOW_UNDERRUN_TOLERANCE_SECONDS = 2


class ValidationError(ValueError):
    pass


def _constant(value: str) -> NoReturn:
    raise ValidationError(f"non-finite JSON value: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValidationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _runtime():
    name = "otel_candidate_terminal_runtime"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, RUNTIME_PATH)
    if spec is None or spec.loader is None:
        raise ValidationError("runtime admission module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _remote():
    """The installed Compose controller: the producer's own parsers and tables."""
    name = "otel_candidate_terminal_remote"
    if name not in sys.modules:
        sys.modules[name] = _runtime()._controller_module("remote-compose-controller", name)
    return sys.modules[name]


def _traceparent_parts(value: Any) -> list[str] | None:
    parts = value.split("-") if isinstance(value, str) else []
    if (
        len(parts) != 4
        or [len(part) for part in parts] != [2, 32, 16, 2]
        or any(re.fullmatch(r"[0-9a-f]+", part) is None for part in parts)
    ):
        return None
    return parts


def _witness_traceparent_matches(witnessed: Any, injected: str, posture: str) -> bool:
    """Whether the proxy's logged traceparent carries the injected identity.

    ``none``: byte-equal. The proxy's tracer is off there (materialize.py
    renders envoy.no-tracing.tmpl.yaml), so any rewrite is a posture leak.
    ``selected``/``full``: Envoy's tracer is a W3C participant and replaces
    the parent-id with its own span id before the access log reads the header
    (run 1: 12 of 12 enabled cells, 7200 of 7200 rows, trace-id and flags
    preserved in every row). Version, trace-id and flags must be equal and the
    parent-id a well-formed non-zero span id.
    """
    if posture == "none":
        return witnessed == injected
    seen, sent = _traceparent_parts(witnessed), _traceparent_parts(injected)
    return (
        seen is not None and sent is not None
        and seen[0] == sent[0] and seen[1] == sent[1] and seen[3] == sent[3]
        and seen[2] != "0" * 16
    )


def _validate_carrier_coverage(cell_root: Path, started: float) -> dict[str, Any]:
    # Container output is retained as bytes (not guaranteed UTF-8); parsed with replacement, as the producer does.
    log = _file(cell_root / "otelcol.log", "collector carrier").decode("utf-8", errors="replace")
    coverage = _remote().collector_carrier_coverage(log, started)
    if not coverage["coversWindow"]:
        raise ValidationError(
            "collector carrier does not cover the measurement window: first retained record "
            f"{coverage['firstRecordEpoch']!r} is not before window start {started!r}"
        )
    return coverage


def _file(path: Path, where: str) -> bytes:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ValidationError(f"{where} is not a regular non-symlink file")
        if metadata.st_nlink != 1:
            raise ValidationError(f"{where} has an external hard link")
        payload = path.read_bytes()
        after = path.lstat()
        if (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValidationError(f"{where} changed while read")
        return payload
    except ValidationError:
        raise
    except OSError as exc:
        raise ValidationError(f"cannot read {where}: {exc}") from exc


def _json(path: Path, where: str) -> dict[str, Any]:
    try:
        value = json.loads(
            _file(path, where).decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except ValidationError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON in {where}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{where} is not an object")
    return value


def _exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        observed = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ValidationError(f"{where} keys differ: expected {sorted(keys)}, observed {observed}")
    return value


def _number(value: Any, where: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValidationError(f"{where} is not a finite non-negative number")
    return float(value)


def _manifest(cell_root: Path, required: list[str]) -> dict[str, str]:
    if required != sorted(required) or len(required) != len(set(required)):
        raise ValidationError("required artifact population is not unique and sorted")
    observed = {path.name for path in cell_root.iterdir()}
    if observed != set(required):
        raise ValidationError(
            f"cell artifact population differs: missing={sorted(set(required)-observed)}, extra={sorted(observed-set(required))}"
        )
    manifest = _json(cell_root / "content-manifest.json", "content manifest")
    _exact(manifest, {"schemaVersion", "algorithm", "files"}, "content manifest")
    if manifest["schemaVersion"] != 1 or isinstance(manifest["schemaVersion"], bool) or manifest["algorithm"] != "sha256":
        raise ValidationError("content manifest identity differs")
    expected_names = sorted(set(required) - {"content-manifest.json"})
    rows = manifest["files"]
    if not isinstance(rows, list) or [row.get("path") for row in rows if isinstance(row, dict)] != expected_names:
        raise ValidationError("content manifest file population differs")
    digests: dict[str, str] = {}
    for row in rows:
        _exact(row, {"path", "bytes", "sha256"}, "content manifest row")
        payload = _file(cell_root / row["path"], row["path"])
        digest = hashlib.sha256(payload).hexdigest()
        if type(row["bytes"]) is not int or row["bytes"] != len(payload) or row["sha256"] != digest:
            raise ValidationError(f"content manifest does not bind {row['path']}")
        digests[row["path"]] = digest
    return digests


def _validate_cpu_resources(
    resources: Mapping[str, Any],
    offered_requests: int,
    *,
    expected_claim_use: str,
) -> float:
    _exact(
        resources,
        {
            "schemaVersion", "counter", "before", "after",
            "applicationCpuSeconds", "offeredRequests",
            "cpuSecondsPerOfferedRequest", "claimUse",
        },
        "CPU resources",
    )
    counter = "docker-engine-cpu_stats.cpu_usage.total_usage"
    if (
        resources["schemaVersion"] != 1
        or isinstance(resources["schemaVersion"], bool)
        or resources["counter"] != counter
        or resources["claimUse"] != expected_claim_use
        or type(resources["offeredRequests"]) is not int
        or resources["offeredRequests"] != offered_requests
        or offered_requests <= 0
    ):
        raise ValidationError("CPU resource identity, claim use, or denominator differs")
    snapshots: list[dict[str, Any]] = []
    expected_services = _runtime().posture_catalog()["costApplicationServices"]
    for label in ("before", "after"):
        snapshot = _exact(
            resources[label],
            {
                "capturedAtStart", "capturedAtEnd", "counter", "services",
                "totalNanoseconds",
            },
            f"CPU {label} snapshot",
        )
        services = snapshot["services"]
        if (
            snapshot["counter"] != counter
            or not isinstance(snapshot["capturedAtStart"], str)
            or not snapshot["capturedAtStart"]
            or not isinstance(snapshot["capturedAtEnd"], str)
            or not snapshot["capturedAtEnd"]
            or not isinstance(services, dict)
            or list(services) != expected_services
        ):
            raise ValidationError(f"CPU {label} snapshot population differs")
        total = 0
        for service in expected_services:
            row = _exact(
                services[service],
                {"containerId", "totalUsageNanoseconds"},
                f"CPU {label} {service}",
            )
            if (
                not isinstance(row["containerId"], str)
                or not row["containerId"]
                or type(row["totalUsageNanoseconds"]) is not int
                or row["totalUsageNanoseconds"] < 0
            ):
                raise ValidationError(f"CPU {label} {service} counter differs")
            total += row["totalUsageNanoseconds"]
        if type(snapshot["totalNanoseconds"]) is not int or snapshot["totalNanoseconds"] != total:
            raise ValidationError(f"CPU {label} total is not the cumulative service sum")
        snapshots.append(snapshot)
    before, after = snapshots
    delta = 0
    for service in expected_services:
        first = before["services"][service]
        second = after["services"][service]
        if first["containerId"] != second["containerId"]:
            raise ValidationError("CPU snapshots do not refer to the same containers")
        service_delta = second["totalUsageNanoseconds"] - first["totalUsageNanoseconds"]
        if service_delta < 0:
            raise ValidationError("cumulative application CPU counter decreased")
        delta += service_delta
    if after["totalNanoseconds"] - before["totalNanoseconds"] != delta:
        raise ValidationError("aggregate CPU delta differs from service deltas")
    cpu_seconds = _number(resources["applicationCpuSeconds"], "application CPU seconds")
    if abs(cpu_seconds - delta / 1_000_000_000) > 1e-12:
        raise ValidationError("application CPU seconds do not replay from cumulative counters")
    per_request = _number(
        resources["cpuSecondsPerOfferedRequest"],
        "CPU seconds per offered request",
    )
    if abs(per_request - cpu_seconds / offered_requests) > 1e-12:
        raise ValidationError("CPU per-offered-request denominator differs")
    return cpu_seconds


def _validate_workload_identity(ledger: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[float, float]:
    """OTEL-RUNTIME-010: the ledger must be the frozen workload, not merely a ledger."""
    workload = contract["workload"]
    window = contract["window"]
    expected_url = f"http://127.0.0.1:{contract['compose']['ports']['frontend']}{workload['urlPath']}"
    if (
        ledger["url"] != expected_url
        or type(ledger["ratePerSecond"]) is not int
        or ledger["ratePerSecond"] != workload["requestsPerSecond"]
        or type(ledger["concurrency"]) is not int
        or ledger["concurrency"] != workload["concurrency"]
    ):
        raise ValidationError("request ledger workload identity (url, rate, concurrency) differs from the frozen contract")
    started = _number(ledger["startedAtEpoch"], "ledger startedAtEpoch")
    ended = _number(ledger["endedAtEpoch"], "ledger endedAtEpoch")
    duration = ended - started
    expected = window["measurementSeconds"]
    if duration < expected - WINDOW_UNDERRUN_TOLERANCE_SECONDS or duration > expected + WINDOW_OVERRUN_TOLERANCE_SECONDS:
        raise ValidationError(
            f"request ledger window {duration:.1f}s is not the frozen {expected}s measurement window"
        )
    return started, ended


def _validate_journey_steps(row: Mapping[str, Any]) -> None:
    """One offered journey: add-to-cart, then place-order only if the cart step
    returned 200; the row's error is None iff both steps returned 200, and the
    row's status/bytes are the last attempted step's."""
    steps = row.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 2:
        raise ValidationError("journey row does not carry one or two steps")
    for step, name in zip(steps, JOURNEY_STEPS):
        _exact(step, {"name", "status", "bytes", "startedAtEpoch", "endedAtEpoch", "error"}, "journey step")
        if step["name"] != name:
            raise ValidationError("journey steps are out of order")
        if (step["error"] is None) != (step["status"] == 200):
            raise ValidationError("journey step error does not replay from its status")
        if _number(step["endedAtEpoch"], "step end") < _number(step["startedAtEpoch"], "step start"):
            raise ValidationError("journey step ends before it starts")
    if len(steps) == 1 and steps[0]["error"] is None:
        raise ValidationError("a successful add-to-cart was not followed by place-order")
    complete = len(steps) == 2 and all(step["error"] is None for step in steps)
    if (row.get("error") is None) != complete:
        raise ValidationError("journey error does not replay from its steps")
    if row.get("status") != steps[-1]["status"] or row.get("bytes") != steps[-1]["bytes"]:
        raise ValidationError("journey status does not replay from its last step")


def _validate_intervention(intervention: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    """Fault ground truth for any declared scenario: identity, state transition
    by action, timing, and the [applied, reverting] detection window."""
    fault = contract["fault"]
    required_fault = {
        "scenario", "service", "targetContainerId", "targetImageId", "preState",
        "duringStateSamples", "postState", "actualOnsetMonotonicOffsetSeconds",
        "actualOffsetMonotonicOffsetSeconds", "barrierMonotonic", "appliedMonotonic",
        "revertingMonotonic", "appliedMonotonicOffsetSeconds", "revertingMonotonicOffsetSeconds",
        "duringRouteAvailable", "manifested", "recovered", "successful", "error",
    }
    _exact(intervention, required_fault, "intervention")
    if (
        intervention["scenario"] != fault["scenario"]
        or intervention["service"] != fault["service"]
        or intervention["manifested"] is not True
        or intervention["recovered"] is not True
        or intervention["successful"] is not True
        or intervention["error"] is not None
        or not intervention["duringStateSamples"]
        or intervention["targetContainerId"] is None
        or intervention["targetImageId"] is None
    ):
        raise ValidationError("fault manifestation and recovery ground truth differs")
    if intervention["targetImageId"] != contract["imageIds"][fault["service"]]:
        raise ValidationError(f"fault target image differs from the installed {fault['service']} image")
    pre, post, during = intervention["preState"], intervention["postState"], intervention["duringStateSamples"]
    if fault["action"] == "pause":
        during_ok = all(row.get("Running") and row.get("Paused") for row in during)
    elif fault["action"] == "stop":
        during_ok = all(not row.get("Running") for row in during)
    else:
        raise ValidationError(f"fault action {fault['action']!r} has no state predicate")
    if not pre.get("Running") or pre.get("Paused") or not during_ok or not post.get("Running") or post.get("Paused"):
        raise ValidationError("fault state transition differs")
    route = intervention["duringRouteAvailable"]
    if not isinstance(route, bool) or (fault["entryRouteDuringFault"] == "must-be-unavailable" and route):
        raise ValidationError("entry route during the fault differs from the scenario contract")
    onset = _number(intervention["actualOnsetMonotonicOffsetSeconds"], "fault onset")
    offset = _number(intervention["actualOffsetMonotonicOffsetSeconds"], "fault offset")
    applied = _number(intervention["appliedMonotonicOffsetSeconds"], "fault applied")
    reverting = _number(intervention["revertingMonotonicOffsetSeconds"], "fault reverting")
    barrier = _number(intervention["barrierMonotonic"], "barrier")
    if (
        abs(_number(intervention["appliedMonotonic"], "applied") - barrier - applied) > MONOTONIC_TOLERANCE_SECONDS
        or abs(_number(intervention["revertingMonotonic"], "reverting") - barrier - reverting) > MONOTONIC_TOLERANCE_SECONDS
        or not onset <= applied <= reverting <= offset
    ):
        raise ValidationError("fault detection window does not replay from the barrier")
    if onset < fault["onsetSeconds"] or reverting - onset < fault["holdSeconds"]:
        raise ValidationError("fault window was shorter than frozen timing")


def _phase(offset: float, intervention: Mapping[str, Any] | None) -> str:
    if intervention is None:
        return "pre-fault"
    onset = _number(intervention["actualOnsetMonotonicOffsetSeconds"], "fault onset")
    offset_end = _number(intervention["actualOffsetMonotonicOffsetSeconds"], "fault offset")
    if offset < onset - FAULT_EDGE_SLACK_SECONDS:
        return "pre-fault"
    if offset > offset_end + FAULT_EDGE_SLACK_SECONDS:
        return "post-readiness"
    return "during-fault"


def _validate_correlation(
    correlation: Mapping[str, Any],
    requests: list[dict[str, Any]],
    request_by_token: Mapping[str, Mapping[str, Any]],
    contract: Mapping[str, Any],
    intervention: Mapping[str, Any] | None,
    started: float,
    route_services: list[str] | None = None,
) -> dict[str, Any]:
    """OTEL-RUNTIME-009: correlation must be complete where the descriptor requires it.

    Enabled postures (selected, full) must carry the full target path for every
    successful request in a required phase (pre-fault, post-readiness); during
    the fault only structural rules apply (no cross-trace, path within target).
    The none posture must carry nothing. Coverage is recorded per phase rather
    than reduced to a single verdict.
    """
    _exact(correlation, {"schemaVersion", "correlation", "crossTraceAssembly", "observedUniqueTraceIds", "rows"}, "trace correlation")
    if correlation["schemaVersion"] != 1 or correlation["correlation"] != "injected-w3c-original-trace-id" or correlation["crossTraceAssembly"] is not False:
        raise ValidationError("trace correlation contract differs")
    rows = correlation["rows"]
    if not isinstance(rows, list) or len(rows) != len(requests):
        raise ValidationError("trace correlation population differs")
    posture = contract["posture"]["id"]
    active = set(contract["posture"]["expected"]["activeApplicationServices"])
    required_services = sorted(set(TARGET_PATH) & active)
    if route_services is not None:
        # A timed (traffic-sweep) cell's required path is its route, which the producer's clip must not hide.
        if not set(route_services) <= set(TARGET_PATH):
            raise ValidationError("route services are not all visible through the correlation clip")
        required_services = sorted(set(route_services) & active)
    enabled = posture != "none"
    truth = contract["fault"]
    coverage: dict[str, dict[str, int]] = {
        phase: {"requests": 0, "successful": 0, "fullPath": 0, "partialPath": 0, "noTrace": 0}
        for phase in ("pre-fault", "during-fault", "post-readiness")
    }
    seen_tokens: set[str] = set()
    unique_ids: set[str] = set()
    catalog_services = set(_runtime().posture_catalog()["applicationServices"])
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"requestToken", "injectedOriginalTraceId", "observedOriginalTraceIds", "observedPathServices", "observedTraceServices"}:
            raise ValidationError("trace correlation row shape differs")
        trace_services = row["observedTraceServices"]
        if (
            not isinstance(trace_services, list)
            or trace_services != sorted(set(trace_services))
            or not set(trace_services) <= catalog_services
            or row["observedPathServices"] != sorted(set(TARGET_PATH) & set(trace_services))
            or (trace_services and not row["observedOriginalTraceIds"])
        ):
            raise ValidationError("trace correlation trace services do not replay the path services")
        token = row["requestToken"]
        expected = request_by_token.get(token)
        if expected is None or row["injectedOriginalTraceId"] != expected["originalTraceId"] or token in seen_tokens:
            raise ValidationError("trace correlation input identity differs")
        seen_tokens.add(token)
        observed_ids = row["observedOriginalTraceIds"]
        services = row["observedPathServices"]
        if (
            observed_ids not in ([], [expected["originalTraceId"]])
            or not isinstance(services, list)
            or services != sorted(set(services))
            or not set(services) <= set(TARGET_PATH)
        ):
            raise ValidationError("trace correlation is many-to-one or cross-trace assembled")
        if not observed_ids and services:
            raise ValidationError("path services exist without their original trace")
        if not enabled and (observed_ids or services):
            raise ValidationError("none posture produced native trace correlation")
        if observed_ids:
            unique_ids.add(observed_ids[0])
        scheduled = _number(expected["scheduledAtEpoch"], "scheduledAtEpoch")
        phase = _phase(scheduled - started, intervention)
        bucket = coverage[phase]
        bucket["requests"] += 1
        status = expected.get("status")
        successful = expected.get("error") is None and isinstance(status, int) and 200 <= status < 300
        if successful:
            bucket["successful"] += 1
        if enabled and services == required_services and observed_ids:
            bucket["fullPath"] += 1
        elif observed_ids:
            bucket["partialPath"] += 1
        else:
            bucket["noTrace"] += 1
        if (
            route_services is None and enabled and successful and phase != "during-fault"
            and (services != required_services or not observed_ids)
        ):
            # A timed (traffic-sweep) cell is held to the recorded completeness share instead (review M1, user
            # 2026-10-03: blocked only below 99 %), replayed by validate_sweep_cell from trace-completeness.json.
            raise ValidationError(
                f"{phase} request {token} completed successfully without the full "
                f"{'/'.join(required_services)} correlation in the {posture} posture"
            )
        if not enabled and successful and phase != "during-fault" and status is None:
            raise ValidationError("successful request without status")
    if (
        type(correlation["observedUniqueTraceIds"]) is not int
        or correlation["observedUniqueTraceIds"] != len(unique_ids)
    ):
        raise ValidationError("observed unique trace count does not replay from the rows")
    if truth["scenario"] is None and coverage["during-fault"]["requests"] + coverage["post-readiness"]["requests"]:
        raise ValidationError("no-fault cell classified requests into fault phases")
    if truth["scenario"] is not None:
        if coverage["pre-fault"]["requests"] == 0 or coverage["during-fault"]["requests"] == 0 or coverage["post-readiness"]["requests"] == 0:
            raise ValidationError("effect cell does not cover pre-fault, during-fault, and post-readiness phases")
        # v1-v3 (150 s hold) also required some during-fault request to lose its
        # path in telemetry. At the offpath hold (15 s by default) a paused
        # frontend still accepts connections and serves the stalled requests
        # after unpause inside the 15 s step and Envoy route timeouts, so every
        # during-fault journey may legitimately complete with a full trace
        # (review 2026-10-02). Manifestation is therefore proven by the
        # independent receipt alone (paused state + the entry route probe
        # failing, _validate_intervention), as groundTruth.fault
        # .independentOfScoredTelemetry says; the during-fault coverage stays
        # reported, never required.
    return {"requiredPathServices": required_services, "phases": coverage}


def _validate_posture_proof(posture: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _runtime()
    catalog = runtime.posture_catalog()
    timed = "timing" in contract
    not_started = sorted(contract["timing"]["upstreamGeneratorsOff"]) if timed else []
    _exact(
        posture,
        {
            "schemaVersion", "posture", "expectedActiveApplicationServices",
            "observedSignalServices", "unexpectedSignalServices",
            "postureConfigSha256", "renderedComposeConfigSha256",
            "services", "loadedServices", "exact",
        } | ({"notStartedServices"} if timed else set()),
        "posture proof",
    )
    if timed and posture["notStartedServices"] != not_started:
        raise ValidationError("posture proof's not-started services differ from the contract's generators off")
    expected_active = contract["posture"]["expected"]["activeApplicationServices"]
    posture_id = contract["posture"]["id"]
    if (
        posture["schemaVersion"] != 2
        or posture["posture"] != posture_id
        or posture["expectedActiveApplicationServices"] != expected_active
        or not isinstance(posture["unexpectedSignalServices"], list)
        or not isinstance(posture["exact"], bool)
        or posture["postureConfigSha256"] != runtime.posture_config_sha256(contract)
        or HEX64.fullmatch(str(posture["renderedComposeConfigSha256"])) is None
    ):
        raise ValidationError("exact none/selected/full posture proof differs")
    recorded_signals = posture["observedSignalServices"]
    if not isinstance(recorded_signals, list) or recorded_signals != sorted(set(recorded_signals)):
        raise ValidationError("observed signal services are not a sorted set")
    # The observation is the recorded set of span service.names; the verdict is
    # recomputed from it. Span names map to catalog ids through the controller's
    # explicit table, which runtime.span_service_aliases() verifies against the
    # pinned Envoy config (fix 1a.2); the collector's own telemetry is excluded
    # in every posture (U3 for none; the 77002f6 override for selected/full).
    # The producer's recorded ``unexpected`` must
    # replay from the same observation under the same two rules -- which a
    # pre-fix producer's record also does, since it differs only by those two --
    # so an internally inconsistent proof still fails closed.
    remote = _remote()
    runtime.span_service_aliases()
    observed_signals = sorted({remote.catalog_service(name) for name in recorded_signals})
    excluded = {remote.COLLECTOR_SELF_SERVICE}
    unexpected = sorted(set(observed_signals) - set(expected_active) - excluded)
    recorded_unexpected = sorted(
        {remote.catalog_service(name) for name in posture["unexpectedSignalServices"]}
        - set(expected_active) - excluded
    )
    if recorded_unexpected != unexpected:
        raise ValidationError("posture proof's recorded unexpected services do not replay from its observation")
    if unexpected:
        raise ValidationError(f"exact none/selected/full posture proof differs: unexpected signal services {unexpected}")
    if posture_id == "none":
        # The collector's own telemetry is not application telemetry.
        if set(observed_signals) - excluded:
            raise ValidationError("none posture observed application telemetry")
    else:
        covered = contract["workload"]["routeServices"] if timed else TARGET_PATH
        if not set(observed_signals) - excluded <= set(expected_active) or not set(covered) <= set(observed_signals):
            raise ValidationError("enabled posture signals do not cover the target path within the active closure")
    if set(posture["services"]) != set(catalog["applicationServices"]) - set(not_started):
        raise ValidationError("posture proof does not cover every application service")
    loaded: list[str] = []
    for service, row in posture["services"].items():
        enabled = service in expected_active
        _exact(
            row,
            {
                "containerId", "imageId", "otelSdkDisabled", "tracesExporter",
                "metricsExporter", "logsExporter", "expectedActive", "instrumentation",
            },
            f"posture proof {service}",
        )
        if row["expectedActive"] is not enabled or row["imageId"] != contract["imageIds"][service]:
            raise ValidationError("posture service activation differs")
        if not isinstance(row["containerId"], str) or not row["containerId"]:
            raise ValidationError("posture service container identity is absent")
        if service != "frontendproxy":
            if row["otelSdkDisabled"] != ("false" if enabled else "true"):
                raise ValidationError("runtime SDK posture differs")
            if row["tracesExporter"] != ("otlp" if enabled else "none"):
                raise ValidationError("runtime exporter posture differs")
        expected = runtime.expected_service_control(catalog, posture_id, service)
        instrumentation = _exact(
            row["instrumentation"],
            {
                "mechanism", "expectedControl", "expectedLoadState", "probe",
                "observedControl", "observedLoadState", "evidence",
            },
            f"{service} instrumentation proof",
        )
        if (
            instrumentation["mechanism"] != expected["mechanism"]
            or instrumentation["expectedControl"] != expected["expectedControl"]
            or instrumentation["expectedLoadState"] != expected["expectedLoadState"]
            or instrumentation["probe"] != expected["probe"]
            or not isinstance(instrumentation["evidence"], dict)
        ):
            raise ValidationError(f"{service} instrumentation expectation differs from the catalog")
        observed_control = instrumentation["observedControl"]
        if expected["probe"] is None:
            if observed_control != "not-probed" or instrumentation["observedLoadState"] != "not-probed":
                raise ValidationError(f"{service} carries an observation without a catalog probe")
            continue
        if observed_control != expected["expectedControl"]:
            raise ValidationError(
                f"{service} instrumentation control observed {observed_control!r}, expected "
                f"{expected['expectedControl']!r} in the {posture_id} posture"
            )
        if instrumentation["observedLoadState"] != expected["expectedLoadState"]:
            raise ValidationError(f"{service} instrumentation load state differs")
        if observed_control == "enabled":
            loaded.append(service)
    if posture["loadedServices"] != sorted(loaded):
        raise ValidationError("loaded service set does not replay from the per-service observations")
    # Every probed control matched above, so the producer's ``exact`` must be
    # exactly "its own unexpected list is empty".
    if posture["exact"] is not (posture["unexpectedSignalServices"] == []):
        raise ValidationError("posture proof's recorded exact flag does not replay from its own fields")
    return {
        "posture": posture_id,
        "loadedServices": sorted(loaded),
        "observedSignalServices": list(observed_signals),
        "postureConfigSha256": posture["postureConfigSha256"],
        "renderedComposeConfigSha256": posture["renderedComposeConfigSha256"],
    }


def validate_cell(cell_root: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    if "timing" in contract:
        # Parameterised epochs only: a frozen-epoch cell is validated exactly as before.
        return validate_sweep_cell(cell_root, contract)
    root = Path(cell_root)
    required = contract["requiredArtifacts"]
    digests = _manifest(root, required)
    ledger = _json(root / "request-ledger.json", "request ledger")
    _exact(ledger, {"schemaVersion", "url", "tokenNamespace", "ratePerSecond", "concurrency", "startedAtEpoch", "endedAtEpoch", "offered", "completed", "failed", "requests"}, "request ledger")
    requests = ledger["requests"]
    if (
        ledger["schemaVersion"] != 1
        or ledger["tokenNamespace"] != contract["runId"]
        or ledger["offered"] != contract["workload"]["offeredRequests"]
        or ledger["completed"] + ledger["failed"] != ledger["offered"]
        or not isinstance(requests, list)
        or len(requests) != ledger["offered"]
    ):
        raise ValidationError("request ledger denominator or identity differs")
    started, ended = _validate_workload_identity(ledger, contract)
    tokens: list[str] = []
    trace_ids: list[str] = []
    for row in requests:
        if not isinstance(row, dict):
            raise ValidationError("request ledger row is not an object")
        token, trace_id, traceparent = row.get("requestToken"), row.get("originalTraceId"), row.get("traceparent")
        if not isinstance(token, str) or not isinstance(trace_id, str):
            raise ValidationError("request token/original trace identity differs")
        span_id = hashlib.sha256((token + "\0span").encode()).hexdigest()[:16]
        if traceparent != f"00-{trace_id}-{span_id}-01":
            raise ValidationError("request token/original trace identity differs")
        scheduled = _number(row.get("scheduledAtEpoch"), "scheduledAtEpoch")
        if scheduled < started - WINDOW_UNDERRUN_TOLERANCE_SECONDS or scheduled > ended + WINDOW_UNDERRUN_TOLERANCE_SECONDS:
            raise ValidationError("request scheduled outside the ledger window")
        tokens.append(token); trace_ids.append(trace_id)
    if len(set(tokens)) != len(tokens) or len(set(trace_ids)) != len(trace_ids):
        raise ValidationError("request identities are duplicate")
    if sum(row.get("error") is None for row in requests) != ledger["completed"]:
        raise ValidationError("completed request count does not replay from the rows")
    for row in requests:
        _validate_journey_steps(row)

    witness = _json(root / "application-witness.json", "application witness")
    _exact(witness, {"schemaVersion", "source", "offeredTokens", "witnessedTokens", "duplicateWitnessTokens", "unknownWitnessTokens", "rows"}, "application witness")
    witnessed = [row.get("request_token") for row in witness["rows"] if isinstance(row, dict)]
    if (
        witness["schemaVersion"] != 1
        or witness["source"] != "frontendproxy-json-access-log"
        or witness["offeredTokens"] != len(tokens)
        or witness["witnessedTokens"] != len(tokens)
        or witness["duplicateWitnessTokens"] != []
        or witness["unknownWitnessTokens"] != []
        or sorted(witnessed) != sorted(tokens)
    ):
        raise ValidationError("application witness does not establish the offered denominator")
    witness_by_token = {row["request_token"]: row for row in witness["rows"]}
    request_by_token = {row["requestToken"]: row for row in requests}
    for token, row in witness_by_token.items():
        if not _witness_traceparent_matches(
            row.get("traceparent"), request_by_token[token]["traceparent"], contract["posture"]["id"]
        ):
            raise ValidationError("application witness traceparent differs from injected identity")
    carrier = _validate_carrier_coverage(root, started)

    intervention: dict[str, Any] | None = None
    if contract["window"]["kind"] != "cost":
        intervention = _json(root / "intervention.json", "intervention")
    correlation_report = _validate_correlation(
        _json(root / "trace-correlation.json", "trace correlation"),
        requests, request_by_token, contract, intervention, started,
    )
    posture_report = _validate_posture_proof(_json(root / "posture-proof.json", "posture proof"), contract)

    telemetry = _json(root / "telemetry-bytes.json", "telemetry bytes")
    _exact(telemetry, {"schemaVersion", "captureTool", "filter", "emittedTelemetryBytes", "onWireTelemetryBytes", "retransmissionsExcludedFromEmitted", "pcapSha256"}, "telemetry bytes")
    emitted = _number(telemetry["emittedTelemetryBytes"], "emitted bytes")
    wire = _number(telemetry["onWireTelemetryBytes"], "wire bytes")
    if telemetry["schemaVersion"] != 1 or telemetry["captureTool"] != "tshark" or telemetry["filter"] != "tcp dst port 4317 or tcp dst port 4318" or telemetry["retransmissionsExcludedFromEmitted"] is not True or wire < emitted or telemetry["pcapSha256"] != digests["telemetry.pcap"]:
        raise ValidationError("emitted/on-wire telemetry measurement differs")

    if contract["window"]["kind"] == "cost":
        resources = _json(root / "resources.json", "resources")
        _validate_cpu_resources(
            resources, ledger["offered"], expected_claim_use="cost-proxy"
        )
        intervention_sha = None
        resources_sha = digests["resources.json"]
    else:
        effect_resources = _json(root / "effect-resources.json", "effect resources")
        _validate_cpu_resources(
            effect_resources,
            ledger["offered"],
            expected_claim_use="diagnostic-only",
        )
        assert intervention is not None
        _validate_intervention(intervention, contract)
        intervention_sha = digests["intervention.json"]
        resources_sha = digests["effect-resources.json"]

    cleanup = _json(root / "cell-cleanup.json", "cell cleanup")
    _exact(cleanup, {"schemaVersion", "project", "remainingResources", "ownedResourcesClean", "completedAt"}, "cell cleanup")
    if cleanup["schemaVersion"] != 1 or cleanup["project"] != contract["compose"]["project"] or cleanup["remainingResources"] != {"containers": [], "networks": [], "volumes": []} or cleanup["ownedResourcesClean"] is not True:
        raise ValidationError("owned resource cleanup differs")
    receipt = _json(root / "receipt.json", "cell receipt")
    _exact(receipt, {"schemaVersion", "kind", "target", "runId", "runKey", "state", "result", "error", "promotionAuthorized"}, "cell receipt")
    runtime = _runtime()
    if receipt["schemaVersion"] != 1 or receipt["kind"] != "otel-demo-candidate-cell-receipt-v1" or receipt["target"] != contract["target"] or receipt["runId"] != contract["runId"] or runtime.canonical_bytes(receipt["runKey"]) != runtime.canonical_bytes(contract["runKey"]) or receipt["state"] != "valid" or receipt["error"] is not None or receipt["promotionAuthorized"] is not False:
        raise ValidationError("cell receipt identity, state, or ceiling differs")
    if receipt["result"] != {"offered": ledger["offered"], "completed": ledger["completed"], "failed": ledger["failed"]}:
        raise ValidationError("cell receipt result does not replay from the request ledger")
    return {
        "runId": contract["runId"], "runKey": contract["runKey"], "state": "valid",
        "posture": posture_report,
        "correlation": correlation_report,
        "collectorCarrier": carrier,
        "manifestSha256": hashlib.sha256(_file(root / "content-manifest.json", "content manifest")).hexdigest(),
        "requestLedgerSha256": digests["request-ledger.json"],
        "applicationWitnessSha256": digests["application-witness.json"],
        "traceCorrelationSha256": digests["trace-correlation.json"],
        "postureProofSha256": digests["posture-proof.json"],
        "telemetryBytesSha256": digests["telemetry-bytes.json"],
        "resourceEvidenceSha256": resources_sha,
        "faultGroundTruthSha256": intervention_sha,
        "cleanupSha256": digests["cell-cleanup.json"],
        "promotionAuthorized": False,
    }

# --------------------------------------------------------------- traffic-sweep epoch (otel-traffic-sweep-v1)
SWEEP_LEDGER_KEYS = {
    "schemaVersion", "kind", "method", "url", "tokenNamespace", "ratePerSecond", "concurrency",
    "requestTimeoutSeconds", "durationSeconds", "barrierMonotonic", "barrierEpoch", "startedAtEpoch",
    "endedAtEpoch", "offered", "completed", "failed", "requests",
}
SWEEP_ROW_KEYS = {
    "requestToken", "originalTraceId", "traceparent", "scheduledOffsetSeconds", "scheduledAtEpoch",
    "startedAtEpoch", "endedAtEpoch", "startedMonotonic", "endedMonotonic", "status", "bytes", "error", "outcome",
}
SWEEP_INTERVENTION_KEYS = {
    "scenario", "service", "action", "targetContainerId", "targetImageId", "preState", "duringStateSamples",
    "postState", "scheduledOnsetSeconds", "scheduledHoldSeconds", "barrierMonotonic", "onsetSource",
    "startedMonotonic", "actualOnsetMonotonicOffsetSeconds", "appliedMonotonic", "appliedMonotonicOffsetSeconds",
    "revertingMonotonic", "revertingMonotonicOffsetSeconds", "revertedMonotonic",
    "actualOffsetMonotonicOffsetSeconds", "readyAtMonotonic", "duringRouteAvailable", "throttle", "probes",
    "manifested", "recovered", "successful", "error",
}
# A request may not start before its schedule (the worker sleeps until barrier + offset) by more than this.
SWEEP_START_TOLERANCE_SECONDS = 0.05
# The fault worker sleeps until the scheduled onset, so the pre-command stamp may not precede it by more than this.
SWEEP_ONSET_EARLY_TOLERANCE_SECONDS = 0.05
# Campaign B (otel-repeat-episodes-v1): H4 adds the freeze stamps to the receipt (the epoch's compiled timing names
# freezeStamps) and H10 removes the during-fault probe (duringFaultProbe False).
SWEEP_FREEZE_INTERVENTION_KEYS = SWEEP_INTERVENTION_KEYS | {"freeze"}
FREEZE_KEYS = {
    "schemaVersion", "kind", "action", "commandIssuedMonotonic", "commandReturnedMonotonic", "stateReadbackMonotonic",
    "commandIssuedOffsetSeconds", "commandReturnedOffsetSeconds", "stateReadbackOffsetSeconds", "dockerEventsFile",
    "stampCheck",
}
DOCKER_EVENTS_KEYS = {
    "schemaVersion", "kind", "runId", "service", "containerId", "clock", "stream", "raw", "events", "parseProblems",
    "verdict",
}
DOCKER_TIMESTAMP = re.compile(r"\| \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z ")


def _validate_sweep_ledger(ledger: Mapping[str, Any], contract: Mapping[str, Any], timing: Mapping[str, Any]) -> None:
    """The route ledger: the compiled rate, offered count, worker cap, timeout and window; one row per planned slot
    with the producer's identity, the planned offset, start/end on the fault receipt's clock, and its outcome."""
    _exact(ledger, SWEEP_LEDGER_KEYS, "route ledger")
    workload = contract["workload"]
    remote = _remote()
    expected_url = f"http://127.0.0.1:{contract['compose']['ports']['frontend']}{workload['urlPath']}"
    rate = float(timing["requestsPerSecond"])
    if (
        ledger["schemaVersion"] != 1 or ledger["kind"] != "otel-demo-route-ledger-v1"
        or ledger["method"] != workload["method"] or ledger["url"] != expected_url
        or ledger["tokenNamespace"] != contract["runId"]
        or ledger["ratePerSecond"] != rate or isinstance(ledger["ratePerSecond"], bool)
        or ledger["concurrency"] != timing["concurrency"]
        or ledger["requestTimeoutSeconds"] != float(timing["requestTimeoutSeconds"])
        or ledger["durationSeconds"] != float(timing["measurementSeconds"])
        or ledger["offered"] != timing["offered"] or ledger["offered"] != workload["offeredRequests"]
        or ledger["startedAtEpoch"] != ledger["barrierEpoch"]
        or not isinstance(ledger["requests"], list) or len(ledger["requests"]) != ledger["offered"]
        or ledger["completed"] + ledger["failed"] != ledger["offered"]
    ):
        raise ValidationError("route ledger identity, rate, denominator or worker cap differs from the compiled timing")
    started = _number(ledger["startedAtEpoch"], "ledger startedAtEpoch")
    duration = _number(ledger["endedAtEpoch"], "ledger endedAtEpoch") - started
    expected = float(timing["measurementSeconds"])
    if duration < expected - WINDOW_UNDERRUN_TOLERANCE_SECONDS or duration > expected + WINDOW_OVERRUN_TOLERANCE_SECONDS:
        raise ValidationError(f"route ledger window {duration:.1f}s is not the compiled {expected}s measurement window")
    barrier = _number(ledger["barrierMonotonic"], "ledger barrier")
    for sequence, row in enumerate(ledger["requests"]):
        _exact(row, SWEEP_ROW_KEYS, "route ledger row")
        token, trace_id, traceparent = remote.request_identity(contract["runId"], sequence)
        offset = sequence / rate
        if (
            row["requestToken"] != token or row["originalTraceId"] != trace_id or row["traceparent"] != traceparent
            or row["scheduledOffsetSeconds"] != offset
            or row["scheduledAtEpoch"] != ledger["barrierEpoch"] + offset
        ):
            raise ValidationError("route ledger row identity or schedule differs from the plan slot")
        start = _number(row["startedMonotonic"], "row start")
        if start < barrier + offset - SWEEP_START_TOLERANCE_SECONDS or _number(row["endedMonotonic"], "row end") < start:
            raise ValidationError("route ledger row starts before its slot or ends before it starts")
        if _number(row["endedAtEpoch"], "row end epoch") < _number(row["startedAtEpoch"], "row start epoch"):
            raise ValidationError("route ledger row ends before it starts")
        if (row["error"] is None) != (row["status"] == 200) or row["outcome"] != remote.request_outcome(row["status"], row["error"]):
            raise ValidationError("route ledger outcome does not replay from status and error")
    if sum(row["outcome"] == "ok" for row in ledger["requests"]) != ledger["completed"]:
        raise ValidationError("completed request count does not replay from the rows")


def _validate_sweep_intervention(
    intervention: Mapping[str, Any], contract: Mapping[str, Any], timing: Mapping[str, Any], barrier: float,
) -> dict[str, Any]:
    """Fault truth of a timed cell: identity, state transition by action, the pre-command onset on the
    compiled schedule, the hold, the shared barrier, and every stamped route probe."""
    h10 = timing.get("duringFaultProbe") is False
    freeze = timing.get("freezeStamps") is True
    _exact(intervention, SWEEP_FREEZE_INTERVENTION_KEYS if freeze else SWEEP_INTERVENTION_KEYS, "intervention")
    fault = contract["fault"]
    if (
        intervention["scenario"] != fault["scenario"] or intervention["service"] != fault["service"]
        or intervention["action"] != fault["action"]
        or intervention["manifested"] is not True or intervention["recovered"] is not True
        or intervention["successful"] is not True or intervention["error"] is not None
        or not intervention["duringStateSamples"]
        or intervention["targetContainerId"] is None
        or intervention["targetImageId"] != contract["imageIds"][fault["service"]]
        or intervention["onsetSource"] != "pre-command"
        or intervention["scheduledOnsetSeconds"] != timing["faultOnsetSeconds"]
        or intervention["scheduledHoldSeconds"] != timing["faultHoldSeconds"]
        or intervention["barrierMonotonic"] != barrier
    ):
        raise ValidationError("fault manifestation, recovery, schedule or barrier differs")
    pre, post, during = intervention["preState"], intervention["postState"], intervention["duringStateSamples"]
    if fault["action"] == "pause":
        during_ok = all(row.get("Running") and row.get("Paused") for row in during)
        if intervention["throttle"] is not None:
            raise ValidationError("a pause receipt carries a throttle record")
    elif fault["action"] == "cpu-throttle":
        during_ok = all(row.get("Running") and not row.get("Paused") for row in during)
        throttle = _exact(intervention["throttle"], {
            "originalNanoCpus", "appliedNanoCpus", "restoreNanoCpus", "hostNanoCpus", "duringNanoCpus", "postNanoCpus",
        }, "throttle record")
        original, host = throttle["originalNanoCpus"], throttle["hostNanoCpus"]
        if (
            type(original) is not int or original < 0 or type(host) is not int or host <= 0
            or throttle["appliedNanoCpus"] != fault["nanoCpus"]
            or throttle["duringNanoCpus"] != fault["nanoCpus"]
            or throttle["restoreNanoCpus"] != (original if original > 0 else host)
            or throttle["postNanoCpus"] != throttle["restoreNanoCpus"]
        ):
            raise ValidationError("CPU throttle was not applied and restored as declared")
    else:
        raise ValidationError(f"fault action {fault['action']!r} has no state predicate")
    if not pre.get("Running") or pre.get("Paused") or not during_ok or not post.get("Running") or post.get("Paused"):
        raise ValidationError("fault state transition differs")
    route = intervention["duringRouteAvailable"]
    if h10:
        # H10: the route is not probed during the fault, so there is no observation to hold to the scenario contract.
        if route is not None or fault["entryRouteDuringFault"] != "not-probed-h10":
            raise ValidationError("a cell with no during-fault probe (H10) records a route observation or a probed contract")
    elif not isinstance(route, bool) or (fault["entryRouteDuringFault"] == "must-be-unavailable" and route):
        raise ValidationError("entry route during the fault differs from the scenario contract")
    stamps = {}
    for absolute, relative in (
        ("startedMonotonic", "actualOnsetMonotonicOffsetSeconds"),
        ("appliedMonotonic", "appliedMonotonicOffsetSeconds"),
        ("revertingMonotonic", "revertingMonotonicOffsetSeconds"),
        ("revertedMonotonic", "actualOffsetMonotonicOffsetSeconds"),
    ):
        stamps[relative] = _number(intervention[relative], relative)
        if abs(_number(intervention[absolute], absolute) - barrier - stamps[relative]) > MONOTONIC_TOLERANCE_SECONDS:
            raise ValidationError("fault stamps do not replay from the shared barrier")
    onset, applied = stamps["actualOnsetMonotonicOffsetSeconds"], stamps["appliedMonotonicOffsetSeconds"]
    reverting, reverted = stamps["revertingMonotonicOffsetSeconds"], stamps["actualOffsetMonotonicOffsetSeconds"]
    ready = _number(intervention["readyAtMonotonic"], "readyAtMonotonic") - barrier
    if not onset <= applied <= reverting <= reverted <= ready:
        raise ValidationError("fault stamps are out of order")
    scheduled = float(timing["faultOnsetSeconds"])
    if onset < scheduled - SWEEP_ONSET_EARLY_TOLERANCE_SECONDS or reverting - onset < float(timing["faultHoldSeconds"]):
        raise ValidationError("fault onset precedes its schedule or the hold was shorter than compiled")
    probes = intervention["probes"]
    if not isinstance(probes, list):
        raise ValidationError("probe stamps are absent")
    during_probes = [row for row in probes if isinstance(row, dict) and row.get("phase") == "during-fault"]
    post_probes = [row for row in probes if isinstance(row, dict) and row.get("phase") == "post-revert"]
    if h10:
        if during_probes or len(post_probes) != len(probes) or not post_probes:
            raise ValidationError("a cell with no during-fault probe (H10) carries a probe that is not a post-revert readiness probe")
    elif len(during_probes) + len(post_probes) != len(probes) or len(during_probes) != 1 or not post_probes:
        raise ValidationError("probe stamps are not one during-fault probe and the post-revert readiness probes")
    for row in probes:
        _exact(row, {"phase", "startMonotonic", "endMonotonic", "available", "status"}, "probe stamp")
        start, end = _number(row["startMonotonic"], "probe start") - barrier, _number(row["endMonotonic"], "probe end") - barrier
        if not isinstance(row["available"], bool) or end < start:
            raise ValidationError("probe stamp is malformed")
        if h10 and end > onset and start < reverting:
            raise ValidationError("a probe was sent between the fault onset and the end of the hold (H10)")
        window = (applied, reverting) if row["phase"] == "during-fault" else (reverted, ready)
        if start < window[0] - MONOTONIC_TOLERANCE_SECONDS or start > window[1] + MONOTONIC_TOLERANCE_SECONDS:
            raise ValidationError("probe stamp lies outside its phase")
    if (not h10 and during_probes[0]["available"] is not route) or post_probes[-1]["available"] is not True:
        raise ValidationError("probe stamps do not replay the receipt's route observations")
    freeze_report = _validate_freeze(intervention, contract, barrier, onset, applied, reverting) if freeze else None
    return {
        "scenario": fault["scenario"], "onsetSeconds": onset, "holdSeconds": reverting - onset,
        "onsetLatenessSeconds": onset - scheduled, "probeCount": len(probes),
        "probeWindows": [[_number(row["startMonotonic"], "s") - barrier, _number(row["endMonotonic"], "e") - barrier] for row in probes],
        **({"freeze": freeze_report} if freeze_report is not None else {}),
    }


def _validate_freeze(
    intervention: Mapping[str, Any], contract: Mapping[str, Any], barrier: float, onset: float, applied: float,
    reverting: float,
) -> dict[str, Any]:
    """H4 (decision 69: recorded, never blocking): the freeze block's identity and the offsets it derives from the barrier
    must replay (integrity); whether the stamps are ordered and agree with the receipt is a record (``stampCheck``), which
    must replay byte for byte but may say ``contradictory``."""
    freeze = _exact(intervention["freeze"], FREEZE_KEYS, "freeze stamps")
    fault = contract["fault"]
    remote = _remote()
    runtime = _runtime()
    if (
        freeze["schemaVersion"] != 1 or freeze["kind"] != remote.FREEZE_KIND or freeze["action"] != fault["action"]
        or freeze["dockerEventsFile"] != (remote.DOCKER_EVENTS_FILE if fault["action"] == "pause" else None)
    ):
        raise ValidationError("freeze stamps identity differs")
    for key, relative in (
        ("commandIssuedMonotonic", "commandIssuedOffsetSeconds"), ("commandReturnedMonotonic", "commandReturnedOffsetSeconds"),
        ("stateReadbackMonotonic", "stateReadbackOffsetSeconds"),
    ):
        if abs(_number(freeze[key], key) - barrier - _number(freeze[relative], relative)) > MONOTONIC_TOLERANCE_SECONDS:
            raise ValidationError("freeze stamps do not replay from the shared barrier")
    if runtime.canonical_bytes(freeze["stampCheck"]) != runtime.canonical_bytes(remote.freeze_stamp_check(intervention)):
        raise ValidationError("freeze stamp check does not replay from the receipt")
    return {
        "action": freeze["action"], "commandIssuedOffsetSeconds": freeze["commandIssuedOffsetSeconds"],
        "commandReturnedOffsetSeconds": freeze["commandReturnedOffsetSeconds"],
        "stateReadbackOffsetSeconds": freeze["stateReadbackOffsetSeconds"],
        "stampStatus": freeze["stampCheck"]["status"], "stampFailures": freeze["stampCheck"]["failures"],
    }


def _validate_docker_events(
    record: Mapping[str, Any], contract: Mapping[str, Any], ledger: Mapping[str, Any], intervention: Mapping[str, Any],
) -> dict[str, Any]:
    """H4, pause cells (decision 69: recorded, never blocking): the retained Docker events replay from their own raw lines,
    the ledger's clock and the receipt, and the recorded verdict (ok, missing or contradictory, with its failures) replays
    byte for byte.  A tampered record is refused; a failed stream is not."""
    runtime, remote = _runtime(), _remote()
    _exact(record, DOCKER_EVENTS_KEYS, "docker events record")
    clock = record["clock"]
    if (
        record["schemaVersion"] != 1 or record["kind"] != remote.DOCKER_EVENTS_KIND or record["runId"] != contract["runId"]
        or record["service"] != contract["fault"]["service"]
        or record["containerId"] != intervention["targetContainerId"]
        or not isinstance(clock, dict) or set(clock) != {"barrierMonotonic", "barrierEpoch", "mapping", "stopPair"}
        or clock["barrierMonotonic"] != ledger["barrierMonotonic"] or clock["barrierEpoch"] != ledger["barrierEpoch"]
        or clock["mapping"] != remote.DOCKER_EVENTS_MAPPING
        or not isinstance(clock["stopPair"], dict) or set(clock["stopPair"]) != {"epoch", "monotonic"}
        or not isinstance(record["stream"], dict)
        or set(record["stream"]) != {"argv", "sinceEpoch", "exitedBeforeStop", "returnCode", "stderr", "error"}
        or not isinstance(record["raw"], list) or any(not isinstance(line, str) for line in record["raw"])
    ):
        raise ValidationError("docker events record identity, clock or stream differs")
    expected_argv = remote.docker_events_argv(contract["compose"]["project"], record["stream"]["sinceEpoch"])
    if record["stream"]["argv"] != expected_argv:
        raise ValidationError("docker events stream was not the declared filtered `docker events` command")
    events, problems = remote.parse_docker_events_lenient(record["raw"], clock)
    if runtime.canonical_bytes(record["events"]) != runtime.canonical_bytes(events) or (
        runtime.canonical_bytes(record["parseProblems"]) != runtime.canonical_bytes(problems)
    ):
        raise ValidationError("docker events do not replay from the retained raw lines")
    if any(event["action"] not in remote.DOCKER_EVENT_ACTIONS for event in events):
        raise ValidationError("docker events stream carries an action that was not asked for")
    verdict = remote.docker_events_verdict(events, record["stream"], intervention, problems)
    if runtime.canonical_bytes(record["verdict"]) != runtime.canonical_bytes(verdict):
        raise ValidationError("docker events verdict does not replay")
    # Decision 69: a missing or contradictory stream is recorded (status, failures, reasons), never a reason to refuse.
    return {
        "status": verdict["status"], "failures": verdict["failures"], "reasons": verdict["reasons"],
        "pauseOffsetSeconds": verdict["pauseOffsetSeconds"], "unpauseOffsetSeconds": verdict["unpauseOffsetSeconds"],
        "onsetIntervalSeconds": verdict["onsetIntervalSeconds"], "otherContainerEvents": verdict["otherContainerEvents"],
    }


def _validate_application_log(root: Path) -> dict[str, Any]:
    """Present, and carrying Docker's sub-second receive stamps (docker compose logs --timestamps)."""
    text = _file(root / "application.log", "application log").decode("utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    stamped = sum(1 for line in lines if DOCKER_TIMESTAMP.search(line))
    if stamped == 0:
        raise ValidationError("application log carries no Docker sub-second timestamps")
    return {"lines": len(lines), "stampedLines": stamped}


def _validate_upstream_generator(record: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    _exact(record, {"schemaVersion", "kind", "mechanism", "afterRemoval", "afterWindow"}, "upstream generator record")
    off = sorted(contract["timing"]["upstreamGeneratorsOff"])
    if record["schemaVersion"] != 1 or record["kind"] != "otel-demo-upstream-generator-off-v1":
        raise ValidationError("upstream generator record identity differs")
    for label in ("afterRemoval", "afterWindow"):
        state = _exact(record[label], {"observedAt", "services"}, f"upstream generator {label}")
        if sorted(state["services"]) != off or any(
            row != {"returnCode": 0, "containers": []} for row in state["services"].values()
        ):
            raise ValidationError(f"an upstream generator the cell turns off was not absent {label}")


def _validate_trace_completeness(
    record: Mapping[str, Any], contract: Mapping[str, Any], ledger: Mapping[str, Any],
    correlation: Mapping[str, Any], intervention: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Replay the target's completeness record from the retained ledger, correlation and receipt (byte equality),
    and require it to pass (protocol decision 25: fault-and-drain incomplete traces recorded, never blocking;
    elsewhere at most max(1, floor(1 % of successful requests)))."""
    runtime = _runtime()
    replayed = _remote().trace_completeness(contract, ledger, correlation, intervention)
    if runtime.canonical_bytes(record) != runtime.canonical_bytes(replayed):
        raise ValidationError("trace completeness record does not replay from the retained ledger and correlation")
    if record["valid"] is not True:
        raise ValidationError(
            f"trace completeness: {record['incomplete']} incomplete of {record['successful']} successful requests "
            f"outside the fault-and-drain window exceeds the allowance {record['allowance']}"
        )
    return {key: record[key] for key in (
        "windows", "blockingWindows", "faultAndDrainWindowSeconds", "recordedFaultEffectIncomplete",
        "successful", "incomplete", "allowance",
    )}


def _validate_container_health(record: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """The per-cell container-health guard: the recorded verdict must replay from its own two inspections, pass, and
    show every declared memory limit applied by inspect (user 2026-10-03, with option A)."""
    _exact(record, {
        "schemaVersion", "kind", "runId", "memoryLimitUpdates", "baselineAt", "baseline", "finalAt", "final",
        "inspectionError", "oomKilled", "restartedApplicationServices", "missingApplicationServices",
        "memoryLimitsNotInEffect", "reasons", "valid",
    }, "container health")
    if record["schemaVersion"] != 1 or record["kind"] != "otel-demo-sweep-container-health-v1" or record["runId"] != contract["runId"]:
        raise ValidationError("container health record identity differs")
    replayed = _remote().container_health_verdict(contract, record["baseline"], record["final"])
    if any(record[key] != value for key, value in replayed.items()):
        raise ValidationError("container health verdict does not replay from its inspections")
    limits = contract["timing"]["serviceMemoryLimitBytes"]
    updates = record["memoryLimitUpdates"]
    if (
        not isinstance(updates, list) or sorted(row.get("service") for row in updates) != sorted(limits)
        or any(row.get("after", {}).get("memory") != limits[row["service"]] for row in updates)
    ):
        raise ValidationError("declared memory limits were not applied as compiled")
    if record["valid"] is not True or record["inspectionError"] is not None:
        raise ValidationError("container health: " + ("; ".join(record["reasons"]) or "inspection failed"))
    return {"containers": len(record["final"]), "memoryLimitUpdates": updates}


def _validate_protocol_gates(
    record: Mapping[str, Any], contract: Mapping[str, Any], ledger: Mapping[str, Any],
    intervention: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Replay F1/G1/G2/G4 with the local vendored module over the retained ledger and receipt; the retained record
    must be byte-identical, and every blocking gate must pass."""
    runtime = _runtime()
    path = ROOT / runtime.CONTROLLER_PATHS["protocol-gates"]
    payload = _file(path, "vendored protocol gates")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != contract["installedControllerDigests"]["protocol-gates"]:
        raise ValidationError("local protocol gate module differs from the installed one")
    gates = _remote().load_protocol_gates(path, digest)
    replayed = _remote().protocol_gate_record(contract, ledger, intervention, gates, digest)
    if runtime.canonical_bytes(record) != runtime.canonical_bytes(replayed):
        raise ValidationError("protocol gate record does not replay from the retained ledger and receipt")
    if record["valid"] is not True or record["failedGates"]:
        raise ValidationError(f"protocol gate(s) {record['failedGates']} did not pass")
    return {"blocking": record["blocking"], "valid": True, "canFire": record["canFire"]}


def validate_sweep_cell(cell_root: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    root = Path(cell_root)
    runtime = _runtime()
    try:
        timing = runtime.sweep_cell_timing(contract)
    except runtime.GateError as exc:
        raise ValidationError(f"cell timing replay failed: {exc}") from exc
    digests = _manifest(root, contract["requiredArtifacts"])
    ledger = _json(root / "request-ledger.json", "request ledger")
    _validate_sweep_ledger(ledger, contract, timing)
    requests = ledger["requests"]
    tokens = [row["requestToken"] for row in requests]
    witness = _json(root / "application-witness.json", "application witness")
    _exact(witness, {"schemaVersion", "source", "offeredTokens", "witnessedTokens", "duplicateWitnessTokens", "unknownWitnessTokens", "rows"}, "application witness")
    witnessed = [row.get("request_token") for row in witness["rows"] if isinstance(row, dict)]
    if (
        witness["schemaVersion"] != 1
        or witness["source"] != "frontendproxy-json-access-log"
        or witness["offeredTokens"] != len(tokens)
        or witness["witnessedTokens"] != len(tokens)
        or witness["duplicateWitnessTokens"] != []
        or witness["unknownWitnessTokens"] != []
        or sorted(witnessed) != sorted(tokens)
    ):
        raise ValidationError("application witness does not establish the offered denominator")
    request_by_token = {row["requestToken"]: row for row in requests}
    for row in witness["rows"]:
        if not _witness_traceparent_matches(
            row.get("traceparent"), request_by_token[row["request_token"]]["traceparent"], contract["posture"]["id"]
        ):
            raise ValidationError("application witness traceparent differs from injected identity")
    started = _number(ledger["startedAtEpoch"], "ledger startedAtEpoch")
    carrier = _validate_carrier_coverage(root, started)
    intervention: dict[str, Any] | None = None
    fault_report = None
    if contract["fault"]["scenario"] is not None:
        intervention = _json(root / "intervention.json", "intervention")
        fault_report = _validate_sweep_intervention(intervention, contract, timing, ledger["barrierMonotonic"])
        if timing.get("freezeStamps") is True and contract["fault"]["action"] == "pause":
            fault_report["dockerEvents"] = _validate_docker_events(
                _json(root / "docker-events.json", "docker events"), contract, ledger, intervention,
            )
    correlation = _json(root / "trace-correlation.json", "trace correlation")
    correlation_report = _validate_correlation(
        correlation, requests, request_by_token, contract, intervention, started,
        route_services=list(contract["workload"]["routeServices"]),
    )
    correlation_report["traceCompleteness"] = _validate_trace_completeness(
        _json(root / "trace-completeness.json", "trace completeness"), contract, ledger, correlation, intervention,
    )
    posture_report = _validate_posture_proof(_json(root / "posture-proof.json", "posture proof"), contract)
    telemetry = _json(root / "telemetry-bytes.json", "telemetry bytes")
    _exact(telemetry, {"schemaVersion", "captureTool", "filter", "emittedTelemetryBytes", "onWireTelemetryBytes", "retransmissionsExcludedFromEmitted", "pcapSha256"}, "telemetry bytes")
    emitted = _number(telemetry["emittedTelemetryBytes"], "emitted bytes")
    wire = _number(telemetry["onWireTelemetryBytes"], "wire bytes")
    if telemetry["schemaVersion"] != 1 or telemetry["captureTool"] != "tshark" or telemetry["filter"] != "tcp dst port 4317 or tcp dst port 4318" or telemetry["retransmissionsExcludedFromEmitted"] is not True or wire < emitted or telemetry["pcapSha256"] != digests["telemetry.pcap"]:
        raise ValidationError("emitted/on-wire telemetry measurement differs")
    _validate_cpu_resources(_json(root / "resources.json", "resources"), ledger["offered"], expected_claim_use="diagnostic-only")
    application = _validate_application_log(root)
    _validate_upstream_generator(_json(root / "upstream-generator.json", "upstream generator"), contract)
    health = _validate_container_health(_json(root / "container-health.json", "container health"), contract)
    gates_report = _validate_protocol_gates(
        _json(root / "protocol-gates.json", "protocol gates"), contract, ledger, intervention,
    )
    cleanup = _json(root / "cell-cleanup.json", "cell cleanup")
    _exact(cleanup, {"schemaVersion", "project", "remainingResources", "ownedResourcesClean", "completedAt"}, "cell cleanup")
    if cleanup["schemaVersion"] != 1 or cleanup["project"] != contract["compose"]["project"] or cleanup["remainingResources"] != {"containers": [], "networks": [], "volumes": []} or cleanup["ownedResourcesClean"] is not True:
        raise ValidationError("owned resource cleanup differs")
    receipt = _json(root / "receipt.json", "cell receipt")
    _exact(receipt, {"schemaVersion", "kind", "target", "runId", "runKey", "state", "result", "error", "promotionAuthorized"}, "cell receipt")
    if receipt["schemaVersion"] != 1 or receipt["kind"] != "otel-demo-candidate-cell-receipt-v1" or receipt["target"] != contract["target"] or receipt["runId"] != contract["runId"] or runtime.canonical_bytes(receipt["runKey"]) != runtime.canonical_bytes(contract["runKey"]) or receipt["state"] != "valid" or receipt["error"] is not None or receipt["promotionAuthorized"] is not False:
        raise ValidationError("cell receipt identity, state, or ceiling differs")
    if receipt["result"] != {"offered": ledger["offered"], "completed": ledger["completed"], "failed": ledger["failed"]}:
        raise ValidationError("cell receipt result does not replay from the request ledger")
    return {
        "runId": contract["runId"], "runKey": contract["runKey"], "state": "valid",
        "posture": posture_report,
        "correlation": correlation_report,
        "collectorCarrier": carrier,
        "fault": fault_report,
        "applicationLog": application,
        "containerHealth": health,
        "protocolGates": gates_report,
        "manifestSha256": hashlib.sha256(_file(root / "content-manifest.json", "content manifest")).hexdigest(),
        "requestLedgerSha256": digests["request-ledger.json"],
        "applicationWitnessSha256": digests["application-witness.json"],
        "traceCorrelationSha256": digests["trace-correlation.json"],
        "traceCompletenessSha256": digests["trace-completeness.json"],
        "postureProofSha256": digests["posture-proof.json"],
        "telemetryBytesSha256": digests["telemetry-bytes.json"],
        "resourceEvidenceSha256": digests["resources.json"],
        "faultGroundTruthSha256": digests.get("intervention.json"),
        "protocolGatesSha256": digests["protocol-gates.json"],
        "cleanupSha256": digests["cell-cleanup.json"],
        "promotionAuthorized": False,
    }


def validate_single_posture(
    cell_reports: list[Mapping[str, Any]], catalog: Mapping[str, Any], not_started: list[str],
) -> dict[str, Any]:
    """A one-posture (full) epoch has no lattice: every cell must observe the catalog's full closure minus the
    services the epoch never starts, under one posture-config digest and one rendered Compose config."""
    rows = [report["posture"] for report in cell_reports]
    if not rows or any(row["posture"] != "full" for row in rows):
        raise ValidationError("a single-posture epoch holds a cell of another posture")
    loaded = {tuple(row["loadedServices"]) for row in rows}
    configs = {row["postureConfigSha256"] for row in rows}
    rendered = {row["renderedComposeConfigSha256"] for row in rows}
    if len(loaded) != 1 or len(configs) != 1 or len(rendered) != 1:
        raise ValidationError("full cells disagree on loaded services or posture configuration")
    expected_loaded = sorted(
        service for service in catalog["postures"]["full"]["activeApplicationServices"]
        if catalog["serviceInstrumentation"][service]["runtimeProbe"] is not None and service not in not_started
    )
    if list(next(iter(loaded))) != expected_loaded:
        raise ValidationError("full observed loaded services differ from the catalog closure")
    return {
        "rule": "single-posture-full-consistent", "notStartedServices": list(not_started),
        "postures": {"full": {
            "loadedServices": expected_loaded, "postureConfigSha256": next(iter(configs)),
            "renderedComposeConfigSha256": next(iter(rendered)), "cells": len(rows),
        }},
    }


def validate_lattice(cell_reports: list[Mapping[str, Any]], catalog: Mapping[str, Any]) -> dict[str, Any]:
    """none ⊂ selected ⊂ async ⊂ full over the *observed* loaded-service sets, and
    every cell of one posture must observe the same set, the same posture-config
    digest, and the same rendered Compose config."""
    by_posture: dict[str, list[Mapping[str, Any]]] = {posture: [] for posture in POSTURES}
    for report in cell_reports:
        by_posture[report["posture"]["posture"]].append(report["posture"])
    observed: dict[str, dict[str, Any]] = {}
    for posture, rows in by_posture.items():
        if not rows:
            raise ValidationError(f"no valid {posture} cell to build the posture lattice from")
        loaded = {tuple(row["loadedServices"]) for row in rows}
        configs = {row["postureConfigSha256"] for row in rows}
        rendered = {row["renderedComposeConfigSha256"] for row in rows}
        if len(loaded) != 1 or len(configs) != 1 or len(rendered) != 1:
            raise ValidationError(f"{posture} cells disagree on loaded services or posture configuration")
        expected_loaded = sorted(
            service for service in catalog["postures"][posture]["activeApplicationServices"]
            if catalog["serviceInstrumentation"][service]["runtimeProbe"] is not None
        )
        if list(next(iter(loaded))) != expected_loaded:
            raise ValidationError(f"{posture} observed loaded services differ from the catalog closure")
        observed[posture] = {
            "loadedServices": expected_loaded,
            "postureConfigSha256": next(iter(configs)),
            "renderedComposeConfigSha256": next(iter(rendered)),
            "cells": len(rows),
        }
    chain = [set(observed[p]["loadedServices"]) for p in POSTURES]
    if not all(lower < upper for lower, upper in zip(chain, chain[1:])):
        raise ValidationError(
            "observed posture lattice is not strictly nested " + " < ".join(POSTURES)
        )
    if len({observed[p]["postureConfigSha256"] for p in observed}) != len(POSTURES):
        raise ValidationError("posture configurations are not distinct across postures")
    return {"rule": "none-subset-selected-subset-async-subset-full", "postures": observed}


def _validate_workload_path_check(retained: Path, package: Any) -> dict[str, Any]:
    """The campaign-level selected-literal check must exist, pass, and replay
    byte-for-byte from the gating cell's own retained artifacts."""
    runtime = _runtime()
    contracts = [runtime.build_cell_contract(package, cell) for cell in package.bindings.cells]
    gates = [contract for contract in contracts if contract["workloadPathCheck"]["gatesCampaign"]]
    if len(gates) != 1:
        raise ValidationError("the plan does not name exactly one workload path check cell")
    contract = gates[0]
    cell_root = retained / contract["compiledArtifactRoot"]
    recorded = _json(retained / "workload-path-check.json", "workload path check")
    receipt = _json(cell_root / "receipt.json", "cell receipt")
    try:
        replayed = _remote().workload_path_check(contract, cell_root, receipt)
    except Exception as exc:  # noqa: BLE001 - any replay failure is a validation failure
        raise ValidationError(f"workload path check does not replay: {exc}") from exc
    if runtime.canonical_bytes(recorded) != runtime.canonical_bytes(replayed):
        raise ValidationError("workload path check does not replay from the gating cell")
    if recorded["verdict"] != "pass":
        raise ValidationError(
            "the first no-fault full cell's traced checkout paths differ from the selected literal: "
            f"{recorded['observedSynchronousSets']}"
        )
    return {
        "runId": recorded["runId"],
        "successfulJourneys": recorded["successfulJourneys"],
        "matchingJourneys": recorded["matchingJourneys"],
        "sha256": hashlib.sha256(_file(retained / "workload-path-check.json", "workload path check")).hexdigest(),
    }


def validate_campaign(campaign_root: Path, retained_root: Path, gate_package: Any) -> dict[str, Any]:
    runtime = _runtime()
    try:
        runtime.refuse_unsupported("terminal validation")
    except runtime.GateError as exc:
        raise ValidationError(str(exc)) from exc
    package = gate_package
    if package is None or getattr(package, "bindings", None) is None:
        raise ValidationError("terminal validation requires the authorized runtime package")
    retained = Path(retained_root)
    binding = package.gate_plan["binding"]
    if not retained.is_dir() or retained.is_symlink():
        raise ValidationError("retained campaign root is not a directory")
    reports: list[dict[str, Any]] = []
    for cell in package.bindings.cells:
        try:
            contract = runtime.build_cell_contract(package, cell)
        except runtime.GateError as exc:
            raise ValidationError(f"cell contract replay failed: {exc}") from exc
        cell_root = retained / contract["compiledArtifactRoot"]
        if not cell_root.is_dir() or cell_root.is_symlink():
            raise ValidationError(f"retained cell {contract['compiledArtifactRoot']} is absent")
        reports.append(validate_cell(cell_root, contract))
    sweep = runtime.is_sweep_epoch()
    expected_runs = runtime.RUN_COUNT if sweep else EXPECTED_RUNS
    if len(reports) != expected_runs or len({row["runId"] for row in reports}) != expected_runs:
        raise ValidationError(f"retained campaign is not the exact {expected_runs}-cell population")
    terminal = _json(retained / "remote-terminal.json", "remote terminal")
    _exact(terminal, {"schemaVersion", "kind", "target", "expectedCells", "attemptedCells", "validCells", "stopped", "promotionAuthorized"}, "remote terminal")
    if (
        terminal["schemaVersion"] != 1
        or terminal["kind"] != "otel-demo-candidate-remote-terminal-v1"
        or terminal["expectedCells"] != expected_runs
        or terminal["attemptedCells"] != expected_runs
        or terminal["validCells"] != expected_runs
        or terminal["stopped"] is not False
        or terminal["promotionAuthorized"] is not False
        or terminal["target"].get("host") != binding["target"]["host"]
    ):
        raise ValidationError(f"remote terminal does not report a complete valid {expected_runs}-cell campaign")
    release = _json(retained / "host-release.json", "host release")
    if (
        release.get("kind") != "srv6-otel-host-release-v1"
        or release.get("campaignId") != binding["campaignId"]
        or release.get("remainingOwnedResources") != {"containers": [], "networks": [], "volumes": []}
        or release.get("readyForSuccessorAfterControllerExit") is not True
        or release.get("foreignResourcesTouched") != []
    ):
        raise ValidationError("host release does not leave srv6 clean for the successor")
    if sweep:
        # The sweep has no selected-literal gate cell and one posture: its route path is checked per cell.
        path_check = None
        not_started = sorted(package.bindings.cells[0]["timing"]["upstreamGeneratorsOff"])
        lattice = validate_single_posture(reports, runtime.posture_catalog(), not_started)
    else:
        path_check = _validate_workload_path_check(retained, package)
        lattice = validate_lattice(reports, runtime.posture_catalog())
    return {
        "schemaVersion": 2,
        "kind": "otel-demo-candidate-terminal-validation-v2",
        "studyEpoch": runtime.STUDY_EPOCH,
        "campaignId": binding["campaignId"],
        "expectedCells": expected_runs,
        "validCells": len(reports),
        "cells": reports,
        "postureLattice": lattice,
        "remoteTerminalSha256": hashlib.sha256(_file(retained / "remote-terminal.json", "remote terminal")).hexdigest(),
        "hostReleaseSha256": hashlib.sha256(_file(retained / "host-release.json", "host release")).hexdigest(),
        "workloadPathCheck": path_check,
        "verdict": "pass",
        "maximumEvidenceLabel": runtime.EVIDENCE_LABEL,
        "canonical": False,
        "promotionAuthorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_root", type=Path)
    parser.add_argument("retained_root", type=Path)
    parser.add_argument("--gate-plan", type=Path, required=True)
    parser.add_argument("--gate-setup", type=Path, required=True)
    parser.add_argument("--setup-receipt", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--gate-run", type=Path, required=True)
    args = parser.parse_args(argv)
    runtime = _runtime()
    package = runtime.replay_runtime_from_files(
        args.campaign_root, args.gate_plan, args.gate_setup, args.setup_receipt,
        args.readiness, args.gate_run,
    )
    report = validate_campaign(args.campaign_root, args.retained_root, package)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXPECTED_RUNS", "TARGET_PATH", "ValidationError", "validate_campaign",
    "validate_cell", "validate_lattice",
]
