"""otel-offpath-pilot-v1: the OTel off-path manifestation pilot (main repo research/traffic-sweep/BUDGET_E.md, user decisions
2026-10-12).

Campaign C's cell at 100 and 150 req/s of the upstream Locust task mix (an open loop with one ledger row per request carrying
its route), five regimes (no fault, frontend pause, productcatalogservice throttle, frauddetectionservice pause,
accountingservice pause), one cell per regime and rate, rate-ascending segments.  Covers, each with a planted defect: the plan
pin (descriptor and attempt-1 plan digests, 3.9/3.13 identity); C-identity (every cell timing is C's at the same regime and
rate apart from the declared keys, and the descriptor is C's apart from the declared keys); the mix (upstream's tasks and
weights, shares, determinism, journeys and their dependencies, per-route required services); the generator sizing at 150 req/s
(concurrency, open files, frontendproxy memory) and its enforcement on the target; the run order; no run-ID reuse; the epoch in
the runtime, the gate chain, the target runner and the terminal (every regime end to end on the fake target, including the
consumers' spans, the per-route trace-completeness rule and the terminal's replay of every ledger row against the plan); the
manifestation criteria computed from what a cell retains (otelcol.log spans, ledger rows with route, intervention.json); the
collector log sampler off and frontendproxy's access-log retention in the pilot's rendered tree only.

Like the other epochs' tests, the pilot is exercised in a copy of the module tree with its own selector, so these tests pass
whichever epoch the worktree's committed selector names.
"""
from __future__ import annotations

import ast
import collections
import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time as real_time
import types
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
PILOT = "otel-offpath-pilot-v1"
LOAD = "otel-load-pilot-v1"
C = "otel-repeat-episodes-c-v1"
REPEAT = "otel-repeat-episodes-v1"
QUIET = "otel-quiet-calibration-v1"
SWEEP = "otel-traffic-sweep-v1"
RATES = (100.0, 150.0)
NO_FAULT = "no-fault-calibration"
FRONTEND = "frontend-pause-effect"
THROTTLE = "productcatalog-cpu-throttle-effect"
FRAUD = "fraud-pause-effect"
ACCOUNTING = "accounting-pause-effect"
REGIMES = (NO_FAULT, FRONTEND, THROTTLE, FRAUD, ACCOUNTING)
SEED = 20261013

PILOT_DESCRIPTOR_SHA256 = "2136639d30bfa33e4ea9f7f1a5a7dd1382841c9c9b5444725e58cb77ba7b557a"
PILOT_PLAN_A1_SHA256 = "8b3d7aa84e26c31de724c3686331b1f7347b9fd086a1debfefdea80799104814"
# C as frozen and run (declaration research/traffic-sweep/DECLARATION_C_OTEL.md, harness 8018a19) and the load pilot as it ran
# (harness 7b20ec4): must not move.
C_DESCRIPTOR_SHA256 = "6dd3cb7215db438cdf2f0618dd62eed583b86004f5f0254c565eabe93cc13721"
C_PLAN_A1_SHA256 = "ece8caa0552fc0bc03ef2cd51f7560e7a8c6f54e96c29755a75d37168609b744"
LOAD_DESCRIPTOR_SHA256 = "45b79b0cf552b12a111ed047803ee535aabdb6d0400d05ce108e5a119a65ac46"
LOAD_PLAN_A1_SHA256 = "aea94eb91d90d18fd41165da3af88771ea1964434c922375196478ef269d25d6"
PILOT_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor", "quiet-compiler", "repeat-compiler", "repeat-descriptor",
    "repeat-c-compiler", "repeat-c-descriptor",
}
# Attempts that ran on fb14srv6, per epoch: their run IDs exist on the host and must never be planned again.
RAN = {SWEEP: (1, 2), QUIET: (1, 2, 3), REPEAT: (1,), C: (1,), LOAD: (1,)}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("otel_offpath_pilot_compiler_test", MODULE / "execution/candidate_offpath_pilot.py")
load_pilot = load("otel_offpath_pilot_load_compiler_test", MODULE / "execution/candidate_load_pilot.py")
repeat_c = p.repeat_c
repeat = p.repeat_b
quiet = p.quiet
sweep = p.sweep
# B's test module supplies the tree copy, the fake target with the H10/H4 observables, the runner/terminal drivers and the
# materializer helpers (read, not edited); it in turn loads the sweep's test module as ``helpers``.
b_tests = load("otel_offpath_pilot_b_test_helpers", ROOT / "tests/test_otel_repeat_episodes.py")
helpers = b_tests.helpers
NOW = helpers.NOW
SCALE = helpers.SCALE


def _tree(tmp_path_factory, epoch: str, label: str):
    root = helpers._copy_tree(
        tmp_path_factory.mktemp(label), selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n",
    )
    module = root / "modules/otel-demo"
    loaded = types.SimpleNamespace(root=root, epoch=epoch)
    loaded.runtime = load(f"otel_{label}_runtime", module / "execution/candidate_runtime.py")
    loaded.remote = load(f"otel_{label}_remote", module / "execution/candidate_remote.py")
    loaded.setup = load(f"otel_{label}_setup", module / "execution/candidate_setup.py")
    loaded.terminal = load(f"otel_{label}_terminal", module / "validation/candidate_terminal.py")
    loaded.compiler = load(f"otel_{label}_compiler", module / "execution/candidate_offpath_pilot.py")
    return loaded


@pytest.fixture(scope="module")
def pilot_tree(tmp_path_factory):
    return _tree(tmp_path_factory, PILOT, "offpath-pilot-tree")


@pytest.fixture(scope="module")
def pilot_package(pilot_tree, tmp_path_factory):
    return helpers._package(pilot_tree.runtime, pilot_tree.compiler, tmp_path_factory.mktemp("offpath-pilot-package"), window_hours=4)


def _plan(attempt: int = 1):
    return p.compile_plan(p.load_descriptor(), attempt)


def _strip(timing, keys):
    return {key: value for key, value in timing.items() if key not in keys}


# ------------------------------------------------------------------------------------- 1. the plan and its pin
def test_the_plan_is_pinned_10_cells_in_two_rate_ascending_segments():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    cells = p.flatten_cells(plan)
    assert p.canonical_sha256(document) == PILOT_DESCRIPTOR_SHA256 == p.EXPECTED_DESCRIPTOR_SHA256
    assert p.canonical_sha256(plan) == PILOT_PLAN_A1_SHA256
    assert len(cells) == plan["runCount"] == plan["uniqueRunCount"] == p.TOTAL_RUNS == 10
    assert [segment["requestsPerSecond"] for segment in plan["blocks"]] == list(RATES)
    assert [cell["ordinalPosition"] for cell in cells] == list(range(1, 11))
    for segment in plan["blocks"]:
        held = sorted((x["runKey"]["regime"], x["runKey"]["block"]) for x in segment["cells"])
        assert held == sorted((regime, 1) for regime in REGIMES)
        assert {x["runKey"]["requestsPerSecond"] for x in segment["cells"]} == {segment["requestsPerSecond"]}
    assert {cell["runKey"]["studyEpoch"] for cell in cells} == {PILOT} and plan["studyEpoch"] == PILOT
    assert {cell["fault"] for cell in cells} == {
        None, "frontend-pause", "productcatalog-cpu-throttle", "fraud-pause", "accounting-pause"}
    assert (p.MINIMUM_REMAINING_SECONDS, p.RUN_WINDOW_HOURS) == (10 * (211 + 500) + 900 + 600, 4) == (8610, 4)


def test_planted_defect_an_edited_descriptor_or_plan_is_refused_and_moves_the_pin():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    for mutate in (
        lambda d: d["schedule"].update(seed=20261012),                                      # the load pilot's seed
        lambda d: d["timing"].update(duringFaultProbe=True),                                # H10 off
        lambda d: d["workload"].update(concurrency=3000),                                   # the load pilot's concurrency
        lambda d: d["design"].update(rates=[50.0, 100.0]),
        lambda d: d.update(declaration="research/traffic-sweep/DECLARATION_PILOT_LOAD_OTEL.md"),
        lambda d: d["workload"]["mix"]["tasks"][1].update(weight=9),                        # a task weight
        lambda d: d["workload"]["mix"]["routes"]["checkout"]["requiredServices"].pop(),     # a route's required services
        lambda d: d["faultDesign"]["scenarios"]["fraud-pause"].update(service="accountingservice"),
    ):
        planted = copy.deepcopy(document)
        mutate(planted)
        assert p.canonical_sha256(planted) != PILOT_DESCRIPTOR_SHA256
        with pytest.raises(p.ProtocolError, match="differs from its generator"):
            p.validate_descriptor(planted)
    for mutate in (
        lambda q: q["blocks"][1]["cells"][0]["timing"].update(faultOnsetSeconds=61.0),
        lambda q: q["blocks"][0]["cells"].pop(),
        lambda q: q["blocks"][0]["cells"][0]["timing"].update(concurrency=3000),
        lambda q: q["blocks"][1]["cells"][1]["timing"].update(generatorOpenFilesMinimum=1024),
        lambda q: q["blocks"][0]["cells"][0]["timing"]["workloadMix"]["tasks"][0].update(weight=2),
        lambda q: q.update(blocks=list(reversed(q["blocks"]))),        # 150 req/s first
        lambda q: q["blocks"][0]["cells"][0]["runKey"].update(studyEpoch=C),
    ):
        broken = copy.deepcopy(plan)
        mutate(broken)
        with pytest.raises(p.ProtocolError, match="differs from the frozen schedule"):
            p.validate_plan(document, broken)
    with pytest.MonkeyPatch.context() as patch:            # a pin that does not match the generator is refused
        patch.setattr(p, "EXPECTED_DESCRIPTOR_SHA256", C_DESCRIPTOR_SHA256)
        with pytest.raises(p.ProtocolError, match="differs from the reviewed pin"):
            p.load_descriptor()


def test_the_descriptor_file_is_the_generators_output():
    path = ROOT / "pipelines/campaigns/otel-offpath-pilot-v1.json"
    assert path.read_bytes() == p._pretty_bytes(p.derive_pilot_descriptor())
    document = p.load_descriptor()
    assert document["id"] == PILOT
    assert document["declaration"].startswith("research/traffic-sweep/DECLARATION_PILOT_OFFPATH_OTEL.md ")
    assert document["derivedFrom"]["studyEpoch"] == C
    assert document["derivedFrom"]["descriptorCanonicalSha256"] == C_DESCRIPTOR_SHA256
    assert document["derivedFrom"]["descriptorByteSha256"] == hashlib.sha256(
        (ROOT / "pipelines/campaigns/otel-repeat-episodes-c-v1.json").read_bytes()).hexdigest()
    assert document["derivedFrom"]["predecessorDerivedFrom"]["studyEpoch"] == REPEAT
    assert document["workload"]["kind"] == "multi-route-open-loop-mix" and document["workload"]["mix"] == p.MIX
    assert document["analysis"]["manifestationCriterion"] == p.MANIFESTATION_CRITERION
    defaults = document["analysis"]["manifestationCriterionDefaults"]
    assert defaults == p.MANIFESTATION_CRITERION_DEFAULTS
    assert defaults["preOnsetSegment"] == "[onset - 60 s, onset)" and defaults["hold"] == "[onset, onset + 60 s)"
    assert ">= 1.25" in defaults["throttleClientSpan"] and ">= 2.0" in defaults["throttleServerSpan"]
    assert "Kind=Consumer" in defaults["offPathPause"] and "<= 10 %" in defaults["offPathPause"] and ">= 95 %" in defaults["offPathPause"]
    assert defaults["spanSelection"].startswith("by span start time") and "'—'" in defaults["verdict"]
    scenarios = document["faultDesign"]["scenarios"]
    assert set(scenarios) == {"accounting-pause", "frontend-pause", "fraud-pause", "productcatalog-cpu-throttle"}
    assert (scenarios["fraud-pause"]["service"], scenarios["accounting-pause"]["service"]) == (
        "frauddetectionservice", "accountingservice")
    assert {row["entryRouteDuringFault"] for row in scenarios.values()} == {"not-probed-h10"}


