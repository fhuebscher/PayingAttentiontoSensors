"""otel-load-pilot-v1: the OTel load pilot (main repo research/traffic-sweep/BUDGET_D.md amendment 1, user 2026-10-12).

Campaign C's cell at 50 and 100 req/s (user decision 2026-10-12; first built at 100 and 200): the same posture, throttle, collector settings, H10 and H4, 2 throttle episodes and
1 no-fault cell per rate, rate-ascending segments.  Covers, each with a planted defect: the plan pin (descriptor and
attempt-1 plan digests, 3.9/3.13 identity); C-identity (every cell timing is C's at the same (regime, rate) apart from the
declared keys, and the descriptor is C's apart from the declared keys); the generator sizing (concurrency >= 2 x rate x
timeout, the open-file minimum, frontendproxy memory) and its enforcement on the target (RLIMIT_NOFILE); the rate-ascending
run order; no run-ID reuse against every attempt that ran (sweep 1-2, quiet 1-3, B 1, C 1); the epoch in the runtime, the
gate chain, the target runner and the terminal (throttle and no-fault cells at 50 and 100 req/s end to end on the fake
target); the collector log sampler off and frontendproxy's access-log retention in the pilot's rendered tree only.

Like the other epochs' tests, the pilot is exercised in a copy of the module tree with its own selector, so these tests pass
whichever epoch the worktree's committed selector names.
"""
from __future__ import annotations

import ast
import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
PILOT = "otel-load-pilot-v1"
C = "otel-repeat-episodes-c-v1"
REPEAT = "otel-repeat-episodes-v1"
QUIET = "otel-quiet-calibration-v1"
SWEEP = "otel-traffic-sweep-v1"
RATES = (50.0, 100.0)
THROTTLE = "productcatalog-cpu-throttle-effect"
NO_FAULT = "no-fault-calibration"
SEED = 20261012

PILOT_DESCRIPTOR_SHA256 = "45b79b0cf552b12a111ed047803ee535aabdb6d0400d05ce108e5a119a65ac46"
PILOT_PLAN_A1_SHA256 = "aea94eb91d90d18fd41165da3af88771ea1964434c922375196478ef269d25d6"
# C as frozen and run (declaration research/traffic-sweep/DECLARATION_C_OTEL.md, harness 8018a19): must not move.
C_DESCRIPTOR_SHA256 = "6dd3cb7215db438cdf2f0618dd62eed583b86004f5f0254c565eabe93cc13721"
C_PLAN_A1_SHA256 = "ece8caa0552fc0bc03ef2cd51f7560e7a8c6f54e96c29755a75d37168609b744"
PILOT_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor", "quiet-compiler", "repeat-compiler", "repeat-descriptor",
    "repeat-c-compiler", "repeat-c-descriptor",
}
# Attempts that ran on fb14srv6, per epoch: their run IDs exist on the host and must never be planned again.
RAN = {SWEEP: (1, 2), QUIET: (1, 2, 3), REPEAT: (1,), C: (1,)}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("otel_load_pilot_compiler_test", MODULE / "execution/candidate_load_pilot.py")
repeat_c = p.repeat_c
repeat = p.repeat_b
quiet = p.quiet
sweep = p.sweep
# B's test module supplies the tree copy, the fake target with the H10/H4 observables, the runner/terminal drivers and the
# materializer helpers (read, not edited); it in turn loads the sweep's test module as ``helpers``.
b_tests = load("otel_load_pilot_b_test_helpers", ROOT / "tests/test_otel_repeat_episodes.py")
helpers = b_tests.helpers
NOW = helpers.NOW


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
    loaded.compiler = load(f"otel_{label}_compiler", module / "execution/candidate_load_pilot.py")
    return loaded


@pytest.fixture(scope="module")
def pilot_tree(tmp_path_factory):
    return _tree(tmp_path_factory, PILOT, "load-pilot-tree")


@pytest.fixture(scope="module")
def pilot_package(pilot_tree, tmp_path_factory):
    return helpers._package(pilot_tree.runtime, pilot_tree.compiler, tmp_path_factory.mktemp("load-pilot-package"), window_hours=3)


def _plan(attempt: int = 1):
    return p.compile_plan(p.load_descriptor(), attempt)


def _strip(timing, keys):
    return {key: value for key, value in timing.items() if key not in keys}


