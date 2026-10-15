#!/usr/bin/env python3
"""Generate the synthetic OTel Demo cells that test analysis v2.2's OTel reader, with the OTel harness's own cell
writer: candidate_remote.run_cell (run_sweep_cell) at harness commit 6e37ec2, driven by the harness's test fake
(tests/test_otel_traffic_sweep.py FakeTarget / FakeTime / _execute, a compressed clock) and accepted by the harness's
terminal (validation/candidate_terminal.validate_cell). Not a test and not evidence; regenerate, never hand-edit.

    W=../observability-placement-runtime-otel-protocol
    $W/.venv/bin/python -B tests/fixtures/sweep_v22/generate_otel.py $W <scratch dir>

The harness fake's collector log carries only `service.name` / `Trace ID` pairs (all the harness's own correlation
reads). This generator subclasses it so that the collector log also carries complete span and metric records in the
collector 0.108.0 debug-exporter layout (the layout of the harness's fixture
tests/fixtures/online_boutique/otelcol-0.108.0-selected.log) for every request the fake served: an Envoy
(`frontend-proxy`) ingress span parented by the client's injected span, and, when the route answered, a frontend and a
productcatalogservice span; probes (no traceparent) get a fresh trace; productcatalogservice and frontend export one
gauge every 10 s (the throttled service's value rises while it is throttled; a paused frontend exports nothing). The
application log adds, per request, Envoy's access-log line (request token, rewritten traceparent, 200 or 504) and a
frontend line, each with a Docker receive stamp. Writes tests/fixtures/sweep_v22/otel/campaign/runs/... (no-fault,
frontend-pause, productcatalog-cpu-throttle at 1 request/s) and tests/fixtures/sweep_v22/otel/MANIFEST.json. The
harness code is `git archive` of the pinned commit (tests/fixtures/sweep_v22/_pinned.py), not the worktree's HEAD.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PINNED = "6e37ec2"
HERE = Path(__file__).resolve().parent
OUT = HERE / "otel"
CELLS = (("no-fault-calibration", 1.0), ("frontend-pause-effect", 1.0), ("productcatalog-cpu-throttle-effect", 1.0))
EXPORT_SECONDS = 10.0


class Factory:
    def __init__(self, base):
        self.base = Path(base)

    def mktemp(self, name):
        return Path(tempfile.mkdtemp(prefix=name + "-", dir=self.base))


def _hex(text, n):
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def _otel_time(epoch):
    whole = int(epoch)
    return datetime.fromtimestamp(whole, timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + \
        ".%09d +0000 UTC" % int(round((epoch - whole) * 1e9))


def _zap(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _docker(epoch):
    whole = int(epoch)
    return datetime.fromtimestamp(whole, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + \
        ".%09dZ" % int(round((epoch - whole) * 1e9))


def rich_target(H):
    class RichTarget(H.FakeTarget):
        """The harness fake, plus complete collector records and application lines (module docstring)."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.calls, self.throttle = [], []

        def http_get(self, url, headers, timeout):
            t0 = self.clock.time()
            status, size, error = super().http_get(url, headers, timeout)
            with self.lock:
                self.calls.append((headers.get("x-obsplacement-request-token"), headers.get("traceparent"), t0,
                                   self.clock.time(), status == 200))
            return status, size, error

        def command(self, argv, **kw):
            argv_s = [str(x) for x in argv]
            if argv_s[:2] == ["docker", "update"] and "--cpus" in argv_s:
                self.throttle.append((self.clock.time(), argv_s[argv_s.index("--cpus") + 1]))
            if argv_s[:2] == ["docker", "compose"] and argv_s[10:11] in (["pause"], ["unpause"]):
                self.throttle.append((self.clock.time(), argv_s[10]))
            return super().command(argv, **kw)

        def _span(self, out, svc, trace, parent, sid, name, start, end, error):
            out += ["otelcol-1  | %s\tinfo\tTracesExporter\t{\"kind\": \"exporter\", \"data_type\": \"traces\", "
                    "\"name\": \"debug\", \"resource spans\": 1, \"spans\": 1}" % _zap(end),
                    "otelcol-1  | %s\tinfo\tResourceSpans #0" % _zap(end), "otelcol-1  | Resource SchemaURL: ",
                    "otelcol-1  | Resource attributes:", "otelcol-1  |      -> service.name: Str(%s)" % svc,
                    "otelcol-1  | ScopeSpans #0", "otelcol-1  | ScopeSpans SchemaURL: ",
                    "otelcol-1  | InstrumentationScope fixture 0.0.0", "otelcol-1  | Span #0",
                    "otelcol-1  |     Trace ID       : %s" % trace, "otelcol-1  |     Parent ID      : %s" % (parent or ""),
                    "otelcol-1  |     ID             : %s" % sid, "otelcol-1  |     Name           : %s" % name,
                    "otelcol-1  |     Kind           : Server",
                    "otelcol-1  |     Start time     : %s" % _otel_time(start),
                    "otelcol-1  |     End time       : %s" % _otel_time(end),
                    "otelcol-1  |     Status code    : %s" % ("Error" if error else "Unset"),
                    "otelcol-1  |     Status message : ", "otelcol-1  | Attributes:",
                    "otelcol-1  |      -> http.response.status_code: Int(%d)" % (504 if error else 200)]

        def _gauge(self, out, svc, name, at, value):
            out += ["otelcol-1  | %s\tinfo\tMetricsExporter\t{\"kind\": \"exporter\", \"data_type\": \"metrics\", "
                    "\"name\": \"debug\", \"resource metrics\": 1, \"metrics\": 1, \"data points\": 1}" % _zap(at),
                    "otelcol-1  | %s\tinfo\tResourceMetrics #0" % _zap(at), "otelcol-1  | Resource SchemaURL: ",
                    "otelcol-1  | Resource attributes:", "otelcol-1  |      -> service.name: Str(%s)" % svc,
                    "otelcol-1  | ScopeMetrics #0", "otelcol-1  | ScopeMetrics SchemaURL: ",
                    "otelcol-1  | InstrumentationScope fixture 0.0.0", "otelcol-1  | Metric #0", "otelcol-1  | Descriptor:",
                    "otelcol-1  |      -> Name: %s" % name, "otelcol-1  |      -> Description: fixture gauge",
                    "otelcol-1  |      -> Unit: 1", "otelcol-1  |      -> DataType: Gauge",
                    "otelcol-1  | NumberDataPoints #0", "otelcol-1  | StartTimestamp: 1970-01-01 00:00:00 +0000 UTC",
                    "otelcol-1  | Timestamp: %s" % _otel_time(at), "otelcol-1  | Value: %.6f" % value]

        def _state_at(self, t):
            throttled = paused = False
            for at, what in sorted(self.throttle):
                if at > t:
                    break
                if what == "pause":
                    paused = True
                elif what == "unpause":
                    paused = False
                else:
                    throttled = what.startswith("0.")
            return throttled, paused

        def collector_log(self):
            out = super().collector_log().rstrip("\n").split("\n")
            for i, (token, tp, t0, t1, ok) in enumerate(sorted(self.calls, key=lambda x: x[2])):
                trace = tp.split("-")[1] if tp else _hex("probe-%d" % i, 32)
                parent = tp.split("-")[2] if tp else None
                envoy = _hex("envoy-%s" % trace, 16)
                self._span(out, "frontend-proxy", trace, parent, envoy, "ingress", t0, t1, not ok)
                if ok:
                    fe = _hex("frontend-%s" % trace, 16)
                    self._span(out, "frontend", trace, envoy, fe, "GET /api/products/[productId]", t0 + 0.001,
                               t1 - 0.001, False)
                    self._span(out, "productcatalogservice", trace, fe, _hex("pc-%s" % trace, 16),
                               "oteldemo.ProductCatalogService/GetProduct", t0 + 0.002, t0 + 0.003, False)
            if self.calls:
                lo, hi = min(c[2] for c in self.calls), max(c[3] for c in self.calls)
                k = 0
                while lo + k * EXPORT_SECONDS <= hi:
                    at = lo + k * EXPORT_SECONDS
                    throttled, paused = self._state_at(at)
                    self._gauge(out, "productcatalogservice", "app.fixture.load", at,
                                (50.0 if throttled else 5.0) + 0.1 * (k % 3))
                    if not paused:
                        self._gauge(out, "frontend", "app.fixture.load", at, 5.0 + 0.1 * (k % 3))
                    k += 1
            return "\n".join(out) + "\n"

        def application_log(self):
            out = [super().application_log().rstrip("\n")]
            for token, tp, t0, t1, ok in sorted(self.calls, key=lambda x: x[3]):
                row = {"obsplacement_kind": "application-request-witness", "request_token": token,
                       "response_code": 200 if ok else 504, "start_time": "%.3f" % t0,
                       "duration_ms": int(round((t1 - t0) * 1000))}
                if tp:
                    p = tp.split("-")
                    row["traceparent"] = "%s-%s-%s-%s" % (p[0], p[1], "a" * 16, p[3])
                out.append("frontendproxy-1  | %s %s" % (_docker(t1 + 0.0005), json.dumps(row)))
                if ok:
                    out.append("frontend-1  | %s GET /api/products/66VCHSJNUP 200 in %d ms" % (
                        _docker(t1 - 0.0005), int(round((t1 - t0) * 1000))))
            return "\n".join(out) + "\n"
    return RichTarget


