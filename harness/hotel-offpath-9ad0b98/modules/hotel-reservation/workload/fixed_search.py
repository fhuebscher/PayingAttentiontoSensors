#!/usr/bin/env python3
"""Apply a deterministic open-loop workload to the audited /hotels path."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def validate(rate: float, duration: float, concurrency: int, timeout: float) -> None:
    if not math.isfinite(rate) or not 0 < rate <= 10000:
        raise ValueError("rate must be finite and in (0, 10000]")
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise ValueError("duration must be finite and in (0, 86400]")
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or not 1 <= concurrency <= 1024:
        raise ValueError("concurrency must be an integer from 1 through 1024")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if rate * duration > 1_000_000:
        raise ValueError("rate times duration may not exceed 1,000,000 offered requests")


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def search_url(base_url: str, sequence: int) -> str:
    # Deterministic dates and coordinates exercise frontend -> search ->
    # geo/rate plus availability/profile calls without mutating reservation data.
    in_day = 9 + sequence % 10
    out_day = in_day + 1
    latitude = 38.0235 + ((sequence % 21) - 10) / 1000
    longitude = -122.095 + ((sequence % 17) - 8) / 1000
    query = urllib.parse.urlencode({
        "inDate": f"2015-04-{in_day:02d}",
        "outDate": f"2015-04-{out_day:02d}",
        "lat": f"{latitude:.4f}",
        "lon": f"{longitude:.4f}",
        "locale": "en",
    })
    return base_url.rstrip("/") + "/hotels?" + query


def request(base_url: str, sequence: int, timeout: float, scheduled: float) -> dict:
    url = search_url(base_url, sequence)
    started_wall = time.time()
    started = time.monotonic()
    try:
        with urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(url, timeout=timeout) as response:
            body = response.read()
            error = None if response.status == 200 and body else "empty-or-non-200-response"
            return {
                "sequence": sequence, "scheduledAtEpoch": scheduled,
                "startedAtEpoch": started_wall, "endedAtEpoch": time.time(),
                "durationMs": (time.monotonic() - started) * 1000,
                "status": response.status, "bytes": len(body),
                "bodySha256": hashlib.sha256(body).hexdigest(), "error": error,
            }
    except (OSError, urllib.error.HTTPError) as exc:
        return {
            "sequence": sequence, "scheduledAtEpoch": scheduled,
            "startedAtEpoch": started_wall, "endedAtEpoch": time.time(),
            "durationMs": (time.monotonic() - started) * 1000,
            "status": getattr(exc, "code", None), "bytes": 0,
            "bodySha256": None, "error": f"{type(exc).__name__}: {exc}",
        }


def run(base_url: str, rate: float, duration: float, concurrency: int, timeout: float) -> dict:
    validate(rate, duration, concurrency, timeout)
    started_wall = time.time()
    started = time.monotonic()
    deadline = started + duration
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        sequence = 0
        while True:
            scheduled_mono = started + sequence / rate
            if scheduled_mono >= deadline:
                break
            delay = scheduled_mono - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            scheduled_wall = started_wall + sequence / rate
            futures.append(pool.submit(request, base_url, sequence, timeout, scheduled_wall))
            sequence += 1
        rows = [future.result() for future in futures]
    successful = [row["durationMs"] for row in rows if row["error"] is None]
    return {
        "schemaVersion": 1,
        "scenario": "hotel-search",
        "baseUrl": base_url,
        "schedule": {"kind": "fixed-open-loop", "requestsPerSecond": rate,
                     "durationSeconds": duration},
        "startedAtEpoch": started_wall, "endedAtEpoch": time.time(),
        "offered": len(rows), "completed": len(successful),
        "failed": len(rows) - len(successful), "concurrency": concurrency,
        "bytesReceived": sum(row["bytes"] for row in rows),
        "latencyMs": {
            "count": len(successful), "p50": percentile(successful, 0.50),
            "p95": percentile(successful, 0.95), "p99": percentile(successful, 0.99),
            "mean": round(statistics.fmean(successful), 3) if successful else None,
        },
        "requests": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:5000")
    parser.add_argument("--rate", required=True, type=float)
    parser.add_argument("--duration", required=True, type=float)
    parser.add_argument("--concurrency", default=8, type=int)
    parser.add_argument("--timeout", default=15.0, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        validate(args.rate, args.duration, args.concurrency, args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    result = run(args.base_url, args.rate, args.duration, args.concurrency, args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
