"""Shared trace-event schema for the STIG collectors.

The pipeline consumes trace events from four collectors that reach different
telemetry backends but MUST emit one common event schema so
`build_propagation_paths.py` can process any SUT unchanged:

  - collect_kieker_traces.py  (kieker_rabbitmq) — TeaStore, RabbitMQ binary scrape
  - collect_kieker_native.py  (kieker_native)   — TeaStore, Kieker 2.0.0 binary
                                                  deserializer (REAL trace ids)
  - collect_otlp_file.py      (otlp_file)       — OTel Demo, file-exporter JSONL
  - collect_jaeger_traces.py  (jaeger_api)      — HotelReservation, Jaeger HTTP API

REQUIRED_FIELDS are present on every event from every collector. OPTIONAL_FIELDS
are backend-dependent; when a collector cannot provide one it must be present
and explicitly None (never absent), so downstream code never has to distinguish
"missing key" from "collector cannot observe this". See
docs/COLLECTOR_UNIFICATION.md for the per-SUT field-provenance table.

Known asymmetries (documented, not bugs):
  - Kieker emits synthetic `scraped_<uuid>` trace_ids and cannot provide
    span_id / parent_span_id / status_code / duration_s (binary scrape, no
    span context). It DOES provide message_sha1 / signature_sha1 /
    signature_ordinal / args / full_signature.
  - OTLP / Jaeger provide REAL trace/span ids + parent_span_id + status +
    duration, but no Kieker message hashes.
  - Kieker-NATIVE (collect_kieker_native.py) provides REAL Kieker trace ids
    (`trace_id=str(traceId)`), eoi/ess-derived span_id / parent_span_id,
    duration_s from tin/tout, AND the Kieker message hashes. It additionally
    carries native-only optionals: kieker_trace_id, eoi, ess, tin, tout,
    session_id, hostname (None on every other collector). It shares the
    RabbitMQ queue with the scraper and must never run concurrently with it.

FILE BOUNDARY: collect_kieker_traces.py internals are owned by a separate
Kieker-native workstream and are NOT edited to use validate_events(); its
output is validated where collect_empirical_data.py receives it instead.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Present on every event, every collector.
REQUIRED_FIELDS = (
    "timestamp",           # float epoch seconds, event/span start
    "collector_timestamp",  # float epoch seconds, when the collector observed it
    "service",             # canonical service name (post trace_service_map)
    "operation",           # operation / method / span name
    "trace_id",            # real (OTLP/Jaeger) or synthetic scraped_<uuid> (Kieker)
    "source",              # provenance tag (kieker_binary_scrape|otlp_file_exporter|jaeger_api)
)

# Backend-dependent; filled with None when a collector cannot observe them.
OPTIONAL_FIELDS = (
    "span_id",            # OTLP/Jaeger only; None for Kieker
    "parent_span_id",     # OTLP/Jaeger only; None for Kieker
    "status_code",        # OTLP/Jaeger only (0=OK,2=ERROR); None for Kieker
    "duration_s",         # OTLP/Jaeger only; None for Kieker
    "args",               # Kieker only (arg type list); [] otherwise
    "full_signature",     # method signature (Kieker) or span name (OTLP/Jaeger)
    "message_sha1",       # Kieker only (RabbitMQ packet hash, replay detection)
    "signature_sha1",     # Kieker only
    "signature_ordinal",  # Kieker scraper only (position within a scraped packet)
    # kieker_native only (real deserialized Kieker records); None elsewhere.
    "kieker_trace_id",    # int, the raw Kieker traceId (trace_id == str() of it)
    "eoi",                # execution-order index within the trace
    "ess",                # execution-stack size (call depth)
    "tin",                # method entry timestamp (ns)
    "tout",               # method exit timestamp (ns)
    "session_id",         # Kieker sessionId
    "hostname",           # Kieker record hostname
)


def validate_events(events: List[Dict[str, Any]], collector_name: str) -> List[Dict[str, Any]]:
    """Assert every event has REQUIRED_FIELDS; fill absent OPTIONAL_FIELDS with None.

    Mutates and returns `events`. Raises ValueError (fail loud at collector exit)
    if a required field is missing, so a schema regression cannot silently reach
    the ground-truth builder.
    """
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            raise ValueError(
                f"{collector_name}: event {i} is not a dict ({type(ev).__name__})"
            )
        missing = [k for k in REQUIRED_FIELDS if k not in ev]
        if missing:
            raise ValueError(
                f"{collector_name}: event {i} missing required field(s) {missing}; "
                f"got keys {sorted(ev.keys())}"
            )
        for k in OPTIONAL_FIELDS:
            if k not in ev:
                ev[k] = None
    return events
