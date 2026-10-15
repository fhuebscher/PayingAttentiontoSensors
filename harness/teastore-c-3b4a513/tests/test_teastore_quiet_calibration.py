"""teastore-quiet-calibration-v1: 40 no-fault cells, each the traffic sweep's no-fault cell (protocol decision 48).

Covers: the 40-cell plan (10 blocks x 4 rates, no fault regime) is deterministic and pinned; the per-block order is
recomputed independently from the recorded encoding; the shuffle and onset rules reproduce the sweep's own when given
the sweep's values; every cell equals the sweep's no-fault cell at its rate apart from the pseudo-window onset (each
tenth stratum once per rate); the budget is the sweep's rule over 40 cells and covers the measured relaunch-2 periods;
the sweep epoch is byte-identical to 0588a41 and, under the sweep selector, the runtime emits the 0588a41 runtime's
epoch, controller set, campaign, plan and contracts; the quiet selector activates the epoch in every runtime file;
materialize -> inspect -> contracts -> package -> producer contract check for all 40 cells; a fake-driven runtime slice
of a quiet cell issues the sweep's no-fault commands; sealed quiet cells validate at every rate and the 40-cell
campaign replays its own allocation; the 3.9 floor and digest identity.

Like tests/test_teastore_traffic_sweep.py (whose fixtures this file reuses), every epoch is exercised in a copy of the
module tree with its own selector, so these tests do not depend on which selector the worktree has committed.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import shutil
import io
import subprocess
import tarfile
import types
from pathlib import Path

import pytest

import test_teastore_traffic_sweep as sw


ROOT = sw.ROOT
MODULE = sw.MODULE
SWEEP = sw.SWEEP
QUIET = "teastore-quiet-calibration-v1"
RATES = sw.RATES
SWEEP_COMMIT = "0588a412ea7355f0aaa143b5468e8c4b9b7f0943"      # sweep relaunch 2's harness
SWEEP_DESCRIPTOR_SHA256 = "f90bd64c13075c3019c03c4aee4df3744bb1494b194645b17d246bea063b160a"
SWEEP_PLAN_SHA256 = "88a3017a781233a4848f7ea638b4763f82f63bc902d848514cd8ae5089529355"
QUIET_SELECTOR = {"schemaVersion": 1, "studyEpoch": QUIET}
SWEEP_SELECTOR = {"schemaVersion": 1, "studyEpoch": SWEEP}
# Files this build changed relative to 0588a41; every other harness file must be byte-identical.
CHANGED_SHARED_FILES = {
    "modules/teastore/execution/study_epoch.py",
    "modules/teastore/execution/candidate_runtime_adapter.py",
    "modules/teastore/extension-ledger.yaml",
    "modules/teastore/execution/study-epoch.json",          # the activation commit points it at the quiet epoch
    # Campaign B (teastore-traffic-sweep-b-v1, 2026-10-09) moved these two for its H10/H4 records; their sweep and quiet
    # behaviour is pinned against 91c4967 in tests/test_teastore_sweep_b.py (receipts and validator verdicts equal).
    "modules/teastore/execution/performance_campaign.py",
    "modules/teastore/validation/candidate_pilot.py",
}
QUIET_TARGET_FILES = ("execution/candidate_quiet.py", "execution/study_epoch.py", "execution/candidate_runtime_adapter.py")

quiet = sw.load("teastore_quiet_compiler_test", MODULE / "execution/candidate_quiet.py")
sweep = sw.sweep


def _tree(root: Path) -> dict:
    module = root / "modules/teastore"
    tag = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    loaded = {"root": root}
    for key, relative in (
        ("epoch", "execution/study_epoch.py"),
        ("compiler", "execution/candidate_quiet.py"),
        ("adapter", "execution/candidate_runtime_adapter.py"),
        ("orchestrator", "execution/candidate_orchestrator.py"),
        ("transport", "execution/candidate_transport.py"),
        ("controller", "execution/candidate_remote_controller.py"),
        ("producer", "execution/performance_campaign.py"),
        ("validator", "validation/candidate_pilot.py"),
        ("terminal", "validation/candidate_terminal.py"),
        ("readiness", "validation/candidate_readiness.py"),
        ("witness", "witness/extract_app_witness.py"),
        ("native_token", "witness/extract_native_token_correlation.py"),
        ("kieker", "collectors/kieker_native.py"),
        ("fixed_load", "workload/fixed_load.py"),
        ("gates", "validation/protocol_gates.py"),
    ):
        if (module / relative).is_file():
            loaded[key] = sw.load(f"teastore_quiet_tree_{key}_{tag}", module / relative)
    return loaded


@pytest.fixture(scope="module")
def qtree(tmp_path_factory):
    """Modules loaded from a tree copy whose selector names the quiet calibration."""
    return _tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-quiet-tree"), QUIET_SELECTOR))


@pytest.fixture(scope="module")
def stree(tmp_path_factory):
    """Modules loaded from a tree copy of this commit whose selector names the sweep."""
    return _tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-sweep-tree-now"), SWEEP_SELECTOR))


def _base_tree(destination: Path) -> Path:
    """The same subset of the tree as sw._copy_tree, taken from the sweep relaunch-2 commit (selector: the sweep)."""
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", SWEEP_COMMIT, "modules/teastore", "pipelines/campaigns",
         "src/obsplacement/__init__.py", "src/obsplacement/selection.py"],
        capture_output=True, check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        handle.extractall(destination, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    for path in (destination / "pipelines/campaigns").glob("*.json"):
        if not path.name.startswith("teastore-"):
            path.unlink()
    selector = destination / "modules/teastore/execution/study-epoch.json"
    assert json.loads(selector.read_text()) == SWEEP_SELECTOR
    return destination


@pytest.fixture(scope="module")
def btree(tmp_path_factory):
    """Modules loaded from the 0588a41 tree (the sweep's harness), selector: the sweep."""
    return _tree(_base_tree(tmp_path_factory.mktemp("teastore-sweep-tree-0588a41")))


def _plan() -> dict:
    return quiet.compile_plan(quiet.load_descriptor())


def _cells() -> list:
    return quiet.flatten_cells(_plan())


def _quiet_cell(rate: float, block: int = None) -> dict:
    return next(cell for cell in _cells() if cell["timing"]["journeysPerSecond"] == rate
                and (block is None or cell["runKey"]["block"] == block))


# ------------------------------------------------------------------------------------------ 1. the quiet plan
def test_quiet_plan_is_40_no_fault_cells_10_per_rate_deterministic_and_pinned():
    descriptor = quiet.load_descriptor()
    assert quiet.canonical_sha256(descriptor) == quiet.EXPECTED_DESCRIPTOR_SHA256
    # The checked-in descriptor is the generator's output, byte for byte (regenerate, never hand-edit).
    assert quiet.DEFAULT_DESCRIPTOR.read_bytes() == quiet.descriptor_bytes()
    first, second = quiet.compile_plan(descriptor), quiet.compile_plan(copy.deepcopy(descriptor))
    assert first == second and quiet.canonical_sha256(first) == quiet.EXPECTED_PLAN_SHA256
    assert quiet.validate_plan(descriptor, first) is first
    cells = quiet.flatten_cells(first)
    assert len(cells) == first["runCount"] == quiet.TOTAL_RUNS == 40
    assert len({cell["runId"] for cell in cells}) == 40
    assert {cell["runKey"]["regime"] for cell in cells} == {"no-fault-cost"}
    assert all(cell["fault"] is None and cell["timing"]["faultApplied"] is False and cell["timing"]["fault"] is None
               for cell in cells)
    by_rate = {rate: [cell for cell in cells if cell["timing"]["journeysPerSecond"] == rate] for rate in RATES}
    assert {rate: len(rows) for rate, rows in by_rate.items()} == {rate: 10 for rate in RATES}
    assert [block["block"] for block in first["blocks"]] == list(range(1, 11))
    for block in first["blocks"]:
        assert sorted(cell["timing"]["journeysPerSecond"] for cell in block["cells"]) == sorted(RATES)
        assert [cell["ordinalPosition"] for cell in block["cells"]] == [1, 2, 3, 4]
        assert {cell["runKey"]["block"] for cell in block["cells"]} == {block["block"]}
        assert block["order"] == [cell["runId"] for cell in block["cells"]]
    assert {cell["runKey"]["posture"] for cell in cells} == {"full"}
    assert all(cell["runId"] == quiet.run_id_for("no-fault-cost", cell["timing"]["journeysPerSecond"],
                                                 cell["runKey"]["block"], "full") for cell in cells)
    assert all(cell["runId"].startswith(QUIET + "/no-fault-cost/r") for cell in cells)
    sweep_run_ids = {cell["runId"] for cell in sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor()))}
    assert not sweep_run_ids & {cell["runId"] for cell in cells}
    assert len({cell["artifactRoot"] for cell in cells}) == 40
    # The sweep's plan schema: frozen top-level keys, cells in blocks, one regime in the allocation.
    assert set(first) == set(sweep.compile_plan(sweep.load_descriptor()))
    assert "regimeRoots" not in first and set(first["scheduleAllocation"]) == {"no-fault-cost"}
    assert first["scheduleAllocation"]["no-fault-cost"]["blocks"] == [["full"] * 4] * 10
    assert descriptor["schedule"]["seed"] == quiet.SCHEDULE_SEED == 20261004
    assert descriptor["schedule"]["leadCell"] is None and descriptor["design"]["faultAppliedToAnyCell"] is False
    assert descriptor["design"]["quietSecondsPerRate"] == 1800