def test_the_digests_are_identical_under_python39_isolated_and_this_interpreter(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import importlib.util, json, sys\n"
        f"s = importlib.util.spec_from_file_location('p', {str(MODULE / 'execution/candidate_offpath_pilot.py')!r})\n"
        "m = importlib.util.module_from_spec(s); sys.modules['p'] = m; s.loader.exec_module(m)\n"
        "d = m.load_descriptor(); c = m.repeat_c.load_descriptor()\n"
        "print(json.dumps([m.canonical_sha256(d), m.canonical_sha256(m.compile_plan(d, 1)), m.MINIMUM_REMAINING_SECONDS,"
        " m.RUN_WINDOW_HOURS, m.canonical_sha256(c), m.canonical_sha256(m.repeat_c.compile_plan(c, 1))]))\n"
    )
    result = subprocess.run(
        [str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
        capture_output=True, text=True, check=True,
    )
    expected = [PILOT_DESCRIPTOR_SHA256, PILOT_PLAN_A1_SHA256, 8610, 4, C_DESCRIPTOR_SHA256, C_PLAN_A1_SHA256]
    assert json.loads(result.stdout) == expected
    document = p.load_descriptor()
    assert [p.canonical_sha256(document), p.canonical_sha256(p.compile_plan(document, 1))] == expected[:2]


# ------------------------------------------------------------------------------------- 2. C's cell, at 100 and 150 /s
def _descriptor_differences(document, base):
    """(top-level keys that differ, {parent: subkeys that differ}) between two descriptors."""
    top = {key for key in set(document) | set(base) if document.get(key) != base.get(key)}
    nested = {}
    for parent in sorted(top):
        if isinstance(document.get(parent), dict) and isinstance(base.get(parent), dict) and parent not in p.REPLACED_DESCRIPTOR_KEYS:
            nested[parent] = {key for key in set(document[parent]) | set(base[parent])
                              if document[parent].get(key) != base[parent].get(key)}
    return {key for key in top if key not in nested}, nested


def test_the_descriptor_is_cs_apart_from_exactly_the_declared_keys():
    document, base = p.load_descriptor(), repeat_c.load_descriptor()
    assert repeat_c.canonical_sha256(base) == C_DESCRIPTOR_SHA256
    top, nested = _descriptor_differences(document, base)
    assert top == set(p.REPLACED_DESCRIPTOR_KEYS) - {"amendments"}         # C's amendments are [] too
    assert nested == {key: set(value) for key, value in p.REPLACED_DESCRIPTOR_SUBKEYS.items()}
    # What C was: H10/H4, the trace rule ids per cell kind, the gates, the dose of the throttle -- inherited verbatim.
    for key in ("protocolGates", "containerHealthGuard", "postureRealization", "workflow"):
        assert document[key] == base[key], key
    assert document["faultDesign"]["scenarios"]["productcatalog-cpu-throttle"] == base["faultDesign"]["scenarios"]["productcatalog-cpu-throttle"]
    assert document["faultDesign"]["scenarios"]["frontend-pause"] == base["faultDesign"]["scenarios"]["frontend-pause"]
    assert document["faultDesign"]["scenarios"]["productcatalog-cpu-throttle"]["nanoCpus"] == 100_000_000
    assert _strip(document["timing"], p.REPLACED_DESCRIPTOR_SUBKEYS["timing"]) == _strip(
        base["timing"], p.REPLACED_DESCRIPTOR_SUBKEYS["timing"])
    assert document["analysis"]["traceCompleteness"]["faultCells"]["allowanceShare"] == 0.01
    assert document["analysis"]["traceCompleteness"]["noFaultCells"]["ruleId"] == "protocol-decision-56"
    assert document["schedule"]["seed"] == SEED != base["schedule"]["seed"]


def test_planted_defect_a_descriptor_that_drifts_from_c_outside_the_declared_keys_is_found():
    document, base = p.load_descriptor(), repeat_c.load_descriptor()
    drifted = copy.deepcopy(document)
    drifted["timing"]["faultHoldSeconds"] = 30
    drifted["protocolGates"]["thresholds"]["FLOOR"] = 0.4
    _, nested = _descriptor_differences(drifted, base)
    assert "faultHoldSeconds" in nested["timing"]
    assert nested != {key: set(value) for key, value in p.REPLACED_DESCRIPTOR_SUBKEYS.items()}
    assert "protocolGates" in nested and "protocolGates" not in p.REPLACED_DESCRIPTOR_KEYS


def test_every_cell_is_cs_cell_at_the_same_regime_and_rate_apart_from_the_declared_keys():
    cells = p.flatten_cells(_plan(1))
    for cell in cells:
        key = cell["runKey"]
        template = p.TIMING_TEMPLATE_REGIME.get(key["regime"], key["regime"])
        c_timing = repeat_c.cell_timing(template, key["requestsPerSecond"], 1)
        timing = cell["timing"]
        assert set(timing) == set(c_timing) | p.NEW_TIMING_KEYS
        assert _strip(timing, p.REPLACED_TIMING_KEYS | p.NEW_TIMING_KEYS) == _strip(c_timing, p.REPLACED_TIMING_KEYS), key
        assert timing["faultOnsetSeconds"] == round(60 + timing["faultOnsetPhaseOffsetSeconds"], 6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"], round(timing["faultOnsetSeconds"] + 60, 6)]
        assert 0 <= timing["faultOnsetPhaseOffsetSeconds"] < 1.0 / key["requestsPerSecond"]
        assert timing["offered"] == int(key["requestsPerSecond"] * 180) and timing["requestTimeoutSeconds"] == 15.0
        if cell["fault"] is not None:
            assert timing["scheduledSlotsByPhase"] == sweep.scheduled_slots_by_phase(
                key["requestsPerSecond"], 180, timing["faultOnsetSeconds"], 60)
        else:
            assert timing["scheduledSlotsByPhase"] is None and timing["traceCompletenessRule"] == "protocol-decision-56"
        assert (timing["duringFaultProbe"], timing["freezeStamps"]) == (False, True)
        assert (timing["warmupSeconds"], timing["warmupRequestsPerSecond"], timing["measurementSeconds"]) == (30, 10.0, 180)
        assert timing["route"] == c_timing["route"]               # the probe route stays C's one product route
        assert timing["workloadMix"] == p.MIX
    c_plan = repeat_c.compile_plan(repeat_c.load_descriptor(), 1)
    plan = _plan(1)
    assert set(plan) == set(c_plan) | {"schedule"} or set(plan) == set(c_plan)
    same = {k for k in plan if k in c_plan and plan[k] == c_plan[k]}
    assert set(plan) - same == {
        "kind", "studyEpoch", "descriptorSha256", "scheduleVersion", "schedule", "blocks", "runCount", "uniqueRunCount",
        "minimumRemainingSeconds", "runWindowHours",
    }


def test_planted_defect_a_cell_that_drifts_from_c_outside_the_declared_keys_is_found():
    cell = p.flatten_cells(_plan(1))[0]
    key = cell["runKey"]
    drifted = copy.deepcopy(cell["timing"])
    drifted["faultHoldSeconds"] = 30
    template = p.TIMING_TEMPLATE_REGIME.get(key["regime"], key["regime"])
    c_timing = repeat_c.cell_timing(template, key["requestsPerSecond"], 1)
    assert _strip(drifted, p.REPLACED_TIMING_KEYS | p.NEW_TIMING_KEYS) != _strip(c_timing, p.REPLACED_TIMING_KEYS)


# ------------------------------------------------------------------------------------- 3. the generator sizing
def test_the_generator_is_sized_for_rate_x_timeout_and_its_open_files_and_the_proxy_memory_follow():
    for cell in p.flatten_cells(_plan(1)):
        timing = cell["timing"]
        rate, timeout = timing["requestsPerSecond"], timing["requestTimeoutSeconds"]
        assert timing["concurrency"] == 4500 >= 2 * rate * timeout          # the sweep's rule at the pilot's max rate
        assert timing["generatorOpenFilesMinimum"] == 4500 + 1024
        limit = timing["serviceMemoryLimitBytes"]["frontendproxy"]
        assert limit == 1024 ** 3 >= p.FRONTENDPROXY_BYTES_PER_WAITING_REQUEST * 150 * 15
        # user decision 2026-10-12: the telemetry backend (otelcol, jaeger) gets 1 GiB each; no SUT service limit is touched
        assert timing["serviceMemoryLimitBytes"] == {"frontendproxy": 1024 ** 3, "otelcol": 1024 ** 3, "jaeger": 1024 ** 3}
    assert p.CONCURRENCY == math.ceil(sweep.CONCURRENCY_MARGIN * max(RATES) * sweep.REQUEST_TIMEOUT_SECONDS)
    assert repeat_c.cell_timing(THROTTLE, 150.0, 1)["concurrency"] == 300       # C's value, too small at 150 /s
    assert load_pilot.CONCURRENCY == 3000                                        # the load pilot's, too small for 150 /s (4500)


def test_only_the_proxy_and_the_telemetry_backend_have_a_memory_limit_and_each_is_declared_as_a_deviation():
    document = p.load_descriptor()
    sut = set(json.loads((MODULE / "postures/catalog.json").read_text())["applicationServices"]) - {"frontendproxy"}
    assert set(p.SERVICE_MEMORY_LIMIT_BYTES) == {"frontendproxy", "otelcol", "jaeger"} and not set(p.SERVICE_MEMORY_LIMIT_BYTES) & sut
    rows = {row["service"]: row for row in document["sutDeviations"] if row["setting"] == "memory limit (HostConfig.Memory)"}
    assert set(rows) == {"frontendproxy", "otelcol", "jaeger"}
    assert rows["otelcol"]["upstream"].startswith("209715200") and rows["jaeger"]["upstream"].startswith("419430400")
    assert all("1073741824" in rows[s]["pilot"] for s in rows) and "telemetry backend" in rows["jaeger"]["reason"]
    # planted: a SUT service limit smuggled into the sizing is found by the descriptor generator (descriptor differs) and the plan pin
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "SERVICE_MEMORY_LIMIT_BYTES", {**p.SERVICE_MEMORY_LIMIT_BYTES, "productcatalogservice": 64 * 1024 ** 2})
        planted = p._compile(document, 1)
    assert p.canonical_sha256(planted) != PILOT_PLAN_A1_SHA256
    with pytest.raises(p.ProtocolError, match="differs from the frozen schedule"):
        p.validate_plan(document, planted)


def test_planted_defect_a_load_pilot_sized_generator_at_150_per_second_is_refused_by_the_plan_check():
    document = p.load_descriptor()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "CONCURRENCY", 300)                       # C's worker cap: 300 < 150 x 15
        planted = p._compile(document, 1)
    with pytest.raises(p.ProtocolError):
        p.validate_plan(document, planted)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "CONCURRENCY", 300)
        patch.setattr(p, "_compile", lambda d, a: planted)          # even a plan that replays its own compiler
        patch.setattr(p, "validate_descriptor", lambda d: d)        # and a descriptor generated with the same cap
        with pytest.raises(p.ProtocolError, match="generator sizing"):
            p.validate_plan(document, planted)


# ------------------------------------------------------------------------------------- 4. order and onsets
def test_every_100_per_second_cell_runs_before_any_150_per_second_cell_in_a_seeded_order():
    document = p.load_descriptor()
    cells = p.flatten_cells(_plan(1))
    rates = [cell["runKey"]["requestsPerSecond"] for cell in cells]
    assert rates == sorted(rates) and rates[:5] == [100.0] * 5 and rates[5:] == [150.0] * 5
    for receipt in document["schedule"]["segments"]:
        rows = p.segment_cells(receipt["requestsPerSecond"])
        expected = [{"regime": NO_FAULT, "rate": receipt["requestsPerSecond"], "block": 1}]
        expected += quiet.fisher_yates([r for r in rows if r["regime"] in (FRAUD, ACCOUNTING)], SEED, PILOT, receipt["segment"],
                                       "offpath-pilot-schedule-v1-group1")
        expected += quiet.fisher_yates([r for r in rows if r["regime"] in (FRONTEND, THROTTLE)], SEED, PILOT, receipt["segment"],
                                       "offpath-pilot-schedule-v1-group2")
        assert receipt["order"] == [p.cell_label(row) for row in expected]
        assert receipt["orderSha256"] == p.canonical_sha256(receipt["order"])
    orders = [segment["order"] for segment in document["schedule"]["segments"]]
    assert sorted(x.split("@")[0] for x in orders[0]) == sorted(REGIMES) == sorted(x.split("@")[0] for x in orders[1])


def test_every_segment_runs_no_fault_then_the_off_path_pauses_then_the_frontend_pause_and_throttle_and_a_plan_that_does_not_is_refused():
    """Coordinator's defaults 2026-10-12: within a rate the no-fault cell first (an early stop leaves its baseline), then the two
    off-path pauses (the never-run answers), then the on-path control and the throttle; seeded order inside a group."""
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    for segment in plan["blocks"]:
        regimes = [cell["runKey"]["regime"] for cell in segment["cells"]]
        assert regimes[0] == NO_FAULT and set(regimes[1:3]) == {FRAUD, ACCOUNTING} and set(regimes[3:]) == {FRONTEND, THROTTLE}
    # planted: a plan whose own compiler runs the groups in another order (and a descriptor generated with it) is refused by the rule
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "ORDER_GROUPS", ((FRONTEND, THROTTLE), (NO_FAULT,), (FRAUD, ACCOUNTING)))
        wrong = p.derive_pilot_descriptor()
        wrong_plan = p._compile(wrong, 1)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "validate_descriptor", lambda d: d)
        patch.setattr(p, "_compile", lambda d, a: wrong_plan)
        with pytest.raises(p.ProtocolError, match="does not run its no-fault cell, then the off-path pauses"):
            p.validate_plan(wrong, wrong_plan)
    # planted: a reorder of the compiled plan alone fails the frozen schedule
    broken = copy.deepcopy(plan)
    first = broken["blocks"][0]["cells"]
    first.append(first.pop(0))
    for position, cell in enumerate(first, start=1):
        cell["ordinalPosition"] = position
    broken["blocks"][0]["order"] = [cell["runId"] for cell in first]
    with pytest.raises(p.ProtocolError, match="differs from the frozen schedule"):
        p.validate_plan(document, broken)
    # and the previous rule (every cell shuffled, or only the no-fault cell pinned first) is not the one the pin holds
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "segment_order", lambda n: quiet.fisher_yates(
            p.segment_cells(RATES[n - 1]), SEED, PILOT, n, "offpath-pilot-schedule-v1"))
        reshuffled = p.allocate_schedule()
    assert reshuffled != p.load_descriptor()["schedule"]["segments"]


