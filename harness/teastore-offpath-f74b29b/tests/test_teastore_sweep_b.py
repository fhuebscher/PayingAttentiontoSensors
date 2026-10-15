"""teastore-traffic-sweep-b-v1: campaign B, 3 more blocks of the traffic sweep's 12 cells (protocol decision 49).

Covers: the 36-cell plan (3 blocks x 12 (regime, rate) pairs) is deterministic and pinned; each block's order is recomputed
independently from the recorded encoding; the shuffle and onset rules reproduce the sweep's with the sweep's values; every
cell equals the sweep's cell of the same regime and rate apart from the seeded onset (and what follows from it) and the
harness declaration; the budget is the sweep's rule over 36 cells; the sweep and quiet epochs are byte-identical to
91c4967 and, under their own selectors, the runtime is the 91c4967 runtime (contracts, receipts, validator verdicts);
the B selector activates the epoch in every runtime file; materialize -> inspect -> contracts -> package -> producer
contract check for all 36 cells; the H10 probe window and the H4 freeze stamps, produced by the real fault controller
against a faked Docker and checked by the real validator, each with planted defects; the 3.9 floor and digest identity.

Like tests/test_teastore_quiet_calibration.py (whose fixtures this file reuses), every epoch is exercised in a copy of the
module tree with its own selector, so these tests do not depend on which selector the worktree has committed.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import subprocess
import tarfile
import types
from pathlib import Path

import pytest

import test_teastore_quiet_calibration as qc
import test_teastore_traffic_sweep as sw


ROOT = sw.ROOT
MODULE = sw.MODULE
SWEEP = sw.SWEEP
QUIET = qc.QUIET
B = "teastore-traffic-sweep-b-v1"
RATES = sw.RATES
REGIMES = ("no-fault-cost", "auth-freeze-effect", "persistence-cpu-throttle-effect")
BASE_COMMIT = "91c4967f2d9c12a25eeeaf097f998856c377ca7f"          # the quiet calibration's harness (HEAD before B)
B_SELECTOR = {"schemaVersion": 1, "studyEpoch": B}
SWEEP_SELECTOR = {"schemaVersion": 1, "studyEpoch": SWEEP}
QUIET_SELECTOR = {"schemaVersion": 1, "studyEpoch": QUIET}
# Pinned outputs of the epochs B must not move (measurement repo: the sweep and quiet declarations).
SWEEP_PLAN_SHA256 = qc.SWEEP_PLAN_SHA256
QUIET_PLAN_SHA256 = "879a81ab0c3f2e960ee11a282c8200e58b98e97bc8a541cbcc5704654f858266"
QUIET_DESCRIPTOR_SHA256 = "338226d05f8e9d3557918ef9120727094bd71532f4eba72cc9191070f102315b"
# Files this build changed relative to 91c4967; every other file under modules/teastore and pipelines/campaigns must be
# byte-identical.
CHANGED_SHARED_FILES = {
    "modules/teastore/execution/study_epoch.py",
    "modules/teastore/execution/performance_campaign.py",
    "modules/teastore/validation/candidate_pilot.py",
    "modules/teastore/extension-ledger.yaml",
    "modules/teastore/execution/study-epoch.json",          # the activation commit points it at campaign B
}
ADDED_FILES = {"modules/teastore/execution/candidate_sweep_b.py", "pipelines/campaigns/teastore-traffic-sweep-b-v1.json"}
# Campaign C (teastore-traffic-sweep-c-v1, 2026-10-10, BUDGET_C.md) adds its own compiler and descriptor and moves only
# study_epoch.py, the ledger and the selector (named above); B's files are pinned unchanged in tests/test_teastore_sweep_c.py.
ADDED_FILES |= {"modules/teastore/execution/candidate_sweep_c.py", "pipelines/campaigns/teastore-traffic-sweep-c-v1.json"}
# teastore-offpath-v1 (2026-10-14, BUDGET_TEASTORE_OFFPATH.md) adds its own compiler and descriptor; the shared files it moves
# (performance_campaign.py, validation/candidate_pilot.py, study_epoch.py, the ledger) are already allowed above.
ADDED_FILES |= {"modules/teastore/execution/candidate_offpath_ts.py", "pipelines/campaigns/teastore-offpath-v1.json"}
B_TARGET_FILES = ("execution/candidate_sweep_b.py", "execution/study_epoch.py", "execution/performance_campaign.py",
                  "validation/candidate_pilot.py")

b = sw.load("teastore_sweep_b_compiler_test", MODULE / "execution/candidate_sweep_b.py")
quiet = qc.quiet
sweep = sw.sweep


def _tree(root: Path) -> dict:
    module = root / "modules/teastore"
    tag = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    loaded = {"root": root}
    for key, relative in (
        ("epoch", "execution/study_epoch.py"),
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
        loaded[key] = sw.load(f"teastore_b_tree_{key}_{tag}", module / relative)
    return loaded


@pytest.fixture(scope="module")
def btree(tmp_path_factory):
    """Modules loaded from a tree copy whose selector names campaign B."""
    return _tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-b-tree"), B_SELECTOR))


@pytest.fixture(scope="module")
def stree(tmp_path_factory):
    """Modules of this commit under the sweep selector."""
    return _tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-b-sweep-tree"), SWEEP_SELECTOR))


@pytest.fixture(scope="module")
def qtree(tmp_path_factory):
    """Modules of this commit under the quiet selector."""
    return _tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-b-quiet-tree"), QUIET_SELECTOR))


def _base_tree(destination: Path, selector: dict) -> Path:
    """The same subset of the tree as sw._copy_tree, taken from 91c4967, with the given selector written in."""
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", BASE_COMMIT, "modules/teastore", "pipelines/campaigns",
         "src/obsplacement/__init__.py", "src/obsplacement/selection.py"],
        capture_output=True, check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        handle.extractall(destination, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    for path in (destination / "pipelines/campaigns").glob("*.json"):
        if not path.name.startswith("teastore-"):
            path.unlink()
    (destination / "modules/teastore/execution/study-epoch.json").write_text(json.dumps(selector) + "\n")
    return destination


@pytest.fixture(scope="module")
def base_sweep(tmp_path_factory):
    return _tree(_base_tree(tmp_path_factory.mktemp("teastore-b-base-sweep"), SWEEP_SELECTOR))


@pytest.fixture(scope="module")
def base_quiet(tmp_path_factory):
    return _tree(_base_tree(tmp_path_factory.mktemp("teastore-b-base-quiet"), QUIET_SELECTOR))


def _plan() -> dict:
    return b.compile_plan(b.load_descriptor())


def _cells() -> list:
    return b.flatten_cells(_plan())


def _cell(regime: str, rate: float, block: int = 1) -> dict:
    return next(cell for cell in _cells() if cell["runKey"]["regime"] == regime
                and cell["timing"]["journeysPerSecond"] == rate and cell["runKey"]["block"] == block)


# ------------------------------------------------------------------------------------------- 1. the campaign-B plan
def test_b_plan_is_36_cells_3_blocks_deterministic_and_pinned():
    descriptor = b.load_descriptor()
    assert b.canonical_sha256(descriptor) == b.EXPECTED_DESCRIPTOR_SHA256
    # The checked-in descriptor is the generator's output, byte for byte (regenerate, never hand-edit).
    assert b.DEFAULT_DESCRIPTOR.read_bytes() == b.descriptor_bytes()
    first, second = b.compile_plan(descriptor), b.compile_plan(copy.deepcopy(descriptor))
    assert first == second and b.canonical_sha256(first) == b.EXPECTED_PLAN_SHA256
    assert b.validate_plan(descriptor, first) is first
    assert first["runCount"] == b.TOTAL_RUNS == 36 and first["studyEpoch"] == B
    assert descriptor["schedule"]["seed"] == b.SCHEDULE_SEED == 20261009 != sweep.SCHEDULE_SEED
    assert descriptor["schedule"]["version"] == "sweep-b-schedule-v1" and descriptor["schedule"]["leadCell"] is None
    cells = b.flatten_cells(first)
    assert len(cells) == 36 and len({cell["runId"] for cell in cells}) == 36
    assert [block["block"] for block in first["blocks"]] == [1, 2, 3]
    pairs = sorted((regime, float(rate)) for regime in REGIMES for rate in RATES)
    for block in first["blocks"]:
        assert sorted((c["runKey"]["regime"], c["timing"]["journeysPerSecond"]) for c in block["cells"]) == pairs
        assert [c["ordinalPosition"] for c in block["cells"]] == list(range(1, 13))
    assert all(cell["runId"].startswith(B + "/") for cell in cells)
    # No B run ID can equal a sweep or quiet run ID.
    assert not {cell["runId"] for cell in cells} & {
        cell["runId"] for cell in sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor()))}
    assert not {cell["runId"] for cell in cells} & {cell["runId"] for cell in qc._cells()}
    # The three blocks have three different orders (no lead cell, no fixed first cell).
    assert len({tuple(block["order"]) for block in first["blocks"]}) == 3


def test_the_order_is_recomputed_from_the_recorded_encoding():
    descriptor = b.load_descriptor()
    schedule = descriptor["schedule"]
    assert schedule["drawEncoding"] == "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)"
    for receipt in schedule["blocks"]:
        pairs = [(regime, float(rate)) for regime in REGIMES for rate in RATES]
        for index in range(len(pairs) - 1, 0, -1):          # the recorded Fisher-Yates, written out again
            text = "\0".join([str(schedule["seed"]), B, "block-%02d" % receipt["block"], "draw-%d" % index,
                              schedule["version"]])
            draw = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
            other = draw % (index + 1)
            pairs[index], pairs[other] = pairs[other], pairs[index]
        expected = [b.run_id_for(regime, rate, receipt["block"], "full") for regime, rate in pairs]
        assert receipt["runIds"] == expected
        assert receipt["orderSha256"] == b.canonical_sha256(expected)


def test_the_shuffle_and_onset_rules_reproduce_the_sweeps_with_the_sweeps_values():
    pairs = [{"regime": regime, "rate": float(rate)} for regime in sweep.REGIMES for rate in sweep.RATES]
    shuffled = b.fisher_yates(pairs, sweep.SCHEDULE_SEED, sweep.EPOCH, 1, sweep.SCHEDULE_CONTEXT)
    lead = [row for row in shuffled if (row["regime"], row["rate"]) == sweep.LEAD_CELL]
    assert lead + [row for row in shuffled if row is not lead[0]] == sweep.block_order(1)
    for cell in sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor())):
        rate = cell["timing"]["journeysPerSecond"]
        assert b.stratified_onset_offset(
            sweep.SCHEDULE_SEED, sweep.EPOCH, sweep.EPISODES, cell["runId"], cell["runKey"]["regime"], rate, 1,
        ) == sweep.onset_phase_offset(cell["runId"], rate) == cell["timing"]["faultOnsetPhaseOffsetSeconds"]
    # ... and equals the quiet calibration's copy of the same rule for the same arguments.
    for rate in RATES:
        for block in (1, 4, 10):
            run_id = quiet.run_id_for("no-fault-cost", rate, block, "full")
            assert b.stratified_onset_offset(quiet.SCHEDULE_SEED, quiet.EPOCH, quiet.BLOCKS, run_id, "no-fault-cost",
                                             rate, block) == quiet.onset_phase_offset(run_id, rate)


def test_every_cell_is_the_sweeps_cell_but_for_the_onset_and_the_harness_declaration():
    strata = {}
    for cell in _cells():
        timing, regime, rate = cell["timing"], cell["runKey"]["regime"], cell["timing"]["journeysPerSecond"]
        base = sweep.cell_timing(sweep.run_id_for(regime, rate, 1, "full"), regime, rate)
        assert set(timing) == set(base) | {"faultHarness"}
        own = b.OWN_TIMING_KEYS
        assert {key for key in timing if key in base and timing[key] != base[key]} <= own
        assert {key: timing[key] for key in base if key not in own} == {key: base[key] for key in base if key not in own}
        offset = timing["faultOnsetPhaseOffsetSeconds"]
        assert timing["faultOnsetSeconds"] == round(60 + offset, 6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"], round(timing["faultOnsetSeconds"] + 60, 6)]
        assert 0.0 <= offset < 1.0 / rate
        strata.setdefault((regime, rate), []).append(int(offset * rate * 3))
        # The sweep's cell shape, spelled out once.
        assert (timing["concurrency"], timing["requestTimeoutSeconds"], timing["warmupSeconds"],
                timing["warmupJourneysPerSecond"], timing["measurementSeconds"], timing["faultHoldSeconds"]) == (
            240, 15.0, 30, 10.0, 180, 60)
        assert timing["offered"] == {10.0: 1800, 1.0: 180, 0.2: 36, 0.05: 9}[rate]
        assert timing["journeyKind"] == "login-only" and timing["workloadId"] == "login-only-v1"
        assert timing["systemSampleCount"] == 37 and timing["protocolGates"] == ["F1", "G1", "G2", "G4"]
        if regime == "no-fault-cost":
            assert timing["drainAllowanceSeconds"] is None and timing["minimumActualStartsByPhase"] is None
            assert timing["faultHarness"] is None and timing["faultApplied"] is False
        else:
            assert timing["drainAllowanceSeconds"] == 17.0 and timing["faultApplied"] is True
            assert timing["minimumActualStartsByPhase"] == sweep.phase_floors(
                rate, 180, timing["faultOnsetSeconds"], 60)
            assert timing["faultHarness"] == b.FAULT_HARNESS == {
                "version": "h4-h10-v1", "noProbeDuringFault": True, "freezeStamps": True,
                "freezeFailure": "record-not-block", "freezeEventToleranceSeconds": 0.25}
            assert cell["fault"] == {"auth-freeze-effect": "auth-freeze",
                                     "persistence-cpu-throttle-effect": "persistence-cpu-throttle"}[regime]
        if regime == "persistence-cpu-throttle-effect":
            assert (timing["cpuThrottleCpus"], timing["cpuThrottleNanoCpus"]) == ("0.1", 100_000_000)   # decision 50
    # Each (regime, rate) pair's 3 blocks take the 3 thirds of its inter-arrival, one each.
    assert len(strata) == 12 and all(sorted(values) == [0, 1, 2] for values in strata.values())


def test_the_descriptor_differs_from_the_sweeps_only_where_the_epoch_differs():
    descriptor, base = b.load_descriptor(), sweep.load_descriptor()
    changed = {key for key in set(descriptor) | set(base) if descriptor.get(key) != base.get(key)}
    assert changed == {"id", "declaration", "design", "timing", "schedule", "groundTruth", "collection", "outcomes",
                       "analysis", "continuation", "derivedFrom"}
    assert descriptor["declaration"].startswith("research/traffic-sweep/DECLARATION_B_TEASTORE.md ")
    assert descriptor["derivedFrom"]["descriptorCanonicalSha256"] == qc.SWEEP_DESCRIPTOR_SHA256
    assert descriptor["derivedFrom"]["planCanonicalSha256"] == SWEEP_PLAN_SHA256
    assert descriptor["derivedFrom"]["descriptorByteSha256"] == hashlib.sha256(
        (ROOT / sweep.DESCRIPTOR_RELATIVE).read_bytes()).hexdigest()
    # The doses and the cell shape are carried over untouched (decision 50).
    assert descriptor["faultParameters"] == base["faultParameters"]
    assert descriptor["workload"] == base["workload"] and descriptor["protocolGates"] == base["protocolGates"]
    assert descriptor["design"]["omittedRegimes"] == base["design"]["omittedRegimes"]
    assert descriptor["design"]["totalRuns"] == 36 and descriptor["design"]["blocks"] == 3
    timing_changed = {key for key in set(descriptor["timing"]) | set(base["timing"])
                      if descriptor["timing"].get(key) != base["timing"].get(key)}
    assert timing_changed == {"leadCell", "faultOnsetStrata", "minimumTimedSeconds", "operationalEstimateSeconds",
                              "budget", "faultHarness"}
    # What B stamps, and nothing the sweep's analysis would have to reinterpret: the sweep's receipt notes are extended.
    fault = descriptor["groundTruth"]["fault"]
    assert {key for key in fault if fault[key] != base["groundTruth"]["fault"].get(key)} == {"probeStamps", "freezeStamps"}
    assert descriptor["analysis"]["analysisFreeze"].endswith("(BUDGET_B.md stop rule 4)")


def test_budget_is_the_sweeps_rule_over_36_cells_and_covers_the_measured_periods():
    assert b.CELL_PERIOD_ESTIMATE_SECONDS == sweep.CELL_PERIOD_ESTIMATE_SECONDS == 30 + 15 + 180 + 300
    assert b.MINIMUM_TIMED_SECONDS == 36 * (30 + 180) == 7_560
    assert b.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS == 36 * 525 + 300 == 19_200
    assert b.RUN_WINDOW_HOURS == 6 and b.MAXIMUM_WALL_SECONDS == 21_600
    assert b.RUN_WINDOW_HOURS * 3600 >= b.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + b.PREPARE_RESERVE_SECONDS
    assert (b.RUN_WINDOW_HOURS - 1) * 3600 < b.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + b.PREPARE_RESERVE_SECONDS
    measured = b.MEASURED_CELL_PERIOD_SECONDS
    assert measured["minimum"] <= measured["median"] <= measured["maximum"] < b.CELL_PERIOD_ESTIMATE_SECONDS
    # Even at the slowest measured period every cell starts well before the deadline's cleanup reserve.
    assert b.TOTAL_RUNS * measured["maximum"] + b.PREPARE_RESERVE_SECONDS < (
        b.MAXIMUM_WALL_SECONDS - b.CLEANUP_RESERVE_SECONDS)
    plan = _plan()
    assert (plan["runWindowHours"], plan["maximumWallSeconds"], plan["minimumFirstMutationRemainingSeconds"]) == (
        6, 21_600, 19_200)


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_plan_digest_is_identical_under_python39(tmp_path):
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I",
         str(MODULE / "execution/candidate_sweep_b.py")],
        capture_output=True, text=True, check=True,
    )
    report = json.loads(result.stdout)
    assert report["planCanonicalSha256"] == b.EXPECTED_PLAN_SHA256
    assert report["descriptorCanonicalSha256"] == b.EXPECTED_DESCRIPTOR_SHA256
    assert report["runCount"] == 36 and report["runWindowHours"] == 6


# ------------------------------------------------------------------ 2. the sweep and quiet epochs unchanged
def _changed_since_base() -> set:
    listing = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", BASE_COMMIT, "--",
                              "modules/teastore", "pipelines/campaigns"],
                             capture_output=True, text=True, check=True).stdout.split()
    untracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard", "--",
                                "modules/teastore", "pipelines/campaigns"],
                               capture_output=True, text=True, check=True).stdout.split()
    return set(listing) | set(untracked)


def _git_blob(relative: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:{relative}"],
                          capture_output=True, check=True).stdout


def test_the_sweep_and_quiet_epochs_are_byte_identical_and_their_digests_unchanged():
    assert _changed_since_base() <= CHANGED_SHARED_FILES | ADDED_FILES
    for relative in ("modules/teastore/execution/candidate_sweep.py", sweep.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_quiet.py", quiet.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_pilot.py",
                     "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json",
                     "modules/teastore/validation/protocol_gates.py", "modules/teastore/validation/secret_scan.py",
                     "modules/teastore/execution/candidate_runtime_adapter.py",
                     "modules/teastore/execution/candidate_transport.py",
                     "modules/teastore/execution/candidate_remote_controller.py",
                     "modules/teastore/execution/candidate_release_installer.py",
                     "modules/teastore/execution/candidate_orchestrator.py",
                     "modules/teastore/validation/candidate_terminal.py",
                     "modules/teastore/validation/candidate_readiness.py", "modules/teastore/workload/fixed_load.py",
                     "modules/teastore/witness/extract_app_witness.py"):
        assert (ROOT / relative).read_bytes() == _git_blob(relative), relative
    assert sweep.EXPECTED_DESCRIPTOR_SHA256 == qc.SWEEP_DESCRIPTOR_SHA256 and sweep.EXPECTED_PLAN_SHA256 == SWEEP_PLAN_SHA256
    assert quiet.EXPECTED_DESCRIPTOR_SHA256 == QUIET_DESCRIPTOR_SHA256 and quiet.EXPECTED_PLAN_SHA256 == QUIET_PLAN_SHA256
    assert sweep.canonical_sha256(sweep.compile_plan(sweep.load_descriptor())) == SWEEP_PLAN_SHA256
    assert quiet.canonical_sha256(quiet.compile_plan(quiet.load_descriptor())) == QUIET_PLAN_SHA256


def _moved_names(tree: dict) -> set:
    """Controller names of the files this build changed (their digests move by construction)."""
    changed = {f"modules/teastore/{relative}" for relative in (
        "execution/study_epoch.py", "execution/performance_campaign.py", "validation/candidate_pilot.py")}
    return {name for name, relative in tree["adapter"].CONTROLLER_PATHS.items() if relative in changed}


@pytest.mark.parametrize("selector_name", ["sweep", "quiet"])
def test_under_their_own_selectors_the_runtime_is_the_91c4967_runtime(
        selector_name, stree, qtree, base_sweep, base_quiet, tmp_path, monkeypatch):
    now, base, epoch, plan_sha, count = (
        (stree, base_sweep, SWEEP, SWEEP_PLAN_SHA256, 12) if selector_name == "sweep"
        else (qtree, base_quiet, QUIET, QUIET_PLAN_SHA256, 40))
    assert now["epoch"].active(now["root"]) == base["epoch"].active(base["root"])
    assert now["adapter"].CONTROLLER_PATHS == base["adapter"].CONTROLLER_PATHS
    for name in ("STUDY_EPOCH", "RUN_COUNT", "MINIMUM_FIRST_MUTATION_REMAINING_SECONDS", "OUTER_LEASE_SCOPE",
                 "COMMON_ARTIFACTS"):
        assert getattr(now["adapter"], name) == getattr(base["adapter"], name), name
    assert now["readiness"].SEAM_EXPECTED_VALUES == base["readiness"].SEAM_EXPECTED_VALUES
    left = qc._contracts(now, tmp_path / "now", epoch, monkeypatch)
    right = qc._contracts(base, tmp_path / "base", epoch, monkeypatch)
    assert left[0]["campaignSha256"] == right[0]["campaignSha256"]
    assert left[1].plan_sha256 == right[1].plan_sha256 == plan_sha and left[1].run_ids == right[1].run_ids
    moved = _moved_names(now)
    assert {name for name in left[1].controller_sha256
            if left[1].controller_sha256[name] != right[1].controller_sha256[name]} == moved
    assert len(left[3]) == len(right[3]) == count
    for one, other in zip(left[3], right[3]):
        assert qc._mask_moved_digests(one, moved) == qc._mask_moved_digests(other, moved)


def _fixed_now(monkeypatch, producer):
    monkeypatch.setattr(producer, "now", lambda: "2026-10-09T00:00:00+00:00")


@pytest.mark.parametrize("regime,fault", [("auth-freeze-effect", "auth-freeze"),
                                           ("persistence-cpu-throttle-effect", "persistence-cpu-throttle")])
def test_a_sweep_cells_fault_receipt_is_the_91c4967_receipt(stree, base_sweep, tmp_path, monkeypatch, regime, fault):
    receipts = []
    for tree in (stree, base_sweep):
        producer = tree["producer"]
        clock, fake = sw._fault_kit(producer, monkeypatch)
        _fixed_now(monkeypatch, producer)
        directory = tmp_path / ("now" if tree is stree else "base")
        directory.mkdir()
        receipt, _ = sw._inject(producer, clock, fake, directory, fault, sw._cell_timing(1.0, regime))
        receipts.append((receipt, [args for _, args in fake.calls]))
        monkeypatch.undo()
    (now_receipt, now_calls), (base_receipt, base_calls) = receipts
    assert now_receipt["successful"] is True and now_receipt == base_receipt and now_calls == base_calls
    assert set(now_receipt["sweep"]) == {"schemaVersion", "onsetSource", "commandStamps", "probes", "throttle"}
    assert not any("events" in args for args in now_calls)


@pytest.mark.parametrize("regime,rate", [("auth-freeze-effect", 0.2), ("persistence-cpu-throttle-effect", 10.0),
                                          ("no-fault-cost", 1.0)])
def test_a_sealed_sweep_cell_gets_the_91c4967_verdict(stree, base_sweep, tmp_path, regime, rate):
    cell = sw._cell(regime, rate)
    reports = []
    for tree in (stree, base_sweep):
        root = sw.make_sweep_run(tree, tmp_path / ("now" if tree is stree else "base"), cell)
        reports.append(tree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]}))
    now_report, base_report = reports
    assert now_report["verdict"] == base_report["verdict"] == "pass", sw._failed_gates(now_report)
    assert [(row["gate"], row["status"]) for row in now_report["validationTable"]] == [
        (row["gate"], row["status"]) for row in base_report["validationTable"]]


# ---------------------------------------------------------------------------------------------- 3. the selector
@pytest.mark.parametrize("selector,expected", [(None, SWEEP), (SWEEP_SELECTOR, SWEEP), (QUIET_SELECTOR, QUIET),
                                                (B_SELECTOR, B)])
def test_the_sweep_mode_compiler_follows_the_selector(tmp_path, selector, expected):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_b_resolution_epoch", root / "modules/teastore/execution/study_epoch.py")
    assert epoch.sweep_compiler(root).EPOCH == expected


def test_the_selector_activates_campaign_b(btree):
    epoch = btree["epoch"].active(btree["root"])
    assert epoch == {
        "studyEpoch": B, "sweep": True, "runCount": 36, "minimumFirstMutationRemainingSeconds": 19_200,
        "descriptorRelative": "pipelines/campaigns/teastore-traffic-sweep-b-v1.json",
        "compilerRelative": "modules/teastore/execution/candidate_sweep_b.py", "scheduleVersion": "sweep-b-schedule-v1",
        "outerLeaseScope": "entire-36-cell-one-shot", "regimes": REGIMES,
        "scenarios": {"no-fault-cost": None, "auth-freeze-effect": "auth-freeze",
                      "persistence-cpu-throttle-effect": "persistence-cpu-throttle"},
        "postures": ("full",), "blocksPerRegime": 3, "maximumOrdinal": 12,
        "selectorRelative": "modules/teastore/execution/study-epoch.json", "runWindowHours": 6,
        "maximumWallSeconds": 21_600,
        "additionalControllerPaths": {
            "sweep-compiler": "modules/teastore/execution/candidate_sweep.py",
            "sweep-descriptor": "pipelines/campaigns/teastore-traffic-sweep-v1.json",
            "sweep-b-descriptor": "pipelines/campaigns/teastore-traffic-sweep-b-v1.json",
        },
    }
    adapter = btree["adapter"]
    assert (adapter.STUDY_EPOCH, adapter.RUN_COUNT, adapter.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (B, 36, 19_200)
    assert adapter.OUTER_LEASE_SCOPE == "entire-36-cell-one-shot"
    assert set(adapter.CONTROLLER_PATHS) - sw._frozen_controller_keys() == {
        "frozen-compiler", "sweep-descriptor", "protocol-gates", "study-epoch-loader", "study-epoch-selector",
        "sweep-compiler", "sweep-b-descriptor"}
    assert adapter.CONTROLLER_PATHS["candidate-compiler"] == "modules/teastore/execution/candidate_sweep_b.py"
    assert adapter.CONTROLLER_PATHS["sweep-compiler"] == "modules/teastore/execution/candidate_sweep.py"
    assert adapter.CONTROLLER_PATHS["sweep-descriptor"] == "pipelines/campaigns/teastore-traffic-sweep-v1.json"
    assert adapter.CONTROLLER_PATHS["sweep-b-descriptor"] == "pipelines/campaigns/teastore-traffic-sweep-b-v1.json"
    assert all((btree["root"] / path).is_file() for path in adapter.CONTROLLER_PATHS.values())
    assert "application.log" in adapter.COMMON_ARTIFACTS
    assert btree["transport"].RUN_COUNT == btree["controller"].RUN_COUNT == btree["terminal"].RUN_COUNT == 36
    assert btree["transport"].MINIMUM_FIRST_MUTATION_SECONDS == btree["controller"].MINIMUM_FIRST_MUTATION_SECONDS \
        == 19_200
    assert btree["producer"].CANDIDATE_STUDY_EPOCH == B
    assert btree["validator"].SWEEP is True and btree["validator"].STUDY_EPOCH == B
    assert btree["validator"].REGIMES == REGIMES
    assert btree["validator"].SCENARIOS == {"auth-freeze-effect": "auth-freeze",
                                            "persistence-cpu-throttle-effect": "persistence-cpu-throttle"}
    assert btree["readiness"].SEAM_EXPECTED_VALUES["none-selected-full-materialization"] == {
        "descriptorValidation": "pass", "compiledRunCount": 36, "regimes": sorted(REGIMES), "postures": ["full"]}
    assert btree["witness"].SWEEP_EPOCH_ACTIVE is True and btree["native_token"].SWEEP_EPOCH_ACTIVE is True
    assert btree["orchestrator"].DEFAULT_DESCRIPTOR == btree["root"] / "pipelines/campaigns/teastore-traffic-sweep-b-v1.json"
    assert btree["epoch"].sweep_compiler(btree["root"]).EPOCH == B


@pytest.mark.parametrize("selector", [
    {"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-b-v2"},
    {"schemaVersion": True, "studyEpoch": B},
    {"schemaVersion": 1, "studyEpoch": B, "extra": 1},
    {"schemaVersion": 2, "studyEpoch": B},
    {"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-b-v1 "},
    b'{"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-b-v1", "studyEpoch": "teastore-traffic-sweep-b-v1"}',
])
def test_a_malformed_b_selector_refuses_to_load(tmp_path, selector):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_b_bad_selector_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


def test_a_selector_whose_compiler_names_another_epoch_refuses_to_load(tmp_path):
    root = sw._copy_tree(tmp_path, B_SELECTOR)
    compiler = root / "modules/teastore/execution/candidate_sweep_b.py"
    compiler.write_text(compiler.read_text().replace('EPOCH = "teastore-traffic-sweep-b-v1"',
                                                     'EPOCH = "teastore-traffic-sweep-v1"', 1))
    epoch = sw.load("teastore_b_wrong_compiler_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


# ----------------------------------------------------------- 4. materialize -> inspect -> contracts -> package
@pytest.fixture
def bchain(btree, tmp_path, monkeypatch):
    materialized, bindings, package, contracts = qc._contracts(btree, tmp_path, B, monkeypatch)
    return {"materialized": materialized, "bindings": bindings, "package": package, "contracts": contracts}


def test_inspect_and_contracts_carry_the_compiled_timing(btree, bchain):
    bindings, contracts = bchain["bindings"], bchain["contracts"]
    compiled = _cells()
    assert bindings.plan_sha256 == b.EXPECTED_PLAN_SHA256 and bindings.descriptor_sha256 == b.EXPECTED_DESCRIPTOR_SHA256
    assert list(bindings.run_ids) == [cell["runId"] for cell in compiled]
    assert bindings.campaign["scheduleVersion"] == "sweep-b-schedule-v1" and bindings.campaign["runCount"] == 36
    paths = [row["path"] for row in bindings.campaign["runs"]]
    assert len(set(paths)) == 36
    assert set(bindings.controller_sha256) == set(btree["adapter"].CONTROLLER_PATHS)
    for contract, cell in zip(contracts, compiled):
        timing = cell["timing"]
        assert contract["runId"] == cell["runId"] and contract["window"]["timing"] == timing
        assert contract["window"]["measurementSeconds"] == 180 and contract["window"]["warmupSeconds"] == 30
        assert contract["workload"]["journeysPerSecond"] == timing["journeysPerSecond"]
        assert contract["workload"]["offeredJourneys"] == timing["offered"]
        assert contract["target"]["outerLeaseScope"] == "entire-36-cell-one-shot"
        assert {"application.log"} <= set(contract["requiredArtifacts"])
        assert ("intervention.json" in contract["requiredArtifacts"]) is timing["faultApplied"]
        assert contract["window"]["timing"]["faultHarness"] == (b.FAULT_HARNESS if timing["faultApplied"] else None)


def test_the_runtime_package_round_trips_through_the_transport(btree, bchain):
    transport = btree["transport"]
    runtime_package = types.SimpleNamespace(
        bindings=bchain["bindings"], gate_run=bchain["package"].gate_run,
        gate_plan_sha256="4" * 64, readiness_sha256="5" * 64, gate_run_sha256="6" * 64,
        readiness={**bchain["package"].readiness, "release": {**bchain["package"].readiness["release"]}},
    )
    document = transport.build_runtime_package(runtime_package)
    document["releaseBindingSha256"] = document["cells"][0]["runtimeInputs"]["releaseBindingSha256"]
    for cell in document["cells"]:
        cell["runtimeInputs"]["readinessArchiveSha256"] = document["readinessArchiveSha256"]
    validated = transport.validate_runtime_package(document)
    assert validated["runCount"] == 36 and len(validated["cells"]) == 36
    assert validated["outerLeaseScope"] == "entire-36-cell-one-shot"
    planted = copy.deepcopy(document)
    planted["cells"] = planted["cells"][:35]
    with pytest.raises(transport.TransportError, match="exactly 36 cells"):
        transport.validate_runtime_package(planted)


def test_the_producer_accepts_every_compiled_contract_and_takes_its_numbers_from_timing(btree, bchain, monkeypatch):
    producer = sw._producer_in_tree(btree, monkeypatch)
    for contract in bchain["contracts"]:
        contract = sw._with_real_controller_digests(btree, contract)
        producer._validate_candidate_contract(contract)
        args = producer._candidate_args(contract, Path("out"))
        timing = contract["window"]["timing"]
        assert (args.warmup, args.duration, args.rate, args.concurrency) == (
            30, 180, timing["journeysPerSecond"], 240)
        assert args.timing == timing and args.fault == (timing["fault"] or "none")


@pytest.mark.parametrize("plant", ["rate", "onset", "ordinal", "block", "lease-scope", "sweep-timing",
                                   "harness-dropped", "harness-on-no-fault", "frozen-window"])
def test_the_producer_refuses_a_contract_that_brings_its_own_numbers(btree, bchain, monkeypatch, plant):
    producer = sw._producer_in_tree(btree, monkeypatch)
    index = next(i for i, cell in enumerate(_cells()) if cell["timing"]["faultApplied"]
                 and cell["timing"]["journeysPerSecond"] == 1.0)
    no_fault = next(i for i, cell in enumerate(_cells()) if not cell["timing"]["faultApplied"])
    contract = sw._with_real_controller_digests(btree, bchain["contracts"][no_fault if plant == "harness-on-no-fault"
                                                                           else index])
    producer._validate_candidate_contract(copy.deepcopy(contract))
    timing = contract["window"]["timing"]
    if plant == "rate":
        timing["journeysPerSecond"] = 0.2
    elif plant == "onset":
        timing["faultOnsetSeconds"] = 60.0
        contract["faultGroundTruth"]["faultOnsetSeconds"] = 60.0
    elif plant == "ordinal":
        contract["ordinalPosition"] = 13
    elif plant == "block":
        contract["runKey"]["block"] = 4
    elif plant == "lease-scope":
        contract["target"]["outerLeaseScope"] = "entire-12-cell-one-shot"
    elif plant == "sweep-timing":
        rate, regime = timing["journeysPerSecond"], contract["runKey"]["regime"]
        contract["window"]["timing"] = sweep.cell_timing(sweep.run_id_for(regime, rate, 1, "full"), regime, rate)
    elif plant == "harness-dropped":
        timing["faultHarness"] = None
    elif plant == "harness-on-no-fault":
        timing["faultHarness"] = dict(b.FAULT_HARNESS)
    elif plant == "frozen-window":
        del contract["window"]["timing"]
    with pytest.raises(RuntimeError):
        producer._validate_candidate_contract(contract)


# ------------------------------------------------------------------ 5. H10 and H4 in the fault controller (fake host)
class EventsDocker(sw.FakeDocker):
    """FakeDocker that also keeps Docker's own pause and unpause events and answers ``docker events`` for them."""

    def __init__(self, clock, *, events_rc: int = 0, **kwargs):
        super().__init__(clock, **kwargs)
        self.events, self.events_rc = [], events_rc

    def __call__(self, args, *, output=None, check=True):
        args = list(args)
        if args[:2] == ["docker", "compose"] and args[-2:] in (["pause", "auth"], ["unpause", "auth"]):
            # The daemon emits the event after the freezer confirmed it, inside the command.
            self.events.append({"Type": "container", "Action": args[-2], "Actor": {"ID": self.target, "Attributes": {
                "name": "teastore_auth_1", "com.docker.compose.project": "x"}},
                "time": int(self.clock.wall), "timeNano": int(round((self.clock.wall + 0.1) * 1e9))})
        if args[:3] == ["timeout", "30", "docker"] and args[3] == "events":
            self.calls.append((self.clock.monotonic(), args))
            self.clock.advance(0.05)
            if self.events_rc:
                return types.SimpleNamespace(returncode=self.events_rc, stdout="", stderr="daemon unreachable")
            wanted = {args[i + 1].split("=", 1)[1] for i, value in enumerate(args) if value == "--filter"
                      and args[i + 1].startswith("event=")}
            return types.SimpleNamespace(returncode=0, stderr="", stdout="".join(
                json.dumps(event) + "\n" for event in self.events if event["Action"] in wanted))
        return super().__call__(args, output=output, check=check)


