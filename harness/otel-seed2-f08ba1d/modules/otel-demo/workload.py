#!/usr/bin/env python3
"""Issue a fixed-rate HTTP workload and retain per-request timing receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 3)


def request(
    url: str,
    timeout: float,
    scheduled: float,
    request_token: str,
    original_trace_id: str,
) -> dict:
    started = time.time()
    span_id = hashlib.sha256(f"{request_token}\0span".encode()).hexdigest()[:16]
    traceparent = f"00-{original_trace_id}-{span_id}-01"
    request = urllib.request.Request(
        url,
        headers={
            "traceparent": traceparent,
            "x-obsplacement-request-token": request_token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return {"requestToken": request_token,
                    "originalTraceId": original_trace_id,
                    "traceparent": traceparent,
                    "scheduledAtEpoch": scheduled, "startedAtEpoch": started,
                    "endedAtEpoch": time.time(), "status": response.status,
                    "bytes": len(body), "error": None}
    except (OSError, urllib.error.HTTPError) as exc:
        return {"requestToken": request_token,
                "originalTraceId": original_trace_id,
                "traceparent": traceparent,
                "scheduledAtEpoch": scheduled, "startedAtEpoch": started,
                "endedAtEpoch": time.time(), "status": getattr(exc, "code", None),
                "bytes": 0, "error": f"{type(exc).__name__}: {exc}"}


def request_identity(namespace: str, sequence: int) -> tuple[str, str]:
    """Return deterministic opaque request and W3C trace identities."""

    if not namespace or any(character.isspace() for character in namespace):
        raise ValueError("token namespace must be non-empty and contain no whitespace")
    seed = f"{namespace}\0{sequence}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    return f"opq-{digest[:24]}", digest[:32]


def run(
    url: str,
    rate: float,
    duration: float,
    concurrency: int,
    timeout: float,
    token_namespace: str = "otel-demo-smoke",
) -> dict:
    started = time.time()
    deadline = started + duration
    futures = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        sequence = 0
        while True:
            scheduled = started + sequence / rate
            if scheduled >= deadline:
                break
            delay = scheduled - time.time()
            if delay > 0:
                time.sleep(delay)
            token, trace_id = request_identity(token_namespace, sequence)
            futures.append(
                pool.submit(request, url, timeout, scheduled, token, trace_id)
            )
            sequence += 1
        requests = [future.result() for future in futures]
    latencies = [(item["endedAtEpoch"] - item["startedAtEpoch"]) * 1000
                 for item in requests if item["error"] is None]
    identities = [(item["requestToken"], item["originalTraceId"]) for item in requests]
    return {"url": url, "ratePerSecond": rate, "durationSeconds": duration,
            "concurrency": concurrency, "startedAtEpoch": started,
            "endedAtEpoch": time.time(), "offered": len(requests),
            "completed": len(latencies), "failed": len(requests) - len(latencies),
            "tokenNamespace": token_namespace,
            "uniqueRequestTokens": len({token for token, _ in identities}),
            "uniqueOriginalTraceIds": len({trace for _, trace in identities}),
            "latencyMs": {"p50": percentile(latencies, .50),
                          "p95": percentile(latencies, .95),
                          "p99": percentile(latencies, .99)},
            "requests": requests}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8080/")
    parser.add_argument("--rate", type=float, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--token-namespace", default="otel-demo-smoke")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.rate) or args.rate <= 0 or args.duration <= 0 or args.concurrency <= 0:
        parser.error("rate, duration, and concurrency must be positive")
    if not args.token_namespace or any(character.isspace() for character in args.token_namespace):
        parser.error("token namespace must be non-empty and contain no whitespace")
    result = run(
        args.url,
        args.rate,
        args.duration,
        args.concurrency,
        args.timeout,
        args.token_namespace,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
