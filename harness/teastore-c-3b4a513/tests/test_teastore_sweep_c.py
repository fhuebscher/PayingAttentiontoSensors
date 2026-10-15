"""teastore-traffic-sweep-c-v1: campaign C, campaign B's shape with new blocks, run IDs and draws (BUDGET_C.md).

Covers: the 36-cell plan (3 blocks x 12 (regime, rate) pairs) is deterministic and pinned, with seed 20261011 and
schedule version sweep-c-schedule-v1; each block's order is recomputed from the recorded encoding; no C run ID equals a
sweep, quiet (A and A2 share theirs) or campaign-B run ID; every cell equals campaign B's cell of the same regime and
rate apart from the seeded onset and the phase floors that follow from it (so the H10/H4 declaration, doses and gates are
B's); the plan and the descriptor differ from B's only where the epoch differs; the budget is B's; the sweep, quiet and
B epochs are byte-identical to bb3717e (A2's harness) and, under B's selector, the runtime is the bb3717e runtime; the C
selector activates the epoch in every runtime file; materialize -> inspect -> contracts -> package for all 36 cells;
H10 and H4 act on C fault cells (real fault controller against a faked Docker; sealed cells and planted defects through
the real validator); the 3.9 floor and digest identity.

Every epoch is exercised in a copy of the module tree with its own selector (the fixtures of
tests/test_teastore_sweep_b.py), so these tests do not depend on which selector the worktree has committed.
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
import test_teastore_sweep_b as tb
import test_teastore_traffic_sweep as sw


ROOT = sw.ROOT
MODULE = sw.MODULE
SWEEP = sw.SWEEP
QUIET = qc.QUIET
B = tb.B
C = "teastore-traffic-sweep-c-v1"
RATES = sw.RATES
REGIMES = tb.REGIMES
A2_COMMIT = "bb3717e8adeeaa05a45fd8e587cee481da206ac7"         # quiet run A2's harness (HEAD before C)
B_COMMIT = "bbb6b1165410be5bd4eb304b56c4eac9490310d1"          # campaign B's harness
C_SELECTOR = {"schemaVersion": 1, "studyEpoch": C}
B_SELECTOR = tb.B_SELECTOR
SWEEP_PLAN_SHA256 = tb.SWEEP_PLAN_SHA256
QUIET_PLAN_SHA256 = tb.QUIET_PLAN_SHA256
B_DESCRIPTOR_SHA256 = "d4d846337263f57bfe2b9a0d8de8f0f9cde319157ad8e7611b62faecfe99b7c7"
B_PLAN_SHA256 = "aa3469708cc7f27f3262e12a6293a4a77bc6af1ec9e06cc4156f8bdd123101db"
# What C may change relative to bb3717e under the harness directories; every other file must be byte-identical.
C_CHANGED = {
    "modules/teastore/execution/study_epoch.py",            # the selector accepts C's document
    "modules/teastore/extension-ledger.yaml",               # C's compiler classified; selector text
    "modules/teastore/execution/study-epoch.json",          # the activation commit points it at campaign C
}
C_ADDED = {"modules/teastore/execution/candidate_sweep_c.py", "pipelines/campaigns/teastore-traffic-sweep-c-v1.json"}
C_TARGET_FILES = ("execution/candidate_sweep_c.py", "execution/study_epoch.py")
# The timing keys C sets itself (the seeded onset and the floors that follow from it); everything else is B's.
ONSET_KEYS = {"faultOnsetPhaseOffsetSeconds", "faultOnsetSeconds", "scoredWindowSeconds", "minimumActualStartsByPhase"}

c = sw.load("teastore_sweep_c_compiler_test", MODULE / "execution/candidate_sweep_c.py")
b = tb.b
quiet = qc.quiet
sweep = sw.sweep


@pytest.fixture(scope="module")
def ctree(tmp_path_factory):
    """Modules loaded from a tree copy whose selector names campaign C."""
    return tb._tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-c-tree"), C_SELECTOR))


@pytest.fixture(scope="module")
def btree_now(tmp_path_factory):
    """Modules of this commit under campaign B's selector."""
    return tb._tree(sw._copy_tree(tmp_path_factory.mktemp("teastore-c-b-tree"), B_SELECTOR))


def _a2_tree(destination: Path, selector: dict) -> Path:
    """The same subset of the tree as sw._copy_tree, taken from bb3717e, with the given selector written in."""
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", A2_COMMIT, "modules/teastore", "pipelines/campaigns",
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
def base_b(tmp_path_factory):
    """bb3717e's modules under campaign B's selector (the runtime campaign B's relaunch would get without C)."""
    return tb._tree(_a2_tree(tmp_path_factory.mktemp("teastore-c-base-b"), B_SELECTOR))


@pytest.fixture
def as_c(monkeypatch):
    """sw.make_sweep_run writes the receipt's studyEpoch from its module constant; seal C cells with it."""
    monkeypatch.setattr(sw, "SWEEP", C)


