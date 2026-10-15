import importlib.util
import subprocess
from pathlib import Path

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

    assert "require('./InstrumentationEnabled.js')" in node
    assert node.index("OTEL_PLACEMENT_ENABLED") < node.index("InstrumentationEnabled")
    assert "import('./FrontendTracerEnabled')" in browser
    assert "OTEL_PLACEMENT_ENABLED" in recommendation
    assert "logger_provider = LoggerProvider" in recommendation
    assert "                tracing:\n" not in no_trace
    assert "InstrumentationEnabled.js ./" in frontend_dockerfile
    assert "COPY .source.sha256 /obsplacement-source.sha256" in frontend_dockerfile
    assert "COPY .source.sha256 /obsplacement-source.sha256" in recommendation_dockerfile
    assert "container_name:" not in isolated_compose
    assert "name: opentelemetry-demo" not in isolated_compose
    assert (output / ".source.sha256").read_text().strip() == materialize.sha256(output)


def test_compose_mounts_the_template_read_by_envoy_entrypoint():
    overlay = (ROOT / "modules/otel-demo/deployment/compose.otel-placement.yml").read_text()
    assert ":/home/envoy/envoy.tmpl.yaml:ro" in overlay
    assert "LOCUST_AUTOSTART: \"false\"" in overlay
    assert overlay.count("obsplacement/otel-demo:${OTEL_IMAGE_TAG:") == 3


def test_otel_module_extension_ledger_is_complete():
    result = audit(ROOT / "modules/otel-demo")
    assert result["verdict"] == "pass", result
    assert result["classified_files"] == 7
