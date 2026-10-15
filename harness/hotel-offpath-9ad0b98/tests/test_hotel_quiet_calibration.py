"""hotel-quiet-calibration-v1: the quiet calibration run (protocol decision 48), a third Hotel epoch.

Covers: the plan has exactly 40 no-fault cells, 10 per rate, and no fault regime; its order is one seeded
Fisher-Yates shuffle over all 40 cells (seed 20261004, recomputed here from the recorded encoding); every cell
has the sweep's no-fault cell shape, only the seeded onset offset differs; the descriptor differs from the
sweep's in exactly the design sections; the traffic sweep epoch is unchanged (descriptor and plan digests,
files byte-identical to ca58974, and its runtime contracts, budget, launcher and policy identical to the ones
the ca58974 runtime compiles); the committed selector activates the quiet epoch with a derived 4 h budget;
the validators accept a sealed quiet cell at every rate; one fake-driven run_cell of a quiet cell issues the
same commands as a sweep no-fault cell; and the 3.9 floor.

The quiet epoch is exercised in a copy of the module tree with its selector written into it (what the target
sees after the selector is committed); the sweep in a copy with the sweep's selector.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
from datetime import timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation"
QUIET = "hotel-quiet-calibration-v1"
SWEEP = "hotel-traffic-sweep-v1"
RATES = (10.0, 1.0, 0.2, 0.05)
SWEEP_COMMIT = "ca58974785c97fe54afe351f928c65fa46f18403"   # the harness of sweep relaunch 3 (AMENDMENT_2.md)
SWEEP_DESCRIPTOR_SHA256 = "788ff28cc44248fec518fd04e3e0f91ab6d92229888a1412a52e50f9dd889dab"
SWEEP_PLAN_SHA256 = "766063c5a0f0b90ab1aba1ada29b86e152e8ec1e7f7bd048d4c802c10b7bbc72"
# Onset-derived timing keys: the only ones in which a quiet cell may differ from the sweep's no-fault cell.
ONSET_KEYS = {"faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "tcpSnapshotOffsetsSeconds"}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


quiet = load("hotel_quiet_compiler_test", MODULE / "execution/candidate_quiet.py")
sweep = load("hotel_quiet_test_sweep_compiler", MODULE / "execution/candidate_sweep.py")
# The sweep tests' sealing and fake-driving helpers, reused so both epochs are checked by the same code.
helpers = load("hotel_quiet_test_sweep_helpers", Path(__file__).parent / "test_hotel_traffic_sweep.py")


def _tree(root: Path, epoch: str | None, *, source: Path = ROOT) -> dict:
    """A copy of the module tree (from `source`) with `epoch`'s selector written into it."""
    shutil.copytree(source / "modules/hotel-reservation", root / "modules/hotel-reservation",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "pipelines/campaigns").mkdir(parents=True)
    for path in (source / "pipelines/campaigns").glob("hotel-*.json"):
        shutil.copyfile(path, root / "pipelines/campaigns" / path.name)
    selector = root / "modules/hotel-reservation/execution/study-epoch.json"
    if epoch is not None:
        selector.write_text(json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n")
    tag = "%s_%s" % ((epoch or "frozen").replace("-", "_"), hashlib.sha256(str(root).encode()).hexdigest()[:8])
    module = root / "modules/hotel-reservation"
    loaded = {
        "root": root,
        "runtime": load("hotel_quiet_tree_runtime_" + tag, module / "execution/candidate_runtime.py"),
        "terminal": load("hotel_quiet_tree_terminal_" + tag, module / "validation/candidate_terminal.py"),
    }
    loaded["workload"] = loaded["terminal"].workload
    loaded["witness"] = loaded["terminal"].witness
    loaded["resources"] = loaded["terminal"].resources
    return loaded


@pytest.fixture(scope="module")
def quiet_tree(tmp_path_factory):
    return _tree(tmp_path_factory.mktemp("quiet-tree"), QUIET)


@pytest.fixture(scope="module")
def sweep_tree(tmp_path_factory):
    return _tree(tmp_path_factory.mktemp("sweep-tree"), SWEEP)


def _contracts(tree, artifact_root: Path, compiler) -> tuple:
    runtime = tree["runtime"]
    document = helpers._admission(
        runtime, artifact_root, plan_sha256=compiler.EXPECTED_PLAN_SHA256,
        run_count=compiler.TOTAL_RUNS, wall=compiler.MAXIMUM_WALL_SECONDS,
    )
    return document, runtime.cell_contracts(document)


# ------------------------------------------------------------------------------------ 1. the quiet plan
def test_plan_has_exactly_40_no_fault_cells_10_per_rate_and_no_fault_regime():
    descriptor = quiet.load_descriptor()
    assert quiet.canonical_sha256(descriptor) == quiet.EXPECTED_DESCRIPTOR_SHA256
    assert quiet.DEFAULT_DESCRIPTOR.read_bytes() == quiet.descriptor_bytes()   # generated, never hand-edited
    plan = quiet.compile_plan(descriptor)
    assert plan == quiet.compile_plan(copy.deepcopy(descriptor))
    assert plan["planCanonicalSha256"] == quiet.EXPECTED_PLAN_SHA256
    cells = quiet.flatten_cells(plan)
    assert plan["runCount"] == quiet.TOTAL_RUNS == len(cells) == len({c["runId"] for c in cells}) == 40
    assert "blocks" not in plan and "regimeRoots" not in plan
    # No fault anywhere: not in a cell, not in its timing, not in the declared design.
    assert {c["runKey"]["regime"] for c in cells} == {"no-fault-calibration"}
    assert all(c["fault"] is None for c in cells)
    assert all(c["timing"]["faultApplied"] is False and c["timing"]["minimumWitnessedStartsByPhase"] is None
               for c in cells)
    assert [(r["id"], r["kind"], r["fault"]) for r in descriptor["design"]["regimes"]] == [
        ("no-fault-calibration", "no-fault-calibration", None)]
    assert descriptor["design"]["faultAppliedToAnyCell"] is False
    # 10 per rate: blocks 1..10 of every rate exactly once, and 30 min of quiet measurement per rate.
    for rate in RATES:
        blocks = sorted(c["runKey"]["block"] for c in cells if c["runKey"]["requestsPerSecond"] == rate)
        assert blocks == list(range(1, 11))
        assert sum(c["timing"]["measurementSeconds"] for c in cells
                   if c["runKey"]["requestsPerSecond"] == rate) == 1800
    assert {c["runKey"]["posture"] for c in cells} == {"full"}
    assert [c["position"] for c in cells] == list(range(1, 41))
    assert all(c["artifactRoot"].startswith("calibration/") for c in cells)


def test_order_is_one_seeded_fisher_yates_shuffle_over_all_40_cells(monkeypatch):
    descriptor = quiet.load_descriptor()
    plan = quiet.compile_plan(descriptor)
    assert descriptor["schedule"]["seed"] == plan["sequence"]["seed"] == quiet.SCHEDULE_SEED == 20261004
    # Independent recomputation from the encoding recorded in the descriptor.
    cells = [(block, rate) for block in range(1, 11) for rate in RATES]
    for index in range(39, 0, -1):
        text = "20261004\0%s\0all-cells\0draw-%d\0quiet-schedule-v1" % (QUIET, index)
        other = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (index + 1)
        cells[index], cells[other] = cells[other], cells[index]
    expected = ["no-fault-calibration-r%s-b%02d-full-a01" % (quiet.rate_token(rate), block) for block, rate in cells]
    assert plan["sequence"]["order"] == descriptor["schedule"]["order"]["runIds"] == expected
    assert [c["runId"] for c in plan["sequence"]["cells"]] == expected
    assert descriptor["schedule"]["order"]["orderSha256"] == quiet.canonical_sha256(expected)
    # Not block-wise: block numbers are interleaved, so the shuffle is over all cells, not within blocks.
    assert [c["runKey"]["block"] for c in plan["sequence"]["cells"]] != sorted(
        c["runKey"]["block"] for c in plan["sequence"]["cells"])
    # Another seed gives another order: the order is the seed's.
    monkeypatch.setattr(quiet, "SCHEDULE_SEED", 1)
    assert [(row["block"], row["rate"]) for row in quiet.sequence_order()] != cells


def test_every_cell_has_the_sweep_no_fault_shape_and_only_the_seeded_onset_differs():
    sweep_cells = sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor()))
    shape = {}
    for cell in sweep_cells:
        if cell["fault"] is None:
            shape.setdefault(cell["timing"]["requestsPerSecond"], []).append(cell["timing"])
    strata: dict = {}
    for cell in quiet.flatten_cells(quiet.compile_plan(quiet.load_descriptor())):
        timing = cell["timing"]
        rate = timing["requestsPerSecond"]
        for reference in shape[rate]:
            assert set(timing) == set(reference)
            assert {k: v for k, v in timing.items() if k not in ONSET_KEYS} == {
                k: v for k, v in reference.items() if k not in ONSET_KEYS}
        offset = timing["faultOnsetPhaseOffsetSeconds"]
        onset = timing["faultOnsetSeconds"]
        assert 0 <= offset < 1 / rate and onset == round(60 + offset, 6)
        assert timing["scoredWindowSeconds"] == [onset, round(onset + 60, 6)]
        assert timing["tcpSnapshotOffsetsSeconds"] == {"pre-fault": round(onset - 15, 6),
                                                       "during-fault": round(onset + 7, 6)}
        strata.setdefault(rate, []).append(int(10 * offset / timing["interArrivalSeconds"]))
        assert cell["artifactRoot"].split("/")[:3] == ["calibration", "r" + quiet.rate_token(rate),
                                                        "b%02d" % cell["runKey"]["block"]]
    # The sweep's stratified rule with ten strata: each tenth of one inter-arrival exactly once per rate.
    assert {rate: sorted(value) for rate, value in strata.items()} == {rate: list(range(10)) for rate in RATES}


