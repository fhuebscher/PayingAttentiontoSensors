"""otel-repeat-episodes-v1: campaign B on the OTel Demo (main repo research/PROTOCOL_DRAFT_20261002.md decisions 49, 50, 56
and 66; budget research/traffic-sweep/BUDGET_B.md, 92ca1c7; harness changes research/protocol/METHODOLOGY_HARDENING.md
H10 and H4).

Covers: the plan is 36 cells (3 blocks x 3 regimes x 4 rates), each block holding every (regime, rate) pair once in a seeded
Fisher-Yates order (seed 20261009, no lead cell) with one seeded fault onset per (regime, rate, block) stratified over the 3
blocks; every cell is the sweep's cell apart from the onset, the plan budget, the H10/H4 flags and (no-fault cells only) the
decision-56 trace rule; the sweep and quiet epochs are unchanged (their files at the quiet relaunch commit 6a47d0b, their
descriptors and plans, their materialized source, and the terminal's verdict on their artifacts); H10 (no probe from the fault
onset to the end of the hold) proven on the fake target's request log, with a planted defect; H4 (command issued / returned /
state readback, and the Docker pause and unpause events with the cell's monotonic mapping) executed end to end and replayed by
the terminal, with planted defects in the source and in the retained artifacts; which trace rule applies to which cell; the
collector's log sampler off in the repeat epoch's rendered config (decision 66) and nowhere else; the gate chain, host paths,
and the 3.9 floor.

Like the sweep's and the quiet epoch's tests, the epoch is exercised in a copy of the module tree with its own selector, so
these tests pass whichever epoch the worktree's committed selector names.
"""
from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
REPEAT = "otel-repeat-episodes-v1"
QUIET = "otel-quiet-calibration-v1"
SWEEP = "otel-traffic-sweep-v1"
OFFPATH = "otel-demo-offpath-v1"
BASE_COMMIT = "92be2b7"             # the frozen offpath epoch's harness
SWEEP_COMMIT = "c532853"            # the harness of the sweep's relaunch 1 (terminal-valid 12/12, 2026-10-03)
QUIET_COMMIT = "6a47d0b"            # the harness of the quiet epoch's relaunch 1 (the commit B is built on)
RATES = (10.0, 1.0, 0.2, 0.05)
REGIMES = ("no-fault-calibration", "frontend-pause-effect", "productcatalog-cpu-throttle-effect")
TRACE_RULE_56 = "protocol-decision-56"

REPEAT_DESCRIPTOR_SHA256 = "6e5d0f3460d28142428221c259994011a3a02973392aca4ffe6a4eb47a81a4ce"
REPEAT_PLAN_A1_SHA256 = "3aaf5923a051270f715aab822dafb7d63bbe0c8d6475f984afa2e2317cb2b142"
# What the sweep and quiet epochs ran / were pinned at (must not move).
SWEEP_DESCRIPTOR_SHA256 = "be5b0b4dcd212aaa47908a6dd533e5cb73a104ab22b1b9e04a147e21ccb2c86d"
SWEEP_PLAN_A1_SHA256 = "09b2563a7f15a0d50da49418b7aa9be203c4e1ecbfe95faf9edebf9729924865"
SWEEP_PLAN_A2_SHA256 = "fa770ccf62f3eca24081d0c9ca004c05104250da69ee3422bcf8a172b5349498"
QUIET_DESCRIPTOR_SHA256 = "36a7fd173a9995e6b0c0e9897d98ff76995ca375e045b90804fe92221dfd2286"
QUIET_PLAN_A1_SHA256 = "f2e7158fd2e007b705ad598459aad6a97940f42c9f8f86134b97d844ea4d9fc6"
QUIET_PLAN_A2_SHA256 = "bb1eb1fc6bb4047b83c69d4d216d70b18f49dd7689c1245e4d0b7d0e18ffe8d6"
REPEAT_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor", "quiet-compiler",
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


repeat = load("otel_repeat_compiler_test", MODULE / "execution/candidate_repeat.py")
sweep = repeat.sweep
quiet = repeat.quiet
# The sweep's test module supplies the tree copy, the gate-document builder and the fake target (read, not edited).
helpers = load("otel_repeat_sweep_test_helpers", ROOT / "tests/test_otel_traffic_sweep.py")
NOW = helpers.NOW


def _git_show(relative: str, commit: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"], capture_output=True, check=True,
    ).stdout


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
    compiler = {SWEEP: "candidate_sweep.py", QUIET: "candidate_quiet.py", REPEAT: "candidate_repeat.py"}[epoch]
    loaded.compiler = load(f"otel_{label}_compiler", module / "execution" / compiler)
    return loaded


@contextlib.contextmanager
def bound(tree):
    """The terminal resolves its runtime and remote through these module names: bind them to ``tree``."""
    names = ("otel_candidate_terminal_runtime", "otel_candidate_terminal_remote")
    saved = {name: sys.modules.get(name) for name in names}
    sys.modules["otel_candidate_terminal_runtime"] = tree.runtime
    sys.modules["otel_candidate_terminal_remote"] = tree.remote
    try:
        yield
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@pytest.fixture(scope="module")
def repeat_tree(tmp_path_factory):
    return _tree(tmp_path_factory, REPEAT, "repeat-tree")


@pytest.fixture(scope="module")
def sweep_tree(tmp_path_factory):
    return _tree(tmp_path_factory, SWEEP, "repeat-sweep-tree")


@pytest.fixture(scope="module")
def quiet_tree(tmp_path_factory):
    return _tree(tmp_path_factory, QUIET, "repeat-quiet-tree")


@pytest.fixture(scope="module")
def repeat_package(repeat_tree, tmp_path_factory):
    return helpers._package(repeat_tree.runtime, repeat_tree.compiler, tmp_path_factory.mktemp("repeat-package"), window_hours=5)


@pytest.fixture(scope="module")
def sweep_package(sweep_tree, tmp_path_factory):
    return helpers._package(sweep_tree.runtime, sweep_tree.compiler, tmp_path_factory.mktemp("repeat-sweep-package"), window_hours=3)


@pytest.fixture(scope="module")
def quiet_package(quiet_tree, tmp_path_factory):
    return helpers._package(quiet_tree.runtime, quiet_tree.compiler, tmp_path_factory.mktemp("repeat-quiet-package"), window_hours=6)


# ------------------------------------------------------------------------------------------ 1. the plan
def test_the_plan_is_36_cells_3_blocks_each_holding_every_regime_and_rate_once():
    document = repeat.load_descriptor()
    plan = repeat.compile_plan(document, 1)
    cells = repeat.flatten_cells(plan)
    assert repeat.canonical_sha256(document) == REPEAT_DESCRIPTOR_SHA256
    assert repeat.canonical_sha256(plan) == REPEAT_PLAN_A1_SHA256
    assert len(cells) == plan["runCount"] == plan["uniqueRunCount"] == repeat.TOTAL_RUNS == 36
    assert len({cell["runId"] for cell in cells}) == 36
    assert [block["block"] for block in plan["blocks"]] == [1, 2, 3]
    pairs = sorted((regime, rate) for regime in REGIMES for rate in RATES)
    for block in plan["blocks"]:
        assert sorted((c["runKey"]["regime"], c["runKey"]["requestsPerSecond"]) for c in block["cells"]) == pairs
        assert {c["runKey"]["block"] for c in block["cells"]} == {block["block"]}
        assert [c["ordinalPosition"] for c in block["cells"]] == list(range(1, 13))
    assert {c["runKey"]["posture"] for c in cells} == {"full"} and {c["runKey"]["studyEpoch"] for c in cells} == {REPEAT}
    assert {c["fault"] for c in cells} == {None, "frontend-pause", "productcatalog-cpu-throttle"}
    assert sum(c["fault"] is None for c in cells) == 12 and sum(c["fault"] is not None for c in cells) == 24
    # None of the sweep's run IDs: the epoch is part of the run key.
    sweep_ids = {c["runId"] for c in sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor(), 1))}
    assert not sweep_ids & {c["runId"] for c in cells}
    assert repeat.canonical_json_bytes(repeat.compile_plan(document, 1)) == repeat.canonical_json_bytes(plan)


def test_the_order_is_a_seeded_fisher_yates_per_block_with_no_lead_cell():
    document = repeat.load_descriptor()
    plan = repeat.compile_plan(document, 1)
    assert document["schedule"]["seed"] == plan["schedule"]["seed"] == 20261009
    assert document["schedule"]["leadCell"] is None and plan["schedule"]["blockOrders"] == document["schedule"]["blocks"]
    for receipt, block in zip(document["schedule"]["blocks"], plan["blocks"]):
        expected = quiet.fisher_yates(
            [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES],
            20261009, REPEAT, receipt["block"], "repeat-schedule-v1",
        )
        assert receipt["order"] == ["%s@r%s" % (row["regime"], repeat.rate_token(row["rate"])) for row in expected]
        assert receipt["orderSha256"] == repeat.canonical_sha256(receipt["order"])
        assert [(c["runKey"]["regime"], c["runKey"]["requestsPerSecond"]) for c in block["cells"]] == [
            (row["regime"], row["rate"]) for row in expected]
    assert len({tuple(receipt["order"]) for receipt in document["schedule"]["blocks"]}) == 3      # keyed by block
    # The sweep's lead cell (frontend pause at 10/s first) is not forced here.
    leads = {(plan["blocks"][b]["cells"][0]["runKey"]["regime"], plan["blocks"][b]["cells"][0]["runKey"]["requestsPerSecond"])
             for b in range(3)}
    assert leads != {("frontend-pause-effect", 10.0)}


