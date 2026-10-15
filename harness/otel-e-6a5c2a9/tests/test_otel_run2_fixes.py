"""OTel run-2 fixes at the producer and plan level (terminal plants live in
test_otel_candidate_terminal.py::test_run2_fix_plants).

1a.1 carrier retention and the fail-closed coverage check, 1a.2 the explicit
span-name alias table verified against the pinned Envoy config, 1a.3 the
collector exclusion under ``none`` only, 1a.5 the attempt as a launcher
parameter with attempt 1 spent. Each check is watched failing on the shape run 1
actually produced (offline replay, 2026-09-23).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("otel_run2_runtime_tests", "modules/otel-demo/execution/candidate_runtime.py")
remote = _load("otel_run2_remote_tests", "modules/otel-demo/execution/candidate_remote.py")
pilot = _load("otel_run2_pilot_tests", "modules/otel-demo/execution/candidate_pilot.py")

# Run 1, no-fault-cost/b01-01-full: ledger window 14:56:22.307Z, log head below.
RUN1_WINDOW_START = 1789743382.3071687
RUN1_CARRIER_HEAD = (
    "otelcol-1  | NumberDataPoints #2\n"
    "otelcol-1  | Data point attributes:\n"
    "otelcol-1  |      -> state: Str(wait)\n"
    "otelcol-1  | StartTimestamp: 2025-02-15 17:37:27 +0000 UTC\n"
    "otelcol-1  | Timestamp: 2026-09-18 15:06:12.450767915 +0000 UTC\n"
    "otelcol-1  | Value: 0.000000\n"
)


# --- 1a.1 carrier -----------------------------------------------------------

def test_collector_logging_is_one_unrotated_segment_in_every_posture():
    overlay = yaml.safe_load((ROOT / "modules/otel-demo/deployment/compose.otel-placement.yml").read_text())
    logging = overlay["services"]["otelcol"]["logging"]
    assert logging == {"driver": "json-file", "options": {"max-size": "4g", "max-file": "1"}}
    # Posture parity: the base overlay is shared by none/selected/full and the
    # logging block interpolates nothing a posture could vary.
    assert "${" not in yaml.safe_dump(logging)
    posture_overlay = yaml.safe_load((ROOT / "modules/otel-demo/deployment/compose.candidate-postures.yml").read_text())
    assert "logging" not in posture_overlay["services"].get("otelcol", {})
    # What the override exists to replace: upstream's rotating anchor.
    upstream = (ROOT / "upstream/opentelemetry-demo/docker-compose.yml").read_text()
    assert 'max-size: "5m"' in upstream and 'max-file: "2"' in upstream


def test_carrier_coverage_refuses_run1_and_accepts_a_complete_carrier():
    truncated = remote.collector_carrier_coverage(RUN1_CARRIER_HEAD, RUN1_WINDOW_START)
    assert truncated["coversWindow"] is False
    assert truncated["firstRecordEpoch"] == pytest.approx(RUN1_WINDOW_START + 590.143, abs=0.01)
    with pytest.raises(remote.RuntimeFailure, match="does not cover the measurement window"):
        remote.require_collector_carrier_coverage(RUN1_CARRIER_HEAD, RUN1_WINDOW_START)
    complete = (
        "otelcol-1  | 2026-09-18T14:53:40.100Z\tinfo\tservice@v0.117.0/service.go:\tStarting otelcol-contrib\n"
        "otelcol-1  | Timestamp: 2026-09-18 14:54:01.5 +0000 UTC\n"
    ) + RUN1_CARRIER_HEAD
    assert remote.collector_carrier_coverage(complete, RUN1_WINDOW_START)["coversWindow"] is True
    remote.require_collector_carrier_coverage(complete, RUN1_WINDOW_START)


@pytest.mark.parametrize(
    "log",
    (
        "",
        "otelcol-1  | StartTimestamp: 2025-02-15 17:37:27 +0000 UTC\n",
        "otelcol-1  | Timestamp: 1970-01-01 00:00:00 +0000 UTC\n",
        "otelcol-1  | Timestamp: not-a-time +0000 UTC\n",
        "otelcol-1  | ObservedTimestamp: 2026-09-18 14:00:00 +0000 UTC\n",
    ),
)
def test_carrier_coverage_fails_closed_without_a_real_first_record(log):
    assert remote.collector_carrier_coverage(log, RUN1_WINDOW_START)["coversWindow"] is False


def test_controller_retains_the_carrier_before_refusing_it():
    source = (ROOT / "modules/otel-demo/execution/candidate_remote.py").read_text()
    body = source[source.index("def run_cell("):]
    write_at = body.index('(root / "otelcol.log").write_text(collector')
    check_at = body.index("require_collector_carrier_coverage(collector")
    derived_at = body.index('write_json(root / "trace-correlation.json"')
    assert write_at < check_at < derived_at


# --- 1a.2 alias ---------------------------------------------------------------

def test_alias_table_is_the_pinned_envoy_tracer_name():
    text = (ROOT / "upstream/opentelemetry-demo/src/frontendproxy/envoy.tmpl.yaml").read_text()
    assert runtime.envoy_tracer_service_name(text) == "frontend-proxy"
    assert runtime.span_service_aliases() == {"frontend-proxy": "frontendproxy"} == remote.SPAN_SERVICE_ALIASES
    assert remote.catalog_service("frontend-proxy") == "frontendproxy"
    assert remote.catalog_service("frontend") == "frontend"


@pytest.mark.parametrize(
    "text",
    (
        "tracing:\n  service_name: frontend-proxy\n  service_name: other\n",
        "tracing:\n  provider: {}\n",
        "tracing:\n  service_name: \n",
    ),
)
def test_envoy_tracer_name_refuses_a_config_it_was_not_written_against(text):
    with pytest.raises(runtime.GateError, match="exactly one tracer service_name"):
        runtime.envoy_tracer_service_name(text)


@pytest.mark.parametrize(
    "table",
    ({}, {"frontend_proxy": "frontendproxy"}, {"frontend-proxy": "frontend"},
     {"frontend-proxy": "frontendproxy", "otelcol": "frontend"}),
)
def test_alias_verification_refuses_a_drifted_controller_table(monkeypatch, table):
    stub = types.SimpleNamespace(SPAN_SERVICE_ALIASES=table, COLLECTOR_SELF_SERVICE="otelcol")
    monkeypatch.setattr(runtime, "_controller_module", lambda controller, name: stub)
    with pytest.raises(runtime.GateError, match="alias"):
        runtime.span_service_aliases()


def test_correlation_parser_maps_the_proxy_span_name_onto_the_target_path():
    trace_id = "70793d19455dfbd2b5c836d5e910a7b0"
    log = "".join(
        f"otelcol-1  |      -> service.name: Str({service})\notelcol-1  | Trace ID       : {trace_id}\n"
        for service in ("frontend-proxy", "frontend", "checkoutservice", "frauddetectionservice", "otelcol")
    )
    report = remote.parse_trace_correlation(log, [{"requestToken": "opq-x", "originalTraceId": trace_id}])
    # The path is the synchronous checkout path within the trace; the trace's
    # full service set (async consumers included, collector excluded) is beside it.
    assert report["rows"][0]["observedPathServices"] == ["checkoutservice", "frontend", "frontendproxy"]
    assert report["rows"][0]["observedTraceServices"] == ["checkoutservice", "frauddetectionservice", "frontend", "frontendproxy"]


# --- 1a.3 collector self-telemetry (U3 + the 77002f6 override: every posture) ---

def test_collector_exclusion_is_exactly_one_named_service_in_every_posture():
    source = (ROOT / "modules/otel-demo/execution/candidate_remote.py").read_text()
    assert "    excluded = {COLLECTOR_SELF_SERVICE}\n" in source
    assert remote.COLLECTOR_SELF_SERVICE == "otelcol"
    # The excluded name can never shadow an application service.
    assert remote.COLLECTOR_SELF_SERVICE not in remote.APP_SERVICES
    assert remote.COLLECTOR_SELF_SERVICE not in runtime.posture_catalog()["applicationServices"]


# --- 1a.5 attempt ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    ((None, 1), ("2", 2), ("3", 3), ("17", 17)),
)
def test_campaign_attempt_reads_the_launcher_variable(raw, expected):
    environment = {} if raw is None else {pilot.ATTEMPT_ENVIRONMENT: raw}
    assert pilot.campaign_attempt(environment) == expected


@pytest.mark.parametrize("raw", ("0", "-1", "02", "2.0", "two", "", " 2", "٢"))
def test_campaign_attempt_refuses_a_non_canonical_value(raw):
    with pytest.raises(pilot.ProtocolError):
        pilot.campaign_attempt({pilot.ATTEMPT_ENVIRONMENT: raw})


def test_attempts_give_disjoint_run_ids_under_one_descriptor():
    document = pilot.load_descriptor(pilot.DEFAULT_DESCRIPTOR)
    plans = {attempt: pilot.compile_plan(document, attempt) for attempt in (1, 2, 3)}
    ids = {
        attempt: {cell["runId"] for root in plan["regimeRoots"] for block in root["blocks"] for cell in block["cells"]}
        for attempt, plan in plans.items()
    }
    assert all(len(value) == 36 for value in ids.values())
    assert not ids[1] & ids[2] and not ids[1] & ids[3] and not ids[2] & ids[3]
    assert len({plan["descriptorSha256"] for plan in plans.values()}) == 1
    assert len({pilot.canonical_sha256(plan) for plan in plans.values()}) == 3
    for attempt, plan in plans.items():
        assert pilot.plan_attempt(plan) == attempt
        pilot.validate_plan(document, plan)
    # The admission plan (attempt 1) keeps the digest governance pins.
    assert pilot.compile_plan(document) == plans[1]


def test_a_plan_mixing_attempts_is_refused():
    document = pilot.load_descriptor(pilot.DEFAULT_DESCRIPTOR)
    plan = pilot.compile_plan(document, 2)
    plan["regimeRoots"][0]["blocks"][0]["cells"][0]["runKey"]["attempt"] = 1
    with pytest.raises(pilot.ProtocolError, match="mixes attempts"):
        pilot.plan_attempt(plan)
    with pytest.raises(pilot.ProtocolError):
        pilot.validate_plan(document, plan)


def test_a_plan_directory_from_another_attempt_is_not_silently_reused(tmp_path):
    plan_dir = tmp_path / "plan"
    pilot.materialize(plan_dir, attempt=1)
    with pytest.raises(pilot.ProtocolError, match="differs"):
        pilot.materialize(plan_dir, attempt=2)


def test_driver_path_refuses_the_spent_attempt_and_takes_the_launcher_attempt(monkeypatch, tmp_path):
    adapter = _load("otel_run2_adapter_tests", "modules/otel-demo/execution/candidate_runtime_adapter.py")
    # Spent attempts are per study epoch: v2 spent 1-3 (runs 1-3); v3 has spent none,
    # and its attempt 1 has run IDs no v2 attempt had (the epoch is in every runKey).
    assert set(adapter.SPENT_ATTEMPTS_BY_EPOCH["otel-demo-candidate-pilot-v2"]) == {1, 2, 3}
    assert adapter.SPENT_ATTEMPTS is adapter.SPENT_ATTEMPTS_BY_EPOCH[adapter.STUDY_EPOCH] == {}
    monkeypatch.delenv(pilot.ATTEMPT_ENVIRONMENT, raising=False)
    bindings = adapter.inspect_campaign(tmp_path / "plan-default", "a" * 40)
    assert bindings.plan_bindings.attempt == 1
    # Planted: once v3 attempt 1 is recorded spent, the driver path refuses it.
    monkeypatch.setitem(adapter.SPENT_ATTEMPTS, 1, "planted")
    monkeypatch.setenv(pilot.ATTEMPT_ENVIRONMENT, "1")
    with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
        adapter.inspect_campaign(tmp_path / "plan-one", "a" * 40)
    monkeypatch.setenv(pilot.ATTEMPT_ENVIRONMENT, "2")
    bindings = adapter.inspect_campaign(tmp_path / "plan-two", "a" * 40)
    assert bindings.plan_bindings.attempt == 2


# --- Run-3 fixes (2026-09-24), each watched failing on the shape run 2 actually produced ---

def _carrier(*trace_ids: str) -> str:
    return "".join(
        f"otelcol-1  |      -> service.name: Str(frontend)\notelcol-1  | Trace ID       : {t}\n"
        for t in trace_ids
    )


def test_unique_trace_count_is_request_correlated_not_carrier_wide():
    # Run 2: carrier held background traces besides the 600 request traces; the producer
    # counted all of them (735-737 selected, 1,635-1,699 full) and the validator rejected it.
    requested = [f"{i:032x}" for i in range(1, 4)]
    background = [f"{i:032x}" for i in range(100, 105)]
    requests = [{"requestToken": f"t{i}", "originalTraceId": t} for i, t in enumerate(requested)]
    out = remote.parse_trace_correlation(_carrier(*requested, *background, requested[0]), requests)
    replayed = {r["observedOriginalTraceIds"][0] for r in out["rows"] if r["observedOriginalTraceIds"]}
    assert out["observedUniqueTraceIds"] == len(replayed) == 3


class _Result:
    def __init__(self, rc: int, out: str = "", err: str = ""):
        self.returncode, self.stdout, self.stderr = rc, out, err


PROBE = {"kind": "container-file", "path": "/home/envoy/envoy.tmpl.yaml", "loadedWhenContains": "tracing:\n"}


def _probe(results, monkeypatch):
    calls = iter(results)
    monkeypatch.setattr(remote.time, "sleep", lambda _s: None)
    monkeypatch.setattr(remote, "command", lambda argv, check=False: next(calls))
    return remote.probe_instrumentation_control("cid", {"Config": {}}, PROBE)


def test_container_file_probe_retries_a_transient_failure(monkeypatch):
    # Run 2, frontend-pause-effect/b02-02-selected: one read failed with an empty stderr.
    out = _probe([_Result(1), _Result(0, "  tracing:\n")], monkeypatch)
    assert out["observedControl"] == "enabled"
    assert out["evidence"]["containerFile"]["attempts"] == 2


def test_container_file_probe_is_bounded_and_stays_indeterminate(monkeypatch):
    out = _probe([_Result(1)] * remote.PROBE_EXEC_ATTEMPTS, monkeypatch)
    assert out["observedControl"] == "indeterminate"
    assert out["evidence"]["containerFile"] == {
        "path": PROBE["path"], "available": False, "attempts": 3, "error": "",
    }