class ProbeInHoldDocker(EventsDocker):
    """The planted defect: a readiness probe (curl) fired inside the fault window, at the hold-midpoint readback."""

    def __init__(self, clock, **kwargs):
        super().__init__(clock, **kwargs)
        self.inspects = 0

    def __call__(self, args, *, output=None, check=True):
        if list(args)[:2] == ["docker", "inspect"]:
            self.inspects += 1
            if self.inspects == 3:       # pre-state, manifested, hold-midpoint (this one), hold-end
                super().__call__(["curl", "-fsS", "--max-time", "10",
                                  "http://localhost:8080/tools.descartes.teastore.webui/status"])
        return super().__call__(args, output=output, check=check)


def _b_kit(producer, monkeypatch, docker=EventsDocker, **kwargs):
    clock = sw.FakeClock()
    fake = docker(clock, **kwargs)
    monkeypatch.setattr(producer, "time", clock)
    monkeypatch.setattr(producer, "command", fake)
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "teastore_candidate_0123456789abcdef")
    return clock, fake


def _b_timing(regime: str, rate: float = 1.0, block: int = 2) -> dict:
    return _cell(regime, rate, block)["timing"]


def probes_inside(calls: list, barrier: float, start: float, end: float) -> list:
    """Monotonic offsets of every SUT request (curl) the controller issued in [start, end): the H10 check."""
    return [at - barrier for at, args in calls if args[0] == "curl" and start <= at - barrier < end]