def _independent_order(seed, epoch: str, block: int, context: str, pairs: list) -> list:
    """Fisher-Yates with SHA-256 draws, written from the descriptor's drawEncoding text, not from the compiler."""
    pairs = list(pairs)
    for index in range(len(pairs) - 1, 0, -1):
        material = "\0".join([str(seed), epoch, "block-%02d" % block, "draw-%d" % index, context])
        other = int(hashlib.sha256(material.encode("utf-8")).hexdigest(), 16) % (index + 1)
        pairs[index], pairs[other] = pairs[other], pairs[index]
    return pairs


def test_the_order_is_recomputed_from_the_recorded_encoding(monkeypatch):
    descriptor = quiet.load_descriptor()
    schedule = descriptor["schedule"]
    assert schedule["drawEncoding"] == "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)"
    assert schedule["version"] == "quiet-schedule-v1"
    plan = quiet.compile_plan(descriptor)
    for receipt, block in zip(schedule["blocks"], plan["blocks"]):
        order = _independent_order(schedule["seed"], QUIET, receipt["block"], schedule["version"], list(RATES))
        expected = [quiet.run_id_for("no-fault-cost", rate, receipt["block"], "full") for rate in order]
        assert receipt["runIds"] == expected == block["order"]
        assert receipt["orderSha256"] == quiet.canonical_sha256(expected) == block["orderSha256"]
    orders = [tuple(cell["timing"]["journeysPerSecond"] for cell in block["cells"]) for block in plan["blocks"]]
    assert len(set(orders)) > 1                                  # not one order repeated in every block
    monkeypatch.setattr(quiet, "SCHEDULE_SEED", quiet.SCHEDULE_SEED + 1)
    assert [tuple(row["rate"] for row in quiet.block_order(block)) for block in range(1, 11)] != orders