# ------------------------------------------------------------------------------------- 1. the plan and its pin
def test_the_plan_is_pinned_6_cells_in_two_rate_ascending_segments():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    cells = p.flatten_cells(plan)
    assert p.canonical_sha256(document) == PILOT_DESCRIPTOR_SHA256 == p.EXPECTED_DESCRIPTOR_SHA256
    assert p.canonical_sha256(plan) == PILOT_PLAN_A1_SHA256
    assert len(cells) == plan["runCount"] == plan["uniqueRunCount"] == p.TOTAL_RUNS == 6
    assert [segment["requestsPerSecond"] for segment in plan["blocks"]] == list(RATES)
    assert [cell["ordinalPosition"] for cell in cells] == [1, 2, 3, 4, 5, 6]
    for segment in plan["blocks"]:
        held = sorted((x["runKey"]["regime"], x["runKey"]["block"]) for x in segment["cells"])
        assert held == [(NO_FAULT, 1), (THROTTLE, 1), (THROTTLE, 2)]
        assert {x["runKey"]["requestsPerSecond"] for x in segment["cells"]} == {segment["requestsPerSecond"]}
    assert {cell["runKey"]["studyEpoch"] for cell in cells} == {PILOT} and plan["studyEpoch"] == PILOT
    assert {cell["fault"] for cell in cells} == {None, "productcatalog-cpu-throttle"}
    assert (p.MINIMUM_REMAINING_SECONDS, p.RUN_WINDOW_HOURS) == (6 * (211 + 450) + 900 + 600, 3) == (5466, 3)


