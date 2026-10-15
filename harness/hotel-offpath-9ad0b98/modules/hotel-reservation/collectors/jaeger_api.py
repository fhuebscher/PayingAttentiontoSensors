#!/usr/bin/env python3
"""Collect bounded raw Jaeger traces while retaining the exact query window."""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path


def validate_window(start_us: int, end_us: int, limit: int) -> None:
    if (not isinstance(start_us, int) or isinstance(start_us, bool) or
            not isinstance(end_us, int) or isinstance(end_us, bool) or
            start_us <= 0 or end_us <= start_us):
        raise ValueError("start/end must be positive integer microseconds with end after start")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000:
        raise ValueError("limit must be an integer from 1 through 10000")


def collect(base_url: str, services: list[str], start_us: int, end_us: int,
            limit: int = 10000, timeout: float = 30.0) -> dict:
    validate_window(start_us, end_us, limit)
    if not services or len(services) != len(set(services)) or any(not service.strip() for service in services):
        raise ValueError("services must be a non-empty unique list")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    queries = []
    for service in services:
        parameters = urllib.parse.urlencode({"service": service, "start": start_us,
                                             "end": end_us, "limit": limit})
        url = base_url.rstrip("/") + "/api/traces?" + parameters
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(url, timeout=timeout) as response:
            payload = json.loads(response.read())
        if not isinstance(payload.get("data"), list):
            raise RuntimeError(f"Jaeger response for {service!r} has no data list")
        if payload.get("errors"):
            raise RuntimeError(f"Jaeger response for {service!r} contains errors: {payload['errors']}")
        queries.append({"service": service, "url": url, "traceCount": len(payload["data"]),
                        "response": payload})
    return {
        "schemaVersion": 1, "collector": "jaeger-query-api-v1",
        "collectedAtEpoch": time.time(), "window": {"startUs": start_us, "endUs": end_us},
        "limitPerService": limit, "queries": queries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:16686")
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--start-us", required=True, type=int)
    parser.add_argument("--end-us", required=True, type=int)
    parser.add_argument("--limit", default=10000, type=int)
    parser.add_argument("--timeout", default=30.0, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = collect(args.base_url, args.service or ["frontend"], args.start_us,
                         args.end_us, args.limit, args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