def test_descriptor_differs_from_the_sweeps_in_exactly_the_design_sections():
    mine, base = quiet.load_descriptor(), sweep.load_descriptor()
    assert {k for k in set(mine) | set(base) if mine.get(k) != base.get(k)} == {
        "id", "declaration", "design", "timing", "schedule", "analysis", "derivedFrom"}
    assert {k for k in set(mine["timing"]) | set(base["timing"])
            if mine["timing"].get(k) != base["timing"].get(k)} == {
        "leadCell", "onsetStrataPerRate", "minimumTimedSeconds", "budget"}
    assert {k for k in mine["timing"]["budget"] if mine["timing"]["budget"][k] != base["timing"]["budget"][k]} == {
        "maximumWallSeconds", "minimumFirstMutationRemainingSeconds"}
    assert mine["design"]["regimes"] == [r for r in base["design"]["regimes"] if r["id"] == "no-fault-calibration"]
    assert mine["derivedFrom"] == {"studyEpoch": SWEEP, "descriptorCanonicalSha256": SWEEP_DESCRIPTOR_SHA256,
                                   "planCanonicalSha256": SWEEP_PLAN_SHA256, "regime": "no-fault-calibration"}
    planted = copy.deepcopy(mine)
    planted["design"]["blocks"] = 9
    with pytest.raises(quiet.ProtocolError):
        quiet.validate_descriptor(planted)