def test_planted_defect_an_edited_descriptor_or_plan_is_refused_and_moves_the_pin():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    for mutate in (
        lambda d: d["schedule"].update(seed=20261011),                  # C's seed
        lambda d: d["timing"].update(duringFaultProbe=True),             # H10 off
        lambda d: d["workload"].update(concurrency=300),                 # C's concurrency
        lambda d: d["design"].update(rates=[10.0, 1.0, 0.2, 0.05]),
        lambda d: d.update(declaration="research/traffic-sweep/DECLARATION_C_OTEL.md"),
    ):
        planted = copy.deepcopy(document)
        mutate(planted)
        assert p.canonical_sha256(planted) != PILOT_DESCRIPTOR_SHA256
        with pytest.raises(p.ProtocolError, match="differs from its generator"):
            p.validate_descriptor(planted)
    for mutate in (
        lambda q: q["blocks"][1]["cells"][0]["timing"].update(faultOnsetSeconds=61.0),
        lambda q: q["blocks"][0]["cells"].pop(),
        lambda q: q["blocks"][0]["cells"][0]["timing"].update(concurrency=300),
        lambda q: q["blocks"][1]["cells"][1]["timing"].update(generatorOpenFilesMinimum=1024),
        lambda q: q.update(blocks=list(reversed(q["blocks"]))),        # 100 req/s first
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
    path = ROOT / "pipelines/campaigns/otel-load-pilot-v1.json"
    assert path.read_bytes() == p._pretty_bytes(p.derive_pilot_descriptor())
    document = p.load_descriptor()
    assert document["id"] == PILOT
    assert document["declaration"].startswith("research/traffic-sweep/DECLARATION_PILOT_LOAD_OTEL.md ")
    assert document["derivedFrom"]["studyEpoch"] == C
    assert document["derivedFrom"]["descriptorCanonicalSha256"] == C_DESCRIPTOR_SHA256
    assert document["derivedFrom"]["descriptorByteSha256"] == hashlib.sha256(
        (ROOT / "pipelines/campaigns/otel-repeat-episodes-c-v1.json").read_bytes()).hexdigest()
    assert document["derivedFrom"]["predecessorDerivedFrom"]["studyEpoch"] == REPEAT
    assert document["analysis"]["manifestationCriterion"] == p.MANIFESTATION_CRITERION
    assert "both throttle cells" in p.MANIFESTATION_CRITERION and ">= 2x" in p.MANIFESTATION_CRITERION
    defaults = document["analysis"]["manifestationCriterionDefaults"]
    assert defaults == p.MANIFESTATION_CRITERION_DEFAULTS
    assert defaults["preOnsetSegment"] == "[onset - 60 s, onset)" and defaults["hold"] == "[onset, onset + hold)"
    assert ">= 1.25" in defaults["clientSpanRatio"] and ">= 2.0" in defaults["serverSpanRatio"]
    assert defaults["spanSelection"].startswith("by span start time") and "'—'" in defaults["verdictPerRate"]


def test_the_digests_are_identical_under_python39_isolated_and_this_interpreter(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import importlib.util, json, sys\n"
        f"s = importlib.util.spec_from_file_location('p', {str(MODULE / 'execution/candidate_load_pilot.py')!r})\n"
        "m = importlib.util.module_from_spec(s); sys.modules['p'] = m; s.loader.exec_module(m)\n"
        "d = m.load_descriptor(); c = m.repeat_c.load_descriptor()\n"
        "print(json.dumps([m.canonical_sha256(d), m.canonical_sha256(m.compile_plan(d, 1)), m.MINIMUM_REMAINING_SECONDS,"
        " m.RUN_WINDOW_HOURS, m.canonical_sha256(c), m.canonical_sha256(m.repeat_c.compile_plan(c, 1))]))\n"
    )
    result = subprocess.run(
        [str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
        capture_output=True, text=True, check=True,
    )
    expected = [PILOT_DESCRIPTOR_SHA256, PILOT_PLAN_A1_SHA256, 5466, 3, C_DESCRIPTOR_SHA256, C_PLAN_A1_SHA256]
    assert json.loads(result.stdout) == expected
    document = p.load_descriptor()
    assert [p.canonical_sha256(document), p.canonical_sha256(p.compile_plan(document, 1))] == expected[:2]


# ------------------------------------------------------------------------------------- 2. C's cell, at 100 and 200 /s
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
    # What C was: the throttle scenario and dose, H10/H4, the trace rules per cell kind, the gates -- inherited verbatim.
    for key in ("faultDesign", "groundTruth", "protocolGates", "containerHealthGuard", "postureRealization", "workflow"):
        assert document[key] == base[key], key
    assert document["faultDesign"]["scenarios"]["productcatalog-cpu-throttle"]["nanoCpus"] == 100_000_000
    assert document["analysis"]["traceCompleteness"] == base["analysis"]["traceCompleteness"]
    assert _strip(document["timing"], p.REPLACED_DESCRIPTOR_SUBKEYS["timing"]) == _strip(
        base["timing"], p.REPLACED_DESCRIPTOR_SUBKEYS["timing"])
    assert document["schedule"]["seed"] == SEED != base["schedule"]["seed"]


def test_planted_defect_a_descriptor_that_drifts_from_c_outside_the_declared_keys_is_found():
    document, base = p.load_descriptor(), repeat_c.load_descriptor()
    drifted = copy.deepcopy(document)
    drifted["timing"]["faultHoldSeconds"] = 30
    drifted["faultDesign"]["scenarios"]["productcatalog-cpu-throttle"]["nanoCpus"] = 200_000_000
    _, nested = _descriptor_differences(drifted, base)
    assert "faultHoldSeconds" in nested["timing"] and nested["faultDesign"] == {"scenarios"}
    assert nested != {key: set(value) for key, value in p.REPLACED_DESCRIPTOR_SUBKEYS.items()}


def test_every_cell_is_cs_cell_at_the_same_regime_and_rate_apart_from_the_declared_keys():
    cells = p.flatten_cells(_plan(1))
    for cell in cells:
        key = cell["runKey"]
        c_timing = repeat_c.cell_timing(key["regime"], key["requestsPerSecond"], 1)
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
    # The plan layout is C's apart from the segment layout under ``blocks`` and its schedule receipt.
    c_plan = repeat_c.compile_plan(repeat_c.load_descriptor(), 1)
    plan = _plan(1)
    assert set(plan) == set(c_plan)
    same = {k for k in plan if plan[k] == c_plan[k]}
    assert set(plan) - same == {
        "kind", "studyEpoch", "descriptorSha256", "scheduleVersion", "schedule", "blocks", "runCount", "uniqueRunCount",
        "minimumRemainingSeconds", "runWindowHours",
    }


def test_planted_defect_a_cell_that_drifts_from_c_outside_the_declared_keys_is_found():
    cell = p.flatten_cells(_plan(1))[0]
    key = cell["runKey"]
    drifted = copy.deepcopy(cell["timing"])
    drifted["faultHoldSeconds"] = 30
    c_timing = repeat_c.cell_timing(key["regime"], key["requestsPerSecond"], 1)
    assert _strip(drifted, p.REPLACED_TIMING_KEYS | p.NEW_TIMING_KEYS) != _strip(c_timing, p.REPLACED_TIMING_KEYS)


# ------------------------------------------------------------------------------------- 3. the generator sizing
def test_the_generator_is_sized_for_rate_x_timeout_and_its_open_files_and_the_proxy_memory_follow():
    for cell in p.flatten_cells(_plan(1)):
        timing = cell["timing"]
        rate, timeout = timing["requestsPerSecond"], timing["requestTimeoutSeconds"]
        assert timing["concurrency"] == 3000 >= 2 * rate * timeout          # the sweep's rule at the pilot's max rate
        assert timing["generatorOpenFilesMinimum"] == 3000 + 1024
        limit = timing["serviceMemoryLimitBytes"]["frontendproxy"]
        assert limit == 512 * 1024 ** 2 >= p.FRONTENDPROXY_BYTES_PER_WAITING_REQUEST * 100 * 15
    assert p.CONCURRENCY == math.ceil(sweep.CONCURRENCY_MARGIN * max(RATES) * sweep.REQUEST_TIMEOUT_SECONDS)
    assert repeat_c.cell_timing(THROTTLE, 100.0, 1)["concurrency"] == 300       # C's value, too small at 100 /s


def test_planted_defect_c_sized_generator_at_100_per_second_is_refused_by_the_plan_check():
    document = p.load_descriptor()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "CONCURRENCY", 300)                       # C's worker cap: 300 < 100 x 15
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
def test_every_50_per_second_cell_runs_before_any_100_per_second_cell_in_a_seeded_order():
    document = p.load_descriptor()
    cells = p.flatten_cells(_plan(1))
    rates = [cell["runKey"]["requestsPerSecond"] for cell in cells]
    assert rates == sorted(rates) and rates[:3] == [50.0] * 3
    for receipt in document["schedule"]["segments"]:
        expected = quiet.fisher_yates(
            p.segment_cells(receipt["requestsPerSecond"]), SEED, PILOT, receipt["segment"], "load-pilot-schedule-v1")
        assert receipt["order"] == [p.cell_label(row) for row in expected]
        assert receipt["orderSha256"] == p.canonical_sha256(receipt["order"])


def test_planted_defect_a_descending_rate_order_is_refused():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "RATES", (100.0, 50.0))
        with pytest.raises(p.ProtocolError, match="ascending"):
            p.allocate_schedule()


