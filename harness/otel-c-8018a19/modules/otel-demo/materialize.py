#!/usr/bin/env python3
"""Materialize a pinned OTel checkout with the experiment's source guards."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, stat, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "upstream" / "opentelemetry-demo"
DEFAULT_OUT = ROOT / ".local/otel-demo"
# 2026-10-09 (protocol decision 66, campaign B): the repeat-episodes epoch's collector config turns the collector's own log
# sampler off (service::telemetry::logs::sampling::enabled, a key of collector 0.108.0's service/telemetry LogsSamplingConfig),
# because the zap sampler dropped an exported batch's debug-exporter record in the quiet run (research/traffic-sweep/
# OTEL_LOST_BATCH_DIAGNOSIS.md).  The epoch is read from the committed selector of the tree this file runs in, so the local
# projection of the materialized-source digest and the target's install agree; every other epoch (and no selector) renders
# the collector config byte for byte as before.
EPOCH_SELECTOR = ROOT / "modules/otel-demo/execution/study-epoch.json"
# 2026-10-11: campaign C (otel-repeat-episodes-c-v1, decision 82) is B's shape exactly, collector log sampler off included.
COLLECTOR_LOG_SAMPLING_OFF_EPOCHS = ("otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1")
COLLECTOR_LOG_SAMPLING_OFF = "service:\n  telemetry:\n    logs:\n      sampling:\n        enabled: false\n  pipelines:\n"


def selected_study_epoch(selector: Path = EPOCH_SELECTOR):
    """The study epoch the committed selector names, or None when the tree has none (the frozen epoch)."""
    if not selector.is_file():
        return None
    return json.loads(selector.read_text(encoding="utf-8")).get("studyEpoch")
REQUIRED_HOST_PORT_BINDINGS = (
    '${FRONTEND_PROXY_OTLP_HOST_PORT}:10000',
    '${JAEGER_HOST_PORT}:${JAEGER_SERVICE_PORT}',
    '${GRAFANA_HOST_PORT}:${GRAFANA_SERVICE_PORT}',
    '${PROMETHEUS_HOST_PORT}:${PROMETHEUS_SERVICE_PORT}',
)

# Posture-conditional entrypoints, one shell statement per service, keyed by the
# service whose upstream entrypoint loads an instrumentation agent unconditionally.
# ``recommendationservice`` is rendered into its Dockerfile (the image is built
# locally); ``accountingservice`` and ``paymentservice`` run the upstream ghcr
# image and are overridden through compose.candidate-postures.yml ``entrypoint``.
# Every enabled branch is the exact upstream launch (verified against the pinned
# checkout in ``main``), so the only difference between postures is the agent.
ENTRYPOINT_GUARDS = {
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
# The exact upstream launch each enabled branch must reproduce.
UPSTREAM_ENTRYPOINTS = {
    "recommendationservice": 'ENTRYPOINT [ "opentelemetry-instrument", "python", "recommendation_server.py" ]',
    "accountingservice": 'ENTRYPOINT ["./instrument.sh", "dotnet", "AccountingService.dll"]',
    "paymentservice": 'ENTRYPOINT [ "npm", "run", "start" ]',
}
UPSTREAM_PAYMENT_START_SCRIPT = "node --require ./opentelemetry.js index.js"
# JVM agents that upstream bakes into an image ENV. The compose overlay rebinds
# the variable per posture: the upstream value when enabled, the empty string
# when disabled, so a disabled JVM never receives ``-javaagent`` at all
# (``otel.javaagent.enabled=false`` would still load the agent jar and create
# its class loaders -- see opentelemetry-java-instrumentation
# AgentInstaller.installBytebuddyAgent -- so it is not used).
AGENT_ENVIRONMENT = {
    "adservice": ("JAVA_TOOL_OPTIONS", "-javaagent:/usr/src/app/opentelemetry-javaagent.jar"),
    "frauddetectionservice": ("JAVA_TOOL_OPTIONS", "-javaagent:/app/opentelemetry-javaagent.jar"),
    "kafka": (
        "KAFKA_OPTS",
        "-javaagent:/tmp/opentelemetry-javaagent.jar -Dotel.jmx.target.system=kafka-broker",
    ),
}
# flagd (prebuilt ghcr image) is configured by two start-up variables, not by
# the OTel SDK environment: an empty collector URI skips its trace provider and
# connect interceptor, an empty metrics exporter selects the pull-only
# Prometheus reader, and any exporter value other than ``otel`` is an error.
UPSTREAM_ENV_PINS = {"OTEL_COLLECTOR_HOST": "otelcol", "OTEL_COLLECTOR_PORT_GRPC": "4317"}
FLAGD_ENABLED_ENVIRONMENT = {
    "FLAGD_OTEL_COLLECTOR_URI": "otelcol:4317",
    "FLAGD_METRICS_EXPORTER": "otel",
}
FLAGD_DISABLED_ENVIRONMENT = {"FLAGD_OTEL_COLLECTOR_URI": "", "FLAGD_METRICS_EXPORTER": ""}
NGINX_OTEL_DIRECTIVES = (
    "load_module modules/ngx_otel_module.so;\n\n",
    "    otel_exporter {\n        endpoint ${OTEL_COLLECTOR_HOST}:${OTEL_COLLECTOR_PORT_GRPC};\n    }\n",
    "    otel_trace on;\n",
    "    otel_trace_context propagate;\n",
    "    otel_service_name ${OTEL_SERVICE_NAME};\n",
    "    otel_span_name imageprovider;\n",
)
# Services whose OTel SDK pipeline is constructed directly in application code
# (in-code-sdk in postures/catalog.json) with no wrapper process or attached
# agent to gate at the entrypoint or via ENV -- so, unlike ENTRYPOINT_GUARDS and
# AGENT_ENVIRONMENT above, the guard patches the exact call site that builds the
# exporter/provider. Each value is the exact upstream text the guard replaces
# (``replace_once`` fails closed if the pinned checkout no longer contains it
# unconditionally) paired with the posture-conditional replacement; the enabled
# branch reproduces the exact upstream call graph the disabled branch skips, so
# only the guard is new, nothing upstream builds is removed.
SOURCE_PLACEMENT_GUARD_FILES = {
    "cartservice": "src/cartservice/src/Program.cs",
    "checkoutservice": "src/checkoutservice/main.go",
    "currencyservice": "src/currencyservice/src/server.cpp",
    "productcatalogservice": "src/productcatalogservice/main.go",
    "shippingservice": "src/shippingservice/src/main.rs",
}
SOURCE_PLACEMENT_GUARDS = {
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


def apply_source_placement_guards(text: str, service: str) -> str:
    """Gate ``service``'s in-code OTel SDK construction behind OTEL_PLACEMENT_ENABLED.

    Text-only: unlike the executed proof for ENTRYPOINT_GUARDS
    (``resolve_entrypoint_launch`` runs the real shell statement), these guards
    are a conditional inside a compiled language this repo cannot build or run
    without a container image build, so the fail-closed check available here is
    that the pinned upstream anchor is present exactly once (``replace_once``)
    and the rendered text contains the guard. Whether the patched source still
    compiles is proven only when a local image is actually built.
    """
    for anchor, replacement in SOURCE_PLACEMENT_GUARDS[service]:
        text = replace_once(text, anchor, replacement, f"{service} source placement guard")
    return text


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one {label} anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def verify_upstream_entrypoint(text: str, service: str) -> None:
    """Fail closed unless the pinned upstream launch is the one the guard mirrors."""
    lines = [line for line in text.splitlines() if line.startswith("ENTRYPOINT")]
    if lines != [UPSTREAM_ENTRYPOINTS[service]]:
        raise RuntimeError(f"upstream {service} ENTRYPOINT differs from the guarded launch: {lines}")


def verify_payment_start_script(package_json_text: str) -> None:
    document = json.loads(package_json_text)
    start = document.get("scripts", {}).get("start")
    if start != UPSTREAM_PAYMENT_START_SCRIPT:
        raise RuntimeError(f"upstream paymentservice start script differs: {start!r}")


def upstream_agent_environment(dockerfile_text: str, service: str) -> str:
    """Return the exact agent value upstream bakes into ``ENV`` for ``service``."""
    variable, expected = AGENT_ENVIRONMENT[service]
    matches = re.findall(rf"(?m)^ENV {re.escape(variable)}=(.*)$", dockerfile_text)
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one ENV {variable} in the {service} Dockerfile, found {len(matches)}")
    value = matches[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if value != expected:
        raise RuntimeError(f"upstream {service} {variable} differs from the pinned agent value: {value!r}")
    return value


def verify_upstream_env_pins(env_text: str) -> None:
    for key, expected in UPSTREAM_ENV_PINS.items():
        matches = re.findall(rf"(?m)^{re.escape(key)}=(.*)$", env_text)
        if matches != [expected]:
            raise RuntimeError(f"upstream .env {key} differs from the flagd collector pin: {matches}")


def render_imageprovider_no_otel_template(text: str) -> str:
    """Derive the disabled nginx template from the upstream one.

    Upstream hardcodes ``load_module modules/ngx_otel_module.so`` and
    ``otel_trace on`` and only env-substitutes the collector endpoint, so no
    environment variable can disable the module; posture has zero effect on
    imageprovider unless the template itself changes. Removing every otel
    directive from the *same* source text keeps the two templates identical
    otherwise (one render source, nested lattice).
    """
    for directive in NGINX_OTEL_DIRECTIVES:
        text = replace_once(text, directive, "", f"imageprovider nginx {directive.strip().split()[0]}")
    if "otel" in text:
        raise RuntimeError("imageprovider disabled template still references otel")
    return text


def apply_recommendation_entrypoint_guard(text: str) -> str:
    """Make the recommendationservice OTel entrypoint posture-conditional.

    Upstream bakes ``ENTRYPOINT [ "opentelemetry-instrument", "python",
    "recommendation_server.py" ]`` unconditionally, so ``OTEL_SDK_DISABLED=true``
    only suppresses export -- ``opentelemetry-instrument`` still runs
    ``_load_instrumentors()`` at process start (monkey-patching every installed
    instrumentor) before any SDK-disabled check is consulted; that check only
    makes ``TracerProvider.get_tracer()`` return a no-op tracer afterwards. A
    "disabled" recommendationservice under the unconditional wrapper therefore
    still pays the auto-instrumentation agent's load/monkey-patch/interception
    cost and is not a true zero baseline.

    This guard reuses the existing ``OTEL_PLACEMENT_ENABLED`` variable (already
    plumbed per-posture through compose.candidate-postures.yml and already used
    by this file's frontend Instrumentation.js guard and the recommendation
    manual-logging guard below) to choose between the plain interpreter and the
    auto-instrumentation wrapper at container start, so a disabled posture never
    imports/loads the instrumentation agent at all.
    """
    anchor = UPSTREAM_ENTRYPOINTS["recommendationservice"] + "\n"
    replacement = "ENTRYPOINT " + ENTRYPOINT_GUARDS["recommendationservice"] + "\n"
    return replace_once(text, anchor, replacement, "recommendation posture-conditional entrypoint")


def validate_candidate_port_bindings(text: str) -> None:
    if "- 10000:10000" in text or any(
        text.count(binding) != 1 for binding in REQUIRED_HOST_PORT_BINDINGS
    ):
        raise RuntimeError(
            "candidate Compose does not bind every experiment host port exactly once"
        )

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file() and ".git" not in p.parts and p.name != ".source.sha256":
            relative = str(p.relative_to(path)).encode()
            payload = p.read_bytes()
            h.update(len(relative).to_bytes(8, "big")); h.update(relative)
            h.update(stat.S_IMODE(p.stat().st_mode).to_bytes(4, "big"))
            h.update(len(payload).to_bytes(8, "big")); h.update(payload)
    return h.hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(); out = args.out.resolve()
    if out in {Path("/"), Path.home(), ROOT, UPSTREAM} or out in ROOT.parents:
        raise RuntimeError(f"refusing unsafe materialization target: {out}")
    expected = next(line.split(":", 1)[1].strip() for line in
                    (ROOT / "modules/otel-demo/source.lock").read_text().splitlines()
                    if line.startswith("commit:"))
    actual = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise RuntimeError(f"pinned checkout mismatch: expected {expected}, found {actual}")
    dirty = subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "status", "--porcelain"], text=True
    ).strip()
    if dirty:
        raise RuntimeError(f"pinned OTel checkout is dirty:\n{dirty}")
    if out.exists():
        if not (out / ".obsplacement-materialized").is_file():
            raise RuntimeError(f"refusing to replace non-materialized directory: {out}")
        shutil.rmtree(out)
    shutil.copytree(UPSTREAM, out, ignore=shutil.ignore_patterns(".git", "._*", ".DS_Store"))
    upstream_compose = out / "docker-compose.yml"
    compose_text = upstream_compose.read_text(encoding="utf-8")
    compose_text, removed_names = re.subn(r"(?m)^    container_name:.*\n", "", compose_text)
    if removed_names < 10:
        raise RuntimeError(f"expected upstream global container names, found {removed_names}")
    compose_text = replace_once(
        compose_text, "    name: opentelemetry-demo\n", "",
        "global default-network name",
    )
    # Keep container ports at the upstream values while binding every published
    # experiment endpoint to a reviewed host port.  In particular, changing
    # GRAFANA_SERVICE_PORT or PROMETHEUS_SERVICE_PORT changes the container-side
    # contract and can produce a deceptively healthy container with a dead
    # published socket.
    compose_text = replace_once(
        compose_text,
        "      - 10000:10000\n",
        '      - "${FRONTEND_PROXY_OTLP_HOST_PORT}:10000"\n',
        "frontendproxy OTLP host port",
    )
    compose_text = replace_once(
        compose_text,
        '      - "${JAEGER_SERVICE_PORT}"         # Jaeger UI\n',
        '      - "${JAEGER_HOST_PORT}:${JAEGER_SERVICE_PORT}" # Jaeger UI\n',
        "Jaeger UI host port",
    )
    compose_text = replace_once(
        compose_text,
        '      - "${GRAFANA_SERVICE_PORT}"\n',
        '      - "${GRAFANA_HOST_PORT}:${GRAFANA_SERVICE_PORT}"\n',
        "Grafana host port",
    )
    compose_text = replace_once(
        compose_text,
        '      - "${PROMETHEUS_SERVICE_PORT}:${PROMETHEUS_SERVICE_PORT}"\n',
        '      - "${PROMETHEUS_HOST_PORT}:${PROMETHEUS_SERVICE_PORT}"\n',
        "Prometheus host port",
    )
    validate_candidate_port_bindings(compose_text)
    (out / "docker-compose.obsplacement.yml").write_text(compose_text, encoding="utf-8")
    # Apply the small, auditable source guards without mutating the pinned
    # submodule. Fail closed if upstream changes invalidate the expected text.
    node = out / "src/frontend/utils/telemetry/Instrumentation.js"
    node_enabled = node.with_name("InstrumentationEnabled.js")
    node_enabled.write_text(node.read_text(encoding="utf-8"), encoding="utf-8")
    node.write_text("""// Generated placement guard. Disabled means the OTel implementation is not imported.