def test_the_shuffle_and_onset_rules_reproduce_the_sweeps_with_the_sweeps_values():
    pairs = [{"regime": regime, "rate": float(rate)} for regime in sweep.REGIMES for rate in sweep.RATES]
    shuffled = quiet.fisher_yates(pairs, sweep.SCHEDULE_SEED, sweep.EPOCH, 1, sweep.SCHEDULE_CONTEXT)
    lead = [row for row in shuffled if (row["regime"], row["rate"]) == sweep.LEAD_CELL]
    assert lead + [row for row in shuffled if row is not lead[0]] == sweep.block_order(1)
    for cell in sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor())):
        rate = cell["timing"]["journeysPerSecond"]
        assert quiet.stratified_onset_offset(
            sweep.SCHEDULE_SEED, sweep.EPOCH, sweep.EPISODES, cell["runId"], cell["runKey"]["regime"], rate, 1,
        ) == sweep.onset_phase_offset(cell["runId"], rate) == cell["timing"]["faultOnsetPhaseOffsetSeconds"]


def test_every_cell_is_the_sweeps_no_fault_cell_but_for_the_pseudo_window_onset():
    strata = {rate: [] for rate in RATES}
    for cell in _cells():
        timing, rate = cell["timing"], cell["timing"]["journeysPerSecond"]
        base = sweep.cell_timing(sweep.run_id_for("no-fault-cost", rate, 1, "full"), "no-fault-cost", rate)
        assert set(timing) == set(base)
        assert {key for key in timing if timing[key] != base[key]} <= quiet.OWN_TIMING_KEYS
        assert {key: timing[key] for key in base if key not in quiet.OWN_TIMING_KEYS} == {
            key: base[key] for key in base if key not in quiet.OWN_TIMING_KEYS}
        offset = timing["faultOnsetPhaseOffsetSeconds"]
        assert timing["faultOnsetSeconds"] == round(60 + offset, 6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"], round(timing["faultOnsetSeconds"] + 60, 6)]
        assert 0.0 <= offset < 1.0 / rate
        strata[rate].append(int(offset * rate * 10))
        # The sweep's cell shape, spelled out once.
        assert (timing["concurrency"], timing["requestTimeoutSeconds"], timing["warmupSeconds"],
                timing["warmupJourneysPerSecond"], timing["measurementSeconds"], timing["faultHoldSeconds"]) == (
            240, 15.0, 30, 10.0, 180, 60)
        assert timing["offered"] == {10.0: 1800, 1.0: 180, 0.2: 36, 0.05: 9}[rate]
        assert timing["journeyKind"] == "login-only" and timing["workloadId"] == "login-only-v1"
        assert timing["drainAllowanceSeconds"] is None and timing["minimumActualStartsByPhase"] is None
        assert timing["systemSampleCount"] == 37 and timing["protocolGates"] == ["F1", "G1", "G2", "G4"]
    assert {rate: sorted(values) for rate, values in strata.items()} == {rate: list(range(10)) for rate in RATES}


def test_the_descriptor_differs_from_the_sweeps_only_where_the_epoch_differs():
    descriptor, base = quiet.load_descriptor(), sweep.load_descriptor()
    changed = {key for key in set(descriptor) | set(base) if descriptor.get(key) != base.get(key)}
    assert changed == {"id", "declaration", "design", "timing", "schedule", "outcomes", "analysis", "continuation",
                       "protocolGates", "derivedFrom"}
    assert descriptor["declaration"].startswith("research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md ")
    assert descriptor["derivedFrom"]["descriptorCanonicalSha256"] == SWEEP_DESCRIPTOR_SHA256
    assert descriptor["derivedFrom"]["planCanonicalSha256"] == SWEEP_PLAN_SHA256
    assert descriptor["derivedFrom"]["descriptorByteSha256"] == hashlib.sha256(
        (ROOT / sweep.DESCRIPTOR_RELATIVE).read_bytes()).hexdigest()
    timing_changed = {key for key in descriptor["timing"] if descriptor["timing"][key] != base["timing"].get(key)}
    assert timing_changed == {"leadCell", "faultOnsetStrata", "minimumTimedSeconds", "operationalEstimateSeconds",
                              "budget"}
    assert descriptor["protocolGates"]["blocking"] == ["G1", "G2", "G4"]
    assert {key: value for key, value in descriptor["protocolGates"].items() if key not in ("blocking", "blockingNote")} \
        == {key: value for key, value in base["protocolGates"].items() if key != "blocking"}


def test_budget_is_the_sweeps_rule_over_40_cells_and_covers_the_measured_periods():
    assert quiet.CELL_PERIOD_ESTIMATE_SECONDS == sweep.CELL_PERIOD_ESTIMATE_SECONDS == 30 + 15 + 180 + 300
    assert quiet.MINIMUM_TIMED_SECONDS == 40 * (30 + 180) == 8_400
    assert quiet.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS == 40 * 525 + 300 == 21_300
    assert quiet.RUN_WINDOW_HOURS == 7 and quiet.MAXIMUM_WALL_SECONDS == 25_200
    assert quiet.RUN_WINDOW_HOURS * 3600 >= quiet.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + quiet.PREPARE_RESERVE_SECONDS
    assert (quiet.RUN_WINDOW_HOURS - 1) * 3600 < (
        quiet.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + quiet.PREPARE_RESERVE_SECONDS)
    measured = quiet.MEASURED_CELL_PERIOD_SECONDS
    assert measured["minimum"] <= measured["median"] <= measured["maximum"] < quiet.CELL_PERIOD_ESTIMATE_SECONDS
    # Even at the slowest measured period every cell starts well before the deadline's cleanup reserve.
    assert quiet.TOTAL_RUNS * measured["maximum"] + quiet.PREPARE_RESERVE_SECONDS < (
        quiet.MAXIMUM_WALL_SECONDS - quiet.CLEANUP_RESERVE_SECONDS)
    plan = _plan()
    assert (plan["runWindowHours"], plan["maximumWallSeconds"], plan["minimumFirstMutationRemainingSeconds"]) == (
        7, 25_200, 21_300)


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_plan_digest_is_identical_under_python39(tmp_path):
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I",
         str(MODULE / "execution/candidate_quiet.py")],
        capture_output=True, text=True, check=True,
    )
    report = json.loads(result.stdout)
    assert report["planCanonicalSha256"] == quiet.EXPECTED_PLAN_SHA256
    assert report["descriptorCanonicalSha256"] == quiet.EXPECTED_DESCRIPTOR_SHA256
    assert report["runCount"] == 40 and report["runWindowHours"] == 7