def test_throttle_onsets_take_the_two_strata_of_one_inter_arrival():
    cells = p.flatten_cells(_plan(1))
    for rate in RATES:
        rows = [x["timing"] for x in cells if (x["runKey"]["regime"], x["runKey"]["requestsPerSecond"]) == (THROTTLE, rate)]
        strata = sorted(int(row["faultOnsetPhaseOffsetSeconds"] / (1.0 / rate) * 2) for row in rows)
        assert strata == [0, 1], (rate, strata)


# ------------------------------------------------------------------------------------- 5. no run-ID reuse
def _ran_run_ids() -> dict:
    compilers = {SWEEP: sweep, QUIET: quiet, REPEAT: repeat, C: repeat_c}
    ids = {}
    for epoch, attempts in RAN.items():
        compiler = compilers[epoch]
        document = compiler.load_descriptor()
        for attempt in attempts:
            ids[(epoch, attempt)] = {cell["runId"] for cell in compiler.flatten_cells(compiler.compile_plan(document, attempt))}
    return ids


def _reused(run_ids, ran) -> dict:
    return {key: len(run_ids & ids) for key, ids in ran.items() if run_ids & ids}


def test_no_pilot_run_id_equals_one_that_ran_in_the_sweep_quiet_b_or_c():
    ran = _ran_run_ids()
    assert {key: len(ids) for key, ids in ran.items()} == {
        (SWEEP, 1): 12, (SWEEP, 2): 12, (QUIET, 1): 40, (QUIET, 2): 40, (QUIET, 3): 40, (REPEAT, 1): 36, (C, 1): 36}
    for attempt in (1, 2, 3):
        ids = {cell["runId"] for cell in p.flatten_cells(_plan(attempt))}
        assert len(ids) == 6 and _reused(ids, ran) == {}
    assert repeat_c.canonical_sha256(repeat_c.compile_plan(repeat_c.load_descriptor(), 1)) == C_PLAN_A1_SHA256


def test_planted_defect_with_cs_epoch_the_pilot_would_reuse_cs_run_ids_and_the_check_finds_them():
    ran = _ran_run_ids()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "EPOCH", C)
        patch.setattr(p, "RATES", (10.0,))
        ids = {p.run_id_for(p.run_key_for(r, 10.0, b, "full", 1)) for r in p.REGIMES for b in (1, 2)}
    assert _reused(ids, ran) == {(C, 1): 4}