if (process.env.OTEL_PLACEMENT_ENABLED === 'false' || process.env.OTEL_SDK_DISABLED === 'true') {
  module.exports = {};
} else {
  module.exports = require('./InstrumentationEnabled.js');
}
""", encoding="utf-8")
    frontend_dockerfile = out / "src/frontend/Dockerfile"
    text = frontend_dockerfile.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "COPY --from=builder /app/utils/telemetry/Instrumentation.js ./",
        "COPY --from=builder /app/utils/telemetry/Instrumentation.js ./\n"
        "COPY --from=builder /app/utils/telemetry/InstrumentationEnabled.js ./\n"
        "COPY .source.sha256 /obsplacement-source.sha256",
        "frontend runtime instrumentation",
    )
    frontend_dockerfile.write_text(text, encoding="utf-8")
    browser = out / "src/frontend/utils/telemetry/FrontendTracer.ts"
    browser_enabled = browser.with_name("FrontendTracerEnabled.ts")
    browser_enabled.write_text(browser.read_text(encoding="utf-8"), encoding="utf-8")
    browser.write_text("""// Generated placement guard. Disabled browsers do not load the OTel chunk.
const FrontendTracer = (collectorString: string) => {
  if (typeof window !== 'undefined' && (window as any).ENV?.OTEL_PLACEMENT_ENABLED === 'false') return;
  void import('./FrontendTracerEnabled').then(module => module.default(collectorString));
};
export default FrontendTracer;
""", encoding="utf-8")
    document = out / "src/frontend/pages/_document.tsx"
    text = document.read_text(encoding="utf-8")
    text = replace_once(text, "const { ENV_PLATFORM, WEB_OTEL_SERVICE_NAME, PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, OTEL_COLLECTOR_HOST} = process.env;", "const { ENV_PLATFORM, WEB_OTEL_SERVICE_NAME, PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, OTEL_COLLECTOR_HOST, OTEL_PLACEMENT_ENABLED} = process.env;", "frontend document environment")
    text = replace_once(text, "NEXT_PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: '${otlpTracesEndpoint}',", "NEXT_PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: '${otlpTracesEndpoint}',\n          OTEL_PLACEMENT_ENABLED: '${OTEL_PLACEMENT_ENABLED ?? 'true'}',", "browser placement environment")
    document.write_text(text, encoding="utf-8")
    rec = out / "src/recommendationservice/Dockerfile"
    text = rec.read_text(encoding="utf-8")
    anchor = "RUN python -m pip install grpcio-tools==1.59.2"
    replacement = "RUN python -m pip install setuptools==69.5.1 grpcio-tools==1.59.2"
    if anchor not in text:
        raise RuntimeError("recommendation grpcio-tools anchor missing")
    text = text.replace(anchor, replacement, 1)
    bootstrap = "RUN opentelemetry-bootstrap -a install"
    if bootstrap not in text:
        raise RuntimeError("opentelemetry bootstrap anchor missing")
    text = text.replace(bootstrap, "RUN pip install setuptools==69.5.1 && opentelemetry-bootstrap -a install", 1)
    text = replace_once(
        text,
        "COPY ./src/recommendationservice/ ./",
        "COPY ./src/recommendationservice/ ./\nCOPY .source.sha256 /obsplacement-source.sha256",
        "recommendation runtime provenance",
    )
    text = apply_recommendation_entrypoint_guard(text)
    rec.write_text(text, encoding="utf-8")
    # Services whose OTel SDK is constructed in application code: patch the
    # exact call site in the pinned checkout copy (never upstream in place).
    for service, relative in SOURCE_PLACEMENT_GUARD_FILES.items():
        guarded_path = out / relative
        guarded_path.write_text(
            apply_source_placement_guards(guarded_path.read_text(encoding="utf-8"), service),
            encoding="utf-8",
        )
    # Services that run the upstream ghcr image: the guard lives in the compose
    # overlay, so verify here that the upstream launch it mirrors is unchanged.
    verify_upstream_entrypoint(
        (out / "src/accountingservice/Dockerfile").read_text(encoding="utf-8"), "accountingservice"
    )
    verify_upstream_entrypoint(
        (out / "src/paymentservice/Dockerfile").read_text(encoding="utf-8"), "paymentservice"
    )
    verify_payment_start_script((out / "src/paymentservice/package.json").read_text(encoding="utf-8"))
    for service in AGENT_ENVIRONMENT:
        upstream_agent_environment(
            (out / "src" / service / "Dockerfile").read_text(encoding="utf-8"), service
        )
    verify_upstream_env_pins((out / ".env").read_text(encoding="utf-8"))
    nginx = out / "src/imageprovider/nginx.conf.template"
    (out / "src/imageprovider/nginx.no-otel.conf.template").write_text(
        render_imageprovider_no_otel_template(nginx.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    server = out / "src/recommendationservice/recommendation_server.py"
    text = server.read_text(encoding="utf-8")
    start = "    # Initialize Logs\n    logger_provider = LoggerProvider("
    end = "    logger.addHandler(handler)"
    begin_at, end_at = text.find(start), text.find(end)
    if begin_at < 0 or end_at < begin_at:
        raise RuntimeError("recommendation manual logging anchors missing")
    end_at += len(end)
    replacement = """    # Placement guard: source-off does not construct the OTLP log pipeline.
    logger = logging.getLogger('main')
    if os.environ.get('OTEL_PLACEMENT_ENABLED', 'true').lower() != 'false':
        logger_provider = LoggerProvider(resource=Resource.create({'service.name': service_name}))
        set_logger_provider(logger_provider)
        log_exporter = OTLPLogExporter(insecure=True)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        logger.addHandler(LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider))"""
    text = text[:begin_at] + replacement + text[end_at:]
    server.write_text(text, encoding="utf-8")
    envoy = out / "src/frontendproxy/envoy.tmpl.yaml"
    text = envoy.read_text(encoding="utf-8")
    witness = """                access_log:
                  - name: envoy.access_loggers.stdout
                    typed_config:
                      \"@type\": type.googleapis.com/envoy.extensions.access_loggers.stream.v3.StdoutAccessLog
                      log_format:
                        json_format:
                          obsplacement_kind: application-request-witness
                          request_token: \"%REQ(X-OBSPLACEMENT-REQUEST-TOKEN)%\"
                          traceparent: \"%REQ(TRACEPARENT)%\"
                          response_code: \"%RESPONSE_CODE%\"
                          response_flags: \"%RESPONSE_FLAGS%\"
                          start_time: \"%START_TIME(%s.%3f)%\"
                          duration_ms: \"%DURATION%\"
"""
    text = replace_once(
        text,
        "                http_filters:\n",
        witness + "                http_filters:\n",
        "frontendproxy application witness",
    )
    start, end = text.find("                tracing:\n"), text.find("                route_config:\n")
    if start < 0 or end < start:
        raise RuntimeError("Envoy tracing block anchor missing")
    (out / "src/frontendproxy/envoy.no-tracing.tmpl.yaml").write_text(text[:start] + text[end:], encoding="utf-8")
    envoy.write_text(text, encoding="utf-8")
    proxy_dockerfile = out / "src/frontendproxy/Dockerfile"
    text = proxy_dockerfile.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "COPY ./src/frontendproxy/envoy.tmpl.yaml envoy.tmpl.yaml",
        "COPY ./src/frontendproxy/envoy.tmpl.yaml envoy.tmpl.yaml\n"
        "COPY .source.sha256 /obsplacement-source.sha256",
        "frontendproxy runtime provenance",
    )
    proxy_dockerfile.write_text(text, encoding="utf-8")
    collector = out / "src/otelcollector/otelcol-config.yml"
    ctext = collector.read_text(encoding="utf-8")
    # srv5/srv6 ship Docker API clients older than the daemon. Keep telemetry
    # pipelines alive and measure CPU externally rather than failing the whole
    # collector on the optional docker_stats receiver.
    ctext = replace_once(ctext, "  docker_stats:\n    endpoint: unix:///var/run/docker.sock\n", "", "docker_stats receiver")
    ctext = replace_once(ctext, "hostmetrics, docker_stats, httpcheck/frontendproxy", "hostmetrics, httpcheck/frontendproxy", "docker_stats pipeline")
    ctext = replace_once(
        ctext,
        "  debug:\n",
        "  debug:\n    verbosity: detailed\n",
        "detailed debug exporter",
    )
    if selected_study_epoch() in COLLECTOR_LOG_SAMPLING_OFF_EPOCHS:
        ctext = replace_once(ctext, "service:\n  pipelines:\n", COLLECTOR_LOG_SAMPLING_OFF, "collector log sampling off")
    (out / "src/otelcollector/otelcol-placement.yml").write_text(ctext, encoding="utf-8")
    shutil.copyfile(
        ROOT / "modules/otel-demo/postures/catalog.json",
        out / "candidate-posture-contract.json",
    )
    shutil.copyfile(
        ROOT / "modules/otel-demo/deployment/compose.otel-placement.yml",
        out / "compose.otel-placement.yml",
    )
    shutil.copyfile(
        ROOT / "modules/otel-demo/deployment/compose.candidate-postures.yml",
        out / "compose.candidate-postures.yml",
    )
    (out / ".obsplacement-materialized").write_text(
        json.dumps({"upstreamSha": actual, "removedGlobalContainerNames": removed_names}) + "\n",
        encoding="utf-8",
    )
    (out / ".source.sha256").write_text(sha256(out), encoding="utf-8")
    print(out); print((out / ".source.sha256").read_text().strip())
    return 0
if __name__ == "__main__": raise SystemExit(main())