def _plan() -> dict:
    return c.compile_plan(c.load_descriptor())


def _cells() -> list:
    return c.flatten_cells(_plan())


def _cell(regime: str, rate: float, block: int = 1) -> dict:
    return next(cell for cell in _cells() if cell["runKey"]["regime"] == regime
                and cell["timing"]["journeysPerSecond"] == rate and cell["runKey"]["block"] == block)


def _run_ids(plan: dict) -> set:
    return {cell["runId"] for block in plan["blocks"] for cell in block["cells"]}


# ---------------------------------------------------------------------- 0. the activation (the committed selector)
def test_the_committed_selector_names_campaign_c_and_the_tree_runs_it():
    """The worktree's own selector (not a copy) activates C: what the drivers and the release read at this commit."""
    assert json.loads((ROOT / "modules/teastore/execution/study-epoch.json").read_text()) == C_SELECTOR
    epoch = sw.load("teastore_c_committed_epoch", MODULE / "execution/study_epoch.py")
    active = epoch.active(ROOT)
    assert (active["studyEpoch"], active["runCount"], active["runWindowHours"]) == (C, 36, 6)
    assert active["compilerRelative"] == "modules/teastore/execution/candidate_sweep_c.py"
    assert epoch.sweep_compiler(ROOT).EXPECTED_PLAN_SHA256 == c.EXPECTED_PLAN_SHA256


# ------------------------------------------------------------------------------------------- 1. the campaign-C plan
def test_c_plan_is_36_cells_3_blocks_deterministic_and_pinned():
    descriptor = c.load_descriptor()
    assert c.canonical_sha256(descriptor) == c.EXPECTED_DESCRIPTOR_SHA256
    # The checked-in descriptor is the generator's output, byte for byte (regenerate, never hand-edit).
    assert c.DEFAULT_DESCRIPTOR.read_bytes() == c.descriptor_bytes()
    first, second = c.compile_plan(descriptor), c.compile_plan(copy.deepcopy(descriptor))
    assert first == second and c.canonical_sha256(first) == c.EXPECTED_PLAN_SHA256
    assert c.validate_plan(descriptor, first) is first
    assert first["runCount"] == c.TOTAL_RUNS == 36 and first["studyEpoch"] == C
    assert descriptor["schedule"]["seed"] == c.SCHEDULE_SEED == 20261011
    assert len({c.SCHEDULE_SEED, b.SCHEDULE_SEED, sweep.SCHEDULE_SEED, quiet.SCHEDULE_SEED}) == 4    # new draws
    assert descriptor["schedule"]["version"] == "sweep-c-schedule-v1" and descriptor["schedule"]["leadCell"] is None
    cells = c.flatten_cells(first)
    assert len(cells) == 36 and len({cell["runId"] for cell in cells}) == 36
    assert [block["block"] for block in first["blocks"]] == [1, 2, 3]
    pairs = sorted((regime, float(rate)) for regime in REGIMES for rate in RATES)
    for block in first["blocks"]:
        assert sorted((x["runKey"]["regime"], x["timing"]["journeysPerSecond"]) for x in block["cells"]) == pairs
        assert [x["ordinalPosition"] for x in block["cells"]] == list(range(1, 13))
    assert len({tuple(block["order"]) for block in first["blocks"]}) == 3


def test_no_c_run_id_equals_a_sweep_quiet_or_b_run_id():
    """Blocks are keyed by the epoch name (b01-b03 under teastore-traffic-sweep-c-v1/), not renumbered 4-6."""
    mine = _run_ids(_plan())
    assert all(run_id.startswith(C + "/") and run_id.endswith("/full/a01") for run_id in mine)
    others = {
        "sweep": _run_ids(sweep.compile_plan(sweep.load_descriptor())),
        "quiet A/A2": _run_ids(quiet.compile_plan(quiet.load_descriptor())),
        "B": _run_ids(b.compile_plan(b.load_descriptor())),
    }
    assert [len(others[name]) for name in ("sweep", "quiet A/A2", "B")] == [12, 40, 36]
    for name, run_ids in others.items():
        assert not mine & run_ids, name
    # Not by luck: C's run IDs are B's strings with the epoch segment replaced, one for one.
    assert {run_id.replace(C + "/", B + "/", 1) for run_id in mine} == others["B"]
    # The runtime's own parser refuses a B run ID as a C run ID, and the other way round.
    with pytest.raises(c.ProtocolError):
        c._run_id_parts(sorted(others["B"])[0])
    with pytest.raises(b.ProtocolError):
        b._run_id_parts(sorted(mine)[0])


def test_the_run_id_collision_check_catches_a_planted_collision(monkeypatch):
    """Planted defect for the test above: C compiled under B's epoch name collides with B in all 36 run IDs."""
    monkeypatch.setattr(c, "EPOCH", B)
    planted = {c.run_id_for(row["regime"], row["rate"], block, "full")
               for block in (1, 2, 3) for row in c.block_order(block)}
    assert planted == _run_ids(b.compile_plan(b.load_descriptor()))


def test_the_order_is_recomputed_from_the_recorded_encoding():
    descriptor = c.load_descriptor()
    schedule = descriptor["schedule"]
    assert schedule["drawEncoding"] == "UTF-8(seed || NUL || epoch || NUL || block-NN || NUL || draw-i || NUL || version)"
    for receipt in schedule["blocks"]:
        pairs = [(regime, float(rate)) for regime in REGIMES for rate in RATES]
        for index in range(len(pairs) - 1, 0, -1):          # the recorded Fisher-Yates, written out again
            text = "\0".join([str(schedule["seed"]), C, "block-%02d" % receipt["block"], "draw-%d" % index,
                              schedule["version"]])
            draw = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
            other = draw % (index + 1)
            pairs[index], pairs[other] = pairs[other], pairs[index]
        expected = [c.run_id_for(regime, rate, receipt["block"], "full") for regime, rate in pairs]
        assert receipt["runIds"] == expected
        assert receipt["orderSha256"] == c.canonical_sha256(expected)


def test_with_bs_seed_epoch_and_version_the_rules_reproduce_bs_order_and_onsets():
    """C's draws are B's functions with C's arguments: given B's values they give B's schedule and onsets back."""
    pairs = [{"regime": regime, "rate": float(rate)} for regime in REGIMES for rate in RATES]
    for block in (1, 2, 3):
        assert c.fisher_yates(pairs, b.SCHEDULE_SEED, B, block, b.SCHEDULE_CONTEXT) == b.block_order(block)
    for cell in b.flatten_cells(b.compile_plan(b.load_descriptor())):
        rate, regime = cell["timing"]["journeysPerSecond"], cell["runKey"]["regime"]
        assert c.stratified_onset_offset(b.SCHEDULE_SEED, B, 3, cell["runId"], regime, rate,
                                         cell["runKey"]["block"]) == cell["timing"]["faultOnsetPhaseOffsetSeconds"]


# -------------------------------------------------------------------------------------- 2. B's shape, exactly
def test_every_cell_is_bs_cell_but_for_the_onset():
    strata = {}
    moved = 0
    for cell in _cells():
        timing, regime, rate = cell["timing"], cell["runKey"]["regime"], cell["timing"]["journeysPerSecond"]
        block = cell["runKey"]["block"]
        twin = b.compiled_cell(b.run_id_for(regime, rate, block, "full"))     # B's cell, same (regime, rate, block)
        assert set(timing) == set(twin["timing"])
        assert {key for key in timing if timing[key] != twin["timing"][key]} <= ONSET_KEYS == set(c.ONSET_TIMING_KEYS)
        assert {key: value for key, value in cell.items() if key not in ("runId", "runKey", "ordinalPosition", "timing")} \
            == {key: value for key, value in twin.items() if key not in ("runId", "runKey", "ordinalPosition", "timing")}
        assert cell["runKey"] == {**twin["runKey"], "studyEpoch": C}
        moved += timing["faultOnsetPhaseOffsetSeconds"] != twin["timing"]["faultOnsetPhaseOffsetSeconds"]
        offset = timing["faultOnsetPhaseOffsetSeconds"]
        assert timing["faultOnsetSeconds"] == round(60 + offset, 6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"], round(timing["faultOnsetSeconds"] + 60, 6)]
        assert 0.0 <= offset < 1.0 / rate
        strata.setdefault((regime, rate), []).append(int(offset * rate * 3))
        if regime == "no-fault-cost":
            assert timing["faultHarness"] is None and timing["minimumActualStartsByPhase"] is None
        else:
            assert timing["faultHarness"] == b.FAULT_HARNESS == c.FAULT_HARNESS == {
                "version": "h4-h10-v1", "noProbeDuringFault": True, "freezeStamps": True,
                "freezeFailure": "record-not-block", "freezeEventToleranceSeconds": 0.25}
            assert timing["minimumActualStartsByPhase"] == sweep.phase_floors(rate, 180, timing["faultOnsetSeconds"], 60)
            assert timing["drainAllowanceSeconds"] == 17.0
    # New draws: every one of the 36 onsets differs from B's for the same (regime, rate, block).
    assert moved == 36
    # Each (regime, rate) pair's 3 blocks take the 3 thirds of its inter-arrival, one each (B's stratification).
    assert len(strata) == 12 and all(sorted(values) == [0, 1, 2] for values in strata.values())


def test_the_plan_differs_from_bs_only_where_the_epoch_differs():
    plan, twin = _plan(), b.compile_plan(b.load_descriptor())
    changed = {key for key in set(plan) | set(twin) if plan.get(key) != twin.get(key)}
    assert changed == {"studyEpoch", "descriptorId", "descriptorSha256", "scheduleVersion", "scheduleAllocation",
                       "blocks", "analysisBoundary"}
    for key in ("runCount", "minimumTimedSeconds", "operationalEstimateSeconds", "minimumFirstMutationRemainingSeconds",
                "runWindowHours", "maximumWallSeconds", "missingnessBoundary", "kind", "schemaVersion"):
        assert plan[key] == twin[key], key


def test_the_descriptor_differs_from_bs_only_where_the_epoch_differs():
    descriptor, base = c.load_descriptor(), b.load_descriptor()
    changed = {key for key in set(descriptor) | set(base) if descriptor.get(key) != base.get(key)}
    assert changed == {"id", "declaration", "design", "schedule", "analysis", "continuation", "derivedFrom"}
    assert descriptor["id"] == C
    assert descriptor["declaration"].startswith("research/traffic-sweep/DECLARATION_C_TEASTORE.md ")
    assert {key for key in descriptor["design"] if descriptor["design"][key] != base["design"].get(key)} == {"purpose"}
    assert set(descriptor["design"]) == set(base["design"])
    assert {key for key in descriptor["schedule"] if descriptor["schedule"][key] != base["schedule"].get(key)} == {
        "version", "seed", "blocks"}
    # Same timing (budget, strata, H10/H4 declaration), doses, workload, gates, collection as B (BUDGET_C: nothing else).
    for key in ("timing", "faultParameters", "workload", "protocolGates", "collection", "groundTruth", "outcomes",
                "missingness", "evidence", "targetHost", "source"):
        assert descriptor[key] == base[key], key
    assert descriptor["derivedFrom"]["studyEpoch"] == B
    assert descriptor["derivedFrom"]["descriptorCanonicalSha256"] == B_DESCRIPTOR_SHA256
    assert descriptor["derivedFrom"]["planCanonicalSha256"] == B_PLAN_SHA256
    assert descriptor["derivedFrom"]["descriptorByteSha256"] == hashlib.sha256(
        (ROOT / b.DESCRIPTOR_RELATIVE).read_bytes()).hexdigest()
    assert descriptor["derivedFrom"]["sweepDerivation"] == base["derivedFrom"]
    assert "BUDGET_C.md stop rule 4" in descriptor["analysis"]["analysisFreeze"]
    assert descriptor["continuation"] == {**base["continuation"], "repeatOfEpoch": B}


def test_the_b_shape_checks_catch_a_planted_shape_change(monkeypatch):
    """Planted defect for the two tests above: a C cell with another hold is no longer B's cell."""
    real = b.cell_timing

    def longer_hold(run_id, regime, rate):
        timing = real(run_id, regime, rate)
        timing["faultHoldSeconds"] = timing["faultHoldSeconds"] + 1
        return timing
    monkeypatch.setattr(c.b, "cell_timing", longer_hold)
    cell = c.cell_timing(c.run_id_for("auth-freeze-effect", 1.0, 1, "full"), "auth-freeze-effect", 1.0)
    twin = b.compiled_cell(b.run_id_for("auth-freeze-effect", 1.0, 1, "full"))["timing"]
    assert {key for key in cell if cell[key] != twin[key]} - ONSET_KEYS == {"faultHoldSeconds"}
    monkeypatch.undo()
    monkeypatch.setattr(c.b, "FAULT_HARNESS", {**b.FAULT_HARNESS, "freezeFailure": "block"})
    with pytest.raises(c.ProtocolError, match="campaign B's cell shape changed"):
        c.cell_timing(c.run_id_for("auth-freeze-effect", 1.0, 1, "full"), "auth-freeze-effect", 1.0)


def test_budget_is_bs():
    for name in ("TOTAL_RUNS", "MINIMUM_TIMED_SECONDS", "MINIMUM_FIRST_MUTATION_REMAINING_SECONDS", "RUN_WINDOW_HOURS",
                 "MAXIMUM_WALL_SECONDS", "OPERATIONAL_ESTIMATE_SECONDS", "MEASURED_CELL_PERIOD_SECONDS",
                 "CELL_PERIOD_ESTIMATE_SECONDS", "PREPARE_RESERVE_SECONDS", "CLEANUP_RESERVE_SECONDS", "BLOCKS",
                 "EPISODES", "CELLS_PER_BLOCK", "POSTURES", "RATES", "REGIMES", "FAULTS"):
        assert getattr(c, name) == getattr(b, name), name
    assert (c.RUN_WINDOW_HOURS, c.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS, c.MAXIMUM_WALL_SECONDS) == (6, 19_200, 21_600)


def test_c_exposes_every_name_of_bs_compiler():
    """The runtime calls the sweep-mode compiler by name; C offers every module-level name B offers."""
    names = {name for name in vars(b) if not name.startswith("__")}
    assert names - set(vars(c)) == set()


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_plan_digest_is_identical_under_python39(tmp_path):
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I",
         str(MODULE / "execution/candidate_sweep_c.py")],
        capture_output=True, text=True, check=True,
    )
    report = json.loads(result.stdout)
    assert report["planCanonicalSha256"] == c.EXPECTED_PLAN_SHA256
    assert report["descriptorCanonicalSha256"] == c.EXPECTED_DESCRIPTOR_SHA256
    assert report["runCount"] == 36 and report["runWindowHours"] == 6
    assert report["firstRunId"].startswith(C + "/")


# ------------------------------------------------------------- 3. the sweep, quiet and B epochs unchanged
def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True, text=True).stdout


def _changed_since(commit: str) -> set:
    listing = _git("diff", "--name-only", commit, "--", "modules/teastore", "pipelines/campaigns").split()
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", "modules/teastore",
                     "pipelines/campaigns").split()
    return set(listing) | set(untracked)


def _blob(commit: str, relative: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{relative}"], capture_output=True,
                          check=True).stdout


def test_since_a2_only_c_files_moved_and_the_earlier_epochs_are_byte_identical():
    assert _changed_since(A2_COMMIT) <= C_CHANGED | C_ADDED, _changed_since(A2_COMMIT) - (C_CHANGED | C_ADDED)
    for relative in ("modules/teastore/execution/candidate_sweep.py", sweep.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_quiet.py", quiet.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/candidate_sweep_b.py", b.DESCRIPTOR_RELATIVE,
                     "modules/teastore/execution/performance_campaign.py",
                     "modules/teastore/validation/candidate_pilot.py",
                     "modules/teastore/execution/candidate_pilot.py",
                     "modules/teastore/execution/candidate_runtime_adapter.py"):
        assert (ROOT / relative).read_bytes() == _blob(A2_COMMIT, relative), relative
        # ... and B's harness files are the ones campaign B ran.
        assert (ROOT / relative).read_bytes() == _blob(B_COMMIT, relative), relative
    assert (b.EXPECTED_DESCRIPTOR_SHA256, b.EXPECTED_PLAN_SHA256) == (B_DESCRIPTOR_SHA256, B_PLAN_SHA256)
    assert b.canonical_sha256(b.compile_plan(b.load_descriptor())) == B_PLAN_SHA256
    assert sweep.canonical_sha256(sweep.compile_plan(sweep.load_descriptor())) == SWEEP_PLAN_SHA256
    assert quiet.canonical_sha256(quiet.compile_plan(quiet.load_descriptor())) == QUIET_PLAN_SHA256


def test_the_changed_file_check_catches_a_planted_harness_edit():
    """Planted defect for the test above: a C-time edit of B's compiler is outside the allowed set."""
    planted = _changed_since(A2_COMMIT) | {"modules/teastore/execution/candidate_sweep_b.py"}
    assert not planted <= C_CHANGED | C_ADDED


def test_under_bs_selector_the_runtime_is_the_bb3717e_runtime(btree_now, base_b, tmp_path, monkeypatch):
    """Campaign B (and its relaunches) get the same contracts as before C, except the study-epoch loader's digest."""
    assert btree_now["epoch"].active(btree_now["root"]) == base_b["epoch"].active(base_b["root"])
    assert btree_now["adapter"].CONTROLLER_PATHS == base_b["adapter"].CONTROLLER_PATHS
    left = qc._contracts(btree_now, tmp_path / "now", B, monkeypatch)
    right = qc._contracts(base_b, tmp_path / "base", B, monkeypatch)
    assert left[0]["campaignSha256"] == right[0]["campaignSha256"]
    assert left[1].plan_sha256 == right[1].plan_sha256 == B_PLAN_SHA256 and left[1].run_ids == right[1].run_ids
    moved = {name for name, relative in btree_now["adapter"].CONTROLLER_PATHS.items()
             if relative == "modules/teastore/execution/study_epoch.py"}
    assert moved == {"study-epoch-loader"}
    assert {name for name in left[1].controller_sha256
            if left[1].controller_sha256[name] != right[1].controller_sha256[name]} == moved
    assert len(left[3]) == len(right[3]) == 36
    for one, other in zip(left[3], right[3]):
        assert qc._mask_moved_digests(one, moved) == qc._mask_moved_digests(other, moved)


# ---------------------------------------------------------------------------------------------- 4. the selector
@pytest.mark.parametrize("selector,expected", [(None, SWEEP), (tb.SWEEP_SELECTOR, SWEEP), (tb.QUIET_SELECTOR, QUIET),
                                                (B_SELECTOR, B), (C_SELECTOR, C)])
def test_the_sweep_mode_compiler_follows_the_selector(tmp_path, selector, expected):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_c_resolution_epoch", root / "modules/teastore/execution/study_epoch.py")
    assert epoch.sweep_compiler(root).EPOCH == expected


def test_the_selector_activates_campaign_c(ctree):
    epoch = ctree["epoch"].active(ctree["root"])
    assert epoch == {
        "studyEpoch": C, "sweep": True, "runCount": 36, "minimumFirstMutationRemainingSeconds": 19_200,
        "descriptorRelative": "pipelines/campaigns/teastore-traffic-sweep-c-v1.json",
        "compilerRelative": "modules/teastore/execution/candidate_sweep_c.py", "scheduleVersion": "sweep-c-schedule-v1",
        "outerLeaseScope": "entire-36-cell-one-shot", "regimes": REGIMES,
        "scenarios": {"no-fault-cost": None, "auth-freeze-effect": "auth-freeze",
                      "persistence-cpu-throttle-effect": "persistence-cpu-throttle"},
        "postures": ("full",), "blocksPerRegime": 3, "maximumOrdinal": 12,
        "selectorRelative": "modules/teastore/execution/study-epoch.json", "runWindowHours": 6,
        "maximumWallSeconds": 21_600,
        "additionalControllerPaths": {
            "sweep-compiler": "modules/teastore/execution/candidate_sweep.py",
            "sweep-descriptor": "pipelines/campaigns/teastore-traffic-sweep-v1.json",
            "sweep-b-compiler": "modules/teastore/execution/candidate_sweep_b.py",
            "sweep-b-descriptor": "pipelines/campaigns/teastore-traffic-sweep-b-v1.json",
            "sweep-c-descriptor": "pipelines/campaigns/teastore-traffic-sweep-c-v1.json",
        },
    }
    adapter = ctree["adapter"]
    assert (adapter.STUDY_EPOCH, adapter.RUN_COUNT, adapter.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (C, 36, 19_200)
    assert adapter.OUTER_LEASE_SCOPE == "entire-36-cell-one-shot"
    assert set(adapter.CONTROLLER_PATHS) - sw._frozen_controller_keys() == {
        "frozen-compiler", "sweep-descriptor", "protocol-gates", "study-epoch-loader", "study-epoch-selector",
        "sweep-compiler", "sweep-b-compiler", "sweep-b-descriptor", "sweep-c-descriptor"}
    assert adapter.CONTROLLER_PATHS["candidate-compiler"] == "modules/teastore/execution/candidate_sweep_c.py"
    assert all((ctree["root"] / path).is_file() for path in adapter.CONTROLLER_PATHS.values())
    assert ctree["transport"].RUN_COUNT == ctree["controller"].RUN_COUNT == ctree["terminal"].RUN_COUNT == 36
    assert ctree["transport"].MINIMUM_FIRST_MUTATION_SECONDS == ctree["controller"].MINIMUM_FIRST_MUTATION_SECONDS \
        == 19_200
    assert ctree["producer"].CANDIDATE_STUDY_EPOCH == C
    assert ctree["validator"].SWEEP is True and ctree["validator"].STUDY_EPOCH == C
    assert ctree["validator"].REGIMES == REGIMES
    assert ctree["readiness"].SEAM_EXPECTED_VALUES["none-selected-full-materialization"] == {
        "descriptorValidation": "pass", "compiledRunCount": 36, "regimes": sorted(REGIMES), "postures": ["full"]}
    assert ctree["witness"].SWEEP_EPOCH_ACTIVE is True and ctree["native_token"].SWEEP_EPOCH_ACTIVE is True
    assert ctree["orchestrator"].DEFAULT_DESCRIPTOR == ctree["root"] / "pipelines/campaigns/teastore-traffic-sweep-c-v1.json"
    assert ctree["epoch"].sweep_compiler(ctree["root"]).EPOCH == C


@pytest.mark.parametrize("selector", [
    {"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-c-v2"},
    {"schemaVersion": True, "studyEpoch": C},
    {"schemaVersion": 1, "studyEpoch": C, "extra": 1},
    {"schemaVersion": 2, "studyEpoch": C},
    {"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-c-v1 "},
    b'{"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-c-v1", "studyEpoch": "teastore-traffic-sweep-c-v1"}',
])
def test_a_malformed_c_selector_refuses_to_load(tmp_path, selector):
    root = sw._copy_tree(tmp_path, selector)
    epoch = sw.load("teastore_c_bad_selector_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


def test_a_selector_whose_compiler_names_another_epoch_refuses_to_load(tmp_path):
    root = sw._copy_tree(tmp_path, C_SELECTOR)
    compiler = root / "modules/teastore/execution/candidate_sweep_c.py"
    compiler.write_text(compiler.read_text().replace('EPOCH = "teastore-traffic-sweep-c-v1"',
                                                     'EPOCH = "teastore-traffic-sweep-b-v1"', 1))
    epoch = sw.load("teastore_c_wrong_compiler_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


# ----------------------------------------------------------- 5. materialize -> inspect -> contracts -> package
@pytest.fixture
def cchain(ctree, tmp_path, monkeypatch):
    materialized, bindings, package, contracts = qc._contracts(ctree, tmp_path, C, monkeypatch)
    return {"materialized": materialized, "bindings": bindings, "package": package, "contracts": contracts}


def test_inspect_and_contracts_carry_the_compiled_timing(ctree, cchain):
    bindings, contracts = cchain["bindings"], cchain["contracts"]
    compiled = _cells()
    assert bindings.plan_sha256 == c.EXPECTED_PLAN_SHA256 and bindings.descriptor_sha256 == c.EXPECTED_DESCRIPTOR_SHA256
    assert list(bindings.run_ids) == [cell["runId"] for cell in compiled]
    assert bindings.campaign["scheduleVersion"] == "sweep-c-schedule-v1" and bindings.campaign["runCount"] == 36
    assert len({row["path"] for row in bindings.campaign["runs"]}) == 36
    assert set(bindings.controller_sha256) == set(ctree["adapter"].CONTROLLER_PATHS)
    assert bindings.controller_sha256["sweep-b-compiler"] == hashlib.sha256(
        (ROOT / "modules/teastore/execution/candidate_sweep_b.py").read_bytes()).hexdigest()
    for contract, cell in zip(contracts, compiled):
        timing = cell["timing"]
        assert contract["runId"] == cell["runId"] and contract["window"]["timing"] == timing
        assert contract["target"]["outerLeaseScope"] == "entire-36-cell-one-shot"
        assert ("intervention.json" in contract["requiredArtifacts"]) is timing["faultApplied"]
        assert contract["window"]["timing"]["faultHarness"] == (c.FAULT_HARNESS if timing["faultApplied"] else None)


def test_the_runtime_package_round_trips_through_the_transport(ctree, cchain):
    transport = ctree["transport"]
    runtime_package = types.SimpleNamespace(
        bindings=cchain["bindings"], gate_run=cchain["package"].gate_run,
        gate_plan_sha256="4" * 64, readiness_sha256="5" * 64, gate_run_sha256="6" * 64,
        readiness={**cchain["package"].readiness, "release": {**cchain["package"].readiness["release"]}},
    )
    document = transport.build_runtime_package(runtime_package)
    document["releaseBindingSha256"] = document["cells"][0]["runtimeInputs"]["releaseBindingSha256"]
    for cell in document["cells"]:
        cell["runtimeInputs"]["readinessArchiveSha256"] = document["readinessArchiveSha256"]
    validated = transport.validate_runtime_package(document)
    assert validated["runCount"] == 36 and len(validated["cells"]) == 36
    planted = copy.deepcopy(document)
    planted["cells"] = planted["cells"][:35]
    with pytest.raises(transport.TransportError, match="exactly 36 cells"):
        transport.validate_runtime_package(planted)


def test_the_producer_accepts_every_compiled_contract_and_refuses_bs_timing(ctree, cchain, monkeypatch):
    producer = sw._producer_in_tree(ctree, monkeypatch)
    for contract in cchain["contracts"]:
        contract = sw._with_real_controller_digests(ctree, contract)
        producer._validate_candidate_contract(contract)
        args = producer._candidate_args(contract, Path("out"))
        assert args.timing == contract["window"]["timing"]
    # Planted: a C contract carrying B's timing of the same (regime, rate, block) (B's onset) is refused.
    index = next(i for i, cell in enumerate(_cells()) if cell["timing"]["faultApplied"])
    contract = sw._with_real_controller_digests(ctree, cchain["contracts"][index])
    key = contract["runKey"]
    rate = contract["window"]["timing"]["journeysPerSecond"]
    contract["window"]["timing"] = b.compiled_cell(b.run_id_for(key["regime"], rate, key["block"], "full"))["timing"]
    with pytest.raises(RuntimeError):
        producer._validate_candidate_contract(contract)


# ------------------------------------------------------- 6. H10 and H4 on C fault cells (fake host, real validator)
def test_a_c_pause_cell_gets_the_h10_window_and_the_h4_events(ctree, tmp_path, monkeypatch):
    producer = ctree["producer"]
    clock, fake = tb._b_kit(producer, monkeypatch)
    timing = _cell("auth-freeze-effect", 1.0, 2)["timing"]
    receipt, barrier = sw._inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    assert receipt["successful"] is True, receipt["error"]
    policy, stamps = receipt["sweep"]["probePolicy"], receipt["sweep"]["commandStamps"]
    assert policy["scoredWindowEndMonotonicOffsetSeconds"] == timing["faultOnsetSeconds"] + 60
    assert tb.probes_inside(fake.calls, barrier, policy["noProbeFromMonotonicOffsetSeconds"],
                            policy["noProbeUntilMonotonicOffsetSeconds"]) == []
    freeze = receipt["sweep"]["freezeStamps"]
    assert freeze["status"] == "recorded" and [row["action"] for row in freeze["events"]["rows"]] == ["pause", "unpause"]
    assert (stamps["onsetCommandIssuedMonotonicOffsetSeconds"] <= freeze["events"]["rows"][0]["monotonicOffsetSeconds"]
            <= stamps["onsetCommandReturnedMonotonicOffsetSeconds"])


@pytest.mark.parametrize("regime,rate", [(regime, rate) for regime in REGIMES for rate in RATES])
def test_a_sealed_c_cell_is_accepted_at_every_regime_and_rate(ctree, tmp_path, as_c, regime, rate):
    cell = _cell(regime, rate, block=3)
    root = tb._seal_b(ctree, tmp_path / "run", cell)
    report = ctree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", sw._failed_gates(report)
    if cell["timing"]["faultApplied"]:
        assert tb._h4_of(report) == {"status": "recorded", "reasons": [], "failureCount": 0}


@pytest.mark.parametrize("plant", ["probe-inside-window", "policy-window-forged", "pause-event-late", "receipt-of-b"])
def test_planted_defects_on_a_c_pause_cell(ctree, tmp_path, as_c, plant):
    cell = _cell("auth-freeze-effect", 0.2, block=2)
    root = tb._seal_b(ctree, tmp_path / "run", cell)
    assert tb._verdict(ctree, root, cell) == []
    if plant == "receipt-of-b":
        # A B cell's validity record presented as a C cell: the run key names the other epoch.
        report = ctree["validator"].validate_run(root, expected={**cell["runKey"], "studyEpoch": B,
                                                                 "runId": cell["runId"].replace(C, B, 1)})
        assert report["verdict"] != "pass"
        return

    def mutate(intervention):
        record = intervention["sweep"]
        if plant == "probe-inside-window":
            record["probes"][0]["startMonotonicOffsetSeconds"] = (
                record["probePolicy"]["scoredWindowEndMonotonicOffsetSeconds"] - 1.0)
        elif plant == "policy-window-forged":
            record["probePolicy"]["noProbeUntilMonotonicOffsetSeconds"] -= 5.0
        elif plant == "pause-event-late":
            row = record["freezeStamps"]["events"]["rows"][0]
            row["timeNano"] += int(1.0e9)
            row["monotonicOffsetSeconds"] += 1.0
    sw._mutate(ctree, root, "intervention.json", mutate)
    tb._check_plant(ctree, root, cell, plant, {"probe-inside-window", "policy-window-forged"})


def test_the_c_campaign_replays_its_own_allocation(ctree, tmp_path, monkeypatch, as_c):
    adapter = ctree["adapter"]
    monkeypatch.setattr(adapter, "_git_repository_state", sw._git_state(adapter))
    root = tmp_path / "campaign"
    materialized = ctree["orchestrator"].materialize_campaign(root)
    assert len(materialized["cells"]) == 36
    for row, cell in zip(materialized["campaign"]["runs"], materialized["cells"]):
        assert row["runId"] == cell["runId"]
        tb._seal_b(ctree, root / row["path"], cell)
    report = ctree["validator"].validate_campaign(root)
    assert report["verdict"] == "pass", [(r["runKey"], sw._failed_gates(r)) for r in report["runReports"]]
    assert len(report["runReports"]) == 36
    campaign = json.loads((root / "campaign.json").read_text())
    campaign["runs"][0], campaign["runs"][1] = campaign["runs"][1], campaign["runs"][0]
    sw._json(root / "campaign.json", campaign)
    assert "scheduled-cell-population" in sw._failed_gates(ctree["validator"].validate_campaign(root))


# ------------------------------------------------------------------------------------------ 7. the 3.9 floor
@pytest.mark.parametrize("relative", C_TARGET_FILES)
def test_c_target_files_parse_at_the_python39_floor(relative):
    tree_ = ast.parse((MODULE / relative).read_text(), feature_version=(3, 9))
    assert any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
               and any(alias.name == "annotations" for alias in node.names) for node in tree_.body), relative


@pytest.mark.parametrize("relative", C_TARGET_FILES)
def test_no_name_is_loaded_that_is_bound_nowhere_in_the_files_c_touches(relative):
    assert tb._unbound_in_functions(MODULE / relative) == []


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_the_c_runtime_imports_under_system_python_isolated(tmp_path):
    root = sw._copy_tree(tmp_path / "tree", C_SELECTOR)
    script = (
        "import importlib.util, json, sys\n"
        "root = sys.argv[1]\n"
        "spec = importlib.util.spec_from_file_location('epoch', root + '/modules/teastore/execution/study_epoch.py')\n"
        "module = importlib.util.module_from_spec(spec); sys.modules['epoch'] = module; spec.loader.exec_module(module)\n"
        "for relative in sys.argv[2:]:\n"
        "    s = importlib.util.spec_from_file_location('m_' + str(abs(hash(relative))), root + '/' + relative)\n"
        "    m = importlib.util.module_from_spec(s); sys.modules[s.name] = m; s.loader.exec_module(m)\n"
        "active = module.active(__import__('pathlib').Path(root))\n"
        "print(json.dumps([active['studyEpoch'], active['runCount']]))\n"
    )
    files = ["modules/teastore/execution/candidate_runtime_adapter.py", "modules/teastore/execution/performance_campaign.py",
             "modules/teastore/validation/candidate_pilot.py", "modules/teastore/execution/candidate_sweep_c.py"]
    result = subprocess.run(["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script,
                             str(root), *files], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [C, 36]