# ------------------------------------------------------------------------------ 2. the sweep epoch unchanged
def _changed_since_sweep() -> set:
    listing = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", SWEEP_COMMIT, "--",
                              "modules/teastore", "pipelines/campaigns"],
                             capture_output=True, text=True, check=True).stdout.split()
    untracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard", "--",
                                "modules/teastore", "pipelines/campaigns"],
                               capture_output=True, text=True, check=True).stdout.split()
    return set(listing) | set(untracked)


def test_the_sweep_epoch_is_byte_identical_and_its_digests_unchanged():
    added = {"modules/teastore/execution/candidate_quiet.py", "pipelines/campaigns/teastore-quiet-calibration-v1.json",
             "modules/teastore/execution/candidate_sweep_b.py", "pipelines/campaigns/teastore-traffic-sweep-b-v1.json",
             # campaign C (teastore-traffic-sweep-c-v1, 2026-10-10)
             "modules/teastore/execution/candidate_sweep_c.py", "pipelines/campaigns/teastore-traffic-sweep-c-v1.json"}
    assert _changed_since_sweep() <= CHANGED_SHARED_FILES | added
    for relative in ("modules/teastore/execution/candidate_sweep.py", sweep.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_pilot.py",
                     "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json",
                     "modules/teastore/validation/protocol_gates.py",
                     "modules/teastore/validation/secret_scan.py"):
        assert (ROOT / relative).read_bytes() == subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{SWEEP_COMMIT}:{relative}"], capture_output=True, check=True,
        ).stdout, relative
    assert sweep.EXPECTED_DESCRIPTOR_SHA256 == SWEEP_DESCRIPTOR_SHA256
    assert sweep.EXPECTED_PLAN_SHA256 == SWEEP_PLAN_SHA256
    assert sweep.canonical_sha256(sweep.compile_plan(sweep.load_descriptor())) == SWEEP_PLAN_SHA256


def _contracts(tree, tmp_path: Path, campaign_id: str, monkeypatch) -> tuple:
    adapter = tree["adapter"]
    monkeypatch.setattr(adapter, "_git_repository_state", sw._git_state(adapter))
    campaign_root = tmp_path / "campaign"
    materialized = tree["orchestrator"].materialize_campaign(campaign_root)
    bindings = adapter.inspect_campaign(campaign_root, sw.FRAMEWORK_COMMIT)
    images = {service: f"repo/{service}@sha256:{index:064x}"
              for index, service in enumerate(adapter.IMAGE_SERVICES, 1)}
    release = {"gateSetupSha256": "1" * 64, "releaseManifestSha256": "2" * 64, "bundleSha256": "3" * 64}
    authorization = {
        "campaignId": campaign_id, "transportUser": "root", "executionUser": "stig", "executionUid": 1015,
        "executionGid": 1015, "executionMethod": "runuser",
        "releaseRoot": "/home/stig/.local/share/observability-placement/candidate-v4/teastore/releases/"
                       + "0" * 32 + "-" + "a" * 12 + "-" + "3" * 16,
        "resultsRoot": "/home/stig/.local/share/observability-placement/candidate-v4/teastore/results/" + "0" * 32,
        "exclusiveLeasePath": adapter.LEASE_PATH, "setupId": "0" * 32,
        "gateSetupSha256": "1" * 64, "releaseManifestSha256": "2" * 64, "bundleSha256": "3" * 64,
        "releaseInstalledAt": "2026-10-04T00:00:00Z", "notBefore": "2026-10-04T00:00:00Z",
        "authorizationDeadline": "2026-10-04T07:00:00Z", "cleanupReserveSeconds": 300,
        "authorizedRunIds": list(bindings.run_ids),
    }
    package = types.SimpleNamespace(
        bindings=bindings, gate_run={"authorization": authorization},
        gate_plan_sha256="4" * 64, readiness_sha256="5" * 64, gate_run_sha256="6" * 64,
        readiness={"imageDigests": images, "transport": {"implementationSha256": "7" * 64},
                   "release": release, "ingressArchiveSha256": "8" * 64,
                   "runtimePreflight": {"capturedAt": "2026-10-04T00:00:00Z"}},
    )
    contracts = [adapter.build_cell_contract(package, cell) for cell in bindings.cells]
    return materialized, bindings, package, contracts


def _mask_moved_digests(value, moved: set):
    """Drop the controller digests of the files this build changed (their bytes moved by construction)."""
    value = copy.deepcopy(value)

    def walk(node):
        if isinstance(node, dict):
            for key, child in list(node.items()):
                if key == "controllerDigests" and isinstance(child, dict):
                    for name in moved:
                        child.pop(name, None)
                else:
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(value)
    return value