def test_no_probe_is_scheduled_inside_the_fault_window_on_a_pause(btree, tmp_path, monkeypatch):
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch)
    timing = _b_timing("auth-freeze-effect")
    receipt, barrier = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    assert receipt["successful"] is True, receipt["error"]
    policy = receipt["sweep"]["probePolicy"]
    stamps = receipt["sweep"]["commandStamps"]
    assert policy == {
        "version": "h4-h10-v1",
        "noProbeFromMonotonicOffsetSeconds": stamps["onsetCommandIssuedMonotonicOffsetSeconds"],
        "scoredWindowEndMonotonicOffsetSeconds": timing["faultOnsetSeconds"] + 60,
        "noProbeUntilMonotonicOffsetSeconds": stamps["revertCommandReturnedMonotonicOffsetSeconds"],
    }
    # No SUT request between the onset command and the end of the window, by the fake docker's own call log.
    assert probes_inside(fake.calls, barrier, policy["noProbeFromMonotonicOffsetSeconds"],
                         policy["noProbeUntilMonotonicOffsetSeconds"]) == []
    # ... but the readiness probes after the revert are still there, and start at or after the window's end.
    probes = receipt["sweep"]["probes"]
    assert probes and all(row["startMonotonicOffsetSeconds"] >= policy["noProbeUntilMonotonicOffsetSeconds"]
                          for row in probes)
    assert [at - barrier for at, args in fake.calls if args[0] == "curl"] == [
        row["startMonotonicOffsetSeconds"] for row in probes]
    # Probes outside the window are unchanged: the same stamped GET /status loop the sweep runs.
    assert probes[-1]["ready"] is True and {row["phase"] for row in probes} == {"post-revert-readiness"}


