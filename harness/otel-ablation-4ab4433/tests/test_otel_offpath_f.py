"""otel-offpath-f-v1: the OTel campaign-F epoch (main repo research/traffic-sweep/BUDGET_F.md, research/PLAN_LANES_20261014.md), built while
campaign E's epoch is active and NOT activated.

F is campaign E's design (the upstream task mix as an open loop at 25 req/s, the regimes no-fault, fraud pause, accounting pause and the frontend pause,
5 blocks, blocks 1-3 training and 4-5 test) with four changes, each covered here with a planted defect: (1) the SDK metric export interval of 5 s,
rendered into the materialized posture overlay from a new plan variable, epoch-gated; (2) the spanmetrics flush interval of 5 s; (3) the collector's
kafkametrics receiver with service.name=kafka and its pipeline; (4) two no-fault cells per block (25 cells).  Also covered: E is untouched (its
descriptor and plan pins, its rendered tree), F's plan and descriptor pins (3.9/3.13 identity), the run order and the onset strata, no run-ID reuse,
the epoch in the runtime and the gate chain (selector NOT naming F at this commit), a cell of each kind end to end on the fake target (including the
second no-fault cell), the posture proof's view of the kafka resource, and the 3.9 floor.

Like the other epochs' tests, F is exercised in a copy of the module tree with its own selector, so these tests pass whichever epoch the worktree's
committed selector names.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
SOURCE = MODULE / "execution/candidate_offpath_f.py"
EPOCH = "otel-offpath-f-v1"
E_EPOCH = "otel-offpath-e-v1"
NO_FAULT = "no-fault-calibration"
FRONTEND = "frontend-pause-effect"
FRAUD = "fraud-pause-effect"
ACCOUNTING = "accounting-pause-effect"
F_DESCRIPTOR_SHA256 = "6164052dc62c323be37c286afd0f41a90808bbd251f62d56eb959eec01233b7e"
F_PLAN1_SHA256 = "30aa2484fa1aa42c0f9bedbc3b98123dd8a3290a417237d0bb07fb93ae28b5bd"
E_DESCRIPTOR_SHA256 = "a17ac3d676a85dd9b488bd100a925679322ff93ec6c4257e8f102acd700e4398"          # E at 25 req/s, all three faults
E_PLAN1_SHA256 = "503bf014cfb51cc85c96010b2dc4632fe24bba644c804c21fbd405b7bb517661"
F_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor", "quiet-compiler", "repeat-compiler", "repeat-descriptor",
    "repeat-c-compiler", "repeat-c-descriptor",
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


e_tests = load("otel_offpath_f_e_tests", ROOT / "tests/test_otel_offpath_e.py")     # E's compiler, v1's fake target and every shared helper
e = e_tests.p
v1 = e_tests.v1
b_tests = e_tests.b_tests
helpers = e_tests.helpers
NOW = helpers.NOW
p = load("otel_offpath_f_compiler_test", SOURCE)
yaml = pytest.importorskip("yaml")


def _exec(text: str):
    """The compiler source, run as a fresh module that believes it lives at SOURCE (its siblings and ROOT resolve there)."""
    module = types.ModuleType("otel_offpath_f_variant")
    module.__file__ = str(SOURCE)
    exec(compile(text, str(SOURCE), "exec"), module.__dict__)
    return module


def _planted(old: str, new: str):
    """F's compiler with exactly one source edit, as a fresh module."""
    text = SOURCE.read_text()
    assert text.count(old) == 1, old
    return _exec(text.replace(old, new))


def _plan(attempt: int = 1):
    return p.compile_plan(p.load_descriptor(), attempt)


def _cells(plan=None):
    return p.flatten_cells(plan or _plan())