def test_every_cell_is_the_sweeps_cell_apart_from_the_declared_differences():
    plan = repeat.compile_plan(repeat.load_descriptor(), 1)
    for cell in repeat.flatten_cells(plan):
        regime, rate = cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"]
        timing, base = cell["timing"], sweep.cell_timing(regime, rate, 1)
        faulted = cell["fault"] is not None
        differing = {key for key in set(timing) | set(base) if timing.get(key) != base.get(key)}
        # Every key that differs is one this epoch sets itself (the onset draw and what follows from it) or is new.
        assert differing <= repeat.OWN_TIMING_KEYS | repeat.NO_FAULT_ONLY_TIMING_KEYS | {"faultOnsetPhaseOffsetSeconds"}
        assert set(timing) - set(base) == {"duringFaultProbe", "freezeStamps"} | (
            set() if faulted else {"traceCompletenessRule"})
        assert (timing["duringFaultProbe"], timing["freezeStamps"]) == (False, True)
        assert timing["planRunCount"] == 36 and timing["planMinimumRemainingSeconds"] == 13_416
        for key in ("route", "concurrency", "requestTimeoutSeconds", "warmupSeconds", "measurementSeconds", "offered",
                    "faultHoldSeconds", "serviceMemoryLimitBytes", "containerHealthGuard", "upstreamGeneratorsOff",
                    "traceDrainSeconds", "traceIncompleteAllowanceShare", "traceIncompleteAllowanceMinimum"):
            assert timing[key] == base[key], key
        assert timing["route"]["path"] == "/api/products/66VCHSJNUP"
        assert (timing["concurrency"], timing["requestTimeoutSeconds"]) == (300, 15.0)
        assert timing["serviceMemoryLimitBytes"] == {"frontendproxy": 256 * 1024 * 1024}
        assert (timing["scheduledSlotsByPhase"] is None) == (not faulted)
        if faulted:
            assert all(count >= 1 for count in timing["scheduledSlotsByPhase"].values())
            assert timing["scheduledSlotsByPhase"] == sweep.scheduled_slots_by_phase(
                rate, 180, timing["faultOnsetSeconds"], 60)
        assert timing["faultOnsetSeconds"] == round(60 + timing["faultOnsetPhaseOffsetSeconds"], 6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"], round(timing["faultOnsetSeconds"] + 60, 6)]
        assert 0 <= timing["faultOnsetPhaseOffsetSeconds"] < 1.0 / rate


def test_the_trace_rule_key_is_on_no_fault_cells_only():
    """Decision 25 for fault cells (no key, as the sweep), decision 56 for no-fault cells (the key, as the quiet epoch)."""
    plan = repeat.compile_plan(repeat.load_descriptor(), 1)
    for cell in repeat.flatten_cells(plan):
        assert ("traceCompletenessRule" in cell["timing"]) == (cell["fault"] is None)
        if cell["fault"] is None:
            assert cell["timing"]["traceCompletenessRule"] == TRACE_RULE_56 == quiet.TRACE_COMPLETENESS_RULE


def test_onsets_are_stratified_over_the_three_blocks_inside_one_inter_arrival():
    cells = repeat.flatten_cells(repeat.compile_plan(repeat.load_descriptor(), 1))
    for regime in REGIMES:
        for rate in RATES:
            rows = [c["timing"] for c in cells if (c["runKey"]["regime"], c["runKey"]["requestsPerSecond"]) == (regime, rate)]
            assert len(rows) == 3
            strata = sorted(int(row["faultOnsetPhaseOffsetSeconds"] / (1.0 / rate) * 3) for row in rows)
            assert strata == [0, 1, 2], (regime, rate, strata)
    # With the sweep's seed, epoch and stratum count the shared rule reproduces the sweep's own offsets.
    for regime in REGIMES:
        for rate in RATES:
            assert quiet.stratified_onset_offset(
                sweep.SCHEDULE_SEED, sweep.EPOCH, sweep.EPISODES, regime, rate, 1) == sweep.onset_phase_offset(regime, rate, 1)
    # Keyed by (regime, rate, block), never by attempt: attempt 2 keeps every timing and changes every run ID.
    first = repeat.flatten_cells(repeat.compile_plan(repeat.load_descriptor(), 1))
    second = repeat.flatten_cells(repeat.compile_plan(repeat.load_descriptor(), 2))
    assert [c["timing"] for c in first] == [c["timing"] for c in second]
    assert not {c["runId"] for c in first} & {c["runId"] for c in second}


def test_budget_and_run_window_are_derived_from_the_plan():
    assert repeat.MINIMUM_REMAINING_SECONDS == 36 * 331 + 900 + 600 == 13_416
    assert repeat.RUN_WINDOW_HOURS == 5 == -(-(13_416 + 3600) // 3600)
    assert repeat.MEASURED_CELL_PERIOD_SECONDS["maximum"] < repeat.CELL_PERIOD_ESTIMATE_SECONDS
    budget = repeat.load_descriptor()["timing"]["budget"]
    assert (budget["minimumRemainingSeconds"], budget["runWindowHours"]) == (13_416, 5)


def test_the_descriptor_file_is_the_generators_output_and_records_the_binding_changes():
    path = ROOT / "pipelines/campaigns/otel-repeat-episodes-v1.json"
    assert path.read_bytes() == repeat._pretty_bytes(repeat.derive_repeat_descriptor())
    document = repeat.load_descriptor()
    assert document["id"] == REPEAT and document["derivedFrom"]["studyEpoch"] == SWEEP
    assert document["derivedFrom"]["descriptorCanonicalSha256"] == SWEEP_DESCRIPTOR_SHA256
    assert document["timing"]["duringFaultProbe"] is False and document["timing"]["freezeStamps"] is True
    assert document["design"]["blocks"] == 3 and document["design"]["totalRuns"] == 36
    assert set(document["design"]["harnessChanges"]) == {"H10", "H4"}
    scenarios = document["faultDesign"]["scenarios"]
    assert {s["entryRouteDuringFault"] for s in scenarios.values()} == {"not-probed-h10"}
    assert scenarios["productcatalog-cpu-throttle"]["nanoCpus"] == 100_000_000      # decision 50: the dose is inherited
    rules = document["analysis"]["traceCompleteness"]
    assert set(rules["ruleByCellKind"]) == {"fault", "no-fault"}
    assert "decision-25" in rules["ruleByCellKind"]["fault"] and TRACE_RULE_56 in rules["ruleByCellKind"]["no-fault"]
    assert rules["faultCells"]["drainRule"] and rules["noFaultCells"]["ruleId"] == TRACE_RULE_56
    assert "freeze" in document["groundTruth"]["fault"]["requiredReceiptFields"]


def test_a_planted_descriptor_or_plan_edit_is_refused():
    document = repeat.load_descriptor()
    plan = repeat.compile_plan(document, 1)
    planted = copy.deepcopy(document)
    planted["schedule"]["seed"] = 20261003
    with pytest.raises(repeat.ProtocolError, match="differs from its generator"):
        repeat.validate_descriptor(planted)
    planted = copy.deepcopy(document)
    planted["timing"]["duringFaultProbe"] = True
    with pytest.raises(repeat.ProtocolError, match="differs from its generator"):
        repeat.validate_descriptor(planted)
    for mutate in (
        lambda p: p["blocks"][1]["cells"][0]["timing"].update(faultOnsetSeconds=61.0),
        lambda p: p["blocks"][0]["cells"].pop(),
        lambda p: p["blocks"][2]["cells"][1]["timing"].update(duringFaultProbe=True),
        lambda p: p["blocks"][2]["cells"][1]["timing"].update(freezeStamps=False),
        lambda p: p["schedule"].update(seed=1),
    ):
        broken = copy.deepcopy(plan)
        mutate(broken)
        with pytest.raises(repeat.ProtocolError, match="differs from the frozen schedule"):
            repeat.validate_plan(document, broken)
    with pytest.raises(repeat.ProtocolError, match="unknown regime"):
        repeat.cell_timing("net-delay", 10.0, 1)
    with pytest.raises(repeat.ProtocolError, match="outside 1..3"):
        repeat.block_order(4)


# ---------------------------------------------------------------------- 2. the sweep and quiet epochs are unchanged
@pytest.mark.parametrize("relative", (
    "modules/otel-demo/execution/candidate_sweep.py",
    "pipelines/campaigns/otel-traffic-sweep-v1.json",
    "modules/otel-demo/execution/candidate_quiet.py",
    "pipelines/campaigns/otel-quiet-calibration-v1.json",
    "modules/otel-demo/execution/candidate_pilot.py",
    "pipelines/campaigns/otel-demo-offpath-v1.json",
    "modules/otel-demo/validation/protocol_gates.py",
    "modules/otel-demo/drivers/gate_driver_config.py",
    "modules/otel-demo/workload.py",
    "modules/otel-demo/deployment/compose.otel-placement.yml",
    "modules/otel-demo/deployment/compose.candidate-postures.yml",
))
def test_the_sweeps_and_quiet_epochs_files_are_byte_identical_to_the_quiet_relaunch_commit(relative):
    assert (ROOT / relative).read_bytes() == _git_show(relative, QUIET_COMMIT)


def test_the_sweeps_and_quiet_epochs_keep_their_digests_and_their_controller_sets(sweep_tree, quiet_tree):
    document = sweep.load_descriptor()
    assert sweep.canonical_sha256(document) == SWEEP_DESCRIPTOR_SHA256
    assert sweep.canonical_sha256(sweep.compile_plan(document, 1)) == SWEEP_PLAN_A1_SHA256
    assert sweep.canonical_sha256(sweep.compile_plan(document, 2)) == SWEEP_PLAN_A2_SHA256
    document = quiet.load_descriptor()
    assert quiet.canonical_sha256(document) == QUIET_DESCRIPTOR_SHA256
    assert quiet.canonical_sha256(quiet.compile_plan(document, 1)) == QUIET_PLAN_A1_SHA256
    assert quiet.canonical_sha256(quiet.compile_plan(document, 2)) == QUIET_PLAN_A2_SHA256
    # Their runtime bindings are as at 6a47d0b: the sweep's and the quiet epoch's controller keys, and their run windows.
    assert set(sweep_tree.runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | helpers.SWEEP_CONTROLLER_KEYS
    assert (sweep_tree.runtime.RUN_COUNT, sweep_tree.runtime.RUN_WINDOW_HOURS) == (12, 3)
    assert (quiet_tree.runtime.RUN_COUNT, quiet_tree.runtime.RUN_WINDOW_HOURS) == (40, 6)
    assert "quiet-compiler" not in quiet_tree.runtime.CONTROLLER_PATHS
    assert quiet_tree.runtime.timed_cell_timing_keys() == quiet_tree.runtime.SWEEP_TIMING_KEYS | {"traceCompletenessRule"}
    assert sweep_tree.runtime.timed_cell_timing_keys() == sweep_tree.runtime.SWEEP_TIMING_KEYS
    assert sweep_tree.runtime.timed_cell_timing_keys(True) == sweep_tree.runtime.SWEEP_TIMING_KEYS


# ------------------------------------------------- 3. the repeat epoch in the runtime, the gate chain and the host paths
def test_the_selector_activates_the_repeat_epoch_in_every_reader(repeat_tree, tmp_path):
    runtime = repeat_tree.runtime
    assert runtime.STUDY_EPOCH == REPEAT and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (36, 13_416, 5)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | REPEAT_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_repeat.py"
    assert runtime.DESCRIPTOR == repeat_tree.root / "pipelines/campaigns/otel-repeat-episodes-v1.json"
    assert repeat_tree.setup.controller_paths(REPEAT) == runtime.CONTROLLER_PATHS
    assert repeat_tree.setup.EPOCH_CONTROLLER_PATHS[REPEAT] == runtime.EPOCH_CONTROLLER_PATHS[REPEAT]
    digests = runtime.controller_digests()
    for key, relative in (("quiet-compiler", "execution/candidate_quiet.py"), ("sweep-compiler", "execution/candidate_sweep.py")):
        assert digests[key] == hashlib.sha256((MODULE / relative).read_bytes()).hexdigest()
    assert runtime.frozen_descriptor()["id"] == REPEAT
    # The key sets: H10/H4 on every cell, the trace rule on no-fault cells only.
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {"duringFaultProbe", "freezeStamps"}
    assert runtime.timed_cell_timing_keys(False) == runtime.timed_cell_timing_keys(True) | {"traceCompletenessRule"}
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    copied = load("otel_repeat_driver_config_tree", repeat_tree.root / "modules/otel-demo/drivers/gate_driver_config.py")
    assert (copied.CONFIG.study, copied.CONFIG.campaign_id, copied.CONFIG.run_window_hours) == (REPEAT, REPEAT, 5)
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_repeat_tree_adapter", repeat_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == REPEAT
        # 2026-10-10: attempt 1 ran (2026-10-09, plan 3aaf5923) and is recorded spent: the driver path refuses it. Its plan
        # is still the pinned one (the planted removal of the row plans it again), and a relaunch would be attempt 2.
        assert adapter.pilot.EPOCH == REPEAT and set(adapter.SPENT_ATTEMPTS) == {1}
        assert "3aaf5923" in adapter.SPENT_ATTEMPTS[1] and "c4aa313" in adapter.SPENT_ATTEMPTS[1]
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
                adapter.inspect_campaign(tmp_path / "plan-a1", "a" * 40)
            patch.delitem(adapter.SPENT_ATTEMPTS, 1)
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 36 and bindings.plan_sha256 == REPEAT_PLAN_A1_SHA256
        assert bindings.descriptor_sha256 == REPEAT_DESCRIPTOR_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_the_tombstone_names_exactly_the_epoch_the_committed_selector_names():
    selected = json.loads((MODULE / "execution/study-epoch.json").read_text())["studyEpoch"]
    remote = load("otel_repeat_real_remote", MODULE / "execution/candidate_remote.py")
    setup = load("otel_repeat_real_setup", MODULE / "execution/candidate_setup.py")
    assert remote.ADMITTED_STUDY_EPOCHS == setup.ADMITTED_STUDY_EPOCHS == (selected,)
    # 2026-10-11: campaign C (otel-repeat-episodes-c-v1) joins B in the repeat family (tests/test_otel_repeat_episodes_c.py).
    # 2026-10-12: the load pilot (otel-load-pilot-v1) joins the family too (tests/test_otel_load_pilot.py).
    # 2026-10-13: the off-path pilot (otel-offpath-pilot-v1) joins the family too (tests/test_otel_offpath_pilot.py).
    assert remote.TIMED_STUDY_EPOCHS == (
        SWEEP, QUIET, REPEAT, "otel-repeat-episodes-c-v1", "otel-load-pilot-v1", "otel-offpath-pilot-v1",
        "otel-offpath-pilot-v2", "otel-offpath-e-v1")
    assert remote.REPEAT_STUDY_EPOCH == REPEAT and remote.REPEAT_STUDY_EPOCHS == (
        REPEAT, "otel-repeat-episodes-c-v1", "otel-load-pilot-v1", "otel-offpath-pilot-v1", "otel-offpath-pilot-v2",
        "otel-offpath-e-v1")


def test_gate_chain_derives_36_cells_the_budget_and_disjoint_host_paths(repeat_tree, repeat_package, tmp_path):
    runtime, remote = repeat_tree.runtime, repeat_tree.remote
    plan_text = repeat_package.gate_plan["typedApproval"]
    assert f"study={REPEAT} " in plan_text and " runs=36 " in plan_text and f"campaign={REPEAT} " in plan_text
    assert " runs=36 " in repeat_package.gate_run["typedApproval"]
    assert repeat_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 13_416
    binding = repeat_package.gate_plan["binding"]
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_repeat_episodes_v1"
    assert remote.SAFE_NAME.fullmatch(binding["compose"]["project"]) and len(REPEAT) <= 40
    other = [
        "/home/stig/observability-placement-candidate-v4-runs/" + epoch for epoch in (SWEEP, QUIET)
    ] + ["/home/stig/observability-placement-candidate-v4-runs/.setup-" + epoch for epoch in (SWEEP, QUIET)] + [
        "/home/stig/observability-placement-candidate-v4-otel-srv6/" + epoch + "-" for epoch in (SWEEP, QUIET)]
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert REPEAT in binding[key] and not any(binding[key].startswith(path) for path in other), key
    assert set(binding["controllerDigests"]) == helpers.FROZEN_CONTROLLER_KEYS | REPEAT_CONTROLLER_KEYS
    document = runtime.execution_package(repeat_package)
    assert document["runCount"] == 36 and len(document["cells"]) == 36
    pauses = 0
    for contract, cell in zip(document["cells"], repeat_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and contract["runId"] == cell["runId"]
        assert contract["workloadPathCheck"]["gatesCampaign"] is False
        assert runtime.sweep_cell_timing(contract) == cell["timing"]
        scenario, artifacts = contract["fault"]["scenario"], contract["requiredArtifacts"]
        assert ("intervention.json" in artifacts) == (scenario is not None)
        # H4: only a pause cell retains the Docker events.
        assert ("docker-events.json" in artifacts) == (scenario == "frontend-pause")
        pauses += scenario == "frontend-pause"
        if scenario is not None:
            assert contract["fault"]["entryRouteDuringFault"] == "not-probed-h10"
    assert pauses == 12
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (REPEAT,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
        remote.refuse_unsupported("probe", REPEAT)
    assert len(cells) == 36 and remote.expected_run_count(document) == 36
    assert remote.expected_minimum_remaining(document) == 13_416
    assert remote.require_path_check_before_faults(cells) == -1
    with pytest.raises(runtime.GateError, match="too little time for 36 cells"):
        helpers._package(runtime, repeat_tree.compiler, tmp_path / "short", window_hours=3)


def test_a_contract_cannot_drop_or_change_its_h10_h4_or_trace_rule_keys(repeat_tree, repeat_package):
    runtime = repeat_tree.runtime
    cells = runtime.execution_package(repeat_package)["cells"]
    fault = next(c for c in cells if c["fault"]["scenario"] is not None)
    clean = next(c for c in cells if c["fault"]["scenario"] is None)
    for contract, key in ((fault, "duringFaultProbe"), (fault, "freezeStamps"), (clean, "traceCompletenessRule")):
        dropped = copy.deepcopy(contract)
        del dropped["timing"][key]
        with pytest.raises(runtime.GateError, match="cell timing fields differ"):
            runtime.sweep_cell_timing(dropped)
    # A fault cell cannot carry the no-fault trace rule, nor a no-fault cell lack it.
    planted = copy.deepcopy(fault)
    planted["timing"]["traceCompletenessRule"] = TRACE_RULE_56
    with pytest.raises(runtime.GateError, match="cell timing fields differ"):
        runtime.sweep_cell_timing(planted)
    for contract, key, value in ((fault, "duringFaultProbe", True), (fault, "freezeStamps", False),
                                 (clean, "traceCompletenessRule", "protocol-decision-25")):
        changed = copy.deepcopy(contract)
        changed["timing"][key] = value
        with pytest.raises(runtime.GateError, match="not the active compiled plan's timing"):
            runtime.sweep_cell_timing(changed)


# ---------------------------------------------------------------- 4. a fake-driven execution of the target's runner
class RepeatTarget(helpers.FakeTarget):
    """The sweep tests' fake fb14srv6 plus the repeat epoch's observables: every request that carries the readiness token
    is logged with its monotonic start (H10), and the Docker pause/unpause events of the paused container are produced
    from the moment the fake pauses it (H4).  ``event_skew`` delays the events, ``drop_events`` loses them,
    ``duplicate_pause`` repeats the pause event and ``stream_exits`` makes the stream die before it is stopped."""

    def __init__(self, contract, clock, *, event_skew=0.0, drop_events=(), duplicate_pause=False, stream_exits=False,
                 other_container_events=0, garbage_line=False, start_fails=False, **options):
        super().__init__(contract, clock, **options)
        self.probe_starts = []
        self.event_log = []
        self.event_skew, self.drop_events = event_skew, set(drop_events)
        self.duplicate_pause, self.stream_exits = duplicate_pause, stream_exits
        self.other_container_events = other_container_events
        self.garbage_line, self.start_fails = garbage_line, start_fails
        self.events_started = 0

    def http_get(self, url, headers, timeout):
        if headers.get("x-obsplacement-request-token") == "readiness-not-scored":
            self.probe_starts.append(self.clock.monotonic())
        return super().http_get(url, headers, timeout)

    def command(self, argv, **kwargs):
        result = super().command(argv, **kwargs)
        argv = [str(item) for item in argv]
        if argv[:2] == ["docker", "compose"] and len(argv) > 10 and argv[10] in ("pause", "unpause"):
            self.event_log.append((argv[10], self.clock.time()))     # the daemon emits it as the freeze takes effect
        return result

    def event_lines(self):
        def line(action, at, cid="cid-frontend", service="frontend"):
            return json.dumps({
                "status": action, "id": cid, "from": "img", "Type": "container", "Action": action,
                "Actor": {"ID": cid, "Attributes": {"com.docker.compose.service": service, "name": service}},
                "scope": "local", "time": int(at), "timeNano": int((at + self.event_skew) * 1e9),
            })
        rows = [line(action, at) for action, at in self.event_log if action not in self.drop_events]
        if self.duplicate_pause and self.event_log:
            rows.append(line("pause", self.event_log[0][1]))
        rows += [line("pause", self.clock.time(), cid=f"cid-other{index}", service="cartservice")
                 for index in range(self.other_container_events)]
        if self.garbage_line:
            rows.append("this is not a docker event")
        return rows


def _contract(tree, package, regime: str, rate: float, tmp_path: Path, block: int = 1) -> dict:
    document = tree.runtime.execution_package(package)
    contract = copy.deepcopy(next(
        c for c in document["cells"]
        if (c["runKey"]["regime"], c["runKey"]["requestsPerSecond"], c["runKey"]["block"]) == (regime, rate, block)
    ))
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


def _run(tree, contract, monkeypatch, *, remote=None, target_class=RepeatTarget, **fake_options):
    """The target's per-cell runner (``remote``, by default the tree's) against the fake fb14srv6."""
    remote = remote if remote is not None else tree.remote
    clock = helpers.FakeTime(helpers.real_time.time())
    target = target_class(contract, clock, **fake_options)
    target.contract["_firstToken"] = remote.request_identity(contract["runId"], 0)[0]
    monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (contract["studyEpoch"],))      # the activation edit
    monkeypatch.setattr(remote, "time", clock)
    monkeypatch.setattr(remote, "command", target.command)
    monkeypatch.setattr(remote, "http_get", target.http_get)
    monkeypatch.setattr(remote, "post_json", target.post_json)
    monkeypatch.setattr(remote, "docker_stats", target.docker_stats)
    monkeypatch.setattr(remote, "cell_environment", lambda cell: {"OTEL_IMAGE_TAG": "fake"})

    def start_capture(path):
        Path(path).write_bytes(b"\xd4\xc3\xb2\xa1fake-pcap")
        return remote.Capture(types.SimpleNamespace(poll=lambda: 0, pid=0, returncode=0), Path(path).with_suffix(".log"))

    monkeypatch.setattr(remote, "start_capture", start_capture)
    monkeypatch.setattr(remote, "stop_capture", lambda capture: None)
    if hasattr(remote, "start_docker_events"):
        def start_events(cell):
            if target.start_fails:
                raise OSError("docker: not found")
            target.events_started += 1
            return types.SimpleNamespace(
                argv=remote.docker_events_argv(cell["compose"]["project"], int(clock.time()) - 1), since=int(clock.time()) - 1)

        def stop_events(handle):
            rows = target.event_lines()
            return {"argv": handle.argv, "sinceEpoch": handle.since, "exitedBeforeStop": bool(target.stream_exits),
                    "returnCode": 1 if target.stream_exits else -15, "stderr": "", "error": None, "raw": rows}

        monkeypatch.setattr(remote, "start_docker_events", start_events)
        monkeypatch.setattr(remote, "stop_docker_events", stop_events)
    receipt = remote.run_cell(contract, datetime.now(timezone.utc) + timedelta(hours=5))
    return receipt, target


def _read(contract, name):
    return json.loads((Path(contract["remoteArtifactRoot"]) / name).read_text())


def _probes_inside_the_fault(target, contract):
    """Readiness-token requests that started from the fault onset to the end of the hold (the scored window)."""
    barrier = _read(contract, "request-ledger.json")["barrierMonotonic"]
    onset, hold = contract["timing"]["faultOnsetSeconds"], contract["timing"]["faultHoldSeconds"]
    return [at for at in target.probe_starts if barrier + onset <= at <= barrier + onset + hold]


CASES = (
    ("frontend-pause-effect", 10.0, 1),
    ("frontend-pause-effect", 0.05, 2),
    ("productcatalog-cpu-throttle-effect", 10.0, 3),
    ("productcatalog-cpu-throttle-effect", 0.05, 1),
    ("no-fault-calibration", 0.2, 2),
)


@pytest.mark.parametrize("regime,rate,block", CASES)
def test_run_cell_executes_a_repeat_cell_and_the_terminal_accepts_it(
    repeat_tree, repeat_package, tmp_path, monkeypatch, regime, rate, block,
):
    contract = _contract(repeat_tree, repeat_package, regime, rate, tmp_path, block)
    receipt, target = _run(repeat_tree, contract, monkeypatch)
    root = Path(contract["remoteArtifactRoot"])
    assert receipt["state"] == "valid", receipt["error"]
    timing = contract["timing"]
    ledger = _read(contract, "request-ledger.json")
    assert ledger["offered"] == timing["offered"] == len(ledger["requests"]) and ledger["ratePerSecond"] == rate
    faulted = contract["fault"]["scenario"] is not None
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    with bound(repeat_tree):
        report = repeat_tree.terminal.validate_cell(root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    # H10: no readiness-token request between the onset and the end of the hold; probes outside it are the same as before
    # (the readiness waits before the warm-up and the post-revert readiness probes).
    barrier = ledger["barrierMonotonic"]
    assert target.probe_starts and min(target.probe_starts) < barrier
    if not faulted:
        assert not (root / "intervention.json").exists() and not (root / "docker-events.json").exists()
        assert target.events_started == 0 and report["fault"] is None
        return
    assert _probes_inside_the_fault(target, contract) == []
    intervention = _read(contract, "intervention.json")
    assert intervention["duringRouteAvailable"] is None and intervention["manifested"] is True
    assert {row["phase"] for row in intervention["probes"]} == {"post-revert"}
    assert intervention["probes"][-1]["available"] is True
    onset_end = barrier + timing["faultOnsetSeconds"] + timing["faultHoldSeconds"]
    assert all(at >= onset_end for at in target.probe_starts if at > barrier)
    # H4: the stamps, in order, on the receipt's clock.
    freeze = intervention["freeze"]
    assert freeze["kind"] == "otel-demo-fault-freeze-stamps-v1" and freeze["action"] == contract["fault"]["action"]
    assert freeze["commandIssuedMonotonic"] == intervention["startedMonotonic"]
    assert freeze["stateReadbackMonotonic"] == intervention["appliedMonotonic"]
    assert freeze["commandIssuedMonotonic"] <= freeze["commandReturnedMonotonic"] <= freeze["stateReadbackMonotonic"]
    assert freeze["commandReturnedMonotonic"] - freeze["commandIssuedMonotonic"] >= helpers.COMMAND_SECONDS - 0.2
    assert freeze["commandReturnedOffsetSeconds"] == freeze["commandReturnedMonotonic"] - barrier
    assert report["fault"]["freeze"]["commandReturnedOffsetSeconds"] == freeze["commandReturnedOffsetSeconds"]
    if contract["fault"]["action"] == "pause":
        record = json.loads((root / "docker-events.json").read_text())
        assert (record["kind"], record["runId"], record["service"]) == (
            "otel-demo-fault-docker-events-v1", contract["runId"], "frontend")
        assert freeze["dockerEventsFile"] == "docker-events.json" and target.events_started == 1
        assert record["clock"]["barrierMonotonic"] == ledger["barrierMonotonic"]
        assert record["clock"]["barrierEpoch"] == ledger["barrierEpoch"]
        events = {event["action"]: event for event in record["events"]}
        assert sorted(events) == ["pause", "unpause"]
        assert (record["verdict"]["status"], record["verdict"]["failures"], record["verdict"]["reasons"]) == ("ok", 0, [])
        assert freeze["stampCheck"] == {"status": "ok", "failures": 0, "reasons": []}
        # The Docker pause event lies between the command's issue and return; the unpause between the revert's.
        assert freeze["commandIssuedOffsetSeconds"] - 0.25 <= events["pause"]["offsetSeconds"] <= (
            freeze["commandReturnedOffsetSeconds"] + 0.25)
        assert intervention["revertingMonotonicOffsetSeconds"] - 0.25 <= events["unpause"]["offsetSeconds"] <= (
            intervention["actualOffsetMonotonicOffsetSeconds"] + 0.25)
        assert events["pause"]["monotonic"] == pytest.approx(barrier + events["pause"]["offsetSeconds"])
        assert report["fault"]["dockerEvents"]["onsetIntervalSeconds"][0] == freeze["commandIssuedOffsetSeconds"]
    else:
        assert freeze["dockerEventsFile"] is None and target.events_started == 0
        assert not (root / "docker-events.json").exists()
        assert ["docker", "update", "--cpus", "0.100", "cid-productcatalogservice"] in target.commands
        assert intervention["throttle"]["duringNanoCpus"] == 100_000_000       # decision 50: the dose is unchanged


def test_h10_planted_defect_a_probe_in_the_window_is_caught_by_the_checker_and_the_terminal(
    repeat_tree, repeat_package, tmp_path, monkeypatch,
):
    """The planted defect: the during-fault probe is reinstated (the sweep's behaviour) in a repeat cell."""
    contract = _contract(repeat_tree, repeat_package, "frontend-pause-effect", 1.0, tmp_path / "guarded", 1)
    monkeypatch.setattr(repeat_tree.remote, "h10_enabled", lambda timing: False)
    # First line of defence: the runner refuses a cell whose flag and scenario contract disagree, before any container.
    with pytest.raises(repeat_tree.remote.RuntimeFailure, match="differs from the cell's H10 flag"):
        _run(repeat_tree, contract, monkeypatch)
    # With that guard also gone, the test's own checker and then the terminal catch the probe.
    monkeypatch.setattr(repeat_tree.remote, "require_harness_flags_consistent", lambda cell: None)
    contract = _contract(repeat_tree, repeat_package, "frontend-pause-effect", 1.0, tmp_path / "unguarded", 1)
    receipt, target = _run(repeat_tree, contract, monkeypatch)
    assert receipt["state"] == "valid", receipt["error"]          # the target itself does not notice
    assert len(_probes_inside_the_fault(target, contract)) == 1    # the test's checker does
    intervention = _read(contract, "intervention.json")
    assert intervention["duringRouteAvailable"] is False and "during-fault" in {row["phase"] for row in intervention["probes"]}
    with bound(repeat_tree):
        with pytest.raises(repeat_tree.terminal.ValidationError, match="H10"):
            repeat_tree.terminal.validate_cell(Path(contract["remoteArtifactRoot"]), contract)


def test_h4_planted_defect_no_freeze_stamps_means_no_docker_events_and_an_invalid_cell(
    repeat_tree, repeat_package, tmp_path, monkeypatch,
):
    contract = _contract(repeat_tree, repeat_package, "frontend-pause-effect", 1.0, tmp_path, 1)
    monkeypatch.setattr(repeat_tree.remote, "freeze_enabled", lambda timing: False)
    receipt, target = _run(repeat_tree, contract, monkeypatch)
    assert receipt["state"] == "invalid" and "missing=['docker-events.json']" in receipt["error"]
    assert target.events_started == 0 and "freeze" not in _read(contract, "intervention.json")


@pytest.mark.parametrize("option,status,message", (
    ({"drop_events": ("pause",)}, "missing", "no pause event of the target container"),
    ({"drop_events": ("unpause",)}, "missing", "no unpause event of the target container"),
    ({"drop_events": ("pause", "unpause")}, "missing", "no pause event"),
    ({"duplicate_pause": True}, "contradictory", "2 pause events of the target container"),
    ({"event_skew": 10.0}, "contradictory", "the pause event .* is outside the pause command"),
    ({"stream_exits": True}, "missing", "had exited before the fault settled"),
    ({"garbage_line": True}, "contradictory", "docker event line is not JSON"),
    ({"start_fails": True}, "missing", "the docker events stream could not be used: RuntimeFailure: OSError: docker: not found"),
))
def test_h4_a_failed_dead_or_contradictory_event_stream_is_recorded_and_the_cell_stays_valid(
    repeat_tree, repeat_package, tmp_path, monkeypatch, option, status, message,
):
    """Decision 69 (user 2026-10-09): H4 is record, don't block.  The same stream defects that invalidated the cell under the
    first draft now leave it valid, with the record marked missing or contradictory, its reasons and its failure count; the
    terminal accepts the retained record because it replays."""
    contract = _contract(repeat_tree, repeat_package, "frontend-pause-effect", 1.0, tmp_path, 1)
    receipt, _ = _run(repeat_tree, contract, monkeypatch, **option)
    assert receipt["state"] == "valid", receipt["error"]
    verdict = _read(contract, "docker-events.json")["verdict"]
    assert verdict["status"] == status and verdict["failures"] == len(verdict["reasons"]) >= 1
    assert __import__("re").search(message, " | ".join(row["reason"] for row in verdict["reasons"])), verdict["reasons"]
    assert {row["kind"] for row in verdict["reasons"]} <= {"missing", "contradictory"}
    with bound(repeat_tree):
        report = repeat_tree.terminal.validate_cell(Path(contract["remoteArtifactRoot"]), contract)
    assert report["state"] == "valid"
    assert (report["fault"]["dockerEvents"]["status"], report["fault"]["dockerEvents"]["failures"]) == (status, verdict["failures"])


def test_h4_contradictory_stamps_are_recorded_and_the_cell_stays_valid(repeat_tree, repeat_package, tmp_path, monkeypatch):
    """The producer's own stamps contradict each other (the command 'returns' before it was issued): recorded, not blocking."""
    original = repeat_tree.remote.freeze_stamps

    def bad(action, issued, returned, readback, barrier):
        return original(action, issued, issued - 0.5, readback, barrier)

    monkeypatch.setattr(repeat_tree.remote, "freeze_stamps", bad)
    contract = _contract(repeat_tree, repeat_package, "productcatalog-cpu-throttle-effect", 1.0, tmp_path, 1)
    receipt, _ = _run(repeat_tree, contract, monkeypatch)
    assert receipt["state"] == "valid", receipt["error"]
    check = _read(contract, "intervention.json")["freeze"]["stampCheck"]
    assert check["status"] == "contradictory" and check["failures"] == 1
    assert "issued <= returned <= readback" in check["reasons"][0]["reason"]
    with bound(repeat_tree):
        report = repeat_tree.terminal.validate_cell(Path(contract["remoteArtifactRoot"]), contract)
    assert (report["fault"]["freeze"]["stampStatus"], report["fault"]["freeze"]["stampFailures"]) == ("contradictory", 1)


def test_h4_events_of_other_containers_are_recorded_and_do_not_count(repeat_tree, repeat_package, tmp_path, monkeypatch):
    contract = _contract(repeat_tree, repeat_package, "frontend-pause-effect", 0.2, tmp_path, 3)
    receipt, _ = _run(repeat_tree, contract, monkeypatch, other_container_events=2)
    assert receipt["state"] == "valid", receipt["error"]
    verdict = _read(contract, "docker-events.json")["verdict"]
    assert (verdict["pauseEvents"], verdict["unpauseEvents"], verdict["otherContainerEvents"]) == (1, 1, 2)


# --------------------------------------------- planted defects in the retained artifacts: the terminal rejects each
@pytest.fixture(scope="module")
def sealed(repeat_tree, repeat_package, tmp_path_factory):
    cells = {}
    with pytest.MonkeyPatch.context() as patch:
        for regime, rate in (("frontend-pause-effect", 1.0), ("productcatalog-cpu-throttle-effect", 0.2)):
            base = tmp_path_factory.mktemp("repeat-sealed")
            contract = _contract(repeat_tree, repeat_package, regime, rate, base, 2)
            receipt, _ = _run(repeat_tree, contract, patch)
            assert receipt["state"] == "valid", receipt["error"]
            cells[regime] = (Path(contract["remoteArtifactRoot"]), contract)
    return cells


def _shift(value, keys, seconds):
    for key in keys:
        value[key] += seconds


PAUSE, THROTTLE = "frontend-pause-effect", "productcatalog-cpu-throttle-effect"
PLANTS = {
    "a-probe-inside-the-hold": (PAUSE, "intervention.json", lambda v: v["probes"].append({
        "phase": "post-revert", "startMonotonic": v["barrierMonotonic"] + v["appliedMonotonicOffsetSeconds"] + 5.0,
        "endMonotonic": v["barrierMonotonic"] + v["appliedMonotonicOffsetSeconds"] + 5.1, "available": False,
        "status": None}), "H10|outside its phase"),
    "a-during-fault-probe-appears": (PAUSE, "intervention.json", lambda v: v["probes"].append({
        "phase": "during-fault", "startMonotonic": v["appliedMonotonic"] + 1.0, "endMonotonic": v["appliedMonotonic"] + 1.1,
        "available": False, "status": None}), "H10"),
    "a-route-observation-appears": (PAUSE, "intervention.json", lambda v: v.__setitem__("duringRouteAvailable", False), "H10"),
    "the-freeze-block-is-dropped": (PAUSE, "intervention.json", lambda v: v.pop("freeze"), "intervention"),
    "the-freeze-returns-before-it-is-issued": (PAUSE, "intervention.json", lambda v: v["freeze"].update(
        commandReturnedMonotonic=v["freeze"]["commandIssuedMonotonic"] - 0.5,
        commandReturnedOffsetSeconds=v["freeze"]["commandIssuedOffsetSeconds"] - 0.5), "freeze stamp check does not replay"),
    "the-freeze-offsets-do-not-replay": (THROTTLE, "intervention.json", lambda v: v["freeze"].update(
        commandReturnedOffsetSeconds=v["freeze"]["commandReturnedOffsetSeconds"] + 0.4), "do not replay from the shared barrier"),
    "the-freeze-issue-stamp-differs-from-the-receipts": (THROTTLE, "intervention.json", lambda v: v["freeze"].update(
        commandIssuedMonotonic=v["freeze"]["commandIssuedMonotonic"] - 0.3,
        commandIssuedOffsetSeconds=v["freeze"]["commandIssuedOffsetSeconds"] - 0.3), "freeze stamp check does not replay"),
    "a-contradiction-relabelled-ok-in-the-stamp-check": (THROTTLE, "intervention.json", lambda v: v["freeze"].update(
        commandReturnedMonotonic=v["freeze"]["commandIssuedMonotonic"] - 0.5,
        commandReturnedOffsetSeconds=v["freeze"]["commandIssuedOffsetSeconds"] - 0.5,
        stampCheck={"status": "ok", "failures": 0, "reasons": []}), "freeze stamp check does not replay"),
    "a-throttle-claims-docker-events": (THROTTLE, "intervention.json", lambda v: v["freeze"].update(
        dockerEventsFile="docker-events.json"), "freeze stamps identity differs"),
    "the-pause-event-is-removed": (PAUSE, "docker-events.json", lambda v: (
        v.__setitem__("raw", [r for r in v["raw"] if json.loads(r)["Action"] != "pause"]),
        v.__setitem__("events", [e for e in v["events"] if e["action"] != "pause"])), "verdict does not replay"),
    "the-events-are-edited-but-not-the-raw-lines": (PAUSE, "docker-events.json", lambda v: v["events"][0].__setitem__(
        "offsetSeconds", v["events"][0]["offsetSeconds"] + 3.0), "do not replay from the retained raw lines"),
    "the-pause-event-is-moved-late-but-the-verdict-is-left-ok": (
        PAUSE, "docker-events.json", lambda v: _move_event(v, "pause", 4.0), "do not replay from the retained raw lines|verdict does not replay"),
    "a-parse-problem-is-hidden": (PAUSE, "docker-events.json", lambda v: (
        v["raw"].append("junk"), v["parseProblems"].clear()), "do not replay from the retained raw lines"),
    "a-failed-stream-is-relabelled-alive": (PAUSE, "docker-events.json", lambda v: v["stream"].update(
        exitedBeforeStop=True, error="x"), "verdict does not replay"),
    "the-verdict-is-relabelled-valid": (PAUSE, "docker-events.json", lambda v: (
        v["verdict"].__setitem__("pauseEvents", 2)), "verdict does not replay"),
    "another-container-id": (PAUSE, "docker-events.json", lambda v: v.__setitem__("containerId", "cid-cartservice"),
                             "identity, clock or stream differs"),
    "the-mapping-clock-is-moved": (PAUSE, "docker-events.json", lambda v: v["clock"].__setitem__(
        "barrierEpoch", v["clock"]["barrierEpoch"] + 1.0), "identity, clock or stream differs"),
    "the-stream-was-not-the-declared-command": (PAUSE, "docker-events.json", lambda v: v["stream"].__setitem__(
        "argv", v["stream"]["argv"][:-2]), "declared filtered"),
    "an-undeclared-action-in-the-stream": (PAUSE, "docker-events.json", lambda v: (
        v["raw"].append(json.dumps({"Action": "kill", "Actor": {"ID": "x", "Attributes": {}}, "timeNano": 1})),
        v["events"].append({"action": "kill", "containerId": "x", "service": None, "timeNano": 1,
                            "offsetSeconds": 1 / 1e9 - v["clock"]["barrierEpoch"],
                            "monotonic": v["clock"]["barrierMonotonic"] + 1 / 1e9 - v["clock"]["barrierEpoch"]})),
                                        "was not asked for"),
}


def _move_event(record, action, seconds):
    """Move one event later in the raw lines and in the parsed events together (so only the interval check can object)."""
    raw = []
    for line in record["raw"]:
        row = json.loads(line)
        if row["Action"] == action:
            row["timeNano"] += int(seconds * 1e9)
        raw.append(json.dumps(row))
    record["raw"] = raw
    for event in record["events"]:
        if event["action"] == action:
            event["timeNano"] += int(seconds * 1e9)
            event["offsetSeconds"] += seconds
            event["monotonic"] += seconds


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_planted_h10_h4_artifact_defects_are_rejected_by_the_terminal(repeat_tree, sealed, tmp_path, plant):
    regime, name, mutate, message = PLANTS[plant]
    source, contract = sealed[regime]
    cell_root = tmp_path / "cell"
    shutil.copytree(source, cell_root)
    with bound(repeat_tree):
        assert repeat_tree.terminal.validate_cell(cell_root, contract)["state"] == "valid"
        path = cell_root / name
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        (cell_root / "content-manifest.json").write_text(json.dumps(
            repeat_tree.remote.content_manifest(cell_root, contract["requiredArtifacts"]), indent=2, sort_keys=True) + "\n")
        with pytest.raises(repeat_tree.terminal.ValidationError, match=message):
            repeat_tree.terminal.validate_cell(cell_root, contract)


def test_a_consistently_recorded_contradiction_is_accepted_but_the_same_edit_without_its_record_is_refused(
    repeat_tree, sealed, tmp_path,
):
    """Integrity vs availability: a producer that records the pause event 4 s late and says so (contradictory) passes the
    terminal; the identical raw edit with the verdict left 'ok' does not."""
    source, contract = sealed[PAUSE]
    cell_root = tmp_path / "cell"
    shutil.copytree(source, cell_root)
    remote = repeat_tree.remote
    path = cell_root / "docker-events.json"
    record = json.loads(path.read_text())
    _move_event(record, "pause", 4.0)
    intervention = json.loads((cell_root / "intervention.json").read_text())
    events, problems = remote.parse_docker_events_lenient(record["raw"], record["clock"])
    record["events"], record["parseProblems"] = events, problems
    record["verdict"] = remote.docker_events_verdict(events, record["stream"], intervention, problems)
    assert record["verdict"]["status"] == "contradictory" and record["verdict"]["failures"] >= 1
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    (cell_root / "content-manifest.json").write_text(json.dumps(
        remote.content_manifest(cell_root, contract["requiredArtifacts"]), indent=2, sort_keys=True) + "\n")
    with bound(repeat_tree):
        report = repeat_tree.terminal.validate_cell(cell_root, contract)
    assert report["state"] == "valid" and report["fault"]["dockerEvents"]["status"] == "contradictory"


def test_a_missing_or_extra_events_file_is_refused_by_population(repeat_tree, sealed, tmp_path):
    source, contract = sealed[PAUSE]
    cell_root = tmp_path / "cell"
    shutil.copytree(source, cell_root)
    (cell_root / "docker-events.json").unlink()
    with bound(repeat_tree):
        with pytest.raises(repeat_tree.terminal.ValidationError, match="docker-events.json"):
            repeat_tree.terminal.validate_cell(cell_root, contract)
    source, contract = sealed[THROTTLE]
    cell_root = tmp_path / "throttle"
    shutil.copytree(source, cell_root)
    (cell_root / "docker-events.json").write_text("{}\n")
    with bound(repeat_tree):
        with pytest.raises(repeat_tree.terminal.ValidationError, match="docker-events.json"):
            repeat_tree.terminal.validate_cell(cell_root, contract)


def test_h10_h4_flags_belong_to_the_repeat_epoch_and_fail_closed_elsewhere(repeat_tree, repeat_package, sweep_tree, sweep_package):
    remote = repeat_tree.remote
    repeat_cell = repeat_tree.runtime.execution_package(repeat_package)["cells"][0]
    remote.require_harness_flags_consistent(repeat_cell)
    for mutate in (
        lambda c: c["timing"].update(duringFaultProbe=True),
        lambda c: c["timing"].update(freezeStamps=False),
        lambda c: (c["timing"].pop("duringFaultProbe"), c["timing"].pop("freezeStamps")),
        lambda c: c.update(studyEpoch=SWEEP),
    ):
        planted = copy.deepcopy(repeat_cell)
        mutate(planted)
        with pytest.raises(remote.RuntimeFailure, match="only the repeat-episodes epoch|runs with H10 and H4 on"):
            remote.require_harness_flags_consistent(planted)
    fault = next(c for c in repeat_tree.runtime.execution_package(repeat_package)["cells"] if c["fault"]["scenario"])
    planted = copy.deepcopy(fault)
    planted["fault"]["entryRouteDuringFault"] = "must-be-unavailable"
    with pytest.raises(remote.RuntimeFailure, match="entry-route expectation differs from the cell's H10 flag"):
        remote.require_harness_flags_consistent(planted)
    sweep_cell = sweep_tree.runtime.execution_package(sweep_package)["cells"][0]
    sweep_tree.remote.require_harness_flags_consistent(sweep_cell)
    planted = copy.deepcopy(sweep_cell)
    planted["timing"]["duringFaultProbe"] = False
    with pytest.raises(sweep_tree.remote.RuntimeFailure, match="only the repeat-episodes epoch"):
        sweep_tree.remote.require_harness_flags_consistent(planted)


# ------------------------------------------------------ 5. which trace rule applies to which cell
def _tokens(tree, contract, sequences):
    return {tree.remote.request_identity(contract["runId"], sequence)[0] for sequence in sequences}


def test_a_lost_batch_is_recorded_never_blocking_in_a_no_fault_cell(repeat_tree, repeat_package, tmp_path, monkeypatch):
    """Decision 56 in a no-fault repeat cell: the quiet attempt-1 pattern (50 consecutive requests without their
    productcatalogservice span at 10/s) seals valid with the loss recorded."""
    contract = _contract(repeat_tree, repeat_package, "no-fault-calibration", 10.0, tmp_path, 1)
    receipt, _ = _run(repeat_tree, contract, monkeypatch, lose_spans=_tokens(repeat_tree, contract, range(1349, 1399)))
    assert receipt["state"] == "valid", receipt["error"]
    record = _read(contract, "trace-completeness.json")
    assert (record["schemaVersion"], record["rule"], record["blocking"], record["valid"]) == (3, TRACE_RULE_56, False, True)
    window = record["windows"]["whole-measurement"]
    assert (window["successful"], window["incomplete"]) == (1800, 50)
    assert record["decision25Counterfactual"] == {"allowance": 18, "wouldHaveBlocked": True, "applied": False}
    with bound(repeat_tree):
        assert repeat_tree.terminal.validate_cell(Path(contract["remoteArtifactRoot"]), contract)["state"] == "valid"


def test_the_same_loss_outside_the_fault_and_drain_window_blocks_a_fault_cell_by_decision_25(
    repeat_tree, repeat_package, tmp_path, monkeypatch,
):
    """Decision 25 in a fault cell: 30 incomplete requests, all of them after the drain at 10/s, exceed max(1, 1 %)."""
    contract = _contract(repeat_tree, repeat_package, "productcatalog-cpu-throttle-effect", 10.0, tmp_path, 1)
    after = range(1500, 1530)      # scheduled 150-153 s: after the drain of a 60 s fault that began at about 60 s
    receipt, _ = _run(repeat_tree, contract, monkeypatch, lose_spans=_tokens(repeat_tree, contract, after))
    assert receipt["state"] == "invalid" and "trace completeness:" in receipt["error"], receipt["error"]
    record = _read(contract, "trace-completeness.json")
    assert record["rule"] == "protocol-decision-25" and record["valid"] is False and "traceCompletenessRule" not in contract["timing"]


def test_the_trace_rule_key_is_bound_to_the_cell_kind(repeat_tree):
    remote = repeat_tree.remote
    no_fault = repeat.cell_timing("no-fault-calibration", 1.0, 1)
    fault = repeat.cell_timing("frontend-pause-effect", 1.0, 1)
    assert remote.names_trace_rule({"studyEpoch": REPEAT, "timing": no_fault}) is True
    assert remote.names_trace_rule({"studyEpoch": REPEAT, "timing": fault}) is False
    assert remote.names_trace_rule({"studyEpoch": QUIET, "timing": no_fault}) is True
    assert remote.names_trace_rule({"studyEpoch": SWEEP, "timing": no_fault}) is False
    route = ["frontend", "frontendproxy", "productcatalogservice"]
    base = {"runId": "r" * 24, "posture": {"expected": {"activeApplicationServices": route}}}
    ledger, correlation = {"barrierMonotonic": 5000.0, "requests": []}, {"rows": []}
    # A repeat fault cell cannot opt in to decision 56, nor a repeat no-fault cell opt out.
    for timing, epoch in ((dict(fault, traceCompletenessRule=TRACE_RULE_56), REPEAT), (dict(no_fault), REPEAT)):
        timing = dict(timing)
        if epoch == REPEAT and timing["faultApplied"] is False:
            timing.pop("traceCompletenessRule")
        with pytest.raises(remote.RuntimeFailure, match="only the quiet calibration epoch's compiled timing"):
            remote.trace_completeness(dict(base, studyEpoch=epoch, timing=timing), ledger, correlation, None)
    # The record-only rule still refuses a fault cell (its receipt, or its timing's faultApplied).
    with pytest.raises(remote.RuntimeFailure, match="applies to no-fault cells only"):
        remote.trace_completeness(
            dict(base, studyEpoch=REPEAT, timing=dict(no_fault)), ledger, correlation, {"actualOnsetMonotonicOffsetSeconds": 60.0})


def test_the_sweeps_and_quiet_trace_records_are_byte_identical_to_the_quiet_relaunch_commit(tmp_path):
    old_file = tmp_path / "candidate_remote_6a47d0b.py"
    old_file.write_bytes(_git_show("modules/otel-demo/execution/candidate_remote.py", QUIET_COMMIT))
    old = load("otel_repeat_remote_6a47d0b", old_file)
    new = load("otel_repeat_remote_now", MODULE / "execution/candidate_remote.py")
    quiet_test = load("otel_repeat_quiet_test_helpers", ROOT / "tests/test_otel_quiet_calibration.py")
    for timing, epoch, lost, failed, rate in (
        (sweep.cell_timing("no-fault-calibration", 10.0, 1), SWEEP, set(range(1349, 1399)), (5,), 10.0),
        (quiet.cell_timing("no-fault-calibration", 10.0, 2), QUIET, set(range(1349, 1399)), (5,), 10.0),
        (sweep.cell_timing("productcatalog-cpu-throttle-effect", 1.0, 1), SWEEP, (3, 70, 71, 150), (), 1.0),
    ):
        cell, ledger, correlation = quiet_test._synthetic(timing, epoch=epoch, lost=lost, failed=failed, rate=rate)
        receipt = None if timing["faultApplied"] is False else {
            "actualOnsetMonotonicOffsetSeconds": timing["faultOnsetSeconds"],
            "readyAtMonotonic": 5000.0 + timing["faultOnsetSeconds"] + 61.0}
        assert quiet.canonical_json_bytes(new.trace_completeness(cell, ledger, correlation, receipt)) == (
            quiet.canonical_json_bytes(old.trace_completeness(cell, ledger, correlation, receipt)))


# ----------------------------------- 6. the sweep and quiet epochs behave as at 6a47d0b (target runner and terminal)
def _run_and_report(tree, package, regime, rate, block, tmp_path, monkeypatch, *, remote, terminal):
    contract = _contract(tree, package, regime, rate, tmp_path, block)
    receipt, target = _run(tree, contract, monkeypatch, remote=remote, target_class=helpers.FakeTarget)
    assert receipt["state"] == "valid", receipt["error"]
    root = Path(contract["remoteArtifactRoot"])
    with bound(tree):
        report = terminal.validate_cell(root, contract)
    intervention = json.loads((root / "intervention.json").read_text()) if (root / "intervention.json").exists() else None
    return contract, root, report, intervention, target


@pytest.mark.parametrize("regime,rate", (("frontend-pause-effect", 1.0), ("productcatalog-cpu-throttle-effect", 0.2)))
def test_the_target_runner_and_terminal_treat_a_sweep_cell_as_at_6a47d0b(
    sweep_tree, sweep_package, tmp_path, monkeypatch, regime, rate,
):
    TREE = sweep_tree
    old_remote = load("otel_repeat_old_remote_sweep", _write_old(TREE, "modules/otel-demo/execution/candidate_remote.py"))
    old_terminal = load("otel_repeat_old_terminal_sweep", _write_old(TREE, "modules/otel-demo/validation/candidate_terminal.py"))
    contract, root, report, intervention, target = _run_and_report(
        sweep_tree, sweep_package, regime, rate, 1, tmp_path / "new", monkeypatch,
        remote=sweep_tree.remote, terminal=sweep_tree.terminal)
    # The sweep's receipt: no freeze, a during-fault probe, the route observation, no events file.
    assert "freeze" not in intervention and "docker-events.json" not in contract["requiredArtifacts"]
    assert {row["phase"] for row in intervention["probes"]} == {"during-fault", "post-revert"}
    assert isinstance(intervention["duringRouteAvailable"], bool)
    assert not hasattr(target, "events_started")
    # The terminal at 6a47d0b judges the same artifacts the same way.
    with bound(sweep_tree):
        assert sweep_tree.runtime.canonical_bytes(old_terminal.validate_cell(root, contract)) == (
            sweep_tree.runtime.canonical_bytes(report))
    # And the old target runner produces the same artifact population and receipt shape for the same cell.
    old_tree = types.SimpleNamespace(**vars(sweep_tree))
    old_tree.remote = old_remote
    contract2, root2, report2, intervention2, _ = _run_and_report(
        old_tree, sweep_package, regime, rate, 1, tmp_path / "old", monkeypatch, remote=old_remote, terminal=sweep_tree.terminal)
    assert sorted(p.name for p in root.iterdir()) == sorted(p.name for p in root2.iterdir())
    assert set(intervention) == set(intervention2) and report["fault"]["scenario"] == report2["fault"]["scenario"]


def test_the_target_runner_and_terminal_treat_a_quiet_cell_as_at_6a47d0b(quiet_tree, quiet_package, tmp_path, monkeypatch):
    TREE = quiet_tree
    old_remote = load("otel_repeat_old_remote_quiet", _write_old(TREE, "modules/otel-demo/execution/candidate_remote.py"))
    old_terminal = load("otel_repeat_old_terminal_quiet", _write_old(TREE, "modules/otel-demo/validation/candidate_terminal.py"))
    contract, root, report, intervention, _ = _run_and_report(
        quiet_tree, quiet_package, "no-fault-calibration", 1.0, 4, tmp_path / "new", monkeypatch,
        remote=quiet_tree.remote, terminal=quiet_tree.terminal)
    assert intervention is None
    with bound(quiet_tree):
        assert quiet_tree.runtime.canonical_bytes(old_terminal.validate_cell(root, contract)) == (
            quiet_tree.runtime.canonical_bytes(report))
    record = json.loads((root / "trace-completeness.json").read_text())
    assert record["rule"] == TRACE_RULE_56 and record["kind"] == "otel-demo-quiet-trace-completeness-v3"
    old_tree = types.SimpleNamespace(**vars(quiet_tree))
    old_tree.remote = old_remote
    _, root2, _, _, _ = _run_and_report(
        old_tree, quiet_package, "no-fault-calibration", 1.0, 4, tmp_path / "old", monkeypatch,
        remote=old_remote, terminal=quiet_tree.terminal)
    assert sorted(p.name for p in root.iterdir()) == sorted(p.name for p in root2.iterdir())


def _write_old(tree, relative):
    """The file at 6a47d0b, beside its successor in the tree copy (the terminal resolves ROOT from its own location)."""
    target = (tree.root / relative).with_name(Path(relative).stem + "_6a47d0b.py")
    target.write_bytes(_git_show(relative, QUIET_COMMIT))
    return target


def test_the_terminal_judges_sweep_and_quiet_cells_as_it_did_at_6a47d0b_under_planted_defects(sweep_tree, sweep_package, tmp_path, monkeypatch):
    """The sweep's planted artifact defects are rejected with the same messages by the new terminal and the old one."""
    TREE = sweep_tree
    old_terminal = load("otel_repeat_old_terminal_plants", _write_old(TREE, "modules/otel-demo/validation/candidate_terminal.py"))
    contract, root, _, _, _ = _run_and_report(
        sweep_tree, sweep_package, "frontend-pause-effect", 1.0, 1, tmp_path / "cell", monkeypatch,
        remote=sweep_tree.remote, terminal=sweep_tree.terminal)
    plants = (
        ("intervention.json", lambda v: v.__setitem__("duringRouteAvailable", True), "entry route"),
        ("intervention.json", lambda v: v.__setitem__("probes", []), "probe stamps"),
        ("intervention.json", lambda v: v["probes"][0].__setitem__("startMonotonic", v["barrierMonotonic"] + 1.0), "outside its phase"),
        ("intervention.json", lambda v: v.__setitem__("freeze", {}), "intervention"),      # a freeze key is not the sweep's
    )
    for name, mutate, message in plants:
        copy_root = tmp_path / ("plant-" + str(abs(hash(message))))
        shutil.copytree(root, copy_root)
        helpers._plant(sweep_tree, copy_root, contract, name, mutate)
        with bound(sweep_tree):
            for terminal in (sweep_tree.terminal, old_terminal):
                with pytest.raises(terminal.ValidationError, match=message):
                    terminal.validate_cell(copy_root, contract)


# -------------------------------------------- 7. decision 66: the collector's log sampler is off in the repeat epoch only
def _materialize(tree_root: Path, out: Path, *, materializer: Path = None) -> str:
    script = materializer or (tree_root / "modules/otel-demo/materialize.py")
    result = subprocess.run(
        [sys.executable, "-I", str(script), "--out", str(out)], capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().splitlines()[-1]


def _collector_config(out: Path) -> str:
    return (out / "src/otelcollector/otelcol-placement.yml").read_text()


def _log_sampling_enabled(text: str):
    """service.telemetry.logs.sampling.enabled of a rendered collector config (None if the key is absent)."""
    yaml = pytest.importorskip("yaml")
    node = (yaml.safe_load(text).get("service") or {}).get("telemetry") or {}
    return ((node.get("logs") or {}).get("sampling") or {}).get("enabled")


@pytest.fixture(scope="module")
def materialized(tmp_path_factory):
    """The materializer run in a tree copy per selector: no selector (frozen), sweep, quiet, repeat; plus the materializer
    of the base commit 92be2b7 run in the same trees (its output is what every non-repeat epoch must keep)."""
    out = {}
    for label, selector in (("frozen", None), (SWEEP, SWEEP), (QUIET, QUIET), (REPEAT, REPEAT)):
        tree = helpers._copy_tree(
            tmp_path_factory.mktemp("materialize-" + label),
            selector=None if selector is None else json.dumps({"schemaVersion": 1, "studyEpoch": selector}) + "\n",
        )
        if selector is None:       # a tree with no selector is the frozen epoch (the copy brings the committed one)
            (tree / "modules/otel-demo/execution/study-epoch.json").unlink(missing_ok=True)
        base = tmp_path_factory.mktemp("materialize-base-" + label) / "materialize.py"
        base.write_bytes(_git_show("modules/otel-demo/materialize.py", BASE_COMMIT))
        # The base materializer resolves ROOT from its own location: place it where the tree's copy lives.
        old_in_tree = tree / "modules/otel-demo/materialize_base.py"
        old_in_tree.write_bytes(base.read_bytes())
        new_out, old_out = tree / "out-new", tree / "out-base"
        out[label] = {
            "new": _materialize(tree, new_out), "base": _materialize(tree, old_out, materializer=old_in_tree),
            "new_out": new_out, "base_out": old_out,
        }
    return out


@pytest.mark.parametrize("label", ("frozen", SWEEP, QUIET))
def test_the_materialized_source_of_the_frozen_sweep_and_quiet_epochs_is_unchanged(materialized, label):
    row = materialized[label]
    assert row["new"] == row["base"]
    assert _collector_config(row["new_out"]) == _collector_config(row["base_out"])
    assert _log_sampling_enabled(_collector_config(row["new_out"])) is None        # the collector's default sampler


def test_the_repeat_epochs_collector_config_turns_the_log_sampler_off_and_nothing_else_changes(materialized):
    row = materialized[REPEAT]
    config = _collector_config(row["new_out"])
    assert _log_sampling_enabled(config) is False
    assert "service:\n  telemetry:\n    logs:\n      sampling:\n        enabled: false\n  pipelines:\n" in config
    base = _collector_config(row["base_out"])
    assert config.replace("  telemetry:\n    logs:\n      sampling:\n        enabled: false\n", "") == base
    assert row["new"] != row["base"]                  # the materialized-source digest, bound in the GATE-PLAN, moves
    assert "verbosity: detailed" in config            # the debug exporter's verbosity is as before
    # Every other file of the materialized tree is byte-identical.
    changed = sorted(
        str(path.relative_to(row["new_out"])) for path in row["new_out"].rglob("*")
        if path.is_file() and path.read_bytes() != (row["base_out"] / path.relative_to(row["new_out"])).read_bytes()
    )
    assert changed == ["src/otelcollector/otelcol-placement.yml"] or changed == [
        ".source.sha256", "src/otelcollector/otelcol-placement.yml"]


def test_planted_defect_a_repeat_config_without_the_key_or_with_it_on_is_caught(materialized):
    base = _collector_config(materialized[REPEAT]["base_out"])
    assert _log_sampling_enabled(base) is None != False
    on = base.replace("service:\n  pipelines:\n", "service:\n  telemetry:\n    logs:\n      sampling:\n        enabled: true\n  pipelines:\n")
    assert _log_sampling_enabled(on) is True
    # The checker the two tests above use cannot be fooled by the key under a different parent.
    misplaced = base.replace("service:\n  pipelines:\n", "service:\n  pipelines:\n")
    misplaced += "telemetry:\n  logs:\n    sampling:\n      enabled: false\n"
    assert _log_sampling_enabled(misplaced) is None


def test_the_materializer_reads_the_epoch_from_the_selector_of_its_own_tree():
    materialize = load("otel_repeat_materialize_module", MODULE / "materialize.py")
    assert materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS == (
        REPEAT, "otel-repeat-episodes-c-v1", "otel-load-pilot-v1", "otel-offpath-pilot-v1", "otel-offpath-pilot-v2",
        "otel-offpath-e-v1")   # + C, 2026-10-11; + load pilot, 2026-10-12; + off-path pilot, 2026-10-13; + campaign E, 2026-10-12
    assert materialize.selected_study_epoch(Path("/nonexistent/study-epoch.json")) is None
    assert materialize.selected_study_epoch() == json.loads((MODULE / "execution/study-epoch.json").read_text())["studyEpoch"]


def test_the_collector_key_was_checked_against_the_pinned_collector_version():
    """The key ``service::telemetry::logs::sampling::enabled`` is a field of collector v0.108.0's service/telemetry
    LogsSamplingConfig (``Enabled bool `mapstructure:"enabled"```; source read at tag v0.108.0 on 2026-10-09, and the pinned
    image's otelcol-contrib binary, read from `docker save` of image 38088dde2576 on fb14srv6, carries the type
    telemetry.LogsSamplingConfig).  The pin below is what that check was made against: if the collector moves, the key must
    be checked again."""
    env = (ROOT / "upstream/opentelemetry-demo/.env").read_text()
    assert "COLLECTOR_CONTRIB_IMAGE=otel/opentelemetry-collector-contrib:0.108.0" in env


# ------------------------------------------------------------------------------------- 8. the 3.9 floor
REPEAT_TARGET_FILES = (
    "modules/otel-demo/execution/candidate_repeat.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/validation/candidate_terminal.py",
    "modules/otel-demo/materialize.py",
)


@pytest.mark.parametrize("relative", REPEAT_TARGET_FILES)
def test_changed_target_files_parse_as_python39_and_defer_annotations(relative):
    tree_ = ast.parse((ROOT / relative).read_text(), feature_version=(3, 9))
    assert any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__" and any(a.name == "annotations" for a in node.names)
        for node in tree_.body
    ), "a PEP 604 annotation would be evaluated eagerly on 3.9 (py_compile does not catch it)"


def _unbound_names(tree_: ast.Module):
    """Names loaded in a function that are bound nowhere (the Hotel #6 shape; tests/test_unbound_names.py's scan, applied
    here to every file this change touches)."""
    import builtins
    module_bound = set(dir(builtins))
    for node in ast.walk(tree_):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module_bound.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            module_bound.add(node.id)
        elif isinstance(node, ast.arg):
            module_bound.add(node.arg)
        elif isinstance(node, ast.Global):
            module_bound.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            module_bound.add(node.name)
    module_bound |= {"__file__", "__name__", "__doc__", "__spec__"}
    return sorted(
        (node.id, node.lineno) for node in ast.walk(tree_)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in module_bound
    )


@pytest.mark.parametrize("relative", REPEAT_TARGET_FILES)
def test_no_function_this_change_touches_reads_a_name_bound_nowhere(relative):
    assert _unbound_names(ast.parse((ROOT / relative).read_text())) == []


def test_the_unbound_name_scan_catches_a_planted_defect():
    planted = ast.parse("def f(events):\n    return [e for e in events if e == suffix]\n")
    assert _unbound_names(planted) == [("suffix", 2)]
    assert _unbound_names(ast.parse("def f(events):\n    suffix = 1\n    return [e for e in events if e == suffix]\n")) == []


def test_digests_and_the_event_functions_are_identical_under_python39_isolated(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    clock = {"barrierMonotonic": 5000.0, "barrierEpoch": 1_790_000_000.5, "mapping": "m", "stopPair": {"epoch": 0, "monotonic": 0}}
    raw = [json.dumps({"Action": "pause", "Actor": {"ID": "c", "Attributes": {"com.docker.compose.service": "frontend"}},
                       "timeNano": 1_790_000_061_250_000_000})]
    script = (
        "import importlib.util, json, sys\n"
        "def load(n, p):\n"
        "    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s)\n"
        "    sys.modules[n] = m; s.loader.exec_module(m); return m\n"
        f"r = load('r', {str(MODULE / 'execution/candidate_repeat.py')!r})\n"
        f"x = load('x', {str(MODULE / 'execution/candidate_remote.py')!r})\n"
        "d = r.load_descriptor()\n"
        f"events = x.parse_docker_events({raw!r}, {clock!r})\n"
        "print(json.dumps([r.canonical_sha256(d), r.canonical_sha256(r.compile_plan(d, 1)), r.MINIMUM_REMAINING_SECONDS,"
        " r.RUN_WINDOW_HOURS, events]))\n"
    )
    result = subprocess.run(
        [str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
        capture_output=True, text=True, check=True,
    )
    got = json.loads(result.stdout)
    assert got[:4] == [REPEAT_DESCRIPTOR_SHA256, REPEAT_PLAN_A1_SHA256, 13_416, 5]
    remote = load("otel_repeat_remote_for_events", MODULE / "execution/candidate_remote.py")
    assert got[4] == json.loads(json.dumps(remote.parse_docker_events(raw, clock)))
    assert got[4][0]["offsetSeconds"] == pytest.approx(1_790_000_061.25 - 1_790_000_000.5)
    document = repeat.load_descriptor()
    assert [repeat.canonical_sha256(document), repeat.canonical_sha256(repeat.compile_plan(document, 1))] == got[:2]


# ------------------------- 9. B attempt 1 is spent (2026-10-10, before campaign C): it ran on fb14srv6 on 2026-10-09
# (harness c4aa313, plan 3aaf5923), fetch receipt terminal-valid, 36 cells, host and local sha256 lists identical (619/619).
RAN_REPEAT_ATTEMPTS = {1: "3aaf5923"}         # attempt -> the plan prefix that ran on fb14srv6


def _spent_table_in_source() -> dict:
    """SPENT_ATTEMPTS_BY_EPOCH read from the adapter's source text, so it does not depend on which epoch a selector names."""
    tree_ = ast.parse((MODULE / "execution/candidate_runtime_adapter.py").read_text())
    for node in tree_.body:
        if isinstance(node, ast.Assign) and any(getattr(t_, "id", None) == "SPENT_ATTEMPTS_BY_EPOCH" for t_ in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SPENT_ATTEMPTS_BY_EPOCH not found")


def _unrecorded_repeat_attempts(table: dict) -> list:
    spent = table.get(REPEAT, {})
    return sorted(a for a, prefix in RAN_REPEAT_ATTEMPTS.items() if a not in spent or prefix not in spent[a])


def test_every_repeat_attempt_that_ran_is_recorded_as_spent_with_its_plan():
    table = _spent_table_in_source()
    assert _unrecorded_repeat_attempts(table) == []
    assert set(table[REPEAT]) == {1} and "c4aa313" in table[REPEAT][1]
    assert repeat.canonical_sha256(repeat.compile_plan(repeat.load_descriptor(), 1)).startswith(RAN_REPEAT_ATTEMPTS[1])


def test_planted_defect_a_repeat_attempt_that_ran_but_is_not_recorded_is_found():
    table = _spent_table_in_source()
    assert _unrecorded_repeat_attempts({**table, REPEAT: {}}) == [1]
    assert _unrecorded_repeat_attempts({**table, REPEAT: {1: "campaign B attempt 1, plan 00000000"}}) == [1]
    assert _unrecorded_repeat_attempts({}) == [1]