def test_the_checker_catches_a_probe_planted_inside_the_fault_window(btree, tmp_path, monkeypatch):
    """Planted defect for the H10 test above: a curl fired at the hold-midpoint readback is found by probes_inside."""
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch, docker=ProbeInHoldDocker)
    timing = _b_timing("auth-freeze-effect")
    receipt, barrier = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    policy = receipt["sweep"]["probePolicy"]
    found = probes_inside(fake.calls, barrier, policy["noProbeFromMonotonicOffsetSeconds"],
                          policy["noProbeUntilMonotonicOffsetSeconds"])
    assert len(found) == 1 and timing["faultOnsetSeconds"] < found[0] < timing["faultOnsetSeconds"] + 60


def test_the_controller_refuses_to_probe_inside_the_window(btree, monkeypatch):
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch)
    probes: list = []
    with pytest.raises(RuntimeError, match="no-probe window"):
        producer.wait_ready_stamped(probes, clock.monotonic() - 100.0, not_before_monotonic=clock.monotonic() + 1.0)
    assert probes == [] and not any(args[0] == "curl" for _, args in fake.calls)
    producer.wait_ready_stamped(probes, clock.monotonic() - 100.0, not_before_monotonic=clock.monotonic())
    assert len(probes) == 1 and probes[0]["ready"] is True