def test_budget_is_derived_by_the_sweeps_rule_and_covers_the_measured_cell_period():
    assert (quiet.MAXIMUM_WALL_SECONDS, quiet.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (14400, 14100)
    assert quiet.MAXIMUM_WALL_SECONDS >= 40 * quiet.CELL_PERIOD_ESTIMATE_SECONDS + 900
    # Measured on sweep relaunch 3 (hotel-v1-20261003t134611z-db51eb9e, srv4, runtime-journal recordedAt gaps,
    # 63 intervals): median 246.5 s, maximum 261.6 s per cell. Instance-level; 40 x max + reserves fits.
    assert quiet.MAXIMUM_WALL_SECONDS >= 40 * 261.6 + 600 + 300 + 3000
    assert quiet.MINIMUM_TIMED_SECONDS == 40 * 210


# --------------------------------------------------------------------------- 2. the sweep epoch is unchanged
def test_sweep_epoch_plan_digest_is_unchanged():
    descriptor = sweep.load_descriptor()
    assert sweep.canonical_sha256(descriptor) == sweep.EXPECTED_DESCRIPTOR_SHA256 == SWEEP_DESCRIPTOR_SHA256
    plan = sweep.compile_plan(descriptor)
    assert plan["planCanonicalSha256"] == sweep.EXPECTED_PLAN_SHA256 == SWEEP_PLAN_SHA256
    assert sweep.TOTAL_RUNS == 64 and sweep.MAXIMUM_WALL_SECONDS == 21600


@pytest.mark.parametrize("relative", [
    "modules/hotel-reservation/execution/candidate_sweep.py",
    "modules/hotel-reservation/execution/candidate_pilot.py",
    "modules/hotel-reservation/execution/runtime-policy.hotel-traffic-sweep-v1.json",
    "modules/hotel-reservation/validation/protocol_gates.py",
    "modules/hotel-reservation/workload/candidate_search.py",
    "pipelines/campaigns/hotel-traffic-sweep-v1.json",
    "pipelines/campaigns/hotel-reservation-selected-v1.json",
])
def test_sweep_files_are_byte_identical_to_the_relaunch_3_harness(relative):
    # candidate_cell.py, candidate_terminal.py and candidate_evidence.py were pinned here until hotel-offpath-v1
    # (2026-10-15) edited them for its consul scope and off-path pause.  What replaces the pin is behavioural, in
    # tests/test_hotel_offpath_executor.py: the same sealed sweep cells through the ca58974 terminal and the current
    # one give byte-identical results, and the same fake-driven runs through both runners issue identical commands.
    blob = subprocess.run(["git", "-C", str(ROOT), "show", "%s:%s" % (SWEEP_COMMIT, relative)],
                          capture_output=True, check=True).stdout
    assert (ROOT / relative).read_bytes() == blob


def test_sweep_runtime_compiles_the_same_contracts_budget_launcher_and_policy_as_at_ca58974(sweep_tree, tmp_path):
    """The runtime changed (a third epoch, a `sequence` reader); under the sweep's selector nothing it emits may."""
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", SWEEP_COMMIT,
                              "modules/hotel-reservation", "pipelines/campaigns"],
                             capture_output=True, check=True).stdout
    source = tmp_path / "ca58974"
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(source, filter="data")
    assert json.loads((source / "modules/hotel-reservation/execution/study-epoch.json").read_text()) == {
        "schemaVersion": 1, "studyEpoch": SWEEP}
    old = _tree(tmp_path / "old", SWEEP, source=source)
    new = sweep_tree
    for tree in (old, new):
        assert tree["runtime"].STUDY_EPOCH == SWEEP
    old_rt, new_rt = old["runtime"], new["runtime"]
    assert (old_rt.CELL_COUNT, old_rt.MAXIMUM_WALL_SECONDS, old_rt.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (
        new_rt.CELL_COUNT, new_rt.MAXIMUM_WALL_SECONDS, new_rt.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS)
    assert old_rt.CONTROLLER_PATHS == new_rt.CONTROLLER_PATHS
    assert old_rt.REMOTE_DETACHED_LAUNCH == new_rt.REMOTE_DETACHED_LAUNCH
    assert old_rt._validate_policy(old_rt._json_file(old_rt.POLICY, "p")) == new_rt._validate_policy(
        new_rt._json_file(new_rt.POLICY, "p"))
    artifact = tmp_path / "campaign"
    _, before = _contracts(old, artifact, sweep)
    _, after = _contracts(new, artifact, sweep)
    assert len(after) == 64
    assert new_rt.canonical_bytes(before) == new_rt.canonical_bytes(after)
    # Every controller the sweep binds hashes as it did at ca58974, except those later epochs edited: the runtime
    # (further epochs, `sequence` reader; its sweep output is compared above), the committed selector, and the
    # executor files hotel-offpath-v1 changed (consul scope, off-path pause); those are compared by behaviour in
    # tests/test_hotel_offpath_executor.py (same sealed cells, same commands as ca58974).
    changed = {"candidate-runtime", "study-epoch-selector", "candidate-cell-runner", "candidate-terminal",
               "candidate-witness", "candidate-resources", "fault-adapter", "fault-adapter-lmt"}
    for name, relative in new_rt.CONTROLLER_PATHS.items():
        if name not in changed:
            assert (source / relative).read_bytes() == (ROOT / relative).read_bytes(), name


# ------------------------------------------------------------------------- 3. the committed selector activates
def test_the_quiet_epoch_is_registered_and_the_committed_selector_names_a_declared_epoch():
    """The selector named the quiet epoch from 2026-10-04 until hotel-offpath-v1 was activated (2026-10-15); the quiet
    epoch itself is selected in a tree copy by the tests below."""
    selector = json.loads((MODULE / "execution/study-epoch.json").read_text())
    runtime = load("hotel_quiet_selector_runtime", MODULE / "execution/candidate_runtime.py")
    assert selector["studyEpoch"] in runtime.EPOCH_CONTROLLER_PATHS and QUIET in runtime.EPOCH_CONTROLLER_PATHS


def test_the_selector_activates_the_quiet_epoch_with_a_derived_budget(quiet_tree, tmp_path):
    runtime = quiet_tree["runtime"]
    assert runtime.STUDY_EPOCH == QUIET and runtime.CELL_COUNT == 40
    assert (runtime.MAXIMUM_WALL_SECONDS, runtime.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (14400, 14100)
    policy = runtime._validate_policy(runtime._json_file(runtime.POLICY, "policy"))
    sweep_policy = json.loads((MODULE / "execution/runtime-policy.hotel-traffic-sweep-v1.json").read_text())
    assert list(policy) == list(sweep_policy)
    assert {key for key in policy if policy[key] != sweep_policy[key]} == {
        "studyEpoch", "maximumCells", "maximumWallSeconds", "minimumFirstMutationRemainingSeconds"}
    paths = runtime.CONTROLLER_PATHS
    assert paths["candidate-compiler"].endswith("candidate_quiet.py")
    assert paths["sweep-compiler"].endswith("candidate_sweep.py")
    assert len(set(paths.values())) == len(paths)            # the install manifest needs distinct paths
    for name in ("sweep-compiler", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector"):
        assert (quiet_tree["root"] / paths[name]).is_file()
    document, contracts = _contracts(quiet_tree, tmp_path / "campaign", quiet)
    assert len(contracts) == 40 and [row["ordinal"] for row in contracts] == list(range(1, 41))
    assert runtime.frozen_cell_contracts(document) == contracts
    assert [row["runId"] for row in contracts] == quiet.compile_plan(quiet.load_descriptor())["sequence"]["order"]
    assert all(row["fault"] is None and set(row["timing"]) == runtime.CELL_TIMING_KEYS for row in contracts)
    assert all(row["studyEpoch"] == QUIET for row in contracts)
    for row in contracts:
        assert runtime.cell_timing(row) == row["timing"]
    planted = copy.deepcopy(contracts[3])
    planted["timing"]["faultOnsetSeconds"] += 1
    with pytest.raises(runtime.GateError, match="not the active compiled plan"):
        runtime.cell_timing(planted)
    launcher = runtime.REMOTE_DETACHED_LAUNCH
    compile(launcher, "quiet-launcher", "exec")
    assert 'binding.get("maximumWallSeconds")!=14400' in launcher
    assert "remaining < 14100 or remaining > 14405" in launcher
    assert "21600" not in launcher and "17700" not in launcher
    runtime.validate_embedded_remote_programs()
    text = runtime.expected_gate_run_text({**document["bindings"], "frameworkCommit": "a" * 40,
                                           "readinessCaptureId": "x", "readinessObservedAt": "y",
                                           "transportUser": "root", "setupUser": "root",
                                           "executionUser": "fhuebscher", "executionUid": 1007,
                                           "executionGid": 1007, "dockerGid": 998})
    assert f"study={QUIET} " in text and "cells=40 " in text and "wallSeconds=14400 " in text


def test_driver_config_reads_the_quiet_epoch_and_a_4_hour_window(quiet_tree, sweep_tree):
    pytest.importorskip("obsplacement.gate_driver.contract")
    config = load("hotel_quiet_driver_config_test", MODULE / "drivers/gate_driver_config.py")
    assert config._active_epoch(quiet_tree["root"]) == (QUIET, 4)
    assert config._active_epoch(sweep_tree["root"]) == (SWEEP, 6)
    # The launcher's watcher cap is run_window_hours + 1 = 5 h > the 4 h wall budget.
    assert (4 + 1) * 3600 > quiet.MAXIMUM_WALL_SECONDS


@pytest.mark.parametrize("rate", RATES)
def test_workload_accepts_quiet_run_ids_up_to_block_10(quiet_tree, rate):
    work = quiet_tree["workload"]
    run_id = "no-fault-calibration-r%s-b10-full-a01" % quiet.rate_token(rate)
    plan = work.build_plan(run_id, quiet.EXPECTED_PLAN_SHA256, helpers.BARRIER_AT, helpers.BARRIER,
                           rate=rate, duration_seconds=180.0,
                           created_at=helpers.BARRIER_AT - timedelta(minutes=1))
    assert plan["offered"] == round(rate * 180) and plan["rate"] == rate


# --------------------------------------------------------------------------- 4. sealed quiet cells
def _quiet_contract(tree, campaign: Path, rate: float, block: int = 10) -> dict:
    _, contracts = _contracts(tree, campaign, quiet)
    run_id = "no-fault-calibration-r%s-b%02d-full-a01" % (quiet.rate_token(rate), block)
    return next(row for row in contracts if row["runId"] == run_id)


@pytest.mark.parametrize("rate", RATES)
def test_validator_accepts_a_sealed_quiet_cell_at_every_rate(quiet_tree, tmp_path, rate):
    contract = _quiet_contract(quiet_tree, tmp_path / "campaign", rate)
    root = Path(contract["runtimeArtifactRoot"])
    helpers._seal_sweep_cell(quiet_tree, root, contract)
    result = quiet_tree["terminal"].validate_cell(root, contract)
    assert result["candidateCellValid"] is True
    assert result["opportunities"]["offered"] == round(rate * 180)
    gates = {row["gate"]: row["verdict"] for row in result["protocolGates"]["verdicts"]}
    assert result["protocolGates"]["blocking"] == ["G1", "G2", "G4"]
    assert {gate: gates[gate] for gate in ("G1", "G2", "G4")} == {"G1": "pass", "G2": "pass", "G4": "pass"}
    assert result["system"]["systemSamples"] == 37
    correlation = json.loads((root / "correlation.json").read_text())
    assert set(correlation["traceCompleteness"]["windows"]) == {"measurement"}   # decision 25, no-fault form


@pytest.mark.parametrize("rate", [10.0, 0.05])
def test_validator_rejects_a_quiet_cell_with_one_request_missing(quiet_tree, tmp_path, rate):
    contract = _quiet_contract(quiet_tree, tmp_path / "campaign", rate)
    root = Path(contract["runtimeArtifactRoot"])
    helpers._seal_sweep_cell(quiet_tree, root, contract, drop_last_request=True)
    with pytest.raises(ValueError, match="row count differs from offered denominator"):
        quiet_tree["terminal"].validate_cell(root, contract)


def test_a_sweep_cell_is_not_a_quiet_cell(quiet_tree, sweep_tree, tmp_path):
    """A sweep contract cannot be validated under the quiet epoch: its timing is not the active plan's."""
    _, contracts = _contracts(sweep_tree, tmp_path / "s", sweep)
    contract = next(row for row in contracts if row["runId"] == "no-fault-calibration-r1-b01-full-a01")
    with pytest.raises(quiet_tree["runtime"].GateError, match="not the active compiled plan"):
        quiet_tree["runtime"].cell_timing(contract)


# ------------------------------------------------------------- 5. one fake-driven execution of the cell runner
def test_run_cell_drives_a_quiet_cell_exactly_like_a_sweep_no_fault_cell(monkeypatch, quiet_tree, sweep_tree,
                                                                          tmp_path):
    seen = {}
    for name, tree, compiler, run_id in (
        ("sweep", sweep_tree, sweep, "no-fault-calibration-r0p05-b01-full-a01"),
        ("quiet", quiet_tree, quiet, "no-fault-calibration-r0p05-b10-full-a01"),
    ):
        cell = load("hotel_quiet_test_cell_" + name,
                    tree["root"] / "modules/hotel-reservation/execution/candidate_cell.py")
        artifact = tmp_path / name
        document = helpers._admission(cell.runtime, artifact, plan_sha256=compiler.EXPECTED_PLAN_SHA256,
                                      run_count=compiler.TOTAL_RUNS, wall=compiler.MAXIMUM_WALL_SECONDS)
        contract = next(row for row in cell.runtime.cell_contracts(document) if row["runId"] == run_id)
        with monkeypatch.context() as patch:
            calls = helpers._drive_run_cell(patch, cell, contract, document, artifact)
        assert "inject" not in calls                        # no fault command in a no-fault cell
        assert helpers._warmup(calls) == {"--rate": "10", "--duration": "30", "--concurrency": "16",
                                          "timeout": 90.0}
        assert calls["execute"] == {"concurrency": 16, "timeout": 1.0, "offered": 9, "rate": 0.05,
                                    "duration": 180.0}
        assert calls["collect"][0] == {"services": ["frontend"], "windowUs": 185_000_000}
        assert "--timestamps" in helpers._logs_argv(calls) and "jaeger-raw-remainder.json" in calls["files"]
        assert calls["correlate"]["timing"] == contract["timing"]
        seen[name] = calls
    def comparable(calls, root):
        # The compose overlay argument is `<tree root>/modules/...`; the two trees are two temp directories, so the
        # root is normalised (before this, the argv comparison failed on the directory name alone, at e9d35f7).
        commands = [
            [arg.replace(str(root), "<tree>") for arg in row["argv"] if "hotel_candidate_v4_" not in arg
             and "/campaign" not in arg and "/sweep/" not in arg and "/quiet/" not in arg]
            for row in calls["commands"]]
        keep = ("execute", "collect", "tcp", "emissionWindowNs", "cpu", "samplerJoin", "files")
        return commands, {key: calls.get(key) for key in keep}
    assert comparable(seen["quiet"], quiet_tree["root"]) == comparable(seen["sweep"], sweep_tree["root"])


# ---------------------------------------------------------------------------------- 6. the 3.9 floor
def test_quiet_compiler_parses_with_the_39_grammar():
    helpers.test_changed_target_side_files_parse_with_the_39_grammar("execution/candidate_quiet.py")
    helpers.test_changed_target_side_files_parse_with_the_39_grammar("execution/candidate_runtime.py")
    tree_ = ast.parse((MODULE / "execution/candidate_quiet.py").read_text(), feature_version=(3, 9))
    assert any(isinstance(node, ast.ImportFrom) and node.module == "__future__" for node in tree_.body)


PY39 = Path("/usr/bin/python3")


@pytest.mark.skipif(not PY39.exists(), reason="no /usr/bin/python3 on this machine")
def test_quiet_compiler_and_runtime_compile_identically_under_python39_isolated(quiet_tree, tmp_path):
    version = subprocess.run([str(PY39), "-c", "import sys; print(sys.version_info[:2])"],
                             capture_output=True, text=True, check=True).stdout.strip()
    if version != "(3, 9)":
        pytest.skip("/usr/bin/python3 is %s, not 3.9" % version)
    module = quiet_tree["root"] / "modules/hotel-reservation"
    program = (
        "import importlib.util,json,sys\n"
        "def load(n,p):\n"
        " s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;"
        "s.loader.exec_module(m);return m\n"
        "c=load('c',%r)\n"
        "load('cell',%r)\n"
        "r=sys.modules['hotel_candidate_cell_runtime']\n"
        "p=c.compile_plan(c.load_descriptor())\n"
        "s=c.sweep.compile_plan(c.sweep.load_descriptor())\n"
        "print(json.dumps([r.STUDY_EPOCH,r.CELL_COUNT,r.MAXIMUM_WALL_SECONDS,c.canonical_sha256(c.load_descriptor()),"
        "p['planCanonicalSha256'],s['planCanonicalSha256'],len(r._flatten_plan())]))\n"
    ) % (str(module / "execution/candidate_quiet.py"), str(module / "execution/candidate_cell.py"))
    # -X pycache_prefix: a fresh cache, so the Apple 3.9 cache cannot serve a stale module (CLAUDE.md trap).
    result = subprocess.run([str(PY39), "-X", "pycache_prefix=" + str(tmp_path / "pyc"), "-I", "-c", program],
                            capture_output=True, text=True, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [QUIET, 40, 14400, quiet.EXPECTED_DESCRIPTOR_SHA256,
                                         quiet.EXPECTED_PLAN_SHA256, SWEEP_PLAN_SHA256, 40]