def _tree(tmp_path_factory, label: str, epoch: str = EPOCH):
    root = helpers._copy_tree(tmp_path_factory.mktemp(label), selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n")
    module = root / "modules/otel-demo"
    loaded = types.SimpleNamespace(root=root, epoch=epoch)
    loaded.runtime = load(f"otel_{label}_runtime", module / "execution/candidate_runtime.py")
    loaded.remote = load(f"otel_{label}_remote", module / "execution/candidate_remote.py")
    loaded.setup = load(f"otel_{label}_setup", module / "execution/candidate_setup.py")
    loaded.terminal = load(f"otel_{label}_terminal", module / "validation/candidate_terminal.py")
    loaded.compiler = load(f"otel_{label}_compiler", module / "execution/candidate_offpath_f.py")
    return loaded


@pytest.fixture(scope="module")
def f_tree(tmp_path_factory):
    return _tree(tmp_path_factory, "offpath-f-tree")


@pytest.fixture(scope="module")
def f_package(f_tree, tmp_path_factory):
    return helpers._package(f_tree.runtime, f_tree.compiler, tmp_path_factory.mktemp("offpath-f-package"), window_hours=5)


@pytest.fixture(scope="module")
def materialized(tmp_path_factory):
    out = {}
    for label, epoch in (("f", EPOCH), ("e", E_EPOCH), ("v2", e_tests.V2), ("c", e_tests.C)):
        tree = helpers._copy_tree(tmp_path_factory.mktemp("materialize-f-" + label),
                                  selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n")
        out[label] = tree / "out"
        out[label + "-digest"] = b_tests._materialize(tree, out[label])
    return out


# ------------------------------------------------------------------------------------- 1. the plan, its pins, E untouched
def test_f_is_pinned_25_cells_in_5_blocks_two_no_fault_cells_per_block_and_the_split_is_in_the_descriptor():
    document = p.load_descriptor()
    plan = _plan()
    assert p.canonical_sha256(document) == F_DESCRIPTOR_SHA256 == p.EXPECTED_DESCRIPTOR_SHA256
    assert p.canonical_sha256(plan) == F_PLAN1_SHA256
    assert (p.TOTAL_RUNS, p.CELLS_PER_BLOCK, p.BLOCKS, p.RATE) == (25, 5, 5, 25.0) and plan["runCount"] == plan["uniqueRunCount"] == 25
    assert (p.MINIMUM_REMAINING_SECONDS, p.RUN_WINDOW_HOURS) == (14275, 5)
    cells = _cells(plan)
    assert sorted(cell["runKey"]["regime"] for cell in cells) == sorted([NO_FAULT] * 10 + [FRAUD] * 5 + [ACCOUNTING] * 5 + [FRONTEND] * 5)
    for block in plan["blocks"]:
        assert [c["runKey"]["regime"] for c in block["cells"][:2]] == [NO_FAULT, NO_FAULT]
        assert sorted(c["runKey"]["replicate"] for c in block["cells"][:2]) == [1, 2]
        assert all(c["runKey"]["replicate"] == 1 for c in block["cells"][2:])
        assert block["cells"][-1]["runKey"]["regime"] == FRONTEND
        assert block["split"] == ("training" if block["block"] in (1, 2, 3) else "test")
    assert document["design"]["split"] == p.split_record() == document["analysis"]["split"] == document["schedule"]["split"]
    assert document["design"]["episodesPerRegimeAndRate"] == {NO_FAULT: 10, FRAUD: 5, ACCOUNTING: 5, FRONTEND: 5}
    assert document["design"]["totalRuns"] == 25 and document["design"]["noFaultCellsPerBlock"] == 2
    assert document["schedule"]["leadCell"] is None
    assert [r["id"] for r in document["design"]["regimes"]] == [NO_FAULT, FRAUD, ACCOUNTING, FRONTEND]


def test_planted_defect_an_edited_descriptor_or_plan_or_parameter_is_refused():
    document = p.load_descriptor()
    edited = copy.deepcopy(document)
    edited["timing"]["metricExportIntervalMilliseconds"] = None
    with pytest.raises(p.ProtocolError, match="differs from its generator"):
        p.validate_descriptor(edited)
    plan = _plan()
    broken = copy.deepcopy(plan)
    broken["blocks"][0]["cells"][1]["runKey"]["replicate"] = 1
    with pytest.raises(p.ProtocolError):
        p.validate_plan(document, broken)
    for old, new, message in (
        ("RATE = 25.0\nKEPT_FAULTS", "RATE = 50.0\nKEPT_FAULTS", "RATE"),
        ("NO_FAULT_CELLS_PER_BLOCK = 2\n# ====", "NO_FAULT_CELLS_PER_BLOCK = 1\n# ====", "NO_FAULT_CELLS_PER_BLOCK"),
        ('KEPT_FAULTS = ("fraud-pause", "accounting-pause", "frontend-pause")', 'KEPT_FAULTS = ("fraud-pause", "frontend-pause")', "KEPT_FAULTS"),
    ):
        with pytest.raises(Exception, match=message):
            _planted(old, new)
    # a stale pin cannot be loaded
    module = _planted(F_DESCRIPTOR_SHA256, "0" * 64)
    with pytest.raises(module.ProtocolError, match="reviewed pin"):
        module.load_descriptor()


def test_the_descriptor_file_is_the_generators_output_and_the_digests_are_identical_under_python39_isolated():
    assert (ROOT / "pipelines/campaigns/otel-offpath-f-v1.json").read_bytes() == p._pretty_bytes(p.derive_f_descriptor())
    result = subprocess.run(["/usr/bin/python3", "-I", str(SOURCE), "--print-digests"], capture_output=True, text=True, check=True)
    digests = json.loads(result.stdout)
    assert digests["descriptorCanonicalSha256"] == F_DESCRIPTOR_SHA256 and digests["planCanonicalSha256"] == F_PLAN1_SHA256
    assert (digests["runCount"], digests["runWindowHours"]) == (25, 5)


def test_e_is_untouched_its_pins_its_epoch_and_its_run_ids_and_f_shares_none_of_them():
    assert e.canonical_sha256(e.load_descriptor()) == E_DESCRIPTOR_SHA256 == p.DESIGN_DESCRIPTOR_SHA256
    assert e.canonical_sha256(e.compile_plan(e.load_descriptor(), 1)) == E_PLAN1_SHA256
    assert e.TOTAL_RUNS == 20 and e.EPOCH == E_EPOCH != p.EPOCH
    assert p.load_descriptor()["derivedFrom"]["designSource"] == {
        "studyEpoch": E_EPOCH, "descriptorCanonicalSha256": E_DESCRIPTOR_SHA256,
        "note": "campaign E's variant (25 req/s, all three faults), pinned by digest; this generator does not read E's descriptor or compiler"}
    ran = e_tests._ran_run_ids()
    ran_e = {(E_EPOCH, attempt): {c["runId"] for c in e.flatten_cells(e.compile_plan(e.load_descriptor(), attempt))} for attempt in (1, 2, 3)}
    for attempt in (1, 2, 3):
        ids = {cell["runId"] for cell in _cells(_plan(attempt))}
        assert len(ids) == 25 and v1._reused(ids, {**ran, **ran_e}) == {}, attempt
    # planted: F's run key without the replicate collides the two no-fault cells of every block, and the plan refuses it
    module = _planted('"block": int(block), "replicate": int(replicate), "posture": posture,', '"block": int(block), "posture": posture,')
    with pytest.raises(module.ProtocolError):
        module.compile_plan(module.derive_f_descriptor(), 1)
    # planted: F under E's epoch id and E's run-key shape would reuse E's run IDs, and the reuse check finds them (the check is not trivially true)
    clash = _planted('EPOCH = "otel-offpath-f-v1"\n', 'EPOCH = "otel-offpath-e-v1"\n')
    ids = {c["runId"] for c in clash.flatten_cells(clash._compile(clash.derive_f_descriptor(), 1))}
    assert len(ids) == 25 and v1._reused(ids, ran_e) == {}      # the replicate field alone already separates the keys
    legacy = {c["runKey"]["regime"] for c in e.flatten_cells(e.compile_plan(e.load_descriptor(), 1))}
    assert legacy == {NO_FAULT, FRAUD, ACCOUNTING, FRONTEND}


def test_f_is_e_apart_from_the_declared_keys_the_mix_the_scenarios_and_the_criteria_are_es():
    f_doc, e_doc = p.load_descriptor(), e.load_descriptor()
    assert p.MIX == e.MIX and p.canonical_json_bytes(p.MIX) == e.canonical_json_bytes(e.MIX)
    assert f_doc["faultDesign"]["scenarios"] == e_doc["faultDesign"]["scenarios"]
    assert p.MANIFESTATION_CRITERION == e.MANIFESTATION_CRITERION
    assert {k: v for k, v in p.MANIFESTATION_CRITERION_DEFAULTS.items() if k != "unit"} == {
        k: v for k, v in e.MANIFESTATION_CRITERION_DEFAULTS.items() if k != "unit"}
    assert p.MANIFESTATION_CRITERION_DEFAULTS["unit"] == e.MANIFESTATION_CRITERION_DEFAULTS["unit"].replace("campaign E", "campaign F")
    assert (p.CONCURRENCY, p.GENERATOR_OPEN_FILES_MINIMUM, p.FRONTENDPROXY_MEMORY_LIMIT_BYTES) == (
        e.CONCURRENCY, e.GENERATOR_OPEN_FILES_MINIMUM, e.FRONTENDPROXY_MEMORY_LIMIT_BYTES)
    assert f_doc["workload"] == e_doc["workload"]
    # every key of every cell's timing other than the onset keys and the plan-level sizing is E's cell of the same regime and block
    skip = p.ONSET_TIMING_KEYS | {"planRunCount", "planMinimumRemainingSeconds"}
    for cell in _cells():
        key = cell["runKey"]
        twin = e.cell_timing(key["regime"], 25.0, key["block"])
        assert {k: v for k, v in cell["timing"].items() if k not in skip} == {k: v for k, v in twin.items() if k not in skip}
    top = {k for k in f_doc if f_doc[k] != e_doc[k]}
    assert top == {
        "id", "declaration", "design", "schedule", "timing", "collection", "faultDesign", "outcomes", "sutDeviations", "analysis", "derivedFrom"}


# ------------------------------------------------------------------------------------- 2. change 4: the run order and the onsets
def test_every_block_runs_the_two_no_fault_cells_then_the_off_path_pauses_in_the_seeded_order_then_the_frontend_pause():
    seen = set()
    for block in range(1, 6):
        order = p.block_order(block)
        regimes = [row["regime"] for row in order]
        assert regimes[:2] == [NO_FAULT] * 2 and regimes[-1] == FRONTEND and set(regimes[2:4]) == {FRAUD, ACCOUNTING}
        assert sorted(row["replicate"] for row in order[:2]) == [1, 2]
        seen.add(tuple(regimes[2:4]))
    assert len(seen) == 2                      # both off-path orders occur over the 5 blocks (the seeded draw is not constant)


@pytest.mark.parametrize("old,new", [
    ("(FRONTEND_PAUSE_REGIME,),\n)", "(FRONTEND_PAUSE_REGIME,),\n    (NO_FAULT_REGIME,),\n)"),
    ("ORDER_GROUPS = (\n    (NO_FAULT_REGIME,),\n    (FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME),\n    (FRONTEND_PAUSE_REGIME,),\n)",
     "ORDER_GROUPS = (\n    (FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME),\n    (NO_FAULT_REGIME,),\n    (FRONTEND_PAUSE_REGIME,),\n)"),
])
def test_planted_defect_a_block_order_other_than_nofault_offpath_frontend_is_refused_by_the_rule(old, new):
    text = SOURCE.read_text()
    if text.count(old) != 1:
        pytest.skip("marker")
    module = _exec(text.replace(old, new))
    with pytest.raises(module.ProtocolError):
        module.compile_plan(module.derive_f_descriptor(), 1)


def test_each_no_fault_replicate_takes_the_five_onset_strata_once_over_the_blocks_and_the_replicates_differ():
    width = (1.0 / 25.0) / 5
    by_replicate = {}
    for replicate in (1, 2):
        offsets = [p.onset_phase_offset(NO_FAULT, 25.0, block, replicate) for block in range(1, 6)]
        assert sorted(int(offset / width) for offset in offsets) == [0, 1, 2, 3, 4], (replicate, offsets)
        by_replicate[replicate] = offsets
    assert by_replicate[1] != by_replicate[2]
    for regime in (FRAUD, ACCOUNTING, FRONTEND):
        offsets = [p.onset_phase_offset(regime, 25.0, block) for block in range(1, 6)]
        assert sorted(int(offset / width) for offset in offsets) == [0, 1, 2, 3, 4]
    with pytest.raises(p.ProtocolError):
        p.onset_phase_offset(NO_FAULT, 25.0, 1, 3)
    with pytest.raises(p.ProtocolError):
        p.onset_phase_offset(FRAUD, 25.0, 1, 2)
    # planted: a replicate label that is ignored gives the second no-fault cell the first one's onsets
    module = _planted(
        '''label = regime if int(replicate) == 1 else "%s#replicate-%d" % (regime, int(replicate))''', "label = regime")
    assert [module.onset_phase_offset(NO_FAULT, 25.0, b, 2) for b in range(1, 6)] == by_replicate[1] != by_replicate[2]
    # E's no-fault cell kept its own draw: F's replicate 1 is not E's (the epoch id is in the draw)
    assert [e.onset_phase_offset(NO_FAULT, 25.0, b) for b in range(1, 6)] != by_replicate[1]


# ------------------------------------------------------------------------------------- 3. changes 1 to 3 in the descriptor
SDK_HONOURS = {"yes", "no", "not-applicable", "unverified"}


def _coverage_problems(rows, services):
    """What is wrong with an SDK-coverage table: services missing, listed twice, or a verdict outside the vocabulary."""
    listed = [service for row in rows for service in row["services"]]
    problems = ["missing %s" % s for s in sorted(set(services) - set(listed))]
    problems += ["twice %s" % s for s in sorted({s for s in listed if listed.count(s) > 1})]
    problems += ["extra %s" % s for s in sorted(set(listed) - set(services))]
    problems += ["verdict %r" % row["honours"] for row in rows if row["honours"] not in SDK_HONOURS]
    problems += ["no basis for %s" % row["language"] for row in rows if not row.get("basis")]
    return problems


def test_the_descriptor_declares_the_5_second_sdk_interval_and_covers_every_catalog_service_once():
    document = p.load_descriptor()
    catalog = json.loads((MODULE / "postures/catalog.json").read_text())
    cadence = document["collection"]["telemetryCadence"]
    assert document["timing"]["metricExportIntervalMilliseconds"] == 5000 == document["faultDesign"]["metricExportIntervalMilliseconds"]
    assert "set: OTEL_METRIC_EXPORT_INTERVAL=5000" in document["timing"]["metricExportIntervalNote"]
    assert cadence["sdkMetricExportIntervalMilliseconds"] == 5000 and cadence["spanmetricsFlushInterval"] == "5s"
    assert _coverage_problems(cadence["sdkCoverage"], catalog["applicationServices"]) == []
    by_service = {s: row["honours"] for row in cadence["sdkCoverage"] for s in row["services"]}
    assert {s for s, v in by_service.items() if v == "yes"} == {
        "adservice", "frauddetectionservice", "kafka", "quoteservice", "checkoutservice", "productcatalogservice",
        "recommendationservice", "loadgenerator", "cartservice"}
    assert {s for s, v in by_service.items() if v == "no"} == {"flagd", "frontend", "paymentservice", "currencyservice"}
    assert {s for s, v in by_service.items() if v == "unverified"} == {"accountingservice", "flagd-ui"}
    # planted: a table that drops a service, lists one twice, or carries a verdict outside the vocabulary is found
    rows = copy.deepcopy(cadence["sdkCoverage"])
    rows[0]["services"] = rows[0]["services"][1:]
    assert _coverage_problems(rows, catalog["applicationServices"]) == ["missing %s" % cadence["sdkCoverage"][0]["services"][0]]
    rows = copy.deepcopy(cadence["sdkCoverage"])
    rows[1]["services"] = rows[1]["services"] + ["adservice"]
    rows[2]["honours"] = "probably"
    assert _coverage_problems(rows, catalog["applicationServices"]) == ["twice adservice", "verdict 'probably'"]


def test_the_descriptor_declares_the_kafkametrics_receiver_and_the_other_epochs_refuse_a_non_null_interval():
    document = p.load_descriptor()
    cadence = document["collection"]["telemetryCadence"]
    assert cadence["kafkametrics"] == {
        "receiver": "kafkametrics", "brokers": ["kafka:9092"], "scrapers": ["consumers"], "collectionInterval": "5s",
        "resourceServiceName": "kafka", "processor": "resource/kafka", "pipeline": "metrics/kafka", "exporters": ["debug"]}
    assert "receiver/kafkametricsreceiver v0.108.0" in cadence["kafkametricsImage"]
    rows = [row for row in document["sutDeviations"] if row["service"] == "otelcol" and "kafkametrics" in row["setting"]]
    assert len(rows) == 1 and rows[0]["scope"] == "campaign F's cells only"
    # the sweep's compiler (C's, E's and the pilots' base) refuses an interval override: F's descriptor says so itself, E's still says null
    assert e.load_descriptor()["timing"]["metricExportIntervalMilliseconds"] is None
    assert e.load_descriptor()["faultDesign"]["metricExportIntervalMilliseconds"] is None
    assert "telemetryCadence" not in e.load_descriptor()["collection"]
    # planted: the descriptor generator with the interval left null is not F's descriptor
    module = _planted("SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS = 5000 ", "SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS = None ")
    assert module.derive_f_descriptor()["timing"]["metricExportIntervalMilliseconds"] is None
    with pytest.raises(module.ProtocolError, match="differs from its generator"):
        module.validate_descriptor(p.load_descriptor())


# ------------------------------------------------------------------------------------- 4. changes 1 to 3 in the rendered tree
def _services(path: Path) -> dict:
    return yaml.safe_load(path.read_text())["services"]


def test_the_collector_config_of_f_carries_the_spanmetrics_flush_the_kafkametrics_receiver_its_processor_and_its_pipeline(materialized):
    f_config = yaml.safe_load(b_tests._collector_config(materialized["f"]))
    e_config = yaml.safe_load(b_tests._collector_config(materialized["e"]))
    assert f_config["connectors"]["spanmetrics"] == {"metrics_flush_interval": "5s"}
    assert f_config["receivers"]["kafkametrics"] == {"brokers": ["kafka:9092"], "scrapers": ["consumers"], "collection_interval": "5s"}
    assert f_config["processors"]["resource/kafka"] == {"attributes": [{"key": "service.name", "value": "kafka", "action": "upsert"}]}
    pipelines = f_config["service"]["pipelines"]
    assert pipelines["metrics/kafka"] == {"receivers": ["kafkametrics"], "processors": ["resource/kafka", "batch"], "exporters": ["debug"]}
    assert "debug" in f_config["exporters"]
    # every component a pipeline names is defined; every other pipeline is E's, byte for byte as data
    defined = {"receivers": set(f_config["receivers"]), "processors": set(f_config["processors"]),
               "exporters": set(f_config["exporters"]) | set(f_config["connectors"])}
    for name, pipeline in pipelines.items():
        for kind in ("receivers", "processors", "exporters"):
            assert set(pipeline.get(kind, [])) <= defined[kind] | (set(f_config["connectors"]) if kind == "receivers" else set()), (name, kind)
    assert {k: v for k, v in pipelines.items() if k != "metrics/kafka"} == e_config["service"]["pipelines"]
    for section in ("receivers", "processors", "exporters", "connectors"):
        removed = {"receivers": {"kafkametrics"}, "processors": {"resource/kafka"}, "exporters": set(), "connectors": set()}[section]
        assert {k: v for k, v in f_config[section].items() if k not in removed} == {
            k: v for k, v in e_config[section].items() if not (section == "connectors" and k == "spanmetrics")} | (
            {"spanmetrics": f_config["connectors"]["spanmetrics"]} if section == "connectors" else {})
    assert e_config["connectors"]["spanmetrics"] is None and "kafkametrics" not in e_config["receivers"]
    assert f_config["service"]["telemetry"]["logs"]["sampling"]["enabled"] is False          # the collector's log sampler stays off


def test_the_posture_overlay_of_f_binds_the_interval_on_every_service_with_a_metrics_exporter_and_e_renders_the_repository_file(materialized):
    repo = (MODULE / "deployment/compose.candidate-postures.yml").read_text()
    catalog = json.loads((MODULE / "postures/catalog.json").read_text())
    f_services = _services(materialized["f"] / "compose.candidate-postures.yml")
    e_services = _services(materialized["e"] / "compose.candidate-postures.yml")
    expected = "${OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL:?candidate posture required}"
    bound = sorted(s for s, row in f_services.items() if "OTEL_METRIC_EXPORT_INTERVAL" in row.get("environment", {}))
    assert bound == sorted(set(catalog["applicationServices"]) - {"frontendproxy"}) and len(bound) == 18      # frontendproxy has no SDK environment
    assert {f_services[s]["environment"]["OTEL_METRIC_EXPORT_INTERVAL"] for s in bound} == {expected}
    assert {s for s, row in e_services.items() if "OTEL_METRICS_EXPORTER" in row.get("environment", {})} == set(bound)
    assert all("OTEL_METRIC_EXPORT_INTERVAL" not in row.get("environment", {}) for row in e_services.values())
    # everything else of F's overlay is the repository file's: removing the added lines gives the file back
    rendered = (materialized["f"] / "compose.candidate-postures.yml").read_text()
    assert re.sub(r'^ +OTEL_METRIC_EXPORT_INTERVAL: .*\n', "", rendered, flags=re.M) == repo
    for label in ("e", "v2", "c"):
        assert (materialized[label] / "compose.candidate-postures.yml").read_bytes() == repo.encode()


def test_otelcol_waits_for_a_healthy_kafka_in_f_and_every_other_epoch_keeps_its_overlay(materialized):
    f_overlay = yaml.safe_load((materialized["f"] / "compose.otel-placement.yml").read_text())["services"]
    e_overlay = yaml.safe_load((materialized["e"] / "compose.otel-placement.yml").read_text())["services"]
    assert f_overlay["otelcol"]["depends_on"] == {"kafka": {"condition": "service_healthy"}}
    assert "depends_on" not in e_overlay["otelcol"]
    assert {k: v for k, v in f_overlay["otelcol"].items() if k != "depends_on"} == e_overlay["otelcol"]
    assert {k: v for k, v in f_overlay.items() if k != "otelcol"} == {k: v for k, v in e_overlay.items() if k != "otelcol"}
    base = yaml.safe_load((ROOT / "upstream/opentelemetry-demo/docker-compose.yml").read_text())["services"]
    assert base["kafka"]["healthcheck"]["test"] == "nc -z kafka 9092"       # service_healthy has something to wait for
    assert "otelcol" not in base["kafka"].get("depends_on", {})              # and no dependency cycle


def test_e_renders_exactly_as_it_did_f_has_its_own_source_digest_and_the_repositorys_files_are_unchanged(materialized):
    assert materialized["e-digest"] == materialized["v2-digest"] != materialized["c-digest"]
    assert materialized["f-digest"] not in (materialized["e-digest"], materialized["v2-digest"], materialized["c-digest"])
    for name in ("src/otelcollector/otelcol-placement.yml", "compose.otel-placement.yml"):
        assert (materialized["e"] / name).read_bytes() == (materialized["v2"] / name).read_bytes()
    materialize = load("otel_offpath_f_materialize_module", MODULE / "materialize.py")
    assert EPOCH in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS and EPOCH in materialize.FRONTENDPROXY_LOG_RETENTION_EPOCHS
    # 2026-10-15: the F ablation shares the interval and the flush (TELEMETRY_CADENCE_EPOCHS) and not the kafkametrics rendering (KAFKAMETRICS_EPOCHS)
    assert materialize.TELEMETRY_CADENCE_EPOCHS == materialize.METRIC_EXPORT_INTERVAL_EPOCHS == (EPOCH, "otel-offpath-f-nolag-v1")
    assert materialize.KAFKAMETRICS_EPOCHS == (EPOCH,)
    # the rendering functions are the identity for every other epoch and for no selector
    for epoch in (None, E_EPOCH, e_tests.V2, e_tests.C):
        text = (MODULE / "deployment/compose.candidate-postures.yml").read_text()
        assert materialize.render_posture_overlay(text, epoch) == text
        assert materialize.render_collector_config("anything", epoch) == "anything"
    assert (materialized["f"] / "src/otelcollector/otelcol-placement.yml").read_text().count("kafkametrics") == 2     # the receiver and the pipeline's list


@pytest.mark.parametrize("old,new,probe", [
    ('"otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1", "otel-offpath-f-nolag-v1")\nCOLLECTOR_LOG_SAMPLING_OFF =',
     '"otel-offpath-pilot-v2", "otel-offpath-e-v1")\nCOLLECTOR_LOG_SAMPLING_OFF =', "sampler"),
    ('TELEMETRY_CADENCE_EPOCHS = ("otel-offpath-f-v1", "otel-offpath-f-nolag-v1")', "TELEMETRY_CADENCE_EPOCHS = ()", "collector"),
    ('SPANMETRICS_FLUSH_INTERVAL = "5s"', 'SPANMETRICS_FLUSH_INTERVAL = "60s"', "flush"),
    ('"    brokers: [\\"kafka:9092\\"]\\n"', '"    brokers: [\\"kafka:9093\\"]\\n"', "brokers"),
    ('"        action: upsert\\n"', '"        action: insert\\n"', "upsert"),
    ('METRIC_EXPORT_INTERVAL_EPOCHS = TELEMETRY_CADENCE_EPOCHS', "METRIC_EXPORT_INTERVAL_EPOCHS = ()", "interval"),
])
def test_planted_defect_in_the_rendering_of_f_is_seen_by_the_rendered_tree_checks(old, new, probe, tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    assert text.count(old) == 1, old
    script.write_text(text.replace(old, new))
    out = tree / "out"
    b_tests._materialize(tree, out)
    config = yaml.safe_load(b_tests._collector_config(out))
    overlay = _services(out / "compose.candidate-postures.yml")
    if probe == "sampler":
        assert b_tests._log_sampling_enabled(b_tests._collector_config(out)) is None
    elif probe == "collector":
        assert "kafkametrics" not in config["receivers"] and "metrics/kafka" not in config["service"]["pipelines"]
        assert config["connectors"]["spanmetrics"] is None
    elif probe == "flush":
        assert config["connectors"]["spanmetrics"] == {"metrics_flush_interval": "60s"} != {"metrics_flush_interval": "5s"}
    elif probe == "brokers":
        assert config["receivers"]["kafkametrics"]["brokers"] == ["kafka:9093"]
    elif probe == "upsert":
        assert config["processors"]["resource/kafka"]["attributes"][0]["action"] == "insert"
    else:
        assert all("OTEL_METRIC_EXPORT_INTERVAL" not in row.get("environment", {}) for row in overlay.values())


# ------------------------------------------------------------------------------------- 5. change 1 in the plan and install environments
def _referenced(overlay_text: str) -> set:
    return set(re.findall(r"\$\{(OTEL_CANDIDATE_[A-Z0-9_]+):?\?", overlay_text))


def test_the_plan_environment_carries_the_interval_in_f_only_and_covers_every_variable_the_rendered_overlay_names(f_tree, materialized, tmp_path_factory):
    e_tree = _tree(tmp_path_factory, "offpath-f-checks-e", E_EPOCH)                   # a tree copy whose selector names E (F is activated in the worktree)
    assert e_tree.runtime.STUDY_EPOCH == E_EPOCH != EPOCH
    for posture in ("none", "selected", "async", "full"):
        env = f_tree.runtime.posture_environment(posture, "/bound/source")
        assert env["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == "5000"
        assert "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL" not in e_tree.runtime.posture_environment(posture, "/bound/source")
        assert _referenced((materialized["f"] / "compose.candidate-postures.yml").read_text()) <= set(env), posture
        assert _referenced((materialized["e"] / "compose.candidate-postures.yml").read_text()) <= set(
            e_tree.runtime.posture_environment(posture, "/bound/source")), posture
    # the environments differ by exactly the one variable
    full_f = f_tree.runtime.posture_environment("full", "/s")
    full_e = e_tree.runtime.posture_environment("full", "/s")
    assert {k: v for k, v in full_f.items() if k != "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"} == full_e
    # planted: an environment without the variable leaves the rendered overlay's reference unbound, and the closure check names it
    missing = {k: v for k, v in full_f.items() if k != "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"}
    assert _referenced((materialized["f"] / "compose.candidate-postures.yml").read_text()) - set(missing) == {"OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"}


def test_the_install_side_environment_follows_the_rendered_overlay_and_equals_the_full_posture_environment(f_tree, materialized, tmp_path, tmp_path_factory):
    for label, tree_runtime, tree_setup in (("f", f_tree.runtime, f_tree.setup),):
        source = materialized[label]
        installed = tree_setup.compose_environment(source, "f" * 64)
        full = tree_runtime.posture_environment("full", str(source))
        assert installed["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == full["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == "5000"
        for key, value in full.items():
            assert installed[key] == value, key
    e_copy = _tree(tmp_path_factory, "offpath-f-checks-e2", E_EPOCH)                 # a tree copy whose selector names E
    e_runtime, e_setup = e_copy.runtime, e_copy.setup
    installed = e_setup.compose_environment(materialized["e"], "f" * 64)
    assert "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL" not in installed
    assert {k: v for k, v in installed.items() if k in e_runtime.posture_environment("full", str(materialized["e"]))} == \
        e_runtime.posture_environment("full", str(materialized["e"]))
    # planted: an install side that ignores the rendered overlay leaves F's `:?` reference unbound
    text = (MODULE / "execution/candidate_setup.py").read_text()
    marker = 'if overlay.is_file() and "${" + METRIC_EXPORT_INTERVAL_VARIABLE + ":?" in overlay.read_text(encoding="utf-8"):'
    assert text.count(marker) == 1
    planted = _exec_setup(text.replace(marker, "if False:"))
    bad = planted.compose_environment(materialized["f"], "f" * 64)
    assert _referenced((materialized["f"] / "compose.candidate-postures.yml").read_text()) - set(bad) == {"OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"}


def _exec_setup(text: str):
    module = types.ModuleType("otel_offpath_f_planted_setup")
    module.__file__ = str(MODULE / "execution/candidate_setup.py")
    sys.modules[module.__name__] = module
    exec(compile(text, module.__file__, "exec"), module.__dict__)
    return module


def test_the_materializer_and_the_runtime_state_the_same_epochs_and_variable_and_a_difference_is_refused(f_tree, tmp_path):
    runtime = f_tree.runtime
    runtime.verify_materializer_constants()
    assert runtime.METRIC_EXPORT_INTERVAL_STUDY_EPOCHS == (EPOCH, "otel-offpath-f-nolag-v1") and runtime.METRIC_EXPORT_INTERVAL_MILLISECONDS == "5000"
    assert f_tree.setup.METRIC_EXPORT_INTERVAL_MILLISECONDS == runtime.METRIC_EXPORT_INTERVAL_MILLISECONDS
    assert f_tree.setup.METRIC_EXPORT_INTERVAL_VARIABLE == runtime.METRIC_EXPORT_INTERVAL_VARIABLE
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    marker = 'METRIC_EXPORT_INTERVAL_VARIABLE = "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, 'METRIC_EXPORT_INTERVAL_VARIABLE = "OTEL_CANDIDATE_METRIC_INTERVAL"'))
    planted = load("otel_offpath_f_planted_runtime", tree / "modules/otel-demo/execution/candidate_runtime.py")
    with pytest.raises(planted.GateError, match="metric export interval"):
        planted.verify_materializer_constants()


# ------------------------------------------------------------------------------------- 6. the posture proof's view of the kafka resource
SAMPLE_KAFKA_METRICS = """\
ResourceMetrics #0
Resource SchemaURL:
Resource attributes:
     -> service.name: Str(kafka)
ScopeMetrics #0
Metric #0
Descriptor:
     -> Name: kafka.consumer_group.lag
"""


def test_the_kafka_resource_is_in_the_full_active_set_and_a_resource_named_otherwise_would_be_flagged(f_tree):
    catalog = json.loads((MODULE / "postures/catalog.json").read_text())
    active = catalog["postures"]["full"]["activeApplicationServices"]
    assert "kafka" in active and F_DESCRIPTOR_SHA256 == p.canonical_sha256(p.load_descriptor())
    assert p.load_descriptor()["postureRealization"]["full"]["status"] == _cells()[0]["realizationStatus"]
    assert set(p.POSTURES) == {"full"}
    remote = f_tree.remote

    def observed(log: str) -> list:
        return sorted({remote.catalog_service(n) for n in re.findall(r"service\.name:\s*Str\(([^)]+)\)", log)})

    assert observed(SAMPLE_KAFKA_METRICS) == ["kafka"] and not set(observed(SAMPLE_KAFKA_METRICS)) - set(active) - {remote.COLLECTOR_SELF_SERVICE}
    # planted: the same receiver without the upsert names no service and the reader would drop it; a differently named one is unexpected
    unnamed = SAMPLE_KAFKA_METRICS.replace("     -> service.name: Str(kafka)\n", "")
    assert observed(unnamed) == []
    renamed = SAMPLE_KAFKA_METRICS.replace("Str(kafka)", "Str(kafka-broker)")
    assert set(observed(renamed)) - set(active) - {remote.COLLECTOR_SELF_SERVICE} == {"kafka-broker"}
    config = yaml.safe_load((ROOT / "pipelines/campaigns/otel-offpath-f-v1.json").read_text())
    assert config["collection"]["telemetryCadence"]["kafkametrics"]["resourceServiceName"] == "kafka"


# ------------------------------------------------------------------------------------- 7. the epoch in the runtime and the gate chain (NOT activated)
def test_f_is_not_selected_in_the_ablation_worktree_the_selector_and_the_tombstone_name_the_ablation_and_e_is_terminal():
    # 2026-10-15: in the worktree observability-placement-runtime-otel-ablation the selector and the tombstone name the F ablation
    # (otel-offpath-f-nolag-v1); campaign F's own worktree names F.  F is exercised in tree copies with their own selector.
    selector = json.loads((MODULE / "execution/study-epoch.json").read_text())
    assert selector == {"schemaVersion": 1, "studyEpoch": "otel-offpath-f-nolag-v1"}
    for name in ("candidate_remote.py", "candidate_setup.py"):
        tree_ = ast.parse((MODULE / "execution" / name).read_text())
        values = [ast.literal_eval(n.value) for n in tree_.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "ADMITTED_STUDY_EPOCHS"]
        assert values == [("otel-offpath-f-nolag-v1",)], name
    assert EPOCH not in (MODULE / "execution/study-epoch.json").read_text()
    assert E_EPOCH not in (MODULE / "execution/study-epoch.json").read_text()
    assert e_tests.V2 not in (MODULE / "execution/study-epoch.json").read_text()


def test_a_selector_naming_f_activates_it_in_every_reader_and_the_gate_chain_derives_25_cells(f_tree, f_package, tmp_path):
    runtime, remote = f_tree.runtime, f_tree.remote
    assert runtime.STUDY_EPOCH == EPOCH and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (25, 14275, 5)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | F_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_offpath_f.py"
    assert runtime.DESCRIPTOR == f_tree.root / "pipelines/campaigns/otel-offpath-f-v1.json"
    assert f_tree.setup.controller_paths(EPOCH) == runtime.CONTROLLER_PATHS
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {
        "duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}
    assert EPOCH in remote.REPEAT_STUDY_EPOCHS and EPOCH in remote.TIMED_STUDY_EPOCHS and E_EPOCH in remote.REPEAT_STUDY_EPOCHS
    binding = f_package.gate_plan["binding"]
    assert f"study={EPOCH} " in f_package.gate_plan["typedApproval"] and " runs=25 " in f_package.gate_plan["typedApproval"]
    assert f_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 14275
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_offpath_f_v1" and remote.SAFE_NAME.fullmatch(binding["compose"]["project"])
    earlier = (e_tests.SWEEP, e_tests.QUIET, e_tests.REPEAT, e_tests.C, e_tests.LOAD, e_tests.V1, e_tests.V2, E_EPOCH)
    other = (["/home/stig/observability-placement-candidate-v4-runs/" + x for x in earlier]
             + ["/home/stig/observability-placement-candidate-v4-runs/.setup-" + x for x in earlier]
             + ["/home/stig/observability-placement-candidate-v4-otel-srv6/" + x + "-" for x in earlier])
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert EPOCH in binding[key] and not any(binding[key].startswith(path) for path in other), key
    document = runtime.execution_package(f_package)
    assert document["runCount"] == 25 and len(document["cells"]) == 25
    for contract, cell in zip(document["cells"], f_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and runtime.sweep_cell_timing(contract) == cell["timing"]
        assert contract["runKey"]["replicate"] in (1, 2)
        assert contract["posture"]["environment"]["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == "5000"
        assert contract["workload"]["concurrency"] == 750
    assert sum("docker-events.json" in c["requiredArtifacts"] for c in document["cells"]) == 15
    assert len({c["runId"] for c in document["cells"]}) == 25
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (EPOCH,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
    assert len(cells) == 25 and remote.expected_minimum_remaining(document) == 14275
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_offpath_f_tree_adapter", f_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == EPOCH and adapter.SPENT_ATTEMPTS == {}
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 25 and bindings.plan_sha256 == F_PLAN1_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_planted_defect_a_selector_naming_f_without_its_controller_set_is_refused(tmp_path_factory):
    root = helpers._copy_tree(tmp_path_factory.mktemp("offpath-f-no-paths"), selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    runtime_path = root / "modules/otel-demo/execution/candidate_runtime.py"
    text = runtime_path.read_text()
    marker = '    OFFPATH_F_STUDY_EPOCH: {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_f.py",'
    assert text.count(marker) == 1
    runtime_path.write_text(text.replace(marker, '    "otel-offpath-f-v0": {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_f.py",'))
    with pytest.raises(Exception, match="names no declared non-frozen epoch"):
        load("otel_offpath_f_no_paths_runtime", runtime_path)


def test_f_has_spent_nothing_and_e_attempt_1_is_recorded_spent_in_the_adapter():
    table = v1._spent_table_in_source()
    assert table[EPOCH] == {} and set(table[E_EPOCH]) == {1}


# ------------------------------------------------------------------------------------- 8. cells of each kind, end to end (fake target)
def _contract(tree, package, run_id: str, tmp_path: Path) -> dict:
    document = tree.runtime.execution_package(package)
    contract = copy.deepcopy(next(c for c in document["cells"] if c["runId"] == run_id))
    source = tmp_path / "source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "candidate-posture-contract.json").write_bytes((MODULE / "postures/catalog.json").read_bytes())
    release = tmp_path / "release"
    gates = release / "repository/modules/otel-demo/validation/protocol_gates.py"
    gates.parent.mkdir(parents=True, exist_ok=True)
    gates.write_bytes((MODULE / "validation/protocol_gates.py").read_bytes())
    contract["remoteSourceRoot"] = str(source)
    contract["releaseRoot"] = str(release)
    contract["remoteArtifactRoot"] = str(tmp_path / "artifacts" / contract["compiledArtifactRoot"])
    return contract


def _run_id(plan, regime: str, block: int, replicate: int) -> str:
    return next(c["runId"] for c in p.flatten_cells(plan)
                if (c["runKey"]["regime"], c["runKey"]["block"], c["runKey"]["replicate"]) == (regime, block, replicate))


CELL_KEYS = [(NO_FAULT, 1, 1), (NO_FAULT, 4, 2), (FRAUD, 4, 1)]


@pytest.fixture(scope="module")
def cells(f_tree, f_package, tmp_path_factory):
    out = {}
    plan = _plan()
    for regime, block, replicate in CELL_KEYS:
        with pytest.MonkeyPatch.context() as patch:
            base = tmp_path_factory.mktemp(f"offpath-f-cell-{regime}-{block}-{replicate}")
            contract = _contract(f_tree, f_package, _run_id(plan, regime, block, replicate), base)
            assert contract["studyEpoch"] == EPOCH
            receipt, target, limits = v1._run(f_tree, contract, patch, pool_cap=256)
            assert receipt["state"] == "valid", (regime, block, replicate, receipt["error"])
            out[(regime, block, replicate)] = types.SimpleNamespace(contract=contract, root=Path(contract["remoteArtifactRoot"]), target=target)
    return out


@pytest.mark.parametrize("key", CELL_KEYS)
def test_run_cell_executes_an_f_cell_and_the_terminal_accepts_it(f_tree, cells, key):
    cell = cells[key]
    contract, root = cell.contract, cell.root
    regime, block, replicate = key
    assert contract["runKey"]["replicate"] == replicate and contract["runKey"]["block"] == block
    assert contract["timing"]["faultOnsetSeconds"] == p.cell_timing(regime, 25.0, block, replicate)["faultOnsetSeconds"]
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    ledger = json.loads((root / "request-ledger.json").read_text())
    assert ledger["offered"] == 4500 == len(ledger["requests"])
    report = v1._validate(f_tree, root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True


def test_the_two_no_fault_cells_of_a_block_are_two_cells_with_their_own_run_ids_roots_and_onsets(cells):
    first, second = cells[(NO_FAULT, 1, 1)].contract, cells[(NO_FAULT, 4, 2)].contract
    assert first["runId"] != second["runId"] and first["compiledArtifactRoot"] != second["compiledArtifactRoot"]
    plan = _plan()
    ids = [(c["runKey"]["block"], c["runKey"]["replicate"], c["runId"]) for c in p.flatten_cells(plan) if c["runKey"]["regime"] == NO_FAULT]
    assert len(ids) == 10 and len({row[2] for row in ids}) == 10
    for block in range(1, 6):
        pair = [row for row in ids if row[0] == block]
        assert sorted(row[1] for row in pair) == [1, 2]
        assert p.cell_timing(NO_FAULT, 25.0, block, 1)["faultOnsetSeconds"] != p.cell_timing(NO_FAULT, 25.0, block, 2)["faultOnsetSeconds"]


# ------------------------------------------------------------------------------------- 9. the 3.9 floor
F_TARGET_FILES = (
    "modules/otel-demo/execution/candidate_offpath_f.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/execution/candidate_runtime_adapter.py",
    "modules/otel-demo/materialize.py",
)


@pytest.mark.parametrize("relative", F_TARGET_FILES)
def test_touched_target_files_parse_as_python39_and_read_no_name_bound_nowhere(relative):
    tree_ = ast.parse((ROOT / relative).read_text(), feature_version=(3, 9))
    assert b_tests._unbound_names(tree_) == []
    assert any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names) for n in tree_.body)
    result = subprocess.run(["/usr/bin/python3", "-I", "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())", str(ROOT / relative)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_a_planted_name_bound_nowhere_in_f_is_found_by_the_scan():
    text = SOURCE.read_text().replace(
        "    return min(offset, round(inter_arrival - 1e-6, 6))", "    return min(offset, round(inter_arrival - 1e-6, 6))")
    planted = text.replace('    label = regime if int(replicate) == 1', '    label = regime if int(replicate) == unbound_replicate_name')
    assert planted != text
    assert b_tests._unbound_names(ast.parse(planted, feature_version=(3, 9))) != []