def test_under_the_sweep_selector_the_runtime_is_the_0588a41_runtime(stree, btree, tmp_path, monkeypatch):
    now, base = stree, btree
    assert now["epoch"].active(now["root"]) == base["epoch"].active(base["root"])
    assert now["epoch"].sweep_compiler(now["root"]).EPOCH == SWEEP
    assert now["adapter"].CONTROLLER_PATHS == base["adapter"].CONTROLLER_PATHS
    for name in ("STUDY_EPOCH", "RUN_COUNT", "MINIMUM_FIRST_MUTATION_REMAINING_SECONDS", "OUTER_LEASE_SCOPE",
                 "COMMON_ARTIFACTS"):
        assert getattr(now["adapter"], name) == getattr(base["adapter"], name), name
    assert now["readiness"].SEAM_EXPECTED_VALUES == base["readiness"].SEAM_EXPECTED_VALUES
    a = _contracts(now, tmp_path / "now", SWEEP, monkeypatch)
    b = _contracts(base, tmp_path / "base", SWEEP, monkeypatch)
    assert a[0]["campaignSha256"] == b[0]["campaignSha256"]
    assert a[1].plan_sha256 == b[1].plan_sha256 == SWEEP_PLAN_SHA256 and a[1].run_ids == b[1].run_ids
    moved = {"candidate-runtime-adapter", "study-epoch-loader", "candidate-validator", "bounded-performance-runner"}
    assert {name for name in a[1].controller_sha256 if a[1].controller_sha256[name] != b[1].controller_sha256[name]} \
        == moved
    assert len(a[3]) == len(b[3]) == 12
    for left, right in zip(a[3], b[3]):
        assert _mask_moved_digests(left, moved) == _mask_moved_digests(right, moved)


@pytest.mark.parametrize("selector,expected", [(None, SWEEP), (SWEEP_SELECTOR, SWEEP), (QUIET_SELECTOR, QUIET)])
def test_the_sweep_mode_compiler_follows_the_selector(tmp_path, selector, expected):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_quiet_resolution_epoch", root / "modules/teastore/execution/study_epoch.py")
    assert epoch.sweep_compiler(root).EPOCH == expected