def test_planted_defect_a_descending_rate_order_is_refused():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "RATES", (150.0, 100.0))
        with pytest.raises(p.ProtocolError, match="ascending"):
            p.allocate_schedule()


def test_every_cell_has_one_onset_inside_one_inter_arrival():
    for cell in p.flatten_cells(_plan(1)):
        key, timing = cell["runKey"], cell["timing"]
        assert key["block"] == 1
        assert 0 <= timing["faultOnsetPhaseOffsetSeconds"] < 1.0 / key["requestsPerSecond"]
    with pytest.raises(p.ProtocolError, match="one episode"):
        p.onset_phase_offset(THROTTLE, 100.0, 2)


# ------------------------------------------------------------------------------------- 5. no run-ID reuse
def _ran_run_ids() -> dict:
    compilers = {SWEEP: sweep, QUIET: quiet, REPEAT: repeat, C: repeat_c, LOAD: load_pilot}
    ids = {}
    for epoch, attempts in RAN.items():
        compiler = compilers[epoch]
        document = compiler.load_descriptor()
        for attempt in attempts:
            ids[(epoch, attempt)] = {cell["runId"] for cell in compiler.flatten_cells(compiler.compile_plan(document, attempt))}
    return ids


def _reused(run_ids, ran) -> dict:
    return {key: len(run_ids & ids) for key, ids in ran.items() if run_ids & ids}


def test_no_pilot_run_id_equals_one_that_ran_in_the_sweep_quiet_b_c_or_the_load_pilot():
    ran = _ran_run_ids()
    assert {key: len(ids) for key, ids in ran.items()} == {
        (SWEEP, 1): 12, (SWEEP, 2): 12, (QUIET, 1): 40, (QUIET, 2): 40, (QUIET, 3): 40, (REPEAT, 1): 36, (C, 1): 36,
        (LOAD, 1): 6}
    for attempt in (1, 2, 3):
        ids = {cell["runId"] for cell in p.flatten_cells(_plan(attempt))}
        assert len(ids) == 10 and _reused(ids, ran) == {}
    assert load_pilot.canonical_sha256(load_pilot.compile_plan(load_pilot.load_descriptor(), 1)) == LOAD_PLAN_A1_SHA256
    assert load_pilot.canonical_sha256(load_pilot.load_descriptor()) == LOAD_DESCRIPTOR_SHA256


def test_planted_defect_with_the_load_pilots_epoch_the_pilot_would_reuse_its_run_ids_and_the_check_finds_them():
    ran = _ran_run_ids()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "EPOCH", LOAD)
        ids = {p.run_id_for(p.run_key_for(regime, rate, 1, "full", 1)) for regime in (NO_FAULT, THROTTLE) for rate in (100.0,)}
    # the load pilot ran (no-fault, 100) and (throttle, 100) with the same run keys (blocks 1 and 2 for the throttle)
    assert _reused(ids, ran) == {(LOAD, 1): 2}


