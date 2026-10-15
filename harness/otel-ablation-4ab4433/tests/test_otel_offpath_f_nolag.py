"""otel-offpath-f-nolag-v1: the F ablation epoch (main repo research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md item 2).

The epoch is campaign F's design (tests/test_otel_offpath_f.py) with exactly ONE change: the collector's kafkametrics receiver, its resource/kafka
processor, its metrics/kafka pipeline and otelcol's depends_on kafka are not rendered.  Everything else is F's (25 cells, 5 blocks, two no-fault cells
per block, the mix, the faults, the 25 req/s rate, the 1-3 / 4-5 split, the 5 s SDK export interval, the 5 s spanmetrics flush, the sizing).  Covered
here, each with a planted defect where the claim is about a rule: the plan and descriptor pins (3.9/3.13 identity), that F and E are untouched (pins,
rendered-tree digests measured at 715d57b), that the descriptor equals F's apart from the declared keys, the run order and the onset strata, the
rendered tree (nolag == F minus the four kafka pieces, nothing else), the plan and install environments, the epoch in the runtime and the gate chain,
cells of each kind end to end on the fake target, the activation in this worktree, and the 3.9 floor.

Like the other epochs' tests, the epoch is exercised in a copy of the module tree with its own selector, so these tests pass whichever epoch the
worktree's committed selector names (except the activation test, which reads the committed selector).
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
SOURCE = MODULE / "execution/candidate_offpath_f_nolag.py"
EPOCH = "otel-offpath-f-nolag-v1"
F_EPOCH = "otel-offpath-f-v1"
E_EPOCH = "otel-offpath-e-v1"
NO_FAULT = "no-fault-calibration"
FRONTEND = "frontend-pause-effect"
FRAUD = "fraud-pause-effect"
ACCOUNTING = "accounting-pause-effect"
NOLAG_DESCRIPTOR_SHA256 = "a65f4e33ae7698cfc6bd43829857bfda02030af546e712a471687031f1ca4dd8"
NOLAG_PLAN1_SHA256 = "858bbcd3634a48c30af55546308d181ebed6daf9af29161f1b5cf760e263026e"
F_DESCRIPTOR_SHA256 = "6164052dc62c323be37c286afd0f41a90808bbd251f62d56eb959eec01233b7e"
F_PLAN1_SHA256 = "30aa2484fa1aa42c0f9bedbc3b98123dd8a3290a417237d0bb07fb93ae28b5bd"
# Materialized-source digests (.source.sha256): F's and E's measured with the F worktree's materialize.py at 715d57b and again with this tree's
# (byte-identical trees, `diff -r` empty); the ablation's measured at its build.
F_SOURCE_DIGEST = "b27445b2e78dbe098a7f7d2ceb56f6e691dc7171c420fef6565f3c5f8d451234"
E_SOURCE_DIGEST = "850de25ffc100191a5f98ebfa6d041e13ece9c956ab11385458a1b4f39e5b441"
NOLAG_SOURCE_DIGEST = "28ffe6d799224ce080734dfaa27134c40e3feb3de217a19625b9cfdfa18213f8"
CONTROLLER_KEYS = {
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


f_tests = load("otel_offpath_f_nolag_f_tests", ROOT / "tests/test_otel_offpath_f.py")        # F's compiler and every helper F's tests use
f = f_tests.p
e = f_tests.e
v1 = f_tests.v1
b_tests = f_tests.b_tests
helpers = f_tests.helpers
e_tests = f_tests.e_tests
NOW = helpers.NOW
p = load("otel_offpath_f_nolag_compiler_test", SOURCE)
yaml = pytest.importorskip("yaml")


def _exec(text: str):
    module = types.ModuleType("otel_offpath_f_nolag_variant")
    module.__file__ = str(SOURCE)
    exec(compile(text, str(SOURCE), "exec"), module.__dict__)
    return module


def _planted(old: str, new: str):
    """The ablation's compiler with exactly one source edit, as a fresh module."""
    text = SOURCE.read_text()
    assert text.count(old) == 1, old
    return _exec(text.replace(old, new))


def _plan(attempt: int = 1):
    return p.compile_plan(p.load_descriptor(), attempt)


def _cells(plan=None):
    return p.flatten_cells(plan or _plan())


