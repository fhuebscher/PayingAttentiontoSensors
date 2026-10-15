"""otel-repeat-episodes-c-v1: campaign C on the OTel Demo (main repo research/PROTOCOL_DRAFT_20261002.md decision 82; budget
and stop rule research/traffic-sweep/BUDGET_C.md, d5b9af0).

Campaign C is campaign B's shape exactly (36 cells, H10, H4 recorded and never blocking, collector log sampler off, decision
25 in fault cells and 56 in no-fault cells) with new blocks and run IDs under a new study epoch.  Covers, each with a planted
defect: the plan pin (descriptor and attempt-1 plan digests, 3.9/3.13 identity); B-shape identity (every cell timing is B's
for the same (regime, rate, block) apart from the onset draw, and the descriptor is B's apart from the declared keys); no
run-ID reuse against the sweep (attempts 1, 2), quiet A and A2 (attempts 1-3) and B (attempt 1); B attempt 1 recorded spent;
the epoch in the runtime, the gate chain, the target runner and the terminal (H10/H4 cells end to end on the fake target);
the collector log sampler off in C's rendered config (decision 66 membership).

Like the other epochs' tests, C is exercised in a copy of the module tree with its own selector, so these tests pass
whichever epoch the worktree's committed selector names.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
C = "otel-repeat-episodes-c-v1"
REPEAT = "otel-repeat-episodes-v1"
QUIET = "otel-quiet-calibration-v1"
SWEEP = "otel-traffic-sweep-v1"
RATES = (10.0, 1.0, 0.2, 0.05)
REGIMES = ("no-fault-calibration", "frontend-pause-effect", "productcatalog-cpu-throttle-effect")
SEED = 20261011

C_DESCRIPTOR_SHA256 = "6dd3cb7215db438cdf2f0618dd62eed583b86004f5f0254c565eabe93cc13721"
C_PLAN_A1_SHA256 = "ece8caa0552fc0bc03ef2cd51f7560e7a8c6f54e96c29755a75d37168609b744"
# B as frozen and run (declaration research/traffic-sweep/DECLARATION_B_OTEL.md, harness c4aa313): must not move.
REPEAT_DESCRIPTOR_SHA256 = "6e5d0f3460d28142428221c259994011a3a02973392aca4ffe6a4eb47a81a4ce"
REPEAT_PLAN_A1_SHA256 = "3aaf5923a051270f715aab822dafb7d63bbe0c8d6475f984afa2e2317cb2b142"
C_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor", "quiet-compiler", "repeat-compiler", "repeat-descriptor",
}
# Attempts that ran on fb14srv6, per epoch: their run IDs exist on the host and must never be planned again.
RAN = {SWEEP: (1, 2), QUIET: (1, 2, 3), REPEAT: (1,)}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


c = load("otel_repeat_c_compiler_test", MODULE / "execution/candidate_repeat_c.py")
repeat = c.repeat_b
quiet = c.quiet
sweep = c.sweep
# B's test module supplies the tree copy, the fake target with the H10/H4 observables, the runner/terminal drivers and the
# materializer helpers (read, not edited); it in turn loads the sweep's test module as ``helpers``.
b_tests = load("otel_repeat_c_b_test_helpers", ROOT / "tests/test_otel_repeat_episodes.py")
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
    compiler = {REPEAT: "candidate_repeat.py", C: "candidate_repeat_c.py"}[epoch]
    loaded.compiler = load(f"otel_{label}_compiler", module / "execution" / compiler)
    return loaded


@pytest.fixture(scope="module")
def c_tree(tmp_path_factory):
    return _tree(tmp_path_factory, C, "repeat-c-tree")


@pytest.fixture(scope="module")
def c_package(c_tree, tmp_path_factory):
    return helpers._package(c_tree.runtime, c_tree.compiler, tmp_path_factory.mktemp("repeat-c-package"), window_hours=5)


def _plan(attempt: int = 1):
    return c.compile_plan(c.load_descriptor(), attempt)


def _strip(timing, keys):
    return {key: value for key, value in timing.items() if key not in keys}


# ------------------------------------------------------------------------------------- 1. the plan and its pin
def test_the_plan_is_pinned_and_is_36_cells_3_blocks_each_holding_every_regime_and_rate_once():
    document = c.load_descriptor()
    plan = c.compile_plan(document, 1)
    cells = c.flatten_cells(plan)
    assert c.canonical_sha256(document) == C_DESCRIPTOR_SHA256 == c.EXPECTED_DESCRIPTOR_SHA256
    assert c.canonical_sha256(plan) == C_PLAN_A1_SHA256
    assert len(cells) == plan["runCount"] == plan["uniqueRunCount"] == c.TOTAL_RUNS == 36
    assert [block["block"] for block in plan["blocks"]] == [1, 2, 3]
    pairs = sorted((regime, rate) for regime in REGIMES for rate in RATES)
    for block in plan["blocks"]:
        assert sorted((cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"]) for cell in block["cells"]) == pairs
        assert [cell["ordinalPosition"] for cell in block["cells"]] == list(range(1, 13))
    assert {cell["runKey"]["studyEpoch"] for cell in cells} == {C} and plan["studyEpoch"] == C
    assert sum(cell["fault"] is None for cell in cells) == 12
    assert (c.MINIMUM_REMAINING_SECONDS, c.RUN_WINDOW_HOURS) == (13_416, 5)


def test_planted_defect_an_edited_descriptor_or_plan_is_refused_and_moves_the_pin():
    document = c.load_descriptor()
    plan = c.compile_plan(document, 1)
    for mutate in (
        lambda d: d["schedule"].update(seed=20261009),            # B's seed
        lambda d: d["timing"].update(duringFaultProbe=True),       # H10 off
        lambda d: d["timing"]["budget"].update(runWindowHours=6),
        lambda d: d.update(declaration="research/traffic-sweep/DECLARATION_B_OTEL.md"),
    ):
        planted = copy.deepcopy(document)
        mutate(planted)
        assert c.canonical_sha256(planted) != C_DESCRIPTOR_SHA256
        with pytest.raises(c.ProtocolError, match="differs from its generator"):
            c.validate_descriptor(planted)
    for mutate in (
        lambda p: p["blocks"][1]["cells"][0]["timing"].update(faultOnsetSeconds=61.0),
        lambda p: p["blocks"][0]["cells"].pop(),
        lambda p: p["blocks"][2]["cells"][1]["timing"].update(freezeStamps=False),
        lambda p: p["blocks"][0]["cells"][0]["runKey"].update(studyEpoch=REPEAT),
        lambda p: p.update(studyEpoch=REPEAT),
    ):
        broken = copy.deepcopy(plan)
        mutate(broken)
        with pytest.raises(c.ProtocolError, match="differs from the frozen schedule"):
            c.validate_plan(document, broken)
    with pytest.MonkeyPatch.context() as patch:            # a pin that does not match the generator is refused
        patch.setattr(c, "EXPECTED_DESCRIPTOR_SHA256", REPEAT_DESCRIPTOR_SHA256)
        with pytest.raises(c.ProtocolError, match="differs from the reviewed pin"):
            c.load_descriptor()


def test_the_descriptor_file_is_the_generators_output():
    path = ROOT / "pipelines/campaigns/otel-repeat-episodes-c-v1.json"
    assert path.read_bytes() == c._pretty_bytes(c.derive_c_descriptor())
    document = c.load_descriptor()
    assert document["id"] == C and document["declaration"].startswith("research/traffic-sweep/DECLARATION_C_OTEL.md ")
    assert document["derivedFrom"]["studyEpoch"] == REPEAT
    assert document["derivedFrom"]["descriptorCanonicalSha256"] == REPEAT_DESCRIPTOR_SHA256
    assert document["derivedFrom"]["descriptorByteSha256"] == hashlib.sha256(
        (ROOT / "pipelines/campaigns/otel-repeat-episodes-v1.json").read_bytes()).hexdigest()
    assert document["derivedFrom"]["predecessorDerivedFrom"]["studyEpoch"] == SWEEP


def test_the_digests_are_identical_under_python39_isolated_and_this_interpreter(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import importlib.util, json, sys\n"
        f"s = importlib.util.spec_from_file_location('c', {str(MODULE / 'execution/candidate_repeat_c.py')!r})\n"
        "m = importlib.util.module_from_spec(s); sys.modules['c'] = m; s.loader.exec_module(m)\n"
        "d = m.load_descriptor(); b = m.repeat_b.load_descriptor()\n"
        "print(json.dumps([m.canonical_sha256(d), m.canonical_sha256(m.compile_plan(d, 1)), m.MINIMUM_REMAINING_SECONDS,"
        " m.RUN_WINDOW_HOURS, m.canonical_sha256(b), m.canonical_sha256(m.repeat_b.compile_plan(b, 1))]))\n"
    )
    result = subprocess.run(
        [str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
        capture_output=True, text=True, check=True,
    )
    expected = [C_DESCRIPTOR_SHA256, C_PLAN_A1_SHA256, 13_416, 5, REPEAT_DESCRIPTOR_SHA256, REPEAT_PLAN_A1_SHA256]
    assert json.loads(result.stdout) == expected
    document = c.load_descriptor()
    assert [c.canonical_sha256(document), c.canonical_sha256(c.compile_plan(document, 1))] == expected[:2]


# ------------------------------------------------------------------------------------- 2. B's shape exactly
def _descriptor_differences(document, base):
    """(top-level keys that differ, {parent: subkeys that differ}) between two descriptors."""
    top = {key for key in set(document) | set(base) if document.get(key) != base.get(key)}
    nested = {}
    for parent in sorted(top):
        if isinstance(document.get(parent), dict) and isinstance(base.get(parent), dict) and parent not in c.REPLACED_DESCRIPTOR_KEYS:
            nested[parent] = {key for key in set(document[parent]) | set(base[parent])
                              if document[parent].get(key) != base[parent].get(key)}
    return {key for key in top if key not in nested}, nested


def test_the_descriptor_is_bs_apart_from_exactly_the_declared_keys():
    document, base = c.load_descriptor(), repeat.load_descriptor()
    assert repeat.canonical_sha256(base) == REPEAT_DESCRIPTOR_SHA256
    top, nested = _descriptor_differences(document, base)
    assert top == set(c.REPLACED_DESCRIPTOR_KEYS) - {"amendments"}         # B's amendments are [] too
    assert nested == {key: set(value) for key, value in c.REPLACED_DESCRIPTOR_SUBKEYS.items()}
    # What B was: H10, H4, the budget, the scenarios and doses, the trace rules per cell kind -- all inherited verbatim.
    for key in ("timing", "faultDesign", "groundTruth", "collection", "workload", "protocolGates", "containerHealthGuard"):
        assert document[key] == base[key], key
    assert document["analysis"]["traceCompleteness"] == base["analysis"]["traceCompleteness"]
    assert {k: v for k, v in document["design"].items() if k != "purpose"} == {
        k: v for k, v in base["design"].items() if k != "purpose"}
    assert document["schedule"]["seed"] == SEED != base["schedule"]["seed"]
    assert {k: v for k, v in document["schedule"].items() if k not in ("seed", "blocks")} == {
        k: v for k, v in base["schedule"].items() if k not in ("seed", "blocks")}


def test_planted_defect_a_descriptor_that_drifts_from_b_outside_the_declared_keys_is_found():
    document, base = c.load_descriptor(), repeat.load_descriptor()
    drifted = copy.deepcopy(document)
    drifted["timing"]["budget"]["runWindowHours"] = 6
    drifted["faultDesign"]["scenarios"]["productcatalog-cpu-throttle"]["nanoCpus"] = 200_000_000
    top, nested = _descriptor_differences(drifted, base)
    assert nested["timing"] == {"budget"} and nested["faultDesign"] == {"scenarios"}
    assert nested != {key: set(value) for key, value in c.REPLACED_DESCRIPTOR_SUBKEYS.items()}


def test_every_cell_is_bs_cell_for_the_same_regime_rate_and_block_apart_from_the_onset():
    plan, base = _plan(1), repeat.compile_plan(repeat.load_descriptor(), 1)
    cells = {(x["runKey"]["regime"], x["runKey"]["requestsPerSecond"], x["runKey"]["block"]): x for x in c.flatten_cells(plan)}
    b_cells = {(x["runKey"]["regime"], x["runKey"]["requestsPerSecond"], x["runKey"]["block"]): x
               for x in repeat.flatten_cells(base)}
    assert set(cells) == set(b_cells) and len(cells) == 36
    onsets_differ = 0
    for key, cell in cells.items():
        b_cell = b_cells[key]
        assert _strip(cell["timing"], c.ONSET_TIMING_KEYS) == _strip(b_cell["timing"], c.ONSET_TIMING_KEYS), key
        assert set(cell["timing"]) == set(b_cell["timing"])
        assert (cell["fault"], cell["realizationStatus"]) == (b_cell["fault"], b_cell["realizationStatus"])
        timing = cell["timing"]
        assert timing["faultOnsetSeconds"] == round(60 + timing["faultOnsetPhaseOffsetSeconds"], 6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"], round(timing["faultOnsetSeconds"] + 60, 6)]
        assert 0 <= timing["faultOnsetPhaseOffsetSeconds"] < 1.0 / key[1]
        if cell["fault"] is not None:
            assert timing["scheduledSlotsByPhase"] == sweep.scheduled_slots_by_phase(key[1], 180, timing["faultOnsetSeconds"], 60)
        else:
            assert timing["scheduledSlotsByPhase"] is None and timing["traceCompletenessRule"] == "protocol-decision-56"
        assert (timing["duringFaultProbe"], timing["freezeStamps"]) == (False, True)
        onsets_differ += timing["faultOnsetSeconds"] != b_cell["timing"]["faultOnsetSeconds"]
    assert onsets_differ == 36                                   # new draws: no onset repeats B's for its cell
    # The plan layout is B's: same keys, kind, budget and blockers; epoch, descriptor digest, orders and cells differ.
    assert set(plan) == set(base) and plan["kind"] == base["kind"]
    same = {k for k in plan if plan[k] == base[k]}
    assert set(plan) - same == {"studyEpoch", "descriptorSha256", "schedule", "blocks"}


def test_new_seed_and_epoch_give_new_block_orders_and_onsets_stratified_over_the_three_blocks():
    document, base = c.load_descriptor(), repeat.load_descriptor()
    assert [row["orderSha256"] for row in document["schedule"]["blocks"]] != [
        row["orderSha256"] for row in base["schedule"]["blocks"]]
    assert all(mine["order"] != theirs["order"]
               for mine, theirs in zip(document["schedule"]["blocks"], base["schedule"]["blocks"]))
    for receipt in document["schedule"]["blocks"]:
        expected = quiet.fisher_yates(
            [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES],
            SEED, C, receipt["block"], "repeat-schedule-v1",
        )
        assert receipt["order"] == ["%s@r%s" % (row["regime"], c.rate_token(row["rate"])) for row in expected]
    cells = c.flatten_cells(_plan(1))
    for regime in REGIMES:
        for rate in RATES:
            rows = [x["timing"] for x in cells if (x["runKey"]["regime"], x["runKey"]["requestsPerSecond"]) == (regime, rate)]
            strata = sorted(int(row["faultOnsetPhaseOffsetSeconds"] / (1.0 / rate) * 3) for row in rows)
            assert strata == [0, 1, 2], (regime, rate, strata)


# ------------------------------------------------------------------------------------- 3. no run-ID reuse
def _ran_run_ids() -> dict:
    """Run IDs of every attempt that ran on fb14srv6 (sweep, quiet A and A2, B), per (epoch, attempt)."""
    compilers = {SWEEP: sweep, QUIET: quiet, REPEAT: repeat}
    ids = {}
    for epoch, attempts in RAN.items():
        compiler = compilers[epoch]
        document = compiler.load_descriptor()
        for attempt in attempts:
            ids[(epoch, attempt)] = {cell["runId"] for cell in compiler.flatten_cells(compiler.compile_plan(document, attempt))}
    return ids


def _reused(run_ids, ran) -> dict:
    return {key: len(run_ids & ids) for key, ids in ran.items() if run_ids & ids}


def test_no_c_run_id_equals_one_that_ran_in_the_sweep_quiet_a_a2_or_b():
    ran = _ran_run_ids()
    assert {key: len(ids) for key, ids in ran.items()} == {
        (SWEEP, 1): 12, (SWEEP, 2): 12, (QUIET, 1): 40, (QUIET, 2): 40, (QUIET, 3): 40, (REPEAT, 1): 36}
    for attempt in (1, 2, 3):
        ids = {cell["runId"] for cell in c.flatten_cells(_plan(attempt))}
        assert len(ids) == 36 and _reused(ids, ran) == {}
    b_plan = repeat.compile_plan(repeat.load_descriptor(), 1)
    assert repeat.canonical_sha256(b_plan) == REPEAT_PLAN_A1_SHA256       # the B IDs checked are the ones that ran


def test_planted_defect_with_bs_epoch_the_plan_would_reuse_bs_36_run_ids_and_the_check_finds_them():
    """The planted defect: C's compiler left with B's epoch id and seed (a copy of B never re-keyed)."""
    ran = _ran_run_ids()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(c, "EPOCH", REPEAT)
        patch.setattr(c, "SCHEDULE_SEED", repeat.SCHEDULE_SEED)
        planted = c._compile(c.derive_c_descriptor(), 1)
    ids = {cell["runId"] for cell in c.flatten_cells(planted)}
    assert _reused(ids, ran) == {(REPEAT, 1): 36}
    # With B's epoch but C's seed the run IDs are B's too (they hash the run key, not the order): the epoch is what keys them.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(c, "EPOCH", REPEAT)
        ids = {c.run_id_for(c.run_key_for(r, q, b, "full", 1)) for r in REGIMES for q in RATES for b in (1, 2, 3)}
    assert _reused(ids, ran) == {(REPEAT, 1): 36}


# ------------------------------------------------------------------------------------- 4. the spent tables
def _spent_table_in_source() -> dict:
    tree_ = ast.parse((MODULE / "execution/candidate_runtime_adapter.py").read_text())
    for node in tree_.body:
        if isinstance(node, ast.Assign) and any(getattr(t_, "id", None) == "SPENT_ATTEMPTS_BY_EPOCH" for t_ in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SPENT_ATTEMPTS_BY_EPOCH not found")


def test_c_has_spent_nothing_and_b_attempt_1_is_spent():
    table = _spent_table_in_source()
    assert table[C] == {}
    assert set(table[REPEAT]) == {1} and "3aaf5923" in table[REPEAT][1]


def test_the_b_tree_adapter_refuses_b_attempt_1(tmp_path_factory, tmp_path):
    b_tree = _tree(tmp_path_factory, REPEAT, "repeat-c-b-tree")
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_repeat_c_b_tree_adapter", b_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.STUDY_EPOCH == REPEAT and set(adapter.SPENT_ATTEMPTS) == {1}
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
                adapter.inspect_campaign(tmp_path / "plan-b1", "a" * 40)
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


# ------------------------------------------------------------- 5. the epoch in the runtime, the gate chain and the target
def test_the_selector_activates_campaign_c_in_every_reader(c_tree, tmp_path):
    runtime = c_tree.runtime
    assert runtime.STUDY_EPOCH == C and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (36, 13_416, 5)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | C_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_repeat_c.py"
    assert runtime.CONTROLLER_PATHS["repeat-compiler"] == "modules/otel-demo/execution/candidate_repeat.py"
    assert runtime.DESCRIPTOR == c_tree.root / "pipelines/campaigns/otel-repeat-episodes-c-v1.json"
    assert c_tree.setup.controller_paths(C) == runtime.CONTROLLER_PATHS
    assert c_tree.setup.EPOCH_CONTROLLER_PATHS[C] == runtime.EPOCH_CONTROLLER_PATHS[C]
    digests = runtime.controller_digests()
    for key, relative in (("repeat-compiler", "execution/candidate_repeat.py"), ("quiet-compiler", "execution/candidate_quiet.py")):
        assert digests[key] == hashlib.sha256((MODULE / relative).read_bytes()).hexdigest()
    assert runtime.frozen_descriptor()["id"] == C
    # B's timing key sets: H10/H4 on every cell, the trace rule on no-fault cells only.
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {"duringFaultProbe", "freezeStamps"}
    assert runtime.timed_cell_timing_keys(False) == runtime.timed_cell_timing_keys(True) | {"traceCompletenessRule"}
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    copied = load("otel_repeat_c_driver_config_tree", c_tree.root / "modules/otel-demo/drivers/gate_driver_config.py")
    assert (copied.CONFIG.study, copied.CONFIG.campaign_id, copied.CONFIG.run_window_hours) == (C, C, 5)
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_repeat_c_tree_adapter", c_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == C
        assert adapter.pilot.EPOCH == C and adapter.SPENT_ATTEMPTS == {}          # nothing has run: attempt 1 is free
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 36 and bindings.plan_sha256 == C_PLAN_A1_SHA256
        assert bindings.descriptor_sha256 == C_DESCRIPTOR_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_gate_chain_derives_36_cells_the_budget_and_host_paths_disjoint_from_every_earlier_epoch(c_tree, c_package, tmp_path):
    runtime, remote = c_tree.runtime, c_tree.remote
    plan_text = c_package.gate_plan["typedApproval"]
    assert f"study={C} " in plan_text and " runs=36 " in plan_text and f"campaign={C} " in plan_text
    assert c_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 13_416
    binding = c_package.gate_plan["binding"]
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_repeat_episodes_c_v1"
    assert remote.SAFE_NAME.fullmatch(binding["compose"]["project"])
    earlier = (SWEEP, QUIET, REPEAT)
    other = ["/home/stig/observability-placement-candidate-v4-runs/" + epoch for epoch in earlier] + [
        "/home/stig/observability-placement-candidate-v4-runs/.setup-" + epoch for epoch in earlier] + [
        "/home/stig/observability-placement-candidate-v4-otel-srv6/" + epoch + "-" for epoch in earlier]
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert C in binding[key] and not any(binding[key].startswith(path) for path in other), key
    assert set(binding["controllerDigests"]) == helpers.FROZEN_CONTROLLER_KEYS | C_CONTROLLER_KEYS
    document = runtime.execution_package(c_package)
    assert document["runCount"] == 36 and len(document["cells"]) == 36
    pauses = 0
    for contract, cell in zip(document["cells"], c_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and runtime.sweep_cell_timing(contract) == cell["timing"]
        scenario, artifacts = contract["fault"]["scenario"], contract["requiredArtifacts"]
        assert ("docker-events.json" in artifacts) == (scenario == "frontend-pause")
        pauses += scenario == "frontend-pause"
    assert pauses == 12
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (C,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
    assert len(cells) == 36 and remote.expected_minimum_remaining(document) == 13_416


def test_the_target_treats_campaign_c_as_a_repeat_epoch_and_a_b_only_membership_is_refused(c_tree, c_package):
    remote = c_tree.remote
    assert C in remote.REPEAT_STUDY_EPOCHS and C in remote.TIMED_STUDY_EPOCHS and REPEAT in remote.REPEAT_STUDY_EPOCHS
    cells = c_tree.runtime.execution_package(c_package)["cells"]
    fault = next(x for x in cells if x["fault"]["scenario"] is not None)
    clean = next(x for x in cells if x["fault"]["scenario"] is None)
    remote.require_harness_flags_consistent(fault)
    assert remote.names_trace_rule(clean) is True and remote.names_trace_rule(fault) is False
    # Planted: the target knows only B as a repeat epoch (C's H10/H4 keys and trace rule would then be refused).
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "REPEAT_STUDY_EPOCHS", (REPEAT,))
        with pytest.raises(remote.RuntimeFailure, match="H10"):
            remote.require_harness_flags_consistent(fault)
        assert remote.names_trace_rule(clean) is False


CASES = (
    ("frontend-pause-effect", 10.0, 1),
    ("productcatalog-cpu-throttle-effect", 0.05, 2),
    ("no-fault-calibration", 0.2, 3),
)


@pytest.mark.parametrize("regime,rate,block", CASES)
def test_run_cell_executes_a_campaign_c_cell_and_the_terminal_accepts_it(c_tree, c_package, tmp_path, monkeypatch, regime, rate, block):
    contract = b_tests._contract(c_tree, c_package, regime, rate, tmp_path, block)
    assert contract["studyEpoch"] == C
    receipt, target = b_tests._run(c_tree, contract, monkeypatch)
    root = Path(contract["remoteArtifactRoot"])
    assert receipt["state"] == "valid", receipt["error"]
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    with b_tests.bound(c_tree):
        report = c_tree.terminal.validate_cell(root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    if contract["fault"]["scenario"] is None:
        assert b_tests._read(contract, "trace-completeness.json")["rule"] == "protocol-decision-56"
        return
    assert b_tests._probes_inside_the_fault(target, contract) == []                      # H10
    intervention = b_tests._read(contract, "intervention.json")
    assert intervention["duringRouteAvailable"] is None and intervention["freeze"]["stampCheck"]["status"] == "ok"   # H4
    if contract["fault"]["action"] == "pause":
        assert b_tests._read(contract, "docker-events.json")["verdict"]["status"] == "ok"


# ------------------------------------------------------------------------------------- 6. decision 66 membership
@pytest.fixture(scope="module")
def materialized_c(tmp_path_factory):
    out = {}
    for label, epoch in (("c", C), ("b", REPEAT), ("quiet", QUIET)):
        tree = helpers._copy_tree(
            tmp_path_factory.mktemp("materialize-c-" + label),
            selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n",
        )
        out[label] = tree / "out"
        out[label + "-digest"] = b_tests._materialize(tree, out[label])
    return out


def test_campaign_cs_collector_config_turns_the_log_sampler_off_exactly_as_bs(materialized_c):
    materialize = load("otel_repeat_c_materialize_module", MODULE / "materialize.py")
    assert C in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS and REPEAT in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS
    assert QUIET not in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS
    config = b_tests._collector_config(materialized_c["c"])
    assert b_tests._log_sampling_enabled(config) is False
    assert config == b_tests._collector_config(materialized_c["b"])
    assert b_tests._log_sampling_enabled(b_tests._collector_config(materialized_c["quiet"])) is None
    # The rendered trees of C and B are byte-identical file for file (the selector is not part of the materialized source).
    files = sorted(str(p.relative_to(materialized_c["c"])) for p in materialized_c["c"].rglob("*") if p.is_file())
    assert files and all(
        (materialized_c["c"] / name).read_bytes() == (materialized_c["b"] / name).read_bytes() for name in files)
    assert materialized_c["c-digest"] == materialized_c["b-digest"] != materialized_c["quiet-digest"]


def test_planted_defect_without_c_in_the_sampling_off_tuple_the_config_keeps_the_sampler(tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": C}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    marker = 'COLLECTOR_LOG_SAMPLING_OFF_EPOCHS = ("otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1")'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, 'COLLECTOR_LOG_SAMPLING_OFF_EPOCHS = ("otel-repeat-episodes-v1",)'))
    b_tests._materialize(tree, tree / "out")
    assert b_tests._log_sampling_enabled(b_tests._collector_config(tree / "out")) is None


# ------------------------------------------------------------------------------------- 7. the 3.9 floor
C_TARGET_FILES = (
    "modules/otel-demo/execution/candidate_repeat_c.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/execution/candidate_runtime_adapter.py",
    "modules/otel-demo/materialize.py",
)


@pytest.mark.parametrize("relative", C_TARGET_FILES)
def test_touched_target_files_parse_as_python39_and_read_no_name_bound_nowhere(relative):
    tree_ = ast.parse((ROOT / relative).read_text(), feature_version=(3, 9))
    assert b_tests._unbound_names(tree_) == []
    assert any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__" and any(a.name == "annotations" for a in node.names)
        for node in tree_.body
    ), "a PEP 604 annotation would be evaluated eagerly on 3.9 (py_compile does not catch it)"