def _spent_table_in_source() -> dict:
    tree_ = ast.parse((MODULE / "execution/candidate_runtime_adapter.py").read_text())
    for node in tree_.body:
        if isinstance(node, ast.Assign) and any(getattr(t_, "id", None) == "SPENT_ATTEMPTS_BY_EPOCH" for t_ in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SPENT_ATTEMPTS_BY_EPOCH not found")


RAN_PILOT_ATTEMPTS = {1: "aea94eb9"}           # attempt -> the plan prefix that ran on fb14srv6 (2026-10-12, harness 7b20ec4)


def _unrecorded_pilot_attempts(table: dict) -> list:
    spent = table.get(PILOT, {})
    return sorted(a for a, prefix in RAN_PILOT_ATTEMPTS.items() if a not in spent or prefix not in spent[a])


def test_the_pilots_attempt_1_ran_and_is_recorded_as_spent_beside_cs():
    # 2026-10-12: the pilot ran on fb14srv6 (launched 03:52Z, host terminal 04:33Z, 6/6 valid, fetched 107/107).
    table = _spent_table_in_source()
    assert set(table[PILOT]) == {1} and "7b20ec4" in table[PILOT][1] and "aea94eb9" in table[PILOT][1]
    assert set(table[C]) == {1}
    assert _unrecorded_pilot_attempts(table) == []
    assert p.canonical_sha256(_plan(1)).startswith(RAN_PILOT_ATTEMPTS[1])


def test_planted_defect_a_pilot_attempt_that_ran_but_is_not_recorded_is_found():
    table = _spent_table_in_source()
    assert _unrecorded_pilot_attempts({**table, PILOT: {}}) == [1]
    assert _unrecorded_pilot_attempts({**table, PILOT: {1: "load pilot attempt 1, plan 00000000"}}) == [1]


# ------------------------------------------------------------- 6. the epoch in the runtime, the gate chain and the target
def test_the_selector_activates_the_pilot_in_every_reader(pilot_tree, tmp_path):
    runtime = pilot_tree.runtime
    assert runtime.STUDY_EPOCH == PILOT and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (6, 5466, 3)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | PILOT_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_load_pilot.py"
    assert runtime.CONTROLLER_PATHS["repeat-c-compiler"] == "modules/otel-demo/execution/candidate_repeat_c.py"
    assert runtime.DESCRIPTOR == pilot_tree.root / "pipelines/campaigns/otel-load-pilot-v1.json"
    assert pilot_tree.setup.controller_paths(PILOT) == runtime.CONTROLLER_PATHS
    assert pilot_tree.setup.EPOCH_CONTROLLER_PATHS[PILOT] == runtime.EPOCH_CONTROLLER_PATHS[PILOT]
    digests = runtime.controller_digests()
    for key, relative in (("repeat-c-compiler", "execution/candidate_repeat_c.py"), ("repeat-compiler", "execution/candidate_repeat.py")):
        assert digests[key] == hashlib.sha256((MODULE / relative).read_bytes()).hexdigest()
    assert runtime.frozen_descriptor()["id"] == PILOT
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {
        "duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum"}
    assert runtime.timed_cell_timing_keys(False) == runtime.timed_cell_timing_keys(True) | {"traceCompletenessRule"}
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    copied = load("otel_load_pilot_driver_config_tree", pilot_tree.root / "modules/otel-demo/drivers/gate_driver_config.py")
    assert (copied.CONFIG.study, copied.CONFIG.campaign_id, copied.CONFIG.run_window_hours) == (PILOT, PILOT, 3)
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_load_pilot_tree_adapter", pilot_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == PILOT
        # 2026-10-12: attempt 1 ran (plan aea94eb9) and is recorded spent: the driver path refuses it; with the row removed
        # (planted) it plans the pinned attempt-1 plan again.
        assert adapter.pilot.EPOCH == PILOT and set(adapter.SPENT_ATTEMPTS) == {1}
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
                adapter.inspect_campaign(tmp_path / "plan-a1", "a" * 40)
            patch.delitem(adapter.SPENT_ATTEMPTS, 1)
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 6 and bindings.plan_sha256 == PILOT_PLAN_A1_SHA256
        assert bindings.descriptor_sha256 == PILOT_DESCRIPTOR_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_planted_defect_a_selector_naming_the_pilot_without_its_controller_set_is_refused(tmp_path_factory):
    root = helpers._copy_tree(
        tmp_path_factory.mktemp("load-pilot-no-paths"), selector=json.dumps({"schemaVersion": 1, "studyEpoch": PILOT}) + "\n")
    runtime_path = root / "modules/otel-demo/execution/candidate_runtime.py"
    text = runtime_path.read_text()
    marker = "    LOAD_PILOT_STUDY_EPOCH: {\n        \"candidate-compiler\": \"modules/otel-demo/execution/candidate_load_pilot.py\","
    assert text.count(marker) == 1
    runtime_path.write_text(text.replace(marker, "    \"otel-load-pilot-v0\": {\n        \"candidate-compiler\": \"modules/otel-demo/execution/candidate_load_pilot.py\","))
    with pytest.raises(Exception, match="names no declared non-frozen epoch"):
        load("otel_load_pilot_no_paths_runtime", runtime_path)


def test_gate_chain_derives_6_cells_the_budget_and_host_paths_disjoint_from_every_earlier_epoch(pilot_tree, pilot_package):
    runtime, remote = pilot_tree.runtime, pilot_tree.remote
    plan_text = pilot_package.gate_plan["typedApproval"]
    assert f"study={PILOT} " in plan_text and " runs=6 " in plan_text and f"campaign={PILOT} " in plan_text
    assert pilot_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 5466
    binding = pilot_package.gate_plan["binding"]
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_load_pilot_v1"
    assert remote.SAFE_NAME.fullmatch(binding["compose"]["project"])
    earlier = (SWEEP, QUIET, REPEAT, C)
    other = ["/home/stig/observability-placement-candidate-v4-runs/" + epoch for epoch in earlier] + [
        "/home/stig/observability-placement-candidate-v4-runs/.setup-" + epoch for epoch in earlier] + [
        "/home/stig/observability-placement-candidate-v4-otel-srv6/" + epoch + "-" for epoch in earlier]
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert PILOT in binding[key] and not any(binding[key].startswith(path) for path in other), key
    assert set(binding["controllerDigests"]) == helpers.FROZEN_CONTROLLER_KEYS | PILOT_CONTROLLER_KEYS
    document = runtime.execution_package(pilot_package)
    assert document["runCount"] == 6 and len(document["cells"]) == 6
    for contract, cell in zip(document["cells"], pilot_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and runtime.sweep_cell_timing(contract) == cell["timing"]
        assert "docker-events.json" not in contract["requiredArtifacts"]          # no pause cell in the pilot
        assert contract["workload"]["concurrency"] == 3000
    assert [c["runKey"]["requestsPerSecond"] for c in document["cells"]] == [50.0] * 3 + [100.0] * 3
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (PILOT,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
    assert len(cells) == 6 and remote.expected_minimum_remaining(document) == 5466 and remote.expected_run_count(document) == 6


def test_a_contract_cannot_drop_the_open_file_minimum(pilot_tree, pilot_package):
    runtime = pilot_tree.runtime
    contract = copy.deepcopy(runtime.execution_package(pilot_package)["cells"][0])
    contract["timing"].pop("generatorOpenFilesMinimum")
    with pytest.raises(runtime.GateError, match="cell timing fields differ"):
        runtime.sweep_cell_timing(contract)


def test_the_target_treats_the_pilot_as_an_h10_h4_epoch_and_a_family_without_it_is_refused(pilot_tree, pilot_package):
    remote = pilot_tree.remote
    assert PILOT in remote.REPEAT_STUDY_EPOCHS and PILOT in remote.TIMED_STUDY_EPOCHS and C in remote.REPEAT_STUDY_EPOCHS
    cells = pilot_tree.runtime.execution_package(pilot_package)["cells"]
    fault = next(x for x in cells if x["fault"]["scenario"] is not None)
    clean = next(x for x in cells if x["fault"]["scenario"] is None)
    remote.require_harness_flags_consistent(fault)
    assert remote.names_trace_rule(clean) is True and remote.names_trace_rule(fault) is False
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "REPEAT_STUDY_EPOCHS", (REPEAT, C))
        with pytest.raises(remote.RuntimeFailure, match="H10"):
            remote.require_harness_flags_consistent(fault)
        assert remote.names_trace_rule(clean) is False


# ------------------------------------------------------------- 7. the generator's open files on the target
class _Limits:
    def __init__(self, soft, hard):
        self.soft, self.hard, self.calls = soft, hard, []

    def get(self, which):
        return self.soft, self.hard

    def set(self, which, value):
        self.calls.append(value)
        self.soft, self.hard = value


def test_the_open_file_soft_limit_is_raised_to_the_declared_minimum_and_never_above_the_hard_limit(pilot_tree):
    import resource
    remote = pilot_tree.remote
    timing = {"concurrency": 3000, "generatorOpenFilesMinimum": 4024}
    limits = _Limits(1024, 524288)                                   # systemd's DefaultLimitNOFILE on the targets' systemd
    record = remote.ensure_generator_open_files(timing, getrlimit=limits.get, setrlimit=limits.set)
    assert limits.calls == [(4024, 524288)] and record["after"] == {"soft": 4024, "hard": 524288}
    already = _Limits(1048576, 1048576)
    assert remote.ensure_generator_open_files(timing, getrlimit=already.get, setrlimit=already.set)["before"]["soft"] == 1048576
    assert already.calls == []
    infinite = _Limits(resource.RLIM_INFINITY, resource.RLIM_INFINITY)
    remote.ensure_generator_open_files(timing, getrlimit=infinite.get, setrlimit=infinite.set)
    assert infinite.calls == []
    # A timing without the key (every earlier epoch) leaves the limits alone.
    untouched = _Limits(1024, 2048)
    assert remote.ensure_generator_open_files({"concurrency": 300}, getrlimit=untouched.get, setrlimit=untouched.set) is None
    assert untouched.calls == []


def test_planted_defect_a_hard_limit_below_the_minimum_or_a_minimum_below_concurrency_is_refused(pilot_tree):
    remote = pilot_tree.remote
    low = _Limits(1024, 2048)
    with pytest.raises(remote.RuntimeFailure, match="hard limit 2048"):
        remote.ensure_generator_open_files(
            {"concurrency": 3000, "generatorOpenFilesMinimum": 4024}, getrlimit=low.get, setrlimit=low.set)
    assert low.calls == []
    with pytest.raises(remote.RuntimeFailure, match="covering the cell's concurrency"):
        remote.ensure_generator_open_files({"concurrency": 3000, "generatorOpenFilesMinimum": 1024})
    stuck = _Limits(1024, 524288)
    with pytest.raises(remote.RuntimeFailure, match="stayed at 1024"):
        remote.ensure_generator_open_files(
            {"concurrency": 3000, "generatorOpenFilesMinimum": 4024}, getrlimit=stuck.get, setrlimit=lambda w, v: None)


class _CappedPool(concurrent.futures.ThreadPoolExecutor):
    """The fake target answers at once, so a few hundred workers keep the open loop on time (macOS caps a process at 4096
    threads, kern.num_taskthreads).  The cap the controller asked for is recorded."""

    asked: list = []

    def __init__(self, max_workers=None, **kwargs):
        type(self).asked.append(max_workers)
        super().__init__(max_workers=min(int(max_workers), 256), **kwargs)


CASES = (
    (THROTTLE, 50.0, 1),
    (NO_FAULT, 50.0, 1),
    (THROTTLE, 100.0, 2),
)


@pytest.mark.parametrize("regime,rate,block", CASES)
def test_run_cell_executes_a_pilot_cell_and_the_terminal_accepts_it(pilot_tree, pilot_package, tmp_path, monkeypatch, regime, rate, block):
    contract = b_tests._contract(pilot_tree, pilot_package, regime, rate, tmp_path, block)
    assert contract["studyEpoch"] == PILOT
    limits = _Limits(1024, 524288)
    monkeypatch.setattr(pilot_tree.remote, "ensure_generator_open_files",
                        lambda timing, _real=pilot_tree.remote.ensure_generator_open_files: _real(
                            timing, getrlimit=limits.get, setrlimit=limits.set))
    _CappedPool.asked = []
    monkeypatch.setattr(pilot_tree.remote, "ThreadPoolExecutor", _CappedPool)
    receipt, target = b_tests._run(pilot_tree, contract, monkeypatch)
    root = Path(contract["remoteArtifactRoot"])
    assert receipt["state"] == "valid", receipt["error"]
    assert limits.calls == [(4024, 524288)]
    assert _CappedPool.asked.count(3000) == 2                     # the warm-up and the measurement both ask for the cell's cap
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    ledger = b_tests._read(contract, "request-ledger.json")
    assert ledger["offered"] == int(rate * 180) == len(ledger["requests"]) and ledger["concurrency"] == 3000
    with b_tests.bound(pilot_tree):
        report = pilot_tree.terminal.validate_cell(root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    if contract["fault"]["scenario"] is None:
        assert b_tests._read(contract, "trace-completeness.json")["rule"] == "protocol-decision-56"
        return
    assert b_tests._probes_inside_the_fault(target, contract) == []                      # H10
    intervention = b_tests._read(contract, "intervention.json")
    assert intervention["duringRouteAvailable"] is None and intervention["freeze"]["stampCheck"]["status"] == "ok"   # H4
    assert intervention["throttle"]["appliedNanoCpus"] == 100_000_000


def test_planted_defect_a_target_whose_open_files_cannot_reach_the_minimum_seals_the_cell_invalid_before_any_container(
    pilot_tree, pilot_package, tmp_path, monkeypatch,
):
    contract = b_tests._contract(pilot_tree, pilot_package, THROTTLE, 50.0, tmp_path, 1)
    low = _Limits(1024, 2048)
    monkeypatch.setattr(pilot_tree.remote, "ensure_generator_open_files",
                        lambda timing, _real=pilot_tree.remote.ensure_generator_open_files: _real(
                            timing, getrlimit=low.get, setrlimit=low.set))
    receipt, target = b_tests._run(pilot_tree, contract, monkeypatch)
    assert receipt["state"] == "invalid" and "hard limit 2048" in receipt["error"]
    assert not any(argv[:2] == ["docker", "compose"] and "up" in argv for argv in target.commands)


# ------------------------------------------------------------------------------------- 8. the rendered tree
@pytest.fixture(scope="module")
def materialized_pilot(tmp_path_factory):
    out = {}
    for label, epoch in (("pilot", PILOT), ("c", C), ("quiet", QUIET)):
        tree = helpers._copy_tree(
            tmp_path_factory.mktemp("materialize-pilot-" + label),
            selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n",
        )
        out[label] = tree / "out"
        out[label + "-digest"] = b_tests._materialize(tree, out[label])
    return out


def _overlay(out: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((out / "compose.otel-placement.yml").read_text())


def test_the_pilots_tree_keeps_cs_collector_and_adds_frontendproxy_log_retention_only(materialized_pilot):
    materialize = load("otel_load_pilot_materialize_module", MODULE / "materialize.py")
    assert PILOT in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS and materialize.FRONTENDPROXY_LOG_RETENTION_EPOCHS == (PILOT, "otel-offpath-pilot-v1", "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1", "otel-offpath-f-nolag-v1")
    pilot, c_out = materialized_pilot["pilot"], materialized_pilot["c"]
    assert b_tests._log_sampling_enabled(b_tests._collector_config(pilot)) is False
    assert b_tests._collector_config(pilot) == b_tests._collector_config(c_out)
    overlay, c_overlay = _overlay(pilot), _overlay(c_out)
    assert overlay["services"]["frontendproxy"]["logging"] == {
        "driver": "json-file", "options": {"max-size": "4g", "max-file": "1"}}
    assert overlay["services"]["frontendproxy"]["logging"] == overlay["services"]["otelcol"]["logging"]
    assert "logging" not in c_overlay["services"]["frontendproxy"]
    without = copy.deepcopy(overlay)
    del without["services"]["frontendproxy"]["logging"]
    assert without == c_overlay
    # C's rendered overlay is the repository's, byte for byte; every other rendered file is C's.
    assert (c_out / "compose.otel-placement.yml").read_bytes() == (MODULE / "deployment/compose.otel-placement.yml").read_bytes()
    files = sorted(str(q.relative_to(c_out)) for q in c_out.rglob("*") if q.is_file())
    differ = [name for name in files if (pilot / name).read_bytes() != (c_out / name).read_bytes()]
    assert set(differ) <= {"compose.otel-placement.yml", ".source.sha256"} and "compose.otel-placement.yml" in differ
    assert materialized_pilot["pilot-digest"] != materialized_pilot["c-digest"] != materialized_pilot["quiet-digest"]


def test_planted_defect_without_the_pilot_in_the_retention_tuple_frontendproxy_keeps_upstreams_rotation(tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": PILOT}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    # 2026-10-13: the tuple also names the off-path pilot (otel-offpath-pilot-v1); the plant removes the load pilot only.
    marker = 'FRONTENDPROXY_LOG_RETENTION_EPOCHS = ("otel-load-pilot-v1", "otel-offpath-pilot-v1", "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1", "otel-offpath-f-nolag-v1")'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, 'FRONTENDPROXY_LOG_RETENTION_EPOCHS = ("otel-offpath-pilot-v1", "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1", "otel-offpath-f-nolag-v1")'))
    b_tests._materialize(tree, tree / "out")
    assert "logging" not in _overlay(tree / "out")["services"]["frontendproxy"]


def test_the_retention_rule_gives_the_100_per_second_witness_margin():
    """Upstream's 5m x 2 loses lines once a container has written 10 MB; ~0.4 kB per access-log line on disk is an
    estimate (C's r10 lines are ~260-330 bytes before json-file framing).  A 100 req/s cell writes warm-up 300 + 18,000
    lines: ~7.3 MB at 0.4 kB, over 10 MB at 0.55 kB (a 37 % estimation error), far under 4g either way."""
    lines = 300 + int(100 * 180)
    assert lines * 400 < 10 * 1000 * 1000 < lines * 550 and lines * 550 < 4 * 1000 ** 3


# ------------------------------------------------------------------------------------- 9. the 3.9 floor
PILOT_TARGET_FILES = (
    "modules/otel-demo/execution/candidate_load_pilot.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/execution/candidate_runtime_adapter.py",
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
