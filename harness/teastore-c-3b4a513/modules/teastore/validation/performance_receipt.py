#!/usr/bin/env python3
"""Validate denominators and provenance in a TeaStore performance receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FROZEN_SERVICE_REGEX = r'tools\.descartes\.teastore\.([a-zA-Z0-9_]+)\.'
FROZEN_SERVICE_MAP = {
    "store": "auth", "entities": "persistence", "registryclient": "registry",
}
CANONICAL_SERVICES = {
    "auth", "db", "image", "persistence", "rabbitmq", "recommender",
    "registry", "webui",
}
ATTRIBUTION_FIELDS = {
    "schemaVersion", "serviceRegex", "serviceMap", "canonicalHostAliases",
    "runtimeHostAliases", "explicitHostAliases", "effectiveHostAliases",
}
SPOOL_FIELDS = {
    "schemaVersion", "path", "deliveryCount", "uniqueBodyCount",
    "duplicateBodyCount", "rawBodyBytes", "spoolBytes", "artifactSha256",
    "terminalDigestSha256", "sealed", "complete", "blockers",
    "replayedEventCount", "replayedRecordFailures",
}
# The activation group(s) whose sensor opens each request trace. The canonical
# definition is TRACE_ROOT_ACTIVATION_GROUPS in
# modules/teastore/collectors/kieker_native.py; it is duplicated here because
# this validator is loaded standalone with no cross-module imports.
TRACE_ROOT_ACTIVATION_GROUPS = frozenset({"aspectj:webui"})


def _entry_point_woven(receipt: dict) -> bool:
    """True when the receipt's woven closure includes a trace-root sensor.

    Keyed on the embedded posture proof's closure membership, not the posture
    name, so a future placement whose name differs but whose closure omits the
    entry point is still classified correctly (F-ADH-064/065). A posture proof
    with an unreadable closure fails closed to woven, keeping the gate strict.
    Receipts that predate the embedded posture proof fall back to the frozen
    posture-name mapping (only 'full' weaves aspectj:webui).
    """
    proof = receipt.get("postureProof")
    if isinstance(proof, dict):
        groups = proof.get("closureGroups")
        if isinstance(groups, list) and all(isinstance(group, str) for group in groups):
            return bool(TRACE_ROOT_ACTIVATION_GROUPS & set(groups))
        return True
    return receipt.get("posture") not in {"selected", "none"}


def _attribution_blockers(receipt: dict, telemetry: dict) -> list[str]:
    blockers: list[str] = []
    collector = telemetry.get("collectorStats")
    if not isinstance(collector, dict):
        return ["schema-v2 receipt has no collector attribution binding"]
    configuration = collector.get("attribution_configuration")
    digest = collector.get("attribution_configuration_sha256")
    if not isinstance(configuration, dict) or set(configuration) != ATTRIBUTION_FIELDS:
        return ["collector attribution configuration fields differ"]
    canonical = {service: service for service in sorted(CANONICAL_SERVICES)}
    runtime = configuration.get("runtimeHostAliases")
    explicit = configuration.get("explicitHostAliases")
    effective = configuration.get("effectiveHostAliases")
    if (configuration.get("schemaVersion") != 1
            or configuration.get("serviceRegex") != FROZEN_SERVICE_REGEX
            or configuration.get("serviceMap") != FROZEN_SERVICE_MAP
            or configuration.get("canonicalHostAliases") != canonical
            or not isinstance(runtime, dict)
            or explicit != {}
            or not isinstance(effective, dict)):
        blockers.append("collector attribution configuration differs from frozen inputs")
    else:
        merged = dict(canonical)
        for alias, service in runtime.items():
            if (not isinstance(alias, str) or not alias
                    or not isinstance(service, str) or service not in CANONICAL_SERVICES
                    or (alias in merged and merged[alias] != service)):
                blockers.append("collector runtime host aliases are malformed or contradictory")
                break
            merged[alias] = service
        if effective != dict(sorted(merged.items())):
            blockers.append("collector effective host aliases do not reconcile")
    payload = json.dumps(
        configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    expected_digest = hashlib.sha256(payload).hexdigest()
    if not isinstance(digest, str) or digest != expected_digest:
        blockers.append("collector attribution configuration digest disagrees with content")
    source = receipt.get("source")
    if (not isinstance(source, dict)
            or source.get("collectorAttributionConfigurationSha256") != digest):
        blockers.append("receipt source does not bind the collector attribution configuration")
    return blockers


def _spool_blockers(receipt: dict, telemetry: dict) -> list[str]:
    blockers: list[str] = []
    summary = telemetry.get("spool")
    collector = telemetry.get("collectorStats")
    collector_summary = collector.get("spool") if isinstance(collector, dict) else None
    if not isinstance(summary, dict) or set(summary) != SPOOL_FIELDS:
        return ["telemetry durable spool fields differ"]
    integer_fields = (
        "deliveryCount", "uniqueBodyCount", "duplicateBodyCount", "rawBodyBytes",
        "spoolBytes", "replayedEventCount", "replayedRecordFailures",
    )
    if any(not isinstance(summary.get(field), int) or isinstance(summary.get(field), bool)
           or summary[field] < 0 for field in integer_fields):
        blockers.append("telemetry durable spool counters are invalid")
    if (summary.get("schemaVersion") != 1
            or summary.get("path") != "kieker-amqp.spool"
            or summary.get("sealed") is not True
            or summary.get("complete") is not True
            or summary.get("blockers") != []):
        blockers.append("telemetry durable spool is not terminally complete")
    for field in ("artifactSha256", "terminalDigestSha256"):
        if not isinstance(summary.get(field), str) or not SHA256_RE.fullmatch(summary[field]):
            blockers.append(f"telemetry durable spool {field} is invalid")
    messages = collector.get("messages") if isinstance(collector, dict) else None
    records_ok = collector.get("records_ok") if isinstance(collector, dict) else None
    records_bad = collector.get("records_bad") if isinstance(collector, dict) else None
    if (summary.get("deliveryCount") != messages
            or summary.get("uniqueBodyCount") != messages
            or summary.get("duplicateBodyCount") != 0
            or summary.get("replayedEventCount") != records_ok
            or summary.get("replayedRecordFailures") != records_bad):
        blockers.append("telemetry durable spool counters do not reconcile")
    if collector_summary != summary:
        blockers.append("telemetry durable spool differs from collector summary")
    source = receipt.get("source")
    if (not isinstance(source, dict)
            or source.get("spoolSha256") != summary.get("artifactSha256")):
        blockers.append("receipt source does not bind the durable spool artifact")
    return blockers


def validate(receipt: dict) -> dict:
    blockers: list[str] = []
    workload = receipt.get("workload", {})
    latency = receipt.get("latencyMs", {})
    queue = receipt.get("queue", {})
    source = receipt.get("source", {})
    resources = receipt.get("resources")
    telemetry = receipt.get("telemetry", {})
    analysis_kind = receipt.get("analysisKind")
    resource_use = receipt.get("resourceUse")
    schema_version = receipt.get("schemaVersion")
    evidence_label = source.get("evidenceLabel") if isinstance(source, dict) else None
    if evidence_label == "candidate-evidence" and schema_version != 2:
        blockers.append("candidate receipt schemaVersion is not 2")
    elif schema_version not in {None, 1, 2}:
        blockers.append("performance receipt schemaVersion is unsupported")
    legacy_resource_contract = analysis_kind is None and resource_use is None
    cost_contract = analysis_kind == "cost" and resource_use == "cost-proxy"
    effect_contract = analysis_kind == "effect" and resource_use == "diagnostic-only"
    if not (legacy_resource_contract or cost_contract or effect_contract):
        blockers.append("analysis/resource claim boundary is invalid")
    if effect_contract:
        if resources is not None:
            blockers.append("effect receipt exposes a resource cost projection")
        resources = {}
    elif not isinstance(resources, dict):
        blockers.append("cost receipt has no resource evidence")
        resources = {}
    required = {
        "workload": ("offered", "completed", "failed", "concurrency"),
        "latencyMs": ("count", "p50", "p95", "p99"),
        "telemetry": ("records", "bytes", "uniqueSignatures", "parseFailures"),
        "queue": ("purgedBefore", "messagesBefore", "messagesAfter", "exclusiveConsumer"),
    }
    if not effect_contract:
        required["resources"] = (
            "applicationCpuSeconds", "applicationMemoryPeakBytes", "hostCpuSeconds",
        )
    sections = {"workload": workload, "latencyMs": latency, "resources": resources,
                "telemetry": telemetry, "queue": queue}
    for name, fields in required.items():
        missing = [field for field in fields if field not in sections[name]]
        if missing:
            blockers.append(f"{name} missing denominators: {missing}")
    if latency.get("count") != workload.get("completed"):
        blockers.append("latency count differs from completed workload")
    enriched = all(field in workload for field in ("successful", "timedOut", "settled"))
    if enriched:
        if not (
            workload.get("completed") == workload.get("successful")
            and workload.get("successful", 0) + workload.get("failed", 0)
            + workload.get("timedOut", 0) == workload.get("settled")
            == workload.get("offered")
        ):
            blockers.append("terminal workload outcomes differ from offered denominator")
        if latency.get("denominator") != "successful-journeys":
            blockers.append("latency population differs from successful journeys")
        statistics = ("p50", "p95", "p99", "mean")
        if latency.get("count") == 0 and any(latency.get(field) is not None for field in statistics):
            blockers.append("empty successful latency statistics must be null")
        if latency.get("count", 0) > 0 and any(latency.get(field) is None for field in statistics):
            blockers.append("non-empty successful latency statistics are missing")
    if source.get("dirty") is not False:
        blockers.append("dirty or unreported framework source")
    if not queue.get("purgedBefore"):
        blockers.append("queue purge not proven")
    if not queue.get("exclusiveConsumer"):
        blockers.append("exclusive collector not proven")
    if receipt.get("posture") == "none" and telemetry.get("records") != 0:
        blockers.append("none posture emitted telemetry")
    parse_failures = telemetry.get("parseFailures")
    if (not isinstance(parse_failures, int) or isinstance(parse_failures, bool)
            or parse_failures < 0):
        blockers.append("telemetry parseFailures is not a non-negative integer")
    elif effect_contract:
        if parse_failures > 1:
            blockers.append("effect telemetry has more than one bad record")
    elif parse_failures != 0:
        blockers.append("cost/no-fault telemetry has parse failures")
    collector_stats = telemetry.get("collectorStats")
    if collector_stats is not None:
        if not isinstance(collector_stats, dict):
            blockers.append("telemetry collectorStats is not an object")
        else:
            if collector_stats.get("acknowledgement_mode") != "manual":
                blockers.append("collector AMQP acknowledgement mode was not manual")
            if collector_stats.get("runtime_host_map_loaded") is not True:
                blockers.append("collector runtime host/service map was not loaded")
            # F-ADH-084: identical formula to performance_campaign /
            # srv5_terminal / candidate_pilot. A rejected AMQP container is
            # netted out only against a receipt tolerance whose diagnostics
            # account for every rejection; absent or cost => zero netting.
            containers_bad = collector_stats.get("containers_bad") or 0
            tolerance = receipt.get("exposureTolerance")
            tolerated_containers = 0
            if isinstance(tolerance, dict):
                claimed = tolerance.get("toleratedContainerParseFailures", 0)
                described = tolerance.get("containerParseFailures")
                if not isinstance(claimed, int) or isinstance(claimed, bool) or claimed < 0:
                    blockers.append("container parse tolerance counter is invalid")
                elif claimed and not effect_contract:
                    blockers.append("cost evidence carries a nonzero container parse tolerance")
                elif claimed and (not isinstance(described, list)
                                  or len(described) != containers_bad
                                  or claimed > containers_bad):
                    blockers.append(
                        "container parse tolerance is not accounted for by its diagnostics")
                elif claimed:
                    tolerated_containers = claimed
            if containers_bad - tolerated_containers != 0:
                blockers.append("collector container parse failures are nonzero")
            correlation = collector_stats.get("correlation")
            if not isinstance(correlation, dict):
                blockers.append("collector correlation summary is missing")
            else:
                # A missing depth-0 parent is expected when the woven closure
                # omits the trace-root sensor (see _entry_point_woven); genuine
                # errors, and any missing root while the entry point is woven,
                # still block. See F-ADH-064.
                unwoven_root = correlation.get("eventsWithUnwovenRootParent") or 0
                # F-ADH-083: readiness-probe orphans are a counted subset of
                # the unwoven roots (identical formula to performance_campaign).
                probe_orphans = correlation.get("eventsWithProbeOrphanRoot") or 0
                if probe_orphans > unwoven_root:
                    blockers.append("collector probe-orphan-root count is inconsistent")
                    probe_orphans = 0
                if probe_orphans and not effect_contract:
                    blockers.append("collector readiness-probe orphans on cost evidence")
                raw_errors = correlation.get("eventsWithCorrelationErrors") or 0
                # F-ADH-080 twin: this validator never learned the F-ADH-074/076
                # exposure tolerance, so a valid fault cell stayed "blocked"
                # here. Identical bound to srv5_terminal: a tolerance may excuse
                # what was observed, never more; absent or cost => zero.
                tolerance = receipt.get("exposureTolerance")
                tolerated_events = 0
                if isinstance(tolerance, dict) and effect_contract and tolerance.get("applied") is True:
                    tolerated_events = tolerance.get("toleratedCorrelationErrorEvents")
                    if (not isinstance(tolerated_events, int) or isinstance(tolerated_events, bool)
                            or tolerated_events < 0
                            or tolerated_events > max(raw_errors - unwoven_root, 0)):
                        blockers.append("exposure tolerance exceeds the observed collector counters")
                        tolerated_events = 0
                elif isinstance(tolerance, dict) and not effect_contract and any(
                        isinstance(value, int) and not isinstance(value, bool) and value
                        for key, value in tolerance.items() if key.startswith("tolerated")):
                    blockers.append("cost evidence carries a nonzero exposure tolerance")
                genuine_errors = raw_errors - unwoven_root - tolerated_events
                if genuine_errors != 0:
                    blockers.append("collector native parent correlation errors are nonzero")
                if unwoven_root - probe_orphans != 0 and _entry_point_woven(receipt):
                    blockers.append(
                        "collector missing native trace roots while the entry point is woven")
                if correlation.get("eventsWithCorrelationWarnings") != 0:
                    blockers.append("collector native correlation/replay warnings are nonzero")
                if correlation.get("eventsWithServiceAttributionErrors") != 0:
                    blockers.append("collector service-attribution errors are nonzero")
                completeness = correlation.get("traceCompleteness")
                if (not isinstance(completeness, dict)
                        or completeness.get("tracesWithEoiGaps") != 0
                        or completeness.get("missingEoiCount") != 0):
                    blockers.append("collector native EOI completeness gaps are nonzero")
    if receipt.get("schemaVersion") == 2:
        blockers.extend(_spool_blockers(receipt, telemetry))
        blockers.extend(_attribution_blockers(receipt, telemetry))
    return {"verdict": "pass" if not blockers else "blocked", "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    report = validate(json.loads(args.receipt.read_text()))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