def main(argv):
    worktree, scratch = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(HERE))
    from _pinned import pinned_tree                     # noqa: E402
    source, head = pinned_tree(worktree, PINNED, scratch)
    sys.path.insert(0, str(source / "tests"))
    import pytest                                       # noqa: E402  the harness venv's
    import test_otel_traffic_sweep as H                 # noqa: E402  the harness's own fixtures
    factory = Factory(scratch)
    tree = H.tree.__wrapped__(factory)
    package = H.sweep_package.__wrapped__(tree, factory)
    sys.modules["otel_candidate_terminal_runtime"] = tree.runtime        # as the harness's autouse fixture
    sys.modules["otel_candidate_terminal_remote"] = tree.remote
    if OUT.exists():
        shutil.rmtree(OUT)
    camp = OUT / "campaign"
    written = []
    for regime, rate in CELLS:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(H, "FakeTarget", rich_target(H))
            contract = H._contract_for(tree, package, regime, rate, factory.mktemp("cell"))
            receipt, _ = H._execute(tree, contract, mp)
        root = Path(contract["remoteArtifactRoot"])
        if receipt["state"] != "valid":
            raise SystemExit("the harness's runner sealed %s %s invalid: %s" % (regime, rate, receipt["error"]))
        report = tree.terminal.validate_cell(root, contract)
        if report["state"] != "valid":
            raise SystemExit("the harness's terminal refused %s %s: %s" % (regime, rate, report.get("errors")))
        rel = Path(contract["compiledArtifactRoot"])
        dest = camp / (rel if rel.parts[0] == "runs" else Path("runs") / rel)
        shutil.copytree(root, dest)
        written.append({"cell": dest.relative_to(OUT).as_posix(), "runId": contract["runId"], "regime": regime,
                        "rate": rate})
    files = sorted(p for p in camp.rglob("*") if p.is_file())
    manifest = {"harness": "observability-placement-runtime-otel-protocol", "harnessCommit": head,
                "writer": "modules/otel-demo/execution/candidate_remote.py run_cell (harness), driven by "
                          "tests/test_otel_traffic_sweep.py FakeTarget (+ this generator's records), terminal-validated",
                "generator": "tests/fixtures/sweep_v22/generate_otel.py", "cells": written,
                "files": {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print("wrote %d files under %s" % (len(files), OUT))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    sys.exit(main(sys.argv))
