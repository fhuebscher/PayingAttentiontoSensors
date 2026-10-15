#!/usr/bin/env python3
"""Fail-closed runtime admission for the OTel Demo candidate pilot.

This controller binds ONE current study epoch (``STUDY_EPOCH``, the offpath
direction-(c) descriptor; main repo research/otel-offpath/DECLARATION.md,
8194d74 and errata 24d3b5f, ff65eea) and keeps the superseded v1 epoch only as the byte-frozen
UNSUPPORTED ledger it replays (``UNSUPPORTED_STUDY_EPOCH``).  Every transport,
readiness, setup, launch, status, fetch, and mutation entry point goes through
``refuse_unsupported`` first, which fails closed on two independent facts:

1. the frozen descriptor must realize every required posture and the posture
   catalog must agree (D13, user, 2026-09-06: ``none`` means no telemetry
   emitted; the four loaded-but-silenced services are a named claim boundary,
   not a blocker), and
2. the study epoch must be admitted by the installed target controllers --
   ``ADMITTED_STUDY_EPOCHS`` in ``candidate_setup.py`` and
   ``candidate_remote.py`` must agree and must name ``STUDY_EPOCH``.  Until
   that governed edit lands, no local transport method may mutate the target,
   even though the v2 descriptor itself no longer refuses.

Decision D13 settled the catalog rule; the v2 study epoch writes that reading
into the frozen design.  The v1 descriptor's bytes did not move.

2026-10-03 (branch otel-protocol-20261002): a second epoch,
``otel-traffic-sweep-v1`` (``candidate_sweep.py``), is selected only by the
committed file ``execution/study-epoch.json``; with no selector every constant
below keeps its offpath value (see "study-epoch selection").

2026-10-04: a third, ``otel-quiet-calibration-v1`` (``candidate_quiet.py``; main
repo research/PROTOCOL_DRAFT_20261002.md decision 48), 40 no-fault cells of the
sweep's cell shape, selected the same way.  ``is_sweep_epoch`` means "a timed
(selector-activated) epoch" and is true for both.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import functools
import grp
import hashlib
import importlib.util
import json
import math
import os
import platform
import pwd
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, NoReturn, Protocol, Sequence


ROOT = Path(__file__).resolve().parents[3]
# The change id stays the v2 admission change: v3 has no OpenSpec change of its
# own; its authority is the main-repo declaration (research/otel-postures/
# DECLARATION.md, 6221145), recorded in the v3 descriptor's supersedes.authority.
# Engineering default, 2026-09-30: creating a governance change was outside the
# declared change set, and the sentences stay byte-derivable either way.
CHANGE_ID = "admit-otel-demo-candidate-pilot-v2"
STUDY_EPOCH = "otel-demo-offpath-v1"
# Design order; nested by closure: none < selected < async < full.
POSTURES = ("none", "selected", "async", "full")
# The literal closures posture_catalog() pins (offpath, DECLARATION.md 8194d74):
# selected = the synchronous checkout path as traversed (candidate_pilot.
# OFFPATH_SYNC_PATH, derivation recorded in the descriptor; flagd is on it);
# async = selected + the orders topic's broker and its two consumers.
# Instrumentation activation only -- every application service runs in every
# posture. The harness re-checks selected against the first no-fault full cell
# (candidate_remote.workload_path_check) before any fault cell.
SELECTED_CLOSURE = (
    "cartservice", "checkoutservice", "currencyservice", "emailservice", "flagd",
    "frontend", "frontendproxy", "paymentservice", "productcatalogservice",
    "quoteservice", "shippingservice",
)
ASYNC_CLOSURE = (
    "accountingservice", "cartservice", "checkoutservice", "currencyservice",
    "emailservice", "flagd", "frauddetectionservice", "frontend", "frontendproxy",
    "kafka", "paymentservice", "productcatalogservice", "quoteservice",
    "shippingservice",
)
# Every binary the launch argv spends on the target, and every gid whose name
# that argv needs. Resolved on the target at launch time (see
# ``ComposeSshAdapter._resolve_launch_tokens``), never hardcoded: `runuser` is
# /usr/sbin on fb14srv4 and /sbin on fb14srv5 and fb14srv6.
LAUNCH_ARGV_BINARIES = ("runuser", "flock", "python3")
LAUNCH_ARGV_GIDS = (1016, 998)
LAUNCH_VERIFY_ATTEMPTS = 5
LAUNCH_VERIFY_SETTLE_SECONDS = 3.0
# The superseded v1 epoch: its change id, study epoch, and descriptor are bound
# here only so the exact 18-cell UNSUPPORTED ledger keeps replaying against the
# bytes it was written for. Nothing runtime-facing reads these.
UNSUPPORTED_CHANGE_ID = "admit-otel-demo-candidate-runtime"
UNSUPPORTED_STUDY_EPOCH = "otel-demo-candidate-pilot-v1"
UNSUPPORTED_RUN_COUNT = 18
# The v1 ledger's recorded successor. It names v2 (the epoch that superseded v1)
# and must keep doing so after v3: the ledger's bytes do not move.
UNSUPPORTED_SUCCESSOR_EPOCH = "otel-demo-candidate-pilot-v2"
UNSUPPORTED_SUCCESSOR_CHANGE_ID = "admit-otel-demo-candidate-pilot-v2"
RUN_COUNT = 36
# No ATTEMPT literal: the attempt is read from the compiled plan
# (candidate_pilot.plan_attempt), which the launcher selects through
# candidate_pilot.ATTEMPT_ENVIRONMENT. Run 1 was attempt 1.
EVIDENCE_LABEL = "candidate-evidence"
PLAN_KIND = "otel-demo-candidate-gate-plan-v1"
SETUP_KIND = "otel-demo-candidate-gate-setup-v1"
RUN_KIND = "otel-demo-candidate-gate-run-v1"
READINESS_KIND = "otel-demo-candidate-target-readiness-v2"
CELL_KIND = "otel-demo-candidate-cell-contract-v1"
EXECUTION_KIND = "otel-demo-candidate-execution-package-v1"
SETUP_PACKAGE_KIND = "otel-demo-candidate-setup-package-v1"
MAX_GATE_AGE_SECONDS = 15 * 60
# 14 400 s (4 h) was sized for 18 cells. Run 3 took 4.02 h for 18 cells (13.4 min
# per cell); v3r1 took 5.32 h for 24 cells (first cell 03:24:50Z -> terminal
# 08:44Z, 13.3 min per cell). 36 offpath cells therefore need ~8.0 h (28 800 s)
# plus a 15 s collector settle and a full checkout readiness journey per cell;
# 36 000 s (10 h) leaves ~2 h margin (review 2026-10-02: 9 h left ~50 min).
# run_window_hours = 11 (the shared library default) leaves 1 h between GATE-RUN
# approval and first mutation.
MINIMUM_REMAINING_SECONDS = 36_000
CLEANUP_RESERVE_SECONDS = 600
# The checkout journey's two steps (upstream 2d4661e src/frontend/pages/api/
# cart.ts and checkout.ts; the loadgenerator's checkout() task). The product is
# the one v1-v3 requested recommendations for.
OFFPATH_CART_PATH = "/api/cart"
OFFPATH_CHECKOUT_PATH = "/api/checkout?currencyCode=USD"
OFFPATH_PRODUCT_ID = "OLJCESPC7Z"

DESCRIPTOR = ROOT / "pipelines/campaigns/otel-demo-offpath-v1.json"
UNSUPPORTED_DESCRIPTOR = ROOT / "pipelines/campaigns/otel-demo-candidate-pilot-v1.json"
POSTURE_CATALOG = ROOT / "modules/otel-demo/postures/catalog.json"
UPSTREAM_ROOT = ROOT / "upstream/opentelemetry-demo"
UPSTREAM_RECOMMENDATION_DOCKERFILE = UPSTREAM_ROOT / "src/recommendationservice/Dockerfile"
# The exact upstream ENTRYPOINT line the materializer's guard replaces. Kept here so
# the replay-side check can re-render the guard without the upstream checkout present.
UPSTREAM_RECOMMENDATION_ENTRYPOINT = (
    'ENTRYPOINT [ "opentelemetry-instrument", "python", "recommendation_server.py" ]\n'
)
# The posture-conditional launches the plan-time proof executes and accepts, one per
# service whose upstream image loads an instrumentation agent unconditionally.
# Declared here independently of materialize.py on purpose: the two statements are
# compared, so an edit to either side is a gate failure rather than a silently
# agreeing tautology. The disabled branch of each is the plain upstream program; the
# enabled branch is the exact upstream launch.
EXPECTED_ENTRYPOINT_GUARDS = {
    "recommendationservice": (
        'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then '
        "exec python recommendation_server.py; "
        "else exec opentelemetry-instrument python recommendation_server.py; fi"
    ),
    "accountingservice": (
        'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then '
        "exec dotnet AccountingService.dll; "
        "else exec ./instrument.sh dotnet AccountingService.dll; fi"
    ),
    "paymentservice": (
        'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then '
        "exec node index.js; "
        "else exec node --require ./opentelemetry.js index.js; fi"
    ),
}
EXPECTED_RECOMMENDATION_ENTRYPOINT_TEXT = EXPECTED_ENTRYPOINT_GUARDS["recommendationservice"]
# What the executing proof must observe for each guard: (program, argv) when the
# posture is disabled and when it is enabled. The stub programs print their argv, so
# a branch that execs the wrapper twice, inverts the branches, or drops the
# ``--require`` preload cannot pass by looking conditional.
EXPECTED_GUARD_LAUNCHES = {
    "recommendationservice": {
        "false": "python recommendation_server.py",
        "true": "opentelemetry-instrument python recommendation_server.py",
    },
    "accountingservice": {
        "false": "dotnet AccountingService.dll",
        "true": "instrument.sh dotnet AccountingService.dll",
    },
    "paymentservice": {
        "false": "node index.js",
        "true": "node --require ./opentelemetry.js index.js",
    },
}
GUARD_STUB_PROGRAMS = ("python", "opentelemetry-instrument", "dotnet", "node", "npm")
GUARD_STUB_SCRIPTS = ("instrument.sh",)
# JVM agents upstream bakes into an image ENV; the overlay rebinds the variable to
# this exact value when enabled and to the empty string when disabled.
EXPECTED_AGENT_ENVIRONMENT = {
    "adservice": ("JAVA_TOOL_OPTIONS", "-javaagent:/usr/src/app/opentelemetry-javaagent.jar"),
    "frauddetectionservice": ("JAVA_TOOL_OPTIONS", "-javaagent:/app/opentelemetry-javaagent.jar"),
    "kafka": (
        "KAFKA_OPTS",
        "-javaagent:/tmp/opentelemetry-javaagent.jar -Dotel.jmx.target.system=kafka-broker",
    ),
}
EXPECTED_FLAGD_ENVIRONMENT = {
    "enabled": {"FLAGD_OTEL_COLLECTOR_URI": "otelcol:4317", "FLAGD_METRICS_EXPORTER": "otel"},
    "disabled": {"FLAGD_OTEL_COLLECTOR_URI": "", "FLAGD_METRICS_EXPORTER": ""},
}
# Services whose OTel SDK pipeline is constructed in application code, so the
# guard is a source patch at the exporter/provider construction site rather
# than an entrypoint wrapper (EXPECTED_ENTRYPOINT_GUARDS) or an attached agent
# ENV (EXPECTED_AGENT_ENVIRONMENT). Declared here independently of
# materialize.py on purpose, exactly like the two guard tables above: the two
# statements are compared (verify_materializer_constants), so an edit to
# either side alone is a gate failure. Proof against the pinned upstream
# checkout is text-only (prove_materialized_source_guards) -- these are
# conditionals inside a compiled language this repo does not build or run
# without a container image build, unlike the executed shell-level proof for
# EXPECTED_ENTRYPOINT_GUARDS.
EXPECTED_SOURCE_PLACEMENT_GUARD_FILES = {
    "cartservice": "src/cartservice/src/Program.cs",
    "checkoutservice": "src/checkoutservice/main.go",
    "currencyservice": "src/currencyservice/src/server.cpp",
    "productcatalogservice": "src/productcatalogservice/main.go",
    "shippingservice": "src/shippingservice/src/main.rs",
}
EXPECTED_SOURCE_PLACEMENT_GUARDS = {
    "cartservice": ((
        (
            'builder.Logging\n'
            '    .AddOpenTelemetry(options => options.AddOtlpExporter())\n'
            '    .AddConsole();\n'
        ),
        (
            'bool otelPlacementEnabled = Environment.GetEnvironmentVariable("OTEL_PLACEMENT_ENABLED") != "false";\n'
            'builder.Logging.AddConsole();\n'
            'if (otelPlacementEnabled)\n'
            '{\n'
            '    builder.Logging.AddOpenTelemetry(options => options.AddOtlpExporter());\n'
            '}\n'
        ),
    ), (
        (
            'builder.Services.AddOpenTelemetry()\n'
            '    .ConfigureResource(appResourceBuilder)\n'
            '    .WithTracing(tracerBuilder => tracerBuilder\n'
            '        .AddRedisInstrumentation(\n'
            '            options => options.SetVerboseDatabaseStatements = true)\n'
            '        .AddAspNetCoreInstrumentation()\n'
            '        .AddGrpcClientInstrumentation()\n'
            '        .AddHttpClientInstrumentation()\n'
            '        .AddOtlpExporter())\n'
            '    .WithMetrics(meterBuilder => meterBuilder\n'
            '        .AddProcessInstrumentation()\n'
            '        .AddRuntimeInstrumentation()\n'
            '        .AddAspNetCoreInstrumentation()\n'
            '        .AddOtlpExporter());\n'
            'OpenFeature.Api.Instance.AddHooks(new TracingHook());\n'
        ),
        (
            'if (otelPlacementEnabled)\n'
            '{\n'
            '    builder.Services.AddOpenTelemetry()\n'
            '        .ConfigureResource(appResourceBuilder)\n'
            '        .WithTracing(tracerBuilder => tracerBuilder\n'
            '            .AddRedisInstrumentation(\n'
            '                options => options.SetVerboseDatabaseStatements = true)\n'
            '            .AddAspNetCoreInstrumentation()\n'
            '            .AddGrpcClientInstrumentation()\n'
            '            .AddHttpClientInstrumentation()\n'
            '            .AddOtlpExporter())\n'
            '        .WithMetrics(meterBuilder => meterBuilder\n'
            '            .AddProcessInstrumentation()\n'
            '            .AddRuntimeInstrumentation()\n'
            '            .AddAspNetCoreInstrumentation()\n'
            '            .AddOtlpExporter());\n'
            '    OpenFeature.Api.Instance.AddHooks(new TracingHook());\n'
            '}\n'
        ),
    ), (
        'app.Services.GetRequiredService<StackExchangeRedisInstrumentation>().AddConnection(ValkeyCartStore.GetConnection());\n',
        (
            'if (otelPlacementEnabled)\n'
            '{\n'
            '    app.Services.GetRequiredService<StackExchangeRedisInstrumentation>().AddConnection(ValkeyCartStore.GetConnection());\n'
            '}\n'
        ),
    )),
    "checkoutservice": ((
        (
            '\ttp := initTracerProvider()\n'
            '\tdefer func() {\n'
            '\t\tif err := tp.Shutdown(context.Background()); err != nil {\n'
            '\t\t\tlog.Printf("Error shutting down tracer provider: %v", err)\n'
            '\t\t}\n'
            '\t}()\n'
            '\n'
            '\tmp := initMeterProvider()\n'
            '\tdefer func() {\n'
            '\t\tif err := mp.Shutdown(context.Background()); err != nil {\n'
            '\t\t\tlog.Printf("Error shutting down meter provider: %v", err)\n'
            '\t\t}\n'
            '\t}()\n'
            '\n'
            '\terr := runtime.Start(runtime.WithMinimumReadMemStatsInterval(time.Second))\n'
            '\tif err != nil {\n'
            '\t\tlog.Fatal(err)\n'
            '\t}\n'
            '\n'
            '\topenfeature.SetProvider(flagd.NewProvider())\n'
            '\topenfeature.AddHooks(otelhooks.NewTracesHook())\n'
            '\n'
            '\ttracer = tp.Tracer("checkoutservice")\n'
        ),
        (
            '\tplacementEnabled := os.Getenv("OTEL_PLACEMENT_ENABLED") != "false"\n'
            '\tvar err error\n'
            '\tif placementEnabled {\n'
            '\t\ttp := initTracerProvider()\n'
            '\t\tdefer func() {\n'
            '\t\t\tif shutdownErr := tp.Shutdown(context.Background()); shutdownErr != nil {\n'
            '\t\t\t\tlog.Printf("Error shutting down tracer provider: %v", shutdownErr)\n'
            '\t\t\t}\n'
            '\t\t}()\n'
            '\n'
            '\t\tmp := initMeterProvider()\n'
            '\t\tdefer func() {\n'
            '\t\t\tif shutdownErr := mp.Shutdown(context.Background()); shutdownErr != nil {\n'
            '\t\t\t\tlog.Printf("Error shutting down meter provider: %v", shutdownErr)\n'
            '\t\t\t}\n'
            '\t\t}()\n'
            '\n'
            '\t\terr = runtime.Start(runtime.WithMinimumReadMemStatsInterval(time.Second))\n'
            '\t\tif err != nil {\n'
            '\t\t\tlog.Fatal(err)\n'
            '\t\t}\n'
            '\n'
            '\t\topenfeature.AddHooks(otelhooks.NewTracesHook())\n'
            '\t}\n'
            '\n'
            '\topenfeature.SetProvider(flagd.NewProvider())\n'
            '\ttracer = otel.Tracer("checkoutservice")\n'
        ),
    ), (
        (
            '\tvar srv = grpc.NewServer(\n'
            '\t\tgrpc.StatsHandler(otelgrpc.NewServerHandler()),\n'
            '\t)\n'
        ),
        (
            '\tvar serverOpts []grpc.ServerOption\n'
            '\tif placementEnabled {\n'
            '\t\tserverOpts = append(serverOpts, grpc.StatsHandler(otelgrpc.NewServerHandler()))\n'
            '\t}\n'
            '\tvar srv = grpc.NewServer(serverOpts...)\n'
        ),
    )),
    "currencyservice": ((
        '  initTracer();\n  initMeter();\n  initLogger();\n',
        (
            '  const char *otel_placement_enabled = std::getenv("OTEL_PLACEMENT_ENABLED");\n'
            '  if (otel_placement_enabled == nullptr || std::strcmp(otel_placement_enabled, "false") != 0) {\n'
            '    initTracer();\n'
            '    initMeter();\n'
            '    initLogger();\n'
            '  }\n'
        ),
    ),),
    "productcatalogservice": ((
        (
            '\ttp := initTracerProvider()\n'
            '\tdefer func() {\n'
            '\t\tif err := tp.Shutdown(context.Background()); err != nil {\n'
            '\t\t\tlog.Fatalf("Tracer Provider Shutdown: %v", err)\n'
            '\t\t}\n'
            '\t\tlog.Println("Shutdown tracer provider")\n'
            '\t}()\n'
            '\n'
            '\tmp := initMeterProvider()\n'
            '\tdefer func() {\n'
            '\t\tif err := mp.Shutdown(context.Background()); err != nil {\n'
            '\t\t\tlog.Fatalf("Error shutting down meter provider: %v", err)\n'
            '\t\t}\n'
            '\t\tlog.Println("Shutdown meter provider")\n'
            '\t}()\n'
            '\topenfeature.AddHooks(otelhooks.NewTracesHook())\n'
            '\terr := openfeature.SetProvider(flagd.NewProvider())\n'
            '\tif err != nil {\n'
            '\t\tlog.Fatal(err)\n'
            '\t}\n'
            '\n'
            '\terr = runtime.Start(runtime.WithMinimumReadMemStatsInterval(time.Second))\n'
            '\tif err != nil {\n'
            '\t\tlog.Fatal(err)\n'
            '\t}\n'
        ),
        (
            '\tplacementEnabled := os.Getenv("OTEL_PLACEMENT_ENABLED") != "false"\n'
            '\tif placementEnabled {\n'
            '\t\ttp := initTracerProvider()\n'
            '\t\tdefer func() {\n'
            '\t\t\tif err := tp.Shutdown(context.Background()); err != nil {\n'
            '\t\t\t\tlog.Fatalf("Tracer Provider Shutdown: %v", err)\n'
            '\t\t\t}\n'
            '\t\t\tlog.Println("Shutdown tracer provider")\n'
            '\t\t}()\n'
            '\n'
            '\t\tmp := initMeterProvider()\n'
            '\t\tdefer func() {\n'
            '\t\t\tif err := mp.Shutdown(context.Background()); err != nil {\n'
            '\t\t\t\tlog.Fatalf("Error shutting down meter provider: %v", err)\n'
            '\t\t\t}\n'
            '\t\t\tlog.Println("Shutdown meter provider")\n'
            '\t\t}()\n'
            '\t\topenfeature.AddHooks(otelhooks.NewTracesHook())\n'
            '\t}\n'
            '\terr := openfeature.SetProvider(flagd.NewProvider())\n'
            '\tif err != nil {\n'
            '\t\tlog.Fatal(err)\n'
            '\t}\n'
            '\n'
            '\tif placementEnabled {\n'
            '\t\terr = runtime.Start(runtime.WithMinimumReadMemStatsInterval(time.Second))\n'
            '\t\tif err != nil {\n'
            '\t\t\tlog.Fatal(err)\n'
            '\t\t}\n'
            '\t}\n'
        ),
    ), (
        (
            '\tsrv := grpc.NewServer(\n'
            '\t\tgrpc.StatsHandler(otelgrpc.NewServerHandler()),\n'
            '\t)\n'
        ),
        (
            '\tvar serverOpts []grpc.ServerOption\n'
            '\tif placementEnabled {\n'
            '\t\tserverOpts = append(serverOpts, grpc.StatsHandler(otelgrpc.NewServerHandler()))\n'
            '\t}\n'
            '\tsrv := grpc.NewServer(serverOpts...)\n'
        ),
    )),
    "shippingservice": ((
        '    init_reqwest_tracing(init_tracer()?)?;\n\n    info!("OTel pipeline created");\n',
        (
            '    let otel_placement_enabled = env::var("OTEL_PLACEMENT_ENABLED").map(|value| value != "false").unwrap_or(true);\n'
            '    if otel_placement_enabled {\n'
            '        init_reqwest_tracing(init_tracer()?)?;\n'
            '        info!("OTel pipeline created");\n'
            '    }\n'
        ),
    ),),
}
DISABLED_LOAD_STATES = ("not-loaded", "loaded-silenced", "loaded-exporting")
PROBE_KINDS = ("container-env", "pid1-environ", "process-args", "container-file")
INSTRUMENTATION_MECHANISMS = (
    "auto-instrumentation-shim", "jvm-javaagent-via-JAVA_TOOL_OPTIONS",
    "jvm-javaagent-via-KAFKA_OPTS", "in-code-sdk", "node-require-preload",
    "envoy-tracing-config", "nginx-otel-module", "php-sdk-autoload",
    "opentelemetry-instrument-wrapper",
)
TARGET_ALLOCATION = ROOT / "modules/otel-demo/execution/candidate-target-allocation.json"
UNSUPPORTED_EVIDENCE = ROOT / "modules/otel-demo/execution/candidate-unsupported.json"
COMPOSE_OVERLAYS = (
    "modules/otel-demo/deployment/compose.otel-placement.yml",
    "modules/otel-demo/deployment/compose.candidate-postures.yml",
)
CONTROLLER_PATHS = {
    "candidate-compiler": "modules/otel-demo/execution/candidate_pilot.py",
    "runtime-admission": "modules/otel-demo/execution/candidate_runtime.py",
    "remote-setup-controller": "modules/otel-demo/execution/candidate_setup.py",
    "remote-compose-controller": "modules/otel-demo/execution/candidate_remote.py",
    "candidate-terminal": "modules/otel-demo/validation/candidate_terminal.py",
    "unsupported-disposition": "modules/otel-demo/validation/candidate_unsupported.py",
    "materializer": "modules/otel-demo/materialize.py",
    "workload": "modules/otel-demo/workload.py",
    "posture-catalog": "modules/otel-demo/postures/catalog.json",
    "target-contract": "modules/otel-demo/execution/candidate-target-allocation.json",
    "base-compose-overlay": COMPOSE_OVERLAYS[0],
    "candidate-posture-overlay": COMPOSE_OVERLAYS[1],
}

READINESS_SEAMS = (
    "target-contract-projection",
    "target-identity",
    "target-root-and-host-isolation",
    "toolchain-pins",
    "source-image-bindings",
    "installed-release-bindings",
    "foreign-inventory-preservation",
    "project-port-lease-isolation",
    "none-posture",
    "selected-posture",
    "async-posture",
    "full-posture",
    "application-request-witness",
    "request-token-original-trace-correlation",
    "cumulative-application-cpu",
    "emitted-and-on-wire-telemetry-bytes",
    "frontend-fault-manifestation-recovery",
    "owned-cleanup-and-deadline",
    "candidate-terminal-validation",
)
TARGET_OBSERVATION_SEAMS = frozenset(READINESS_SEAMS[:8])
HARNESS_REPLAY_SEAMS = frozenset(READINESS_SEAMS[8:])
READINESS_SCOPE = {
    seam: (
        "target-observation"
        if seam in TARGET_OBSERVATION_SEAMS
        else "harness-contract-replay"
    )
    for seam in READINESS_SEAMS
}

PORT_KEYS = (
    "frontend",
    "frontendProxyOtlp",
    "grafana",
    "jaeger",
    "prometheus",
)
SAFE_HOST = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,62})$")
SAFE_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class GateError(ValueError):
    """A schedule, readiness, authorization, or outcome failed closed."""


def _reject_constant(value: str) -> NoReturn:
    raise GateError(f"non-finite JSON value is forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise GateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_bytes(payload: bytes, where: str) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except GateError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(f"invalid JSON in {where}: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateError(f"value is not canonical JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(_read_file(path, str(path))).hexdigest()


def _read_file(path: Path, where: str) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise GateError(f"{where} is not a regular non-symlink file")
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        payload = path.read_bytes()
        after = path.lstat()
        if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise GateError(f"{where} changed while being read")
        return payload
    except GateError:
        raise
    except OSError as exc:
        raise GateError(f"cannot read {where}: {exc}") from exc


def _json_file(path: Path, where: str) -> dict[str, Any]:
    value = strict_json_bytes(_read_file(path, where), where)
    if not isinstance(value, dict):
        raise GateError(f"{where} is not a JSON object")
    return value


def _exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        observed = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise GateError(
            f"{where} keys differ: expected {sorted(keys)}, observed {observed}"
        )
    return value


def _int(value: Any, where: str, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise GateError(f"{where} is not an exact bounded integer")
    return value


def _timestamp(value: Any, where: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GateError(f"{where} must be a UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateError(f"{where} is not an ISO timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise GateError(f"{where} is not UTC")
    return parsed


def _safe_posix(value: Any, where: str, *, absolute: bool) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise GateError(f"{where} is not a safe POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() is not absolute or any(part in {"", ".", ".."} for part in path.parts):
        raise GateError(f"{where} is not a normalized {'absolute' if absolute else 'relative'} path")
    if str(path) != value:
        raise GateError(f"{where} is not canonical")
    return path


def _controller_module(controller: str, name: str):
    path = ROOT / CONTROLLER_PATHS[controller]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise GateError(f"{controller} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pilot_module():
    return _controller_module("candidate-compiler", "otel_candidate_runtime_pilot")


FROZEN_COMPILER = ROOT / "modules/otel-demo/execution/candidate_pilot.py"


def _frozen_pilot_module():
    """candidate_pilot.py whatever epoch is active: the v1 UNSUPPORTED ledger and the offpath readiness fixture
    read the frozen compiler's tables, so they do not move when a selector swaps the active compiler."""
    spec = importlib.util.spec_from_file_location("otel_candidate_runtime_frozen_pilot", FROZEN_COMPILER)
    if spec is None or spec.loader is None:
        raise GateError("frozen candidate compiler cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------- study-epoch selection
# 2026-10-03 (branch otel-protocol-20261002): this checkout carries two epochs.  The frozen otel-demo-offpath-v1
# (candidate_pilot.py) stays the active epoch, and every constant above keeps its value, unless the committed file
# execution/study-epoch.json selects another one.  The selector is a controller file like any other: committing it
# is a framework commit (every gate sentence is re-derived) and, when present, its digest is bound in
# CONTROLLER_PATHS together with the sweep compiler, both descriptors and the vendored protocol gates.  No selector =
# the frozen epoch, byte for byte as at 92be2b7.  The target's own runtime copy reads the selector of the installed
# release, so the local chain and the target agree by construction.
FROZEN_STUDY_EPOCH = STUDY_EPOCH
FROZEN_RUN_COUNT = RUN_COUNT
FROZEN_MINIMUM_REMAINING_SECONDS = MINIMUM_REMAINING_SECONDS
EPOCH_SELECTOR = ROOT / "modules/otel-demo/execution/study-epoch.json"
SWEEP_STUDY_EPOCH = "otel-traffic-sweep-v1"
QUIET_STUDY_EPOCH = "otel-quiet-calibration-v1"
REPEAT_STUDY_EPOCH = "otel-repeat-episodes-v1"
REPEAT_C_STUDY_EPOCH = "otel-repeat-episodes-c-v1"
LOAD_PILOT_STUDY_EPOCH = "otel-load-pilot-v1"
OFFPATH_PILOT_STUDY_EPOCH = "otel-offpath-pilot-v1"
OFFPATH_PILOT_V2_STUDY_EPOCH = "otel-offpath-pilot-v2"
OFFPATH_E_STUDY_EPOCH = "otel-offpath-e-v1"
OFFPATH_F_STUDY_EPOCH = "otel-offpath-f-v1"
OFFPATH_F_NOLAG_STUDY_EPOCH = "otel-offpath-f-nolag-v1"
EPOCH_CONTROLLER_PATHS = {
    SWEEP_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "candidate-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        # The sweep descriptor is generated from the offpath descriptor's bytes (candidate_sweep.derive_sweep_descriptor).
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-04: the quiet calibration epoch compiles the sweep's no-fault cell (candidate_quiet.cell_timing reads
    # candidate_sweep.cell_timing) and derives its descriptor from the sweep's pinned descriptor, so both sweep files
    # are digest-bound inputs here, beside the frozen pair the sweep compiler itself reads.
    QUIET_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "candidate-descriptor": "pipelines/campaigns/otel-quiet-calibration-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-09: the repeat-episodes epoch (campaign B, candidate_repeat.py) compiles the sweep's cell (candidate_sweep.cell_timing),
    # draws its onset and block order with the quiet compiler's parameterised functions and derives its descriptor from
    # the sweep's pinned descriptor, so the sweep pair and the quiet compiler are digest-bound inputs here.
    REPEAT_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "candidate-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-11: campaign C (candidate_repeat_c.py, decision 82) is B's shape exactly: its compiler takes B's cell timing
    # and derives its descriptor from B's pinned descriptor, so B's compiler and descriptor are digest-bound inputs here,
    # beside everything B's compiler itself reads.
    REPEAT_C_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "candidate-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-12: the load pilot (candidate_load_pilot.py, main repo research/traffic-sweep/BUDGET_D.md amendment 1) takes
    # C's cell timing and derives its descriptor from C's pinned descriptor, so C's compiler and descriptor are digest-bound
    # inputs here, beside everything C's compiler itself reads.
    LOAD_PILOT_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_load_pilot.py",
        "candidate-descriptor": "pipelines/campaigns/otel-load-pilot-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-13: the off-path pilot (candidate_offpath_pilot.py, main repo research/traffic-sweep/BUDGET_E.md) takes C's cell
    # timing and derives its descriptor from C's pinned descriptor, like the load pilot, so C's compiler and descriptor are
    # digest-bound inputs here and the load pilot's are not.
    OFFPATH_PILOT_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_pilot.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-pilot-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-12: the second off-path pilot (candidate_offpath_pilot_v2.py, BUDGET_E amendment 1, decision 108): v1's chain, v2's compiler
    # and descriptor.
    OFFPATH_PILOT_V2_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_pilot_v2.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-pilot-v2.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-12: campaign E (candidate_offpath_e.py, BUDGET_E, decisions 95-102): pilot v2's chain, E's compiler and descriptor (not selected here).
    OFFPATH_E_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_e.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-e-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-14: campaign F (candidate_offpath_f.py, BUDGET_F): E's chain, F's compiler and descriptor (not selected here).
    OFFPATH_F_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_f.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-f-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
    # 2026-10-15: the F ablation (candidate_offpath_f_nolag.py, BUDGET_OVERNIGHT_20261014 item 2): F's chain with the ablation's compiler and descriptor.
    OFFPATH_F_NOLAG_STUDY_EPOCH: {
        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_f_nolag.py",
        "candidate-descriptor": "pipelines/campaigns/otel-offpath-f-nolag-v1.json",
        "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
        "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
        "sweep-compiler": "modules/otel-demo/execution/candidate_sweep.py",
        "sweep-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
        "quiet-compiler": "modules/otel-demo/execution/candidate_quiet.py",
        "repeat-compiler": "modules/otel-demo/execution/candidate_repeat.py",
        "repeat-descriptor": "pipelines/campaigns/otel-repeat-episodes-v1.json",
        "repeat-c-compiler": "modules/otel-demo/execution/candidate_repeat_c.py",
        "repeat-c-descriptor": "pipelines/campaigns/otel-repeat-episodes-c-v1.json",
        "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
        "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
    },
}


def _selected_study_epoch(selector: Path = EPOCH_SELECTOR) -> str:
    if not selector.exists() and not selector.is_symlink():
        return FROZEN_STUDY_EPOCH
    document = _json_file(selector, "study epoch selector")
    if (
        set(document) != {"schemaVersion", "studyEpoch"} or document["schemaVersion"] != 1
        or isinstance(document["schemaVersion"], bool)
        or document["studyEpoch"] not in EPOCH_CONTROLLER_PATHS
    ):
        raise GateError("study epoch selector names no declared non-frozen epoch")
    return document["studyEpoch"]


STUDY_EPOCH = _selected_study_epoch()
# The GATE-RUN window the drivers must request: the frozen epoch's library default (11 h) unless the active
# compiler derives one (candidate_sweep.RUN_WINDOW_HOURS = 3, candidate_quiet.RUN_WINDOW_HOURS = 6,
# candidate_repeat.RUN_WINDOW_HOURS = 5, candidate_repeat_c.RUN_WINDOW_HOURS = 5, candidate_load_pilot.RUN_WINDOW_HOURS = 3,
# candidate_offpath_pilot.RUN_WINDOW_HOURS = 4, candidate_offpath_pilot_v2.RUN_WINDOW_HOURS = 3,
# candidate_offpath_e.RUN_WINDOW_HOURS = 3 to 5 by the prepared (rate, kept faults) variant, candidate_offpath_f.RUN_WINDOW_HOURS = 5, candidate_offpath_f_nolag.RUN_WINDOW_HOURS = 5).
RUN_WINDOW_HOURS = 11
if STUDY_EPOCH != FROZEN_STUDY_EPOCH:
    CONTROLLER_PATHS = {**CONTROLLER_PATHS, **EPOCH_CONTROLLER_PATHS[STUDY_EPOCH]}
    DESCRIPTOR = ROOT / CONTROLLER_PATHS["candidate-descriptor"]
    _ACTIVE_COMPILER = _pilot_module()
    if _ACTIVE_COMPILER.EPOCH != STUDY_EPOCH:
        raise GateError("selected study epoch differs from its compiler's epoch")
    RUN_COUNT = int(_ACTIVE_COMPILER.TOTAL_RUNS)
    MINIMUM_REMAINING_SECONDS = int(_ACTIVE_COMPILER.MINIMUM_REMAINING_SECONDS)
    RUN_WINDOW_HOURS = int(_ACTIVE_COMPILER.RUN_WINDOW_HOURS)
    del _ACTIVE_COMPILER


def is_sweep_epoch() -> bool:
    """True for every selector-activated (timed) epoch: the traffic sweep and the quiet calibration."""
    return STUDY_EPOCH != FROZEN_STUDY_EPOCH


def admitted_study_epochs() -> tuple[str, ...]:
    """The study epochs the installed target controllers admit, read live.

    ``candidate_setup.ADMITTED_STUDY_EPOCHS`` and
    ``candidate_remote.ADMITTED_STUDY_EPOCHS`` are the tombstone: both must be
    the same tuple, or the release would install a setup controller and a
    Compose controller that disagree about what may run. Re-read on every call
    so the answer is the bytes on disk, never a cached import.
    """
    setup = _controller_module("remote-setup-controller", "otel_candidate_runtime_setup_tombstone")
    remote = _controller_module("remote-compose-controller", "otel_candidate_runtime_remote_tombstone")
    admitted = tuple(getattr(setup, "ADMITTED_STUDY_EPOCHS", None) or ())
    if admitted != tuple(getattr(remote, "ADMITTED_STUDY_EPOCHS", None) or ()):
        raise GateError(
            "target controllers disagree about admitted study epochs: "
            f"candidate_setup={admitted!r} candidate_remote={tuple(remote.ADMITTED_STUDY_EPOCHS)!r}"
        )
    if any(not isinstance(item, str) or not item for item in admitted):
        raise GateError("admitted study epochs are not non-empty strings")
    return admitted


@functools.lru_cache(maxsize=1)
def _materialize_module():
    path = ROOT / CONTROLLER_PATHS["materializer"]
    spec = importlib.util.spec_from_file_location("otel_candidate_runtime_materialize", path)
    if spec is None or spec.loader is None:
        raise GateError("materializer cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recommendation_entrypoint_command(dockerfile_text: str) -> str:
    """Extract the sole shell-form ENTRYPOINT command from a rendered Dockerfile."""
    lines = [line for line in dockerfile_text.splitlines() if line.startswith("ENTRYPOINT ")]
    if len(lines) != 1:
        raise GateError("recommendation Dockerfile does not have exactly one ENTRYPOINT")
    shell_command = lines[0][len("ENTRYPOINT "):]
    if shell_command.startswith("["):
        raise GateError(
            "recommendation ENTRYPOINT is exec-form (unconditional); expected the "
            "posture-conditional shell form"
        )
    return shell_command


def resolve_entrypoint_launch(shell_command: str, otel_placement_enabled: str) -> str:
    """Behaviorally resolve the program *and argv* a guarded launch actually execs.

    Runs the real shell statement under ``/bin/sh -c`` with ``PATH`` stubbed by
    marker programs (``GUARD_STUB_PROGRAMS``) and a scratch working directory
    holding marker scripts (``GUARD_STUB_SCRIPTS``, e.g. ``./instrument.sh``).
    Every stub prints its own name and argv, so the result is the launch line the
    container would run -- not a pattern match over the text, so a conditional
    that never selects the plain path, inverts the branches, or drops a
    ``--require`` preload cannot fake a pass.
    """
    if not isinstance(shell_command, str) or not shell_command or "\n" in shell_command:
        raise GateError("guarded launch is not a single shell statement")
    with tempfile.TemporaryDirectory() as shim_dir, tempfile.TemporaryDirectory() as work_dir:
        shim = Path(shim_dir)
        work = Path(work_dir)
        for program in GUARD_STUB_PROGRAMS:
            script = shim / program
            script.write_text(f'#!/bin/sh\necho "INVOKED:{program} $*"\n')
            script.chmod(0o755)
        for name in GUARD_STUB_SCRIPTS:
            script = work / name
            script.write_text(f'#!/bin/sh\necho "INVOKED:{name} $*"\n')
            script.chmod(0o755)
        result = subprocess.run(
            ["/bin/sh", "-c", shell_command],
            env={"PATH": str(shim), "OTEL_PLACEMENT_ENABLED": otel_placement_enabled},
            cwd=work, capture_output=True, text=True, timeout=5, check=True,
        )
    invoked = [line for line in result.stdout.splitlines() if line.startswith("INVOKED:")]
    if len(invoked) != 1:
        raise GateError(
            "guarded launch did not invoke exactly one stub program "
            f"(observed stdout: {result.stdout!r})"
        )
    return invoked[0][len("INVOKED:"):].strip()


def resolve_recommendation_entrypoint_program(
    dockerfile_text: str, otel_placement_enabled: str,
) -> str:
    """Program (first argv word) the rendered recommendationservice ENTRYPOINT execs."""
    launch = resolve_entrypoint_launch(
        recommendation_entrypoint_command(dockerfile_text), otel_placement_enabled
    )
    return launch.split()[0]


def prove_entrypoint_guard(service: str, shell_command: str) -> str:
    """Execute one guarded launch in both postures and require the exact upstream
    program lines, then require the statement to be the exported constant.

    Both halves are load-bearing: the behavioral half executes the real
    statement, the text half rejects a statement that merely prints the expected
    markers without exec'ing anything.
    """
    if service not in EXPECTED_GUARD_LAUNCHES:
        raise GateError(f"{service} has no guarded launch contract")
    expected = EXPECTED_GUARD_LAUNCHES[service]
    disabled = resolve_entrypoint_launch(shell_command, "false")
    enabled = resolve_entrypoint_launch(shell_command, "true")
    if disabled != expected["false"]:
        raise GateError(
            f"{service} launch when OTEL_PLACEMENT_ENABLED=false is {disabled!r}, not the "
            f"plain program {expected['false']!r}; the disabled posture is not a true zero baseline"
        )
    if enabled != expected["true"]:
        raise GateError(
            f"{service} launch when OTEL_PLACEMENT_ENABLED=true is {enabled!r}, not the "
            f"upstream instrumented launch {expected['true']!r}; the enabled posture would under-instrument"
        )
    if shell_command != EXPECTED_ENTRYPOINT_GUARDS[service]:
        raise GateError(
            f"{service} entrypoint guard text does not match the exported constant proven at plan time"
        )
    return shell_command


def verify_recommendation_source_instrumentation_posture(guarded_entrypoint_text: str) -> None:
    """Replay-side check: the guarded entrypoint is byte-identical to the one the
    plan-time proof executed.

    ``OTEL_SDK_DISABLED=true`` alone does not skip
    ``opentelemetry.instrumentation.auto_instrumentation`` loading every
    installed instrumentor (that only happens once, in
    ``_load_instrumentors()``, and is unconditional); it only makes
    ``TracerProvider.get_tracer()`` return a no-op tracer afterwards. So a
    posture that merely toggles ``OTEL_SDK_DISABLED`` under the unconditional
    upstream entrypoint is not a true zero-instrumentation baseline. That claim
    is settled behaviorally, once, by
    ``prove_recommendation_source_instrumentation_posture`` at plan time; replay
    re-checks the recorded text instead of re-executing it, so replaying retained
    evidence needs neither the upstream checkout nor ``/bin/sh``.
    """
    if guarded_entrypoint_text != EXPECTED_RECOMMENDATION_ENTRYPOINT_TEXT:
        raise GateError(
            "recommendation entrypoint guard text does not match the exported constant "
            "proven at plan time"
        )


def rendered_recommendation_entrypoint_command() -> str:
    """Render the guarded ENTRYPOINT through the installed materializer.

    Hermetic: it feeds the materializer the exact upstream anchor line rather than
    reading ``upstream/opentelemetry-demo``, so it works on a reaped worktree.
    """
    try:
        guarded = _materialize_module().apply_recommendation_entrypoint_guard(
            UPSTREAM_RECOMMENDATION_ENTRYPOINT
        )
    except RuntimeError as exc:
        raise GateError(
            f"materializer no longer guards the upstream recommendation entrypoint: {exc}"
        ) from exc
    return recommendation_entrypoint_command(guarded)


def prove_recommendation_source_instrumentation_posture(dockerfile_text: str) -> str:
    """Fail closed unless the rendered recommendationservice entrypoint genuinely
    execs the plain interpreter when disabled and the auto-instrumentation wrapper
    when enabled, and is byte-identical to the exported constant.

    Both halves are load-bearing and neither alone is sufficient. The behavioral
    half executes the real command, so a conditional that never selects the plain
    path (a typo'd comparison, a branch that execs the wrapper twice) cannot pass by
    merely *looking* conditional. The text half rejects a command that prints the
    expected marker without exec'ing anything, which the behavioral half alone would
    accept.
    """
    disabled = resolve_recommendation_entrypoint_program(dockerfile_text, "false")
    enabled = resolve_recommendation_entrypoint_program(dockerfile_text, "true")
    if disabled != "python":
        raise GateError(
            "recommendationservice entrypoint still loads opentelemetry-instrument when "
            "OTEL_PLACEMENT_ENABLED=false; the disabled posture is not a true zero baseline"
        )
    if enabled != "opentelemetry-instrument":
        raise GateError(
            "recommendationservice entrypoint does not load opentelemetry-instrument when "
            "OTEL_PLACEMENT_ENABLED=true; the enabled posture would under-instrument"
        )
    command = recommendation_entrypoint_command(dockerfile_text)
    verify_recommendation_source_instrumentation_posture(command)
    return prove_entrypoint_guard("recommendationservice", command)


@functools.lru_cache(maxsize=1)
def prove_materialized_recommendation_entrypoint() -> str:
    """Plan-time proof against the real upstream Dockerfile.

    Requires the upstream checkout and ``/bin/sh``; called from
    ``inspect_compiled_plan``, never from ``posture_catalog``.
    """
    materialize = _materialize_module()
    upstream_text = _read_file(
        UPSTREAM_RECOMMENDATION_DOCKERFILE, "upstream recommendation Dockerfile"
    ).decode("utf-8")
    try:
        dockerfile_text = materialize.apply_recommendation_entrypoint_guard(upstream_text)
    except RuntimeError as exc:
        raise GateError(
            f"upstream recommendation Dockerfile no longer carries the guarded anchor: {exc}"
        ) from exc
    return prove_recommendation_source_instrumentation_posture(dockerfile_text)


def _upstream_text(relative: str) -> str:
    return _read_file(UPSTREAM_ROOT / relative, f"upstream {relative}").decode("utf-8")


def _overlay_scalar(value: str, where: str) -> str:
    value = value.strip()
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GateError(f"{where}: malformed double-quoted overlay scalar") from exc
        if not isinstance(parsed, str):
            raise GateError(f"{where}: overlay scalar is not a string")
        return parsed
    if value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            raise GateError(f"{where}: malformed single-quoted overlay scalar")
        return value[1:-1].replace("''", "'")
    # Plain scalars: only the ``${VAR...}:/path:ro`` volume shape is written unquoted;
    # flow collections, comments, and YAML null spellings fail closed.
    if value[:1] in ("{", "[", "") or "]" in value or " #" in value or value in ("~", "null"):
        raise GateError(f"{where}: unsupported overlay scalar {value!r}")
    return value


@functools.lru_cache(maxsize=4)
def _parse_overlay(digest: str, text: str) -> Any:
    """Parse the candidate posture overlay once per distinct byte content.

    Standard library only: the target runs ``/usr/bin/python3 -I``, where PyYAML
    is not guaranteed. The overlay is framework-owned and written in the exact
    shape parsed here (``services:`` / two-space service / four-space
    ``entrypoint``|``environment``|``volumes`` / six-space items); anything else
    fails closed rather than being guessed. ``digest`` keys the cache.
    """
    services: dict[str, dict[str, Any]] = {}
    service: str | None = None
    section: str | None = None
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        where = f"candidate posture overlay line {number}"
        if indent == 0:
            if line != "services:":
                raise GateError(f"{where}: only a services mapping is allowed at the top level")
            continue
        if indent == 2 and line.endswith(":"):
            service = line[:-1]
            if not SAFE_NAME.fullmatch(service) or service in services:
                raise GateError(f"{where}: malformed or duplicate service {service!r}")
            services[service] = {}
            section = None
            continue
        if indent == 4 and line.endswith(":") and service is not None:
            section = line[:-1]
            if section not in ("entrypoint", "environment", "volumes") or section in services[service]:
                raise GateError(f"{where}: unsupported or duplicate service section {section!r}")
            services[service][section] = {} if section == "environment" else []
            continue
        if indent == 6 and service is not None and section is not None:
            if section == "environment":
                key, separator, value = line.partition(":")
                if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                    raise GateError(f"{where}: malformed environment entry")
                if key in services[service][section]:
                    raise GateError(f"{where}: duplicate environment key {key}")
                services[service][section][key] = _overlay_scalar(value, where)
            else:
                if not line.startswith("- "):
                    raise GateError(f"{where}: list item expected")
                services[service][section].append(_overlay_scalar(line[2:], where))
            continue
        raise GateError(f"{where}: unexpected indentation or structure")
    if not services:
        raise GateError("candidate posture overlay declares no services")
    return {"services": services}


def _overlay_document() -> dict[str, Any]:
    payload = _read_file(ROOT / COMPOSE_OVERLAYS[1], "candidate posture overlay")
    document = _parse_overlay(hashlib.sha256(payload).hexdigest(), payload.decode("utf-8"))
    services = document.get("services") if isinstance(document, dict) else None
    if not isinstance(services, dict):
        raise GateError("candidate posture overlay has no services mapping")
    return document


def overlay_service_entrypoints() -> dict[str, str]:
    """Guarded launches the candidate posture overlay gives the ghcr-image services.

    Parses the overlay YAML and undoes Compose's ``$$`` escape so the returned
    statement is what the container shell runs. Only services carrying an
    ``entrypoint`` are returned.
    """
    services = _overlay_document()["services"]
    result: dict[str, str] = {}
    for service, row in services.items():
        if not isinstance(row, dict) or "entrypoint" not in row:
            continue
        entrypoint = row["entrypoint"]
        if (
            not isinstance(entrypoint, list) or len(entrypoint) != 3
            or entrypoint[:2] != ["/bin/sh", "-c"] or not isinstance(entrypoint[2], str)
        ):
            raise GateError(f"{service} overlay entrypoint is not a /bin/sh -c statement")
        if "$" in entrypoint[2].replace("$$", ""):
            raise GateError(f"{service} overlay entrypoint leaks an unescaped $ to Compose interpolation")
        result[service] = entrypoint[2].replace("$$", "$")
    return result


def overlay_service_environment(service: str) -> dict[str, str]:
    row = _overlay_document()["services"].get(service, {})
    environment = row.get("environment", {}) if isinstance(row, dict) else {}
    if not isinstance(environment, dict):
        raise GateError(f"{service} overlay environment is not a mapping")
    return {str(key): str(value) for key, value in environment.items()}


def overlay_service_volumes(service: str) -> list[str]:
    row = _overlay_document()["services"].get(service, {})
    volumes = row.get("volumes", []) if isinstance(row, dict) else []
    if not isinstance(volumes, list):
        raise GateError(f"{service} overlay volumes is not a list")
    return [str(item) for item in volumes]


def verify_overlay_posture_controls() -> None:
    """Replay-safe text checks that the overlay wires every catalog control.

    The overlay bytes are digested in ``controllerDigests``; this makes the digest
    mean something by checking the wiring rather than trusting it.
    """
    entrypoints = overlay_service_entrypoints()
    expected_overlay_guards = {
        service: statement for service, statement in EXPECTED_ENTRYPOINT_GUARDS.items()
        if service != "recommendationservice"
    }
    if entrypoints != expected_overlay_guards:
        raise GateError(
            "candidate posture overlay entrypoints differ from the exported guard constants: "
            f"{sorted(entrypoints)} vs {sorted(expected_overlay_guards)}"
        )
    for service in expected_overlay_guards:
        key = service.replace("-", "_").upper()
        environment = overlay_service_environment(service)
        if environment.get("OTEL_PLACEMENT_ENABLED") != (
            f"${{OTEL_CANDIDATE_{key}_ENABLED:?candidate posture required}}"
        ):
            raise GateError(f"{service} overlay does not bind OTEL_PLACEMENT_ENABLED to its posture variable")
    for service, (variable, _value) in EXPECTED_AGENT_ENVIRONMENT.items():
        key = service.replace("-", "_").upper()
        expected = f"${{OTEL_CANDIDATE_{key}_{variable}?candidate posture required}}"
        if overlay_service_environment(service).get(variable) != expected:
            raise GateError(f"{service} overlay does not rebind {variable} per posture (expected {expected})")
    flagd = overlay_service_environment("flagd")
    if (
        flagd.get("FLAGD_OTEL_COLLECTOR_URI") != "${OTEL_CANDIDATE_FLAGD_OTEL_COLLECTOR_URI?candidate posture required}"
        or flagd.get("FLAGD_METRICS_EXPORTER") != "${OTEL_CANDIDATE_FLAGD_METRICS_EXPORTER?candidate posture required}"
    ):
        raise GateError("flagd overlay does not rebind its collector URI and metrics exporter per posture")
    if overlay_service_volumes("imageprovider") != [
        "${OTEL_CANDIDATE_IMAGEPROVIDER_NGINX_TEMPLATE:?candidate posture required}:/nginx.conf.template:ro"
    ]:
        raise GateError("imageprovider overlay does not mount the posture-selected nginx template")
    if overlay_service_volumes("frontendproxy") != [
        "${OTEL_CANDIDATE_ENVOY_CONFIG:?candidate posture required}:/home/envoy/envoy.tmpl.yaml:ro"
    ]:
        raise GateError("frontendproxy overlay does not mount the posture-selected Envoy template")
    for service in EXPECTED_SOURCE_PLACEMENT_GUARDS:
        key = service.replace("-", "_").upper()
        environment = overlay_service_environment(service)
        if environment.get("OTEL_PLACEMENT_ENABLED") != (
            f"${{OTEL_CANDIDATE_{key}_ENABLED:?candidate posture required}}"
        ):
            raise GateError(f"{service} overlay does not bind OTEL_PLACEMENT_ENABLED to its posture variable")


def verify_materializer_constants() -> None:
    """The materializer is the single render source; its constants must equal the
    independently declared expectations here (two statements, compared)."""
    materialize = _materialize_module()
    if getattr(materialize, "ENTRYPOINT_GUARDS", None) != EXPECTED_ENTRYPOINT_GUARDS:
        raise GateError("materializer entrypoint guards differ from the exported constants")
    if getattr(materialize, "AGENT_ENVIRONMENT", None) != EXPECTED_AGENT_ENVIRONMENT:
        raise GateError("materializer agent environment differs from the exported constants")
    if (
        getattr(materialize, "FLAGD_ENABLED_ENVIRONMENT", None) != EXPECTED_FLAGD_ENVIRONMENT["enabled"]
        or getattr(materialize, "FLAGD_DISABLED_ENVIRONMENT", None) != EXPECTED_FLAGD_ENVIRONMENT["disabled"]
    ):
        raise GateError("materializer flagd environment differs from the exported constants")
    if getattr(materialize, "SOURCE_PLACEMENT_GUARD_FILES", None) != EXPECTED_SOURCE_PLACEMENT_GUARD_FILES:
        raise GateError("materializer source placement guard files differ from the exported constants")
    if getattr(materialize, "SOURCE_PLACEMENT_GUARDS", None) != EXPECTED_SOURCE_PLACEMENT_GUARDS:
        raise GateError("materializer source placement guards differ from the exported constants")
    if (
        getattr(materialize, "METRIC_EXPORT_INTERVAL_EPOCHS", None) != METRIC_EXPORT_INTERVAL_STUDY_EPOCHS
        or getattr(materialize, "METRIC_EXPORT_INTERVAL_VARIABLE", None) != METRIC_EXPORT_INTERVAL_VARIABLE
    ):
        raise GateError("materializer metric export interval epochs or variable differ from the exported constants")


@functools.lru_cache(maxsize=1)
def prove_materialized_source_guards() -> dict[str, Any]:
    """Plan-time proof of every disabled-posture control against the real pinned
    upstream checkout. Requires ``upstream/opentelemetry-demo`` and ``/bin/sh``.

    * entrypoint guards: executed in both postures (recommendationservice through
      the materializer-rendered Dockerfile; accountingservice and paymentservice
      through the compose overlay statement), and the enabled branch is checked
      to be the exact upstream launch (Dockerfile ENTRYPOINT / package.json start).
    * JVM agents: the upstream Dockerfile ``ENV`` value equals the exported
      constant the overlay re-supplies when enabled.
    * flagd: the upstream ``.env`` collector host/port equal the pinned target.
    * imageprovider: the disabled nginx template renders from the upstream one
      with no otel directive left, and the upstream template still carries them.
    * in-code-SDK source guards (cartservice, checkoutservice, currencyservice,
      productcatalogservice, shippingservice): text-only. The pinned upstream
      anchor is proven present exactly once and the rendered guard text is
      proven present in the materialized output; this is NOT the behavioral
      proof the entrypoint guards get (there is no ``/bin/sh`` indirection to
      execute -- the guard is a conditional inside a compiled language this
      repo does not build or run without a container image build), so whether
      the patched source still compiles is unverified until a local image is
      actually built.
    """
    materialize = _materialize_module()
    verify_materializer_constants()
    proven: dict[str, Any] = {"recommendationservice": prove_materialized_recommendation_entrypoint()}
    overlay = overlay_service_entrypoints()
    for service in ("accountingservice", "paymentservice"):
        try:
            materialize.verify_upstream_entrypoint(_upstream_text(f"src/{service}/Dockerfile"), service)
            if service == "paymentservice":
                materialize.verify_payment_start_script(_upstream_text("src/paymentservice/package.json"))
        except (RuntimeError, ValueError) as exc:
            raise GateError(f"upstream {service} launch differs from the guarded launch: {exc}") from exc
        proven[service] = prove_entrypoint_guard(service, overlay[service])
    for service, (variable, expected) in EXPECTED_AGENT_ENVIRONMENT.items():
        try:
            observed = materialize.upstream_agent_environment(_upstream_text(f"src/{service}/Dockerfile"), service)
        except RuntimeError as exc:
            raise GateError(f"upstream {service} agent ENV differs: {exc}") from exc
        if observed != expected:
            raise GateError(f"upstream {service} {variable} differs from the exported constant")
        proven[service] = {variable: observed}
    try:
        materialize.verify_upstream_env_pins(_upstream_text(".env"))
        upstream_nginx = _upstream_text("src/imageprovider/nginx.conf.template")
        disabled_nginx = materialize.render_imageprovider_no_otel_template(upstream_nginx)
    except RuntimeError as exc:
        raise GateError(f"upstream imageprovider/flagd controls differ: {exc}") from exc
    if "load_module modules/ngx_otel_module.so;" not in upstream_nginx or "otel_trace on;" not in upstream_nginx:
        raise GateError("upstream imageprovider template no longer loads the otel module unconditionally")
    if "otel" in disabled_nginx or "${IMAGE_PROVIDER_PORT}" not in disabled_nginx:
        raise GateError("disabled imageprovider template is not otel-free or lost its port binding")
    proven["imageprovider"] = {"disabledTemplateSha256": hashlib.sha256(disabled_nginx.encode()).hexdigest()}
    proven["flagd"] = copy.deepcopy(EXPECTED_FLAGD_ENVIRONMENT)
    for service, relative in EXPECTED_SOURCE_PLACEMENT_GUARD_FILES.items():
        upstream_text = _upstream_text(relative)
        try:
            guarded_text = materialize.apply_source_placement_guards(upstream_text, service)
        except RuntimeError as exc:
            raise GateError(f"upstream {service} source guard anchor differs: {exc}") from exc
        for _anchor, replacement in EXPECTED_SOURCE_PLACEMENT_GUARDS[service]:
            if replacement not in guarded_text:
                raise GateError(f"{service} materialized source guard did not render into the guarded source")
        proven[service] = {"guardedSourceSha256": hashlib.sha256(guarded_text.encode()).hexdigest()}
    return proven


def _compiled_cells() -> list[dict[str, Any]]:
    """The 18 v1 cells the UNSUPPORTED ledger is written against (not the v2 plan)."""
    pilot = _frozen_pilot_module()
    plan = pilot.compile_plan(pilot.load_descriptor(UNSUPPORTED_DESCRIPTOR))
    return [
        copy.deepcopy(cell)
        for regime in plan["regimeRoots"]
        for block in regime["blocks"]
        for cell in block["cells"]
    ]


UNSUPPORTED_LEDGER_SCOPE = {
    "appliesToStudyEpochs": [UNSUPPORTED_STUDY_EPOCH],
    "supersededBy": {
        "studyEpoch": UNSUPPORTED_SUCCESSOR_EPOCH,
        "changeId": UNSUPPORTED_SUCCESSOR_CHANGE_ID,
        "descriptorPath": "pipelines/campaigns/otel-demo-candidate-pilot-v2.json",
    },
    "rule": (
        "this UNSUPPORTED disposition is the terminal result of study epoch "
        "otel-demo-candidate-pilot-v1 only; it neither blocks nor pre-judges any "
        "cell of a later study epoch, and no v1 cell is ever re-scored"
    ),
}


def validate_unsupported_evidence(document: Mapping[str, Any]) -> dict[str, Any]:
    """Replay the exact 18-cell v1 UNSUPPORTED disposition from frozen sources.

    The ledger is scoped to the superseded v1 epoch: its identity, descriptor
    digests and cell ids are checked against the byte-frozen v1 descriptor, not
    against the current study epoch, and its ``scope`` block must name the v2
    epoch as the successor so a reader cannot mistake it for a v2 verdict.
    """

    root = _exact(
        document,
        {
            "schemaVersion", "kind", "changeId", "studyEpoch", "module",
            "executionDisposition", "empiricalResultState", "frozenDesign",
            "targetBinding", "fundamentalReasons", "comparativePolicy",
            "cellLedger", "permissions", "gateStates", "maximumEvidenceLabel",
            "canonical", "promotionAuthorized", "scope",
        },
        "unsupported disposition",
    )
    frozen = _exact(
        root["frozenDesign"],
        {
            "descriptorPath", "descriptorByteSha256",
            "descriptorCanonicalSha256", "cellCount", "postures",
            "randomizedRepeatedBlocks", "separateCostAndFaultEffectWindows",
            "explicitFaultAndPathGroundTruth",
        },
        "unsupported frozen design",
    )
    target = _exact(
        root["targetBinding"],
        {
            "allocationPath", "allocationByteSha256",
            "preservedAsProvenanceOnly", "runtimeAuthority",
            "externalMutationAllowed",
        },
        "unsupported target binding",
    )
    policy = _exact(
        root["comparativePolicy"],
        {
            "unit", "requiredPostures", "partialBlockAllowed",
            "fullOnlyExecutionAllowed", "resultIfAnyRequiredPostureUnsupported",
        },
        "unsupported comparative policy",
    )
    permissions = _exact(
        root["permissions"],
        {
            "setupAllowed", "readinessAllowed", "launchAllowed",
            "statusOrFetchAllowed", "cellMutationAllowed",
            "externalMutationAllowed",
        },
        "unsupported permissions",
    )
    reasons = root["fundamentalReasons"]
    expected_reasons = [
        {
            "id": "none-posture-not-structurally-realizable",
            "scope": ["none"],
            "descriptorPointer": "/postureRealization/none",
            "detail": "The legacy source-off control leaves non-target application instrumentation active and does not establish the frozen none posture.",
        },
        {
            "id": "selected-posture-not-structurally-realizable",
            "scope": ["selected"],
            "descriptorPointer": "/postureRealization/selected",
            "detail": "No audited closure realizes only the selected target-path sensors while disabling all other application instrumentation.",
        },
        {
            "id": "comparative-block-invalid-without-all-postures",
            "scope": ["none", "selected", "full"],
            "descriptorPointer": "/analysis/comparativeUnit",
            "detail": "The frozen comparative unit is a complete (regime, block) containing none, selected, and full; unsupported required postures invalidate every block, so full-only cells may not run.",
        },
    ]
    if (
        root["schemaVersion"] != 1
        or root["kind"] != "otel-demo-candidate-unsupported-disposition-v1"
        or root["changeId"] != UNSUPPORTED_CHANGE_ID
        or root["studyEpoch"] != UNSUPPORTED_STUDY_EPOCH
        or root["module"] != "otel-demo"
        or root["executionDisposition"] != "unsupported"
        or root["empiricalResultState"] != "UNSUPPORTED"
        or root["maximumEvidenceLabel"] is not None
        or root["canonical"] is not False
        or root["promotionAuthorized"] is not False
        or root["scope"] != UNSUPPORTED_LEDGER_SCOPE
        or frozen != {
            "descriptorPath": str(UNSUPPORTED_DESCRIPTOR.relative_to(ROOT)),
            "descriptorByteSha256": file_sha256(UNSUPPORTED_DESCRIPTOR),
            "descriptorCanonicalSha256": _frozen_pilot_module().EPOCHS[UNSUPPORTED_STUDY_EPOCH]["expectedDescriptorSha256"],
            "cellCount": UNSUPPORTED_RUN_COUNT,
            "postures": ["none", "selected", "full"],
            "randomizedRepeatedBlocks": True,
            "separateCostAndFaultEffectWindows": True,
            "explicitFaultAndPathGroundTruth": True,
        }
        or target != {
            "allocationPath": str(TARGET_ALLOCATION.relative_to(ROOT)),
            "allocationByteSha256": file_sha256(TARGET_ALLOCATION),
            "preservedAsProvenanceOnly": True,
            "runtimeAuthority": False,
            "externalMutationAllowed": False,
        }
        or reasons != expected_reasons
        or policy != {
            "unit": "complete-(regime,block)",
            "requiredPostures": ["none", "selected", "full"],
            "partialBlockAllowed": False,
            "fullOnlyExecutionAllowed": False,
            "resultIfAnyRequiredPostureUnsupported": "UNSUPPORTED",
        }
        or permissions != {
            "setupAllowed": False,
            "readinessAllowed": False,
            "launchAllowed": False,
            "statusOrFetchAllowed": False,
            "cellMutationAllowed": False,
            "externalMutationAllowed": False,
        }
        or root["gateStates"] != {
            "GATE-PLAN": "not-requested",
            "GATE-SETUP": "not-requested",
            "GATE-RUN": "not-requested",
        }
    ):
        raise GateError("UNSUPPORTED disposition identity or authority differs")

    expected_rows: list[dict[str, Any]] = []
    for cell in _compiled_cells():
        posture = cell["runKey"]["posture"]
        reason_ids = []
        if posture == "none":
            reason_ids.append("none-posture-not-structurally-realizable")
        elif posture == "selected":
            reason_ids.append("selected-posture-not-structurally-realizable")
        reason_ids.append("comparative-block-invalid-without-all-postures")
        expected_rows.append({
            "runId": cell["runId"],
            "runKey": cell["runKey"],
            "artifactRoot": cell["artifactRoot"],
            "frozenRealizationStatus": cell["realizationStatus"],
            "empiricalResultState": "UNSUPPORTED",
            "externalAttempt": False,
            "numericResults": None,
            "reasonIds": reason_ids,
        })
    if root["cellLedger"] != expected_rows:
        raise GateError("exact 18-cell UNSUPPORTED ledger differs")
    return copy.deepcopy(dict(root))


def unsupported_evidence() -> dict[str, Any]:
    return validate_unsupported_evidence(
        _json_file(UNSUPPORTED_EVIDENCE, "OTel UNSUPPORTED evidence")
    )


def frozen_descriptor() -> dict[str, Any]:
    """The current study epoch's descriptor, loaded through the compiler's contract."""
    pilot = _pilot_module()
    if pilot.EPOCH != STUDY_EPOCH:
        raise GateError("compiler study epoch differs from the runtime study epoch")
    try:
        descriptor = pilot.load_descriptor(DESCRIPTOR)
    except ValueError as exc:
        raise GateError(f"frozen descriptor cannot be loaded: {exc}") from exc
    if descriptor.get("id") != STUDY_EPOCH:
        raise GateError("frozen descriptor id differs from the runtime study epoch")
    return descriptor


def verify_descriptor_bindings(descriptor: Mapping[str, Any], catalog: Mapping[str, Any]) -> None:
    """The v2 descriptor's target block and D13 claim boundary must be the same
    facts the target allocation and the posture catalog state, so the frozen
    design cannot name one execution user or one silenced-service set while the
    controllers install another."""
    allocation = target_allocation()
    identity = allocation["executionIdentities"][0]
    expected_target = {
        "host": allocation["host"],
        "transportUser": allocation["transportUsers"][0],
        "setupUser": allocation["setupUsers"][0],
        "executionUser": identity["user"],
        "executionUid": identity["uid"],
        "executionGid": identity["gid"],
        "dockerGid": allocation["docker"]["expectedGid"],
        "allocationPath": str(TARGET_ALLOCATION.relative_to(ROOT)),
        "leaseScope": "shared-srv6-host-exclusive-otel-then-online-boutique",
    }
    if descriptor.get("target") != expected_target:
        raise GateError("descriptor target identity differs from the reviewed srv6 allocation")
    for posture in POSTURES[:-1]:
        boundary = descriptor["postureRealization"][posture].get("claimBoundary")
        realization = catalog["postureRealization"][posture]
        if (
            not isinstance(boundary, dict)
            or boundary.get("label") != CLAIM_BOUNDARY_LABEL
            or boundary.get("semantics") != NONE_SEMANTICS
            or boundary.get("loadedButSilencedServices") != realization["silencedButLoadedServices"]
            or realization["claimBoundary"] != CLAIM_BOUNDARY_LABEL
        ):
            raise GateError(
                f"{posture} posture: descriptor claim boundary differs from the catalog's "
                "loaded-but-silenced service set"
            )
    if descriptor["postureRealization"]["full"].get("claimBoundary") is not None:
        raise GateError("full posture carries a claim boundary it cannot have")
    for posture in ("selected", "async"):
        if descriptor["postureRealization"][posture].get("closure") != catalog["postures"][posture]["activeApplicationServices"]:
            raise GateError(f"{posture} posture: descriptor closure differs from the catalog's")


def descriptor_posture_statuses() -> dict[str, str]:
    """``postureRealization.<posture>.status`` from the frozen descriptor this runtime binds."""
    realization = frozen_descriptor()["postureRealization"]
    return {posture: str(realization[posture]["status"]) for posture in POSTURES}


def unsupported_postures() -> list[str]:
    """Postures the frozen descriptor does not realize, cross-checked against the
    catalog's per-service realization.

    The catalog realization is *necessary* for a descriptor to claim a posture:
    a descriptor that says ``implemented`` while the per-service table does not
    is a gate failure.  Under the v2 descriptor all three postures are
    ``implemented`` and the catalog agrees (D13), so this is empty; the v1
    descriptor, still compiled for its UNSUPPORTED ledger, would return
    ``["none", "selected"]``.  When the descriptor claims a posture, its D13
    claim boundary and target block are additionally checked against the
    catalog and the target allocation (``verify_descriptor_bindings``).
    """
    descriptor = frozen_descriptor()
    statuses = {
        posture: str(descriptor["postureRealization"][posture]["status"])
        # The descriptor's own vocabulary: the superseded v1 shape (three
        # postures, two unrealized) must still refuse with its own identity.
        for posture in descriptor["design"]["postures"]
    }
    catalog = posture_catalog()
    for posture, status in statuses.items():
        realizable = catalog["postureRealization"][posture]["status"] == "implemented"
        if status == "implemented" and not realizable:
            raise GateError(
                f"{posture} posture: descriptor says {status!r} but the catalog realization "
                f"says {catalog['postureRealization'][posture]['status']!r}"
            )
    if all(status == "implemented" for status in statuses.values()):
        verify_descriptor_bindings(descriptor, catalog)
    return [posture for posture, status in statuses.items() if status != "implemented"]


def refuse_unsupported(operation: str) -> None:
    """Fail closed unless the frozen design realizes every posture AND the target
    controllers admit this study epoch.

    Two independent refusals, in order:

    1. ``unsupported_postures()`` -- a descriptor with an unrealized required
       posture (the superseded v1 shape) refuses with the UNSUPPORTED ledger's
       identity, exactly as the v1 tombstone did.
    2. ``admitted_study_epochs()`` -- the installed controllers' tombstone. The
       v2 descriptor realizes all three postures, so without this check the
       local chain would happily transport to fb14srv6 and stage a release
       before the remote controller refused it. Admitting an epoch is a
       governed edit of ``ADMITTED_STUDY_EPOCHS`` in ``candidate_setup.py``
       and ``candidate_remote.py`` (the same tuple in both), never of this
       function.
    """
    if not isinstance(operation, str) or not operation:
        raise GateError("UNSUPPORTED operation label is absent")
    missing = unsupported_postures()
    if missing:
        evidence = unsupported_evidence()
        raise GateError(
            f"{operation} refused: {evidence['studyEpoch']} is UNSUPPORTED; the frozen descriptor says "
            f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not structurally "
            "realizable, so no complete none/selected/full comparative block or full-only cell may run"
        )
    admitted = admitted_study_epochs()
    if STUDY_EPOCH not in admitted:
        raise GateError(
            f"{operation} refused: study epoch {STUDY_EPOCH} is not admitted by the installed target "
            f"controllers (ADMITTED_STUDY_EPOCHS = {admitted!r} in candidate_setup.py and "
            "candidate_remote.py) and is therefore UNSUPPORTED on the target until that governed edit "
            "lands; no setup, readiness capture, launch, status, fetch, or terminal validation may run"
        )


NONE_SEMANTICS = "no-telemetry-emitted"
CLAIM_BOUNDARY_LABEL = "loaded-but-silenced-instrumentation-still-runs-and-still-costs"


def _expected_realization(catalog: Mapping[str, Any], posture: str) -> dict[str, Any]:
    """Derive one posture's realization from the per-service disabled load states.

    Decision D13 (user, 2026-09-06) fixes the reading of ``none``: it means **no
    telemetry emitted**, not **no instrumentation loaded**.  ``implemented`` is
    therefore gated on ``blockingServices`` alone -- the ``loaded-exporting``
    services whose pinned SDK honours neither ``OTEL_SDK_DISABLED`` nor
    ``OTEL_*_EXPORTER=none`` and so emit in every posture, which is the only
    state that structurally breaks a disabled posture.

    ``loaded-silenced`` services are still computed and still reported, and they
    no longer block: their instrumentation is compiled or imported into the
    process, source-verified to export nothing, and still costs.  That residual
    cost is a **named claim boundary** carried in the evidence
    (``disabledSetSemantics`` + ``claimBoundary`` + the explicit
    ``silencedButLoadedServices`` list beside ``notLoadedServices``) so a reader
    of the proof cannot mistake this posture for "no instrumentation loaded".
    """
    active = set(catalog["postures"][posture]["activeApplicationServices"])
    rows = catalog["serviceInstrumentation"]
    buckets = {"loaded-exporting": [], "loaded-silenced": [], "not-loaded": []}
    for service in catalog["applicationServices"]:
        if service in active:
            continue
        buckets[rows[service]["disabledLoadState"]].append(service)
    blocking = sorted(buckets["loaded-exporting"])
    silenced = sorted(buckets["loaded-silenced"])
    return {
        "status": "implemented" if not blocking else "not-structurally-realizable",
        "disabledSetSemantics": NONE_SEMANTICS,
        "claimBoundary": CLAIM_BOUNDARY_LABEL if silenced else None,
        "blockingServices": blocking,
        "silencedButLoadedServices": silenced,
        "notLoadedServices": sorted(buckets["not-loaded"]),
    }


def posture_catalog() -> dict[str, Any]:
    catalog = _json_file(POSTURE_CATALOG, "posture catalog")
    _exact(
        catalog,
        {
            "schemaVersion", "kind", "applicationServices", "costApplicationServices",
            "postures", "proofRule", "disabledLoadStateVocabulary",
            "serviceInstrumentation", "postureRealization",
        },
        "posture catalog",
    )
    if _int(catalog["schemaVersion"], "posture catalog schema", 1) != 2:
        raise GateError("posture catalog schema differs")
    services = catalog["applicationServices"]
    if (
        catalog["kind"] != "otel-demo-candidate-posture-catalog"
        or not isinstance(services, list)
        or services != sorted(services)
        or len(services) != 19
        or len(set(services)) != len(services)
        or list(catalog["postures"]) != list(POSTURES)
        or list(catalog["postureRealization"]) != list(POSTURES)
        or catalog["costApplicationServices"]
        != [service for service in services if service != "loadgenerator"]
        or set(catalog["disabledLoadStateVocabulary"]) != set(DISABLED_LOAD_STATES)
    ):
        raise GateError("posture catalog identity differs")
    expected = {
        "none": [],
        "selected": list(SELECTED_CLOSURE),
        "async": list(ASYNC_CLOSURE),
        "full": services,
    }
    for posture, active in expected.items():
        row = catalog["postures"][posture]
        if (
            row.get("activeApplicationServices") != active
            or row.get("sourceInstrumentationLoadedServices") != active
            or row.get("envoyTracing") is not (posture != "none")
        ):
            raise GateError(f"{posture} posture closure differs")
    rule = catalog["proofRule"]
    # D13: the disabled posture is proven by emission, not by absence of code.
    # ``not-exporting`` admits both ``not-loaded`` and ``loaded-silenced``;
    # ``loaded-exporting`` is the only state that still breaks the posture.
    if (
        rule.get("nestedLattice") != "none-subset-selected-subset-async-subset-full"
        or rule.get("disabledLoadStateRequired") != "not-exporting"
        or rule.get("zeroStartupApplicationSignalsRequiredForNone") is not True
        or rule.get("noneSemantics") != NONE_SEMANTICS
        or rule.get("loadedButSilencedIsClaimBoundaryNotBlocker") is not True
    ):
        raise GateError("posture proof rule differs")
    rows = catalog["serviceInstrumentation"]
    if not isinstance(rows, dict) or list(rows) != services:
        raise GateError("service instrumentation table does not cover exactly the application services")
    guarded = (
        set(EXPECTED_ENTRYPOINT_GUARDS)
        | set(EXPECTED_AGENT_ENVIRONMENT)
        | set(EXPECTED_SOURCE_PLACEMENT_GUARDS)
        | {"imageprovider", "frontend", "frontendproxy", "quoteservice"}
    )
    for service, row in rows.items():
        keys = {
            "language", "mechanism", "upstreamLoadSite", "disabledControl",
            "disabledControlSite", "disabledLoadState", "runtimeProbe",
        }
        if row.get("mechanism") == "in-code-sdk":
            keys |= {"sdkEnvironmentSwitches", "sdkEvidence"}
        _exact(row, keys, f"{service} instrumentation")
        if (
            row["mechanism"] not in INSTRUMENTATION_MECHANISMS
            or row["disabledLoadState"] not in DISABLED_LOAD_STATES
            or (row["disabledLoadState"] == "not-loaded") != (service in guarded)
            or (row["disabledControl"] == "none-available") != (row["disabledLoadState"] == "loaded-exporting")
            or (row["disabledControlSite"] is None) != (row["disabledControl"] == "none-available")
        ):
            raise GateError(f"{service} instrumentation classification differs")
        probe = row["runtimeProbe"]
        if probe is not None:
            if not isinstance(probe, dict) or probe.get("kind") not in PROBE_KINDS:
                raise GateError(f"{service} runtime probe kind differs")
            if probe["kind"] in ("container-env", "pid1-environ") and not probe.get("variable"):
                raise GateError(f"{service} runtime probe names no variable")
            if probe["kind"] == "container-file" and not probe.get("path"):
                raise GateError(f"{service} runtime probe names no path")
            if not any(key in probe for key in ("loadedWhenContains", "loadedWhenEquals")):
                raise GateError(f"{service} runtime probe has no loaded marker")
    for posture in POSTURES:
        realization = catalog["postureRealization"][posture]
        _exact(
            realization,
            {
                "status", "rule", "disabledSetSemantics", "claimBoundary",
                "blockingServices", "silencedButLoadedServices", "notLoadedServices",
            },
            f"{posture} realization",
        )
        derived = _expected_realization(catalog, posture)
        if {key: realization[key] for key in derived} != derived:
            raise GateError(f"{posture} posture realization differs from the per-service classification")
    # Replay-safe: text equality against the plan-time-proven constants. No upstream
    # checkout, no /bin/sh -- terminal replay of retained evidence must not need either.
    verify_recommendation_source_instrumentation_posture(
        rendered_recommendation_entrypoint_command()
    )
    verify_materializer_constants()
    verify_overlay_posture_controls()
    return copy.deepcopy(catalog)


def expected_service_control(catalog: Mapping[str, Any], posture: str, service: str) -> dict[str, Any]:
    """Expected instrumentation control and load state for one service in a posture."""
    active = service in catalog["postures"][posture]["activeApplicationServices"]
    row = catalog["serviceInstrumentation"][service]
    return {
        "mechanism": row["mechanism"],
        "expectedControl": "enabled" if active else "disabled",
        "expectedLoadState": "loaded" if active else row["disabledLoadState"],
        "probe": copy.deepcopy(row["runtimeProbe"]),
    }


UPSTREAM_ENVOY_CONFIG = "src/frontendproxy/envoy.tmpl.yaml"
ENVOY_SERVICE_NAME_KEY = "service_name:"


def envoy_tracer_service_name(text: str) -> str:
    """The one ``service_name`` the pinned Envoy config gives its tracer.

    Exact key match on stripped lines, not a pattern: the pinned 1.12.0 config
    has exactly one such key (the OpenTelemetry tracer's), and any other count
    means the config is not the one this table was written against.
    """
    values = [
        line.strip()[len(ENVOY_SERVICE_NAME_KEY):].strip()
        for line in text.splitlines()
        if line.strip().startswith(ENVOY_SERVICE_NAME_KEY)
    ]
    if len(values) != 1 or not values[0] or SAFE_NAME.fullmatch(values[0]) is None:
        raise GateError(f"pinned Envoy config does not declare exactly one tracer service_name: {values!r}")
    return values[0]


def span_service_aliases() -> dict[str, str]:
    """The controller's explicit span-name -> catalog-id table, verified.

    Refuses unless the table in candidate_remote.SPAN_SERVICE_ALIASES is exactly
    {<pinned Envoy tracer service_name>: "frontendproxy"}, and every alias
    target is a catalog application service.
    """
    remote = _controller_module("remote-compose-controller", "otel_candidate_runtime_remote_aliases")
    table = dict(getattr(remote, "SPAN_SERVICE_ALIASES", {}) or {})
    envoy_name = envoy_tracer_service_name(_upstream_text(UPSTREAM_ENVOY_CONFIG))
    if table != {envoy_name: "frontendproxy"}:
        raise GateError(
            f"span service alias table {table!r} differs from the pinned Envoy tracer "
            f"service_name {envoy_name!r} -> 'frontendproxy'"
        )
    if not set(table.values()) <= set(posture_catalog()["applicationServices"]):
        raise GateError("span service alias targets a service outside the catalog")
    if getattr(remote, "COLLECTOR_SELF_SERVICE", None) != "otelcol":
        raise GateError("collector self-service name differs")
    return table


def posture_config_document(cell: Mapping[str, Any]) -> dict[str, Any]:
    """The bytes a cell's posture configuration is identified by.

    Producer (target) and terminal validator compute this from the same cell
    contract, so the digest compares bit-exactly (strings only, no floats).
    """
    return {
        "posture": cell["posture"]["id"],
        "environment": {str(key): str(value) for key, value in cell["posture"]["environment"].items()},
        "controllerDigests": {
            name: cell["installedControllerDigests"][name]
            for name in ("base-compose-overlay", "candidate-posture-overlay", "posture-catalog", "materializer")
        },
        "materializedSourceSha256": cell["materializedSourceSha256"],
    }


def posture_config_sha256(cell: Mapping[str, Any]) -> str:
    return canonical_sha256(posture_config_document(cell))


def posture_config_sha256_for_binding(binding: Mapping[str, Any], posture: str) -> str:
    """The same digest a cell contract of ``posture`` under ``binding`` will carry;
    used by the zero-cell readiness seams before any cell contract exists."""
    return canonical_sha256({
        "posture": posture,
        "environment": posture_environment(posture, binding["remoteSourceRoot"]),
        "controllerDigests": {
            name: binding["controllerDigests"][name]
            for name in ("base-compose-overlay", "candidate-posture-overlay", "posture-catalog", "materializer")
        },
        "materializedSourceSha256": binding["expectedMaterializedSourceSha256"],
    })


def target_allocation() -> dict[str, Any]:
    allocation = _json_file(TARGET_ALLOCATION, "target allocation")
    _exact(allocation, {
        "schemaVersion", "kind", "host", "transportUsers", "setupUsers",
        "executionIdentities", "releaseParent", "artifactParent", "leasePath",
        "projectPrefix", "reservedPorts", "freshReadinessAfter",
        "readinessRequirements", "docker", "source", "compose", "isolation",
        "handoff", "claimBoundary",
    }, "target allocation")
    _exact(allocation["executionIdentities"][0], {"user", "uid", "gid", "supplementalGids"}, "execution identity")
    _exact(allocation["docker"], {"expectedGid", "expectedVersion"}, "Docker target")
    _exact(allocation["source"], {"submodulePath", "upstreamCommit"}, "source target")
    _exact(allocation["compose"], {"projectRule", "ports"}, "allocated Compose")
    _exact(allocation["isolation"], {
        "foreignActiveDockerResourcesAllowed", "foreignExitedProjectsAndVolumesPolicy",
        "competingExperimentLeasesAllowed", "noOverlappingHostLocalCostWindows",
    }, "allocated isolation")
    _exact(allocation["handoff"], {"predecessor", "successor", "successorRequires"}, "host handoff")
    expected_projection = {
        "host": "fb14srv6", "transportUsers": ["root"], "setupUsers": ["root"],
        "executionIdentities": [{"user": "stig", "uid": 1016, "gid": 1016, "supplementalGids": [998]}],
        "releaseParent": "/home/stig/observability-placement-candidate-v4-otel-srv6",
        "artifactParent": "/home/stig/observability-placement-candidate-v4-runs",
        "leasePath": "/home/stig/observability-placement-candidate-v4-runs/.srv6-runtime.lock",
        "projectPrefix": "otel_candidate_v4",
        "reservedPorts": [18080, 18081, 18082, 18083, 18084],
        "freshReadinessAfter": None,
        "readinessRequirements": [
            "exact non-symlink installed release with source digest replay",
            "controller-only artifact root after setup with no candidate result entries",
            "no foreign active containers or active compose projects",
            "shared srv6 lease available and reserved ports free",
            "foreign exited projects and volumes inventoried and preserved",
            "installed controller bytes and built image ids match the setup receipt",
        ],
    }
    if {key: allocation[key] for key in expected_projection} != expected_projection:
        raise GateError("target contract projection differs from the reviewed srv6 allocation")
    if (
        allocation["schemaVersion"] != 2
        or allocation["kind"] != "otel-demo-candidate-target-contract-v2"
        or allocation["docker"] != {"expectedGid": 998, "expectedVersion": "29.6.1"}
        or allocation["source"] != {"submodulePath": "upstream/opentelemetry-demo", "upstreamCommit": "2d4661e4897aa7b2d2ddbb5ef8c4824ca8a1b88d"}
        or allocation["compose"]["projectRule"] != "project-prefix-plus-campaign-id"
        or list(allocation["compose"]["ports"].values()) != allocation["reservedPorts"]
        or allocation["isolation"] != {
            "foreignActiveDockerResourcesAllowed": False,
            "foreignExitedProjectsAndVolumesPolicy": "inventory-and-preserve",
            "competingExperimentLeasesAllowed": False,
            "noOverlappingHostLocalCostWindows": True,
        }
        or allocation["handoff"].get("successor") != "online-boutique"
    ):
        raise GateError("target allocation differs from the reviewed srv6 amendment")
    for key in ("releaseParent", "artifactParent", "leasePath"):
        _safe_posix(allocation[key], f"allocated {key}", absolute=True)
    return copy.deepcopy(allocation)


def controller_digests() -> dict[str, str]:
    return {name: file_sha256(ROOT / relative) for name, relative in CONTROLLER_PATHS.items()}


@dataclass(frozen=True)
class PlanBindings:
    root: Path
    descriptor: dict[str, Any]
    plan: dict[str, Any]
    descriptor_sha256: str
    plan_sha256: str
    run_ids: tuple[str, ...]
    cells: tuple[dict[str, Any], ...]
    controller_sha256: dict[str, str]
    attempt: int


def inspect_compiled_plan(root: Path) -> PlanBindings:
    root = Path(root).resolve()
    descriptor = _json_file(root / "campaign-descriptor.json", "candidate descriptor")
    plan = _json_file(root / "compiled-plan.json", "compiled plan")
    pilot = _pilot_module()
    try:
        pilot.validate_plan(descriptor, plan)
    except ValueError as exc:
        raise GateError(f"candidate plan replay failed: {exc}") from exc
    cells: list[dict[str, Any]] = []
    for regime in plan.get("regimeRoots", []):
        for block in regime["blocks"]:
            cells.extend(copy.deepcopy(block["cells"]))
    # A parameterised epoch compiles its execution order block by block (seeded across regimes and rates).
    for block in plan.get("blocks", []):
        cells.extend(copy.deepcopy(block["cells"]))
    run_ids = tuple(cell["runId"] for cell in cells)
    try:
        attempt = pilot.plan_attempt(plan)
    except ValueError as exc:
        raise GateError(f"candidate plan attempt is not one positive integer: {exc}") from exc
    if (
        len(cells) != RUN_COUNT
        or len(set(run_ids)) != RUN_COUNT
        or any(cell["runKey"].get("attempt") != attempt for cell in cells)
    ):
        raise GateError(f"candidate plan is not the exact {RUN_COUNT}-cell single-attempt population")
    posture_catalog()
    # Plan-time only: execute every guarded launch against a stubbed PATH and check
    # every disabled-posture control against the real pinned upstream checkout.
    prove_materialized_source_guards()
    target_allocation()
    span_service_aliases()
    return PlanBindings(
        root=root,
        descriptor=copy.deepcopy(descriptor),
        plan=copy.deepcopy(plan),
        descriptor_sha256=canonical_sha256(descriptor),
        plan_sha256=canonical_sha256(plan),
        run_ids=run_ids,
        cells=tuple(cells),
        controller_sha256=controller_digests(),
        attempt=attempt,
    )


def compose_project_for(campaign_id: str, project_prefix: str) -> str:
    """Derive the Compose project name from the campaign id, separately.

    The campaign id and the Compose project name are two different strings and
    this function is the seam between them. The campaign id is HYPHENATED
    (`otel-demo-candidate-pilot-v2`) because the shared gate-driver library's
    `gate_run_flow._SAFE_CAMPAIGN_SLUG` (`[a-z0-9][a-z0-9-]{0,63}`) rejects an
    underscore, and that validator is shared with TeaStore and Hotel; the
    Compose project keeps the UNDERSCORE spelling this module has always
    produced (`otel_candidate_v4_otel_demo_candidate_pilot_v2`), which is what
    `candidate_remote.EXPECTED_PROJECT_PREFIX` and the
    `systemdUnit == f"{composeProject}.service"` guard were written against.

    Doing the conversion here rather than in the campaign id itself is what
    keeps every path-to-id guard on the target intact: `validate_package`
    asserts `root.name == document["campaignId"]` and `_bounded_abort_identity`
    rebuilds `EXPECTED_ARTIFACT_PARENT / campaignId`, so the artifact root must
    stay named after the id, not after the Compose project.
    """
    project = f"{project_prefix}_{campaign_id.replace('-', '_')}"
    if SAFE_NAME.fullmatch(project) is None:
        raise GateError("derived Compose project is unsafe")
    return project


def operational_binding(
    bindings: PlanBindings,
    *,
    framework_commit: str,
    campaign_id: str,
    repository_bundle_sha256: str,
    upstream_bundle_sha256: str,
    expected_materialized_source_sha256: str,
) -> dict[str, Any]:
    if not isinstance(framework_commit, str) or HEX40.fullmatch(framework_commit) is None:
        raise GateError("framework commit must be one full lowercase commit")
    if (
        not isinstance(campaign_id, str)
        or SAFE_NAME.fullmatch(campaign_id) is None
        or len(campaign_id) > 40
    ):
        raise GateError("campaign name is unsafe")
    for value, where in (
        (repository_bundle_sha256, "repository bundle"),
        (upstream_bundle_sha256, "upstream bundle"),
        (expected_materialized_source_sha256, "materialized source"),
    ):
        if not isinstance(value, str) or HEX64.fullmatch(value) is None:
            raise GateError(f"{where} digest is invalid")
    allocation = target_allocation()
    release_root = f"{allocation['releaseParent']}/{campaign_id}-{framework_commit[:12]}"
    repository_root = f"{release_root}/repository"
    remote_source_root = f"{release_root}/source"
    remote_artifact_root = f"{allocation['artifactParent']}/{campaign_id}"
    setup_staging_root = f"{allocation['artifactParent']}/.setup-{campaign_id}"
    compose_project = compose_project_for(campaign_id, allocation["projectPrefix"])
    projection_keys = (
        "host", "transportUsers", "setupUsers", "executionIdentities",
        "releaseParent", "artifactParent", "leasePath", "projectPrefix",
        "reservedPorts", "freshReadinessAfter", "readinessRequirements",
    )
    return {
        "studyEpoch": STUDY_EPOCH,
        "changeId": CHANGE_ID,
        "frameworkCommit": framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "controllerDigests": copy.deepcopy(bindings.controller_sha256),
        "authorizedRunIds": list(bindings.run_ids),
        "runCount": RUN_COUNT,
        "attempt": bindings.attempt,
        "campaignId": campaign_id,
        "targetContractSha256": file_sha256(TARGET_ALLOCATION),
        "targetContractProjection": {key: copy.deepcopy(allocation[key]) for key in projection_keys},
        "target": {
            "host": allocation["host"], "transportUser": "root", "setupUser": "root",
            "executionIdentity": copy.deepcopy(allocation["executionIdentities"][0]),
        },
        "compose": {
            "project": compose_project, "projectPrefix": allocation["projectPrefix"],
            "ports": copy.deepcopy(allocation["compose"]["ports"]),
        },
        "releaseRoot": release_root,
        "repositoryRoot": repository_root,
        "remoteSourceRoot": remote_source_root,
        "remoteArtifactRoot": remote_artifact_root,
        "setupStagingRoot": setup_staging_root,
        "exclusiveLeasePath": allocation["leasePath"],
        "leaseScope": "shared-srv6-host-exclusive-otel-then-online-boutique",
        "repositoryBundleSha256": repository_bundle_sha256,
        "upstreamBundleSha256": upstream_bundle_sha256,
        "upstreamCommit": allocation["source"]["upstreamCommit"],
        "expectedMaterializedSourceSha256": expected_materialized_source_sha256,
        "handoff": copy.deepcopy(allocation["handoff"]),
        "evidenceLabel": EVIDENCE_LABEL,
        "oneShot": True,
        "retryAllowed": False,
        "substitutionAllowed": False,
        "rerandomizationAllowed": False,
    }


def expected_gate_plan_text(binding: Mapping[str, Any]) -> str:
    return (
        f"APPROVE GATE-PLAN study={STUDY_EPOCH} change={CHANGE_ID} "
        f"campaign={binding['campaignId']} transport=root@{binding['target']['host']} execution=stig:1016:1016+998 "
        f"source={binding['remoteSourceRoot']} artifacts={binding['remoteArtifactRoot']} "
        f"framework={binding['frameworkCommit']} plan={binding['compiledPlanCanonicalSha256']} "
        f"repo-bundle={binding['repositoryBundleSha256']} upstream-bundle={binding['upstreamBundleSha256']} "
        f"materialized-source={binding['expectedMaterializedSourceSha256']} target-contract={binding['targetContractSha256']} "
        f"runs={RUN_COUNT} attempt={binding['attempt']} one-shot no-retry no-substitution "
        f"no-rerandomization maximum-evidence={EVIDENCE_LABEL} runtime-not-authorized"
    )


def validate_gate_plan(document: Any, bindings: PlanBindings) -> tuple[dict[str, Any], str]:
    root = _exact(
        document,
        {
            "schemaVersion", "kind", "gate", "decision", "typedApproval",
            "approvedBy", "approvedAt", "binding", "runtimeAuthorized",
            "promotionAuthorized",
        },
        "GATE-PLAN",
    )
    binding = root["binding"]
    if not isinstance(binding, dict):
        raise GateError("GATE-PLAN binding is not an object")
    expected = operational_binding(
        bindings,
        framework_commit=binding.get("frameworkCommit"),
        campaign_id=binding.get("campaignId"),
        repository_bundle_sha256=binding.get("repositoryBundleSha256"),
        upstream_bundle_sha256=binding.get("upstreamBundleSha256"),
        expected_materialized_source_sha256=binding.get("expectedMaterializedSourceSha256"),
    )
    if (
        _int(root["schemaVersion"], "GATE-PLAN schema", 1) != 1
        or root["kind"] != PLAN_KIND
        or root["gate"] != "GATE-PLAN"
        or root["decision"] != "approve-exact-plan"
        or canonical_bytes(binding) != canonical_bytes(expected)
        or root["typedApproval"] != expected_gate_plan_text(expected)
        or not isinstance(root["approvedBy"], str)
        or not root["approvedBy"].strip()
        or root["runtimeAuthorized"] is not False
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-PLAN identity, exact scope, or authority ceiling differs")
    _timestamp(root["approvedAt"], "GATE-PLAN approvedAt")
    return copy.deepcopy(root), canonical_sha256(root)


def setup_binding(plan: Mapping[str, Any], plan_sha256: str) -> dict[str, Any]:
    binding = plan["binding"]
    return {
        "studyEpoch": STUDY_EPOCH,
        "campaignId": binding["campaignId"],
        "target": copy.deepcopy(binding["target"]),
        "executionIdentity": copy.deepcopy(binding["target"]["executionIdentity"]),
        "gatePlanSha256": plan_sha256,
        "targetContractSha256": binding["targetContractSha256"],
        "repositoryBundleSha256": binding["repositoryBundleSha256"],
        "upstreamBundleSha256": binding["upstreamBundleSha256"],
        "upstreamCommit": binding["upstreamCommit"],
        "expectedMaterializedSourceSha256": binding["expectedMaterializedSourceSha256"],
        "releaseRoot": binding["releaseRoot"],
        "repositoryRoot": binding["repositoryRoot"],
        "remoteSourceRoot": binding["remoteSourceRoot"],
        "remoteArtifactRoot": binding["remoteArtifactRoot"],
        "setupStagingRoot": binding["setupStagingRoot"],
        "exclusiveLeasePath": binding["exclusiveLeasePath"],
        "compose": copy.deepcopy(binding["compose"]),
        "oneShot": True,
        "setupOnly": True,
        "readinessProbeAuthorized": True,
        "cellsAuthorized": 0,
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }


def expected_gate_setup_text(binding: Mapping[str, Any]) -> str:
    return (
        f"APPROVE GATE-SETUP campaign={binding['campaignId']} "
        f"transport=root@{binding['target']['host']} execution=stig:1016:1016+998 "
        f"gate-plan={binding['gatePlanSha256']} release={binding['releaseRoot']} "
        f"artifacts={binding['remoteArtifactRoot']} repo-bundle={binding['repositoryBundleSha256']} "
        f"upstream-bundle={binding['upstreamBundleSha256']} source={binding['expectedMaterializedSourceSha256']} "
        "one-shot setup-only pull-build zero-cell-readiness cells=0 runtime-not-authorized"
    )


def validate_gate_setup(
    document: Any,
    plan: Mapping[str, Any],
    plan_sha256: str,
    *,
    now: datetime,
) -> str:
    root, digest = validate_gate_setup_reference(document, plan, plan_sha256)
    if now.tzinfo != timezone.utc:
        raise GateError("setup clock must be timezone-aware UTC")
    approved = _timestamp(root["approvedAt"], "GATE-SETUP approvedAt")
    age = math.floor((now - approved).total_seconds())
    if age < -5 or age > MAX_GATE_AGE_SECONDS:
        raise GateError("GATE-SETUP is not fresh")
    return digest


def validate_gate_setup_reference(
    document: Any,
    plan: Mapping[str, Any],
    plan_sha256: str,
) -> tuple[dict[str, Any], str]:
    """Replay immutable setup authority without reusing it as runtime authority.

    The setup receipt proves that this exact, once-fresh gate was consumed.
    Runtime authorization is independently temporal: a fresh target readiness
    and a later, fresh GATE-RUN are both mandatory.
    """
    root = _exact(document, {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "binding", "runtimeAuthorized",
        "promotionAuthorized",
    }, "GATE-SETUP")
    expected = setup_binding(plan, plan_sha256)
    if (
        _int(root["schemaVersion"], "GATE-SETUP schema", 1) != 1
        or root["kind"] != SETUP_KIND
        or root["gate"] != "GATE-SETUP"
        or root["decision"] != "authorize-one-shot-exact-setup"
        or canonical_bytes(root["binding"]) != canonical_bytes(expected)
        or root["typedApproval"] != expected_gate_setup_text(expected)
        or not isinstance(root["approvedBy"], str)
        or not root["approvedBy"].strip()
        or root["runtimeAuthorized"] is not False
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-SETUP identity, exact scope, or authority ceiling differs")
    _timestamp(root["approvedAt"], "GATE-SETUP approvedAt")
    return copy.deepcopy(root), canonical_sha256(root)


@dataclass(frozen=True)
class SetupPackage:
    bindings: PlanBindings
    gate_plan: dict[str, Any]
    gate_plan_sha256: str
    gate_setup: dict[str, Any]
    gate_setup_sha256: str
    validated_at: datetime


@dataclass(frozen=True)
class ReadinessRequest:
    bindings: PlanBindings
    gate_plan: dict[str, Any]
    gate_plan_sha256: str
    gate_setup: dict[str, Any]
    gate_setup_sha256: str
    setup_receipt: dict[str, Any]
    setup_receipt_sha256: str


def authorize_setup_from_files(
    campaign_root: Path,
    gate_plan_path: Path,
    gate_setup_path: Path,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> SetupPackage:
    bindings = inspect_compiled_plan(campaign_root)
    plan, plan_sha = validate_gate_plan(_json_file(Path(gate_plan_path), "GATE-PLAN"), bindings)
    now = clock()
    setup = _json_file(Path(gate_setup_path), "GATE-SETUP")
    setup_sha = validate_gate_setup(setup, plan, plan_sha, now=now)
    return SetupPackage(bindings, plan, plan_sha, copy.deepcopy(setup), setup_sha, now)


def authorize_readiness_from_files(
    campaign_root: Path,
    gate_plan_path: Path,
    gate_setup_path: Path,
    setup_receipt_path: Path,
) -> ReadinessRequest:
    bindings = inspect_compiled_plan(campaign_root)
    plan, plan_sha = validate_gate_plan(
        _json_file(Path(gate_plan_path), "GATE-PLAN"), bindings
    )
    setup = _json_file(Path(gate_setup_path), "GATE-SETUP")
    _, setup_sha = validate_gate_setup_reference(setup, plan, plan_sha)
    receipt, receipt_sha = validate_setup_receipt(
        _json_file(Path(setup_receipt_path), "setup receipt"),
        plan, plan_sha, setup_sha,
    )
    validate_consumed_gate_setup(setup, receipt)
    return ReadinessRequest(
        bindings, plan, plan_sha, copy.deepcopy(setup), setup_sha,
        receipt, receipt_sha,
    )


def setup_execution_package(package: SetupPackage) -> dict[str, Any]:
    binding = package.gate_plan["binding"]
    return {
        "schemaVersion": 1,
        "kind": SETUP_PACKAGE_KIND,
        "campaignId": binding["campaignId"],
        "studyEpoch": STUDY_EPOCH,
        "frameworkCommit": binding["frameworkCommit"],
        "gatePlanSha256": package.gate_plan_sha256,
        "gateSetupSha256": package.gate_setup_sha256,
        "targetContractSha256": binding["targetContractSha256"],
        "target": {
            "host": binding["target"]["host"],
            "transportUser": binding["target"]["transportUser"],
            "setupUser": binding["target"]["setupUser"],
        },
        "executionIdentity": copy.deepcopy(binding["target"]["executionIdentity"]),
        "repositoryBundleSha256": binding["repositoryBundleSha256"],
        "upstreamBundleSha256": binding["upstreamBundleSha256"],
        "upstreamCommit": binding["upstreamCommit"],
        "releaseRoot": binding["releaseRoot"],
        "repositoryRoot": binding["repositoryRoot"],
        "remoteSourceRoot": binding["remoteSourceRoot"],
        "remoteArtifactRoot": binding["remoteArtifactRoot"],
        "setupStagingRoot": binding["setupStagingRoot"],
        "leasePath": binding["exclusiveLeasePath"],
        "composeProject": binding["compose"]["project"],
        "ports": copy.deepcopy(binding["compose"]["ports"]),
        "controllerDigests": copy.deepcopy(binding["controllerDigests"]),
        "expectedMaterializedSourceSha256": binding["expectedMaterializedSourceSha256"],
        "oneShot": True,
        "readinessProbeAuthorized": True,
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }


def expected_load_states(posture: str) -> dict[str, str]:
    """Per-service expected instrumentation load state for ``posture`` (catalog-derived)."""
    catalog = posture_catalog()
    return {
        service: expected_service_control(catalog, posture, service)["expectedLoadState"]
        for service in catalog["applicationServices"]
    }


def _service_matrix(observation: Mapping[str, Any], posture: str) -> None:
    catalog = posture_catalog()
    expected = catalog["postures"][posture]
    _exact(
        observation,
        {
            "posture", "activeApplicationServices",
            "sourceInstrumentationLoadedServices", "renderedComposeActiveServices",
            "instrumentationLoadStates", "postureConfigSha256",
            "sourceDigestObservedEveryPatchedImage", "zeroStartupApplicationSignals",
        },
        f"{posture} posture observation",
    )
    if (
        observation["posture"] != posture
        or observation["activeApplicationServices"] != expected["activeApplicationServices"]
        or observation["sourceInstrumentationLoadedServices"]
        != expected["sourceInstrumentationLoadedServices"]
        or observation["renderedComposeActiveServices"]
        != expected["activeApplicationServices"]
        or observation["instrumentationLoadStates"] != expected_load_states(posture)
        or HEX64.fullmatch(str(observation["postureConfigSha256"])) is None
        or observation["sourceDigestObservedEveryPatchedImage"] is not True
        or (posture == "none" and observation["zeroStartupApplicationSignals"] is not True)
        or (posture != "none" and observation["zeroStartupApplicationSignals"] is not None)
    ):
        raise GateError(f"{posture} posture is not exactly realized")


def validate_seam(seam: str, observation: Any, binding: Mapping[str, Any]) -> None:
    if seam not in READINESS_SEAMS or not isinstance(observation, dict):
        raise GateError("unknown or malformed readiness seam")
    target = binding["target"]
    if seam == "target-contract-projection":
        _exact(observation, {"targetContractSha256", "projection"}, seam)
        if (
            observation["targetContractSha256"] != binding["targetContractSha256"]
            or canonical_bytes(observation["projection"]) != canonical_bytes(binding["targetContractProjection"])
        ):
            raise GateError("target contract projection differs")
    elif seam == "target-identity":
        _exact(observation, {"host", "transportUser", "setupUser", "executionUser", "uid", "gid", "supplementalGids", "architecture", "kernel", "observedAt"}, seam)
        identity = target["executionIdentity"]
        if (
            observation["host"] != target["host"]
            or observation["transportUser"] != "root"
            or observation["setupUser"] != "root"
            or observation["executionUser"] != identity["user"]
            or observation["uid"] != identity["uid"]
            or observation["gid"] != identity["gid"]
            or observation["supplementalGids"] != identity["supplementalGids"]
        ):
            raise GateError("target identity differs")
        if not all(isinstance(observation[key], str) and observation[key] for key in ("architecture", "kernel")):
            raise GateError("target platform observation is empty")
        _timestamp(observation["observedAt"], "target observedAt")
    elif seam == "target-root-and-host-isolation":
        _exact(
            observation,
            {
                "target", "releaseRoot", "repositoryRoot", "remoteSourceRoot", "sourceRootOwner",
                "sourceRootWritableByExecutionUser", "sourceRootIsSymlink",
                "remoteArtifactParent", "artifactParentOwner",
                "artifactParentTraversableByExecutionUser", "remoteArtifactRoot",
                "artifactRootOwner", "artifactRootWritableByExecutionUser",
                "exclusiveLeasePath", "leaseOwner", "leaseGroup", "leaseMode",
                "observedAt",
            },
            seam,
        )
        allocation = target_allocation()
        expected = {
            "target": copy.deepcopy(binding["target"]),
            "releaseRoot": binding["releaseRoot"],
            "repositoryRoot": binding["repositoryRoot"],
            "remoteSourceRoot": binding["remoteSourceRoot"],
            "sourceRootOwner": "root",
            "sourceRootWritableByExecutionUser": False,
            "sourceRootIsSymlink": False,
            "remoteArtifactParent": allocation["artifactParent"],
            "artifactParentOwner": "root",
            "artifactParentTraversableByExecutionUser": True,
            "remoteArtifactRoot": binding["remoteArtifactRoot"],
            "artifactRootOwner": "stig",
            "artifactRootWritableByExecutionUser": True,
            "exclusiveLeasePath": binding["exclusiveLeasePath"],
            "leaseOwner": "root", "leaseGroup": 1016, "leaseMode": "0660",
            "observedAt": observation.get("observedAt"),
        }
        if canonical_bytes(observation) != canonical_bytes(expected):
            raise GateError("target roots or host isolation differ")
        _timestamp(observation["observedAt"], "target isolation observedAt")
    elif seam == "toolchain-pins":
        _exact(observation, {"dockerVersion", "composeVersion", "pythonVersion", "tcpdumpVersion", "tsharkVersion", "availableCommands", "tcpdumpNonInteractive"}, seam)
        required = ["docker", "flock", "python3", "runuser", "sha256sum", "sudo", "systemctl", "systemd-run", "tcpdump", "tshark"]
        if (
            observation["availableCommands"] != required
            or observation["dockerVersion"] != "29.6.1"
            or observation["tcpdumpNonInteractive"] is not True
            or any(
            not isinstance(observation[key], str) or not observation[key]
            for key in ("dockerVersion", "composeVersion", "pythonVersion", "tcpdumpVersion", "tsharkVersion")
            )
        ):
            raise GateError("required runtime toolchain is not exact and available")
    elif seam == "source-image-bindings":
        _exact(observation, {"upstreamCommit", "materializedSourceSha256", "imageIds", "controllerDigests"}, seam)
        services = posture_catalog()["applicationServices"]
        images = observation["imageIds"]
        if (
            observation["upstreamCommit"] != binding["upstreamCommit"]
            or observation["materializedSourceSha256"] != binding["expectedMaterializedSourceSha256"]
            or not isinstance(images, dict)
            or set(images) != set(services)
            or any(IMAGE_ID.fullmatch(str(value)) is None for value in images.values())
            or observation["controllerDigests"] != binding["controllerDigests"]
        ):
            raise GateError("source, image, or controller binding differs")
    elif seam == "installed-release-bindings":
        _exact(observation, {"frameworkCommit", "releaseRoot", "repositoryRoot", "remoteSourceRoot", "installedControllerDigests", "sourceTreeImmutable", "sourceTreeSymlinks", "setupReceiptSha256"}, seam)
        if (
            observation["frameworkCommit"] != binding["frameworkCommit"]
            or observation["releaseRoot"] != binding["releaseRoot"]
            or observation["repositoryRoot"] != binding["repositoryRoot"]
            or observation["remoteSourceRoot"] != binding["remoteSourceRoot"]
            or observation["installedControllerDigests"] != binding["controllerDigests"]
            or observation["sourceTreeImmutable"] is not True
            or observation["sourceTreeSymlinks"] != []
            or HEX64.fullmatch(str(observation["setupReceiptSha256"])) is None
        ):
            raise GateError("installed release bytes or immutability differ")
    elif seam == "foreign-inventory-preservation":
        _exact(observation, {"runningContainers", "activeComposeProjects", "exitedComposeProjectsBefore", "exitedComposeProjectsAfter", "foreignVolumesBefore", "foreignVolumesAfter", "deletedForeignResources"}, seam)
        if (
            observation["runningContainers"] != []
            or observation["activeComposeProjects"] != []
            or observation["exitedComposeProjectsBefore"] != observation["exitedComposeProjectsAfter"]
            or observation["foreignVolumesBefore"] != observation["foreignVolumesAfter"]
            or observation["deletedForeignResources"] != []
        ):
            raise GateError("foreign exited projects or volumes were not preserved")
    elif seam == "project-port-lease-isolation":
        _exact(observation, {
            "composeProject", "ports", "preexistingResources", "occupiedPorts",
            "leaseAvailable", "controllerRootPresent", "candidateResultEntries",
        }, seam)
        if (
            observation["composeProject"] != binding["compose"]["project"]
            or observation["ports"] != binding["compose"]["ports"]
            or observation["preexistingResources"] != {"containers": [], "networks": [], "volumes": []}
            or observation["occupiedPorts"] != []
            or observation["leaseAvailable"] is not True
            or observation["controllerRootPresent"] is not True
            or observation["candidateResultEntries"] != []
        ):
            raise GateError("project, port, lease, or artifact-root isolation differs")
    elif seam.endswith("-posture"):
        _service_matrix(observation, seam.removesuffix("-posture"))
    elif seam == "application-request-witness":
        _exact(observation, {"requestToken", "injectedTraceId", "applicationWitnessToken", "applicationWitnessTraceparent", "applicationWitnessCount"}, seam)
        traceparent = observation["applicationWitnessTraceparent"]
        if (
            observation["applicationWitnessToken"] != observation["requestToken"]
            or observation["applicationWitnessCount"] != 1
            or not isinstance(traceparent, str)
            or not traceparent.startswith(f"00-{observation['injectedTraceId']}-")
        ):
            raise GateError("application-side request witness does not bind injected identity")
    elif seam == "request-token-original-trace-correlation":
        _exact(observation, {"requestToken", "injectedTraceId", "observedOriginalTraceIds", "matchingSpanServices", "oneToOne", "crossTraceAssembly"}, seam)
        if (
            observation["observedOriginalTraceIds"] != [observation["injectedTraceId"]]
            or observation["matchingSpanServices"] != list(_frozen_pilot_module().OFFPATH_SYNC_PATH)
            or observation["oneToOne"] is not True
            or observation["crossTraceAssembly"] is not False
        ):
            raise GateError("request-token/original-trace correlation differs")
    elif seam == "cumulative-application-cpu":
        _exact(observation, {"counter", "applicationServices", "beforeNanoseconds", "afterNanoseconds", "monotonic", "cpuSeconds"}, seam)
        before, after = observation["beforeNanoseconds"], observation["afterNanoseconds"]
        if (
            observation["counter"] != "docker-engine-cpu_stats.cpu_usage.total_usage"
            or observation["applicationServices"] != posture_catalog()["costApplicationServices"]
            or _int(before, "CPU before", 0) > _int(after, "CPU after", 0)
            or observation["monotonic"] is not True
            or not isinstance(observation["cpuSeconds"], (int, float))
            or isinstance(observation["cpuSeconds"], bool)
            or not math.isfinite(observation["cpuSeconds"])
            or abs(observation["cpuSeconds"] - (after - before) / 1_000_000_000) > 1e-9
        ):
            raise GateError("cumulative application CPU measurement is invalid")
    elif seam == "emitted-and-on-wire-telemetry-bytes":
        _exact(observation, {"captureTool", "filter", "calibrationPayloadBytes", "measuredPayloadBytes", "calibrationWireBytes", "measuredWireBytes", "retransmissionsExcludedFromPayload"}, seam)
        if (
            observation["captureTool"] != "tshark"
            or observation["filter"] != "tcp dst port 4317 or tcp dst port 4318"
            or _int(observation["calibrationPayloadBytes"], "calibration payload", 1) != observation["measuredPayloadBytes"]
            or _int(observation["calibrationWireBytes"], "calibration wire", 1) != observation["measuredWireBytes"]
            or observation["measuredWireBytes"] < observation["measuredPayloadBytes"]
            or observation["retransmissionsExcludedFromPayload"] is not True
        ):
            raise GateError("emitted/on-wire telemetry-byte measurement failed calibration")
    elif seam == "frontend-fault-manifestation-recovery":
        _exact(observation, {"scenario", "service", "sameContainer", "preRunning", "duringPaused", "outageObserved", "postRunning", "postPaused", "readyAfter"}, seam)
        if observation != {
            "scenario": "frontend-pause", "service": "frontend",
            "sameContainer": True, "preRunning": True, "duringPaused": True,
            "outageObserved": True, "postRunning": True, "postPaused": False,
            "readyAfter": True,
        }:
            raise GateError("frontend fault manifestation or recovery is unproven")
    elif seam == "owned-cleanup-and-deadline":
        _exact(observation, {"leaseScope", "deadlineEnforced", "cleanupEnforced", "remainingResources"}, seam)
        if observation != {"leaseScope": "shared-srv6-host-exclusive-otel-then-online-boutique", "deadlineEnforced": True, "cleanupEnforced": True, "remainingResources": {"containers": [], "networks": [], "volumes": []}}:
            raise GateError("owned cleanup/deadline behavior differs")
    else:
        _exact(observation, {"expectedCells", "validFixtureVerdict", "plantedDefectVerdict", "promotionAuthorized"}, seam)
        if observation != {"expectedCells": RUN_COUNT, "validFixtureVerdict": "pass", "plantedDefectVerdict": "fail", "promotionAuthorized": False}:
            raise GateError("candidate terminal validator was not watched passing and failing")


def planted_observation(seam: str, positive: Mapping[str, Any]) -> dict[str, Any]:
    planted = copy.deepcopy(positive)
    if seam == "target-contract-projection": planted["projection"]["host"] = "fb14srv5"
    elif seam == "target-identity": planted["executionUser"] = "root"
    elif seam == "target-root-and-host-isolation": planted["sourceRootWritableByExecutionUser"] = True
    elif seam == "toolchain-pins": planted["availableCommands"] = planted["availableCommands"][:-1]
    elif seam == "source-image-bindings": planted["upstreamCommit"] = "0" * 40
    elif seam == "installed-release-bindings": planted["sourceTreeImmutable"] = False
    elif seam == "foreign-inventory-preservation": planted["deletedForeignResources"] = ["volume:foreign"]
    elif seam == "project-port-lease-isolation": planted["candidateResultEntries"] = ["planted-result"]
    elif seam.endswith("-posture"):
        planted["instrumentationLoadStates"] = {
            **planted["instrumentationLoadStates"], "adservice": "loaded",
        } if planted["instrumentationLoadStates"].get("adservice") != "loaded" else {
            **planted["instrumentationLoadStates"], "adservice": "not-loaded",
        }
    elif seam == "application-request-witness": planted["applicationWitnessToken"] = "wrong-token"
    elif seam == "request-token-original-trace-correlation": planted["observedOriginalTraceIds"] = ["0" * 32]
    elif seam == "cumulative-application-cpu": planted["afterNanoseconds"] = planted["beforeNanoseconds"] - 1
    elif seam == "emitted-and-on-wire-telemetry-bytes": planted["measuredPayloadBytes"] += 1
    elif seam == "frontend-fault-manifestation-recovery": planted["readyAfter"] = False
    elif seam == "owned-cleanup-and-deadline": planted["remainingResources"] = {"containers": ["leak"], "networks": [], "volumes": []}
    else: planted["plantedDefectVerdict"] = "pass"
    return planted


def validate_setup_receipt(
    document: Any,
    plan: Mapping[str, Any],
    plan_sha256: str,
    setup_sha256: str,
) -> tuple[dict[str, Any], str]:
    root = _exact(document, {
        "schemaVersion", "kind", "campaignId", "target", "executionIdentity",
        "frameworkCommit", "upstreamCommit", "gatePlanSha256", "gateSetupSha256",
        "targetContractSha256", "repositoryBundleSha256", "upstreamBundleSha256",
        "releaseRoot", "repositoryRoot", "remoteSourceRoot", "remoteArtifactRoot",
        "leasePath", "composeProject", "ports", "materializedSourceSha256",
        "imageIds", "installedControllerDigests", "dockerVersion", "dockerGid",
        "foreignInventoryBefore", "foreignInventoryAfter", "foreignVolumesPreserved",
        "activeForeignResourcesAbsent", "containersStarted", "cellsRun",
        "runtimeAuthorized", "promotionAuthorized", "startedAt", "completedAt",
    }, "setup receipt")
    binding = plan["binding"]
    expected_target = {
        "host": binding["target"]["host"],
        "transportUser": binding["target"]["transportUser"],
        "setupUser": binding["target"]["setupUser"],
    }
    images = root["imageIds"]
    before, after = root["foreignInventoryBefore"], root["foreignInventoryAfter"]
    for inventory, where in ((before, "before"), (after, "after")):
        _exact(inventory, {"composeProjects", "runningContainers", "volumes"}, f"foreign inventory {where}")
        if not all(isinstance(inventory[key], list) for key in inventory):
            raise GateError("foreign inventory population differs")
    if (
        root["schemaVersion"] != 1
        or root["kind"] != "otel-demo-candidate-setup-receipt-v1"
        or root["campaignId"] != binding["campaignId"]
        or root["target"] != expected_target
        or root["executionIdentity"] != binding["target"]["executionIdentity"]
        or root["frameworkCommit"] != binding["frameworkCommit"]
        or root["upstreamCommit"] != binding["upstreamCommit"]
        or root["gatePlanSha256"] != plan_sha256
        or root["gateSetupSha256"] != setup_sha256
        or root["targetContractSha256"] != binding["targetContractSha256"]
        or root["repositoryBundleSha256"] != binding["repositoryBundleSha256"]
        or root["upstreamBundleSha256"] != binding["upstreamBundleSha256"]
        or root["releaseRoot"] != binding["releaseRoot"]
        or root["repositoryRoot"] != binding["repositoryRoot"]
        or root["remoteSourceRoot"] != binding["remoteSourceRoot"]
        or root["remoteArtifactRoot"] != binding["remoteArtifactRoot"]
        or root["leasePath"] != binding["exclusiveLeasePath"]
        or root["composeProject"] != binding["compose"]["project"]
        or root["ports"] != binding["compose"]["ports"]
        or root["materializedSourceSha256"] != binding["expectedMaterializedSourceSha256"]
        or not isinstance(images, dict)
        or set(images) != set(posture_catalog()["applicationServices"])
        or any(IMAGE_ID.fullmatch(str(value)) is None for value in images.values())
        or root["installedControllerDigests"] != binding["controllerDigests"]
        or root["dockerVersion"] != "29.6.1"
        or root["dockerGid"] != 998
        or before["runningContainers"] != []
        or after["runningContainers"] != []
        or before["volumes"] != after["volumes"]
        or root["foreignVolumesPreserved"] is not True
        or root["activeForeignResourcesAbsent"] is not True
        or root["containersStarted"] is not False
        or root["cellsRun"] != 0
        or root["runtimeAuthorized"] is not False
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("setup receipt installed bytes, identity, or authority differs")
    started = _timestamp(root["startedAt"], "setup receipt startedAt")
    completed = _timestamp(root["completedAt"], "setup receipt completedAt")
    if completed < started:
        raise GateError("setup receipt completion predates setup start")
    return copy.deepcopy(root), canonical_sha256(root)


def validate_consumed_gate_setup(
    gate_setup: Mapping[str, Any], setup_receipt: Mapping[str, Any]
) -> None:
    """Prove the fresh setup gate was consumed at setup start, not at run time."""
    approved = _timestamp(gate_setup["approvedAt"], "GATE-SETUP approvedAt")
    started = _timestamp(setup_receipt["startedAt"], "setup receipt startedAt")
    age = math.floor((started - approved).total_seconds())
    if age < -5 or age > MAX_GATE_AGE_SECONDS:
        raise GateError("GATE-SETUP was not fresh when setup began")


def installed_bindings(receipt: Mapping[str, Any], receipt_sha256: str) -> dict[str, Any]:
    return {
        "setupReceiptSha256": receipt_sha256,
        "frameworkCommit": receipt["frameworkCommit"],
        "upstreamCommit": receipt["upstreamCommit"],
        "targetContractSha256": receipt["targetContractSha256"],
        "releaseRoot": receipt["releaseRoot"],
        "repositoryRoot": receipt["repositoryRoot"],
        "remoteSourceRoot": receipt["remoteSourceRoot"],
        "remoteArtifactRoot": receipt["remoteArtifactRoot"],
        "materializedSourceSha256": receipt["materializedSourceSha256"],
        "imageIds": copy.deepcopy(receipt["imageIds"]),
        "installedControllerDigests": copy.deepcopy(receipt["installedControllerDigests"]),
    }


def harness_contract_observations(binding: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Deterministic checker fixtures; these are not claims about a live cell."""
    catalog = posture_catalog()
    token = "opq-readiness-contract-0001"
    trace_id = "1" * 32
    observations: dict[str, dict[str, Any]] = {
        "application-request-witness": {
            "requestToken": token,
            "injectedTraceId": trace_id,
            "applicationWitnessToken": token,
            "applicationWitnessTraceparent": f"00-{trace_id}-{'2' * 16}-01",
            "applicationWitnessCount": 1,
        },
        "request-token-original-trace-correlation": {
            "requestToken": token,
            "injectedTraceId": trace_id,
            "observedOriginalTraceIds": [trace_id],
            "matchingSpanServices": list(_frozen_pilot_module().OFFPATH_SYNC_PATH),
            "oneToOne": True,
            "crossTraceAssembly": False,
        },
        "cumulative-application-cpu": {
            "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
            "applicationServices": catalog["costApplicationServices"],
            "beforeNanoseconds": 1_000_000_000,
            "afterNanoseconds": 2_000_000_000,
            "monotonic": True,
            "cpuSeconds": 1.0,
        },
        "emitted-and-on-wire-telemetry-bytes": {
            "captureTool": "tshark",
            "filter": "tcp dst port 4317 or tcp dst port 4318",
            "calibrationPayloadBytes": 128,
            "measuredPayloadBytes": 128,
            "calibrationWireBytes": 256,
            "measuredWireBytes": 256,
            "retransmissionsExcludedFromPayload": True,
        },
        "frontend-fault-manifestation-recovery": {
            "scenario": "frontend-pause",
            "service": "frontend",
            "sameContainer": True,
            "preRunning": True,
            "duringPaused": True,
            "outageObserved": True,
            "postRunning": True,
            "postPaused": False,
            "readyAfter": True,
        },
        "owned-cleanup-and-deadline": {
            "leaseScope": binding["leaseScope"],
            "deadlineEnforced": True,
            "cleanupEnforced": True,
            "remainingResources": {"containers": [], "networks": [], "volumes": []},
        },
        "candidate-terminal-validation": {
            "expectedCells": RUN_COUNT,
            "validFixtureVerdict": "pass",
            "plantedDefectVerdict": "fail",
            "promotionAuthorized": False,
        },
    }
    for posture in POSTURES:
        active = catalog["postures"][posture]["activeApplicationServices"]
        observations[f"{posture}-posture"] = {
            "posture": posture,
            "activeApplicationServices": active,
            "sourceInstrumentationLoadedServices": active,
            "renderedComposeActiveServices": active,
            "instrumentationLoadStates": expected_load_states(posture),
            "postureConfigSha256": posture_config_sha256_for_binding(binding, posture),
            "sourceDigestObservedEveryPatchedImage": True,
            "zeroStartupApplicationSignals": True if posture == "none" else None,
        }
    if set(observations) != HARNESS_REPLAY_SEAMS:
        raise GateError("harness readiness fixture population differs")
    return observations


def _target_command(argv: Sequence[str]) -> str:
    # UTF-8 with replacement: target CLI output is bytes, not guaranteed UTF-8 (Hotel sweep1 attempt 2, 2026-10-03).
    result = subprocess.run(
        list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace", timeout=60, check=False,
    )
    if result.returncode:
        raise GateError(
            f"target readiness command {argv[0]} failed ({result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _target_source_tree_sha256(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts and path.name != ".source.sha256":
            relative = str(path.relative_to(root)).encode()
            payload = _read_file(path, f"installed source file {path}")
            value.update(len(relative).to_bytes(8, "big")); value.update(relative)
            value.update(stat.S_IMODE(path.stat().st_mode).to_bytes(4, "big"))
            value.update(len(payload).to_bytes(8, "big")); value.update(payload)
    return value.hexdigest()


def _compose_inventory() -> dict[str, Any]:
    raw = _target_command(["docker", "compose", "ls", "--all", "--format", "json"])
    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise GateError("target Compose inventory is not JSON") from exc
    if not isinstance(rows, list):
        raise GateError("target Compose inventory is not a list")
    projects = sorted(
        ({
            "name": str(row.get("Name", "")),
            "status": str(row.get("Status", "")),
            "configFiles": str(row.get("ConfigFiles", "")),
        } for row in rows if isinstance(row, dict)),
        key=lambda row: (row["name"], row["configFiles"]),
    )
    return {
        "composeProjects": projects,
        "runningContainers": sorted(filter(None, _target_command(["docker", "ps", "-q"]).splitlines())),
        "volumes": sorted(filter(None, _target_command(["docker", "volume", "ls", "-q"]).splitlines())),
    }


def _project_resources(project: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for kind, argv in {
        "containers": ["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.ID}}"],
        "networks": ["docker", "network", "ls", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.ID}}"],
        "volumes": ["docker", "volume", "ls", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.Name}}"],
    }.items():
        result[kind] = sorted(filter(None, _target_command(argv).splitlines()))
    return result


PORT_TEARDOWN_WAIT_SECONDS = 30


def _probe_reserved_ports(ports: Sequence[int], *, wait_seconds: int = PORT_TEARDOWN_WAIT_SECONDS) -> list[int]:
    """Which of the reserved ports actually has a listener, TIME_WAIT excluded.

    Hotel lesson 8, ported before it can bite. Hotel's boundary probe bound
    without SO_REUSEADDR, so the *previous cell's own* closed connections --
    sockets in TIME_WAIT, owned by nobody, accepting nothing -- read as
    "occupied" and refused cell 2 of the first campaign that ever got past
    cell 1 (fixed in 42ac455).

    SO_REUSEADDR is the correct semantics for the question this seam asks.
    On Linux it never lets a bind steal a socket that is actually LISTENing
    on the same address, so a live foreign listener still reports occupied;
    it only stops a lingering TIME_WAIT from doing so. The bounded retry
    covers the narrower race where our own previous Compose project is still
    tearing its published ports down.

    All sockets are held until the whole set is probed, then closed together,
    so two reserved ports cannot be reported free by reusing one socket.
    """
    deadline = time.monotonic() + max(0, int(wait_seconds))
    occupied: list[int] = []
    while True:
        occupied = []
        sockets: list[socket.socket] = []
        try:
            for port in ports:
                probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    probe.bind(("0.0.0.0", int(port)))
                except OSError:
                    occupied.append(int(port))
                    probe.close()
                else:
                    sockets.append(probe)
        finally:
            for probe in sockets:
                probe.close()
        if not occupied or time.monotonic() >= deadline:
            return occupied
        time.sleep(1.0)


def target_observations(
    plan: Mapping[str, Any],
    setup_receipt: Mapping[str, Any],
    setup_receipt_sha256: str,
    *,
    observed_at: str,
) -> dict[str, dict[str, Any]]:
    """Read the eight zero-cell facts from the reviewed target itself."""
    refuse_unsupported("target readiness observation")
    binding = plan["binding"]
    target = binding["target"]
    identity = target["executionIdentity"]
    if socket.gethostname() != target["host"] or os.geteuid() != 0:
        raise GateError("target readiness producer is not root on the reviewed host")
    account = pwd.getpwnam(identity["user"])
    groups = sorted(
        gid for gid in os.getgrouplist(identity["user"], account.pw_gid)
        if gid != account.pw_gid
    )
    if (
        account.pw_uid != identity["uid"]
        or account.pw_gid != identity["gid"]
        or groups != identity["supplementalGids"]
        or grp.getgrnam("docker").gr_gid != 998
    ):
        raise GateError("registered target execution identity differs")
    release = Path(binding["releaseRoot"])
    repository = Path(binding["repositoryRoot"])
    source = Path(binding["remoteSourceRoot"])
    artifacts = Path(binding["remoteArtifactRoot"])
    allocation = target_allocation()
    artifact_parent = Path(allocation["artifactParent"])
    lease_path = Path(binding["exclusiveLeasePath"])
    for path, where in (
        (release, "release root"), (repository, "repository root"),
        (source, "source root"), (artifacts, "artifact root"),
        (artifact_parent, "artifact parent"), (lease_path, "lease path"),
    ):
        if path.is_symlink() or not path.exists():
            raise GateError(f"target {where} is absent or a symlink")
    if _target_source_tree_sha256(source) != binding["expectedMaterializedSourceSha256"]:
        raise GateError("installed target source digest differs")
    source_symlinks = sorted(
        str(path.relative_to(source)) for path in source.rglob("*") if path.is_symlink()
    )
    source_immutable = not source_symlinks and all(
        stat.S_IMODE(path.lstat().st_mode) & 0o222 == 0
        for path in (source, *source.rglob("*"))
    )
    installed_digests = {
        name: file_sha256(repository / relative)
        for name, relative in CONTROLLER_PATHS.items()
    }
    if installed_digests != binding["controllerDigests"]:
        raise GateError("installed target controller bytes differ")
    for image_id in setup_receipt["imageIds"].values():
        observed_image = _target_command([
            "docker", "image", "inspect", "--format", "{{.Id}}", image_id
        ])
        if observed_image != image_id:
            raise GateError("installed target image ID differs")
    commands = [
        "docker", "flock", "python3", "runuser", "sha256sum", "sudo",
        "systemctl", "systemd-run", "tcpdump", "tshark",
    ]
    available = [name for name in commands if shutil.which(name)]
    tcpdump_probe = subprocess.run(
        [
            # Group NAMES, not gids: util-linux 2.36.1 (all three hosts) rejects a
            # numeric --group with "group <gid> does not exist" even when the gid is
            # in /etc/group, so a numeric probe always returned non-zero and
            # `tcpdumpNonInteractive` was permanently False. Same defect as
            # candidate_setup.run_as_stig; fixed in both places, since fixing one
            # leaves the gate failing for the other's reason.
            "runuser", "--user", identity["user"],
            "--group", grp.getgrgid(int(identity["gid"])).gr_name,
            "--supp-group", grp.getgrgid(998).gr_name,
            "--", "sudo", "-n", "tcpdump", "-D",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        check=False,
    )
    inventory = _compose_inventory()
    active_projects = [
        row for row in inventory["composeProjects"]
        if "running" in row["status"].lower()
    ]
    with lease_path.open("a+") as lease:
        try:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lease_available = False
        else:
            lease_available = True
            fcntl.flock(lease.fileno(), fcntl.LOCK_UN)
    occupied_ports = _probe_reserved_ports(list(binding["compose"]["ports"].values()))
    candidate_entries = sorted(
        path.name for path in artifacts.iterdir() if path.name != ".controller"
    )
    source_writable = subprocess.run(
        ["runuser", "--user", identity["user"], "--", "test", "-w", str(source)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
    artifact_parent_traversable = subprocess.run(
        ["runuser", "--user", identity["user"], "--", "test", "-x", str(artifact_parent)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0
    observations = {
        "target-contract-projection": {
            "targetContractSha256": binding["targetContractSha256"],
            "projection": copy.deepcopy(binding["targetContractProjection"]),
        },
        "target-identity": {
            "host": target["host"], "transportUser": "root", "setupUser": "root",
            "executionUser": identity["user"], "uid": account.pw_uid,
            "gid": account.pw_gid, "supplementalGids": groups,
            "architecture": platform.machine(), "kernel": platform.release(),
            "observedAt": observed_at,
        },
        "target-root-and-host-isolation": {
            "target": copy.deepcopy(target), "releaseRoot": str(release),
            "repositoryRoot": str(repository), "remoteSourceRoot": str(source),
            "sourceRootOwner": pwd.getpwuid(source.stat().st_uid).pw_name,
            "sourceRootWritableByExecutionUser": source_writable,
            "sourceRootIsSymlink": source.is_symlink(),
            "remoteArtifactParent": str(artifact_parent),
            "artifactParentOwner": pwd.getpwuid(artifact_parent.stat().st_uid).pw_name,
            "artifactParentTraversableByExecutionUser": artifact_parent_traversable,
            "remoteArtifactRoot": str(artifacts),
            "artifactRootOwner": pwd.getpwuid(artifacts.stat().st_uid).pw_name,
            "artifactRootWritableByExecutionUser": subprocess.run(
                ["runuser", "--user", identity["user"], "--", "test", "-w", str(artifacts)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            ).returncode == 0,
            "exclusiveLeasePath": str(lease_path),
            "leaseOwner": pwd.getpwuid(lease_path.stat().st_uid).pw_name,
            "leaseGroup": lease_path.stat().st_gid,
            "leaseMode": f"{stat.S_IMODE(lease_path.stat().st_mode):04o}",
            "observedAt": observed_at,
        },
        "toolchain-pins": {
            "dockerVersion": _target_command(["docker", "version", "--format", "{{.Server.Version}}"]),
            "composeVersion": _target_command(["docker", "compose", "version", "--short"]),
            "pythonVersion": _target_command(["python3", "--version"]),
            "tcpdumpVersion": _target_command(["tcpdump", "--version"]).splitlines()[0],
            "tsharkVersion": _target_command(["tshark", "--version"]).splitlines()[0],
            "availableCommands": available,
            "tcpdumpNonInteractive": tcpdump_probe.returncode == 0,
        },
        "source-image-bindings": {
            "upstreamCommit": binding["upstreamCommit"],
            "materializedSourceSha256": binding["expectedMaterializedSourceSha256"],
            "imageIds": copy.deepcopy(setup_receipt["imageIds"]),
            "controllerDigests": copy.deepcopy(installed_digests),
        },
        "installed-release-bindings": {
            "frameworkCommit": binding["frameworkCommit"],
            "releaseRoot": str(release), "repositoryRoot": str(repository),
            "remoteSourceRoot": str(source),
            "installedControllerDigests": copy.deepcopy(installed_digests),
            "sourceTreeImmutable": source_immutable,
            "sourceTreeSymlinks": source_symlinks,
            "setupReceiptSha256": setup_receipt_sha256,
        },
        "foreign-inventory-preservation": {
            "runningContainers": inventory["runningContainers"],
            "activeComposeProjects": active_projects,
            "exitedComposeProjectsBefore": copy.deepcopy(setup_receipt["foreignInventoryBefore"]["composeProjects"]),
            "exitedComposeProjectsAfter": inventory["composeProjects"],
            "foreignVolumesBefore": copy.deepcopy(setup_receipt["foreignInventoryBefore"]["volumes"]),
            "foreignVolumesAfter": inventory["volumes"],
            "deletedForeignResources": [],
        },
        "project-port-lease-isolation": {
            "composeProject": binding["compose"]["project"],
            "ports": copy.deepcopy(binding["compose"]["ports"]),
            "preexistingResources": _project_resources(binding["compose"]["project"]),
            "occupiedPorts": occupied_ports, "leaseAvailable": lease_available,
            "controllerRootPresent": (artifacts / ".controller").is_dir(),
            "candidateResultEntries": candidate_entries,
        },
    }
    if set(observations) != TARGET_OBSERVATION_SEAMS:
        raise GateError("target readiness observation population differs")
    return observations


def produce_target_readiness(
    gate_plan: Mapping[str, Any],
    gate_setup: Mapping[str, Any],
    setup_receipt: Mapping[str, Any],
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    target_observer: Callable[..., dict[str, dict[str, Any]]] = target_observations,
) -> dict[str, Any]:
    refuse_unsupported("target readiness production")
    plan_sha = canonical_sha256(gate_plan)
    if setup_receipt.get("gatePlanSha256") != plan_sha:
        raise GateError("target readiness plan differs from installed setup")
    _, setup_sha = validate_gate_setup_reference(gate_setup, gate_plan, plan_sha)
    checked_receipt, receipt_sha = validate_setup_receipt(
        setup_receipt, gate_plan, plan_sha, setup_sha
    )
    validate_consumed_gate_setup(gate_setup, checked_receipt)
    observed = clock()
    if observed.tzinfo != timezone.utc:
        raise GateError("target readiness clock must be timezone-aware UTC")
    observed_at = observed.isoformat().replace("+00:00", "Z")
    observations = target_observer(
        gate_plan, checked_receipt, receipt_sha, observed_at=observed_at
    )
    observations.update(harness_contract_observations(gate_plan["binding"]))
    readiness = make_readiness(
        gate_plan, plan_sha, setup_sha, checked_receipt, receipt_sha,
        observations, observed_at=observed_at,
    )
    validate_readiness(readiness, gate_plan, plan_sha, now=observed)
    return readiness


def write_target_readiness(path: Path, readiness: Mapping[str, Any]) -> None:
    refuse_unsupported("target readiness write")
    path = Path(path)
    if path.exists() and path.is_symlink():
        raise GateError("target readiness output is a symlink")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(readiness, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def make_readiness(
    plan: Mapping[str, Any],
    plan_sha256: str,
    gate_setup_sha256: str,
    setup_receipt: Mapping[str, Any],
    setup_receipt_sha256: str,
    observations: Mapping[str, Mapping[str, Any]],
    *,
    observed_at: str,
) -> dict[str, Any]:
    binding = plan["binding"]
    observed = _timestamp(observed_at, "readiness observedAt")
    completed = _timestamp(setup_receipt["completedAt"], "setup receipt completedAt")
    if observed < completed:
        raise GateError("readiness predates the completed setup")
    if set(observations) != set(READINESS_SEAMS):
        raise GateError("readiness observations do not cover every seam")
    seams: dict[str, Any] = {}
    for seam in READINESS_SEAMS:
        positive = copy.deepcopy(observations[seam])
        validate_seam(seam, positive, binding)
        planted = planted_observation(seam, positive)
        try:
            validate_seam(seam, planted, binding)
        except GateError as exc:
            diagnostic = str(exc)
        else:
            raise GateError(f"planted {seam} defect was not detected")
        seams[seam] = {
            "status": "pass",
            "scope": READINESS_SCOPE[seam],
            "positiveWitness": positive,
            "positiveWitnessSha256": canonical_sha256(positive),
            "plantedDefectWitness": planted,
            "plantedDefectWitnessSha256": canonical_sha256(planted),
            "checkerExitCode": 2,
            "checkerDiagnostic": diagnostic,
        }
    return {
        "schemaVersion": 2,
        "kind": READINESS_KIND,
        "studyEpoch": STUDY_EPOCH,
        "gatePlanSha256": plan_sha256,
        "gateSetupSha256": gate_setup_sha256,
        "setupReceiptSha256": setup_receipt_sha256,
        "installedBindings": installed_bindings(setup_receipt, setup_receipt_sha256),
        "bindingSha256": canonical_sha256(binding),
        "target": copy.deepcopy(binding["target"]),
        "producer": {
            "host": binding["target"]["host"],
            "entrypoint": CONTROLLER_PATHS["runtime-admission"],
            "entrypointSha256": binding["controllerDigests"]["runtime-admission"],
            "cellsRun": 0,
        },
        "readinessObservedAt": observed_at,
        "runCount": RUN_COUNT,
        "runtimeReady": True,
        "candidateEvidenceAuthorized": False,
        "promotionAuthorized": False,
        "seams": seams,
    }


def validate_readiness_reference(
    document: Any,
    plan: Mapping[str, Any],
    plan_sha256: str,
) -> tuple[dict[str, Any], str]:
    root = _exact(document, {
        "schemaVersion", "kind", "studyEpoch", "gatePlanSha256",
        "gateSetupSha256", "setupReceiptSha256", "installedBindings",
        "bindingSha256", "target", "producer", "readinessObservedAt",
        "runCount", "runtimeReady", "candidateEvidenceAuthorized",
        "promotionAuthorized", "seams",
    }, "runtime readiness")
    binding = plan["binding"]
    producer = {
        "host": binding["target"]["host"],
        "entrypoint": CONTROLLER_PATHS["runtime-admission"],
        "entrypointSha256": binding["controllerDigests"]["runtime-admission"],
        "cellsRun": 0,
    }
    if (
        _int(root["schemaVersion"], "readiness schema", 1) != 2
        or root["kind"] != READINESS_KIND
        or root["studyEpoch"] != STUDY_EPOCH
        or root["gatePlanSha256"] != plan_sha256
        or HEX64.fullmatch(str(root["gateSetupSha256"])) is None
        or HEX64.fullmatch(str(root["setupReceiptSha256"])) is None
        or root["installedBindings"].get("setupReceiptSha256") != root["setupReceiptSha256"]
        or root["installedBindings"].get("materializedSourceSha256") != binding["expectedMaterializedSourceSha256"]
        or root["installedBindings"].get("installedControllerDigests") != binding["controllerDigests"]
        or root["bindingSha256"] != canonical_sha256(binding)
        or root["target"] != binding["target"]
        or root["producer"] != producer
        or _int(root["runCount"], "readiness run count", 1) != RUN_COUNT
        or root["runtimeReady"] is not True
        or root["candidateEvidenceAuthorized"] is not False
        or root["promotionAuthorized"] is not False
        or set(root["seams"]) != set(READINESS_SEAMS)
    ):
        raise GateError("runtime-readiness identity or authority ceiling differs")
    _timestamp(root["readinessObservedAt"], "readiness observedAt")
    for seam in READINESS_SEAMS:
        row = _exact(root["seams"][seam], {"status", "scope", "positiveWitness", "positiveWitnessSha256", "plantedDefectWitness", "plantedDefectWitnessSha256", "checkerExitCode", "checkerDiagnostic"}, f"readiness seam {seam}")
        if (
            row["status"] != "pass"
            or row["scope"] != READINESS_SCOPE[seam]
            or canonical_sha256(row["positiveWitness"]) != row["positiveWitnessSha256"]
            or canonical_sha256(row["plantedDefectWitness"]) != row["plantedDefectWitnessSha256"]
            or _int(row["checkerExitCode"], f"{seam} checker exit") == 0
            or not isinstance(row["checkerDiagnostic"], str)
            or not row["checkerDiagnostic"]
        ):
            raise GateError(f"readiness seam {seam} witness binding differs")
        validate_seam(seam, row["positiveWitness"], binding)
        expected_plant = planted_observation(seam, row["positiveWitness"])
        if canonical_bytes(expected_plant) != canonical_bytes(row["plantedDefectWitness"]):
            raise GateError(f"readiness seam {seam} planted defect differs")
        try:
            validate_seam(seam, row["plantedDefectWitness"], binding)
        except GateError as exc:
            if str(exc) != row["checkerDiagnostic"]:
                raise GateError(f"readiness seam {seam} failure diagnostic differs") from exc
        else:
            raise GateError(f"readiness seam {seam} planted defect no longer fails")
    for seam in ("target-identity", "target-root-and-host-isolation"):
        if root["seams"][seam]["positiveWitness"]["observedAt"] != root["readinessObservedAt"]:
            raise GateError(f"readiness seam {seam} timestamp differs from producer time")
    source_witness = root["seams"]["source-image-bindings"]["positiveWitness"]
    release_witness = root["seams"]["installed-release-bindings"]["positiveWitness"]
    installed = root["installedBindings"]
    if (
        source_witness["materializedSourceSha256"] != installed["materializedSourceSha256"]
        or source_witness["imageIds"] != installed["imageIds"]
        or source_witness["controllerDigests"] != installed["installedControllerDigests"]
        or release_witness["setupReceiptSha256"] != root["setupReceiptSha256"]
        or release_witness["installedControllerDigests"] != installed["installedControllerDigests"]
    ):
        raise GateError("semantic readiness does not bind the installed source, images, and controller bytes")
    return copy.deepcopy(root), canonical_sha256(root)


def validate_readiness(
    document: Any,
    plan: Mapping[str, Any],
    plan_sha256: str,
    *,
    now: datetime,
) -> str:
    root, digest = validate_readiness_reference(document, plan, plan_sha256)
    if now.tzinfo != timezone.utc:
        raise GateError("readiness clock must be timezone-aware UTC")
    observed = _timestamp(root["readinessObservedAt"], "readiness observedAt")
    age = math.floor((now - observed).total_seconds())
    if age < -5 or age > MAX_GATE_AGE_SECONDS:
        raise GateError("runtime readiness is not fresh")
    return digest


def run_binding(
    plan: Mapping[str, Any],
    plan_sha256: str,
    readiness: Mapping[str, Any],
    readiness_sha256: str,
    *,
    not_before: str,
    authorization_deadline: str,
) -> dict[str, Any]:
    return {
        "studyEpoch": STUDY_EPOCH,
        "campaignId": plan["binding"]["campaignId"],
        "target": copy.deepcopy(plan["binding"]["target"]),
        "gatePlanSha256": plan_sha256,
        "gateSetupSha256": readiness["gateSetupSha256"],
        "setupReceiptSha256": readiness["setupReceiptSha256"],
        "runtimeReadinessSha256": readiness_sha256,
        "readinessObservedAt": readiness["readinessObservedAt"],
        "installedBindings": copy.deepcopy(readiness["installedBindings"]),
        "installedBindingsSha256": canonical_sha256(readiness["installedBindings"]),
        "bindingSha256": canonical_sha256(plan["binding"]),
        "authorizedRunIds": copy.deepcopy(plan["binding"]["authorizedRunIds"]),
        "runCount": RUN_COUNT,
        "attempt": plan["binding"]["attempt"],
        "oneShot": True,
        "retryAllowed": False,
        "substitutionAllowed": False,
        "rerandomizationAllowed": False,
        "notBefore": not_before,
        "authorizationDeadline": authorization_deadline,
        "cleanupReserveSeconds": CLEANUP_RESERVE_SECONDS,
        "minimumRemainingAtFirstMutationSeconds": MINIMUM_REMAINING_SECONDS,
    }


def expected_gate_run_text(binding: Mapping[str, Any]) -> str:
    return (
        f"APPROVE GATE-RUN campaign={binding['campaignId']} "
        f"transport=root@{binding['target']['host']} execution=stig:1016:1016+998 gate-plan={binding['gatePlanSha256']} "
        f"gate-setup={binding['gateSetupSha256']} setup-receipt={binding['setupReceiptSha256']} "
        f"readiness={binding['runtimeReadinessSha256']} readiness-observed={binding['readinessObservedAt']} "
        f"installed={binding['installedBindingsSha256']} runs={RUN_COUNT} attempt={binding['attempt']} "
        f"one-shot no-retry no-substitution no-rerandomization "
        f"deadline={binding['authorizationDeadline']}"
    )


def validate_gate_run_reference(
    document: Any,
    plan: Mapping[str, Any],
    plan_sha256: str,
    readiness: Mapping[str, Any],
    readiness_sha256: str,
) -> tuple[dict[str, Any], str]:
    root = _exact(document, {"schemaVersion", "kind", "gate", "decision", "typedApproval", "approvedBy", "approvedAt", "binding", "promotionAuthorized"}, "GATE-RUN")
    binding = root["binding"]
    if not isinstance(binding, dict):
        raise GateError("GATE-RUN binding is not an object")
    expected = run_binding(
        plan,
        plan_sha256,
        readiness,
        readiness_sha256,
        not_before=binding.get("notBefore"),
        authorization_deadline=binding.get("authorizationDeadline"),
    )
    if (
        _int(root["schemaVersion"], "GATE-RUN schema", 1) != 1
        or root["kind"] != RUN_KIND
        or root["gate"] != "GATE-RUN"
        or root["decision"] != "authorize-one-shot-exact-run"
        or canonical_bytes(binding) != canonical_bytes(expected)
        or root["typedApproval"] != expected_gate_run_text(expected)
        or not isinstance(root["approvedBy"], str)
        or not root["approvedBy"].strip()
        or root["promotionAuthorized"] is not False
    ):
        raise GateError("GATE-RUN identity, exact scope, or authority ceiling differs")
    approved = _timestamp(root["approvedAt"], "GATE-RUN approvedAt")
    readiness_observed = _timestamp(
        binding["readinessObservedAt"], "GATE-RUN readinessObservedAt"
    )
    not_before = _timestamp(binding["notBefore"], "GATE-RUN notBefore")
    deadline = _timestamp(binding["authorizationDeadline"], "GATE-RUN deadline")
    if approved <= readiness_observed:
        raise GateError("GATE-RUN approval does not follow target readiness")
    if math.floor((approved - readiness_observed).total_seconds()) > MAX_GATE_AGE_SECONDS:
        raise GateError("target readiness was stale when GATE-RUN was approved")
    first_mutation = max(approved, not_before)
    if math.floor((deadline - first_mutation).total_seconds()) < MINIMUM_REMAINING_SECONDS:
        raise GateError(f"GATE-RUN leaves too little time for {RUN_COUNT} cells and cleanup")
    return copy.deepcopy(root), canonical_sha256(root)


def validate_gate_run(
    document: Any,
    plan: Mapping[str, Any],
    plan_sha256: str,
    readiness: Mapping[str, Any],
    readiness_sha256: str,
    *,
    now: datetime,
) -> str:
    root, digest = validate_gate_run_reference(
        document, plan, plan_sha256, readiness, readiness_sha256
    )
    if now.tzinfo != timezone.utc:
        raise GateError("runtime clock must be timezone-aware UTC")
    approved = _timestamp(root["approvedAt"], "GATE-RUN approvedAt")
    not_before = _timestamp(root["binding"]["notBefore"], "GATE-RUN notBefore")
    deadline = _timestamp(
        root["binding"]["authorizationDeadline"], "GATE-RUN deadline"
    )
    age = math.floor((now - approved).total_seconds())
    if age < -5 or age > MAX_GATE_AGE_SECONDS:
        raise GateError("GATE-RUN is not fresh")
    if now < not_before:
        raise GateError("GATE-RUN window has not opened")
    if math.floor((deadline - now).total_seconds()) < MINIMUM_REMAINING_SECONDS:
        raise GateError(f"GATE-RUN leaves too little time for {RUN_COUNT} cells and cleanup")
    return digest


@dataclass(frozen=True)
class RuntimePackage:
    bindings: PlanBindings
    gate_plan: dict[str, Any]
    gate_plan_sha256: str
    gate_setup: dict[str, Any]
    gate_setup_sha256: str
    setup_receipt: dict[str, Any]
    setup_receipt_sha256: str
    readiness: dict[str, Any]
    readiness_sha256: str
    gate_run: dict[str, Any]
    gate_run_sha256: str
    validated_at: datetime


def replay_runtime_from_files(
    campaign_root: Path,
    gate_plan_path: Path,
    gate_setup_path: Path,
    setup_receipt_path: Path,
    readiness_path: Path,
    gate_run_path: Path,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RuntimePackage:
    plan = _json_file(Path(gate_plan_path), "GATE-PLAN")
    setup = _json_file(Path(gate_setup_path), "GATE-SETUP")
    setup_receipt = _json_file(Path(setup_receipt_path), "setup receipt")
    readiness = _json_file(Path(readiness_path), "runtime readiness")
    gate_run = _json_file(Path(gate_run_path), "GATE-RUN")
    bindings = inspect_compiled_plan(campaign_root)
    checked_plan, plan_sha = validate_gate_plan(plan, bindings)
    now = clock()
    _, setup_sha = validate_gate_setup_reference(setup, checked_plan, plan_sha)
    checked_receipt, receipt_sha = validate_setup_receipt(
        setup_receipt, checked_plan, plan_sha, setup_sha
    )
    validate_consumed_gate_setup(setup, checked_receipt)
    checked_readiness, readiness_sha = validate_readiness_reference(
        readiness, checked_plan, plan_sha
    )
    if _timestamp(readiness["readinessObservedAt"], "readiness observedAt") < _timestamp(
        checked_receipt["completedAt"], "setup receipt completedAt"
    ):
        raise GateError("runtime readiness predates completed setup")
    if (
        checked_readiness["gateSetupSha256"] != setup_sha
        or checked_readiness["setupReceiptSha256"] != receipt_sha
        or canonical_bytes(checked_readiness["installedBindings"])
        != canonical_bytes(installed_bindings(checked_receipt, receipt_sha))
    ):
        raise GateError("readiness is not bound to the exact setup receipt")
    checked_gate_run, gate_run_sha = validate_gate_run_reference(
        gate_run, checked_plan, plan_sha, checked_readiness, readiness_sha
    )
    return RuntimePackage(
        bindings=bindings,
        gate_plan=checked_plan,
        gate_plan_sha256=plan_sha,
        gate_setup=copy.deepcopy(setup),
        gate_setup_sha256=setup_sha,
        setup_receipt=checked_receipt,
        setup_receipt_sha256=receipt_sha,
        readiness=checked_readiness,
        readiness_sha256=readiness_sha,
        gate_run=checked_gate_run,
        gate_run_sha256=gate_run_sha,
        validated_at=now,
    )


def authorize_from_files(
    campaign_root: Path,
    gate_plan_path: Path,
    gate_setup_path: Path,
    setup_receipt_path: Path,
    readiness_path: Path,
    gate_run_path: Path,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RuntimePackage:
    package = replay_runtime_from_files(
        campaign_root, gate_plan_path, gate_setup_path, setup_receipt_path,
        readiness_path, gate_run_path, clock=clock,
    )
    validate_readiness(
        package.readiness, package.gate_plan, package.gate_plan_sha256,
        now=package.validated_at,
    )
    validate_gate_run(
        package.gate_run, package.gate_plan, package.gate_plan_sha256,
        package.readiness, package.readiness_sha256, now=package.validated_at,
    )
    return package


# 2026-10-14 (campaign F, BUDGET_F change 1): the plan variable the materialized posture overlay binds OTEL_METRIC_EXPORT_INTERVAL to, set for the
# epochs below only (materialize.render_posture_overlay renders the binding for the same epochs; verify_materializer_constants compares the two
# statements, and candidate_setup.compose_environment follows the rendered overlay).  Every other epoch's environment is unchanged.
# 2026-10-15: the F ablation (otel-offpath-f-nolag-v1) carries the interval too (it differs from F only by the kafkametrics rendering).
METRIC_EXPORT_INTERVAL_STUDY_EPOCHS = ("otel-offpath-f-v1", "otel-offpath-f-nolag-v1")
METRIC_EXPORT_INTERVAL_VARIABLE = "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"
METRIC_EXPORT_INTERVAL_MILLISECONDS = "5000"


def posture_environment(posture: str, source_root: str) -> dict[str, str]:
    catalog = posture_catalog()
    if posture not in catalog["postures"]:
        raise GateError("unknown candidate posture")
    active = set(catalog["postures"][posture]["activeApplicationServices"])
    environment: dict[str, str] = {
        "OTEL_CANDIDATE_ENVOY_CONFIG": (
            f"{source_root}/src/frontendproxy/envoy.tmpl.yaml"
            if "frontendproxy" in active
            else f"{source_root}/src/frontendproxy/envoy.no-tracing.tmpl.yaml"
        ),
        "OTEL_CANDIDATE_IMAGEPROVIDER_NGINX_TEMPLATE": (
            f"{source_root}/src/imageprovider/nginx.conf.template"
            if "imageprovider" in active
            else f"{source_root}/src/imageprovider/nginx.no-otel.conf.template"
        ),
    }
    for service in catalog["applicationServices"]:
        key = service.replace("-", "_").upper()
        enabled = service in active
        environment[f"OTEL_CANDIDATE_{key}_DISABLED"] = "false" if enabled else "true"
        environment[f"OTEL_CANDIDATE_{key}_ENABLED"] = "true" if enabled else "false"
        environment[f"OTEL_CANDIDATE_{key}_EXPORTER"] = "otlp" if enabled else "none"
    for service, (variable, value) in EXPECTED_AGENT_ENVIRONMENT.items():
        key = service.replace("-", "_").upper()
        environment[f"OTEL_CANDIDATE_{key}_{variable}"] = value if service in active else ""
    flagd = EXPECTED_FLAGD_ENVIRONMENT["enabled" if "flagd" in active else "disabled"]
    for variable, value in flagd.items():
        environment[f"OTEL_CANDIDATE_FLAGD_{variable.removeprefix('FLAGD_')}"] = value
    if STUDY_EPOCH in METRIC_EXPORT_INTERVAL_STUDY_EPOCHS:
        environment[METRIC_EXPORT_INTERVAL_VARIABLE] = METRIC_EXPORT_INTERVAL_MILLISECONDS
    return environment


def _path_check_run_id(cells: Sequence[Mapping[str, Any]]) -> str:
    """The run id of the first no-fault ``full`` cell in plan order; it must
    precede every fault cell, so the path check can stop the campaign first."""
    first_fault = next(
        (index for index, cell in enumerate(cells) if cell.get("fault") is not None), len(cells)
    )
    for index, cell in enumerate(cells):
        key = cell["runKey"]
        if key["regime"] == "no-fault-cost" and key["posture"] == "full":
            if index > first_fault:
                raise GateError("the workload path check cell does not precede every fault cell")
            return str(cell["runId"])
    raise GateError("the plan has no no-fault full cell for the workload path check")


def build_cell_contract(package: RuntimePackage, cell: Mapping[str, Any]) -> dict[str, Any]:
    expected = next((candidate for candidate in package.bindings.cells if candidate["runId"] == cell.get("runId")), None)
    if expected is None or canonical_bytes(expected) != canonical_bytes(cell):
        raise GateError("cell differs from the immutable compiled plan")
    if "timing" in expected:
        # Parameterised epochs only: the frozen epoch's contracts stay byte-identical.
        return _sweep_cell_contract(package, expected)
    binding = package.gate_plan["binding"]
    key = expected["runKey"]
    cost = key["regime"] == "no-fault-cost"
    if cost != (expected["fault"] is None):
        raise GateError("cost/effect cell boundary differs")
    source_root = binding["remoteSourceRoot"]
    descriptor = frozen_descriptor()
    design = descriptor["faultDesign"]
    scenario = expected["fault"]
    if scenario is not None and scenario not in design["scenarios"]:
        raise GateError(f"cell fault {scenario!r} is not in the descriptor's fault design")
    artifacts = [
        "application-witness.json", "cell-cleanup.json", "content-manifest.json",
        "otelcol.log", "posture-proof.json", "receipt.json", "request-ledger.json",
        "telemetry-bytes.json", "telemetry.pcap", "trace-correlation.json",
    ]
    if cost:
        artifacts.append("resources.json")
    else:
        artifacts.extend(("effect-resources.json", "intervention.json"))
    return {
        "schemaVersion": 1,
        "kind": CELL_KIND,
        "campaignId": binding["campaignId"],
        "studyEpoch": STUDY_EPOCH,
        "frameworkCommit": binding["frameworkCommit"],
        "gatePlanSha256": package.gate_plan_sha256,
        "gateSetupSha256": package.gate_setup_sha256,
        "setupReceiptSha256": package.setup_receipt_sha256,
        "runtimeReadinessSha256": package.readiness_sha256,
        "gateRunSha256": package.gate_run_sha256,
        "targetContractSha256": binding["targetContractSha256"],
        "releaseRoot": binding["releaseRoot"],
        "materializedSourceSha256": package.readiness["installedBindings"]["materializedSourceSha256"],
        "imageIds": copy.deepcopy(package.readiness["installedBindings"]["imageIds"]),
        "installedControllerDigests": copy.deepcopy(package.readiness["installedBindings"]["installedControllerDigests"]),
        "runId": expected["runId"],
        "runKey": copy.deepcopy(key),
        "ordinalPosition": expected["ordinalPosition"],
        "compiledArtifactRoot": expected["artifactRoot"],
        "target": copy.deepcopy(binding["target"]),
        "compose": copy.deepcopy(binding["compose"]),
        "remoteSourceRoot": source_root,
        "remoteArtifactRoot": f"{binding['remoteArtifactRoot']}/{expected['artifactRoot']}",
        "exclusiveLeasePath": binding["exclusiveLeasePath"],
        "posture": {
            "id": key["posture"],
            "environment": posture_environment(key["posture"], source_root),
            "expected": posture_catalog()["postures"][key["posture"]],
        },
        "workload": {
            # The offered unit is one checkout journey (descriptor "workload").
            # urlPath is the journey's terminal step: the ledger's url.
            "journey": descriptor["workload"]["journey"],
            "urlPath": OFFPATH_CHECKOUT_PATH,
            "cartPath": OFFPATH_CART_PATH,
            "productId": OFFPATH_PRODUCT_ID,
            "requestsPerSecond": descriptor["workload"]["journeysPerSecond"],
            "concurrency": descriptor["workload"]["concurrency"],
            "offeredRequests": descriptor["workload"]["offeredJourneys"],
            "stepTimeoutSeconds": descriptor["workload"]["stepTimeoutSeconds"],
            "tokenNamespace": expected["runId"],
            "denominator": "offered-journey-ledger",
        },
        "window": {
            "kind": "cost" if cost else "effect",
            "warmupSeconds": 120,
            "measurementSeconds": 600,
            "sharedMonotonicBarrier": True,
            "costClaimEligible": cost,
            "effectResourcesDiagnosticOnly": not cost,
            "poolWithOtherRegime": False,
        },
        "fault": {
            "scenario": scenario,
            "service": design["scenarios"][scenario]["service"] if not cost else None,
            "action": design["scenarios"][scenario]["action"] if not cost else None,
            "entryRouteDuringFault": (
                design["scenarios"][scenario]["entryRouteDuringFault"] if not cost else None
            ),
            "onsetSeconds": design["onsetSeconds"] if not cost else None,
            "holdSeconds": design["holdSeconds"] if not cost else None,
            "manifestationAndRecoveryRequired": not cost,
        },
        # The first no-fault full cell's traced journeys must reproduce the
        # selected literal before any fault cell runs (candidate_remote).
        "workloadPathCheck": {
            "synchronousPath": list(SELECTED_CLOSURE),
            "asynchronousServices": sorted(set(ASYNC_CLOSURE) - set(SELECTED_CLOSURE)),
            "gatesCampaign": expected["runId"] == _path_check_run_id(package.bindings.cells),
        },
        "measurement": {
            "applicationCpu": "docker-engine-cumulative-nanoseconds",
            "emittedTelemetryBytes": "non-retransmitted-otlp-tcp-payload-bytes",
            "onWireTelemetryBytes": "captured-otlp-frame-bytes",
            "requestWitness": "frontendproxy-json-access-log",
            "originalTraceCorrelation": "injected-w3c-trace-id",
        },
        "attemptPolicy": {
            "attempt": key["attempt"], "beginsBeforeFirstExternalMutation": True,
            "retryAllowed": False, "substitutionAllowed": False,
            "rerandomizationAllowed": False,
        },
        "requiredArtifacts": sorted(artifacts),
        "promotionAuthorized": False,
    }


SWEEP_TIMING_KEYS = frozenset({
    "requestsPerSecond", "interArrivalSeconds", "concurrency", "requestTimeoutSeconds", "warmupSeconds",
    "warmupRequestsPerSecond", "warmupOffered", "measurementSeconds", "offered", "faultApplied",
    "faultOnsetBaseSeconds", "faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "faultHoldSeconds",
    "scoredWindowSeconds", "postRecoveryAllowanceSeconds", "scheduledSlotsByPhase", "route",
    "upstreamGeneratorsOff", "planRunCount", "planMinimumRemainingSeconds", "applicationLogTimestamps", "probeStamps",
    "protocolGates", "traceDrainSeconds", "traceIncompleteAllowanceShare", "traceIncompleteAllowanceMinimum",
    "serviceMemoryLimitBytes", "containerHealthGuard",
})
# 2026-10-04 (protocol decision 56, main repo research/PROTOCOL_DRAFT_20261002.md round 12): the quiet calibration
# epoch's compiled timing adds the trace rule it runs under (candidate_quiet.TRACE_COMPLETENESS_RULE); the sweep's key
# set above is unchanged.
# 2026-10-09 (campaign B, candidate_repeat.py): the repeat epoch's timing adds H10 (duringFaultProbe, False) and H4
# (freezeStamps, True) to every cell, and the decision-56 trace rule to its NO-FAULT cells only (fault cells keep the
# sweep's decision-25 rule, which has no key).
# 2026-10-11: campaign C (decision 82) has B's key sets exactly.
# 2026-10-12: the load pilot has C's key sets plus generatorOpenFilesMinimum on every cell (candidate_remote raises the
# generator's open-file soft limit to it before the cell starts, or refuses the cell).
EPOCH_EXTRA_TIMING_KEYS = {
    QUIET_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    REPEAT_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps"}),
    REPEAT_C_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps"}),
    LOAD_PILOT_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum"}),
    # 2026-10-13: the off-path pilot has the load pilot's key sets plus the workload mix on every cell.
    OFFPATH_PILOT_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}),
    OFFPATH_PILOT_V2_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}),
    OFFPATH_E_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}),
    OFFPATH_F_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}),
    OFFPATH_F_NOLAG_STUDY_EPOCH: frozenset({"duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}),
}
EPOCH_NO_FAULT_TIMING_KEYS = {
    REPEAT_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    REPEAT_C_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    LOAD_PILOT_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    OFFPATH_PILOT_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    OFFPATH_PILOT_V2_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    OFFPATH_E_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    OFFPATH_F_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
    OFFPATH_F_NOLAG_STUDY_EPOCH: frozenset({"traceCompletenessRule"}),
}


def timed_cell_timing_keys(faulted: bool = False) -> frozenset[str]:
    """The active timed epoch's compiled timing keys for a fault (``faulted``) or no-fault cell: the sweep's, plus the
    quiet epoch's trace-rule key, or the repeat epoch's H10/H4 keys and, in its no-fault cells, the trace-rule key."""
    keys = SWEEP_TIMING_KEYS | EPOCH_EXTRA_TIMING_KEYS.get(STUDY_EPOCH, frozenset())
    if not faulted:
        keys = keys | EPOCH_NO_FAULT_TIMING_KEYS.get(STUDY_EPOCH, frozenset())
    return keys


def sweep_route_services(timing: Mapping[str, Any]) -> list[str]:
    """The services the cell's workload is required to show in the collector's signals: its one route's (every epoch before the
    off-path pilot), or, for a cell whose timing carries the multi-route mix, the union over the mix's routes of the services each
    route is guaranteed to reach, sorted."""
    mix = timing.get("workloadMix")
    if mix is None:
        return list(timing["route"]["services"])
    return sorted({service for route in mix["routes"].values() for service in route["requiredServices"]})


def sweep_cell_timing(contract: Mapping[str, Any]) -> dict[str, Any]:
    """A sweep contract's timing, which must be exactly the active compiled plan's timing for that run ID: a
    retained contract cannot bring its own numbers."""
    timing = contract.get("timing")
    if not isinstance(timing, dict) or set(timing) != timed_cell_timing_keys(timing.get("faultApplied") is True):
        raise GateError("cell timing fields differ")
    if not is_sweep_epoch():
        raise GateError("a timed cell contract needs the epoch selector that compiled it")
    pilot = _pilot_module()
    plan = pilot.compile_plan(pilot.load_descriptor(DESCRIPTOR), (contract.get("runKey") or {}).get("attempt"))
    compiled = [cell for cell in pilot.flatten_cells(plan) if cell["runId"] == contract.get("runId")]
    if len(compiled) != 1 or canonical_bytes(compiled[0]["timing"]) != canonical_bytes(timing):
        raise GateError("cell timing is not the active compiled plan's timing for this run ID")
    return copy.deepcopy(timing)


def _sweep_cell_contract(package: RuntimePackage, expected: Mapping[str, Any]) -> dict[str, Any]:
    """The cell contract of a parameterised (traffic-sweep) epoch: one route, a per-cell rate and fault onset,
    the upstream generator off, protocol gates on the target.  Every number comes from the cell's compiled timing."""
    if not is_sweep_epoch():
        raise GateError("a timed plan cell needs the epoch selector that compiled it")
    binding = package.gate_plan["binding"]
    key = expected["runKey"]
    timing = copy.deepcopy(expected["timing"])
    if set(timing) != timed_cell_timing_keys(expected["fault"] is not None):
        raise GateError("cell timing fields differ")
    descriptor = frozen_descriptor()
    design = descriptor["faultDesign"]
    scenario = expected["fault"]
    faulted = scenario is not None
    if faulted != bool(timing["faultApplied"]) or faulted != (key["regime"] != "no-fault-calibration"):
        raise GateError("fault/no-fault cell boundary differs")
    if faulted and scenario not in design["scenarios"]:
        raise GateError(f"cell fault {scenario!r} is not in the descriptor's fault design")
    contract_scenario = design["scenarios"][scenario] if faulted else {}
    if key["posture"] != "full" or timing["route"]["path"] != descriptor["workload"]["path"]:
        raise GateError("sweep cell posture or route differs from the descriptor")
    source_root = binding["remoteSourceRoot"]
    artifacts = [
        "application-witness.json", "application.log", "cell-cleanup.json", "container-health.json",
        "content-manifest.json",
        "otelcol.log", "posture-proof.json", "protocol-gates.json", "receipt.json", "request-ledger.json",
        "resources.json", "telemetry-bytes.json", "telemetry.pcap", "trace-completeness.json",
        "trace-correlation.json", "upstream-generator.json",
    ]
    if faulted:
        artifacts.append("intervention.json")
        # H4 (campaign B): a pause cell also retains the Docker pause/unpause events of its target container.
        if timing.get("freezeStamps") is True and contract_scenario["action"] == "pause":
            artifacts.append("docker-events.json")
    return {
        "schemaVersion": 1,
        "kind": CELL_KIND,
        "campaignId": binding["campaignId"],
        "studyEpoch": STUDY_EPOCH,
        "frameworkCommit": binding["frameworkCommit"],
        "gatePlanSha256": package.gate_plan_sha256,
        "gateSetupSha256": package.gate_setup_sha256,
        "setupReceiptSha256": package.setup_receipt_sha256,
        "runtimeReadinessSha256": package.readiness_sha256,
        "gateRunSha256": package.gate_run_sha256,
        "targetContractSha256": binding["targetContractSha256"],
        "releaseRoot": binding["releaseRoot"],
        "materializedSourceSha256": package.readiness["installedBindings"]["materializedSourceSha256"],
        "imageIds": copy.deepcopy(package.readiness["installedBindings"]["imageIds"]),
        "installedControllerDigests": copy.deepcopy(package.readiness["installedBindings"]["installedControllerDigests"]),
        "runId": expected["runId"],
        "runKey": copy.deepcopy(key),
        "ordinalPosition": expected["ordinalPosition"],
        "compiledArtifactRoot": expected["artifactRoot"],
        "target": copy.deepcopy(binding["target"]),
        "compose": copy.deepcopy(binding["compose"]),
        "remoteSourceRoot": source_root,
        "remoteArtifactRoot": f"{binding['remoteArtifactRoot']}/{expected['artifactRoot']}",
        "exclusiveLeasePath": binding["exclusiveLeasePath"],
        "posture": {
            "id": key["posture"],
            "environment": posture_environment(key["posture"], source_root),
            "expected": posture_catalog()["postures"][key["posture"]],
        },
        "workload": {
            "kind": descriptor["workload"]["kind"],
            "method": timing["route"]["method"],
            "urlPath": timing["route"]["path"],
            "productId": descriptor["workload"]["productId"],
            "routeServices": sweep_route_services(timing),
            "requestsPerSecond": timing["requestsPerSecond"],
            "concurrency": timing["concurrency"],
            "offeredRequests": timing["offered"],
            "requestTimeoutSeconds": timing["requestTimeoutSeconds"],
            "warmupRequestsPerSecond": timing["warmupRequestsPerSecond"],
            "warmupOffered": timing["warmupOffered"],
            "tokenNamespace": expected["runId"],
            "denominator": "offered-request-ledger",
            "upstreamGeneratorsOff": list(timing["upstreamGeneratorsOff"]),
            # Stack-wide readiness before the warm-up: the harness's own checkout journey, unchanged.
            "readinessJourney": {
                "cartPath": OFFPATH_CART_PATH,
                "urlPath": OFFPATH_CHECKOUT_PATH,
                "productId": OFFPATH_PRODUCT_ID,
                "stepTimeoutSeconds": descriptor["workload"]["requestTimeoutSeconds"],
            },
        },
        "window": {
            "kind": "effect" if faulted else "calibration",
            "warmupSeconds": timing["warmupSeconds"],
            "measurementSeconds": timing["measurementSeconds"],
            "sharedMonotonicBarrier": True,
            "costClaimEligible": False,
            "effectResourcesDiagnosticOnly": True,
            "poolWithOtherRegime": False,
        },
        "fault": {
            "scenario": scenario,
            "service": contract_scenario.get("service"),
            "action": contract_scenario.get("action"),
            "entryRouteDuringFault": contract_scenario.get("entryRouteDuringFault"),
            "nanoCpus": contract_scenario.get("nanoCpus"),
            "onsetSeconds": timing["faultOnsetSeconds"] if faulted else None,
            "holdSeconds": timing["faultHoldSeconds"] if faulted else None,
            "manifestationAndRecoveryRequired": faulted,
        },
        # The offpath selected-literal check does not apply: the route's path is checked in every cell by the
        # terminal's correlation rule (route services within the trace of every successful pre/post request).
        "workloadPathCheck": {"synchronousPath": [], "asynchronousServices": [], "gatesCampaign": False},
        "measurement": {
            "applicationCpu": "docker-engine-cumulative-nanoseconds",
            "emittedTelemetryBytes": "non-retransmitted-otlp-tcp-payload-bytes",
            "onWireTelemetryBytes": "captured-otlp-frame-bytes",
            "requestWitness": "frontendproxy-json-access-log",
            "originalTraceCorrelation": "injected-w3c-trace-id",
            "applicationLogs": "docker-compose-logs-timestamps",
            "protocolGates": CONTROLLER_PATHS["protocol-gates"],
        },
        "attemptPolicy": {
            "attempt": key["attempt"], "beginsBeforeFirstExternalMutation": True,
            "retryAllowed": False, "substitutionAllowed": False,
            "rerandomizationAllowed": False,
        },
        "timing": timing,
        "requiredArtifacts": sorted(artifacts),
        "promotionAuthorized": False,
    }


def execution_package(package: RuntimePackage) -> dict[str, Any]:
    cells = [build_cell_contract(package, cell) for cell in package.bindings.cells]
    binding = package.gate_plan["binding"]
    return {
        "schemaVersion": 1,
        "kind": EXECUTION_KIND,
        "campaignId": binding["campaignId"],
        "studyEpoch": STUDY_EPOCH,
        "target": copy.deepcopy(binding["target"]),
        "gatePlanSha256": package.gate_plan_sha256,
        "gateSetupSha256": package.gate_setup_sha256,
        "setupReceiptSha256": package.setup_receipt_sha256,
        "runtimeReadinessSha256": package.readiness_sha256,
        "gateRunSha256": package.gate_run_sha256,
        "targetContractSha256": binding["targetContractSha256"],
        "releaseRoot": binding["releaseRoot"],
        "remoteSourceRoot": binding["remoteSourceRoot"],
        "materializedSourceSha256": package.readiness["installedBindings"]["materializedSourceSha256"],
        "imageIds": copy.deepcopy(package.readiness["installedBindings"]["imageIds"]),
        "installedControllerDigests": copy.deepcopy(package.readiness["installedBindings"]["installedControllerDigests"]),
        "authorizationDeadline": package.gate_run["binding"]["authorizationDeadline"],
        "cleanupReserveSeconds": package.gate_run["binding"]["cleanupReserveSeconds"],
        "minimumRemainingAtFirstMutationSeconds": package.gate_run["binding"][
            "minimumRemainingAtFirstMutationSeconds"
        ],
        "exclusiveLeasePath": binding["exclusiveLeasePath"],
        "leaseLaunchMode": "systemd-run-flock-no-fork-inherited-fd",
        "remoteArtifactRoot": binding["remoteArtifactRoot"],
        "composeProject": binding["compose"]["project"],
        "composePorts": copy.deepcopy(binding["compose"]["ports"]),
        "systemdUnit": f"{binding['compose']['project']}.service",
        "handoff": copy.deepcopy(binding["handoff"]),
        "controllerDigests": copy.deepcopy(binding["controllerDigests"]),
        "authorizedRunIds": list(package.bindings.run_ids),
        "runCount": RUN_COUNT,
        "cells": cells,
        "oneShot": True,
        "promotionAuthorized": False,
    }


class CommandRunner(Protocol):
    def __call__(self, argv: Sequence[str], *, input: bytes | None = None) -> subprocess.CompletedProcess[bytes]: ...


def _default_runner(argv: Sequence[str], *, input: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(list(argv), input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


# --- Hotel lesson 2, applied before it can bite ---------------------------
# `ssh host a b c` does NOT run an argv on the far side: openssh joins the
# words with single spaces and hands the result to the remote account's LOGIN
# SHELL. root's login shell on fb14srv6 is zsh (measured 2026-09-12), and on
# fb14srv4 that turned an unquoted `python3 -I -c <source>` into
# `zsh:12: parse error near '()'` and cost a Hotel launch attempt.
#
# This module never sends Python *source* -- every remote program is an
# already-installed file named by absolute path -- so today every token it
# sends is metacharacter-free by construction (`SAFE_NAME`, `_safe_posix`,
# `HEX40`). That is an argument about the current values, not about the
# mechanism, and it is exactly the kind of argument the Hotel attempt-2
# author would also have made. `_ssh` removes the mechanism instead: the
# remote words are quoted for the remote shell with `shlex.join`, so a future
# campaign id, unit name or path containing a space, quote or paren cannot
# be re-parsed by zsh.
#
# `remoteCommand` is kept beside `argv` in the receipt so a reader can still
# see the unquoted intent; `argv` remains the bytes actually executed.
def _ssh(destination: str, tokens: Sequence[str]) -> list[str]:
    """One ssh invocation whose remote words survive the remote login shell."""
    words = [str(token) for token in tokens]
    if not words:
        raise GateError("remote command is empty")
    return ["ssh", "--", destination, shlex.join(words)]


class ComposeSshAdapter:
    """Root transport/setup plus disconnect-safe ``stig`` execution."""

    def __init__(self, runner: CommandRunner = _default_runner):
        self._runner = runner

    @staticmethod
    def _receipt(argv: Sequence[str], result: subprocess.CompletedProcess[bytes]) -> dict[str, Any]:
        return {
            "argv": list(argv), "returnCode": result.returncode,
            "stdoutSha256": hashlib.sha256(result.stdout).hexdigest(),
            "stderrSha256": hashlib.sha256(result.stderr).hexdigest(),
        }

    def setup(
        self,
        package: SetupPackage,
        repository_bundle: Path,
        upstream_bundle: Path,
        local_staging_root: Path,
    ) -> dict[str, Any]:
        refuse_unsupported("GATE-SETUP transport")
        validate_gate_setup(
            package.gate_setup, package.gate_plan, package.gate_plan_sha256,
            now=datetime.now(timezone.utc),
        )
        binding = package.gate_plan["binding"]
        repository_bundle = Path(repository_bundle).resolve()
        upstream_bundle = Path(upstream_bundle).resolve()
        if (
            file_sha256(repository_bundle) != binding["repositoryBundleSha256"]
            or file_sha256(upstream_bundle) != binding["upstreamBundleSha256"]
        ):
            raise GateError("local Git bundle bytes differ from GATE-PLAN")
        staging = Path(local_staging_root).resolve()
        if staging.exists() or staging.is_symlink():
            raise GateError("local setup staging root must be absent")
        staging.mkdir(parents=True, mode=0o700)
        document = setup_execution_package(package)
        package_path = staging / "setup-package.json"
        package_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(package_path, 0o600)
        controller = ROOT / CONTROLLER_PATHS["remote-setup-controller"]
        checksum = staging / "setup.sha256"
        remote_root = binding["setupStagingRoot"]
        remote_files = {
            "candidate_setup.py": controller,
            "framework.bundle": repository_bundle,
            "opentelemetry-demo.bundle": upstream_bundle,
            "setup-package.json": package_path,
        }
        checksum.write_text("".join(
            f"{file_sha256(path)}  {remote_root}/{name}\n"
            for name, path in sorted(remote_files.items())
        ), encoding="ascii")
        destination = f"root@{binding['target']['host']}"
        commands = [_ssh(destination, ["install", "-d", "-m", "0755", "--", remote_root])]
        commands.extend(
            ["scp", "--", str(path), f"{destination}:{remote_root}/{name}"]
            for name, path in remote_files.items()
        )
        commands.extend((
            ["scp", "--", str(checksum), f"{destination}:{remote_root}/setup.sha256"],
            _ssh(destination, ["sha256sum", "-c", f"{remote_root}/setup.sha256"]),
            _ssh(destination, ["/usr/bin/python3", "-I", f"{remote_root}/candidate_setup.py", "install", "--package", f"{remote_root}/setup-package.json"]),
            ["scp", "--", f"{destination}:{binding['remoteArtifactRoot']}/.controller/setup-receipt.json", str(staging / "setup-receipt.json")],
        ))
        receipts: list[dict[str, Any]] = []
        for argv in commands:
            result = self._runner(argv)
            receipts.append(self._receipt(argv, result))
            if result.returncode != 0:
                raise GateError(f"bounded GATE-SETUP transport failed at {argv[0]}")
        receipt = _json_file(staging / "setup-receipt.json", "fetched setup receipt")
        checked, receipt_sha = validate_setup_receipt(
            receipt, package.gate_plan, package.gate_plan_sha256,
            package.gate_setup_sha256,
        )
        validate_consumed_gate_setup(package.gate_setup, checked)
        return {
            "schemaVersion": 1, "kind": "otel-demo-candidate-setup-transport-receipt-v1",
            "campaignId": binding["campaignId"], "target": copy.deepcopy(binding["target"]),
            "commands": receipts, "setupReceiptSha256": receipt_sha,
            "installedBindings": installed_bindings(checked, receipt_sha),
            "cellsRun": 0, "runtimeAuthorized": False, "promotionAuthorized": False,
        }

    def capture_readiness(
        self,
        request: ReadinessRequest,
        local_staging_root: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> dict[str, Any]:
        """Ask the installed target entrypoint for a refreshable zero-cell receipt."""
        refuse_unsupported("target readiness transport")
        binding = request.gate_plan["binding"]
        staging = Path(local_staging_root).resolve()
        if staging.is_symlink() or not staging.is_dir():
            raise GateError("readiness staging root must be an existing non-symlink directory")
        plan_path = staging / "target-readiness-gate-plan.json"
        setup_path = staging / "target-readiness-gate-setup.json"
        local_readiness = staging / "readiness.json"
        for path, document in (
            (plan_path, request.gate_plan), (setup_path, request.gate_setup),
        ):
            if path.exists() and path.is_symlink():
                raise GateError("local readiness control path is a symlink")
            path.write_text(
                json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            os.chmod(path, 0o600)
        if local_readiness.exists() or local_readiness.is_symlink():
            if local_readiness.is_symlink() or not local_readiness.is_file():
                raise GateError("local readiness output is not a regular file")
            local_readiness.unlink()
        destination = f"root@{binding['target']['host']}"
        controller_root = f"{binding['remoteArtifactRoot']}/.controller"
        remote_plan = f"{binding['setupStagingRoot']}/target-readiness-gate-plan.json"
        remote_setup = f"{binding['setupStagingRoot']}/target-readiness-gate-setup.json"
        remote_receipt = f"{controller_root}/setup-receipt.json"
        remote_readiness = f"{controller_root}/readiness.json"
        installed_entrypoint = (
            f"{binding['repositoryRoot']}/{CONTROLLER_PATHS['runtime-admission']}"
        )
        commands = [
            ["scp", "--", str(plan_path), f"{destination}:{remote_plan}"],
            ["scp", "--", str(setup_path), f"{destination}:{remote_setup}"],
            _ssh(destination, ["sha256sum", installed_entrypoint]),
            _ssh(destination, [
                "/usr/bin/python3", "-I", installed_entrypoint,
                "target-readiness", "--gate-plan", remote_plan,
                "--gate-setup", remote_setup, "--setup-receipt", remote_receipt,
                "--output", remote_readiness,
            ]),
            ["scp", "--", f"{destination}:{remote_readiness}", str(local_readiness)],
        ]
        receipts: list[dict[str, Any]] = []
        for index, argv in enumerate(commands):
            result = self._runner(argv)
            receipts.append(self._receipt(argv, result))
            if index == 2 and result.returncode == 0:
                observed = result.stdout.decode("utf-8", errors="replace").strip().split()
                if (
                    not observed
                    or observed[0] != binding["controllerDigests"]["runtime-admission"]
                ):
                    raise GateError("installed readiness producer digest differs")
            if result.returncode != 0:
                raise GateError(f"target readiness transport failed at {argv[0]}")
        readiness = _json_file(local_readiness, "fetched target readiness")
        observed_now = clock()
        readiness_sha = validate_readiness(
            readiness, request.gate_plan, request.gate_plan_sha256,
            now=observed_now,
        )
        if (
            readiness["gateSetupSha256"] != request.gate_setup_sha256
            or readiness["setupReceiptSha256"] != request.setup_receipt_sha256
            or readiness["producer"]["cellsRun"] != 0
        ):
            raise GateError("target readiness differs from the exact consumed setup")
        return {
            "schemaVersion": 1,
            "kind": "otel-demo-candidate-readiness-transport-receipt-v1",
            "campaignId": binding["campaignId"],
            "target": copy.deepcopy(binding["target"]),
            "runtimeReadinessSha256": readiness_sha,
            "readinessObservedAt": readiness["readinessObservedAt"],
            "commands": receipts,
            "cellsRun": 0,
            "runtimeAuthorized": False,
            "promotionAuthorized": False,
        }

    def _resolve_launch_tokens(
        self,
        destination: str,
        binaries: Sequence[str],
        gids: Sequence[int],
    ) -> tuple[dict[str, str], dict[int, str], list[dict[str, Any]]]:
        """Resolve every binary path and group name of the launch argv ON THE TARGET.

        Instance nine of the inherited-from-Hotel spelling class (2026-09-17):
        the launch argv baked ``/usr/sbin/runuser``, which exists only on
        fb14srv4; fb14srv5 and fb14srv6 carry ``/sbin/runuser``.  A second
        hardcoded absolute path would only move the defect, because the three
        hosts genuinely differ, so each name is resolved in the target's own
        shell and then proven executable with ``test -x`` at exactly the
        resolved path.  The resolved string is the one spent in both the
        readability probe and the ``systemd-run`` argv: a guard that exercises
        a different spelling than the thing it guards is not a guard.

        Group names are resolved the same way and for the same reason as
        ``candidate_setup.run_as_stig``: util-linux 2.36.1 (all three hosts)
        rejects a numeric ``--group``/``--supp-group`` even when the gid is in
        ``/etc/group``.  The numeric gid stays the authorization contract and is
        re-asserted against getent's own third field; only the spelling changes.
        """
        receipts: list[dict[str, Any]] = []
        paths: dict[str, str] = {}
        for name in binaries:
            argv = _ssh(destination, ["command", "-v", name])
            result = self._runner(argv)
            receipts.append(self._receipt(argv, result))
            if result.returncode != 0:
                raise GateError(f"launch argv binary {name!r} does not resolve on the target")
            lines = [
                line.strip()
                for line in result.stdout.decode("utf-8", errors="replace").splitlines()
                if line.strip()
            ]
            resolved = lines[-1] if lines else ""
            if not resolved.startswith("/"):
                raise GateError(
                    f"launch argv binary {name!r} did not resolve to an absolute path on the target"
                )
            probe = _ssh(destination, ["test", "-x", resolved])
            probe_result = self._runner(probe)
            receipts.append(self._receipt(probe, probe_result))
            if probe_result.returncode != 0:
                raise GateError(
                    f"launch argv binary {name!r} at {resolved} is not executable on the target"
                )
            paths[name] = resolved
        names: dict[int, str] = {}
        for gid in gids:
            argv = _ssh(destination, ["getent", "group", str(gid)])
            result = self._runner(argv)
            receipts.append(self._receipt(argv, result))
            if result.returncode != 0:
                raise GateError(f"launch argv gid {gid} names no group on the target")
            fields = result.stdout.decode("utf-8", errors="replace").strip().split(":")
            if len(fields) < 3 or not fields[0] or fields[2] != str(gid):
                raise GateError(f"launch argv gid {gid} did not resolve to a named group on the target")
            names[gid] = fields[0]
        return paths, names, receipts

    def _verify_unit_active(
        self, destination: str, unit: str,
    ) -> tuple[dict[str, str], list[dict[str, Any]]]:
        """Prove the unit is RUNNING, not merely accepted.

        ``systemd-run`` exits 0 when systemd *accepts* the transient unit and
        says nothing about whether its first exec succeeded.  On 2026-09-17 the
        OTel unit was accepted and died in 0 s (``status=69/UNAVAILABLE``,
        ``flock: failed to execute /usr/sbin/runuser``) and the launch was
        reported as successful.  ``--collect`` unloads a failed transient unit,
        so a dead launch shows up as ``LoadState=not-found`` rather than
        ``failed``; both fields are therefore required, not just one.
        """
        receipts: list[dict[str, Any]] = []
        fields: dict[str, str] = {}
        for attempt in range(LAUNCH_VERIFY_ATTEMPTS):
            if attempt:
                time.sleep(LAUNCH_VERIFY_SETTLE_SECONDS)
            argv = _ssh(destination, [
                "systemctl", "show", unit, "--no-pager",
                "--property=LoadState", "--property=ActiveState",
                "--property=SubState", "--property=Result",
                "--property=ExecMainStatus", "--property=ExecMainPID",
            ])
            result = self._runner(argv)
            receipts.append(self._receipt(argv, result))
            fields = {}
            for line in result.stdout.decode("utf-8", errors="replace").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    fields[key] = value
            if (
                result.returncode == 0
                and fields.get("LoadState") == "loaded"
                and fields.get("ActiveState") in {"active", "reloading"}
            ):
                return fields, receipts
            if fields.get("ActiveState") != "activating":
                break
        journal_argv = _ssh(destination, [
            "journalctl", "--unit", unit, "--no-pager", "--lines", "40",
        ])
        journal = self._runner(journal_argv)
        receipts.append(self._receipt(journal_argv, journal))
        tail = journal.stdout.decode("utf-8", errors="replace").strip().splitlines()[-6:]
        observed = ", ".join(f"{key}={value}" for key, value in sorted(fields.items()))
        raise GateError(
            "systemd accepted the unit but it is not running: "
            + (observed or "no unit properties returned")
            + ("" if not tail else " | journal: " + " / ".join(line.strip() for line in tail))
        )

    def launch(self, package: RuntimePackage, local_staging_root: Path) -> dict[str, Any]:
        refuse_unsupported("candidate launch")
        # Recheck the temporal gate immediately before creating launch bytes.
        now = datetime.now(timezone.utc)
        validate_readiness(
            package.readiness, package.gate_plan, package.gate_plan_sha256,
            now=now,
        )
        validate_gate_run(
            package.gate_run,
            package.gate_plan,
            package.gate_plan_sha256,
            package.readiness,
            package.readiness_sha256,
            now=now,
        )
        document = execution_package(package)
        binding = package.gate_plan["binding"]
        staging = Path(local_staging_root).resolve()
        if staging.exists() or staging.is_symlink():
            raise GateError("local launch staging root must be absent")
        staging.mkdir(parents=True, mode=0o700)
        package_path = staging / "execution-package.json"
        payload = json.dumps(document, indent=2, sort_keys=True).encode() + b"\n"
        package_path.write_bytes(payload)
        os.chmod(package_path, 0o600)
        host = binding["target"]["host"]
        user = binding["target"]["transportUser"]
        remote_root = f"{binding['remoteArtifactRoot']}/.controller"
        _safe_posix(remote_root, "remote controller root", absolute=True)
        destination = f"{user}@{host}"
        remote_controller = f"{remote_root}/candidate_remote.py"
        remote_package = f"{remote_root}/execution-package.json"
        unit = document["systemdUnit"]
        # Every binary and group spelling this argv spends is resolved on the
        # target first; nothing below is a literal inherited from another host.
        tools, groups, resolution = self._resolve_launch_tokens(
            destination, LAUNCH_ARGV_BINARIES, LAUNCH_ARGV_GIDS,
        )
        commands = [
            ["scp", "--", str(package_path), f"{destination}:{remote_package}"],
            _ssh(destination, ["chown", "1016:1016", "--", remote_package]),
            # Hotel lesson 6: the root supervisor spawns the unprivileged child
            # with --package pointing at this file. On fb14srv4 the equivalent
            # file was root:root 0600 in a root-only directory and the child died
            # with Permission denied 4 s after launch. Prove readability AS the
            # execution identity before systemd-run, not after.
            #
            # 2026-09-18: this probe used to say bare "runuser" while the unit
            # below said "/usr/sbin/runuser". It passed on a host where that
            # path does not exist and certified nothing about the command that
            # mattered. Both now spend the same resolved token.
            _ssh(destination, [tools["runuser"], "--user", "stig", "--", "test", "-r", remote_package]),
            _ssh(destination, ["sha256sum", remote_controller]),
            _ssh(destination, ["systemd-run", "--unit", unit, "--collect", "--property=Type=exec", "--property=TimeoutStartSec=15000", "--", tools["flock"], "--no-fork", "-n", binding["exclusiveLeasePath"], tools["runuser"], "--user", "stig", "--group", groups[1016], "--supp-group", groups[998], "--", tools["python3"], "-I", remote_controller, "run", "--package", remote_package]),
        ]
        receipts: list[dict[str, Any]] = []
        for index, argv in enumerate(commands):
            result = self._runner(argv)
            receipts.append(self._receipt(argv, result))
            if index == 3:
                observed = result.stdout.decode("utf-8", errors="replace").strip().split()
                if result.returncode == 0 and (not observed or observed[0] != binding["controllerDigests"]["remote-compose-controller"]):
                    raise GateError("installed remote controller digest differs before launch")
            if result.returncode != 0:
                raise GateError(f"bounded SSH/Compose transport failed at {argv[0]}")
        # systemd-run returning 0 means the unit was ACCEPTED. Ask the host.
        unit_state, verification = self._verify_unit_active(destination, unit)
        return {
            "schemaVersion": 1, "kind": "otel-demo-candidate-launch-receipt-v1",
            "campaignId": binding["campaignId"], "target": copy.deepcopy(binding["target"]),
            "executionPackageSha256": hashlib.sha256(payload).hexdigest(),
            "systemdUnit": unit, "state": "launched-disconnect-safe",
            "commands": receipts + resolution + verification,
            "resolvedLaunchArgv": {
                "binaries": dict(sorted(tools.items())),
                "groups": {str(gid): name for gid, name in sorted(groups.items())},
            },
            "unitState": unit_state,
            "terminalValidationSha256": None,
            "promotionAuthorized": False,
        }

    def status(self, package: RuntimePackage) -> dict[str, Any]:
        refuse_unsupported("candidate status transport")
        document = execution_package(package)
        binding = package.gate_plan["binding"]
        destination = f"root@{binding['target']['host']}"
        argv = _ssh(destination, ["systemctl", "show", document["systemdUnit"], "--property=ActiveState", "--property=SubState", "--property=Result", "--property=ExecMainStatus", "--no-pager", "--property=LoadState"])
        result = self._runner(argv)
        fields: dict[str, str] = {}
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value
        probes: list[dict[str, Any]] = []
        completion_artifact: str | None = None
        if fields.get("ActiveState") not in {"active", "activating", "reloading"}:
            for name in ("remote-terminal.json", "campaign-abort.json"):
                probe_argv = _ssh(destination, [
                    "test", "-f", f"{binding['remoteArtifactRoot']}/{name}",
                ])
                probe = self._runner(probe_argv)
                probes.append(self._receipt(probe_argv, probe))
                if probe.returncode == 0:
                    completion_artifact = name
                    break
        return {
            "schemaVersion": 1, "kind": "otel-demo-candidate-runtime-status-v1",
            "campaignId": binding["campaignId"], "systemdUnit": document["systemdUnit"],
            "transportReturnCode": result.returncode, "unit": fields,
            "completionProbes": probes,
            "completionArtifact": completion_artifact,
            "terminal": completion_artifact is not None,
            "promotionAuthorized": False,
        }

    def fetch(self, package: RuntimePackage, local_staging_root: Path) -> dict[str, Any]:
        refuse_unsupported("candidate fetch transport")
        binding = package.gate_plan["binding"]
        destination = f"root@{binding['target']['host']}"
        staging = Path(local_staging_root).resolve()
        staging.mkdir(parents=True, mode=0o700, exist_ok=True)
        retained = staging / "retained"
        if retained.exists() or retained.is_symlink():
            raise GateError("refetch destination must be absent")
        argv = ["scp", "-r", "--", f"{destination}:{binding['remoteArtifactRoot']}", str(retained)]
        result = self._runner(argv)
        receipt = self._receipt(argv, result)
        if result.returncode != 0:
            return {"schemaVersion": 1, "kind": "otel-demo-candidate-fetch-receipt-v1", "campaignId": binding["campaignId"], "state": "fetch-failed", "transport": receipt, "terminalValidationSha256": None, "promotionAuthorized": False}
        remote_terminal = retained / "remote-terminal.json"
        remote_abort = retained / "campaign-abort.json"
        if remote_terminal.is_file() and remote_abort.is_file():
            raise GateError("retained campaign contains both terminal and abort artifacts")
        if remote_abort.is_file():
            abort = _exact(_json_file(remote_abort, "campaign abort"), {
                "schemaVersion", "kind", "campaignId", "target", "systemdUnit",
                "errorType", "error", "completedAt", "promotionAuthorized",
            }, "campaign abort")
            if (
                abort["schemaVersion"] != 1
                or abort["kind"] != "otel-demo-candidate-campaign-abort-v1"
                or abort["campaignId"] != binding["campaignId"]
                or abort["target"] != binding["target"]
                or abort["systemdUnit"] != execution_package(package)["systemdUnit"]
                or not isinstance(abort["errorType"], str) or not abort["errorType"]
                or not isinstance(abort["error"], str) or not abort["error"]
                or abort["promotionAuthorized"] is not False
            ):
                raise GateError("retained campaign abort identity differs")
            _timestamp(abort["completedAt"], "campaign abort completedAt")
            return {
                "schemaVersion": 1,
                "kind": "otel-demo-candidate-fetch-receipt-v1",
                "campaignId": binding["campaignId"],
                "state": "retained-abort",
                "transport": receipt,
                "campaignAbortSha256": file_sha256(remote_abort),
                "terminalValidationSha256": None,
                "promotionAuthorized": False,
            }
        if not remote_terminal.is_file():
            return {"schemaVersion": 1, "kind": "otel-demo-candidate-fetch-receipt-v1", "campaignId": binding["campaignId"], "state": "partial-retained", "transport": receipt, "terminalValidationSha256": None, "promotionAuthorized": False}
        terminal_path = ROOT / CONTROLLER_PATHS["candidate-terminal"]
        spec = importlib.util.spec_from_file_location(
            "otel_candidate_runtime_terminal", terminal_path
        )
        if spec is None or spec.loader is None:
            raise GateError("candidate terminal validator cannot be loaded")
        terminal = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = terminal
        spec.loader.exec_module(terminal)
        report = terminal.validate_campaign(
            package.bindings.root, retained, package
        )
        (staging / "terminal-validation.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if report["verdict"] != "pass":
            raise GateError(f"retained {RUN_COUNT}-cell campaign failed terminal validation")
        return {"schemaVersion": 1, "kind": "otel-demo-candidate-fetch-receipt-v1", "campaignId": binding["campaignId"], "state": "terminal-valid", "transport": receipt, "terminalValidationSha256": file_sha256(staging / "terminal-validation.json"), "promotionAuthorized": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup")
    setup.add_argument("campaign_root", type=Path)
    setup.add_argument("--gate-plan", type=Path, required=True)
    setup.add_argument("--gate-setup", type=Path, required=True)
    setup.add_argument("--repository-bundle", type=Path, required=True)
    setup.add_argument("--upstream-bundle", type=Path, required=True)
    setup.add_argument("--staging", type=Path, required=True)
    capture = sub.add_parser("capture-readiness")
    capture.add_argument("campaign_root", type=Path)
    capture.add_argument("--gate-plan", type=Path, required=True)
    capture.add_argument("--gate-setup", type=Path, required=True)
    capture.add_argument("--setup-receipt", type=Path, required=True)
    capture.add_argument("--staging", type=Path, required=True)
    target_readiness = sub.add_parser("target-readiness")
    target_readiness.add_argument("--gate-plan", type=Path, required=True)
    target_readiness.add_argument("--gate-setup", type=Path, required=True)
    target_readiness.add_argument("--setup-receipt", type=Path, required=True)
    target_readiness.add_argument("--output", type=Path, required=True)
    for name in ("validate", "launch", "status", "fetch"):
        command_parser = sub.add_parser(name)
        command_parser.add_argument("campaign_root", type=Path)
        command_parser.add_argument("--gate-plan", type=Path, required=True)
        command_parser.add_argument("--gate-setup", type=Path, required=True)
        command_parser.add_argument("--setup-receipt", type=Path, required=True)
        command_parser.add_argument("--readiness", type=Path, required=True)
        command_parser.add_argument("--gate-run", type=Path, required=True)
        if name in {"launch", "fetch"}:
            command_parser.add_argument("--staging", type=Path, required=True)
    args = parser.parse_args(argv)
    refuse_unsupported(f"candidate runtime command {args.command}")
    if args.command == "target-readiness":
        plan = _json_file(args.gate_plan, "target GATE-PLAN")
        readiness = produce_target_readiness(
            plan,
            _json_file(args.gate_setup, "target GATE-SETUP"),
            _json_file(args.setup_receipt, "target setup receipt"),
        )
        expected_output = Path(plan["binding"]["remoteArtifactRoot"]) / ".controller/readiness.json"
        if args.output != expected_output:
            raise GateError("target readiness output path differs from the bound controller path")
        write_target_readiness(args.output, readiness)
        print(json.dumps({
            "runtimeReadinessSha256": canonical_sha256(readiness),
            "readinessObservedAt": readiness["readinessObservedAt"],
            "cellsRun": 0,
            "promotionAuthorized": False,
        }, indent=2, sort_keys=True))
        return 0
    adapter = ComposeSshAdapter()
    if args.command == "setup":
        setup_package = authorize_setup_from_files(
            args.campaign_root, args.gate_plan, args.gate_setup
        )
        print(json.dumps(adapter.setup(
            setup_package, args.repository_bundle, args.upstream_bundle, args.staging
        ), indent=2, sort_keys=True))
        return 0
    if args.command == "capture-readiness":
        request = authorize_readiness_from_files(
            args.campaign_root, args.gate_plan, args.gate_setup,
            args.setup_receipt,
        )
        print(json.dumps(
            adapter.capture_readiness(request, args.staging),
            indent=2, sort_keys=True,
        ))
        return 0
    package_loader = (
        replay_runtime_from_files
        if args.command in {"status", "fetch"}
        else authorize_from_files
    )
    package = package_loader(
        args.campaign_root, args.gate_plan, args.gate_setup, args.setup_receipt,
        args.readiness, args.gate_run,
    )
    if args.command == "validate":
        print(json.dumps({"status": "authorized", "runCount": RUN_COUNT, "promotionAuthorized": False}, sort_keys=True))
        return 0
    if args.command == "launch":
        result = adapter.launch(package, args.staging)
    elif args.command == "status":
        result = adapter.status(package)
    else:
        result = adapter.fetch(package, args.staging)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHANGE_ID", "READINESS_SEAMS", "TARGET_OBSERVATION_SEAMS",
    "HARNESS_REPLAY_SEAMS", "GateError", "PlanBindings",
    "RuntimePackage", "SetupPackage", "ReadinessRequest", "ComposeSshAdapter",
    "authorize_from_files", "authorize_readiness_from_files", "authorize_setup_from_files",
    "replay_runtime_from_files",
    "build_cell_contract", "canonical_sha256", "execution_package",
    "expected_gate_plan_text", "expected_gate_setup_text", "expected_gate_run_text", "inspect_compiled_plan",
    "harness_contract_observations", "make_readiness", "operational_binding",
    "planted_observation", "produce_target_readiness", "target_observations",
    "EXPECTED_RECOMMENDATION_ENTRYPOINT_TEXT", "EXPECTED_ENTRYPOINT_GUARDS",
    "EXPECTED_GUARD_LAUNCHES", "EXPECTED_AGENT_ENVIRONMENT", "EXPECTED_FLAGD_ENVIRONMENT",
    "recommendation_entrypoint_command",
    "rendered_recommendation_entrypoint_command",
    "resolve_recommendation_entrypoint_program", "resolve_entrypoint_launch",
    "prove_entrypoint_guard", "prove_materialized_source_guards",
    "prove_recommendation_source_instrumentation_posture",
    "prove_materialized_recommendation_entrypoint",
    "verify_recommendation_source_instrumentation_posture",
    "verify_overlay_posture_controls", "verify_materializer_constants",
    "overlay_service_entrypoints", "descriptor_posture_statuses", "unsupported_postures",
    "expected_service_control", "expected_load_states", "posture_config_document",
    "posture_config_sha256", "posture_config_sha256_for_binding",
    "posture_environment", "run_binding", "setup_binding", "setup_execution_package",
    "validate_consumed_gate_setup", "validate_gate_plan", "validate_gate_setup",
    "validate_gate_setup_reference", "validate_setup_receipt",
    "validate_gate_run", "validate_gate_run_reference", "validate_readiness",
    "validate_readiness_reference", "validate_seam", "refuse_unsupported",
    "unsupported_evidence", "validate_unsupported_evidence",
    "STUDY_EPOCH", "UNSUPPORTED_CHANGE_ID", "UNSUPPORTED_STUDY_EPOCH", "UNSUPPORTED_LEDGER_SCOPE",
    "admitted_study_epochs", "frozen_descriptor", "verify_descriptor_bindings",
]