def _tree(tmp_path_factory, label: str, epoch: str = EPOCH, compiler: str = "candidate_offpath_f_nolag.py"):
    root = helpers._copy_tree(tmp_path_factory.mktemp(label), selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n")
    module = root / "modules/otel-demo"
    loaded = types.SimpleNamespace(root=root, epoch=epoch)
    loaded.runtime = load(f"otel_{label}_runtime", module / "execution/candidate_runtime.py")
    loaded.remote = load(f"otel_{label}_remote", module / "execution/candidate_remote.py")
    loaded.setup = load(f"otel_{label}_setup", module / "execution/candidate_setup.py")
    loaded.terminal = load(f"otel_{label}_terminal", module / "validation/candidate_terminal.py")
    loaded.compiler = load(f"otel_{label}_compiler", module / "execution" / compiler)
    return loaded


@pytest.fixture(scope="module")
def nolag_tree(tmp_path_factory):
    return _tree(tmp_path_factory, "offpath-nolag-tree")


@pytest.fixture(scope="module")
def nolag_package(nolag_tree, tmp_path_factory):
    return helpers._package(nolag_tree.runtime, nolag_tree.compiler, tmp_path_factory.mktemp("offpath-nolag-package"), window_hours=5)


@pytest.fixture(scope="module")
def materialized(tmp_path_factory):
    out = {}
    for label, epoch in (("nolag", EPOCH), ("f", F_EPOCH), ("e", E_EPOCH), ("v2", e_tests.V2), ("c", e_tests.C)):
        tree = helpers._copy_tree(tmp_path_factory.mktemp("materialize-nolag-" + label),
                                  selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n")
        out[label] = tree / "out"
        out[label + "-digest"] = b_tests._materialize(tree, out[label])
    return out


# ------------------------------------------------------------------------------------- 1. the plan, its pins, F and E untouched
def test_the_ablation_is_pinned_25_cells_in_5_blocks_two_no_fault_cells_per_block_and_the_split_is_in_the_descriptor():
    document = p.load_descriptor()
    plan = _plan()
    assert p.canonical_sha256(document) == NOLAG_DESCRIPTOR_SHA256 == p.EXPECTED_DESCRIPTOR_SHA256
    assert p.canonical_sha256(plan) == NOLAG_PLAN1_SHA256
    assert (p.TOTAL_RUNS, p.CELLS_PER_BLOCK, p.BLOCKS, p.RATE) == (25, 5, 5, 25.0) and plan["runCount"] == plan["uniqueRunCount"] == 25
    assert (p.MINIMUM_REMAINING_SECONDS, p.RUN_WINDOW_HOURS) == (14275, 5)
    assert p.SCHEDULE_SEED == 20261015 and document["schedule"]["seed"] == 20261015
    assert (p.MINIMUM_REMAINING_SECONDS, p.RUN_WINDOW_HOURS, p.TOTAL_RUNS) == (f.MINIMUM_REMAINING_SECONDS, f.RUN_WINDOW_HOURS, f.TOTAL_RUNS)
    cells = _cells(plan)
    assert sorted(cell["runKey"]["regime"] for cell in cells) == sorted([NO_FAULT] * 10 + [FRAUD] * 5 + [ACCOUNTING] * 5 + [FRONTEND] * 5)
    for block in plan["blocks"]:
        assert [c["runKey"]["regime"] for c in block["cells"][:2]] == [NO_FAULT, NO_FAULT]
        assert sorted(c["runKey"]["replicate"] for c in block["cells"][:2]) == [1, 2]
        assert block["cells"][-1]["runKey"]["regime"] == FRONTEND
        assert block["split"] == ("training" if block["block"] in (1, 2, 3) else "test")
    assert document["design"]["split"] == p.split_record() == document["analysis"]["split"] == document["schedule"]["split"]
    assert document["design"]["episodesPerRegimeAndRate"] == {NO_FAULT: 10, FRAUD: 5, ACCOUNTING: 5, FRONTEND: 5}
    assert [r["id"] for r in document["design"]["regimes"]] == [NO_FAULT, FRAUD, ACCOUNTING, FRONTEND]


def test_planted_defect_an_edited_descriptor_or_plan_or_parameter_is_refused():
    document = p.load_descriptor()
    edited = copy.deepcopy(document)
    edited["collection"]["telemetryCadence"]["kafkametrics"] = copy.deepcopy(f.KAFKAMETRICS)
    with pytest.raises(p.ProtocolError, match="differs from its generator"):
        p.validate_descriptor(edited)
    edited = copy.deepcopy(document)
    edited["design"]["ablation"]["removed"] = []
    with pytest.raises(p.ProtocolError, match="differs from its generator"):
        p.validate_descriptor(edited)
    broken = copy.deepcopy(_plan())
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
    module = _planted(NOLAG_DESCRIPTOR_SHA256, "0" * 64)
    with pytest.raises(module.ProtocolError, match="reviewed pin"):
        module.load_descriptor()


def test_the_descriptor_file_is_the_generators_output_and_the_digests_are_identical_under_python39_isolated():
    assert (ROOT / "pipelines/campaigns/otel-offpath-f-nolag-v1.json").read_bytes() == p._pretty_bytes(p.derive_f_descriptor())
    result = subprocess.run(["/usr/bin/python3", "-I", str(SOURCE), "--print-digests"], capture_output=True, text=True, check=True)
    digests = json.loads(result.stdout)
    assert digests["descriptorCanonicalSha256"] == NOLAG_DESCRIPTOR_SHA256 and digests["planCanonicalSha256"] == NOLAG_PLAN1_SHA256
    assert (digests["runCount"], digests["runWindowHours"]) == (25, 5)


def test_f_and_e_are_untouched_their_pins_their_epochs_and_their_run_ids_and_the_ablation_shares_none_of_them():
    assert f.canonical_sha256(f.load_descriptor()) == F_DESCRIPTOR_SHA256 == p.DESIGN_DESCRIPTOR_SHA256
    assert f.canonical_sha256(f.compile_plan(f.load_descriptor(), 1)) == F_PLAN1_SHA256
    assert f.EPOCH == F_EPOCH == p.DESIGN_EPOCH != p.EPOCH and f.TOTAL_RUNS == 25
    assert e.canonical_sha256(e.load_descriptor()) == p.BASE_DESIGN_DESCRIPTOR_SHA256 == f.DESIGN_DESCRIPTOR_SHA256
    assert p.load_descriptor()["derivedFrom"]["designSource"] == {
        "studyEpoch": F_EPOCH, "descriptorCanonicalSha256": F_DESCRIPTOR_SHA256,
        "note": "campaign F's descriptor (25 req/s, all three faults, two no-fault cells per block), pinned by digest; this generator does not read F's descriptor or compiler",
        "baseDesignSource": {"studyEpoch": E_EPOCH, "descriptorCanonicalSha256": f_tests.E_DESCRIPTOR_SHA256},
    }
    ran = e_tests._ran_run_ids()
    others = {}
    for attempt in (1, 2, 3):
        others[(E_EPOCH, attempt)] = {c["runId"] for c in e.flatten_cells(e.compile_plan(e.load_descriptor(), attempt))}
        others[(F_EPOCH, attempt)] = {c["runId"] for c in f.flatten_cells(f.compile_plan(f.load_descriptor(), attempt))}
    for attempt in (1, 2, 3):
        ids = {cell["runId"] for cell in _cells(_plan(attempt))}
        assert len(ids) == 25 and v1._reused(ids, {**ran, **others}) == {}, attempt
    # planted: the ablation under F's epoch id, schedule version and seed would reproduce F's run IDs, and the reuse check finds them (it is not trivially true)
    clash = _planted('EPOCH = "otel-offpath-f-nolag-v1"\n', 'EPOCH = "otel-offpath-f-v1"\n')
    ids = {c["runId"] for c in clash.flatten_cells(clash._compile(clash.derive_f_descriptor(), 1))}
    assert len(ids) == 25 and v1._reused(ids, {k: v for k, v in others.items() if k[0] == F_EPOCH}) != {}


def test_the_ablation_is_f_apart_from_the_declared_keys_and_the_declared_keys_differ_by_the_kafka_rows_the_ablation_record_and_the_names():
    n_doc, f_doc = p.load_descriptor(), f.load_descriptor()
    assert p.MIX == f.MIX and p.canonical_json_bytes(p.MIX) == f.canonical_json_bytes(f.MIX)
    assert n_doc["faultDesign"]["scenarios"] == f_doc["faultDesign"]["scenarios"]
    assert p.MANIFESTATION_CRITERION == f.MANIFESTATION_CRITERION
    assert {k: v for k, v in p.MANIFESTATION_CRITERION_DEFAULTS.items() if k != "unit"} == {
        k: v for k, v in f.MANIFESTATION_CRITERION_DEFAULTS.items() if k != "unit"}
    assert (p.CONCURRENCY, p.GENERATOR_OPEN_FILES_MINIMUM, p.FRONTENDPROXY_MEMORY_LIMIT_BYTES, p.SERVICE_MEMORY_LIMIT_BYTES) == (
        f.CONCURRENCY, f.GENERATOR_OPEN_FILES_MINIMUM, f.FRONTENDPROXY_MEMORY_LIMIT_BYTES, f.SERVICE_MEMORY_LIMIT_BYTES)
    assert (p.SDK_COVERAGE, p.SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS, p.SPANMETRICS_FLUSH_INTERVAL) == (
        f.SDK_COVERAGE, f.SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS, f.SPANMETRICS_FLUSH_INTERVAL)
    assert n_doc["workload"] == f_doc["workload"]
    # every key of every cell's timing other than the onset keys is F's cell of the same regime, block and replicate
    skip = p.ONSET_TIMING_KEYS
    for cell in _cells():
        key = cell["runKey"]
        twin = f.cell_timing(key["regime"], 25.0, key["block"], key["replicate"])
        assert {k: v for k, v in cell["timing"].items() if k not in skip} == {k: v for k, v in twin.items() if k not in skip}
    top = {k for k in n_doc if n_doc[k] != f_doc[k]}
    assert top == {"id", "declaration", "design", "schedule", "timing", "collection", "outcomes", "sutDeviations", "analysis", "derivedFrom"}
    assert n_doc["faultDesign"] == f_doc["faultDesign"]
    # timing differs by the wording of one note (it adds that the cadence is F's too) and by no number
    assert {k for k in n_doc["timing"] if n_doc["timing"][k] != f_doc["timing"][k]} == {"metricExportIntervalNote"}
    head = "; an emission change relative to campaigns B, C, the pilots and E"
    assert n_doc["timing"]["metricExportIntervalNote"].split(head)[0] == f_doc["timing"]["metricExportIntervalNote"].split(head)[0]
    # the telemetry cadence differs by the kafka entries only
    n_cadence, f_cadence = n_doc["collection"]["telemetryCadence"], f_doc["collection"]["telemetryCadence"]
    kafka_keys = {"kafkametrics", "kafkametricsImage", "kafkametricsMetrics", "collectorStartOrder", "kafkametricsNote"}
    assert {k for k in set(n_cadence) | set(f_cadence) if n_cadence.get(k) != f_cadence.get(k)} == kafka_keys
    assert n_cadence["kafkametrics"] is None and f_cadence["kafkametrics"]["receiver"] == "kafkametrics"
    assert {k: v for k, v in n_cadence.items() if k not in kafka_keys} == {k: v for k, v in f_cadence.items() if k not in kafka_keys}
    # the SUT deviations differ by F's kafka row (absent here) and the scope wording of the rows that name the campaign
    def keyed(rows):
        return {(row["service"], row["setting"]): row for row in rows}
    n_rows, f_rows = keyed(n_doc["sutDeviations"]), keyed(f_doc["sutDeviations"])
    assert set(f_rows) - set(n_rows) == {("otelcol", "receivers.kafkametrics, processors.resource/kafka, pipelines.metrics/kafka, depends_on kafka (service_healthy)")}
    assert set(n_rows) <= set(f_rows)
    for name, row in n_rows.items():
        assert {k: v for k, v in row.items() if k not in ("scope", "reason")} == {k: v for k, v in f_rows[name].items() if k not in ("scope", "reason")}, name
    assert not any("kafkametrics" in json.dumps(row) for row in n_rows.values())
    # the ablation record names exactly the four removed pieces and what is kept
    ablation = n_doc["design"]["ablation"]
    assert ablation["designEpoch"] == F_EPOCH and ablation["designDescriptorCanonicalSha256"] == F_DESCRIPTOR_SHA256
    assert len(ablation["removed"]) == 4 and any("kafkametrics" in x for x in ablation["removed"]) and any("depends_on kafka" in x for x in ablation["removed"])
    assert "ablation" not in f_doc["design"]


# ------------------------------------------------------------------------------------- 2. the run order and the onsets
def test_every_block_runs_the_two_no_fault_cells_then_the_off_path_pauses_in_the_seeded_order_then_the_frontend_pause():
    seen = set()
    for block in range(1, 6):
        order = p.block_order(block)
        regimes = [row["regime"] for row in order]
        assert regimes[:2] == [NO_FAULT] * 2 and regimes[-1] == FRONTEND and set(regimes[2:4]) == {FRAUD, ACCOUNTING}
        assert sorted(row["replicate"] for row in order[:2]) == [1, 2]
        seen.add(tuple(regimes[2:4]))
    assert len(seen) == 2


def test_each_no_fault_replicate_takes_the_five_onset_strata_once_over_the_blocks_and_the_draws_are_new_not_fs():
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
        assert offsets != [f.onset_phase_offset(regime, 25.0, block) for block in range(1, 6)]       # the epoch id and the seed are in the draw
    assert by_replicate[1] != [f.onset_phase_offset(NO_FAULT, 25.0, b, 1) for b in range(1, 6)]
    assert p.SCHEDULE_CONTEXT != f.SCHEDULE_CONTEXT
    with pytest.raises(p.ProtocolError):
        p.onset_phase_offset(NO_FAULT, 25.0, 1, 3)
    with pytest.raises(p.ProtocolError):
        p.onset_phase_offset(FRAUD, 25.0, 1, 2)
    module = _planted(
        '''label = regime if int(replicate) == 1 else "%s#replicate-%d" % (regime, int(replicate))''', "label = regime")
    assert [module.onset_phase_offset(NO_FAULT, 25.0, b, 2) for b in range(1, 6)] == by_replicate[1] != by_replicate[2]


@pytest.mark.parametrize("old,new", [
    ("(FRONTEND_PAUSE_REGIME,),\n)", "(FRONTEND_PAUSE_REGIME,),\n    (NO_FAULT_REGIME,),\n)"),
    ("ORDER_GROUPS = (\n    (NO_FAULT_REGIME,),\n    (FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME),\n    (FRONTEND_PAUSE_REGIME,),\n)",
     "ORDER_GROUPS = (\n    (FRAUD_PAUSE_REGIME, ACCOUNTING_PAUSE_REGIME),\n    (NO_FAULT_REGIME,),\n    (FRONTEND_PAUSE_REGIME,),\n)"),
])
def test_planted_defect_a_block_order_other_than_nofault_offpath_frontend_is_refused_by_the_rule(old, new):
    module = _planted(old, new)
    with pytest.raises(module.ProtocolError):
        module.compile_plan(module.derive_f_descriptor(), 1)


# ------------------------------------------------------------------------------------- 3. the cadence kept, the lag receiver removed (descriptor)
def test_the_descriptor_keeps_the_5_second_interval_and_flush_and_declares_no_kafkametrics_receiver():
    document = p.load_descriptor()
    cadence = document["collection"]["telemetryCadence"]
    assert document["timing"]["metricExportIntervalMilliseconds"] == 5000 == document["faultDesign"]["metricExportIntervalMilliseconds"]
    assert cadence["sdkMetricExportIntervalMilliseconds"] == 5000 and cadence["spanmetricsFlushInterval"] == "5s"
    assert cadence["kafkametrics"] is None and "not rendered in this epoch" in cadence["kafkametricsNote"]
    assert "depends_on" in cadence["collectorStartOrder"] and "does not wait for kafka" in cadence["collectorStartOrder"]
    assert "kafkametricsImage" not in cadence and "kafkametricsMetrics" not in cadence
    assert f_tests._coverage_problems(cadence["sdkCoverage"], json.loads((MODULE / "postures/catalog.json").read_text())["applicationServices"]) == []
    # the lag lane is named as having no signal, and the pass rule and per-lane text are the declaration's
    assert "no kafkametrics signal" in document["outcomes"]["primary"]
    assert "DECLARATION_F_NOLAG_OTEL.md" in document["declaration"] and "BUDGET_OVERNIGHT_20261014.md item 2" in document["derivedFrom"]["authority"]
    # planted: a generator that still emits F's receiver record is not this epoch's descriptor
    module = _planted('        "kafkametrics": None,\n', '        "kafkametrics": {"receiver": "kafkametrics"},\n')
    with pytest.raises(module.ProtocolError, match="differs from its generator"):
        module.validate_descriptor(p.load_descriptor())
    module = _planted("SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS = 5000 ", "SDK_METRIC_EXPORT_INTERVAL_MILLISECONDS = None ")
    with pytest.raises(module.ProtocolError, match="differs from its generator"):
        module.validate_descriptor(p.load_descriptor())


# ------------------------------------------------------------------------------------- 4. the rendered tree
def _services(path: Path) -> dict:
    return yaml.safe_load(path.read_text())["services"]


def _config(out: Path) -> dict:
    return yaml.safe_load(b_tests._collector_config(out))


def test_the_collector_config_is_fs_without_the_kafkametrics_receiver_its_processor_its_pipeline_and_nothing_else(materialized):
    n_config, f_config, e_config = _config(materialized["nolag"]), _config(materialized["f"]), _config(materialized["e"])
    assert n_config["connectors"]["spanmetrics"] == {"metrics_flush_interval": "5s"}
    assert "kafkametrics" not in n_config["receivers"] and "resource/kafka" not in n_config["processors"]
    assert "metrics/kafka" not in n_config["service"]["pipelines"]
    assert "kafkametrics" not in (materialized["nolag"] / "src/otelcollector/otelcol-placement.yml").read_text()
    assert "resource/kafka" not in (materialized["nolag"] / "src/otelcollector/otelcol-placement.yml").read_text()
    assert n_config["service"]["telemetry"]["logs"]["sampling"]["enabled"] is False
    # F's config minus the three pieces is the ablation's config, as data and as text
    stripped = copy.deepcopy(f_config)
    del stripped["receivers"]["kafkametrics"], stripped["processors"]["resource/kafka"], stripped["service"]["pipelines"]["metrics/kafka"]
    assert stripped == n_config
    assert n_config != e_config and {k: v for k, v in n_config["connectors"].items() if k != "spanmetrics"} == {
        k: v for k, v in e_config["connectors"].items() if k != "spanmetrics"}
    f_text = (materialized["f"] / "src/otelcollector/otelcol-placement.yml").read_text()
    n_text = (materialized["nolag"] / "src/otelcollector/otelcol-placement.yml").read_text()
    mat = load("otel_offpath_f_nolag_materialize_text", MODULE / "materialize.py")
    for piece in (mat.KAFKAMETRICS_RECEIVER, mat.KAFKAMETRICS_PROCESSOR, mat.KAFKAMETRICS_PIPELINE):
        assert f_text.count(piece) == 1 and n_text.count(piece) == 0
        f_text = f_text.replace(piece, "")
    assert f_text == n_text                                  # F's text minus the three rendered pieces is the ablation's text, byte for byte
    # every component a pipeline names is defined
    defined = {"receivers": set(n_config["receivers"]) | set(n_config["connectors"]), "processors": set(n_config["processors"]),
               "exporters": set(n_config["exporters"]) | set(n_config["connectors"])}
    for name, pipeline in n_config["service"]["pipelines"].items():
        for kind in ("receivers", "processors", "exporters"):
            assert set(pipeline.get(kind, [])) <= defined[kind], (name, kind)


def test_the_posture_overlay_of_the_ablation_is_fs_byte_for_byte_and_otelcol_does_not_wait_for_kafka(materialized):
    assert (materialized["nolag"] / "compose.candidate-postures.yml").read_bytes() == (materialized["f"] / "compose.candidate-postures.yml").read_bytes()
    services = _services(materialized["nolag"] / "compose.candidate-postures.yml")
    catalog = json.loads((MODULE / "postures/catalog.json").read_text())
    bound = sorted(s for s, row in services.items() if "OTEL_METRIC_EXPORT_INTERVAL" in row.get("environment", {}))
    assert bound == sorted(set(catalog["applicationServices"]) - {"frontendproxy"}) and len(bound) == 18
    n_overlay = yaml.safe_load((materialized["nolag"] / "compose.otel-placement.yml").read_text())["services"]
    f_overlay = yaml.safe_load((materialized["f"] / "compose.otel-placement.yml").read_text())["services"]
    assert "depends_on" not in n_overlay["otelcol"] and f_overlay["otelcol"]["depends_on"] == {"kafka": {"condition": "service_healthy"}}
    assert n_overlay == {k: v for k, v in f_overlay.items() if k != "otelcol"} | {"otelcol": {k: v for k, v in f_overlay["otelcol"].items() if k != "depends_on"}}
    # the ablation's compose overlay is E's byte for byte (the pilots' frontendproxy retention, nothing for otelcol)
    assert (materialized["nolag"] / "compose.otel-placement.yml").read_bytes() == (materialized["e"] / "compose.otel-placement.yml").read_bytes()


def test_f_and_e_render_exactly_as_at_715d57b_and_the_ablation_has_its_own_source_digest(materialized):
    assert materialized["f-digest"] == F_SOURCE_DIGEST and materialized["e-digest"] == E_SOURCE_DIGEST
    assert materialized["nolag-digest"] == NOLAG_SOURCE_DIGEST
    assert len({materialized[k + "-digest"] for k in ("nolag", "f", "e", "c")}) == 4
    materialize = load("otel_offpath_f_nolag_materialize_module", MODULE / "materialize.py")
    assert EPOCH in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS and EPOCH in materialize.FRONTENDPROXY_LOG_RETENTION_EPOCHS
    assert EPOCH in materialize.TELEMETRY_CADENCE_EPOCHS and EPOCH in materialize.METRIC_EXPORT_INTERVAL_EPOCHS
    assert EPOCH not in materialize.KAFKAMETRICS_EPOCHS and materialize.KAFKAMETRICS_EPOCHS == (F_EPOCH,)
    text = (MODULE / "deployment/compose.candidate-postures.yml").read_text()
    for epoch in (None, E_EPOCH, e_tests.V2, e_tests.C):
        assert materialize.render_posture_overlay(text, epoch) == text and materialize.render_collector_config("anything", epoch) == "anything"


@pytest.mark.parametrize("old,new,probe", [
    ('"otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1", "otel-offpath-f-nolag-v1")\nCOLLECTOR_LOG_SAMPLING_OFF =',
     '"otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")\nCOLLECTOR_LOG_SAMPLING_OFF =', "sampler"),
    ('TELEMETRY_CADENCE_EPOCHS = ("otel-offpath-f-v1", "otel-offpath-f-nolag-v1")', 'TELEMETRY_CADENCE_EPOCHS = ("otel-offpath-f-v1",)', "flush"),
    ('KAFKAMETRICS_EPOCHS = ("otel-offpath-f-v1",)', 'KAFKAMETRICS_EPOCHS = ("otel-offpath-f-v1", "otel-offpath-f-nolag-v1")', "kafka"),
    ('SPANMETRICS_FLUSH_INTERVAL = "5s"', 'SPANMETRICS_FLUSH_INTERVAL = "60s"', "flush60"),
    ('METRIC_EXPORT_INTERVAL_EPOCHS = TELEMETRY_CADENCE_EPOCHS', "METRIC_EXPORT_INTERVAL_EPOCHS = (\"otel-offpath-f-v1\",)", "interval"),
])
def test_planted_defect_in_the_rendering_of_the_ablation_is_seen_by_the_rendered_tree_checks(old, new, probe, tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    assert text.count(old) == 1, old
    script.write_text(text.replace(old, new))
    out = tree / "out"
    b_tests._materialize(tree, out)
    config = _config(out)
    overlay = _services(out / "compose.candidate-postures.yml")
    if probe == "sampler":
        assert b_tests._log_sampling_enabled(b_tests._collector_config(out)) is None
    elif probe == "flush":
        assert config["connectors"]["spanmetrics"] is None
    elif probe == "kafka":
        assert "kafkametrics" in config["receivers"] and "metrics/kafka" in config["service"]["pipelines"]
        assert yaml.safe_load((out / "compose.otel-placement.yml").read_text())["services"]["otelcol"]["depends_on"]
    elif probe == "flush60":
        assert config["connectors"]["spanmetrics"] == {"metrics_flush_interval": "60s"}
    else:
        assert all("OTEL_METRIC_EXPORT_INTERVAL" not in row.get("environment", {}) for row in overlay.values())


@pytest.mark.skipif(not os.environ.get("OTELCOL_CONTRIB"), reason="set OTELCOL_CONTRIB to an otelcol-contrib 0.108.x binary to validate the rendered config")
def test_the_official_collector_validates_the_rendered_config_and_refuses_a_planted_undefined_processor(materialized, tmp_path):
    binary = os.environ["OTELCOL_CONTRIB"]
    rendered = (materialized["nolag"] / "src/otelcollector/otelcol-placement.yml").read_text()
    assert rendered.count("root_path") == 1                   # the one Linux-only line (hostfs mount), dropped in the scratch copy only
    scratch = tmp_path / "otelcol.yml"
    scratch.write_text("".join(line for line in rendered.splitlines(keepends=True) if "root_path" not in line))
    ok = subprocess.run([binary, "validate", "--config=" + str(scratch)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    scratch.write_text(scratch.read_text().replace("processors: [batch]", "processors: [resource/kafka, batch]", 1))
    bad = subprocess.run([binary, "validate", "--config=" + str(scratch)], capture_output=True, text=True)
    assert bad.returncode != 0 and "resource/kafka" in bad.stderr


# ------------------------------------------------------------------------------------- 5. the plan and install environments
def _referenced(overlay_text: str) -> set:
    return set(re.findall(r"\$\{(OTEL_CANDIDATE_[A-Z0-9_]+):?\?", overlay_text))


def test_the_plan_and_install_environments_carry_the_interval_as_fs_do_and_the_runtime_and_the_materializer_agree(nolag_tree, materialized, tmp_path_factory, tmp_path):
    runtime = nolag_tree.runtime
    runtime.verify_materializer_constants()
    assert runtime.METRIC_EXPORT_INTERVAL_STUDY_EPOCHS == (F_EPOCH, EPOCH) and runtime.METRIC_EXPORT_INTERVAL_MILLISECONDS == "5000"
    e_tree = _tree(tmp_path_factory, "offpath-nolag-checks-e", E_EPOCH, "candidate_offpath_e.py")
    assert e_tree.runtime.STUDY_EPOCH == E_EPOCH and runtime.STUDY_EPOCH == EPOCH
    referenced = _referenced((materialized["nolag"] / "compose.candidate-postures.yml").read_text())
    for posture in ("none", "selected", "async", "full"):
        env = runtime.posture_environment(posture, "/bound/source")
        assert env["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == "5000" and referenced <= set(env), posture
        assert "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL" not in e_tree.runtime.posture_environment(posture, "/bound/source")
    source = materialized["nolag"]
    installed = nolag_tree.setup.compose_environment(source, "f" * 64)
    full = runtime.posture_environment("full", str(source))
    assert installed["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == full["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == "5000"
    for key, value in full.items():
        assert installed[key] == value, key
    # planted: an environment without the variable leaves the rendered overlay's reference unbound
    missing = {k: v for k, v in full.items() if k != "OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"}
    assert referenced - set(missing) == {"OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"}
    # planted: a materializer that names another variable is refused by the runtime's comparison
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    marker = 'METRIC_EXPORT_INTERVAL_EPOCHS = TELEMETRY_CADENCE_EPOCHS'
    text = script.read_text()
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, 'METRIC_EXPORT_INTERVAL_EPOCHS = ("otel-offpath-f-v1",)'))
    planted = load("otel_offpath_f_nolag_planted_runtime", tree / "modules/otel-demo/execution/candidate_runtime.py")
    with pytest.raises(planted.GateError, match="metric export interval"):
        planted.verify_materializer_constants()


# ------------------------------------------------------------------------------------- 6. the epoch in the runtime and the gate chain
def test_a_selector_naming_the_ablation_activates_it_in_every_reader_and_the_gate_chain_derives_25_cells(nolag_tree, nolag_package, tmp_path):
    runtime, remote = nolag_tree.runtime, nolag_tree.remote
    assert runtime.STUDY_EPOCH == EPOCH and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (25, 14275, 5)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_offpath_f_nolag.py"
    assert runtime.DESCRIPTOR == nolag_tree.root / "pipelines/campaigns/otel-offpath-f-nolag-v1.json"
    assert nolag_tree.setup.controller_paths(EPOCH) == runtime.CONTROLLER_PATHS
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {
        "duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}
    assert EPOCH in remote.REPEAT_STUDY_EPOCHS and EPOCH in remote.TIMED_STUDY_EPOCHS and F_EPOCH in remote.REPEAT_STUDY_EPOCHS
    binding = nolag_package.gate_plan["binding"]
    assert f"study={EPOCH} " in nolag_package.gate_plan["typedApproval"] and " runs=25 " in nolag_package.gate_plan["typedApproval"]
    assert nolag_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 14275
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_offpath_f_nolag_v1" and remote.SAFE_NAME.fullmatch(binding["compose"]["project"])
    earlier = (e_tests.SWEEP, e_tests.QUIET, e_tests.REPEAT, e_tests.C, e_tests.LOAD, e_tests.V1, e_tests.V2, E_EPOCH, F_EPOCH)
    other = (["/home/stig/observability-placement-candidate-v4-runs/" + x for x in earlier]
             + ["/home/stig/observability-placement-candidate-v4-runs/.setup-" + x for x in earlier]
             + ["/home/stig/observability-placement-candidate-v4-otel-srv6/" + x + "-" for x in earlier])
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert EPOCH in binding[key] and not any(binding[key].startswith(path) for path in other), key
    document = runtime.execution_package(nolag_package)
    assert document["runCount"] == 25 and len(document["cells"]) == 25
    for contract, cell in zip(document["cells"], nolag_package.bindings.cells):
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
        adapter = load("otel_offpath_f_nolag_tree_adapter", nolag_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == EPOCH and adapter.SPENT_ATTEMPTS == {}
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 25 and bindings.plan_sha256 == NOLAG_PLAN1_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_planted_defect_a_selector_naming_the_ablation_without_its_controller_set_is_refused(tmp_path_factory):
    root = helpers._copy_tree(tmp_path_factory.mktemp("offpath-nolag-no-paths"), selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    runtime_path = root / "modules/otel-demo/execution/candidate_runtime.py"
    text = runtime_path.read_text()
    marker = '    OFFPATH_F_NOLAG_STUDY_EPOCH: {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_f_nolag.py",'
    assert text.count(marker) == 1
    runtime_path.write_text(text.replace(marker, '    "otel-offpath-f-nolag-v0": {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_f_nolag.py",'))
    with pytest.raises(Exception, match="names no declared non-frozen epoch"):
        load("otel_offpath_f_nolag_no_paths_runtime", runtime_path)


def test_the_ablation_has_spent_nothing_and_e_attempt_1_is_recorded_spent_in_the_adapter():
    table = v1._spent_table_in_source()
    assert table[EPOCH] == {} and set(table[E_EPOCH]) == {1}


# ------------------------------------------------------------------------------------- 7. the activation in this worktree
def test_the_ablation_is_activated_the_selector_and_the_tombstone_name_it_and_f_and_e_are_not_named():
    selector = json.loads((MODULE / "execution/study-epoch.json").read_text())
    assert selector == {"schemaVersion": 1, "studyEpoch": EPOCH}
    for name in ("candidate_remote.py", "candidate_setup.py"):
        tree_ = ast.parse((MODULE / "execution" / name).read_text())
        values = [ast.literal_eval(n.value) for n in tree_.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "ADMITTED_STUDY_EPOCHS"]
        assert values == [(EPOCH,)], name
    text = (MODULE / "execution/study-epoch.json").read_text()
    assert F_EPOCH not in text and E_EPOCH not in text and e_tests.V2 not in text


def test_the_committed_tree_selects_the_ablation_in_the_runtime_the_adapter_and_the_materializer():
    runtime = load("otel_offpath_f_nolag_committed_runtime", MODULE / "execution/candidate_runtime.py")
    assert runtime.STUDY_EPOCH == EPOCH and (runtime.RUN_COUNT, runtime.RUN_WINDOW_HOURS) == (25, 5)
    materialize = load("otel_offpath_f_nolag_committed_materialize", MODULE / "materialize.py")
    assert materialize.selected_study_epoch() == EPOCH
    assert runtime.posture_environment("full", "/s")["OTEL_CANDIDATE_METRIC_EXPORT_INTERVAL"] == "5000"
    runtime.verify_materializer_constants()


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
def cells(nolag_tree, nolag_package, tmp_path_factory):
    out = {}
    plan = _plan()
    for regime, block, replicate in CELL_KEYS:
        with pytest.MonkeyPatch.context() as patch:
            base = tmp_path_factory.mktemp(f"offpath-nolag-cell-{regime}-{block}-{replicate}")
            contract = _contract(nolag_tree, nolag_package, _run_id(plan, regime, block, replicate), base)
            assert contract["studyEpoch"] == EPOCH
            receipt, target, limits = v1._run(nolag_tree, contract, patch, pool_cap=256)
            assert receipt["state"] == "valid", (regime, block, replicate, receipt["error"])
            out[(regime, block, replicate)] = types.SimpleNamespace(contract=contract, root=Path(contract["remoteArtifactRoot"]), target=target)
    return out


@pytest.mark.parametrize("key", CELL_KEYS)
def test_run_cell_executes_an_ablation_cell_and_the_terminal_accepts_it(nolag_tree, cells, key):
    cell = cells[key]
    contract, root = cell.contract, cell.root
    regime, block, replicate = key
    assert contract["runKey"]["replicate"] == replicate and contract["runKey"]["block"] == block
    assert contract["timing"]["faultOnsetSeconds"] == p.cell_timing(regime, 25.0, block, replicate)["faultOnsetSeconds"]
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    ledger = json.loads((root / "request-ledger.json").read_text())
    assert ledger["offered"] == 4500 == len(ledger["requests"])
    report = v1._validate(nolag_tree, root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True


# ------------------------------------------------------------------------------------- 9. the 3.9 floor
TARGET_FILES = (
    "modules/otel-demo/execution/candidate_offpath_f_nolag.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/execution/candidate_runtime_adapter.py",
    "modules/otel-demo/materialize.py",
)


@pytest.mark.parametrize("relative", TARGET_FILES)
def test_touched_target_files_parse_as_python39_and_read_no_name_bound_nowhere(relative):
    tree_ = ast.parse((ROOT / relative).read_text(), feature_version=(3, 9))
    assert b_tests._unbound_names(tree_) == []
    assert any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names) for n in tree_.body)
    result = subprocess.run(["/usr/bin/python3", "-I", "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())", str(ROOT / relative)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_a_planted_name_bound_nowhere_in_the_ablation_compiler_is_found_by_the_scan():
    text = SOURCE.read_text()
    planted = text.replace('    label = regime if int(replicate) == 1', '    label = regime if int(replicate) == unbound_replicate_name')
    assert planted != text
    assert b_tests._unbound_names(ast.parse(planted, feature_version=(3, 9))) != []
