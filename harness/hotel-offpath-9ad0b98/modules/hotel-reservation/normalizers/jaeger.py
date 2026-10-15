#!/usr/bin/env python3
"""Normalize Jaeger v1 responses without losing native trace/span identity."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def _tags(items: list[dict] | None) -> dict:
    return {str(item.get("key")): item.get("value") for item in items or [] if item.get("key")}


def normalize(raw: dict) -> dict:
    if raw.get("schemaVersion") != 1 or raw.get("collector") != "jaeger-query-api-v1":
        raise ValueError("unsupported raw Jaeger envelope")
    traces: dict[str, dict] = {}
    duplicate_query_spans = 0
    for query in raw.get("queries", []):
        response = query.get("response", {})
        for trace in response.get("data", []):
            trace_id = trace.get("traceID")
            if not trace_id:
                raise ValueError("trace lacks native traceID")
            destination = traces.setdefault(trace_id, {"processes": {}, "spans": {}})
            destination["processes"].update(trace.get("processes", {}))
            for span in trace.get("spans", []):
                span_id = span.get("spanID")
                if not span_id:
                    raise ValueError(f"trace {trace_id} contains span without native spanID")
                key = (trace_id, span_id)
                if span_id in destination["spans"]:
                    duplicate_query_spans += 1
                    if destination["spans"][span_id] != span:
                        raise ValueError(f"conflicting duplicate span {key}")
                else:
                    destination["spans"][span_id] = span

    events = []
    for trace_id, trace in sorted(traces.items()):
        spans = trace["spans"]
        process_services = {key: value.get("serviceName") for key, value in trace["processes"].items()}
        for span_id, span in sorted(spans.items(), key=lambda item: (item[1].get("startTime", 0), item[0])):
            references = [reference for reference in span.get("references", [])
                          if reference.get("refType") == "CHILD_OF"]
            parent_id = references[0].get("spanID") if references else None
            parent = spans.get(parent_id) if parent_id else None
            service = process_services.get(span.get("processID"))
            parent_service = process_services.get(parent.get("processID")) if parent else None
            operation = span.get("operationName")
            signature = hashlib.sha256(
                f"{service}\0{operation}\0{parent_service or ''}".encode()).hexdigest()
            events.append({
                "traceId": trace_id, "spanId": span_id, "parentSpanId": parent_id,
                "service": service, "parentService": parent_service,
                "operation": operation, "startTimeUs": span.get("startTime"),
                "durationUs": span.get("duration"), "tags": _tags(span.get("tags")),
                "signatureSha256": signature,
            })
    signatures = Counter(event["signatureSha256"] for event in events)
    top = signatures.most_common(1)[0][1] if signatures else 0
    return {
        "schemaVersion": 1, "normalizer": "hotel-reservation-jaeger-v1",
        "sourceWindow": raw["window"], "rawQueryTraceCount": sum(
            query.get("traceCount", 0) for query in raw.get("queries", [])),
        "uniqueTraceCount": len(traces), "spanCount": len(events),
        "duplicateQuerySpansRemoved": duplicate_query_spans,
        "queryLimitReached": any(query.get("traceCount", 0) >= raw.get("limitPerService", 10000)
                                  for query in raw.get("queries", [])),
        "uniqueSpanSignatureCount": len(signatures),
        "topSignatureConcentration": top / len(events) if events else None,
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = normalize(json.loads(args.raw.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