def _spent_table_in_source() -> dict:
    tree_ = ast.parse((MODULE / "execution/candidate_runtime_adapter.py").read_text())
    for node in tree_.body:
        if isinstance(node, ast.Assign) and any(getattr(t_, "id", None) == "SPENT_ATTEMPTS_BY_EPOCH" for t_ in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SPENT_ATTEMPTS_BY_EPOCH not found")


def test_the_pilots_attempt_1_is_recorded_spent_beside_the_load_pilots_and_cs():
    # 2026-10-12: v1 attempt 1 ran (harness 8c53cb2, plan 8b3d7aa8) and stopped at cell 2 (productcatalogservice OOM at 20 MiB).
    table = _spent_table_in_source()
    assert set(table[PILOT]) == {1} and "8c53cb2" in table[PILOT][1] and "8b3d7aa8" in table[PILOT][1]
    assert set(table[LOAD]) == {1} and set(table[C]) == {1}
    assert PILOT_PLAN_A1_SHA256.startswith("8b3d7aa8")                         # the plan that ran


# ------------------------------------------------------------- 6. the mix: upstream's tasks, shares and journeys
UPSTREAM = ROOT / "upstream/opentelemetry-demo/src/loadgenerator"


def test_the_mix_is_upstreams_task_set_and_weights():
    """Tasks and weights read from the pinned upstream locustfile (skipped without the submodule), flood_home dropped."""
    mix = p.MIX
    assert [(task["id"], task["weight"]) for task in mix["tasks"]] == [
        ("index", 1), ("browse_product", 10), ("get_recommendations", 3), ("get_ads", 3), ("view_cart", 3),
        ("add_to_cart", 2), ("checkout", 1), ("checkout_multi", 1)]
    assert mix["cycleWeight"] == 24 == sum(task["weight"] for task in mix["tasks"])
    locustfile = UPSTREAM / "locustfile.py"
    if not locustfile.exists():
        pytest.skip("upstream/opentelemetry-demo is not checked out")
    source = locustfile.read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == p.UPSTREAM_LOCUSTFILE_SHA256
    upstream = re.findall(r"@task\((\d+)\)\s+def (\w+)\(", source)
    assert [(name, int(weight)) for weight, name in upstream if name != "flood_home"] == [
        (task["id"], task["weight"]) for task in mix["tasks"]]
    assert ("flood_home", 5) == next((name, int(weight)) for weight, name in upstream if name == "flood_home")
    assert hashlib.sha256((UPSTREAM / "people.json").read_bytes()).hexdigest() == p.UPSTREAM_PEOPLE_SHA256
    assert mix["people"] == json.loads((UPSTREAM / "people.json").read_text())
    assert list(mix["products"]) == re.findall(r'"([0-9A-Z]{10})"', source.split("products = [")[1].split("]")[0])


def test_planted_defect_a_mix_that_drifts_from_upstreams_weights_is_found():
    locustfile = UPSTREAM / "locustfile.py"
    if not locustfile.exists():
        pytest.skip("upstream/opentelemetry-demo is not checked out")
    upstream = [(name, int(weight)) for weight, name in re.findall(r"@task\((\d+)\)\s+def (\w+)\(", locustfile.read_text())
                if name != "flood_home"]
    planted = [(task["id"], task["weight"] + (task["id"] == "browse_product")) for task in p.MIX["tasks"]]
    assert planted != upstream


@pytest.fixture(scope="module")
def remote_module(pilot_tree):
    return pilot_tree.remote


def test_the_plan_of_the_mix_has_upstreams_shares_exactly_per_cycle_and_is_deterministic(remote_module):
    remote = remote_module
    plan = remote.mix_plan(p.MIX, "ns-a", 18000)
    assert len(plan) == 18000 and [row["sequence"] for row in plan] == list(range(18000))
    firsts = [row["task"] for row in plan if row["step"] == 0]
    cycle = firsts[:24]
    assert collections.Counter(cycle) == {task["id"]: task["weight"] for task in p.MIX["tasks"]}
    # smooth WRR: every window of 24 consecutive tasks holds each task's weight, so every window of one cycle is exact
    for start in range(0, len(firsts) - 24, 7):
        assert collections.Counter(firsts[start:start + 24]) == collections.Counter(cycle)
    shares = collections.Counter(row["route"] for row in plan)
    expected = {"product": 47.1, "add-to-cart": 17.6, "recommendations": 8.8, "ads": 8.8, "view-cart": 8.8, "checkout": 5.9,
                "index": 2.9}                      # DESIGN.md 2.3 (the multi-checkout's adds are drawn, mean 3)
    assert set(shares) == set(expected)
    assert all(abs(100.0 * shares[route] / len(plan) - share) <= 0.4 for route, share in expected.items())
    assert plan == remote.mix_plan(p.MIX, "ns-a", 18000)                 # a pure function of (mix, namespace, offered)
    assert plan[:50] == remote.mix_plan(p.MIX, "ns-a", 50)               # a shorter plan is a prefix
    assert [row["target"] for row in plan[:60]] != [row["target"] for row in remote.mix_plan(p.MIX, "ns-b", 60)]
    first_checkout = next(row["sequence"] for row in plan if row["route"] == "checkout")
    cut = remote.mix_plan(p.MIX, "ns-a", first_checkout)
    # a journey is cut at the count: its cart POST is the last request, the checkout step is cut off
    assert len(cut) == first_checkout and cut[-1]["route"] == "add-to-cart" and cut[-1]["task"] in ("checkout", "checkout_multi")
    assert all(row["dependsOn"] is None or row["dependsOn"] < row["sequence"] for row in cut)


def test_a_checkout_depends_on_the_cart_post_of_its_own_journey(remote_module):
    remote = remote_module
    plan = remote.mix_plan(p.MIX, "ns-a", 18000)
    checkouts = [row for row in plan if row["route"] == "checkout"]
    journeys = sum(1 for row in plan if row["step"] == 0 and row["task"] in ("checkout", "checkout_multi"))
    assert len(checkouts) in (journeys, journeys - 1) and journeys > 1000
    assert all(row["method"] == "POST" and row["target"] == "/api/checkout" for row in checkouts)
    for row in checkouts:
        before = plan[row["dependsOn"]]
        assert before["route"] == "add-to-cart" and before["taskIndex"] == row["taskIndex"] and row["dependsOn"] == row["sequence"] - 1
        user = json.loads(row["body"])["userId"]
        journey = [other for other in plan if other["taskIndex"] == row["taskIndex"] and other["route"] == "add-to-cart"]
        assert {json.loads(other["body"])["userId"] for other in journey} == {user}      # one session per journey
        assert all(other["dependsOn"] is None for other in plan[row["sequence"] - 6:row["sequence"]] if other["route"] != "checkout")
    users = {json.loads(row["body"])["userId"] for row in checkouts}
    assert len(users) == len(checkouts)                                                  # carts never mix across journeys
    multi = [row for row in plan if row["task"] == "checkout_multi" and row["route"] == "add-to-cart"]
    per_journey = collections.Counter(row["taskIndex"] for row in multi)
    assert set(per_journey.values()) == {2, 3, 4}                                        # 2-4 adds before the checkout
    people = {json.dumps({k: v for k, v in person.items()}, sort_keys=True) for person in p.MIX["people"]}
    for row in checkouts[:50]:
        body = json.loads(row["body"])
        user = body.pop("userId")
        assert json.dumps(body, sort_keys=True) in people and user.startswith("u")
    assert all(row["bodySha256"] == hashlib.sha256(row["body"]).hexdigest() for row in plan if row["body"] is not None)


def test_every_route_names_services_the_posture_catalog_knows_and_the_routes_cover_the_catalog_closure():
    catalog = json.loads((MODULE / "postures/catalog.json").read_text())
    known = set(catalog["applicationServices"])
    for route_id, route in p.MIX["routes"].items():
        assert set(route["requiredServices"]) <= known, route_id
        assert route["requiredServices"][:2] == ["frontendproxy", "frontend"]
        assert "flagd" not in route["requiredServices"]                                   # conservative subset (declared)
        assert not {"accountingservice", "frauddetectionservice", "kafka"} & set(route["requiredServices"])
    union = p.mix_route_services()
    assert {"recommendationservice", "adservice", "cartservice", "checkoutservice", "paymentservice"} <= set(union)
    assert union == sorted(set(union))
    assert set(union) <= set(catalog["postures"]["full"]["activeApplicationServices"])


def test_no_request_of_the_mix_is_sent_to_a_path_the_frontend_would_redirect(remote_module):
    """Next.js (trailingSlash unset) answers /api/data/ with a 308 to /api/data.  Python 3.9's urllib does not follow a 308 (3.11
    does) and a followed redirect would show the request token to the proxy twice, so the mix sends canonical paths only.
    Upstream's locust spells the ads path /api/data/ (requests follows the 308); that is the one deliberate spelling change."""
    plan = remote_module.mix_plan(p.MIX, "ns-a", 6000)
    paths = {row["target"].split("?")[0] for row in plan}
    assert "/api/data" in paths and not any(path != "/" and path.endswith("/") for path in paths)
    assert all(row["target"].startswith("/") and "//" not in row["target"] for row in plan)
    planted = copy.deepcopy(p.MIX)
    planted["routes"]["ads"]["path"] = "/api/data/?contextKeys={category}"
    redirected = {row["target"].split("?")[0] for row in remote_module.mix_plan(planted, "ns-a", 600)}
    assert "/api/data/" in redirected                                 # the defect the check above would catch


def test_the_mix_plan_is_identical_under_python39_isolated_and_this_interpreter(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import hashlib, importlib.util, json, sys\n"
        f"s = importlib.util.spec_from_file_location('c', {str(MODULE / 'execution/candidate_offpath_pilot.py')!r})\n"
        "c = importlib.util.module_from_spec(s); sys.modules['c'] = c; s.loader.exec_module(c)\n"
        f"s = importlib.util.spec_from_file_location('r', {str(MODULE / 'execution/candidate_remote.py')!r})\n"
        "r = importlib.util.module_from_spec(s); sys.modules['r'] = r; s.loader.exec_module(r)\n"
        "plan = r.mix_plan(c.MIX, 'ns-a', 3000)\n"
        "print(hashlib.sha256(json.dumps([[x['sequence'], x['task'], x['route'], x['target'], x['bodySha256'], x['dependsOn']]"
        " for x in plan]).encode()).hexdigest())\n"
    )
    result = subprocess.run(
        [str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
        capture_output=True, text=True, check=True,
    )
    plan = load("otel_offpath_pilot_remote_here", MODULE / "execution/candidate_remote.py").mix_plan(p.MIX, "ns-a", 3000)
    here = hashlib.sha256(json.dumps([[x["sequence"], x["task"], x["route"], x["target"], x["bodySha256"], x["dependsOn"]]
                                       for x in plan]).encode()).hexdigest()
    assert result.stdout.strip() == here


def test_planted_defect_a_mix_naming_an_unknown_task_or_weights_that_do_not_sum_is_refused(remote_module):
    remote = remote_module
    unknown = copy.deepcopy(p.MIX)
    unknown["tasks"][0]["id"] = "flood_home"
    with pytest.raises(remote.RuntimeFailure, match="upstream task set"):
        remote.mix_plan(unknown, "ns", 10)
    skewed = copy.deepcopy(p.MIX)
    skewed["tasks"][1]["weight"] = 11
    with pytest.raises(remote.RuntimeFailure, match="upstream task set"):
        remote.mix_plan(skewed, "ns", 10)
    other = copy.deepcopy(p.MIX)
    other["kind"] = "something-else"
    with pytest.raises(remote.RuntimeFailure, match="kind differs"):
        remote.mix_plan(other, "ns", 10)


# ------------------------------------------------------------- 7. the epoch in the runtime, the gate chain and the target
def test_the_selector_activates_the_pilot_in_every_reader(pilot_tree, tmp_path):
    runtime = pilot_tree.runtime
    assert runtime.STUDY_EPOCH == PILOT and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (10, 8610, 4)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | PILOT_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_offpath_pilot.py"
    assert runtime.CONTROLLER_PATHS["repeat-c-compiler"] == "modules/otel-demo/execution/candidate_repeat_c.py"
    assert runtime.DESCRIPTOR == pilot_tree.root / "pipelines/campaigns/otel-offpath-pilot-v1.json"
    assert pilot_tree.setup.controller_paths(PILOT) == runtime.CONTROLLER_PATHS
    assert pilot_tree.setup.EPOCH_CONTROLLER_PATHS[PILOT] == runtime.EPOCH_CONTROLLER_PATHS[PILOT]
    digests = runtime.controller_digests()
    for key, relative in (("repeat-c-compiler", "execution/candidate_repeat_c.py"), ("repeat-compiler", "execution/candidate_repeat.py"),
                          ("candidate-compiler", "execution/candidate_offpath_pilot.py")):
        assert digests[key] == hashlib.sha256((MODULE / relative).read_bytes()).hexdigest()
    assert runtime.frozen_descriptor()["id"] == PILOT
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {
        "duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}
    assert runtime.timed_cell_timing_keys(False) == runtime.timed_cell_timing_keys(True) | {"traceCompletenessRule"}
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    copied = load("otel_offpath_pilot_driver_config_tree", pilot_tree.root / "modules/otel-demo/drivers/gate_driver_config.py")
    assert (copied.CONFIG.study, copied.CONFIG.campaign_id, copied.CONFIG.run_window_hours) == (PILOT, PILOT, 4)
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_offpath_pilot_tree_adapter", pilot_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == PILOT
        assert adapter.pilot.EPOCH == PILOT and set(adapter.SPENT_ATTEMPTS) == {1}          # attempt 1 ran and is spent
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
                adapter.inspect_campaign(tmp_path / "plan-a1", "a" * 40)
            patch.delitem(adapter.SPENT_ATTEMPTS, 1)
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 10 and bindings.plan_sha256 == PILOT_PLAN_A1_SHA256
        assert bindings.descriptor_sha256 == PILOT_DESCRIPTOR_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_planted_defect_a_selector_naming_the_pilot_without_its_controller_set_is_refused(tmp_path_factory):
    root = helpers._copy_tree(
        tmp_path_factory.mktemp("offpath-pilot-no-paths"), selector=json.dumps({"schemaVersion": 1, "studyEpoch": PILOT}) + "\n")
    runtime_path = root / "modules/otel-demo/execution/candidate_runtime.py"
    text = runtime_path.read_text()
    marker = "    OFFPATH_PILOT_STUDY_EPOCH: {\n        \"candidate-compiler\": \"modules/otel-demo/execution/candidate_offpath_pilot.py\","
    assert text.count(marker) == 1
    runtime_path.write_text(text.replace(marker, "    \"otel-offpath-pilot-v0\": {\n        \"candidate-compiler\": \"modules/otel-demo/execution/candidate_offpath_pilot.py\","))
    with pytest.raises(Exception, match="names no declared non-frozen epoch"):
        load("otel_offpath_pilot_no_paths_runtime", runtime_path)


def test_gate_chain_derives_10_cells_the_budget_and_host_paths_disjoint_from_every_earlier_epoch(pilot_tree, pilot_package):
    runtime, remote = pilot_tree.runtime, pilot_tree.remote
    plan_text = pilot_package.gate_plan["typedApproval"]
    assert f"study={PILOT} " in plan_text and " runs=10 " in plan_text and f"campaign={PILOT} " in plan_text
    assert pilot_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 8610
    binding = pilot_package.gate_plan["binding"]
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_offpath_pilot_v1"
    assert remote.SAFE_NAME.fullmatch(binding["compose"]["project"])
    earlier = (SWEEP, QUIET, REPEAT, C, LOAD)
    other = ["/home/stig/observability-placement-candidate-v4-runs/" + epoch for epoch in earlier] + [
        "/home/stig/observability-placement-candidate-v4-runs/.setup-" + epoch for epoch in earlier] + [
        "/home/stig/observability-placement-candidate-v4-otel-srv6/" + epoch + "-" for epoch in earlier]
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert PILOT in binding[key] and not any(binding[key].startswith(path) for path in other), key
    assert set(binding["controllerDigests"]) == helpers.FROZEN_CONTROLLER_KEYS | PILOT_CONTROLLER_KEYS
    document = runtime.execution_package(pilot_package)
    assert document["runCount"] == 10 and len(document["cells"]) == 10
    union = p.mix_route_services()
    for contract, cell in zip(document["cells"], pilot_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and runtime.sweep_cell_timing(contract) == cell["timing"]
        pause = contract["fault"]["action"] == "pause"
        assert ("docker-events.json" in contract["requiredArtifacts"]) is pause          # H4: every pause cell retains the events
        assert contract["workload"]["concurrency"] == 4500 and contract["workload"]["kind"] == "multi-route-open-loop-mix"
        assert contract["workload"]["routeServices"] == union and contract["workload"]["urlPath"] == "/api/products/66VCHSJNUP"
    assert sum("docker-events.json" in c["requiredArtifacts"] for c in document["cells"]) == 6
    assert [c["runKey"]["requestsPerSecond"] for c in document["cells"]] == [100.0] * 5 + [150.0] * 5
    assert {c["fault"]["service"] for c in document["cells"]} == {
        None, "frontend", "productcatalogservice", "frauddetectionservice", "accountingservice"}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (PILOT,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
    assert len(cells) == 10 and remote.expected_minimum_remaining(document) == 8610 and remote.expected_run_count(document) == 10


def test_a_contract_cannot_drop_or_change_the_mix_or_the_open_file_minimum(pilot_tree, pilot_package):
    runtime = pilot_tree.runtime
    contract = copy.deepcopy(runtime.execution_package(pilot_package)["cells"][0])
    for key in ("workloadMix", "generatorOpenFilesMinimum"):
        dropped = copy.deepcopy(contract)
        dropped["timing"].pop(key)
        with pytest.raises(runtime.GateError, match="cell timing fields differ"):
            runtime.sweep_cell_timing(dropped)
    changed = copy.deepcopy(contract)
    changed["timing"]["workloadMix"]["tasks"][1]["weight"] = 9
    with pytest.raises(runtime.GateError, match="not the active compiled plan's timing"):
        runtime.sweep_cell_timing(changed)
    changed = copy.deepcopy(contract)
    changed["timing"]["workloadMix"]["routes"]["checkout"]["requiredServices"].remove("emailservice")
    with pytest.raises(runtime.GateError, match="not the active compiled plan's timing"):
        runtime.sweep_cell_timing(changed)


def test_the_target_treats_the_pilot_as_an_h10_h4_epoch_and_a_family_without_it_is_refused(pilot_tree, pilot_package):
    remote = pilot_tree.remote
    assert PILOT in remote.REPEAT_STUDY_EPOCHS and PILOT in remote.TIMED_STUDY_EPOCHS and LOAD in remote.REPEAT_STUDY_EPOCHS
    cells = pilot_tree.runtime.execution_package(pilot_package)["cells"]
    fault = next(x for x in cells if x["fault"]["scenario"] == "fraud-pause")
    clean = next(x for x in cells if x["fault"]["scenario"] is None)
    remote.require_harness_flags_consistent(fault)
    assert remote.names_trace_rule(clean) is True and remote.names_trace_rule(fault) is False
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "REPEAT_STUDY_EPOCHS", (REPEAT, C, LOAD))
        with pytest.raises(remote.RuntimeFailure, match="H10"):
            remote.require_harness_flags_consistent(fault)
        assert remote.names_trace_rule(clean) is False


# ------------------------------------------------------------------------------------- 8. a fake target for the mix
class _Limits:
    def __init__(self, soft, hard):
        self.soft, self.hard, self.calls = soft, hard, []

    def get(self, which):
        return self.soft, self.hard

    def set(self, which, value):
        self.calls.append(value)
        self.soft, self.hard = value


class _CappedPool(concurrent.futures.ThreadPoolExecutor):
    """The fake target answers at once, so a few hundred workers keep the open loop on time (macOS caps a process at 4096
    threads, kern.num_taskthreads).  The cap the controller asked for is recorded."""

    asked: list = []
    cap = 256

    def __init__(self, max_workers=None, **kwargs):
        type(self).asked.append(max_workers)
        super().__init__(max_workers=min(int(max_workers), type(self).cap), **kwargs)


def _stamp(epoch: float) -> str:
    moment = datetime.fromtimestamp(epoch, timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S") + ".%07d +0000 UTC" % int((epoch % 1) * 1e7)


def _route_of(method: str, path: str) -> str:
    if path.startswith("/api/products/"):
        return "product"
    if path.startswith("/api/recommendations"):
        return "recommendations"
    if path.startswith("/api/data"):
        return "ads"
    if path == "/api/cart":
        return "view-cart" if method == "GET" else "add-to-cart"
    if path == "/api/checkout":
        return "checkout"
    return "index" if path in ("", "/") else "other"


CONSUMERS = ("accountingservice", "frauddetectionservice")
CONSUMER_LAG_SECONDS = 0.3
SLOW_SERVER_SECONDS, FAST_SERVER_SECONDS = 0.02, 0.0004


class OffpathTarget(b_tests.RepeatTarget):
    """The repeat tests' fake fb14srv6 for the mix: every route of the upstream task mix is served through the frontend (a cart
    per user, so a checkout without its cart POST fails), a pause of any service is tracked with its Docker events, a throttle
    of productcatalogservice slows its server spans, and the collector log carries span blocks in the debug exporter's format
    (service, trace, name, kind, start, end) per route, with the consumers' spans for every accepted checkout: delayed past an
    unpause when the consumer was paused (``consumers_ignore_pause`` plants a consumer that keeps working through the pause)."""

    def __init__(self, contract, clock, *, consumers_ignore_pause=False, checkout_fails_while_paused=(),
                 lose_route_services=(), cart_post_seconds=0.0, no_throttle_effect=False, **options):
        super().__init__(contract, clock, **options)
        self.mix = contract["timing"]["workloadMix"]
        self.routes = {}                  # token -> route id of every scored request
        self.carts = set()
        self.orders = 0
        self.paused = {}                  # service -> epoch the open pause began
        self.pause_intervals = {}         # service -> [(start, end)]
        self.throttled = []               # [[start, end or None]] while productcatalogservice has NanoCpus 0.1 core
        self.event_rows = []              # (action, epoch, service) of every non-frontend pause or unpause
        self.consumers_ignore_pause = consumers_ignore_pause
        self.checkout_fails_while_paused = set(checkout_fails_while_paused)
        self.lose_route_services = set(lose_route_services)     # (route, service): spans that never reach the collector
        self.cart_post_seconds = cart_post_seconds
        self.no_throttle_effect = no_throttle_effect

    # -- HTTP ----------------------------------------------------------------------------------------------
    def _note(self, method, url, headers):
        token = headers.get("x-obsplacement-request-token")
        if token and not token.startswith("readiness"):
            parts = urlsplit(url)
            with self.lock:
                self.routes[token] = _route_of(method, parts.path)
        return token

    def http_get(self, url, headers, timeout):
        self._note("GET", url, headers)
        return super().http_get(url, headers, timeout)

    def http_post(self, url, body, headers, timeout):
        token, traceparent = self._note("POST", url, headers), headers.get("traceparent")
        if not self.frontend_running.is_set():
            if not self.frontend_running.wait(timeout / SCALE):
                self._serve(token, traceparent, False)
                return None, 0, "TimeoutError: timed out"
        payload = json.loads(body)
        route = _route_of("POST", urlsplit(url).path)
        ok = True
        if route == "add-to-cart":
            if self.cart_post_seconds:
                real_time.sleep(self.cart_post_seconds)
            with self.lock:
                self.carts.add(payload["userId"])
        elif route == "checkout":
            with self.lock:
                ok = payload["userId"] in self.carts and not (set(self.paused) & self.checkout_fails_while_paused)
                self.carts.discard(payload["userId"])
                self.orders += int(ok)
        self._serve(token, traceparent, ok)
        return (200, 10, None) if ok else (500, 0, "HTTPError: HTTP Error 500: Internal Server Error")

    # -- Docker ----------------------------------------------------------------------------------------------
    def command(self, argv, **kwargs):
        argv = [str(item) for item in argv]
        if argv[:2] == ["docker", "compose"] and len(argv) > 11 and argv[10] in ("pause", "unpause") and argv[11] != "frontend":
            self.commands.append(argv)
            self.clock.sleep(helpers.COMMAND_SECONDS)
            at, service = self.clock.time(), argv[11]
            with self.lock:
                if argv[10] == "pause":
                    self.paused[service] = at
                else:
                    self.pause_intervals.setdefault(service, []).append((self.paused.pop(service), at))
                self.event_rows.append((argv[10], at, service))
            return subprocess.CompletedProcess(argv, 0, "", "")
        result = super().command(argv, **kwargs)
        if argv[:2] == ["docker", "update"] and "--cpus" in argv and argv[-1] == "cid-productcatalogservice":
            at, bound = self.clock.time(), argv[argv.index("--cpus") + 1] == "0.100"
            with self.lock:
                if bound:
                    self.throttled.append([at, None])
                elif self.throttled and self.throttled[-1][1] is None:
                    self.throttled[-1][1] = at
        return result

    def started_services(self):
        return super().started_services() + ["jaeger"]         # the telemetry backend's trace store (1 GiB from this epoch)

    def _inspect(self, service):
        rows = super()._inspect(service)
        if service in self.paused:
            rows[0]["State"].update(Paused=True, Status="paused")
        return rows

    def event_lines(self):
        def line(action, at, service):
            cid = f"cid-{service}"
            return json.dumps({
                "status": action, "id": cid, "from": "img", "Type": "container", "Action": action,
                "Actor": {"ID": cid, "Attributes": {"com.docker.compose.service": service, "name": service}},
                "scope": "local", "time": int(at), "timeNano": int((at + self.event_skew) * 1e9),
            })
        rows = [line(action, at, "frontend") for action, at in self.event_log if action not in self.drop_events]
        rows += [line(action, at, service) for action, at, service in self.event_rows if action not in self.drop_events]
        return rows

    # -- the collector -------------------------------------------------------------------------------------------
    def _slow(self, at):
        return not self.no_throttle_effect and any(a <= at and (b is None or at < b) for a, b in self.throttled)

    def _consumer_start(self, service, at):
        start = at + CONSUMER_LAG_SECONDS
        if not self.consumers_ignore_pause:
            for a, b in self.pause_intervals.get(service, []):
                if a <= start < b:
                    start = b + 0.01            # the consumer catches up after the unpause
        return start

    def collector_log(self) -> str:
        stamp = datetime.fromtimestamp(self.first_epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"otelcol-1  | Timestamp: {stamp}.123456789 +0000 UTC", f"otelcol-1  | Body: Str(stray {self.STRAY} byte)"]

        def block(service, trace, name=None, kind=None, start=None, end=None):
            lines.extend((
                "otelcol-1  | ResourceSpans #0", "otelcol-1  | Resource attributes:",
                f"otelcol-1  |      -> service.name: Str({service})", "otelcol-1  | ScopeSpans #0", "otelcol-1  | Span #0",
                f"otelcol-1  |     Trace ID       : {trace}",
            ))
            if name is not None:
                lines.extend((
                    "otelcol-1  |     Parent ID      : ", f"otelcol-1  |     Name           : {name}",
                    f"otelcol-1  |     Kind           : {kind}", f"otelcol-1  |     Start time     : {_stamp(start)}",
                    f"otelcol-1  |     End time       : {_stamp(end)}",
                ))

        for token, traceparent, ok, at in self.served:
            route = self.routes.get(token)
            if not traceparent or route is None:
                continue
            trace = traceparent.split("-")[1]
            block("frontend-proxy", trace)
            if not ok and route != "checkout":
                continue
            if not ok:                       # a failed checkout still reached the frontend but nothing below it
                continue
            for service in self.mix["routes"][route]["requiredServices"][1:]:
                if (route, service) in self.lose_route_services or token in self.drop_traces:
                    continue
                if service == "frontend" and route in ("product", "recommendations"):
                    duration = SLOW_SERVER_SECONDS * 1.5 if self._slow(at) else 0.0012
                    block("frontend", trace, "grpc.oteldemo.ProductCatalogService/GetProduct", "Client", at, at + duration)
                elif service == "productcatalogservice":
                    duration = SLOW_SERVER_SECONDS if self._slow(at) else FAST_SERVER_SECONDS
                    block("productcatalogservice", trace, "oteldemo.ProductCatalogService/GetProduct", "Server", at, at + duration)
                else:
                    block(service, trace)
            if route == "checkout":
                for service in CONSUMERS:
                    start = self._consumer_start(service, at)
                    block(service, trace, "orders receive", "Consumer", start, start + 0.05)
        return "\n".join(lines) + "\n"


def _factory(remote, monkeypatch, **options):
    """A target class for ``b_tests._run`` that also routes the target's new POST function to the fake."""
    def make(contract, clock, **fake_options):
        target = OffpathTarget(contract, clock, **options, **fake_options)
        monkeypatch.setattr(remote, "http_post", target.http_post)
        return target
    return make


def _run(tree, contract, monkeypatch, *, pool_cap=256, **options):
    """A paused frontend holds rate x timeout = 1,500 requests at 100 req/s: its cell needs a pool that large (``pool_cap``)."""
    limits = _Limits(1024, 524288)
    monkeypatch.setattr(_CappedPool, "cap", pool_cap)
    remote = tree.remote
    monkeypatch.setattr(remote, "ensure_generator_open_files",
                        lambda timing, _real=remote.ensure_generator_open_files: _real(
                            timing, getrlimit=limits.get, setrlimit=limits.set))
    _CappedPool.asked = []
    monkeypatch.setattr(remote, "ThreadPoolExecutor", _CappedPool)
    receipt, target = b_tests._run(tree, contract, monkeypatch, target_class=_factory(remote, monkeypatch, **options))
    return receipt, target, limits


def _cell(tree, package, regime, rate, tmp_path):
    return b_tests._contract(tree, package, regime, rate, tmp_path, 1)


def _read(contract, name):
    return b_tests._read(contract, name)


# ------------------------------------------------------------------------------------- 9. every regime, end to end
@pytest.fixture(scope="module")
def cells(pilot_tree, pilot_package, tmp_path_factory):
    """One valid cell per regime at 100 req/s (the mix, 18,000 requests), executed once on the fake target."""
    out = {}
    for regime in REGIMES:
        with pytest.MonkeyPatch.context() as patch:            # one context per cell: each run re-patches the runner
            base = tmp_path_factory.mktemp("offpath-cell-" + regime)
            contract = _cell(pilot_tree, pilot_package, regime, 100.0, base)
            assert contract["studyEpoch"] == PILOT
            receipt, target, limits = _run(pilot_tree, contract, patch, pool_cap=2048 if regime == FRONTEND else 256)
            assert receipt["state"] == "valid", (regime, receipt["error"])
            out[regime] = types.SimpleNamespace(
                contract=contract, root=Path(contract["remoteArtifactRoot"]), target=target, limits=limits,
                asked=list(_CappedPool.asked), receipt=receipt)
    return out


def _validate(tree, root, contract):
    with b_tests.bound(tree):
        return tree.terminal.validate_cell(root, contract)


@pytest.mark.parametrize("regime", REGIMES)
def test_run_cell_executes_a_pilot_cell_of_every_regime_and_the_terminal_accepts_it(pilot_tree, cells, regime):
    cell = cells[regime]
    contract, root, target = cell.contract, cell.root, cell.target
    assert cell.limits.calls == [(5524, 524288)] and cell.asked.count(4500) == 2     # the warm-up and the measurement
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    ledger = json.loads((root / "request-ledger.json").read_text())
    assert ledger["kind"] == "otel-demo-mix-ledger-v1" and ledger["method"] == "MIX"
    assert ledger["offered"] == 18000 == len(ledger["requests"]) and ledger["concurrency"] == 4500
    plan = pilot_tree.remote.mix_plan(p.MIX, contract["runId"], 18000)
    assert ledger["routeCounts"] == dict(sorted(collections.Counter(row["route"] for row in plan).items()))
    assert [row["route"] for row in ledger["requests"]] == [row["route"] for row in plan]
    assert ledger["mixSha256"] == hashlib.sha256(pilot_tree.runtime.canonical_bytes(p.MIX)).hexdigest()
    report = _validate(pilot_tree, root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    assert report["correlation"]["requiredPathServices"] == sorted(set(p.mix_route_services()))
    # coverage is judged per request on its own route's services: every successful request of the pre-fault phase has its full path
    # (on the clipped path the recommendations and ads routes could never be full)
    phases = report["correlation"]["phases"]
    assert phases["pre-fault"]["successful"] > 5000 and phases["pre-fault"]["fullPath"] == phases["pre-fault"]["requests"]
    assert phases["pre-fault"]["partialPath"] == phases["pre-fault"]["noTrace"] == 0
    health = _read(contract, "container-health.json")
    updates = {row["service"]: row for row in health["memoryLimitUpdates"]}
    assert health["valid"] is True and set(updates) == {"frontendproxy", "otelcol", "jaeger"}
    assert all(row["after"]["memory"] == 1024 ** 3 and row["argv"][:4] == ["docker", "update", "--memory", str(1024 ** 3)]
               for row in updates.values())
    assert {row["service"]: row["memoryBytes"] for row in health["final"] if row["service"] in updates} == {
        service: 1024 ** 3 for service in updates}
    completeness = _read(contract, "trace-completeness.json")
    assert completeness["valid"] is True and completeness["incomplete"] == 0
    assert set(completeness["requiredServicesByRoute"]) == set(p.MIX["routes"])
    assert completeness["requiredServicesByRoute"]["checkout"] == sorted(p.MIX["routes"]["checkout"]["requiredServices"])
    if contract["fault"]["scenario"] is None:
        assert completeness["rule"] == "protocol-decision-56" or completeness["kind"] == "otel-demo-quiet-trace-completeness-v3"
        assert not (root / "intervention.json").exists() and target.events_started == 0
        return
    assert completeness["rule"] == "protocol-decision-25"
    assert b_tests._probes_inside_the_fault(target, contract) == []                         # H10
    intervention = _read(contract, "intervention.json")
    assert intervention["duringRouteAvailable"] is None and intervention["manifested"] is True
    assert intervention["freeze"]["stampCheck"]["status"] == "ok"                           # H4
    action = contract["fault"]["action"]
    if action == "pause":
        service = contract["fault"]["service"]
        record = json.loads((root / "docker-events.json").read_text())
        assert record["service"] == service and record["verdict"]["status"] == "ok" and target.events_started == 1
        assert [row["action"] for row in record["events"] if row["service"] == service] == ["pause", "unpause"]
        assert all(row["Paused"] for row in intervention["duringStateSamples"])
        assert any(argv[-2:] == ["pause", service] for argv in target.commands)
        assert any(argv[-2:] == ["unpause", service] for argv in target.commands)
    else:
        assert not (root / "docker-events.json").exists()
        assert intervention["throttle"]["duringNanoCpus"] == 100_000_000


def test_the_top_rate_cell_offers_27000_requests_with_the_4500_worker_cap_and_the_terminal_accepts_it(pilot_tree, pilot_package, tmp_path, monkeypatch):
    contract = _cell(pilot_tree, pilot_package, NO_FAULT, 150.0, tmp_path)
    receipt, _, limits = _run(pilot_tree, contract, monkeypatch)
    assert receipt["state"] == "valid", receipt["error"]
    assert limits.calls == [(5524, 524288)] and _CappedPool.asked.count(4500) == 2
    ledger = _read(contract, "request-ledger.json")
    assert ledger["offered"] == 27000 == len(ledger["requests"]) and ledger["ratePerSecond"] == 150.0
    assert _validate(pilot_tree, Path(contract["remoteArtifactRoot"]), contract)["state"] == "valid"


def test_the_open_loop_honours_every_checkouts_dependency_and_the_fake_cart_saw_every_order(cells):
    for regime in (NO_FAULT, FRAUD):
        cell = cells[regime]
        ledger = json.loads((cell.root / "request-ledger.json").read_text())
        rows = ledger["requests"]
        checkouts = [row for row in rows if row["route"] == "checkout"]
        assert len(checkouts) > 1000
        for row in checkouts:
            before = rows[row["dependsOn"]]
            assert before["route"] == "add-to-cart" and row["startedMonotonic"] >= before["endedMonotonic"]
            assert row["startedMonotonic"] >= ledger["barrierMonotonic"] + row["scheduledOffsetSeconds"] - 0.05
        # Every offered token is witnessed exactly once, POSTs included (the terminal checked it); no checkout found an empty cart.
        assert all(row["outcome"] == "ok" for row in checkouts) and cell.target.orders >= len(checkouts)   # plus the warm-up's
        assert not any(row["outcome"] != "ok" for row in rows)


def test_the_consumers_spans_are_retained_for_every_accepted_checkout_and_the_pause_moves_the_target_s_out_of_the_hold(cells):
    for regime, service in ((FRAUD, "frauddetectionservice"), (ACCOUNTING, "accountingservice")):
        cell = cells[regime]
        spans = parse_spans((cell.root / "otelcol.log").read_bytes().decode("utf-8", errors="replace"))
        mine = [s for s in spans if s["service"] == service and s["kind"] == "Consumer"]
        other = [s for s in spans if s["service"] in CONSUMERS and s["service"] != service and s["kind"] == "Consumer"]
        checkouts = [row for row in json.loads((cell.root / "request-ledger.json").read_text())["requests"] if row["route"] == "checkout"]
        assert len(mine) == len(other) >= len(checkouts) > 1000          # plus the warm-up's accepted checkouts
        stats = statistics_of(cell.root, cell.contract)
        assert stats["consumer"][service]["hold"] <= 0.1 * stats["consumer"][service]["pre"]
        assert stats["consumer"][service]["pre"] >= 300          # ~5.9 orders/s x 60 s
        unpaused = next(c for c in CONSUMERS if c != service)
        assert stats["consumer"][unpaused]["hold"] >= 0.9 * stats["consumer"][unpaused]["pre"]


def test_the_pause_of_a_consumer_does_not_make_the_route_unavailable_but_the_frontend_pause_does(cells):
    for regime in (FRAUD, ACCOUNTING):
        stats = statistics_of(cells[regime].root, cells[regime].contract)
        assert stats["checkout"]["rows"] >= 300 and stats["checkout"]["ok"] == stats["checkout"]["rows"]
        assert stats["rows"]["ok"] == stats["rows"]["rows"]
    stats = statistics_of(cells[FRONTEND].root, cells[FRONTEND].contract)
    assert stats["earlyRows"]["rows"] >= 4500 and stats["earlyRows"]["ok"] <= 0.1 * stats["earlyRows"]["rows"]
    assert stats["earlyCheckout"]["rows"] >= 100 and stats["earlyCheckout"]["ok"] <= 0.10 * stats["earlyCheckout"]["rows"]
    # the last 15 s of the hold are served after the unpause inside the request's own timeout: the hold as a whole is not all failures
    assert stats["rows"]["ok"] > stats["earlyRows"]["ok"]


# ------------------------------------------------------------------------------------- 10. the manifestation criteria
# The criteria (analysis.manifestationCriterionDefaults) computed from what a cell retains: otelcol.log (spans: service, name,
# kind, start), request-ledger.json (rows with route and schedule) and intervention.json (the onset command's stamp).  This
# is the computation the declaration freezes; the pilot's own script is written after the fetch and must agree with it.
def _parse_stamp(text: str) -> float:
    match = re.fullmatch(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:\.(\d+))? \+0000 UTC", text.strip())
    assert match, text
    moment = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return moment.timestamp() + (int(match.group(2)[:9].ljust(9, "0")) / 1e9 if match.group(2) else 0.0)


def parse_spans(text: str) -> list:
    """Spans of the collector's debug exporter (a ``Span #n`` block: Name, Kind, Start time, End time) with the service.name of
    the ResourceSpans block they belong to; a block that lacks a field is not a complete span and is skipped."""
    spans, service, current = [], None, None
    for line in text.splitlines():
        payload = line.partition("| ")[2] if "| " in line else line
        match = re.match(r"\s*-> service\.name: Str\((.*)\)\s*$", payload)
        if match:
            service, current = match.group(1), None
            continue
        if payload.startswith("ResourceSpans #"):
            service, current = None, None
        elif re.match(r"\s*Span #\d+\s*$", payload):
            current = {"service": service}
        elif current is not None:
            field = re.match(r"\s+(Name|Kind|Start time|End time)\s+: (.*)$", payload)
            if field:
                key = {"Name": "name", "Kind": "kind", "Start time": "start", "End time": "end"}[field.group(1)]
                current[key] = _parse_stamp(field.group(2)) if key in ("start", "end") else field.group(2).strip()
                if all(k in current for k in ("name", "kind", "start", "end")):
                    spans.append(current)
                    current = None
    return spans


def statistics_of(root: Path, contract) -> dict:
    """Every statistic of the declared criteria for one cell."""
    timing = contract["timing"]
    ledger = json.loads((root / "request-ledger.json").read_text())
    if contract["fault"]["scenario"] is None:
        onset = timing["scoredWindowSeconds"][0]                                    # the pseudo onset
    else:
        onset = json.loads((root / "intervention.json").read_text())["freeze"]["commandIssuedOffsetSeconds"]
    hold_seconds = 60.0
    t0 = ledger["barrierEpoch"] + onset
    pre, hold = (t0 - 60.0, t0), (t0, t0 + hold_seconds)
    spans = parse_spans((root / "otelcol.log").read_bytes().decode("utf-8", errors="replace"))

    def within(span, window):
        return window[0] <= span["start"] < window[1]

    def median(values):
        return statistics.median(values) if len(values) >= 20 else None

    server = [s for s in spans if (s["service"], s["name"], s["kind"]) == (
        "productcatalogservice", "oteldemo.ProductCatalogService/GetProduct", "Server")]
    client = [s for s in spans if (s["service"], s["name"], s["kind"]) == (
        "frontend", "grpc.oteldemo.ProductCatalogService/GetProduct", "Client")]

    def ratio(group):
        before = median([s["end"] - s["start"] for s in group if within(s, pre)])
        during = median([s["end"] - s["start"] for s in group if within(s, hold)])
        return None if before is None or during is None else during / before

    rows = ledger["requests"]
    in_hold = [r for r in rows if onset <= r["scheduledOffsetSeconds"] < onset + hold_seconds]
    early = [r for r in rows if onset <= r["scheduledOffsetSeconds"] < onset + hold_seconds - timing["requestTimeoutSeconds"]]
    checkouts = [r for r in in_hold if r["route"] == "checkout"]
    # checkout rows of the frontend-pause criterion are selected by SEND time (a checkout waits for its cart POST: up to 20 s after its slot)
    barrier_epoch = ledger["barrierEpoch"]
    early_checkouts = [
        r for r in rows if r["route"] == "checkout"
        and onset <= r["startedAtEpoch"] - barrier_epoch < onset + hold_seconds - timing["requestTimeoutSeconds"]
    ]
    return {
        "onset": onset,
        "consumer": {
            service: {
                "pre": sum(1 for s in spans if s["service"] == service and s["kind"] == "Consumer" and within(s, pre)),
                "hold": sum(1 for s in spans if s["service"] == service and s["kind"] == "Consumer" and within(s, hold)),
            } for service in CONSUMERS
        },
        "serverRatio": ratio(server), "clientRatio": ratio(client),
        "checkout": {"rows": len(checkouts), "ok": sum(r["outcome"] == "ok" for r in checkouts)},
        "rows": {"rows": len(in_hold), "ok": sum(r["outcome"] == "ok" for r in in_hold)},
        "earlyRows": {"rows": len(early), "ok": sum(r["outcome"] == "ok" for r in early)},
        "earlyCheckout": {"rows": len(early_checkouts), "ok": sum(r["outcome"] == "ok" for r in early_checkouts)},
    }


def verdict(fault: str, stats: dict, nofault: dict) -> str:
    """The declared per-(fault, rate) verdict: 'manifests', 'does not manifest' or '—'.  A valid no-fault cell that fails its
    precondition (checkout rows and all rows >= 95 % ok in its pseudo hold) gives '—' for every fault at that rate."""
    def share(block):
        return None if block["rows"] < 20 else block["ok"] / block["rows"]

    healthy = [share(nofault["checkout"]), share(nofault["rows"])]
    if None in healthy or min(healthy) < 0.95:
        return "—"

    if fault in ("fraud-pause", "accounting-pause"):
        service = "frauddetectionservice" if fault == "fraud-pause" else "accountingservice"
        pre, during = stats["consumer"][service]["pre"], stats["consumer"][service]["hold"]
        base_pre, base_during = nofault["consumer"][service]["pre"], nofault["consumer"][service]["hold"]
        if pre < 20 or base_pre < 20 or share(stats["checkout"]) is None or share(nofault["checkout"]) is None:
            return "—"
        effect = during <= 0.1 * pre
        route_ok = share(stats["checkout"]) >= 0.95
        none_in_nofault = base_during > 0.1 * base_pre and share(nofault["checkout"]) >= 0.95
        return "manifests" if effect and route_ok and none_in_nofault else "does not manifest"
    if fault == "productcatalog-cpu-throttle":
        if None in (stats["serverRatio"], stats["clientRatio"], nofault["serverRatio"], nofault["clientRatio"]):
            return "—"
        effect = stats["serverRatio"] >= 2.0 and stats["clientRatio"] >= 1.25
        quiet_ = nofault["serverRatio"] < 2.0 and nofault["clientRatio"] < 1.25
        return "manifests" if effect and quiet_ else "does not manifest"
    if fault == "frontend-pause":
        if share(stats["earlyRows"]) is None or share(nofault["earlyRows"]) is None or share(stats["earlyCheckout"]) is None:
            return "—"
        effect = share(stats["earlyRows"]) <= 0.10 and share(stats["earlyCheckout"]) <= 0.10
        return "manifests" if effect and share(nofault["earlyRows"]) >= 0.95 else "does not manifest"
    raise AssertionError(fault)


REAL_ACCOUNTING_SPAN = """otelcol-1  | ResourceSpans #0
otelcol-1  | Resource SchemaURL: 
otelcol-1  | Resource attributes:
otelcol-1  |      -> process.runtime.name: Str(.NET)
otelcol-1  |      -> service.name: Str(accountingservice)
otelcol-1  |      -> docker.cli.cobra.command_path: Str(docker%20compose)
otelcol-1  | ScopeSpans #0
otelcol-1  | ScopeSpans SchemaURL: 
otelcol-1  | InstrumentationScope OpenTelemetry.AutoInstrumentation.Kafka 
otelcol-1  | Span #0
otelcol-1  |     Trace ID       : 4fcb8ec0ebb07ff8dc186a865965487f
otelcol-1  |     Parent ID      : 
otelcol-1  |     ID             : ee45dfb21c492fb8
otelcol-1  |     Name           : orders receive
otelcol-1  |     Kind           : Consumer
otelcol-1  |     Start time     : 2026-10-01 17:12:42.8160382 +0000 UTC
otelcol-1  |     End time       : 2026-10-01 17:12:43.0075244 +0000 UTC
otelcol-1  |     Status code    : Error
otelcol-1  | Attributes:
otelcol-1  |      -> messaging.operation: Str(receive)
otelcol-1  | Events:
otelcol-1  | SpanEvent #0
otelcol-1  |      -> Name: exception
otelcol-1  |      -> Timestamp: 2026-10-01 17:12:43.0063459 +0000 UTC
otelcol-1  | 	{"kind": "exporter", "data_type": "traces", "name": "debug"}
otelcol-1  | 2026-10-01T17:12:46.701Z	info	MetricsExporter	{"kind": "exporter", "data_type": "metrics", "name": "debug"}
otelcol-1  | Metric #0
otelcol-1  | Descriptor:
otelcol-1  |      -> Name: process.runtime.dotnet.gc.collections.count
"""


def test_the_span_parser_reads_the_collector_debug_exporters_real_format():
    """The block is the retained v3a2 b02-02-full otelcol.log's accountingservice span (a 'receive' span of Kind Consumer), plus the
    shapes that must not read as spans: a span event's '-> Name:' and a metric descriptor's '-> Name:'."""
    spans = parse_spans(REAL_ACCOUNTING_SPAN)
    assert len(spans) == 1
    assert (spans[0]["service"], spans[0]["name"], spans[0]["kind"]) == ("accountingservice", "orders receive", "Consumer")
    assert spans[0]["end"] - spans[0]["start"] == pytest.approx(0.1914862, abs=1e-6)
    assert spans[0]["start"] == pytest.approx(datetime(2026, 10, 1, 17, 12, 42, tzinfo=timezone.utc).timestamp() + 0.8160382)


@pytest.mark.parametrize("fault,regime", (
    ("fraud-pause", FRAUD), ("accounting-pause", ACCOUNTING), ("productcatalog-cpu-throttle", THROTTLE),
    ("frontend-pause", FRONTEND),
))
def test_each_fault_manifests_by_its_declared_criterion_and_the_no_fault_cell_shows_neither(cells, fault, regime):
    quiet_stats = statistics_of(cells[NO_FAULT].root, cells[NO_FAULT].contract)
    stats = statistics_of(cells[regime].root, cells[regime].contract)
    assert verdict(fault, stats, quiet_stats) == "manifests", (stats, quiet_stats)
    # the no-fault cell: the consumers keep working in its pseudo hold, checkouts succeed, the product spans do not slow
    for service in CONSUMERS:
        assert quiet_stats["consumer"][service]["hold"] >= 0.9 * quiet_stats["consumer"][service]["pre"] >= 270
    assert quiet_stats["checkout"]["ok"] == quiet_stats["checkout"]["rows"] >= 300
    assert quiet_stats["serverRatio"] == pytest.approx(1.0, abs=0.01) and quiet_stats["clientRatio"] == pytest.approx(1.0, abs=0.01)
    # a fault cell is not the criterion of another fault
    other = "fraud-pause" if fault != "fraud-pause" else "accounting-pause"
    if regime in (THROTTLE, FRONTEND):
        assert verdict(other, stats, quiet_stats) != "manifests"
    assert stats["onset"] == _read(cells[regime].contract, "intervention.json")["freeze"]["commandIssuedOffsetSeconds"]


def test_every_statistic_is_computable_from_the_retained_artifacts_alone(cells):
    """No statistic reads anything but otelcol.log, request-ledger.json and intervention.json / timing."""
    for regime in REGIMES:
        stats = statistics_of(cells[regime].root, cells[regime].contract)
        assert stats["rows"]["rows"] >= 5900 and stats["checkout"]["rows"] >= 300
        assert all(row["pre"] >= 270 for row in stats["consumer"].values())
        assert stats["serverRatio"] is not None and stats["clientRatio"] is not None


def test_planted_defect_a_consumer_that_keeps_working_through_its_pause_does_not_manifest(pilot_tree, pilot_package, cells, tmp_path, monkeypatch):
    contract = _cell(pilot_tree, pilot_package, FRAUD, 100.0, tmp_path)
    receipt, target, _ = _run(pilot_tree, contract, monkeypatch, consumers_ignore_pause=True)
    assert receipt["state"] == "valid", receipt["error"]
    stats = statistics_of(Path(contract["remoteArtifactRoot"]), contract)
    quiet_stats = statistics_of(cells[NO_FAULT].root, cells[NO_FAULT].contract)
    assert stats["consumer"]["frauddetectionservice"]["hold"] >= 0.9 * stats["consumer"]["frauddetectionservice"]["pre"]
    assert verdict("fraud-pause", stats, quiet_stats) == "does not manifest"
    assert verdict("fraud-pause", statistics_of(cells[FRAUD].root, cells[FRAUD].contract), quiet_stats) == "manifests"


def test_planted_defect_a_pause_that_takes_checkout_down_with_it_does_not_manifest_and_the_cell_stays_valid(
    pilot_tree, pilot_package, cells, tmp_path, monkeypatch,
):
    """The route-stays-up condition: if the paused consumer made checkout fail (here: 100 % of the hold), the effect is on the
    route, not off it; G1/G2/G4 look only at the whole mix and the pre-onset share, so the cell is valid and the criterion says no."""
    contract = _cell(pilot_tree, pilot_package, ACCOUNTING, 100.0, tmp_path)
    receipt, _, _ = _run(pilot_tree, contract, monkeypatch, checkout_fails_while_paused=("accountingservice",))
    assert receipt["state"] == "valid", receipt["error"]
    stats = statistics_of(Path(contract["remoteArtifactRoot"]), contract)
    assert stats["checkout"]["ok"] <= 0.05 * stats["checkout"]["rows"] and stats["checkout"]["rows"] > 300   # the pause takes a moment to bite
    quiet_stats = statistics_of(cells[NO_FAULT].root, cells[NO_FAULT].contract)
    assert verdict("accounting-pause", stats, quiet_stats) == "does not manifest"


def test_planted_defect_a_throttle_that_does_not_bind_does_not_manifest(pilot_tree, pilot_package, cells, tmp_path, monkeypatch):
    contract = _cell(pilot_tree, pilot_package, THROTTLE, 100.0, tmp_path)
    receipt, _, _ = _run(pilot_tree, contract, monkeypatch, no_throttle_effect=True)
    assert receipt["state"] == "valid", receipt["error"]
    stats = statistics_of(Path(contract["remoteArtifactRoot"]), contract)
    quiet_stats = statistics_of(cells[NO_FAULT].root, cells[NO_FAULT].contract)
    assert stats["serverRatio"] == pytest.approx(1.0, abs=0.01)
    assert verdict("productcatalog-cpu-throttle", stats, quiet_stats) == "does not manifest"


def test_a_statistic_below_its_minimum_gives_a_dash_not_a_verdict():
    quiet_stats = {"consumer": {s: {"pre": 350, "hold": 350} for s in CONSUMERS}, "checkout": {"rows": 350, "ok": 350},
                   "rows": {"rows": 6000, "ok": 6000}, "serverRatio": 1.0, "clientRatio": 1.0}
    sparse = {"consumer": {s: {"pre": 5, "hold": 0} for s in CONSUMERS}, "checkout": {"rows": 350, "ok": 350},
              "rows": {"rows": 6000, "ok": 6000}, "serverRatio": None, "clientRatio": None}
    assert verdict("fraud-pause", sparse, quiet_stats) == "—"
    assert verdict("productcatalog-cpu-throttle", sparse, quiet_stats) == "—"


def test_a_valid_no_fault_cell_that_fails_its_precondition_gives_a_dash_for_every_fault():
    """S2: a baseline that already fails (checkout or all rows below 95 % ok) cannot be told from a fault's effect."""
    good = {"consumer": {s: {"pre": 350, "hold": 350} for s in CONSUMERS}, "checkout": {"rows": 350, "ok": 350},
            "rows": {"rows": 6000, "ok": 6000}, "earlyRows": {"rows": 4500, "ok": 4500}, "earlyCheckout": {"rows": 260, "ok": 260},
            "serverRatio": 1.0, "clientRatio": 1.0}
    fault = {"consumer": {s: {"pre": 350, "hold": 0} for s in CONSUMERS}, "checkout": {"rows": 350, "ok": 350},
             "rows": {"rows": 6000, "ok": 6000}, "earlyRows": {"rows": 4500, "ok": 100}, "earlyCheckout": {"rows": 260, "ok": 0},
             "serverRatio": 3.0, "clientRatio": 2.0}
    assert verdict("fraud-pause", fault, good) == "manifests" and verdict("frontend-pause", fault, good) == "manifests"
    assert verdict("productcatalog-cpu-throttle", fault, good) == "manifests"
    for broken in ({**good, "checkout": {"rows": 350, "ok": 300}}, {**good, "rows": {"rows": 6000, "ok": 5600}}):
        for name in ("fraud-pause", "accounting-pause", "productcatalog-cpu-throttle", "frontend-pause"):
            assert verdict(name, fault, broken) == "—", (name, broken)
    assert verdict("fraud-pause", fault, {**good, "checkout": {"rows": 10, "ok": 10}}) == "—"        # too few rows


def test_the_frontend_pause_checkouts_are_selected_by_send_time_not_scheduled_time(tmp_path):
    """B1: a checkout waits for its cart POST (up to 20 s past its slot).  One scheduled before the onset but sent in the first 45 s
    counts (it failed); one scheduled in the first 45 s but sent after it does not (it was served after the unpause)."""
    onset, barrier = 60.0, 1_000_000.0
    def row(route, scheduled, sent, outcome):
        return {"route": route, "scheduledOffsetSeconds": scheduled, "startedAtEpoch": barrier + sent, "outcome": outcome}
    rows = [row("checkout", onset - 5.0, onset + 10.0, "timeout"),        # scheduled before, sent inside: counts, failed
            row("checkout", onset + 30.0, onset + 50.0, "ok"),             # scheduled inside, sent after 45 s: does not count
            row("product", onset + 1.0, onset + 1.0, "timeout")]
    (tmp_path / "request-ledger.json").write_text(json.dumps({"barrierEpoch": barrier, "requests": rows}))
    (tmp_path / "otelcol.log").write_text("")
    contract = {"fault": {"scenario": None}, "timing": {"scoredWindowSeconds": [onset, onset + 60.0], "requestTimeoutSeconds": 15.0}}
    stats = statistics_of(tmp_path, contract)
    assert stats["earlyCheckout"] == {"rows": 1, "ok": 0}
    assert stats["checkout"] == {"rows": 1, "ok": 1}                       # the scheduled-time selection sees the other row


# ------------------------------------------------------------------------------------- 11. planted defects in retained artifacts
def _plant(tree, cell_root: Path, contract, name: str, mutate) -> None:
    helpers._plant(tree, cell_root, contract, name, mutate)


def _row_where(ledger, route, skip=0):
    return [row for row in ledger["requests"] if row["route"] == route][skip]


def _break_dependency(ledger):
    """The cart POST 'ends' after its checkout had started: the checkout did not wait."""
    checkout = _row_where(ledger, "checkout", 3)
    before = ledger["requests"][checkout["dependsOn"]]
    before["endedMonotonic"] = checkout["startedMonotonic"] + 1.0
    before["endedAtEpoch"] = checkout["startedAtEpoch"] + 1.0


LEDGER_PLANTS = {
    "a-row-of-another-route": (
        lambda v: _row_where(v, "product", 5).update(route="ads"), "route, task, request or predecessor differs"),
    "a-row-with-another-target": (
        lambda v: _row_where(v, "product", 5).update(target="/api/products/OLJCESPC7Z-planted"), "route, task, request or predecessor"),
    "a-checkout-body-edited": (
        lambda v: _row_where(v, "checkout", 2).update(bodySha256="0" * 64), "route, task, request or predecessor"),
    "a-checkout-without-its-predecessor": (
        lambda v: _row_where(v, "checkout", 2).update(dependsOn=None), "route, task, request or predecessor"),
    "a-checkout-that-did-not-wait": (_break_dependency, "started before the request it depends on had ended"),
    "a-task-relabelled": (
        lambda v: _row_where(v, "checkout", 2).update(task="checkout_multi"), "route, task, request or predecessor"),
    "task-counts-edited": (lambda v: v["taskCounts"].update(checkout=1), "task and route counts do not replay"),
    "route-counts-edited": (lambda v: v["routeCounts"].update(index=1), "task and route counts do not replay"),
    "another-mix": (lambda v: v.update(mixSha256="0" * 64), "mix ledger identity"),
    "a-sweep-ledger-kind": (lambda v: v.update(kind="otel-demo-route-ledger-v1"), "mix ledger identity"),
    "a-missing-request": (
        lambda v: (v["requests"].pop(), v.update(offered=v["offered"] - 1)), "mix ledger identity"),
    "a-rescheduled-request": (
        lambda v: v["requests"][3].update(scheduledOffsetSeconds=3.5), "identity or schedule"),
    "a-row-without-its-route": (lambda v: v["requests"][7].pop("route"), "mix ledger row"),
    "an-outcome-not-replaying": (lambda v: v["requests"][2].update(outcome="timeout"), "outcome does not replay"),
}


@pytest.mark.parametrize("plant", sorted(LEDGER_PLANTS))
def test_planted_ledger_defects_are_rejected_by_the_terminal(pilot_tree, cells, tmp_path, plant):
    mutate, message = LEDGER_PLANTS[plant]
    source = cells[FRAUD]
    cell_root = tmp_path / "cell"
    shutil.copytree(source.root, cell_root)
    assert _validate(pilot_tree, cell_root, source.contract)["state"] == "valid"
    _plant(pilot_tree, cell_root, source.contract, "request-ledger.json", mutate)
    with pytest.raises(pilot_tree.terminal.ValidationError, match=message):
        _validate(pilot_tree, cell_root, source.contract)


def test_planted_defect_a_telemetry_backend_limit_that_was_not_applied_is_rejected_by_the_terminal(pilot_tree, cells, tmp_path):
    source = cells[NO_FAULT]
    cell_root = tmp_path / "cell"
    shutil.copytree(source.root, cell_root)
    _plant(pilot_tree, cell_root, source.contract, "container-health.json",
           lambda v: v.update(memoryLimitUpdates=[row for row in v["memoryLimitUpdates"] if row["service"] != "otelcol"]))
    with pytest.raises(pilot_tree.terminal.ValidationError, match="declared memory limits were not applied"):
        _validate(pilot_tree, cell_root, source.contract)
    shutil.rmtree(cell_root)
    shutil.copytree(source.root, cell_root)
    _plant(pilot_tree, cell_root, source.contract, "container-health.json",
           lambda v: [row.update(memoryBytes=419430400) for row in v["final"] if row["service"] == "jaeger"])
    with pytest.raises(pilot_tree.terminal.ValidationError, match="container health"):
        _validate(pilot_tree, cell_root, source.contract)


def test_planted_defect_a_witness_that_lost_a_post_is_rejected_by_the_terminal(pilot_tree, cells, tmp_path):
    source = cells[NO_FAULT]
    cell_root = tmp_path / "cell"
    shutil.copytree(source.root, cell_root)
    ledger = json.loads((cell_root / "request-ledger.json").read_text())
    token = _row_where(ledger, "checkout", 4)["requestToken"]

    def lose(witness):
        witness["rows"] = [row for row in witness["rows"] if row["request_token"] != token]
        witness["witnessedTokens"] -= 1
    _plant(pilot_tree, cell_root, source.contract, "application-witness.json", lose)
    with pytest.raises(pilot_tree.terminal.ValidationError, match="application witness does not establish the offered denominator"):
        _validate(pilot_tree, cell_root, source.contract)


def test_planted_defect_the_mix_dropped_from_a_contract_is_a_sweep_cell_the_terminal_would_misjudge(pilot_tree, cells, tmp_path):
    source = cells[FRAUD]
    contract = copy.deepcopy(source.contract)
    del contract["timing"]["workloadMix"]
    with pytest.raises(pilot_tree.terminal.ValidationError, match="cell timing replay failed: cell timing fields differ"):
        _validate(pilot_tree, source.root, contract)


def test_planted_defect_a_runner_that_ignores_the_dependency_sends_checkouts_into_empty_carts_and_fails_g2(
    pilot_tree, pilot_package, tmp_path, monkeypatch,
):
    """Source plant: the open loop sends every request at its slot without waiting for its predecessor.  With a cart POST slower
    than one slot (20 ms real = 0.6 s simulated against a 10 ms slot) every checkout finds an empty cart: 5.9 % of the mix fails
    before the onset, G2's bound is 5 %, the cell is invalid on the target."""
    remote = pilot_tree.remote
    original = remote.one_mix_request
    monkeypatch.setattr(remote, "one_mix_request", lambda *args: original(*args[:-2], None, args[-1]))
    contract = _cell(pilot_tree, pilot_package, NO_FAULT, 100.0, tmp_path)
    receipt, _, _ = _run(pilot_tree, contract, monkeypatch, cart_post_seconds=0.02)
    assert receipt["state"] == "invalid" and "protocol gate(s) G2 did not pass" in receipt["error"]
    ledger = _read(contract, "request-ledger.json")
    checkouts = [row for row in ledger["requests"] if row["route"] == "checkout"]
    assert sum(row["outcome"] != "ok" for row in checkouts) > 0.9 * len(checkouts)
    # and the same plant at an unloaded cart (fast POST) shows why the terminal checks the order too: a checkout that started
    # before its predecessor ended is refused even when the fake cart happened to be ready (LEDGER_PLANTS)


def test_planted_defect_a_runner_that_falls_back_to_the_single_route_is_refused_by_the_terminal(
    pilot_tree, pilot_package, tmp_path, monkeypatch,
):
    contract = _cell(pilot_tree, pilot_package, NO_FAULT, 100.0, tmp_path)
    monkeypatch.setattr(pilot_tree.remote, "has_mix", lambda timing: False)
    receipt, _, _ = _run(pilot_tree, contract, monkeypatch)
    ledger = _read(contract, "request-ledger.json")
    assert ledger["kind"] == "otel-demo-route-ledger-v1" and "routeCounts" not in ledger        # one product route, no mix
    monkeypatch.undo()
    with pytest.raises(pilot_tree.terminal.ValidationError, match="mix ledger"):
        _validate(pilot_tree, Path(contract["remoteArtifactRoot"]), contract)


# ------------------------------------------------------------------ 12. per-route trace completeness (decisions 25 and 56)
def test_a_route_whose_required_service_never_reaches_the_collector_is_recorded_in_a_no_fault_cell_by_route(
    pilot_tree, pilot_package, tmp_path, monkeypatch,
):
    """Decision 56 (no-fault cells): the add-to-cart route (17.7 % of the mix) loses its cartservice spans; recorded, never
    blocking, counted per missing service and per route."""
    contract = _cell(pilot_tree, pilot_package, NO_FAULT, 100.0, tmp_path)
    receipt, _, _ = _run(pilot_tree, contract, monkeypatch, lose_route_services={("add-to-cart", "cartservice")})
    assert receipt["state"] == "valid", receipt["error"]
    record = _read(contract, "trace-completeness.json")
    window = record["windows"]["whole-measurement"]
    ledger = _read(contract, "request-ledger.json")
    adds = [row for row in ledger["requests"] if row["route"] == "add-to-cart"]
    assert window["incomplete"] == len(adds) > 3000 and window["incompleteByMissingService"]["cartservice"] == len(adds)
    assert record["decision25Counterfactual"]["wouldHaveBlocked"] is True and record["valid"] is True
    assert {row["missingServices"][0] for row in window["incompleteRequests"]} == {"cartservice"}
    assert _validate(pilot_tree, Path(contract["remoteArtifactRoot"]), contract)["state"] == "valid"


def test_the_same_loss_blocks_a_fault_cell_under_decision_25(pilot_tree, pilot_package, tmp_path, monkeypatch):
    contract = _cell(pilot_tree, pilot_package, FRAUD, 100.0, tmp_path)
    receipt, _, _ = _run(pilot_tree, contract, monkeypatch, lose_route_services={("add-to-cart", "cartservice")})
    record = _read(contract, "trace-completeness.json")
    assert receipt["state"] == "invalid" and "trace completeness:" in receipt["error"] and "exceeds the allowance" in receipt["error"]
    assert record["rule"] == "protocol-decision-25" and record["valid"] is False and record["incomplete"] > record["allowance"]
    assert record["recordedFaultEffectIncomplete"] > 0           # the fault-and-drain window is recorded, never blocking


def test_extra_services_in_a_trace_are_neither_required_nor_unexpected(pilot_tree):
    remote = pilot_tree.remote
    timing = {"workloadMix": p.MIX, "route": {"services": []}}
    active = set(p.mix_route_services()) | {"flagd", "accountingservice", "frauddetectionservice", "kafka"}
    required, by_route = remote.completeness_requirements(timing, active)
    assert by_route["product"] == ["frontend", "frontendproxy", "productcatalogservice"] and set(by_route) == set(p.MIX["routes"])
    request = {"originalTraceId": "t" * 32, "route": "product"}
    row = {"observedOriginalTraceIds": ["t" * 32], "observedPathServices": ["frontend"], "observedTraceServices": [
        "accountingservice", "flagd", "frontend", "frontendproxy", "productcatalogservice"]}
    assert remote.request_is_complete(request, row, required, by_route) is True
    assert remote.request_is_complete(request, {**row, "observedTraceServices": ["frontend", "frontendproxy"]}, required, by_route) is False
    assert remote.request_is_complete(request, {**row, "observedOriginalTraceIds": []}, required, by_route) is False
    assert remote.request_is_complete(request, None, required, by_route) is False
    # the single-route rule (every earlier epoch) is unchanged: exactly the clipped route services
    single = {"route": {"services": ["frontendproxy", "frontend", "productcatalogservice"]}}
    required1, none = remote.completeness_requirements(single, active)
    assert none is None and required1 == ["frontend", "frontendproxy", "productcatalogservice"]
    row1 = {"observedOriginalTraceIds": ["t" * 32], "observedPathServices": required1}
    assert remote.request_is_complete(request, row1, required1, None) is True
    assert remote.request_is_complete(request, {**row1, "observedPathServices": required1 + ["flagd"]}, required1, None) is False


# ------------------------------------------------------------------------------------- 13. the generator on the target
def test_the_generator_open_files_minimum_is_raised_to_5524_and_a_lower_hard_limit_refuses_the_cell(pilot_tree, pilot_package, tmp_path, monkeypatch):
    remote = pilot_tree.remote
    timing = {"concurrency": 4500, "generatorOpenFilesMinimum": 5524}
    limits = _Limits(1024, 524288)
    record = remote.ensure_generator_open_files(timing, getrlimit=limits.get, setrlimit=limits.set)
    assert limits.calls == [(5524, 524288)] and record["after"] == {"soft": 5524, "hard": 524288}
    contract = _cell(pilot_tree, pilot_package, THROTTLE, 100.0, tmp_path)
    low = _Limits(1024, 4096)
    monkeypatch.setattr(remote, "ensure_generator_open_files",
                        lambda timing, _real=remote.ensure_generator_open_files: _real(timing, getrlimit=low.get, setrlimit=low.set))
    receipt, target = b_tests._run(pilot_tree, contract, monkeypatch, target_class=_factory(remote, monkeypatch))
    assert receipt["state"] == "invalid" and "hard limit 4096" in receipt["error"]
    assert not any(argv[:2] == ["docker", "compose"] and "up" in argv for argv in target.commands)


def test_a_dependent_request_that_never_sees_its_predecessor_end_is_sent_after_the_bounded_wait(remote_module, monkeypatch):
    """The wait is bounded by the client timeout plus the slack and the request is sent whatever happened to its predecessor
    (upstream's behaviour; no row is skipped, so every offered token is witnessed)."""
    remote = remote_module
    seen = []
    monkeypatch.setattr(remote, "http_exchange", lambda *args: seen.append(args) or (200, 1, None))
    waited = []

    class Never(threading.Event):
        def wait(self, timeout=None):
            waited.append(timeout)
            return False

    item = {"method": "POST", "target": "/api/checkout", "body": b"{}", "route": "checkout", "task": "checkout",
            "taskIndex": 0, "step": 2, "bodySha256": "0" * 64, "dependsOn": 1}
    now = real_time.monotonic()
    row = remote.one_mix_request("http://x", 15.0, now, 0.0, 0.0, item, ("tok", "t" * 32, "00-" + "t" * 32 + "-" + "s" * 16 + "-01"),
                                 Never(), threading.Event())
    assert waited == [15.0 + remote.MIX_DEPENDENCY_SLACK_SECONDS] and len(seen) == 1 and row["outcome"] == "ok"
    assert row["dependsOn"] == 1 and row["route"] == "checkout"


# ------------------------------------------------------------------------------------- 14. the rendered tree
@pytest.fixture(scope="module")
def materialized_pilot(tmp_path_factory):
    out = {}
    for label, epoch in (("pilot", PILOT), ("load", LOAD), ("c", C)):
        tree = helpers._copy_tree(
            tmp_path_factory.mktemp("materialize-offpath-" + label),
            selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n",
        )
        out[label] = tree / "out"
        out[label + "-digest"] = b_tests._materialize(tree, out[label])
    return out


def _overlay(out: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((out / "compose.otel-placement.yml").read_text())


def test_the_pilots_tree_is_the_load_pilots_collector_and_proxy_retention_and_its_source_digest_is_the_load_pilots(materialized_pilot):
    materialize = load("otel_offpath_pilot_materialize_module", MODULE / "materialize.py")
    assert PILOT in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS and PILOT in materialize.FRONTENDPROXY_LOG_RETENTION_EPOCHS
    pilot, load_out, c_out = materialized_pilot["pilot"], materialized_pilot["load"], materialized_pilot["c"]
    assert b_tests._log_sampling_enabled(b_tests._collector_config(pilot)) is False     # the sampler would drop the consumers' spans
    assert b_tests._collector_config(pilot) == b_tests._collector_config(c_out)
    assert _overlay(pilot)["services"]["frontendproxy"]["logging"] == {
        "driver": "json-file", "options": {"max-size": "4g", "max-file": "1"}}
    assert "logging" not in _overlay(c_out)["services"]["frontendproxy"]
    # The same rendered tree as the load pilot's, byte for byte: the host's images for that source digest are reusable.
    assert materialized_pilot["pilot-digest"] == materialized_pilot["load-digest"] != materialized_pilot["c-digest"]
    files = sorted(str(q.relative_to(load_out)) for q in load_out.rglob("*") if q.is_file())
    assert [name for name in files if (pilot / name).read_bytes() != (load_out / name).read_bytes()] == []


def test_planted_defect_without_the_pilot_in_the_sampling_tuple_the_collector_keeps_its_log_sampler(tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": PILOT}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    marker = '"otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1", "otel-load-pilot-v1", "otel-offpath-pilot-v1",\n    "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, '"otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1", "otel-load-pilot-v1", "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")'))
    b_tests._materialize(tree, tree / "out")
    assert b_tests._log_sampling_enabled(b_tests._collector_config(tree / "out")) is None


def test_planted_defect_without_the_pilot_in_the_retention_tuple_frontendproxy_keeps_upstreams_rotation(tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": PILOT}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    marker = 'FRONTENDPROXY_LOG_RETENTION_EPOCHS = ("otel-load-pilot-v1", "otel-offpath-pilot-v1", "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, 'FRONTENDPROXY_LOG_RETENTION_EPOCHS = ("otel-load-pilot-v1", "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")'))
    b_tests._materialize(tree, tree / "out")
    assert "logging" not in _overlay(tree / "out")["services"]["frontendproxy"]


def test_the_retention_rule_gives_the_150_per_second_witness_the_room_upstreams_rotation_lacks():
    """Upstream's 5m x 2 loses lines once a container has written 10 MB; ~0.4 kB per access-log line on disk is an estimate
    (C's r10 lines are ~260-330 bytes before json-file framing).  A 150 req/s cell writes warm-up 300 + 27,000 lines (~10.9 MB at
    0.4 kB, over 10 MB from 0.37 kB), far under 4g."""
    lines = 300 + int(150 * 180)
    assert lines * 300 < 10 * 1000 * 1000 < lines * 400 and lines * 550 < 4 * 1000 ** 3


# ------------------------------------------------------------------------------------- 15. the 3.9 floor
PILOT_TARGET_FILES = (
    "modules/otel-demo/execution/candidate_offpath_pilot.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/execution/candidate_runtime_adapter.py",
    "modules/otel-demo/validation/candidate_terminal.py",
    "modules/otel-demo/materialize.py",
)


@pytest.mark.parametrize("relative", PILOT_TARGET_FILES)
def test_touched_target_files_parse_as_python39_and_read_no_name_bound_nowhere(relative):
    tree_ = ast.parse((ROOT / relative).read_text(), feature_version=(3, 9))
    assert b_tests._unbound_names(tree_) == []
    assert any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__" and any(a.name == "annotations" for a in node.names)
        for node in tree_.body
    ), "a PEP 604 annotation would be evaluated eagerly on 3.9 (py_compile does not catch it)"


def test_the_terminal_hashes_the_mix_with_the_producers_function():
    """Producer and terminal must share one canonical-JSON function for the ledger's mixSha256: the target's ensure_ascii=True and
    the runtime's ensure_ascii=False agree only while the mix is pure ASCII (a later non-ASCII character would fail every cell)."""
    source = (MODULE / "validation/candidate_terminal.py").read_text()
    assert "remote.canonical_bytes(mix)" in source and "runtime.canonical_bytes(mix)" not in source
    assert p.MIX_PEOPLE_JSON.isascii() and json.dumps(p.MIX, ensure_ascii=False) == json.dumps(p.MIX, ensure_ascii=True)
