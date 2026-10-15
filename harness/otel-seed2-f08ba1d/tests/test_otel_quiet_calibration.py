"""otel-quiet-calibration-v1: the OTel quiet calibration run (main repo research/PROTOCOL_DRAFT_20261002.md decision 48).

Covers: the plan is exactly 40 no-fault cells, 10 per rate, 10 blocks each holding every rate once, in a seeded
Fisher-Yates order (seed 20261004) recorded in the descriptor and the plan; every cell is the sweep's no-fault cell
apart from its pseudo-window onset (the sweep's stratified rule with 10 strata) and the plan-level budget; the sweep
epoch is unchanged (its files at c532853, its descriptor and both attempt plans); the budget and the GATE-RUN window
are derived from the plan; the committed selector activates the quiet epoch in every reader; the GATE chain derives
40 cells and the 6 h window; a fake-driven execution of the target's per-cell runner at the highest and lowest rate,
which the terminal accepts; host paths disjoint from the sweep's; the 3.9 floor and 3.9/3.13 digest identity.

2026-10-04, protocol decision 56 (main repo research/PROTOCOL_DRAFT_20261002.md round 12, after attempt 1 stopped on
r10-b02-04): this epoch's cells record incomplete traces as telemetry loss and never block on them (section 6); the
sweep keeps decision 25, byte for byte; attempt 1 is spent and relaunch 1 is attempt 2.

Like the sweep's tests, the epoch is exercised in a copy of the module tree with its own selector, so these tests
pass whichever epoch the worktree's committed selector names.
"""
from __future__ import annotations

import ast
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
QUIET = "otel-quiet-calibration-v1"
SWEEP = "otel-traffic-sweep-v1"
SWEEP_COMMIT = "c532853"            # the harness of the sweep's relaunch 1 (terminal-valid 12/12, 2026-10-03)
RATES = (10.0, 1.0, 0.2, 0.05)