def test_the_controller_stops_the_cell_when_a_probe_would_fall_inside_the_window(btree, tmp_path, monkeypatch):
    """The end-to-end form of the guard: a window that outlasts the revert (a planted later scored end) fails the cell."""
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch)
    timing = _b_timing("auth-freeze-effect")
    # Plant a no-probe window that outlasts the revert (the scored window ending long after the hold).
    real = producer.wait_ready_stamped

    def late_window(probes, anchor, timeout=240, *, not_before_monotonic=None):
        return real(probes, anchor, timeout, not_before_monotonic=(anchor + 10_000.0))
    monkeypatch.setattr(producer, "wait_ready_stamped", late_window)
    receipt, barrier = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    assert receipt["successful"] is False and "no-probe window" in receipt["error"]
    assert not any(args[0] == "curl" for _, args in fake.calls)


def _offset(receipt: dict, event: dict) -> float:
    clock = receipt["sweep"]["freezeStamps"]["clock"]
    return (event["timeNano"] / 1e9 - clock["barrierWallEpochSeconds"]) * (
        clock["collectedMonotonicOffsetSeconds"] / (clock["collectedWallEpochSeconds"] - clock["barrierWallEpochSeconds"]))


def test_a_pause_records_the_dockers_pause_and_unpause_events_beside_the_command_stamps(btree, tmp_path, monkeypatch):
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch)
    timing = _b_timing("auth-freeze-effect", 0.2, 3)
    receipt, barrier = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    assert receipt["successful"] is True, receipt["error"]
    assert set(receipt["sweep"]) == {"schemaVersion", "onsetSource", "commandStamps", "probes", "throttle",
                                     "probePolicy", "freezeStamps"}
    # The new queries are not commands of the cell: the receipt keeps exactly the pause and the unpause.
    assert [row["command"][-2:] for row in receipt["operational"]["commandResults"]] == [
        ["pause", "auth"], ["unpause", "auth"]]
    freeze = receipt["sweep"]["freezeStamps"]
    stamps = receipt["sweep"]["commandStamps"]
    assert (freeze["version"], freeze["scenario"], freeze["targetContainerId"], freeze["toleranceSeconds"]) == (
        "h4-h10-v1", "auth-freeze", fake.target, 0.25)
    assert freeze["commands"] == {
        "onsetIssuedMonotonicOffsetSeconds": stamps["onsetCommandIssuedMonotonicOffsetSeconds"],
        "onsetReturnedMonotonicOffsetSeconds": stamps["onsetCommandReturnedMonotonicOffsetSeconds"],
        "revertIssuedMonotonicOffsetSeconds": stamps["revertCommandIssuedMonotonicOffsetSeconds"],
        "revertReturnedMonotonicOffsetSeconds": stamps["revertCommandReturnedMonotonicOffsetSeconds"]}
    events = freeze["events"]
    assert events["returnCode"] == 0 and events["error"] is None
    assert [row["action"] for row in events["rows"]] == ["pause", "unpause"]
    assert all(row["containerId"] == fake.target and row["type"] == "container" for row in events["rows"])
    assert "Actor" not in json.dumps(events) and "Attributes" not in json.dumps(events)   # whitelisted fields only
    pause, unpause = events["rows"]
    assert (stamps["onsetCommandIssuedMonotonicOffsetSeconds"] <= pause["monotonicOffsetSeconds"]
            <= stamps["onsetCommandReturnedMonotonicOffsetSeconds"])
    assert (stamps["revertCommandIssuedMonotonicOffsetSeconds"] <= unpause["monotonicOffsetSeconds"]
            <= stamps["revertCommandReturnedMonotonicOffsetSeconds"])
    for row in events["rows"]:
        assert row["monotonicOffsetSeconds"] == pytest.approx(
            _offset(receipt, {"timeNano": row["timeNano"]}), abs=1e-9)
    # The query ran after the readiness and was filtered to the target and the two actions.
    argv = events["command"]
    assert argv[:4] == ["timeout", "30", "docker", "events"] and f"container={fake.target}" in argv
    assert {"event=pause", "event=unpause"} <= set(argv)
    assert freeze["clock"]["collectedMonotonicOffsetSeconds"] >= receipt["readiness"]["observedAtMonotonicOffsetSeconds"]
    assert [row["phase"] for row in freeze["readbacks"]] == ["manifested", "hold-midpoint", "hold-end"]
    assert all(row["paused"] is True and row["nanoCpus"] is None
               and row["issuedMonotonicOffsetSeconds"] <= row["returnedMonotonicOffsetSeconds"]
               for row in freeze["readbacks"])
    assert [row["issuedMonotonicOffsetSeconds"] for row in freeze["readbacks"]] == [
        sample["observedAtMonotonicOffsetSeconds"] for sample in receipt["duringStateSamples"]]


def test_a_throttle_records_command_and_applied_state_readback_stamps_and_no_events(btree, tmp_path, monkeypatch):
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch, ncpu=24)
    timing = _b_timing("persistence-cpu-throttle-effect", 10.0, 1)
    receipt, barrier = sw._inject(producer, clock, fake, tmp_path, "persistence-cpu-throttle", timing)
    assert receipt["successful"] is True, receipt["error"]
    freeze = receipt["sweep"]["freezeStamps"]
    stamps = receipt["sweep"]["commandStamps"]
    assert freeze["scenario"] == "persistence-cpu-throttle" and freeze["events"] is None and freeze["clock"] is None
    assert freeze["commands"]["onsetIssuedMonotonicOffsetSeconds"] == stamps["onsetCommandIssuedMonotonicOffsetSeconds"]
    assert freeze["commands"]["onsetReturnedMonotonicOffsetSeconds"] == stamps["onsetCommandReturnedMonotonicOffsetSeconds"]
    assert all(row["nanoCpus"] == 100_000_000 and row["paused"] is False for row in freeze["readbacks"])
    first = freeze["readbacks"][0]
    assert stamps["onsetCommandReturnedMonotonicOffsetSeconds"] <= first["issuedMonotonicOffsetSeconds"] \
        <= first["returnedMonotonicOffsetSeconds"]
    assert not any(args[:4] == ["timeout", "30", "docker", "events"] for _, args in fake.calls)
    assert probes_inside(fake.calls, barrier, stamps["onsetCommandIssuedMonotonicOffsetSeconds"],
                         receipt["sweep"]["probePolicy"]["noProbeUntilMonotonicOffsetSeconds"]) == []


def test_a_failed_events_query_is_recorded_as_a_missing_h4_record_and_does_not_block(btree, tmp_path, monkeypatch):
    """Decision 69: record, don't block.  The receipt stays successful, the freeze record says missing and why."""
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch, events_rc=1)
    timing = _b_timing("auth-freeze-effect")
    receipt, _ = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    freeze = receipt["sweep"]["freezeStamps"]
    events = freeze["events"]
    assert receipt["successful"] is True and events["returnCode"] == 1 and "daemon unreachable" in events["error"]
    assert events["rows"] == []
    assert (freeze["status"], freeze["failureCount"]) == ("missing", 1)
    assert len(freeze["failures"]) == 1 and "docker events query" in freeze["failures"][0]
    assert freeze["commands"]["onsetIssuedMonotonicOffsetSeconds"] == receipt["sweep"]["commandStamps"][
        "onsetCommandIssuedMonotonicOffsetSeconds"]           # the fallback interval's ends are still there
    validator = btree["validator"]
    assert validator._fault_harness_problem(receipt, receipt["sweep"], b.FAULT_HARNESS, timing, "auth-freeze") is None
    assert validator._freeze_stamp_problems(receipt, receipt["sweep"], b.FAULT_HARNESS, timing, "auth-freeze") == [
        "producer: " + freeze["failures"][0]]


@pytest.mark.parametrize("plant", ["two-pause-events", "wrong-container", "collection-raises"])
def test_every_producer_side_h4_failure_is_a_counted_reason_not_an_error(btree, tmp_path, monkeypatch, plant):
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch)
    if plant == "two-pause-events":
        real = fake.__call__

        def doubled(args, *, output=None, check=True):
            result = real(args, output=output, check=check)
            if args[:3] == ["timeout", "30", "docker"]:
                lines = result.stdout.splitlines(keepends=True)
                result.stdout = lines[0] + lines[0] + lines[1]
            return result
        monkeypatch.setattr(producer, "command", doubled)
    elif plant == "wrong-container":
        real = fake.__call__

        def other(args, *, output=None, check=True):
            result = real(args, output=output, check=check)
            if args[:3] == ["timeout", "30", "docker"]:
                result.stdout = result.stdout.replace(fake.target, "d" * 64)
            return result
        monkeypatch.setattr(producer, "command", other)
    else:
        monkeypatch.setattr(producer, "collect_freeze_events", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    receipt, _ = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", _b_timing("auth-freeze-effect"))
    freeze = receipt["sweep"]["freezeStamps"]
    assert receipt["successful"] is True and receipt["error"] is None
    assert (freeze["status"], freeze["failureCount"]) == ("missing", 1) and len(freeze["failures"]) == 1


def test_a_cell_without_the_harness_declaration_keeps_the_sweeps_receipt_and_asks_no_docker_events(
        stree, btree, tmp_path, monkeypatch):
    """B's producer, given the sweep's timing (no faultHarness): the receipt is the sweep's and no events query runs."""
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch)
    receipt, _ = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", sw._cell_timing(1.0, "auth-freeze-effect"))
    assert receipt["successful"] is True
    assert set(receipt["sweep"]) == {"schemaVersion", "onsetSource", "commandStamps", "probes", "throttle"}
    assert not any("events" in args for _, args in fake.calls)


@pytest.mark.parametrize("plant", ["version", "extra-key"])
def test_an_unknown_harness_declaration_is_refused_before_any_command(btree, tmp_path, monkeypatch, plant):
    producer = btree["producer"]
    clock, fake = _b_kit(producer, monkeypatch)
    timing = copy.deepcopy(_b_timing("auth-freeze-effect"))
    timing["faultHarness"] = {**timing["faultHarness"], "version": "h4-h10-v2"} if plant == "version" else "yes"
    with pytest.raises(ValueError, match="unknown fault harness"):
        sw._inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    assert fake.calls == []


# ----------------------------------------------------------- 6. sealed B cells and the validator (H10 and H4 checks)
@pytest.fixture
def as_b(monkeypatch):
    """sw.make_sweep_run writes the receipt's studyEpoch from its module constant; seal B cells with it."""
    monkeypatch.setattr(sw, "SWEEP", B)


def _extras(intervention: dict, timing: dict) -> dict:
    """The H10 and H4 records a correct producer writes for ``intervention`` (built from its own stamps)."""
    stamps = intervention["sweep"]["commandStamps"]
    issued = stamps["onsetCommandIssuedMonotonicOffsetSeconds"]
    returned = stamps["onsetCommandReturnedMonotonicOffsetSeconds"]
    reverting = stamps["revertCommandIssuedMonotonicOffsetSeconds"]
    reverted = stamps["revertCommandReturnedMonotonicOffsetSeconds"]
    scored_end = timing["faultOnsetSeconds"] + timing["faultHoldSeconds"]
    pause = intervention["scenario"] == "auth-freeze"
    barrier_wall = sw.MEASUREMENT.timestamp()
    collected_mono = intervention["readiness"]["observedAtMonotonicOffsetSeconds"] + 0.5
    clock = events = None
    if pause:
        clock = {"barrierWallEpochSeconds": barrier_wall, "barrierMonotonicOffsetSeconds": 0.0,
                 "collectedWallEpochSeconds": barrier_wall + collected_mono,
                 "collectedMonotonicOffsetSeconds": collected_mono, "mapping": "offset = ..."}
        rows = []
        for action, at in (("pause", issued + 0.1), ("unpause", reverting + 0.1)):
            time_ns = int(round((barrier_wall + at) * 1e9))
            rows.append({"action": action, "type": "container", "containerId": intervention["targetContainerId"],
                         "timeNano": time_ns, "monotonicOffsetSeconds": (time_ns / 1e9 - barrier_wall) * (
                             collected_mono / (collected_mono))})
        events = {"command": ["timeout", "30", "docker", "events"], "returnCode": 0, "error": None, "rows": rows}
    return {
        "probePolicy": {"version": "h4-h10-v1", "noProbeFromMonotonicOffsetSeconds": issued,
                        "scoredWindowEndMonotonicOffsetSeconds": scored_end,
                        "noProbeUntilMonotonicOffsetSeconds": max(scored_end, reverted)},
        "freezeStamps": {
            "schemaVersion": 1, "version": "h4-h10-v1", "scenario": intervention["scenario"],
            "targetContainerId": intervention["targetContainerId"], "toleranceSeconds": 0.25,
            "commands": {"onsetIssuedMonotonicOffsetSeconds": issued, "onsetReturnedMonotonicOffsetSeconds": returned,
                         "revertIssuedMonotonicOffsetSeconds": reverting,
                         "revertReturnedMonotonicOffsetSeconds": reverted},
            "readbacks": [
                {"phase": sample["phase"], "issuedMonotonicOffsetSeconds": sample["observedAtMonotonicOffsetSeconds"],
                 "returnedMonotonicOffsetSeconds": sample["observedAtMonotonicOffsetSeconds"] + 0.04,
                 "paused": sample["state"]["paused"], "nanoCpus": sample["state"].get("nanoCpus")}
                for sample in intervention["duringStateSamples"]],
            "clock": clock, "events": events, "status": "recorded", "failures": [], "failureCount": 0,
        },
    }


def _seal_b(tree: dict, path: Path, cell: dict) -> Path:
    root = sw.make_sweep_run(tree, path, cell)
    if cell["timing"]["faultHarness"] is not None:
        sw._mutate(tree, root, "intervention.json",
                   lambda iv: iv["sweep"].update(_extras(iv, cell["timing"])))
    return root


def _verdict(tree: dict, root: Path, cell: dict) -> list:
    return sw._failed_gates(tree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]}))


@pytest.mark.parametrize("regime,rate", [(regime, rate) for regime in REGIMES for rate in RATES])
def test_a_sealed_b_cell_is_accepted_at_every_regime_and_rate(btree, tmp_path, as_b, regime, rate):
    cell = _cell(regime, rate, block=3)
    root = _seal_b(btree, tmp_path / "run", cell)
    report = btree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", sw._failed_gates(report)
    gates = report["protocolGates"]
    assert gates["failedGates"] == [] and gates["blocking"] == (
        ["F1", "G1", "G2", "G4"] if cell["timing"]["faultApplied"] else ["G1", "G2", "G4"])
    if cell["timing"]["faultApplied"]:
        assert _h4_of(report) == {"status": "recorded", "reasons": [], "failureCount": 0}


PAUSE_PLANTS = [
    "pause-event-late", "pause-event-early", "unpause-event-late", "pause-event-missing", "duplicate-pause",
    "events-query-failed", "events-nonzero-return", "event-other-container", "offset-not-from-time",
    "events-collected-before-readiness", "events-absent", "clock-absent", "extra-event-field",
    "readback-not-paused", "readback-unordered", "readback-count", "commands-differ", "tolerance-changed",
    "tolerance-loosened-in-record", "scenario-wrong", "version-wrong", "container-wrong",
    "policy-window-forged", "policy-missing", "policy-scored-end-forged", "probe-inside-window",
    "freeze-missing", "freeze-key-removed", "freeze-key-absent", "producer-marked-missing",
    "status-failures-disagree", "failure-count-wrong",
]
# H10 and the receipt's own shape block the cell; every H4 defect is recorded as a missing record, never a block.
BLOCKING_PLANTS = {"policy-window-forged", "policy-missing", "policy-scored-end-forged", "probe-inside-window",
                   "freeze-key-absent"}


def _h4_of(report: dict) -> dict:
    row = next(row for row in report["validationTable"] if row["gate"] == "sweep-fault-command-stamps")
    return row["observation"]["h4"]


def _check_plant(tree: dict, root: Path, cell: dict, plant: str, blocking: set) -> None:
    report = tree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    failed = sw._failed_gates(report)
    if plant in blocking:
        assert "sweep-fault-command-stamps" in failed
        return
    assert failed == [] and report["verdict"] == "pass", failed       # an H4 failure must NOT block the cell
    h4 = _h4_of(report)
    assert h4["status"] == "missing" and h4["failureCount"] == len(h4["reasons"]) >= 1


@pytest.mark.parametrize("plant", PAUSE_PLANTS)
def test_planted_h4_defects_are_recorded_and_h10_defects_block_a_pause_cell(btree, tmp_path, as_b, plant):
    cell = _cell("auth-freeze-effect", 0.2, block=2)
    root = _seal_b(btree, tmp_path / "run", cell)
    assert _verdict(btree, root, cell) == []

    def mutate(intervention):
        sweep_record = intervention["sweep"]
        freeze, policy = sweep_record["freezeStamps"], sweep_record["probePolicy"]
        events = freeze["events"]
        if plant == "pause-event-late":
            events["rows"][0]["timeNano"] += int(1.0e9)
            events["rows"][0]["monotonicOffsetSeconds"] += 1.0
        elif plant == "pause-event-early":
            events["rows"][0]["timeNano"] -= int(1.0e9)
            events["rows"][0]["monotonicOffsetSeconds"] -= 1.0
        elif plant == "unpause-event-late":
            events["rows"][1]["timeNano"] += int(2.0e9)
            events["rows"][1]["monotonicOffsetSeconds"] += 2.0
        elif plant == "pause-event-missing":
            events["rows"] = events["rows"][1:]
        elif plant == "duplicate-pause":
            events["rows"] = [events["rows"][0], events["rows"][0], events["rows"][1]]
        elif plant == "events-query-failed":
            events["error"] = "TimeoutError: docker events"
        elif plant == "events-nonzero-return":
            events["returnCode"] = 124
        elif plant == "event-other-container":
            events["rows"][0]["containerId"] = "d" * 64
        elif plant == "offset-not-from-time":
            events["rows"][0]["monotonicOffsetSeconds"] += 0.01
        elif plant == "events-collected-before-readiness":
            freeze["clock"]["collectedMonotonicOffsetSeconds"] = 1.0
        elif plant == "events-absent":
            freeze["events"] = None
        elif plant == "clock-absent":
            freeze["clock"] = None
        elif plant == "extra-event-field":
            events["rows"][0]["attributes"] = {"name": "x"}
        elif plant == "readback-not-paused":
            freeze["readbacks"][1]["paused"] = False
        elif plant == "readback-unordered":
            freeze["readbacks"][0]["returnedMonotonicOffsetSeconds"] = (
                freeze["readbacks"][0]["issuedMonotonicOffsetSeconds"] - 0.01)
        elif plant == "readback-count":
            freeze["readbacks"].pop()
        elif plant == "commands-differ":
            freeze["commands"]["onsetIssuedMonotonicOffsetSeconds"] += 0.001
        elif plant == "tolerance-changed":
            freeze["toleranceSeconds"] = 0.5
        elif plant == "tolerance-loosened-in-record":
            freeze["toleranceSeconds"] = 5.0
            events["rows"][0]["timeNano"] += int(3.0e9)
            events["rows"][0]["monotonicOffsetSeconds"] += 3.0
        elif plant == "scenario-wrong":
            freeze["scenario"] = "persistence-cpu-throttle"
        elif plant == "version-wrong":
            freeze["version"] = "h4-h10-v0"
        elif plant == "container-wrong":
            freeze["targetContainerId"] = "d" * 64
        elif plant == "policy-window-forged":
            policy["noProbeUntilMonotonicOffsetSeconds"] -= 5.0
        elif plant == "policy-missing":
            sweep_record["probePolicy"] = None
        elif plant == "policy-scored-end-forged":
            policy["scoredWindowEndMonotonicOffsetSeconds"] -= 30.0
        elif plant == "probe-inside-window":
            sweep_record["probes"][0]["startMonotonicOffsetSeconds"] = policy["scoredWindowEndMonotonicOffsetSeconds"] - 1.0
        elif plant == "freeze-missing":
            sweep_record["freezeStamps"] = None
        elif plant == "freeze-key-removed":
            del freeze["toleranceSeconds"]
        elif plant == "freeze-key-absent":
            del sweep_record["freezeStamps"]
        elif plant == "producer-marked-missing":
            freeze.update(status="missing", failures=["docker events query: TimeoutError"], failureCount=1)
        elif plant == "status-failures-disagree":
            freeze["failures"] = ["x"]
            freeze["failureCount"] = 1
        elif plant == "failure-count-wrong":
            freeze["failureCount"] = 3
    sw._mutate(btree, root, "intervention.json", mutate)
    _check_plant(btree, root, cell, plant, BLOCKING_PLANTS)


THROTTLE_PLANTS = ["quota-not-applied", "readback-missing", "readback-before-command-returned", "events-on-a-throttle",
                   "clock-on-a-throttle", "readback-paused", "policy-window-forged"]


@pytest.mark.parametrize("plant", THROTTLE_PLANTS)
def test_planted_h4_defects_are_recorded_and_h10_defects_block_a_throttle_cell(btree, tmp_path, as_b, plant):
    cell = _cell("persistence-cpu-throttle-effect", 10.0, block=1)
    root = _seal_b(btree, tmp_path / "run", cell)
    assert _verdict(btree, root, cell) == []

    def mutate(intervention):
        sweep_record = intervention["sweep"]
        freeze = sweep_record["freezeStamps"]
        if plant == "quota-not-applied":
            freeze["readbacks"][1]["nanoCpus"] = 0
        elif plant == "readback-missing":
            freeze["readbacks"].pop(0)
        elif plant == "readback-before-command-returned":
            freeze["readbacks"][0]["issuedMonotonicOffsetSeconds"] = (
                freeze["commands"]["onsetReturnedMonotonicOffsetSeconds"] - 0.05)
        elif plant == "events-on-a-throttle":
            freeze["events"] = {"command": [], "returnCode": 0, "error": None, "rows": []}
        elif plant == "clock-on-a-throttle":
            freeze["clock"] = {"barrierWallEpochSeconds": 0.0}
        elif plant == "readback-paused":
            freeze["readbacks"][2]["paused"] = True
        elif plant == "policy-window-forged":
            sweep_record["probePolicy"]["noProbeFromMonotonicOffsetSeconds"] -= 1.0
    sw._mutate(btree, root, "intervention.json", mutate)
    _check_plant(btree, root, cell, plant, {"policy-window-forged"})


def test_a_b_fault_cell_with_the_sweeps_receipt_shape_is_rejected(btree, tmp_path, as_b):
    """Downgrade: a receipt without the H10/H4 records for a cell whose plan declares them."""
    cell = _cell("auth-freeze-effect", 1.0, block=1)
    root = sw.make_sweep_run(btree, tmp_path / "run", cell)
    assert "sweep-fault-command-stamps" in _verdict(btree, root, cell)


def test_a_sweep_cell_that_carries_the_records_is_rejected(stree, tmp_path):
    """Upgrade: the H10/H4 records on a cell whose compiled timing declares no harness (the sweep's own cell)."""
    cell = sw._cell("persistence-cpu-throttle-effect", 0.2)
    root = sw.make_sweep_run(stree, tmp_path / "run", cell)
    assert sw._failed_gates(stree["validator"].validate_run(root, expected=cell["runKey"])) == []
    sw._mutate(stree, root, "intervention.json", lambda iv: iv["sweep"].update(_extras(iv, cell["timing"])))
    assert "sweep-fault-command-stamps" in sw._failed_gates(stree["validator"].validate_run(root, expected=cell["runKey"]))


def test_the_window_rule_is_not_vacuous_when_the_scored_window_outlasts_the_revert(btree):
    """H10 for a window that ends after the revert returned: a probe starting there is inside the window."""
    cell = _cell("auth-freeze-effect", 1.0, block=1)
    intervention = sw._intervention(cell["timing"], "auth-freeze-effect")
    intervention["sweep"].update(_extras(intervention, cell["timing"]))
    validator = btree["validator"]
    assert validator._fault_harness_problem(
        intervention, intervention["sweep"], b.FAULT_HARNESS, cell["timing"], "auth-freeze") is None
    longer = {**cell["timing"], "faultHoldSeconds": cell["timing"]["faultHoldSeconds"] + 10}
    problem = validator._fault_harness_problem(
        intervention, intervention["sweep"], b.FAULT_HARNESS, longer, "auth-freeze")
    assert problem is not None and "probePolicy window" in problem
    intervention["sweep"]["probePolicy"].update(
        scoredWindowEndMonotonicOffsetSeconds=cell["timing"]["faultOnsetSeconds"] + 70,
        noProbeUntilMonotonicOffsetSeconds=cell["timing"]["faultOnsetSeconds"] + 70)
    problem = validator._fault_harness_problem(
        intervention, intervention["sweep"], b.FAULT_HARNESS, longer, "auth-freeze")
    assert problem is not None and "inside the no-probe window" in problem


def test_the_b_campaign_replays_its_own_allocation(btree, tmp_path, monkeypatch, as_b):
    adapter = btree["adapter"]
    monkeypatch.setattr(adapter, "_git_repository_state", sw._git_state(adapter))
    root = tmp_path / "campaign"
    materialized = btree["orchestrator"].materialize_campaign(root)
    assert len(materialized["cells"]) == 36
    for row, cell in zip(materialized["campaign"]["runs"], materialized["cells"]):
        assert row["runId"] == cell["runId"]
        _seal_b(btree, root / row["path"], cell)
    report = btree["validator"].validate_campaign(root)
    assert report["verdict"] == "pass", [(r["runKey"], sw._failed_gates(r)) for r in report["runReports"]]
    assert len(report["runReports"]) == 36
    campaign = json.loads((root / "campaign.json").read_text())
    campaign["runs"][0], campaign["runs"][1] = campaign["runs"][1], campaign["runs"][0]
    sw._json(root / "campaign.json", campaign)
    assert "scheduled-cell-population" in sw._failed_gates(btree["validator"].validate_campaign(root))


def test_the_terminal_requires_the_fault_artifacts_of_b_regimes(btree):
    terminal = btree["terminal"]
    key = {"studyEpoch": B, "regime": "no-fault-cost", "block": 1, "posture": "full", "attempt": 1}
    assert {"application.log", "resources.json"} <= terminal._required_for(key)
    for regime in ("auth-freeze-effect", "persistence-cpu-throttle-effect"):
        assert {"application.log", "intervention.json"} <= terminal._required_for({**key, "regime": regime})
    with pytest.raises(terminal.TerminalError):
        terminal._required_for({**key, "regime": "persistence-crash-effect"})


# ------------------------------------------------------------------------------------------ 7. the 3.9 floor
@pytest.mark.parametrize("relative", B_TARGET_FILES)
def test_b_target_files_parse_at_the_python39_floor(relative):
    tree_ = ast.parse((MODULE / relative).read_text(), feature_version=(3, 9))
    assert any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
               and any(alias.name == "annotations" for alias in node.names) for node in tree_.body), relative


def _unbound_in_functions(path: Path) -> list:
    """Names loaded inside a function that no scope in the file ever binds (the class of the Hotel #6 NameError)."""
    tree_ = ast.parse(path.read_text())
    import builtins
    bound = set(dir(builtins)) | {"__file__", "__doc__"}
    for node in ast.walk(tree_):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return sorted({node.id for node in ast.walk(tree_) if isinstance(node, ast.Name)
                   and isinstance(node.ctx, ast.Load) and node.id not in bound})


@pytest.mark.parametrize("relative", B_TARGET_FILES)
def test_no_name_is_loaded_that_is_bound_nowhere_in_the_files_b_touches(relative):
    assert _unbound_in_functions(MODULE / relative) == []


def test_the_unbound_name_scan_finds_a_planted_unbound_name(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("def f(values):\n    return sum(v for v in values if v > threshold)\n")
    assert _unbound_in_functions(planted) == ["threshold"]


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_the_b_runtime_imports_under_system_python_isolated(tmp_path):
    root = sw._copy_tree(tmp_path / "tree", B_SELECTOR)
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
    relatives = [f"modules/teastore/{relative}" for relative in sw.CHANGED_TARGET_FILES + ("execution/candidate_sweep_b.py",)]
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script,
         str(root), *relatives],
        capture_output=True, text=True, cwd=root,
    )
    assert result.returncode == 0 and result.stdout.startswith(f"ok {B} 36"), result.stderr[-2000:]