# ---------------------------------------------------------------------------------------------- 3. the selector
def test_the_selector_activates_the_quiet_calibration(qtree):
    epoch = qtree["epoch"].active(qtree["root"])
    assert epoch == {
        "studyEpoch": QUIET, "sweep": True, "runCount": 40, "minimumFirstMutationRemainingSeconds": 21_300,
        "descriptorRelative": "pipelines/campaigns/teastore-quiet-calibration-v1.json",
        "compilerRelative": "modules/teastore/execution/candidate_quiet.py", "scheduleVersion": "quiet-schedule-v1",
        "outerLeaseScope": "entire-40-cell-one-shot", "regimes": ("no-fault-cost",),
        "scenarios": {"no-fault-cost": None}, "postures": ("full",), "blocksPerRegime": 10, "maximumOrdinal": 4,
        "selectorRelative": "modules/teastore/execution/study-epoch.json", "runWindowHours": 7,
        "maximumWallSeconds": 25_200,
        "additionalControllerPaths": {
            "sweep-compiler": "modules/teastore/execution/candidate_sweep.py",
            "sweep-descriptor": "pipelines/campaigns/teastore-traffic-sweep-v1.json",
            "quiet-descriptor": "pipelines/campaigns/teastore-quiet-calibration-v1.json",
        },
    }
    adapter = qtree["adapter"]
    assert (adapter.STUDY_EPOCH, adapter.RUN_COUNT, adapter.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (
        QUIET, 40, 21_300)
    assert adapter.OUTER_LEASE_SCOPE == "entire-40-cell-one-shot"
    assert set(adapter.CONTROLLER_PATHS) - sw._frozen_controller_keys() == {
        "frozen-compiler", "sweep-descriptor", "protocol-gates", "study-epoch-loader", "study-epoch-selector",
        "sweep-compiler", "quiet-descriptor"}
    assert adapter.CONTROLLER_PATHS["candidate-compiler"] == "modules/teastore/execution/candidate_quiet.py"
    assert adapter.CONTROLLER_PATHS["sweep-compiler"] == "modules/teastore/execution/candidate_sweep.py"
    assert adapter.CONTROLLER_PATHS["sweep-descriptor"] == "pipelines/campaigns/teastore-traffic-sweep-v1.json"
    assert adapter.CONTROLLER_PATHS["quiet-descriptor"] == "pipelines/campaigns/teastore-quiet-calibration-v1.json"
    assert all((qtree["root"] / path).is_file() for path in adapter.CONTROLLER_PATHS.values())
    assert "application.log" in adapter.COMMON_ARTIFACTS
    assert qtree["transport"].RUN_COUNT == qtree["controller"].RUN_COUNT == qtree["terminal"].RUN_COUNT == 40
    assert qtree["transport"].MINIMUM_FIRST_MUTATION_SECONDS == qtree["controller"].MINIMUM_FIRST_MUTATION_SECONDS \
        == 21_300
    assert qtree["producer"].CANDIDATE_STUDY_EPOCH == QUIET
    assert qtree["validator"].SWEEP is True and qtree["validator"].STUDY_EPOCH == QUIET
    assert qtree["validator"].REGIMES == ("no-fault-cost",) and qtree["validator"].SCENARIOS == {}
    assert "application.log" in qtree["validator"].REQUIRED_FILES
    assert qtree["readiness"].SEAM_EXPECTED_VALUES["none-selected-full-materialization"] == {
        "descriptorValidation": "pass", "compiledRunCount": 40, "regimes": ["no-fault-cost"], "postures": ["full"]}
    assert qtree["witness"].SWEEP_EPOCH_ACTIVE is True and qtree["native_token"].SWEEP_EPOCH_ACTIVE is True
    assert qtree["orchestrator"].DEFAULT_DESCRIPTOR == qtree["root"] / "pipelines/campaigns/teastore-quiet-calibration-v1.json"
    assert qtree["epoch"].sweep_compiler(qtree["root"]).EPOCH == QUIET


@pytest.mark.parametrize("selector", [
    {"schemaVersion": 1, "studyEpoch": "teastore-quiet-calibration-v2"},
    {"schemaVersion": True, "studyEpoch": QUIET},
    {"schemaVersion": 1, "studyEpoch": QUIET, "extra": 1},
    {"schemaVersion": 2, "studyEpoch": QUIET},
    b'{"schemaVersion": 1, "studyEpoch": "teastore-quiet-calibration-v1", "studyEpoch": "teastore-quiet-calibration-v1"}',
])
def test_a_malformed_quiet_selector_refuses_to_load(tmp_path, selector):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_quiet_bad_selector_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


def test_a_selector_whose_compiler_names_another_epoch_refuses_to_load(tmp_path):
    root = sw._copy_tree(tmp_path, QUIET_SELECTOR)
    compiler = root / "modules/teastore/execution/candidate_quiet.py"
    compiler.write_text(compiler.read_text().replace('EPOCH = "teastore-quiet-calibration-v1"',
                                                     'EPOCH = "teastore-traffic-sweep-v1"', 1))
    epoch = sw.load("teastore_quiet_wrong_compiler_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


# ----------------------------------------------------------- 4. materialize -> inspect -> contracts -> package
@pytest.fixture
def qchain(qtree, tmp_path, monkeypatch):
    materialized, bindings, package, contracts = _contracts(qtree, tmp_path, QUIET, monkeypatch)
    return {"materialized": materialized, "bindings": bindings, "package": package, "contracts": contracts}


def test_inspect_and_contracts_carry_the_compiled_timing(qtree, qchain):
    bindings, contracts = qchain["bindings"], qchain["contracts"]
    compiled = _cells()
    assert bindings.plan_sha256 == quiet.EXPECTED_PLAN_SHA256
    assert bindings.descriptor_sha256 == quiet.EXPECTED_DESCRIPTOR_SHA256
    assert list(bindings.run_ids) == [cell["runId"] for cell in compiled]
    assert bindings.campaign["scheduleVersion"] == "quiet-schedule-v1" and bindings.campaign["runCount"] == 40
    paths = [row["path"] for row in bindings.campaign["runs"]]
    assert len(set(paths)) == 40 and paths[0] == "runs/no-fault-cost/b01-01-full" and paths[-1] == (
        "runs/no-fault-cost/b10-04-full")
    assert set(bindings.controller_sha256) == set(qtree["adapter"].CONTROLLER_PATHS)
    for contract, cell in zip(contracts, compiled):
        timing = cell["timing"]
        assert contract["runId"] == cell["runId"] and contract["window"]["timing"] == timing
        assert contract["window"]["measurementSeconds"] == 180 and contract["window"]["warmupSeconds"] == 30
        assert contract["workload"]["journeysPerSecond"] == timing["journeysPerSecond"]
        assert contract["workload"]["offeredJourneys"] == timing["offered"]
        assert contract["workload"]["id"] == "login-only-v1" and contract["workload"]["concurrency"] == 240
        assert contract["target"]["outerLeaseScope"] == "entire-40-cell-one-shot"
        assert {"application.log", "resources.json"} <= set(contract["requiredArtifacts"])
        assert "intervention.json" not in contract["requiredArtifacts"]


def test_the_runtime_package_round_trips_through_the_transport(qtree, qchain):
    transport, adapter = qtree["transport"], qtree["adapter"]
    runtime_package = types.SimpleNamespace(
        bindings=qchain["bindings"], gate_run=qchain["package"].gate_run,
        gate_plan_sha256="4" * 64, readiness_sha256="5" * 64, gate_run_sha256="6" * 64,
        readiness={**qchain["package"].readiness, "release": {**qchain["package"].readiness["release"]}},
    )
    document = transport.build_runtime_package(runtime_package)
    document["releaseBindingSha256"] = document["cells"][0]["runtimeInputs"]["releaseBindingSha256"]
    for cell in document["cells"]:
        cell["runtimeInputs"]["readinessArchiveSha256"] = document["readinessArchiveSha256"]
    validated = transport.validate_runtime_package(document)
    assert validated["runCount"] == 40 and len(validated["cells"]) == 40
    assert validated["outerLeaseScope"] == "entire-40-cell-one-shot"
    planted = copy.deepcopy(document)
    planted["cells"] = planted["cells"][:39]
    with pytest.raises(transport.TransportError, match="exactly 40 cells"):
        transport.validate_runtime_package(planted)


def test_the_producer_accepts_every_compiled_contract_and_takes_its_numbers_from_timing(qtree, qchain, monkeypatch):
    producer = sw._producer_in_tree(qtree, monkeypatch)
    for contract in qchain["contracts"]:
        contract = sw._with_real_controller_digests(qtree, contract)
        producer._validate_candidate_contract(contract)
        args = producer._candidate_args(contract, Path("out"))
        timing = contract["window"]["timing"]
        assert (args.warmup, args.duration, args.rate, args.concurrency) == (
            30, 180, timing["journeysPerSecond"], 240)
        assert args.fault == "none" and args.timing == timing


@pytest.mark.parametrize("plant", ["rate", "onset", "ordinal", "block", "lease-scope", "sweep-timing", "frozen-window"])
def test_the_producer_refuses_a_contract_that_brings_its_own_numbers(qtree, qchain, monkeypatch, plant):
    producer = sw._producer_in_tree(qtree, monkeypatch)
    contract = sw._with_real_controller_digests(qtree, qchain["contracts"][0])
    producer._validate_candidate_contract(copy.deepcopy(contract))
    timing = contract["window"]["timing"]
    if plant == "rate":
        timing["journeysPerSecond"] = 1.0
    elif plant == "onset":
        timing["faultOnsetSeconds"] = 60.0
    elif plant == "ordinal":
        contract["ordinalPosition"] = 5
    elif plant == "block":
        contract["runKey"]["block"] = 11
    elif plant == "lease-scope":
        contract["target"]["outerLeaseScope"] = "entire-12-cell-one-shot"
    elif plant == "sweep-timing":
        rate = timing["journeysPerSecond"]
        contract["window"]["timing"] = sweep.cell_timing(
            sweep.run_id_for("no-fault-cost", rate, 1, "full"), "no-fault-cost", rate)
    elif plant == "frozen-window":
        del contract["window"]["timing"]
    with pytest.raises(RuntimeError):
        producer._validate_candidate_contract(contract)


# ------------------------------------------------------------- 5. one fake-driven execution of the runtime slice
def _normalised(calls: dict, root: Path) -> list:
    """Every recorded command with the run root and the barrier ID (sha256 of descriptor, run ID, epoch) masked."""
    text = str(root)
    return [[re.sub(r"barrier-[0-9a-f]{32}", "barrier-<id>", value.replace(text, "<root>")) for value in argv]
            for argv in calls["commands"] + calls["popen"]]


@pytest.mark.parametrize("rate", RATES)
def test_a_quiet_runtime_slice_issues_the_sweeps_no_fault_commands(qtree, stree, qchain, tmp_path, monkeypatch, rate):
    contract = next(row for row in qchain["contracts"] if row["window"]["timing"]["journeysPerSecond"] == rate)
    _, _, _, sweep_contracts = _contracts(stree, tmp_path / "sweep-chain", SWEEP, monkeypatch)
    twin = next(row for row in sweep_contracts if row["runKey"]["regime"] == "no-fault-cost"
                and row["window"]["timing"]["journeysPerSecond"] == rate)
    results = []
    for tree, row, name in ((qtree, contract, "quiet"), (stree, twin, "sweep")):
        run_root = tmp_path / name / "run"
        shutil.copytree(tree["root"], run_root)
        producer = tree["producer"]
        args = producer._candidate_args(row, run_root / "cell")
        calls = sw._drive_slice(producer, run_root, args, monkeypatch)
        monkeypatch.undo()
        results.append((calls, run_root, args))
    (quiet_calls, quiet_root, quiet_args), (sweep_calls, sweep_root, sweep_args) = results
    assert quiet_calls["inject"] == sweep_calls["inject"] == []
    assert _normalised(quiet_calls, quiet_root) == _normalised(sweep_calls, sweep_root)
    workload = sw._workload_argv(quiet_calls, "workload.json")
    assert workload[3:9] == ["--rate", str(rate), "--duration", "180", "--concurrency", "240"]
    assert workload[-4:] == ["--timeout", "15.0", "--journey-kind", "login-only"]
    probe = next(argv for argv in quiet_calls["popen"]
                 if "modules/teastore/collectors/performance_probe_v3.py" in argv)
    assert probe[probe.index("--duration") + 1] == "180"
    assert quiet_calls["collectorKwargs"]["trace_completeness_deferred"] is True
    assert quiet_calls["receipt"]["window"]["measurementSeconds"] == sweep_calls["receipt"]["window"][
        "measurementSeconds"] == 180
    assert quiet_args.timing == contract["window"]["timing"] and sweep_args.timing == twin["window"]["timing"]


# ------------------------------------------------------------------- 6. sealed quiet cells and the validator
@pytest.fixture
def as_quiet(monkeypatch):
    """sw.make_sweep_run writes the receipt's studyEpoch from its module constant; seal quiet cells with it."""
    monkeypatch.setattr(sw, "SWEEP", QUIET)


@pytest.mark.parametrize("rate", RATES)
def test_a_sealed_quiet_cell_is_accepted_at_every_rate(qtree, tmp_path, as_quiet, rate):
    cell = _quiet_cell(rate, block=10)
    root = sw.make_sweep_run(qtree, tmp_path / "run", cell)
    report = qtree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", sw._failed_gates(report)
    gates = report["protocolGates"]
    assert gates["failedGates"] == [] and gates["blocking"] == ["G1", "G2", "G4"]
    assert gates["notEvaluated"] == ["P0", "R1", "R2"]
    completeness = report["traceCompleteness"]
    assert list(completeness["windows"]) == ["whole-measurement"] and completeness["blocking"] is False
    assert completeness["incompleteInRuleTwo"] == 0


def test_a_quiet_cell_with_one_journey_missing_is_rejected(qtree, tmp_path, as_quiet):
    cell = _quiet_cell(1.0)
    root = sw.make_sweep_run(qtree, tmp_path / "run", cell)
    lines = (root / "journey-ledger.jsonl").read_text().splitlines(keepends=True)
    (root / "journey-ledger.jsonl").write_text("".join(lines[:3] + lines[4:]))
    sw._rehash(qtree, root)
    report = qtree["validator"].validate_run(root, expected=cell["runKey"])
    assert report["verdict"] == "blocked"
    assert {"pre-outcome-plan-and-ledger-chain", "offered-ledger-denominator"} <= set(sw._failed_gates(report))


def test_a_receipt_carrying_the_sweeps_onset_is_rejected(qtree, tmp_path, as_quiet):
    cell = _quiet_cell(0.2)
    root = sw.make_sweep_run(qtree, tmp_path / "run", cell)
    sweep_timing = sweep.cell_timing(sweep.run_id_for("no-fault-cost", 0.2, 1, "full"), "no-fault-cost", 0.2)
    assert sweep_timing["faultOnsetSeconds"] != cell["timing"]["faultOnsetSeconds"]
    sw._mutate(qtree, root, "receipt.json", lambda receipt: receipt.update(timing=sweep_timing))
    assert "sweep-compiled-timing" in sw._failed_gates(qtree["validator"].validate_run(root, expected=cell["runKey"]))


def test_a_pre_onset_failure_at_the_lowest_rate_fails_g2(qtree, tmp_path, as_quiet):
    cell = _quiet_cell(0.05)
    root = sw.make_sweep_run(qtree, tmp_path / "run", cell)
    report = qtree["validator"].sweep_protocol_gates(
        run_id=cell["runId"], posture="full", timing=cell["timing"],
        plan=json.loads((root / "journey-ledger.plan.json").read_text()),
        journeys=[{**row, "outcome": "timeout" if row["sequence"] == 1 else row["outcome"]}
                  for row in (json.loads(line) for line in (root / "journey-ledger.jsonl").read_text().splitlines())
                  if row["recordType"] == "journey-terminal"],
        intervention=None, harness_valid=True)
    assert report["failedGates"] == ["G2"]


def _rechain_ledger(root: Path, mutate) -> None:
    """Mutate the journey ledger's terminal rows, then rebuild its hash chain exactly as the producer writes it."""
    rows = [json.loads(line) for line in (root / "journey-ledger.jsonl").read_text().splitlines()]
    mutate([row for row in rows if row["recordType"] == "journey-terminal"])
    previous = "0" * 64
    for row in rows:
        row.pop("recordSha256", None)
        row["previousRecordSha256"] = previous
        row["recordSha256"] = sw._canonical(row)
        previous = row["recordSha256"]
    (root / "journey-ledger.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


@pytest.mark.parametrize("drift", [0.0, 1.0])
def test_a_ledger_row_drifting_from_its_planned_offset_blocks_a_quiet_cell(qtree, tmp_path, as_quiet, drift):
    """The generic ledger rule under the quiet selector (its effect-cell twin in test_candidate_pilot_evidence.py is
    skipped there: that fixture builds an auth-freeze cell)."""
    cell = _quiet_cell(1.0, block=5)
    root = sw.make_sweep_run(qtree, tmp_path / "run", cell)

    def mutate(rows):
        rows[27]["scheduledMonotonicOffsetSeconds"] += drift
    _rechain_ledger(root, mutate)
    sw._rehash(qtree, root)
    report = qtree["validator"].validate_run(root, expected=cell["runKey"])
    if drift:
        assert "pre-outcome-plan-and-ledger-chain" in sw._failed_gates(report)
    else:
        assert report["verdict"] == "pass", sw._failed_gates(report)


@pytest.mark.parametrize("plant", ["kind", "count", "grid", "start"])
def test_system_samples_shape_defects_block_a_quiet_cell(qtree, tmp_path, as_quiet, plant):
    """The generic system-samples rule under the quiet selector (twin of the skipped effect-cell test)."""
    cell = _quiet_cell(0.2, block=7)
    root = sw.make_sweep_run(qtree, tmp_path / "run", cell)

    def mutate(value):
        if plant == "kind":
            value["kind"] = "hotel-system-samples-v1"
        elif plant == "count":
            value["samples"].pop()
        elif plant == "grid":
            value["samples"][10]["epoch"] += 1.0
        else:
            value["startAtEpoch"] += 5.0
    sw._mutate(qtree, root, "system-samples.json", mutate)
    assert "system-samples" in sw._failed_gates(qtree["validator"].validate_run(root, expected=cell["runKey"]))


def test_the_terminal_requires_the_no_fault_artifacts_and_refuses_a_sweep_fault_regime(qtree):
    terminal = qtree["terminal"]
    key = {"studyEpoch": QUIET, "regime": "no-fault-cost", "block": 1, "posture": "full", "attempt": 1}
    assert {"application.log", "resources.json"} <= terminal._required_for(key)
    for regime in ("auth-freeze-effect", "persistence-cpu-throttle-effect"):
        with pytest.raises(terminal.TerminalError):
            terminal._required_for({**key, "regime": regime})


def test_the_quiet_campaign_replays_its_own_allocation(qtree, tmp_path, monkeypatch, as_quiet):
    adapter = qtree["adapter"]
    monkeypatch.setattr(adapter, "_git_repository_state", sw._git_state(adapter))
    root = tmp_path / "campaign"
    materialized = qtree["orchestrator"].materialize_campaign(root)
    assert len(materialized["cells"]) == 40
    for row, cell in zip(materialized["campaign"]["runs"], materialized["cells"]):
        assert row["runId"] == cell["runId"]
        sw.make_sweep_run(qtree, root / row["path"], cell)
    report = qtree["validator"].validate_campaign(root)
    assert report["verdict"] == "pass", [(r["runKey"], sw._failed_gates(r)) for r in report["runReports"]]
    assert len(report["runReports"]) == 40
    campaign = json.loads((root / "campaign.json").read_text())
    campaign["runs"][0], campaign["runs"][1] = campaign["runs"][1], campaign["runs"][0]
    sw._json(root / "campaign.json", campaign)
    assert "scheduled-cell-population" in sw._failed_gates(qtree["validator"].validate_campaign(root))


# ------------------------------------------------------------------------------------------ 7. the 3.9 floor
@pytest.mark.parametrize("relative", QUIET_TARGET_FILES)
def test_quiet_target_files_parse_at_the_python39_floor(relative):
    tree_ = ast.parse((MODULE / relative).read_text(), feature_version=(3, 9))
    assert any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
               and any(alias.name == "annotations" for alias in node.names) for node in tree_.body), relative


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_the_quiet_runtime_imports_under_system_python_isolated(tmp_path):
    root = sw._copy_tree(tmp_path / "tree", QUIET_SELECTOR)
    script = (
        "import importlib.util, sys\n"
        "root = sys.argv[1]\n"
        "loaded = {}\n"
        "for relative in sys.argv[2:]:\n"
        "    spec = importlib.util.spec_from_file_location('m_' + str(abs(hash(relative))), root + '/' + relative)\n"
        "    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module\n"
        "    spec.loader.exec_module(module); loaded[relative] = module\n"
        "adapter = loaded['modules/teastore/execution/candidate_runtime_adapter.py']\n"
        "print('ok', adapter.STUDY_EPOCH, adapter.RUN_COUNT, sys.version_info[:2])\n"
    )
    relatives = [f"modules/teastore/{relative}" for relative in sw.CHANGED_TARGET_FILES + ("execution/candidate_quiet.py",)]
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script,
         str(root), *relatives],
        capture_output=True, text=True, cwd=root,
    )
    assert result.returncode == 0 and result.stdout.startswith(f"ok {QUIET} 40"), result.stderr[-2000:]