# Decision 56 re-pinned the descriptor (amendments, analysis.traceCompleteness, the timing key) and so every plan.
QUIET_DESCRIPTOR_SHA256 = "36a7fd173a9995e6b0c0e9897d98ff76995ca375e045b90804fe92221dfd2286"
QUIET_PLAN_A1_SHA256 = "f2e7158fd2e007b705ad598459aad6a97940f42c9f8f86134b97d844ea4d9fc6"   # attempt 1's IDs: spent
QUIET_PLAN_A2_SHA256 = "bb1eb1fc6bb4047b83c69d4d216d70b18f49dd7689c1245e4d0b7d0e18ffe8d6"   # relaunch 1 (ran 40/40, 2026-10-05)
QUIET_PLAN_A3_SHA256 = "d82dcb2f0fed57ae450ed80cd1d708776fe9affced678fea1ab6fc70e91dfbcb"   # run A2 (protocol decision 68)
# What attempt 1 ran (fb14srv6, 2026-10-04, harness 6e37ec2), under the declaration-freeze descriptor.
QUIET_DESCRIPTOR_FROZEN_SHA256 = "02c2d90e39e448f77025de55a0377cb2a65aafc4d2a42c5177a5ec7ce3e6777d"
QUIET_PLAN_A1_RAN_SHA256 = "5cec5a6966fb7f5998b34ca3ab2c6ac5223ec8ecb52a6425697f9a3f8cd87b58"
QUIET_COMMIT = "6e37ec2"            # the harness of attempt 1 (decision 25 in quiet cells)
TRACE_RULE = "protocol-decision-56"
SWEEP_DESCRIPTOR_SHA256 = "be5b0b4dcd212aaa47908a6dd533e5cb73a104ab22b1b9e04a147e21ccb2c86d"
SWEEP_PLAN_A1_SHA256 = "09b2563a7f15a0d50da49418b7aa9be203c4e1ecbfe95faf9edebf9729924865"
SWEEP_PLAN_A2_SHA256 = "fa770ccf62f3eca24081d0c9ca004c05104250da69ee3422bcf8a172b5349498"
QUIET_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor",
}
# The sweep's controller set at c532853 (candidate_runtime.EPOCH_CONTROLLER_PATHS / candidate_setup), unchanged.
SWEEP_EPOCH_CONTROLLER_PATHS = {
    "candidate-compiler": "modules/otel-demo/execution/candidate_sweep.py",
    "candidate-descriptor": "pipelines/campaigns/otel-traffic-sweep-v1.json",
    "frozen-compiler": "modules/otel-demo/execution/candidate_pilot.py",
    "frozen-descriptor": "pipelines/campaigns/otel-demo-offpath-v1.json",
    "protocol-gates": "modules/otel-demo/validation/protocol_gates.py",
    "study-epoch-selector": "modules/otel-demo/execution/study-epoch.json",
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


quiet = load("otel_quiet_compiler_test", MODULE / "execution/candidate_quiet.py")
sweep = load("otel_quiet_sweep_compiler_test", MODULE / "execution/candidate_sweep.py")
# The sweep's test module supplies the tree copy, the gate-document builder and the fake target (read, not edited).
helpers = load("otel_quiet_sweep_test_helpers", ROOT / "tests/test_otel_traffic_sweep.py")
NOW = helpers.NOW


def _git_show(relative: str, commit: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"], capture_output=True, check=True,
    ).stdout


@pytest.fixture(scope="module")
def quiet_tree(tmp_path_factory):
    """A copy of the module tree whose selector names the quiet epoch: modules loaded from it run that epoch."""
    root = helpers._copy_tree(
        tmp_path_factory.mktemp("quiet-tree"),
        selector=json.dumps({"schemaVersion": 1, "studyEpoch": QUIET}) + "\n",
    )
    module = root / "modules/otel-demo"
    loaded = types.SimpleNamespace(root=root)
    loaded.runtime = load("otel_quiet_tree_runtime", module / "execution/candidate_runtime.py")
    loaded.remote = load("otel_quiet_tree_remote", module / "execution/candidate_remote.py")
    loaded.setup = load("otel_quiet_tree_setup", module / "execution/candidate_setup.py")
    loaded.compiler = load("otel_quiet_tree_compiler", module / "execution/candidate_quiet.py")
    loaded.terminal = load("otel_quiet_tree_terminal", module / "validation/candidate_terminal.py")
    return loaded


@pytest.fixture(autouse=True)
def _terminal_handles(request):
    """The terminal resolves its runtime and remote through these module names: bind them to the quiet tree."""
    if "quiet_tree" in request.fixturenames:
        loaded = request.getfixturevalue("quiet_tree")
        names = ("otel_candidate_terminal_runtime", "otel_candidate_terminal_remote")
        saved = {name: sys.modules.get(name) for name in names}
        sys.modules["otel_candidate_terminal_runtime"] = loaded.runtime
        sys.modules["otel_candidate_terminal_remote"] = loaded.remote
        yield
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    else:
        yield


# ------------------------------------------------------------------------------------------ 1. the quiet plan
def test_the_plan_is_exactly_40_no_fault_cells_10_per_rate_in_10_blocks():
    document = quiet.load_descriptor()
    plan = quiet.compile_plan(document, 1)
    cells = quiet.flatten_cells(plan)
    assert quiet.canonical_sha256(document) == QUIET_DESCRIPTOR_SHA256
    assert quiet.canonical_sha256(plan) == QUIET_PLAN_A1_SHA256
    assert len(cells) == plan["runCount"] == plan["uniqueRunCount"] == quiet.TOTAL_RUNS == 40
    assert len({cell["runId"] for cell in cells}) == 40
    # No fault anywhere: regime, contract fault, compiled timing.
    assert {cell["runKey"]["regime"] for cell in cells} == {"no-fault-calibration"}
    assert all(cell["fault"] is None and cell["timing"]["faultApplied"] is False for cell in cells)
    assert all(cell["timing"]["scheduledSlotsByPhase"] is None for cell in cells)
    assert {cell["timing"]["traceCompletenessRule"] for cell in cells} == {TRACE_RULE}
    assert all(cell["artifactRoot"].startswith("runs/calibration/") for cell in cells)
    # 10 per rate, and every block holds every rate exactly once.
    per_rate = {rate: [cell for cell in cells if cell["runKey"]["requestsPerSecond"] == rate] for rate in RATES}
    assert {rate: len(rows) for rate, rows in per_rate.items()} == {rate: 10 for rate in RATES}
    assert [block["block"] for block in plan["blocks"]] == list(range(1, 11))
    for block in plan["blocks"]:
        assert sorted(cell["runKey"]["requestsPerSecond"] for cell in block["cells"]) == sorted(RATES)
        assert {cell["runKey"]["block"] for cell in block["cells"]} == {block["block"]}
        assert [cell["ordinalPosition"] for cell in block["cells"]] == [1, 2, 3, 4]
    assert {cell["runKey"]["posture"] for cell in cells} == {"full"}
    assert {cell["runKey"]["studyEpoch"] for cell in cells} == {QUIET}
    # Deterministic: a second compile is byte-identical.
    assert quiet.canonical_json_bytes(quiet.compile_plan(document, 1)) == quiet.canonical_json_bytes(plan)


def test_the_order_is_a_seeded_fisher_yates_per_block_recorded_in_descriptor_and_plan():
    document = quiet.load_descriptor()
    plan = quiet.compile_plan(document, 1)
    assert document["schedule"]["seed"] == plan["schedule"]["seed"] == 20261004
    assert document["schedule"]["leadCell"] is None
    assert plan["schedule"]["blockOrders"] == document["schedule"]["blocks"]
    for receipt, block in zip(document["schedule"]["blocks"], plan["blocks"]):
        expected = quiet.fisher_yates(
            [{"regime": "no-fault-calibration", "rate": rate} for rate in RATES],
            20261004, QUIET, receipt["block"], "quiet-schedule-v1",
        )
        assert receipt["order"] == ["no-fault-calibration@r%s" % quiet.rate_token(row["rate"]) for row in expected]
        assert receipt["orderSha256"] == quiet.canonical_sha256(receipt["order"])
        assert [cell["runKey"]["requestsPerSecond"] for cell in block["cells"]] == [row["rate"] for row in expected]
        assert block["order"] == [cell["runId"] for cell in block["cells"]]
    # The shuffle is the sweep's rule: with the sweep's seed, epoch and pairs it reproduces the sweep's block 1
    # before the sweep moves its lead cell first.
    pairs = [{"regime": regime, "rate": float(rate)} for regime in sweep.REGIMES for rate in sweep.RATES]
    shuffled = quiet.fisher_yates(pairs, sweep.SCHEDULE_SEED, sweep.EPOCH, 1, sweep.SCHEDULE_CONTEXT)
    lead = [row for row in shuffled if (row["regime"], row["rate"]) == (sweep.LEAD_CELL[0], float(sweep.LEAD_CELL[1]))]
    assert lead + [row for row in shuffled if row not in lead] == sweep.block_order(1)
    # Not every block has the same order (the draws are keyed by block).
    assert len({tuple(receipt["order"]) for receipt in document["schedule"]["blocks"]}) > 1


def test_the_pseudo_window_follows_the_sweeps_onset_rule_with_ten_strata():
    # The rule is the sweep's: given the sweep's seed, epoch and one stratum it reproduces every sweep offset.
    for regime in sweep.REGIMES:
        for rate in sweep.RATES:
            assert quiet.stratified_onset_offset(
                sweep.SCHEDULE_SEED, sweep.EPOCH, sweep.EPISODES, regime, rate, 1,
            ) == sweep.onset_phase_offset(regime, rate, 1)
    cells = quiet.flatten_cells(quiet.compile_plan(quiet.load_descriptor(), 1))
    for rate in RATES:
        rows = [cell["timing"] for cell in cells if cell["runKey"]["requestsPerSecond"] == rate]
        inter_arrival = 1.0 / rate
        strata = sorted(int(row["faultOnsetPhaseOffsetSeconds"] / inter_arrival * 10) for row in rows)
        assert strata == list(range(10)), (rate, strata)          # one onset in every tenth of an inter-arrival
        for row in rows:
            assert row["faultOnsetSeconds"] == round(60 + row["faultOnsetPhaseOffsetSeconds"], 6)
            assert row["scoredWindowSeconds"] == [row["faultOnsetSeconds"], round(row["faultOnsetSeconds"] + 60, 6)]
            assert 0 <= row["faultOnsetPhaseOffsetSeconds"] < inter_arrival
    # Keyed by (regime, rate, block), never by attempt: attempt 2 keeps every timing and changes every run ID.
    first = quiet.flatten_cells(quiet.compile_plan(quiet.load_descriptor(), 1))
    second = quiet.flatten_cells(quiet.compile_plan(quiet.load_descriptor(), 2))
    assert [cell["timing"] for cell in first] == [cell["timing"] for cell in second]
    assert not {cell["runId"] for cell in first} & {cell["runId"] for cell in second}


def test_every_cell_is_the_sweeps_no_fault_cell_apart_from_its_onset_and_the_plan_budget():
    cells = quiet.flatten_cells(quiet.compile_plan(quiet.load_descriptor(), 1))
    for cell in cells:
        rate = cell["runKey"]["requestsPerSecond"]
        mine, theirs = cell["timing"], sweep.cell_timing("no-fault-calibration", rate, 1)
        assert set(mine) == set(theirs) | {"traceCompletenessRule"}       # the one key the sweep has not (decision 56)
        assert {key for key in mine if mine.get(key) != theirs.get(key)} <= quiet.OWN_TIMING_KEYS
        assert mine["planRunCount"] == 40 and mine["planMinimumRemainingSeconds"] == 14_740
    # The shape the declaration names, read from the compiled timing (not from this test's literals alone).
    timing = cells[0]["timing"]
    assert timing["route"] == {"method": "GET", "path": "/api/products/66VCHSJNUP",
                               "services": ["frontendproxy", "frontend", "productcatalogservice"]}
    assert timing["requestTimeoutSeconds"] == 15.0 and timing["concurrency"] == 300
    assert (timing["warmupSeconds"], timing["warmupRequestsPerSecond"], timing["measurementSeconds"]) == (30, 10.0, 180)
    assert timing["faultHoldSeconds"] == 60 and timing["upstreamGeneratorsOff"] == ["loadgenerator"]
    assert timing["serviceMemoryLimitBytes"] == {"frontendproxy": 256 * 1024 * 1024}
    assert timing["containerHealthGuard"] is True and timing["protocolGates"] is True
    assert (timing["traceDrainSeconds"], timing["traceIncompleteAllowanceShare"],
            timing["traceIncompleteAllowanceMinimum"]) == (17.0, 0.01, 1)
    assert {cell["timing"]["offered"] for cell in cells} == {1800, 180, 36, 9}


def test_a_planted_descriptor_or_plan_edit_is_refused():
    document = quiet.load_descriptor()
    plan = quiet.compile_plan(document, 1)
    planted = copy.deepcopy(document)
    planted["schedule"]["seed"] = 20261003
    with pytest.raises(quiet.ProtocolError, match="differs from its generator"):
        quiet.validate_descriptor(planted)
    for mutate, message in (
        (lambda p: p["blocks"][3]["cells"][0]["timing"].update(faultOnsetSeconds=61.0), "differs from the frozen schedule"),
        (lambda p: p["blocks"][0]["cells"].pop(), "differs from the frozen schedule"),
        (lambda p: p["blocks"][2]["cells"][1].update(fault="frontend-pause"), "differs from the frozen schedule"),
        (lambda p: p["schedule"].update(seed=1), "differs from the frozen schedule"),
    ):
        broken = copy.deepcopy(plan)
        mutate(broken)
        with pytest.raises(quiet.ProtocolError, match=message):
            quiet.validate_plan(document, broken)
    with pytest.raises(quiet.ProtocolError, match="no-fault cells only"):
        quiet.cell_timing("frontend-pause-effect", 10.0, 1)


# ---------------------------------------------------------------------------- 2. the sweep epoch is unchanged
@pytest.mark.parametrize("relative", (
    "modules/otel-demo/execution/candidate_sweep.py",
    "pipelines/campaigns/otel-traffic-sweep-v1.json",
    "modules/otel-demo/execution/candidate_pilot.py",
    "pipelines/campaigns/otel-demo-offpath-v1.json",
    "modules/otel-demo/validation/protocol_gates.py",
    "modules/otel-demo/drivers/gate_driver_config.py",
))
# candidate_terminal.py is not in this list since 2026-10-09: campaign B's H10/H4 artifacts (docker-events.json, the
# freeze stamps, a receipt with no during-fault probe) need a terminal that validates them.  Its behaviour on the sweep's
# and the quiet epoch's artifacts is pinned instead, against the terminal at the quiet relaunch commit, by
# tests/test_otel_repeat_episodes.py (test_the_terminal_judges_sweep_and_quiet_cells_as_it_did_at_6a47d0b).
def test_the_sweeps_files_are_byte_identical_to_its_relaunch_commit(relative):
    assert (ROOT / relative).read_bytes() == _git_show(relative, SWEEP_COMMIT)


def test_the_sweeps_descriptor_and_both_attempt_plans_keep_their_digests(tmp_path):
    document = sweep.load_descriptor()
    assert sweep.canonical_sha256(document) == SWEEP_DESCRIPTOR_SHA256
    assert sweep.canonical_sha256(sweep.compile_plan(document, 1)) == SWEEP_PLAN_A1_SHA256
    assert sweep.canonical_sha256(sweep.compile_plan(document, 2)) == SWEEP_PLAN_A2_SHA256
    # The quiet descriptor binds exactly these sweep bytes.
    derived = quiet.load_descriptor()["derivedFrom"]
    assert derived["studyEpoch"] == SWEEP and derived["descriptorCanonicalSha256"] == SWEEP_DESCRIPTOR_SHA256
    assert derived["descriptorByteSha256"] == hashlib.sha256(
        (ROOT / "pipelines/campaigns/otel-traffic-sweep-v1.json").read_bytes()).hexdigest()
    # Under a sweep selector the harness still binds the sweep's controller set and its single spent attempt.
    tree = helpers._copy_tree(tmp_path, selector=json.dumps({"schemaVersion": 1, "studyEpoch": SWEEP}) + "\n")
    runtime = load("otel_quiet_sweep_tree_runtime", tree / "modules/otel-demo/execution/candidate_runtime.py")
    setup = load("otel_quiet_sweep_tree_setup", tree / "modules/otel-demo/execution/candidate_setup.py")
    assert runtime.EPOCH_CONTROLLER_PATHS[SWEEP] == setup.EPOCH_CONTROLLER_PATHS[SWEEP] == SWEEP_EPOCH_CONTROLLER_PATHS
    assert (runtime.STUDY_EPOCH, runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (
        SWEEP, 12, 5472, 3)
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_quiet_sweep_tree_adapter", tree / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.STUDY_EPOCH == SWEEP and set(adapter.SPENT_ATTEMPTS) == {1}
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


# --------------------------------------------------------------------- 3. budget, selector and the gate chain
def test_budget_and_run_window_are_derived_from_the_plan():
    assert quiet.CELL_PERIOD_ESTIMATE_SECONDS == sweep.CELL_PERIOD_ESTIMATE_SECONDS == 331
    assert quiet.MINIMUM_REMAINING_SECONDS == 40 * 331 + 900 + 600 == 14_740
    assert quiet.RUN_WINDOW_HOURS == 6 == -(-(14_740 + 3600) // 3600)
    # The estimate is above every period relaunch 1 measured, so the window is sized from an upper value.
    measured = quiet.MEASURED_CELL_PERIOD_SECONDS
    assert measured["maximum"] < quiet.CELL_PERIOD_ESTIMATE_SECONDS
    budget = quiet.load_descriptor()["timing"]["budget"]
    assert (budget["minimumRemainingSeconds"], budget["runWindowHours"]) == (14_740, 6)
    assert quiet.QUIET_SECONDS_PER_RATE == 1800         # 30 min of quiet time per rate: 3 / 0.5 h = 6/h at 0 alarms


def test_the_selector_activates_the_quiet_epoch_in_every_reader(quiet_tree):
    runtime = quiet_tree.runtime
    assert runtime.STUDY_EPOCH == QUIET and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (40, 14_740, 6)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | QUIET_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_quiet.py"
    assert runtime.DESCRIPTOR == quiet_tree.root / "pipelines/campaigns/otel-quiet-calibration-v1.json"
    assert quiet_tree.setup.controller_paths(QUIET) == runtime.CONTROLLER_PATHS
    assert quiet_tree.setup.EPOCH_CONTROLLER_PATHS[QUIET] == runtime.EPOCH_CONTROLLER_PATHS[QUIET]
    digests = runtime.controller_digests()
    assert digests["sweep-compiler"] == hashlib.sha256((MODULE / "execution/candidate_sweep.py").read_bytes()).hexdigest()
    assert digests["sweep-descriptor"] == hashlib.sha256(
        (ROOT / "pipelines/campaigns/otel-traffic-sweep-v1.json").read_bytes()).hexdigest()
    assert runtime.frozen_descriptor()["id"] == QUIET
    assert runtime.unsupported_evidence()["studyEpoch"] == "otel-demo-candidate-pilot-v1"


def test_driver_config_and_adapter_follow_the_quiet_selector(quiet_tree, tmp_path):
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    copied = load("otel_quiet_driver_config_tree", quiet_tree.root / "modules/otel-demo/drivers/gate_driver_config.py")
    assert (copied.CONFIG.study, copied.CONFIG.campaign_id, copied.CONFIG.run_window_hours) == (QUIET, QUIET, 6)
    assert copied.CONFIG.root == quiet_tree.root
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_quiet_tree_adapter", quiet_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == QUIET
        # Attempt 1 ran on fb14srv6 (stopped at cell 8) and attempt 2 (relaunch 1) ran 40/40: both spent, so the driver path
        # refuses them and takes attempt 3 (run A2, protocol decision 68).
        assert adapter.pilot.EPOCH == QUIET and set(adapter.SPENT_ATTEMPTS) == {1, 2}
        assert "5cec5a69" in adapter.SPENT_ATTEMPTS[1] and "STOP_QUIET_OTEL_A1.md" in adapter.SPENT_ATTEMPTS[1]
        assert "bb1eb1fc" in adapter.SPENT_ATTEMPTS[2] and "40/40" in adapter.SPENT_ATTEMPTS[2]
        with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
            adapter.inspect_campaign(tmp_path / "plan-a1", "a" * 40)
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "2")
            with pytest.raises(adapter.runtime.GateError, match="attempt 2 is spent"):
                adapter.inspect_campaign(tmp_path / "plan-a2", "a" * 40)
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "3")
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 40 and bindings.plan_sha256 == QUIET_PLAN_A3_SHA256
        assert bindings.descriptor_sha256 == QUIET_DESCRIPTOR_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


@pytest.fixture(scope="module")
def quiet_package(quiet_tree, tmp_path_factory):
    return helpers._package(quiet_tree.runtime, quiet_tree.compiler, tmp_path_factory.mktemp("quiet-package"), window_hours=6)


def test_gate_chain_derives_40_cells_the_budget_and_disjoint_host_paths(quiet_tree, quiet_package, tmp_path):
    runtime, remote = quiet_tree.runtime, quiet_tree.remote
    plan_text = quiet_package.gate_plan["typedApproval"]
    assert f"study={QUIET} " in plan_text and " runs=40 " in plan_text and f"campaign={QUIET} " in plan_text
    assert " runs=40 " in quiet_package.gate_run["typedApproval"]
    assert quiet_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 14_740
    binding = quiet_package.gate_plan["binding"]
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_quiet_calibration_v1"
    assert remote.SAFE_NAME.fullmatch(binding["compose"]["project"]) and len(QUIET) <= 40
    # Host paths follow the campaign id: none is, or lies under, one of the sweep's.
    sweep_paths = (
        "/home/stig/observability-placement-candidate-v4-runs/" + SWEEP,
        "/home/stig/observability-placement-candidate-v4-runs/.setup-" + SWEEP,
        "/home/stig/observability-placement-candidate-v4-otel-srv6/" + SWEEP + "-",
    )
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert QUIET in binding[key] and not any(binding[key].startswith(path) for path in sweep_paths), key
    assert binding["remoteArtifactRoot"] == "/home/stig/observability-placement-candidate-v4-runs/" + QUIET
    assert set(binding["controllerDigests"]) == helpers.FROZEN_CONTROLLER_KEYS | QUIET_CONTROLLER_KEYS
    document = runtime.execution_package(quiet_package)
    assert document["runCount"] == 40 and len(document["cells"]) == 40
    for contract, cell in zip(document["cells"], quiet_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and contract["runId"] == cell["runId"]
        assert contract["fault"]["scenario"] is None and contract["window"]["kind"] == "calibration"
        assert "intervention.json" not in contract["requiredArtifacts"]
        assert contract["workloadPathCheck"]["gatesCampaign"] is False
        assert runtime.sweep_cell_timing(contract) == cell["timing"]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (QUIET,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
        remote.refuse_unsupported("probe", QUIET)
    assert len(cells) == 40 and remote.expected_run_count(document) == 40
    assert remote.expected_minimum_remaining(document) == 14_740
    assert remote.require_path_check_before_faults(cells) == -1
    # The sweep's 3 h window (and anything short of 14,740 s) is refused for 40 cells.
    with pytest.raises(runtime.GateError, match="too little time for 40 cells"):
        helpers._package(runtime, quiet_tree.compiler, tmp_path / "short", window_hours=4)
    planted = copy.deepcopy(document)
    planted["cells"][7]["timing"]["planRunCount"] = 12
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (QUIET,))
        with pytest.raises(remote.RuntimeFailure, match="disagree on planRunCount"):
            remote.validate_package(planted, clock=lambda: NOW)


# ----------------------------------------------- 4. a fake-driven execution of the target's per-cell runner
def _quiet_contract(quiet_tree, quiet_package, rate: float, block: int, tmp_path: Path) -> dict:
    document = quiet_tree.runtime.execution_package(quiet_package)
    contract = copy.deepcopy(next(
        c for c in document["cells"] if (c["runKey"]["requestsPerSecond"], c["runKey"]["block"]) == (rate, block)
    ))
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    (source / "candidate-posture-contract.json").write_bytes((MODULE / "postures/catalog.json").read_bytes())
    release = tmp_path / "release"
    gates = release / "repository/modules/otel-demo/validation/protocol_gates.py"
    gates.parent.mkdir(parents=True, exist_ok=True)
    gates.write_bytes((MODULE / "validation/protocol_gates.py").read_bytes())
    contract["remoteSourceRoot"] = str(source)
    contract["releaseRoot"] = str(release)
    contract["remoteArtifactRoot"] = str(tmp_path / "artifacts" / contract["compiledArtifactRoot"])
    return contract


def _run_quiet(quiet_tree, contract, monkeypatch, **fake_options):
    """The target's per-cell runner against the sweep tests' fake fb14srv6 (``fake_options`` plant defects)."""
    remote = quiet_tree.remote
    clock = helpers.FakeTime(helpers.real_time.time())
    target = helpers.FakeTarget(contract, clock, **fake_options)
    target.contract["_firstToken"] = remote.request_identity(contract["runId"], 0)[0]
    monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (QUIET,))    # the activation edit
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
    return remote.run_cell(contract, datetime.now(timezone.utc) + timedelta(hours=6)), target


@pytest.mark.parametrize("rate,block", ((10.0, 7), (0.05, 3)))
def test_run_cell_executes_a_quiet_cell_from_its_timing_and_the_terminal_accepts_it(
    quiet_tree, quiet_package, tmp_path, monkeypatch, rate, block,
):
    contract = _quiet_contract(quiet_tree, quiet_package, rate, block, tmp_path)
    receipt, target = _run_quiet(quiet_tree, contract, monkeypatch)
    root = Path(contract["remoteArtifactRoot"])
    assert receipt["state"] == "valid", receipt["error"]
    assert not (root / "intervention.json").exists()
    assert not any(argv[-2:] in (["pause", "frontend"], ["unpause", "frontend"]) for argv in target.commands)
    assert not any(argv[:2] == ["docker", "update"] and "--cpus" in argv for argv in target.commands)
    ledger = json.loads((root / "request-ledger.json").read_text())
    assert ledger["offered"] == contract["timing"]["offered"] == len(ledger["requests"]) and ledger["ratePerSecond"] == rate
    gates = json.loads((root / "protocol-gates.json").read_text())
    assert gates["valid"] is True and gates["blocking"] == ["G1", "G2", "G4"]
    health = json.loads((root / "container-health.json").read_text())
    assert health["valid"] is True and health["memoryLimitUpdates"][0]["argv"][:4] == [
        "docker", "update", "--memory", str(256 * 1024 * 1024)]
    report = quiet_tree.terminal.validate_cell(root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    completeness = report["correlation"]["traceCompleteness"]
    assert completeness["incomplete"] == 0 and completeness["blockingWindows"] == [] and completeness["allowance"] is None
    record = json.loads((root / "trace-completeness.json").read_text())
    assert (record["rule"], record["blocking"], record["valid"]) == (TRACE_RULE, False, True)
    assert record["windows"]["whole-measurement"]["incompleteRuns"] == []


# -------------------------------------------------------------------------------- 5. the 3.9 floor and digests
def test_the_quiet_compiler_parses_as_python39_and_defers_annotations():
    tree_ = ast.parse((MODULE / "execution/candidate_quiet.py").read_text(), feature_version=(3, 9))
    assert any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__" and any(a.name == "annotations" for a in node.names)
        for node in tree_.body
    )


def test_quiet_and_sweep_digests_are_identical_under_python39_isolated_and_this_interpreter(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import importlib.util, json, sys\n"
        "def load(n, p):\n"
        "    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s)\n"
        "    sys.modules[n] = m; s.loader.exec_module(m); return m\n"
        f"q = load('q', {str(MODULE / 'execution/candidate_quiet.py')!r})\n"
        f"s = load('s', {str(MODULE / 'execution/candidate_sweep.py')!r})\n"
        "d = q.load_descriptor(); sd = s.load_descriptor()\n"
        "print(json.dumps([q.canonical_sha256(d), q.canonical_sha256(q.compile_plan(d, 1)),"
        " q.canonical_sha256(q.compile_plan(d, 2)), q.canonical_sha256(q.compile_plan(d, 3)),"
        " q.MINIMUM_REMAINING_SECONDS,"
        " q.RUN_WINDOW_HOURS, s.canonical_sha256(sd), s.canonical_sha256(s.compile_plan(sd, 1)),"
        " s.canonical_sha256(s.compile_plan(sd, 2))]))\n"
    )
    result = subprocess.run(
        [str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
        capture_output=True, text=True, check=True,
    )
    expected = [QUIET_DESCRIPTOR_SHA256, QUIET_PLAN_A1_SHA256, QUIET_PLAN_A2_SHA256, QUIET_PLAN_A3_SHA256, 14_740, 6,
                SWEEP_DESCRIPTOR_SHA256, SWEEP_PLAN_A1_SHA256, SWEEP_PLAN_A2_SHA256]
    assert json.loads(result.stdout) == expected
    document = quiet.load_descriptor()
    assert [quiet.canonical_sha256(document), quiet.canonical_sha256(quiet.compile_plan(document, 1)),
            quiet.canonical_sha256(quiet.compile_plan(document, 2)),
            quiet.canonical_sha256(quiet.compile_plan(document, 3)),
            quiet.MINIMUM_REMAINING_SECONDS, quiet.RUN_WINDOW_HOURS] == expected[:6]


def test_the_descriptor_file_is_the_generators_output():
    assert (ROOT / "pipelines/campaigns/otel-quiet-calibration-v1.json").read_bytes() == quiet._pretty_bytes(
        quiet.derive_quiet_descriptor())


# ------------------------- 6. protocol decision 56 (user 2026-10-04): trace loss recorded, never blocking, quiet only
# Attempt 1, cell r10-b02-04 (main repo research/traffic-sweep/STOP_QUIET_OTEL_A1.md): 50 consecutive successful requests
# scheduled 134.9-139.8 s at 10/s, each with frontendproxy and frontend spans and no productcatalogservice span.
ATTEMPT1_LOST = range(1349, 1399)


def _tokens(quiet_tree, contract, sequences):
    return {quiet_tree.remote.request_identity(contract["runId"], sequence)[0] for sequence in sequences}


def _record(contract):
    return json.loads((Path(contract["remoteArtifactRoot"]) / "trace-completeness.json").read_text())


@pytest.fixture(scope="module")
def lost_batch_cell(quiet_tree, quiet_package, tmp_path_factory):
    """Attempt 1's failing pattern replayed on the quiet cell it hit (r10, block 2, position 4), sealed once."""
    base = tmp_path_factory.mktemp("lost-batch")
    contract = _quiet_contract(quiet_tree, quiet_package, 10.0, 2, base)
    assert contract["compiledArtifactRoot"].endswith("r10-b02-04-full")
    with pytest.MonkeyPatch.context() as patch:
        receipt, _ = _run_quiet(quiet_tree, contract, patch, lose_spans=_tokens(quiet_tree, contract, ATTEMPT1_LOST))
    return receipt, contract


def test_attempt1s_lost_batch_now_seals_valid_with_the_loss_recorded(quiet_tree, lost_batch_cell):
    """Fails at 6e37ec2, where the cell sealed invalid: "trace completeness: 50 incomplete of 1800 successful requests
    outside the fault-and-drain window exceeds the allowance 18" (decision 25, rule ii)."""
    receipt, contract = lost_batch_cell
    assert receipt["state"] == "valid", receipt["error"]
    record = _record(contract)
    assert (record["schemaVersion"], record["kind"], record["rule"], record["blocking"], record["valid"]) == (
        3, "otel-demo-quiet-trace-completeness-v3", TRACE_RULE, False, True)
    assert record["requiredPathServices"] == ["frontend", "frontendproxy", "productcatalogservice"]
    assert list(record["windows"]) == ["whole-measurement"] and record["blockingWindows"] == []
    window = record["windows"]["whole-measurement"]
    assert (window["requests"], window["successful"], window["complete"], window["incomplete"]) == (1800, 1800, 1750, 50)
    assert (window["unsuccessful"], window["unsuccessfulIncomplete"]) == (0, 0)
    assert set(window["incompleteRequestTokens"]) == _tokens(quiet_tree, contract, ATTEMPT1_LOST)
    # Which required path service each incomplete request lacked, and the count per service.
    assert window["incompleteByMissingService"] == {"frontend": 0, "frontendproxy": 0, "productcatalogservice": 50}
    assert [row["requestToken"] for row in window["incompleteRequests"]] == window["incompleteRequestTokens"]
    assert {(row["ownTraceObserved"], tuple(row["missingServices"]), tuple(row["unexpectedServices"]))
            for row in window["incompleteRequests"]} == {(True, ("productcatalogservice",), ())}
    assert [row["scheduledOffsetSeconds"] for row in window["incompleteRequests"]] == [
        sequence / 10.0 for sequence in ATTEMPT1_LOST]
    # The lost batch is one contiguous run: 5 s at 10/s.
    assert window["incompleteRuns"] == [{
        "firstScheduledOffsetSeconds": 134.9, "lastScheduledOffsetSeconds": 139.8, "requests": 50,
        "missingServices": ["productcatalogservice"],
    }]
    assert (record["successful"], record["incomplete"], record["allowance"]) == (1800, 50, None)
    assert record["decision25Counterfactual"] == {"allowance": 18, "wouldHaveBlocked": True, "applied": False}
    # Every other gate ran and passed; the terminal replays the record byte for byte and accepts the cell.
    root = Path(contract["remoteArtifactRoot"])
    assert json.loads((root / "protocol-gates.json").read_text())["valid"] is True
    assert json.loads((root / "container-health.json").read_text())["valid"] is True
    report = quiet_tree.terminal.validate_cell(root, contract)
    assert report["state"] == "valid"
    summary = report["correlation"]["traceCompleteness"]
    assert (summary["incomplete"], summary["blockingWindows"], summary["allowance"]) == (50, [], None)
    assert summary["windows"]["whole-measurement"]["incompleteRuns"] == window["incompleteRuns"]


def test_other_gates_still_block_a_quiet_cell(quiet_tree, quiet_package, tmp_path, monkeypatch):
    """Decision 56 relaxes trace completeness only: G2 (a pre-onset failure at 0.05/s) and the container-health guard
    (an OOM kill) still invalidate a quiet cell, with the loss recorded either way."""
    for name in ("g2", "oom"):
        (tmp_path / name).mkdir()
    contract = _quiet_contract(quiet_tree, quiet_package, 0.05, 3, tmp_path / "g2")
    receipt, _ = _run_quiet(quiet_tree, contract, monkeypatch, fail_first_request=True)
    assert receipt["state"] == "invalid" and "protocol gate(s) G2" in receipt["error"]
    assert _record(contract)["valid"] is True
    contract = _quiet_contract(quiet_tree, quiet_package, 1.0, 4, tmp_path / "oom")
    receipt, _ = _run_quiet(quiet_tree, contract, monkeypatch, oom_killed=("frontendproxy",),
                            lose_spans=_tokens(quiet_tree, contract, range(20, 40)))
    assert receipt["state"] == "invalid" and "container health: OOMKilled: frontendproxy" in receipt["error"]
    assert _record(contract)["windows"]["whole-measurement"]["incomplete"] == 20


def _synthetic(timing, *, epoch, lost=(), bare=(), proxy_only=(), failed=(), rate=1.0, offered=None):
    """A cell, ledger and correlation for the record functions alone (no runner): request i is scheduled at i / rate;
    ``lost`` lack productcatalogservice, ``proxy_only`` keep only frontendproxy, ``bare`` have no trace at all and
    ``failed`` timed out without one."""
    offered = offered if offered is not None else int(timing["offered"])
    route = ["frontend", "frontendproxy", "productcatalogservice"]
    requests, rows = [], []
    for sequence in range(offered):
        token, trace = "tok-%04d" % sequence, "%032x" % (sequence + 1)
        requests.append({
            "requestToken": token, "originalTraceId": trace, "scheduledOffsetSeconds": sequence / rate,
            "startedMonotonic": 5000.0 + sequence / rate + 0.001, "outcome": "timeout" if sequence in failed else "ok",
        })
        services = (["frontend", "frontendproxy"] if sequence in lost else ["frontendproxy"] if sequence in proxy_only
                    else [] if sequence in bare or sequence in failed else route)
        rows.append({"requestToken": token, "injectedOriginalTraceId": trace,
                     "observedOriginalTraceIds": [trace] if services else [], "observedPathServices": services})
    cell = {"runId": "r" * 24, "studyEpoch": epoch, "timing": timing,
            "posture": {"expected": {"activeApplicationServices": sorted(set(route) | {"cartservice", "otelcol"})}}}
    return cell, {"barrierMonotonic": 5000.0, "requests": requests}, {"rows": rows}


def test_runs_and_missing_services_are_recorded_per_request():
    """Runs are maximal stretches of consecutively scheduled requests that are each successful and incomplete: a
    complete request and an unsuccessful one both end a run."""
    remote = load("otel_quiet_record_remote", MODULE / "execution/candidate_remote.py")
    timing = quiet.cell_timing("no-fault-calibration", 1.0, 1)
    cell, ledger, correlation = _synthetic(
        timing, epoch=QUIET, lost=(10, 11, 12), proxy_only=(14,), failed=(15,), bare=(16, 17),
    )
    record = remote.trace_completeness(cell, ledger, correlation, None)
    window = record["windows"]["whole-measurement"]
    assert (window["requests"], window["successful"], window["complete"], window["incomplete"]) == (180, 179, 173, 6)
    assert (window["unsuccessful"], window["unsuccessfulIncomplete"]) == (1, 1)
    assert window["incompleteByMissingService"] == {"frontend": 3, "frontendproxy": 2, "productcatalogservice": 6}
    assert [(row["scheduledOffsetSeconds"], row["ownTraceObserved"], row["missingServices"])
            for row in window["incompleteRequests"]] == [
        (10.0, True, ["productcatalogservice"]), (11.0, True, ["productcatalogservice"]),
        (12.0, True, ["productcatalogservice"]), (14.0, True, ["frontend", "productcatalogservice"]),
        (16.0, False, ["frontend", "frontendproxy", "productcatalogservice"]),
        (17.0, False, ["frontend", "frontendproxy", "productcatalogservice"]),
    ]
    assert window["incompleteRuns"] == [
        {"firstScheduledOffsetSeconds": 10.0, "lastScheduledOffsetSeconds": 12.0, "requests": 3,
         "missingServices": ["productcatalogservice"]},
        {"firstScheduledOffsetSeconds": 14.0, "lastScheduledOffsetSeconds": 14.0, "requests": 1,
         "missingServices": ["frontend", "productcatalogservice"]},
        {"firstScheduledOffsetSeconds": 16.0, "lastScheduledOffsetSeconds": 17.0, "requests": 2,
         "missingServices": ["frontend", "frontendproxy", "productcatalogservice"]},
    ]
    assert record["decision25Counterfactual"] == {"allowance": 1, "wouldHaveBlocked": True, "applied": False}
    assert record["valid"] is True
    # The ledger's own order does not matter: runs follow the scheduled offsets.
    shuffled = dict(ledger, requests=list(reversed(ledger["requests"])))
    assert remote.trace_completeness(cell, shuffled, correlation, None) == record


def test_the_rule_key_is_bound_to_the_quiet_epoch_and_fails_closed():
    remote = load("otel_quiet_guard_remote", MODULE / "execution/candidate_remote.py")
    quiet_timing = quiet.cell_timing("no-fault-calibration", 1.0, 1)
    sweep_timing = sweep.cell_timing("no-fault-calibration", 1.0, 1)
    for timing, epoch in ((quiet_timing, SWEEP), (sweep_timing, QUIET)):   # a sweep cell cannot opt in, nor a quiet out
        with pytest.raises(remote.RuntimeFailure, match="only the quiet calibration epoch's compiled timing"):
            remote.trace_completeness(*_synthetic(timing, epoch=epoch), None)
    with pytest.raises(remote.RuntimeFailure, match="unknown trace completeness rule"):
        remote.trace_completeness(*_synthetic(dict(quiet_timing, traceCompletenessRule="protocol-decision-25"),
                                              epoch=QUIET), None)
    cell, ledger, correlation = _synthetic(quiet_timing, epoch=QUIET)
    with pytest.raises(remote.RuntimeFailure, match="applies to no-fault cells only"):
        remote.trace_completeness(cell, ledger, correlation, {"actualOnsetMonotonicOffsetSeconds": 60.0})
    with pytest.raises(remote.RuntimeFailure, match="applies to no-fault cells only"):
        remote.trace_completeness(dict(cell, timing=dict(quiet_timing, faultApplied=True)), ledger, correlation, None)


def test_a_contract_cannot_drop_or_change_its_trace_rule(quiet_tree, quiet_package):
    runtime = quiet_tree.runtime
    contract = runtime.execution_package(quiet_package)["cells"][5]
    assert runtime.sweep_cell_timing(contract)["traceCompletenessRule"] == TRACE_RULE
    dropped = copy.deepcopy(contract)
    del dropped["timing"]["traceCompletenessRule"]
    with pytest.raises(runtime.GateError, match="cell timing fields differ"):
        runtime.sweep_cell_timing(dropped)
    changed = copy.deepcopy(contract)
    changed["timing"]["traceCompletenessRule"] = "protocol-decision-25"
    with pytest.raises(runtime.GateError, match="not the active compiled plan's timing"):
        runtime.sweep_cell_timing(changed)


def test_the_sweeps_trace_record_is_byte_identical_to_its_relaunch_commit(tmp_path):
    """Decision 25 is untouched for the sweep: on sweep timings the record equals the one candidate_remote.py at
    c532853 writes, for the lost batch in a no-fault cell (blocking there) and for a fault cell."""
    old_file = tmp_path / "candidate_remote_c532853.py"
    old_file.write_bytes(_git_show("modules/otel-demo/execution/candidate_remote.py", SWEEP_COMMIT))
    old = load("otel_quiet_remote_c532853", old_file)
    new = load("otel_quiet_remote_now", MODULE / "execution/candidate_remote.py")
    no_fault = _synthetic(sweep.cell_timing("no-fault-calibration", 10.0, 1), epoch=SWEEP, rate=10.0,
                          lost=set(ATTEMPT1_LOST), failed=(5,))
    fault_timing = sweep.cell_timing("productcatalog-cpu-throttle-effect", 1.0, 1)
    fault = _synthetic(fault_timing, epoch=SWEEP, lost=(3, 70, 71, 150), bare=(100,))
    intervention = {"actualOnsetMonotonicOffsetSeconds": fault_timing["faultOnsetSeconds"],
                    "readyAtMonotonic": 5000.0 + fault_timing["faultOnsetSeconds"] + 61.0}
    for (cell, ledger, correlation), receipt in ((no_fault, None), (fault, intervention)):
        mine, theirs = new.trace_completeness(cell, ledger, correlation, receipt), old.trace_completeness(
            cell, ledger, correlation, receipt)
        assert quiet.canonical_json_bytes(mine) == quiet.canonical_json_bytes(theirs)
        assert mine["rule"] == "protocol-decision-25" and "traceCompletenessRule" not in cell["timing"]
    assert new.trace_completeness(*no_fault, None)["valid"] is False          # 50 > 18 still blocks a sweep cell


# Planted defects in the retained record or its inputs: the terminal's byte-for-byte replay rejects each one.
QUIET_PLANTS = {
    "a-lost-run-erased": ("trace-completeness.json",
                          lambda v: v["windows"]["whole-measurement"].__setitem__("incompleteRuns", [])),
    "the-missing-service-relabelled": ("trace-completeness.json",
                                       lambda v: v["windows"]["whole-measurement"]["incompleteByMissingService"].update(
                                           frontend=50, productcatalogservice=0)),
    "the-loss-counted-as-blocking": ("trace-completeness.json",
                                     lambda v: (v.__setitem__("blocking", True), v.__setitem__("allowance", 18))),
    "the-loss-hidden-in-the-correlation": ("trace-correlation.json", lambda v: [
        (row.__setitem__("observedPathServices", ["frontend", "frontendproxy", "productcatalogservice"]),
         row.__setitem__("observedTraceServices", ["frontend", "frontendproxy", "productcatalogservice"]))
        for row in v["rows"] if row["observedPathServices"] == ["frontend", "frontendproxy"]]),
}


@pytest.mark.parametrize("plant", sorted(QUIET_PLANTS))
def test_planted_trace_loss_record_defects_are_rejected_by_the_terminal(quiet_tree, lost_batch_cell, tmp_path, plant):
    receipt, contract = lost_batch_cell
    name, mutate = QUIET_PLANTS[plant]
    cell_root = tmp_path / "cell"
    shutil.copytree(Path(contract["remoteArtifactRoot"]), cell_root)
    assert quiet_tree.terminal.validate_cell(cell_root, contract)["state"] == "valid"
    helpers._plant(quiet_tree, cell_root, contract, name, mutate)
    with pytest.raises(quiet_tree.terminal.ValidationError, match="trace completeness record does not replay"):
        quiet_tree.terminal.validate_cell(cell_root, contract)


# ------------------------- 7. run A2 (protocol decision 68, 2026-10-10): attempt 3 of the same epoch, descriptor and design
# A ran as attempt 1 (stopped at cell 8) and relaunch 1 = attempt 2 (40/40). A2 is attempt 3: the run ID hashes the runKey,
# which carries the attempt, so its 40 IDs are new, while every timing (keyed by regime, rate and block) is A's.
RAN_QUIET_ATTEMPTS = {1: "5cec5a69", 2: "bb1eb1fc"}         # attempt -> the plan prefix that ran on fb14srv6


def _spent_table_in_source() -> dict:
    """SPENT_ATTEMPTS_BY_EPOCH read from the adapter's source text, so it does not depend on which epoch a selector names."""
    tree_ = ast.parse((MODULE / "execution/candidate_runtime_adapter.py").read_text())
    for node in tree_.body:
        if isinstance(node, ast.Assign) and any(getattr(t_, "id", None) == "SPENT_ATTEMPTS_BY_EPOCH" for t_ in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("SPENT_ATTEMPTS_BY_EPOCH not found")


def _unrecorded_attempts(table: dict, epoch: str, ran: dict) -> list:
    """Attempts that ran on a host but are not recorded as spent for their epoch, each recorded with its plan prefix."""
    spent = table.get(epoch, {})
    return sorted(a for a, prefix in ran.items() if a not in spent or prefix not in spent[a])


def test_every_quiet_attempt_that_ran_is_recorded_as_spent_with_its_plan():
    table = _spent_table_in_source()
    assert _unrecorded_attempts(table, QUIET, RAN_QUIET_ATTEMPTS) == []
    assert set(table[QUIET]) == {1, 2}                      # attempt 3 (A2) is the first unspent attempt
    assert 3 not in table[QUIET]


def test_planted_defect_a_quiet_attempt_that_ran_but_is_not_recorded_is_found():
    table = _spent_table_in_source()
    forgot_two = {**table, QUIET: {a: r for a, r in table[QUIET].items() if a != 2}}
    assert _unrecorded_attempts(forgot_two, QUIET, RAN_QUIET_ATTEMPTS) == [2]
    wrong_plan = {**table, QUIET: {**table[QUIET], 2: "quiet attempt 2, plan 00000000"}}
    assert _unrecorded_attempts(wrong_plan, QUIET, RAN_QUIET_ATTEMPTS) == [2]
    assert _unrecorded_attempts({}, QUIET, RAN_QUIET_ATTEMPTS) == [1, 2]


def test_planted_defect_without_the_spent_row_attempt_2_would_reuse_as_run_ids_and_the_adapter_refuses_it(
    quiet_tree, tmp_path,
):
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_quiet_a2_tree_adapter", quiet_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "2")
            with pytest.raises(adapter.runtime.GateError, match="attempt 2 is spent"):
                adapter.inspect_campaign(tmp_path / "real", "a" * 40)
            # The planted defect: attempt 2's row is missing. The adapter then plans A's relaunch-1 cells again, with the
            # run IDs that already exist on the host, and only the spent table stood between that and a launch.
            patch.delitem(adapter.SPENT_ATTEMPTS, 2)
            bindings = adapter.inspect_campaign(tmp_path / "planted", "a" * 40)
        assert bindings.plan_sha256 == QUIET_PLAN_A2_SHA256
        ran = {cell["runId"] for cell in quiet.flatten_cells(quiet.compile_plan(quiet.load_descriptor(), 2))}
        assert set(bindings.run_ids) == ran and len(ran) == 40
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_run_a2_is_attempt_3_same_descriptor_same_timings_new_run_ids():
    document = quiet.load_descriptor()
    assert quiet.canonical_sha256(document) == QUIET_DESCRIPTOR_SHA256           # the descriptor A2 binds is A's relaunch-1 one
    plans = {attempt: quiet.compile_plan(document, attempt) for attempt in (1, 2, 3)}
    assert quiet.canonical_sha256(plans[3]) == QUIET_PLAN_A3_SHA256
    assert len({quiet.canonical_sha256(plan) for plan in plans.values()}) == 3
    cells = {attempt: quiet.flatten_cells(plan) for attempt, plan in plans.items()}
    ids = {attempt: {cell["runId"] for cell in rows} for attempt, rows in cells.items()}
    assert all(len(rows) == 40 for rows in ids.values())
    assert not ids[3] & (ids[1] | ids[2])                                          # none of A's 80 run IDs is reused
    assert not ids[1] & ids[2]
    # Same cells in the same order with the same onsets and timing: A2 repeats A's schedule (keyed by regime, rate, block).
    for attempt in (2, 3):
        assert [c["timing"] for c in cells[attempt]] == [c["timing"] for c in cells[1]]
        assert [(c["runKey"]["requestsPerSecond"], c["runKey"]["block"]) for c in cells[attempt]] == [
            (c["runKey"]["requestsPerSecond"], c["runKey"]["block"]) for c in cells[1]]
    assert {c["runKey"]["attempt"] for c in cells[3]} == {3}
    assert plans[3]["schedule"] == plans[2]["schedule"] == plans[1]["schedule"]
    assert {c["timing"]["traceCompletenessRule"] for c in cells[3]} == {TRACE_RULE}


def test_the_collector_carrier_of_the_quiet_epoch_keeps_the_default_log_sampler(quiet_tree):
    """Decision 66 (sampling off) names the repeat epoch only: run A2's carrier is run A's (sampling on)."""
    materialize = load("otel_quiet_a2_materialize", quiet_tree.root / "modules/otel-demo/materialize.py")
    assert materialize.selected_study_epoch() == QUIET
    assert materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS == (
        "otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1", "otel-load-pilot-v1", "otel-offpath-pilot-v1",
        "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")   # B, C, the pilots, campaign E
    assert QUIET not in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS
