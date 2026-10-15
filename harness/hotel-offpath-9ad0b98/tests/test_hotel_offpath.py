"""hotel-offpath-v1: the Hotel off-path epoch (budget BUDGET_OVERNIGHT_20261014 item 4), a fourth Hotel epoch.

Covers: the plan is 30 cells (3 regimes x 2 rates x 5 blocks), each block holds every (regime, rate) pair once in a
seeded order recomputed here from the recorded encoding; every cell has the sweep's cell shape and only the seeded
onset (and what derives from it) differs; the descriptor differs from the sweep's in exactly the design sections,
and the frozen ground truth is overridden there, never edited; the earlier epochs (frozen, sweep, quiet) are
unchanged (digests, files, and what their runtimes compile); the selector activates the epoch with a derived 3 h
budget; sealed consul-pause cells validate (route up or down), and every scope and manifestation defect planted
into a sealed cell is refused; one fake-driven run_cell of each regime collects consul and unpauses it in cleanup;
and the 3.9 floor.

The epoch is exercised in a copy of the module tree with its selector written into it (what the target sees after
the selector is committed), the earlier epochs in copies with their own selectors.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from datetime import timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation"
OFFPATH = "hotel-offpath-v1"
SWEEP = "hotel-traffic-sweep-v1"
QUIET = "hotel-quiet-calibration-v1"
RATES = (10.0, 1.0)
REGIMES = ("no-fault-calibration", "consul-pause-effect", "search-pause-effect")
FROZEN_COMMIT = "e4fd4c7"                                   # the frozen epoch's harness
SWEEP_COMMIT = "ca58974785c97fe54afe351f928c65fa46f18403"   # the harness of sweep relaunch 3
QUIET_COMMIT = "e9d35f7fffcab4134b53a864cd36613cc628cb4d"   # the quiet calibration epoch, activated
SWEEP_DESCRIPTOR_SHA256 = "788ff28cc44248fec518fd04e3e0f91ab6d92229888a1412a52e50f9dd889dab"
SWEEP_PLAN_SHA256 = "766063c5a0f0b90ab1aba1ada29b86e152e8ec1e7f7bd048d4c802c10b7bbc72"
QUIET_DESCRIPTOR_SHA256 = "fa42391ddb766e03bfbbf0eb212bff0b5409ed8def238a754199c17a4301efea"
QUIET_PLAN_SHA256 = "554a7a1e753a7f3535a7ae1c796cceee986bf0b1ae4b629858de2a547d79b127"
# Onset-derived timing keys (and the witnessed-start floors derived from the onset): the only ones in which an
# off-path cell may differ from the sweep's cell of the same fault.
ONSET_KEYS = {"faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "tcpSnapshotOffsetsSeconds",
              "minimumWitnessedStartsByPhase"}



def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


offpath = load("hotel_offpath_compiler_test", MODULE / "execution/candidate_offpath.py")
quiet_tests = load("hotel_offpath_test_quiet_tests", Path(__file__).parent / "test_hotel_quiet_calibration.py")
executor = load("hotel_offpath_test_executor_tests", Path(__file__).parent / "test_hotel_offpath_executor.py")
helpers = quiet_tests.helpers
sweep = quiet_tests.sweep
quiet = quiet_tests.quiet


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    return quiet_tests._tree(tmp_path_factory.mktemp("offpath-tree"), OFFPATH)


@pytest.fixture(scope="module")
def sweep_tree(tmp_path_factory):
    return quiet_tests._tree(tmp_path_factory.mktemp("offpath-sweep-tree"), SWEEP)


@pytest.fixture(scope="module")
def quiet_tree(tmp_path_factory):
    return quiet_tests._tree(tmp_path_factory.mktemp("offpath-quiet-tree"), QUIET)


def _contracts(tr, artifact_root: Path) -> tuple:
    runtime = tr["runtime"]
    document = helpers._admission(runtime, artifact_root, plan_sha256=offpath.EXPECTED_PLAN_SHA256,
                                  run_count=offpath.TOTAL_RUNS, wall=offpath.MAXIMUM_WALL_SECONDS)
    return document, runtime.cell_contracts(document)


def _contract(tr, campaign: Path, regime: str, rate: float, block: int = 2) -> dict:
    _, contracts = _contracts(tr, campaign)
    run_id = "%s-r%s-b%02d-full-a01" % (regime, offpath.rate_token(rate), block)
    return next(row for row in contracts if row["runId"] == run_id)


# ----------------------------------------------------------------------------------------------- 1. the plan
def test_plan_is_30_cells_3_regimes_2_rates_5_blocks_with_every_pair_once_per_block():
    descriptor = offpath.load_descriptor()
    assert offpath.canonical_sha256(descriptor) == offpath.EXPECTED_DESCRIPTOR_SHA256
    assert offpath.DEFAULT_DESCRIPTOR.read_bytes() == offpath.descriptor_bytes()    # generated, never hand-edited
    plan = offpath.compile_plan(descriptor)
    assert plan == offpath.compile_plan(copy.deepcopy(descriptor))
    assert plan["planCanonicalSha256"] == offpath.EXPECTED_PLAN_SHA256
    cells = offpath.flatten_cells(plan)
    assert plan["runCount"] == offpath.TOTAL_RUNS == len(cells) == len({c["runId"] for c in cells}) == 30
    assert "sequence" not in plan and "regimeRoots" not in plan and [b["block"] for b in plan["blocks"]] == [1, 2, 3, 4, 5]
    pairs = {(regime, rate) for regime in REGIMES for rate in RATES}
    for block in plan["blocks"]:
        assert [c["position"] for c in block["cells"]] == [1, 2, 3, 4, 5, 6]
        assert {(c["runKey"]["regime"], c["runKey"]["requestsPerSecond"]) for c in block["cells"]} == pairs
        assert all(c["runKey"]["block"] == block["block"] for c in block["cells"])
    assert {c["runKey"]["posture"] for c in cells} == {"full"} and {c["runKey"]["studyEpoch"] for c in cells} == {OFFPATH}
    assert {c["runKey"]["regime"]: c["fault"] for c in cells} == {
        "no-fault-calibration": None, "consul-pause-effect": "consul-pause", "search-pause-effect": "search-pause"}
    assert {c["artifactRoot"].split("/r")[0] for c in cells} == {
        "calibration", "effect/consul-pause", "effect/search-pause"}
    assert [(r["id"], r["fault"], r["role"]) for r in descriptor["design"]["regimes"]] == [
        ("no-fault-calibration", None, "no-fault"), ("consul-pause-effect", "consul-pause", "off-path-pause"),
        ("search-pause-effect", "search-pause", "on-path-control")]
    assert descriptor["design"]["offPathRouteOutageRequired"] is False
    # The off-path pause target exists only here; the sweep never declares it.
    assert "consul-pause" not in sweep.FAULTS.values() and set(offpath.RATES) <= set(sweep.RATES)


def test_block_order_is_a_seeded_fisher_yates_shuffle_recomputed_from_the_recorded_encoding(monkeypatch):
    descriptor = offpath.load_descriptor()
    plan = offpath.compile_plan(descriptor)
    assert descriptor["schedule"]["seed"] == offpath.SCHEDULE_SEED == 20261015
    orders = []
    for block in range(1, 6):
        pairs = [(regime, rate) for regime in REGIMES for rate in RATES]
        for index in range(len(pairs) - 1, 0, -1):
            text = "20261015\0%s\0block-%02d\0draw-%d\0offpath-schedule-v1" % (OFFPATH, block, index)
            other = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (index + 1)
            pairs[index], pairs[other] = pairs[other], pairs[index]
        expected = ["%s-r%s-b%02d-full-a01" % (regime, offpath.rate_token(rate), block) for regime, rate in pairs]
        assert plan["blocks"][block - 1]["order"] == descriptor["schedule"]["blocks"][block - 1]["runIds"] == expected
        assert [c["runId"] for c in plan["blocks"][block - 1]["cells"]] == expected
        assert descriptor["schedule"]["blocks"][block - 1]["orderSha256"] == offpath.canonical_sha256(expected)
        orders.append(expected)
    # Shuffled per block: the five blocks do not all run the same order, and no block-1 lead cell is fixed.
    assert len({tuple(run_id.rsplit("-b", 1)[0] for run_id in order) for order in orders}) > 1
    assert descriptor["timing"]["leadCell"] is None
    # Another seed gives another order: the order is the seed's.
    before = [(row["regime"], row["rate"]) for row in offpath.block_order(1)]
    monkeypatch.setattr(offpath, "SCHEDULE_SEED", 1)
    assert [(row["regime"], row["rate"]) for row in offpath.block_order(1)] != before


def test_every_cell_has_the_sweep_cell_shape_and_only_the_onset_derived_values_differ():
    references = {}
    for cell in sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor())):
        references.setdefault((cell["fault"], cell["timing"]["requestsPerSecond"]), cell["timing"])
    strata: dict = {}
    for cell in offpath.flatten_cells(offpath.compile_plan(offpath.load_descriptor())):
        timing, rate = cell["timing"], cell["timing"]["requestsPerSecond"]
        # consul-pause is timed like the sweep's pause of the same rate (60 s hold, same floors rule).
        reference = references[("search-pause" if cell["fault"] == "consul-pause" else cell["fault"], rate)]
        assert set(timing) == set(reference)
        assert {k: v for k, v in timing.items() if k not in ONSET_KEYS} == {
            k: v for k, v in reference.items() if k not in ONSET_KEYS}
        offset, onset = timing["faultOnsetPhaseOffsetSeconds"], timing["faultOnsetSeconds"]
        assert 0 <= offset < 1 / rate and onset == round(60 + offset, 6)
        assert timing["scoredWindowSeconds"] == [onset, round(onset + 60, 6)]
        assert timing["tcpSnapshotOffsetsSeconds"] == {"pre-fault": round(onset - 15, 6),
                                                       "during-fault": round(onset + 7, 6)}
        if cell["fault"] is None:
            assert timing["minimumWitnessedStartsByPhase"] is None and timing["faultApplied"] is False
        else:
            assert timing["faultApplied"] is True and timing["probeStamps"] is True
            assert timing["minimumWitnessedStartsByPhase"] == sweep.phase_floors(rate, 180, onset, 60)
        key = (cell["runKey"]["regime"], rate)
        strata.setdefault(key, []).append(int(5 * offset / timing["interArrivalSeconds"]))
    # The sweep's stratified rule with five strata: each fifth of one inter-arrival exactly once per (regime, rate).
    assert len(strata) == 6 and all(sorted(value) == [0, 1, 2, 3, 4] for value in strata.values())


def test_descriptor_differs_from_the_sweeps_in_exactly_the_design_sections():
    mine, base = offpath.load_descriptor(), sweep.load_descriptor()
    assert {k for k in set(mine) | set(base) if mine.get(k) != base.get(k)} == {
        "id", "declaration", "workload", "design", "timing", "schedule", "groundTruth", "protocolGates",
        "collection", "faultParameters", "analysis", "derivedFrom"}
    assert {k for k in set(mine["timing"]) | set(base["timing"]) if mine["timing"].get(k) != base["timing"].get(k)} == {
        "leadCell", "onsetStrataPerRegimeAndRate", "offeredByRate", "minimumTimedSeconds", "budget"}
    assert {k for k in mine["timing"]["budget"] if mine["timing"]["budget"][k] != base["timing"]["budget"][k]} == {
        "maximumWallSeconds", "minimumFirstMutationRemainingSeconds"}
    assert {k for k in set(mine["workload"]) | set(base["workload"]) if mine["workload"].get(k) != base["workload"].get(k)} == {
        "requestsPerSecondLevels"}
    assert {k for k in set(mine["protocolGates"]) | set(base["protocolGates"])
            if mine["protocolGates"].get(k) != base["protocolGates"].get(k)} == {"f1OffPathManifestation"}
    assert mine["derivedFrom"]["descriptorCanonicalSha256"] == SWEEP_DESCRIPTOR_SHA256
    assert mine["derivedFrom"]["planCanonicalSha256"] == SWEEP_PLAN_SHA256
    assert mine["faultParameters"]["targets"] == {"consul-pause": "consul", "search-pause": "search"}
    # The collection scope: consul beside the ten application services, in this descriptor only.
    assert mine["collection"]["extraScopeServices"] == ["consul"] and len(mine["collection"]["scopeServices"]) == 11
    assert "scopeServices" not in base["collection"]


def test_ground_truth_declares_consul_pause_and_keeps_the_frozen_descriptor_untouched():
    truth = offpath.load_descriptor()["groundTruth"]
    contracts = {row["scenario"]: row for row in truth["fault"]["scenarioContracts"]}
    assert set(contracts) == {"search-pause", "consul-pause"}
    assert contracts["consul-pause"]["service"] == "consul"
    assert contracts["consul-pause"]["routeOutageDuringHold"] == "recorded-not-required"
    assert contracts["consul-pause"]["duringPathTruth"] == "hotel-search-normal-v1"          # nothing is excused
    assert truth["fault"]["offPathManifestation"]["scenarios"] == ["consul-pause"]
    assert [row["fault"] for row in truth["path"]["faultSpecific"]] == ["search-pause"]
    # Overridden here, never edited: the frozen epoch's own files are the bytes they were at e4fd4c7.
    for relative in ("modules/hotel-reservation/execution/candidate_pilot.py",
                     "pipelines/campaigns/hotel-reservation-selected-v1.json",
                     "modules/hotel-reservation/execution/runtime-policy.json"):
        blob = subprocess.run(["git", "-C", str(ROOT), "show", "%s:%s" % (FROZEN_COMMIT, relative)],
                              capture_output=True, check=True).stdout
        assert (ROOT / relative).read_bytes() == blob, relative
    assert "consul-pause" not in offpath.frozen.FAULT_TARGETS


@pytest.mark.parametrize("mutate", [
    lambda d: d["design"].__setitem__("blocks", 4),
    lambda d: d["design"].__setitem__("rates", [10.0, 1.0, 0.2]),
    lambda d: d["design"].__setitem__("offPathRouteOutageRequired", True),
    lambda d: d["design"]["regimes"][1].__setitem__("fault", "search-pause"),
    lambda d: d["groundTruth"]["fault"]["scenarioContracts"].pop(),                  # no consul-pause contract
    lambda d: d["groundTruth"]["fault"]["scenarioContracts"][-1].__setitem__("routeOutageDuringHold", "required"),
    lambda d: d["collection"].__setitem__("extraScopeServices", []),
    lambda d: d["faultParameters"]["targets"].__setitem__("consul-pause", "jaeger"),
    lambda d: d["timing"].__setitem__("leadCell", "consul-pause-effect-r10-b01 first in block 1"),
])
def test_planted_descriptor_changes_are_refused(mutate):
    planted = copy.deepcopy(offpath.load_descriptor())
    mutate(planted)
    with pytest.raises(offpath.ProtocolError):
        offpath.validate_descriptor(planted)


def test_a_changed_parameter_changes_the_digests_so_the_pins_refuse_it(monkeypatch):
    monkeypatch.setattr(offpath, "BLOCKS", 4)
    with pytest.raises(offpath.ProtocolError):
        offpath.load_descriptor()
    monkeypatch.setattr(offpath, "BLOCKS", 5)
    monkeypatch.setattr(offpath, "RATES", (10.0, 3.0))
    with pytest.raises(offpath.ProtocolError, match="members of the sweep's rate set"):
        offpath._check_parameters()


def test_budget_is_derived_by_the_sweeps_rule_and_fits_four_hours_on_srv4():
    assert (offpath.MAXIMUM_WALL_SECONDS, offpath.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (10800, 10500)
    assert offpath.TOTAL_RUNS == 30 and offpath.MINIMUM_TIMED_SECONDS == 30 * 210
    assert offpath.MAXIMUM_WALL_SECONDS >= 30 * offpath.CELL_PERIOD_ESTIMATE_SECONDS + 900
    # Sweep relaunch 3 (srv4): median 246.5 s, maximum 261.6 s per cell.  Instance-level.
    assert offpath.MAXIMUM_WALL_SECONDS >= 30 * 261.6 + 600 + 300
    assert offpath.MAXIMUM_WALL_SECONDS <= 4 * 3600
    assert 30 * 246.5 / 3600 < 2.1                                  # the expected duration, from the median period


# ---------------------------------------------------------------------------- 2. earlier epochs are unchanged
def test_the_sweep_and_quiet_plans_are_unchanged():
    descriptor = sweep.load_descriptor()
    assert sweep.canonical_sha256(descriptor) == SWEEP_DESCRIPTOR_SHA256
    assert sweep.compile_plan(descriptor)["planCanonicalSha256"] == SWEEP_PLAN_SHA256
    descriptor = quiet.load_descriptor()
    assert quiet.canonical_sha256(descriptor) == QUIET_DESCRIPTOR_SHA256
    assert quiet.compile_plan(descriptor)["planCanonicalSha256"] == QUIET_PLAN_SHA256


@pytest.mark.parametrize("commit, relative", [
    (SWEEP_COMMIT, "modules/hotel-reservation/execution/candidate_sweep.py"),
    (SWEEP_COMMIT, "pipelines/campaigns/hotel-traffic-sweep-v1.json"),
    (SWEEP_COMMIT, "modules/hotel-reservation/execution/runtime-policy.hotel-traffic-sweep-v1.json"),
    (QUIET_COMMIT, "modules/hotel-reservation/execution/candidate_quiet.py"),
    (QUIET_COMMIT, "pipelines/campaigns/hotel-quiet-calibration-v1.json"),
    (QUIET_COMMIT, "modules/hotel-reservation/execution/runtime-policy.hotel-quiet-calibration-v1.json"),
    (QUIET_COMMIT, "modules/hotel-reservation/validation/protocol_gates.py"),
    (QUIET_COMMIT, "modules/hotel-reservation/workload/candidate_search.py"),
])
def test_earlier_epoch_descriptors_plans_policies_and_compilers_are_byte_identical(commit, relative):
    blob = subprocess.run(["git", "-C", str(ROOT), "show", "%s:%s" % (commit, relative)],
                          capture_output=True, check=True).stdout
    assert (ROOT / relative).read_bytes() == blob


def _extract(commit: str, target: Path) -> Path:
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", commit,
                              "modules/hotel-reservation", "pipelines/campaigns"],
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(target, filter="data")
    return target


@pytest.mark.parametrize("epoch, compiler", [(SWEEP, sweep), (QUIET, quiet)])
def test_earlier_epochs_compile_the_same_runtime_contracts_budget_launcher_and_policy_as_at_e9d35f7(
        tmp_path, epoch, compiler):
    """The runtime gained a fourth epoch and a collection-scope table; under an earlier epoch's selector nothing
    it emits may change (planted differences are shown to fail in tests/test_hotel_offpath_executor.py)."""
    source = _extract(QUIET_COMMIT, tmp_path / "e9d35f7")
    old = quiet_tests._tree(tmp_path / "old", epoch, source=source)
    new = quiet_tests._tree(tmp_path / "new", epoch)
    old_rt, new_rt = old["runtime"], new["runtime"]
    assert old_rt.STUDY_EPOCH == new_rt.STUDY_EPOCH == epoch
    assert (old_rt.CELL_COUNT, old_rt.MAXIMUM_WALL_SECONDS, old_rt.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (
        new_rt.CELL_COUNT, new_rt.MAXIMUM_WALL_SECONDS, new_rt.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS)
    assert old_rt.CONTROLLER_PATHS == new_rt.CONTROLLER_PATHS
    assert old_rt.REMOTE_DETACHED_LAUNCH == new_rt.REMOTE_DETACHED_LAUNCH
    assert old_rt._validate_policy(old_rt._json_file(old_rt.POLICY, "p")) == new_rt._validate_policy(
        new_rt._json_file(new_rt.POLICY, "p"))
    _, before = quiet_tests._contracts(old, tmp_path / "campaign", compiler)
    _, after = quiet_tests._contracts(new, tmp_path / "campaign", compiler)
    assert len(after) == compiler.TOTAL_RUNS and new_rt.canonical_bytes(before) == new_rt.canonical_bytes(after)
    assert new_rt.collection_extra_services(epoch) == ()


# -------------------------------------------------------------------------- 3. the committed selector activates
def test_the_epoch_is_registered_and_selectable_with_a_derived_budget(tree, tmp_path):
    runtime = tree["runtime"]
    assert runtime.STUDY_EPOCH == OFFPATH and runtime.CELL_COUNT == 30
    assert (runtime.MAXIMUM_WALL_SECONDS, runtime.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (10800, 10500)
    policy = runtime._validate_policy(runtime._json_file(runtime.POLICY, "policy"))
    sweep_policy = json.loads((MODULE / "execution/runtime-policy.hotel-traffic-sweep-v1.json").read_text())
    assert list(policy) == list(sweep_policy)
    assert {key for key in policy if policy[key] != sweep_policy[key]} == {
        "studyEpoch", "maximumCells", "maximumWallSeconds", "minimumFirstMutationRemainingSeconds"}
    assert policy["maximumCells"] == 30
    paths = runtime.CONTROLLER_PATHS
    assert paths["candidate-compiler"].endswith("candidate_offpath.py")
    assert paths["sweep-compiler"].endswith("candidate_sweep.py")
    assert len(set(paths.values())) == len(paths)                # the install manifest needs distinct paths
    for name in ("sweep-compiler", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
                 "candidate-descriptor", "runtime-policy"):
        assert (tree["root"] / paths[name]).is_file()
    document, contracts = _contracts(tree, tmp_path / "campaign")
    assert len(contracts) == 30 and [row["ordinal"] for row in contracts] == list(range(1, 31))
    assert runtime.frozen_cell_contracts(document) == contracts
    assert all(row["studyEpoch"] == OFFPATH and set(row["timing"]) == runtime.CELL_TIMING_KEYS for row in contracts)
    assert sorted({row["fault"] for row in contracts if row["fault"]}) == ["consul-pause", "search-pause"]
    assert [row["runId"] for row in contracts] == [c["runId"] for c in offpath.flatten_cells(
        offpath.compile_plan(offpath.load_descriptor()))]
    for row in contracts:
        assert runtime.cell_timing(row) == row["timing"]
    planted = copy.deepcopy(contracts[3])
    planted["timing"]["faultOnsetSeconds"] += 1
    with pytest.raises(runtime.GateError, match="not the active compiled plan"):
        runtime.cell_timing(planted)
    launcher = runtime.REMOTE_DETACHED_LAUNCH
    compile(launcher, "offpath-launcher", "exec")
    assert 'binding.get("maximumWallSeconds")!=10800' in launcher
    assert "remaining < 10500 or remaining > 10805" in launcher
    assert "21600" not in launcher and "14400" not in launcher and "17700" not in launcher
    runtime.validate_embedded_remote_programs()
    text = runtime.expected_gate_run_text({**document["bindings"], "frameworkCommit": "a" * 40,
                                           "readinessCaptureId": "x", "readinessObservedAt": "y",
                                           "transportUser": "root", "setupUser": "root",
                                           "executionUser": "fhuebscher", "executionUid": 1007,
                                           "executionGid": 1007, "dockerGid": 998})
    assert f"study={OFFPATH} " in text and "cells=30 " in text and "wallSeconds=10800 " in text


def test_the_collection_scope_table_names_consul_for_this_epoch_only(tree):
    runtime = tree["runtime"]
    assert runtime.collection_extra_services(OFFPATH) == ("consul",)
    for other in (SWEEP, QUIET, "hotel-reservation-selected-v1", None, 3):
        assert runtime.collection_extra_services(other) == ()
    assert runtime.COLLECTION_EXTRA_SERVICES == {OFFPATH: ("consul",)}


def test_the_committed_selector_is_a_declared_epoch():
    selector = json.loads((MODULE / "execution/study-epoch.json").read_text())
    runtime = load("hotel_offpath_selector_runtime", MODULE / "execution/candidate_runtime.py")
    assert selector["studyEpoch"] in runtime.EPOCH_CONTROLLER_PATHS
    assert {SWEEP, QUIET, OFFPATH} <= set(runtime.EPOCH_CONTROLLER_PATHS)


def test_driver_config_reads_the_offpath_epoch_and_a_3_hour_window(tree, sweep_tree, quiet_tree):
    pytest.importorskip("obsplacement.gate_driver.contract")
    config = load("hotel_offpath_driver_config_test", MODULE / "drivers/gate_driver_config.py")
    assert config._active_epoch(tree["root"]) == (OFFPATH, 3)
    assert config._active_epoch(sweep_tree["root"]) == (SWEEP, 6)
    assert config._active_epoch(quiet_tree["root"]) == (QUIET, 4)
    assert (3 + 1) * 3600 > offpath.MAXIMUM_WALL_SECONDS         # the launcher's watcher cap is run_window_hours + 1


@pytest.mark.parametrize("regime", REGIMES)
@pytest.mark.parametrize("rate", RATES)
def test_workload_accepts_offpath_run_ids(tree, regime, rate):
    run_id = "%s-r%s-b05-full-a01" % (regime, offpath.rate_token(rate))
    plan = tree["workload"].build_plan(run_id, offpath.EXPECTED_PLAN_SHA256, helpers.BARRIER_AT, helpers.BARRIER,
                                       rate=rate, duration_seconds=180.0,
                                       created_at=helpers.BARRIER_AT - timedelta(minutes=1))
    assert plan["offered"] == round(rate * 180) and plan["rate"] == rate


# --------------------------------------------------------------------------- 4. sealed cells of this epoch
SCOPE = ("consul",)


def _seal(tr, root: Path, contract: dict, *, receipt=None, extra=SCOPE, events=None, **kwargs) -> None:
    helpers._seal_sweep_cell(tr, root, contract, receipt=receipt, extra_services=extra,
                             docker_events=events if events is not None else (), **kwargs)


def _consul_cell(tr, campaign: Path, rate: float, *, route_during: bool = True, block: int = 2):
    contract = _contract(tr, campaign, "consul-pause-effect", rate, block)
    return contract, executor._consul_receipt(contract["timing"], route_during=route_during)


@pytest.mark.parametrize("route_during", [True, False])
@pytest.mark.parametrize("rate", RATES)
def test_a_sealed_consul_pause_cell_validates_with_the_route_up_or_down(tree, tmp_path, rate, route_during):
    contract, receipt = _consul_cell(tree, tmp_path / "campaign", rate, route_during=route_during)
    root = Path(contract["runtimeArtifactRoot"])
    _seal(tree, root, contract, receipt=receipt, events=executor._pause_events("consul"))
    result = tree["terminal"].validate_cell(root, contract)
    assert result["candidateCellValid"] is True and result["opportunities"]["offered"] == round(rate * 180)
    assert result["system"]["faultEventActions"] == ["pause", "unpause"]
    # The application aggregates are the ten application containers' (10 x 10 % CPU, 10 x 2.5 s cgroup); consul is
    # reported beside them.
    assert result["cpu"]["applicationCpuSeconds"] == pytest.approx(180.0)
    assert result["system"]["costContainersCpuSeconds"] == pytest.approx(25.0)
    assert result["system"]["costExtraServicesCpuSeconds"] == {"consul": 2.5}
    verdicts = {row["gate"]: row["verdict"] for row in result["protocolGates"]["verdicts"]}
    assert result["protocolGates"]["blocking"] == ["F1", "G1", "G2", "G4"]
    assert all(verdicts[gate] == "pass" for gate in ("F1", "G1", "G2", "G4"))
    correlation = json.loads((root / "correlation.json").read_text())
    # No fault-specific path truth: nothing during the pause is excused.
    assert "faultPathTruth" not in correlation and correlation["faultTruth"]["state"] == "supported"
    assert correlation["scenario"] == "consul-pause"
    receipt_on_disk = json.loads((root / "fault-receipt.json").read_text())
    assert receipt_on_disk["outageObserved"] is (not route_during)


def test_the_on_path_control_keeps_its_during_policy_in_this_epoch(tree, tmp_path):
    contract = _contract(tree, tmp_path / "campaign", "search-pause-effect", 1.0)
    receipt = executor._consul_receipt(contract["timing"], route_during=False, scenario="search-pause",
                                       targetService="search")
    root = Path(contract["runtimeArtifactRoot"])
    _seal(tree, root, contract, receipt=receipt, events=executor._pause_events("search"))
    result = tree["terminal"].validate_cell(root, contract)
    assert result["candidateCellValid"] is True and result["system"]["faultEventActions"] == ["pause", "unpause"]
    assert "faultPathTruth" in json.loads((root / "correlation.json").read_text())
    assert "costExtraServicesCpuSeconds" in result["system"]       # the scope belongs to the epoch, not to the fault


@pytest.mark.parametrize("rate", RATES)
def test_a_sealed_no_fault_cell_of_this_epoch_also_collects_consul(tree, tmp_path, rate):
    contract = _contract(tree, tmp_path / "campaign", "no-fault-calibration", rate)
    root = Path(contract["runtimeArtifactRoot"])
    _seal(tree, root, contract)
    result = tree["terminal"].validate_cell(root, contract)
    assert result["candidateCellValid"] is True and result["system"]["faultEventActions"] == []
    assert result["system"]["costExtraServicesCpuSeconds"] == {"consul": 2.5}
    # Planted: the same cell collected without consul (an earlier epoch's scope) is refused here.
    other = _contract(tree, tmp_path / "campaign2", "no-fault-calibration", rate, block=3)
    root2 = Path(other["runtimeArtifactRoot"])
    _seal(tree, root2, other, extra=())
    with pytest.raises(tree["terminal"].TerminalError, match="application image provenance"):
        tree["terminal"].validate_cell(root2, other)


@pytest.mark.parametrize("events, label", [
    (lambda ids: [], "no docker event at all"),
    (lambda ids: [{"Action": "pause", "Actor": {"ID": ids["consul"]}}], "paused and never unpaused"),
    (lambda ids: [{"Action": a, "Actor": {"ID": ids["search"]}} for a in ("pause", "unpause")],
     "the pause happened on another container"),
    (lambda ids: [{"Action": a, "Actor": {"ID": ids["consul"]}} for a in ("pause", "unpause", "pause", "unpause")],
     "a second pause"),
    (lambda ids: [{"Action": a, "Actor": {"ID": ids["consul"]}} for a in ("unpause", "pause")], "reversed"),
    (lambda ids: [{"Action": a, "Actor": {"ID": ids["consul"]}} for a in ("pause", "unpause")]
     + [{"Action": "update", "Actor": {"ID": ids["frontend"]}}], "an unrelated mutation"),
])
def test_planted_missing_or_wrong_docker_events_refuse_a_consul_pause_cell(tree, tmp_path, events, label):
    """The independent leg of the manifestation: the receipt alone (container read back as paused) is not enough."""
    contract, receipt = _consul_cell(tree, tmp_path / "campaign", 1.0)
    root = Path(contract["runtimeArtifactRoot"])
    _seal(tree, root, contract, receipt=receipt, events=events)
    with pytest.raises(tree["terminal"].TerminalError, match="docker events do not record exactly the admitted"):
        tree["terminal"].validate_cell(root, contract)


def _reseal(tr, root: Path, name: str, edit) -> None:
    """Edit one retained file of a sealed cell and seal it again (so only the planted defect can refuse it)."""
    (root / "content-manifest.json").unlink()
    path = root / name
    document = json.loads(path.read_text())
    edit(document)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    tr["terminal"].write_manifest(root)


def _drop_consul_everywhere(document):
    if "containers" in document:
        document["containers"] = [row for row in document["containers"] if row["service"] != "consul"]


@pytest.mark.parametrize("name, edit, error, match", [
    ("images.json", _drop_consul_everywhere, "TerminalError", "application image provenance"),
    ("cost-cgroup.json", lambda d: d["containersCpuSeconds"].pop("consul"), "TerminalError", "cost cgroup evidence"),
    ("system-samples.json", lambda d: [row["services"].pop("consul") for row in d["samples"]], "TerminalError",
     "system samples are incomplete"),
    ("tcp-snapshots.json", lambda d: [row["services"].pop("consul") for row in d["snapshots"]], "TerminalError",
     "TCP snapshots are incomplete"),
    ("cost-cgroup.json", lambda d: d["containersCpuSeconds"].__setitem__("jaeger", 1.0), "TerminalError",
     "cost cgroup evidence"),
    ("cost-cgroup.json", lambda d: d["containersCpuSeconds"].__setitem__("consul", 9.0), "TerminalError",
     "figures differ from their own retained edges"),
    ("cpu.json", lambda d: d.update(applicationServices=d["applicationServices"][:-1]), "ValueError",
     "resource scope differs"),
    ("cpu.json", lambda d: [d["samples"][i].update(applicationCpuPercent=105.0) for i in range(len(d["samples"]))],
     "ValueError", "aggregate differs"),
])
def test_planted_scope_defects_in_a_sealed_consul_cell_are_refused(tree, tmp_path, name, edit, error, match):
    contract, receipt = _consul_cell(tree, tmp_path / "campaign", 1.0)
    root = Path(contract["runtimeArtifactRoot"])
    _seal(tree, root, contract, receipt=receipt, events=executor._pause_events("consul"))
    assert tree["terminal"].validate_cell(root, contract)["candidateCellValid"] is True    # the baseline is valid
    _reseal(tree, root, name, edit)
    with pytest.raises(ValueError, match=match) as raised:
        tree["terminal"].validate_cell(root, contract)
    assert error in {type(raised.value).__name__, "ValueError"}


def test_an_earlier_epoch_cell_collected_with_consul_is_refused(sweep_tree, tmp_path):
    """Planted: a sweep cell carrying consul in every collector file: the sweep's scope is the ten services."""
    _, contracts = helpers._sweep_contracts(sweep_tree, tmp_path / "campaign")
    contract = next(row for row in contracts if row["runId"] == "no-fault-calibration-r1-b01-full-a01")
    root = Path(contract["runtimeArtifactRoot"])
    helpers._seal_sweep_cell(sweep_tree, root, contract, extra_services=("consul",))
    with pytest.raises(sweep_tree["terminal"].TerminalError, match="application image provenance"):
        sweep_tree["terminal"].validate_cell(root, contract)


# ------------------------------------------------------------------ 5. one fake-driven execution of the cell runner
def _drive(monkeypatch, tr, tmp_path: Path, regime: str, rate: float, block: int = 1) -> tuple:
    cell = load("hotel_offpath_cell_%s_%s_%d" % (regime.replace("-", "_"), offpath.rate_token(rate), block),
                tr["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
    artifact = tmp_path / "campaign"
    document = helpers._admission(cell.runtime, artifact, plan_sha256=offpath.EXPECTED_PLAN_SHA256,
                                  run_count=offpath.TOTAL_RUNS, wall=offpath.MAXIMUM_WALL_SECONDS)
    run_id = "%s-r%s-b%02d-full-a01" % (regime, offpath.rate_token(rate), block)
    contract = next(row for row in cell.runtime.cell_contracts(document) if row["runId"] == run_id)
    with monkeypatch.context() as patch:
        calls = helpers._drive_run_cell(patch, cell, contract, document, artifact, extra_services=("consul",),
                                        real_cleanup=True)
    return calls, contract, cell


@pytest.mark.parametrize("regime", REGIMES)
def test_run_cell_collects_consul_and_unpauses_it_in_cleanup_in_every_regime(monkeypatch, tree, tmp_path, regime):
    calls, contract, cell = _drive(monkeypatch, tree, tmp_path, regime, 1.0)
    scope = sorted(cell.APPLICATION_SERVICES + ("consul",))
    assert calls["identitiesAsked"] == list(cell.APPLICATION_SERVICES) + ["consul"]
    assert calls["imageServices"] == list(cell.APPLICATION_SERVICES) + ["consul"]
    for key in ("cpuServices", "costServices", "tcpServices", "samplerServices"):
        assert calls[key] == scope, key
    logs = next(row["argv"] for row in calls["commands"] if "logs" in row["argv"])
    assert logs[-11:] == list(cell.APPLICATION_SERVICES) + ["consul"]
    unpause = next(row["argv"] for row in calls["commands"] if "unpause" in row["argv"])
    assert unpause[unpause.index("unpause"):] == ["unpause", "search", "reservation", "consul"]
    assert calls["execute"]["rate"] == 1.0 and calls["execute"]["duration"] == 180.0
    if regime == "no-fault-calibration":
        assert "inject" not in calls
    else:
        timing = contract["timing"]
        assert calls["inject"]["scenario"] == contract["fault"]
        assert calls["inject"]["faultAt"] == calls["inject"]["scheduled"] == timing["faultOnsetSeconds"]
        assert calls["inject"]["hold"] == 60 and calls["inject"]["recordProbes"] is True
    assert calls["collect"][0] == {"services": ["frontend"], "windowUs": 185_000_000}      # jaeger scope is unchanged
    assert [row["services"] for row in calls["collect"][1:]] == [[s] for s in cell.APPLICATION_SERVICES
                                                                  if s != "frontend"]


def test_planted_removal_of_the_scope_declaration_collects_only_the_ten_services(monkeypatch, tree, tmp_path):
    """The runner's scope follows the epoch's declaration and nothing else (the planted change is seen)."""
    cell = load("hotel_offpath_cell_planted", tree["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
    cell.runtime.COLLECTION_EXTRA_SERVICES.clear()
    artifact = tmp_path / "campaign"
    document = helpers._admission(cell.runtime, artifact, plan_sha256=offpath.EXPECTED_PLAN_SHA256,
                                  run_count=offpath.TOTAL_RUNS, wall=offpath.MAXIMUM_WALL_SECONDS)
    contract = next(row for row in cell.runtime.cell_contracts(document)
                    if row["runId"] == "consul-pause-effect-r1-b01-full-a01")
    with monkeypatch.context() as patch:
        calls = helpers._drive_run_cell(patch, cell, contract, document, artifact, extra_services=("consul",),
                                        real_cleanup=True)
    assert calls["cpuServices"] == sorted(cell.APPLICATION_SERVICES)
    unpause = next(row["argv"] for row in calls["commands"] if "unpause" in row["argv"])
    assert unpause[unpause.index("unpause"):] == ["unpause", "search", "reservation"]


def test_campaign_cleanup_unpauses_consul_in_this_epoch(monkeypatch, tree, tmp_path):
    cell = load("hotel_offpath_cleanup_cell", tree["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
    artifact = tmp_path / "campaign"
    artifact.mkdir()
    (artifact / "materialization-proof.json").write_text(json.dumps({
        "materializedSourceSha256": "2" * 64,
        "runtimeImages": {"consul": "c", "jaeger": "j", "memcached": "m", "mongo": "o", "builder": "b"}}))
    document = helpers._admission(cell.runtime, artifact, plan_sha256=offpath.EXPECTED_PLAN_SHA256,
                                  run_count=offpath.TOTAL_RUNS, wall=offpath.MAXIMUM_WALL_SECONDS)
    recorded = []
    monkeypatch.setattr(cell, "_require_lease", lambda admission: None)
    monkeypatch.setattr(cell, "_bindings", lambda admission: (cell.ROOT, artifact))
    monkeypatch.setattr(cell, "_command", lambda arguments, **kw: recorded.append(list(arguments)) or helpers._Done("", 0))
    monkeypatch.setattr(cell.smoke, "project_resources", lambda project: {"containers": [], "networks": [], "volumes": []})
    assert cell.cleanup_campaign(document)["ownedResourcesRemaining"] == []
    unpauses = [argv[argv.index("unpause"):] for argv in recorded if "unpause" in argv]
    assert unpauses == [["unpause", "search", "reservation", "consul"]] * 30


# ---------------------------------------------------------------------------------- 6. the 3.9 floor
@pytest.mark.parametrize("relative", ["execution/candidate_offpath.py"])
def test_offpath_compiler_parses_with_the_39_grammar(relative):
    import ast
    helpers.test_changed_target_side_files_parse_with_the_39_grammar(relative)
    tree_ = ast.parse((MODULE / relative).read_text(), feature_version=(3, 9))
    assert any(isinstance(node, ast.ImportFrom) and node.module == "__future__" for node in tree_.body)


PY39 = Path("/usr/bin/python3")


@pytest.mark.skipif(not PY39.exists(), reason="no /usr/bin/python3 on this machine")
def test_offpath_compiler_runtime_and_cell_compile_identically_under_python39_isolated(tree, tmp_path):
    version = subprocess.run([str(PY39), "-c", "import sys; print(sys.version_info[:2])"],
                             capture_output=True, text=True, check=True).stdout.strip()
    if version != "(3, 9)":
        pytest.skip("/usr/bin/python3 is %s, not 3.9" % version)
    module = tree["root"] / "modules/hotel-reservation"
    program = (
        "import importlib.util,json,sys\n"
        "def load(n,p):\n"
        " s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;"
        "s.loader.exec_module(m);return m\n"
        "c=load('c',%r)\n"
        "cell=load('cell',%r)\n"
        "r=sys.modules['hotel_candidate_cell_runtime']\n"
        "p=c.compile_plan(c.load_descriptor())\n"
        "w=sys.modules['hotel_candidate_cell_witness']\n"
        "q=sys.modules['hotel_candidate_cell_resources']\n"
        "f=sys.modules['hotel_candidate_cell_faults']\n"
        "print(json.dumps([r.STUDY_EPOCH,r.CELL_COUNT,r.MAXIMUM_WALL_SECONDS,c.canonical_sha256(c.load_descriptor()),"
        "p['planCanonicalSha256'],len(r._flatten_plan()),list(cell._collection_scope('hotel-offpath-v1')),"
        "list(cell._pausable_services('hotel-offpath-v1')),list(cell._pausable_services('hotel-traffic-sweep-v1')),"
        "sorted(w.OFFPATH_PAUSE_TARGETS),list(q.scope_of(q.EXTENDED_SERVICES))==list(q.EXTENDED_SERVICES),"
        "sorted(f.pause.OFFPATH_ALLOWED)]))\n"
    ) % (str(module / "execution/candidate_offpath.py"), str(module / "execution/candidate_cell.py"))
    # -X pycache_prefix: a fresh cache, so the Apple 3.9 cache cannot serve a stale module (CLAUDE.md trap).
    result = subprocess.run([str(PY39), "-X", "pycache_prefix=" + str(tmp_path / "pyc"), "-I", "-c", program],
                            capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
    app = ["frontend", "search", "geo", "rate", "reservation", "profile", "user", "recommendation", "review",
           "attractions"]
    assert json.loads(result.stdout) == [
        OFFPATH, 30, 10800, offpath.EXPECTED_DESCRIPTOR_SHA256, offpath.EXPECTED_PLAN_SHA256, 30,
        app + ["consul"], ["search", "reservation", "consul"], ["search", "reservation"], ["consul-pause"], True,
        ["consul-pause"]]


# ------------------------------------------- 7. the image receipt the runner writes, through the validator (review B1)
def _real_image_receipt(tr, tmp_path: Path, contract: dict) -> dict:
    """candidate_cell._image_receipt with only the shell faked: `compose ps -q` answers a container id per service and
    `docker inspect` the image ID a real container reports (consul runs its own pinned image, not the application's)."""
    cell = load("hotel_offpath_image_receipt_cell", tr["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
    app_image, consul_image = "sha256:" + "3" * 64, "sha256:" + "5" * 64
    ids = {s: "%064x" % n for n, s in enumerate(cell.APPLICATION_SERVICES + ("consul",), 1)}
    by_id = {cid: s for s, cid in ids.items()}

    def command(arguments, *, environment=None, timeout=600, check=True, binary=False):
        if "ps" in arguments and "-q" in arguments:
            return helpers._Done(ids[arguments[-1]] + "\n", 0)
        service = by_id[arguments[-1]]
        return helpers._Done(json.dumps([{
            "Config": {"Labels": {"com.docker.compose.project": contract["project"]}},
            "Image": consul_image if service == "consul" else app_image}]), 0)

    cell._command = command
    source = "2" * 64
    return cell._image_receipt(
        tmp_path, contract["project"], {}, {"materializedSourceSha256": source, "runtimeInputsSha256": "1" * 64},
        {"imageId": app_image, "imageReference": "obsplacement/hotel-reservation-candidate:" + source[:16]},
        cell.APPLICATION_SERVICES + ("consul",))


def test_the_real_image_receipt_of_this_epoch_passes_the_real_validator_and_planted_ids_do_not(tree, tmp_path):
    contract = _contract(tree, tmp_path / "campaign", "consul-pause-effect", 1.0)
    receipt = _real_image_receipt(tree, tmp_path, contract)
    terminal = tree["terminal"]
    row = next(r for r in receipt["containers"] if r["service"] == "consul")
    assert row["imageId"] != receipt["applicationImageId"]          # what the host really produces
    terminal._images(receipt, contract)                              # accepted
    for planted, match in (
        ({"imageId": receipt["applicationImageId"]}, "application image provenance"),   # consul cannot be the app image
        ({"imageId": "not-an-image-id"}, "application image provenance"),
        ({"project": "other"}, "application image provenance"),
    ):
        broken = copy.deepcopy(receipt)
        next(r for r in broken["containers"] if r["service"] == "consul").update(planted)
        with pytest.raises(terminal.TerminalError, match=match):
            terminal._images(broken, contract)
    broken = copy.deepcopy(receipt)                                  # an application container on another image
    next(r for r in broken["containers"] if r["service"] == "geo")["imageId"] = "sha256:" + "6" * 64
    with pytest.raises(terminal.TerminalError, match="application image provenance"):
        terminal._images(broken, contract)
