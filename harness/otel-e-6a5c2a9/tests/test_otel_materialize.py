import importlib.util
import subprocess
from pathlib import Path

import pytest

from obsplacement.module_audit import audit


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo/materialize.py"
SPEC = importlib.util.spec_from_file_location("otel_materialize", MODULE)
materialize = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(materialize)


def test_materialized_guards_do_not_load_enabled_implementations_when_disabled(tmp_path):
    output = tmp_path / "otel"
    subprocess.run(["python3", str(MODULE), "--out", str(output)], check=True)

    node = (output / "src/frontend/utils/telemetry/Instrumentation.js").read_text()
    browser = (output / "src/frontend/utils/telemetry/FrontendTracer.ts").read_text()
    recommendation = (output / "src/recommendationservice/recommendation_server.py").read_text()
    frontend_dockerfile = (output / "src/frontend/Dockerfile").read_text()
    recommendation_dockerfile = (output / "src/recommendationservice/Dockerfile").read_text()
    isolated_compose = (output / "docker-compose.obsplacement.yml").read_text()
    no_trace = (output / "src/frontendproxy/envoy.no-tracing.tmpl.yaml").read_text()
    traced = (output / "src/frontendproxy/envoy.tmpl.yaml").read_text()
    collector = (output / "src/otelcollector/otelcol-placement.yml").read_text()

    assert "require('./InstrumentationEnabled.js')" in node
    assert node.index("OTEL_PLACEMENT_ENABLED") < node.index("InstrumentationEnabled")
    assert "import('./FrontendTracerEnabled')" in browser
    assert "OTEL_PLACEMENT_ENABLED" in recommendation
    assert "logger_provider = LoggerProvider" in recommendation
    assert "                tracing:\n" not in no_trace
    assert "obsplacement_kind: application-request-witness" in traced
    assert "obsplacement_kind: application-request-witness" in no_trace
    assert 'request_token: "%REQ(X-OBSPLACEMENT-REQUEST-TOKEN)%"' in traced
    assert "verbosity: detailed" in collector
    assert "InstrumentationEnabled.js ./" in frontend_dockerfile
    assert "COPY .source.sha256 /obsplacement-source.sha256" in frontend_dockerfile
    assert "COPY .source.sha256 /obsplacement-source.sha256" in recommendation_dockerfile
    assert 'ENTRYPOINT [ "opentelemetry-instrument", "python", "recommendation_server.py" ]' not in (
        recommendation_dockerfile
    )
    assert (
        'ENTRYPOINT if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec python '
        "recommendation_server.py; else exec opentelemetry-instrument python "
        "recommendation_server.py; fi"
    ) in recommendation_dockerfile
    assert "container_name:" not in isolated_compose
    assert "name: opentelemetry-demo" not in isolated_compose
    assert "- 10000:10000" not in isolated_compose
    assert '${FRONTEND_PROXY_OTLP_HOST_PORT}:10000' in isolated_compose
    assert '${JAEGER_HOST_PORT}:${JAEGER_SERVICE_PORT}' in isolated_compose
    assert '${GRAFANA_HOST_PORT}:${GRAFANA_SERVICE_PORT}' in isolated_compose
    assert '${PROMETHEUS_HOST_PORT}:${PROMETHEUS_SERVICE_PORT}' in isolated_compose
    assert (output / ".source.sha256").read_text().strip() == materialize.sha256(output)
    assert (output / "candidate-posture-contract.json").is_file()
    assert (output / "compose.candidate-postures.yml").is_file()
    # imageprovider: the disabled template is derived from the upstream one and is
    # otel-free; the upstream one still loads the module unconditionally.
    nginx = (output / "src/imageprovider/nginx.conf.template").read_text()
    nginx_off = (output / "src/imageprovider/nginx.no-otel.conf.template").read_text()
    assert "load_module modules/ngx_otel_module.so;" in nginx and "otel_trace on;" in nginx
    assert "otel" not in nginx_off and "listen ${IMAGE_PROVIDER_PORT};" in nginx_off
    assert nginx_off.count("\n") < nginx.count("\n")
    # The upstream launches the compose-overlay guards mirror are unchanged.
    assert 'ENTRYPOINT ["./instrument.sh", "dotnet", "AccountingService.dll"]' in (
        output / "src/accountingservice/Dockerfile"
    ).read_text()
    assert '"start": "node --require ./opentelemetry.js index.js"' in (
        output / "src/paymentservice/package.json"
    ).read_text()
    for service, (variable, value) in materialize.AGENT_ENVIRONMENT.items():
        assert materialize.upstream_agent_environment(
            (output / "src" / service / "Dockerfile").read_text(), service
        ) == value, (service, variable)

    planted = isolated_compose.replace(
        "${FRONTEND_PROXY_OTLP_HOST_PORT}:10000", "10000:10000", 1
    )
    with pytest.raises(RuntimeError, match="host port"):
        materialize.validate_candidate_port_bindings(planted)


def test_apply_recommendation_entrypoint_guard_is_posture_conditional():
    unconditional = 'ENTRYPOINT [ "opentelemetry-instrument", "python", "recommendation_server.py" ]\n'
    guarded = materialize.apply_recommendation_entrypoint_guard(f"FROM base\n{unconditional}")
    assert unconditional not in guarded
    assert (
        'ENTRYPOINT if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec python '
        "recommendation_server.py; else exec opentelemetry-instrument python "
        "recommendation_server.py; fi\n"
    ) in guarded


def test_apply_recommendation_entrypoint_guard_fails_closed_if_anchor_missing():
    with pytest.raises(RuntimeError, match="entrypoint"):
        materialize.apply_recommendation_entrypoint_guard("FROM base\n# no entrypoint here\n")


def test_disabled_nginx_template_render_fails_closed_on_upstream_drift():
    upstream = (ROOT / "upstream/opentelemetry-demo/src/imageprovider/nginx.conf.template").read_text()
    rendered = materialize.render_imageprovider_no_otel_template(upstream)
    assert "otel" not in rendered and "load_module" not in rendered
    assert "resolver 127.0.0.11;" in rendered
    with pytest.raises(RuntimeError, match="load_module"):
        materialize.render_imageprovider_no_otel_template(upstream.replace("load_module", "load_modul"))
    # An otel directive added upstream that this renderer does not know fails closed.
    with pytest.raises(RuntimeError, match="still references otel"):
        materialize.render_imageprovider_no_otel_template(upstream.replace("    sendfile on;\n", "    sendfile on;\n    otel_span_attr x y;\n"))


def test_upstream_agent_environment_is_exact_and_unquoted():
    assert materialize.upstream_agent_environment(
        'FROM x\nENV KAFKA_OPTS="-javaagent:/tmp/opentelemetry-javaagent.jar -Dotel.jmx.target.system=kafka-broker"\n', "kafka"
    ) == "-javaagent:/tmp/opentelemetry-javaagent.jar -Dotel.jmx.target.system=kafka-broker"
    with pytest.raises(RuntimeError, match="differs"):
        materialize.upstream_agent_environment("FROM x\nENV JAVA_TOOL_OPTIONS=-javaagent:/other.jar\n", "adservice")
    with pytest.raises(RuntimeError, match="exactly one"):
        materialize.upstream_agent_environment("FROM x\n", "adservice")
    with pytest.raises(RuntimeError, match=".env"):
        materialize.verify_upstream_env_pins("OTEL_COLLECTOR_HOST=elsewhere\nOTEL_COLLECTOR_PORT_GRPC=4317\n")
    with pytest.raises(RuntimeError, match="start script"):
        materialize.verify_payment_start_script('{"scripts": {"start": "npm run something"}}')
    with pytest.raises(RuntimeError, match="ENTRYPOINT"):
        materialize.verify_upstream_entrypoint('ENTRYPOINT ["dotnet", "AccountingService.dll"]\n', "accountingservice")


def test_compose_mounts_the_template_read_by_envoy_entrypoint():
    overlay = (ROOT / "modules/otel-demo/deployment/compose.otel-placement.yml").read_text()
    assert ":/home/envoy/envoy.tmpl.yaml:ro" in overlay
    assert "LOCUST_AUTOSTART: \"false\"" in overlay
    assert overlay.count("obsplacement/otel-demo:${OTEL_IMAGE_TAG:") == 3


def test_otel_module_extension_ledger_is_complete():
    result = audit(ROOT / "modules/otel-demo")
    assert result["verdict"] == "pass", result
    # 17 module files, plus the eight gate-chain files added 2026-09-12: the
    # three shims under execution/ (deployment-overlay) and the five drivers
    # (governance-driver). The count is pinned so a new file cannot enter the
    # module without a ledger entry naming what it is. 2026-10-03: +2, the
    # traffic-sweep compiler (execution/candidate_sweep.py) and the vendored
    # shared gates (validation/protocol_gates.py), both classified as validator;
    # +1 more once the activation commits execution/study-epoch.json.
    # 2026-10-04: +1, the quiet calibration compiler (execution/candidate_quiet.py), validator.
    # 2026-10-09: +1, the repeat-episodes compiler (execution/candidate_repeat.py), validator.
    # 2026-10-11: +1, campaign C's compiler (execution/candidate_repeat_c.py), validator.
    # 2026-10-12: +1, the load pilot's compiler (execution/candidate_load_pilot.py), validator.
    # 2026-10-13: +1, the off-path pilot's compiler (execution/candidate_offpath_pilot.py), validator.
    # 2026-10-12: +1, the second off-path pilot's compiler (execution/candidate_offpath_pilot_v2.py), validator.
    # 2026-10-12: +1, campaign E's compiler (execution/candidate_offpath_e.py), validator.
    selector = ROOT / "modules/otel-demo/execution/study-epoch.json"
    assert result["classified_files"] == 34 + selector.exists()
    assert result["lines_by_class"]["governance-driver"] > 0
