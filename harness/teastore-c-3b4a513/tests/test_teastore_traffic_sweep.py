"""teastore-traffic-sweep-v1: a second, parameterised TeaStore epoch beside the frozen sys-v1 pilot.

Covers: the 12-cell plan is deterministic from its seed and pinned; offered per cell is rate x measurement; the
frozen epoch's files, constants and runner arguments are unchanged without a selector; a committed selector
activates the sweep (and any other selector refuses to load); the materialize -> inspect -> contract -> package ->
producer-contract chain carries every cell's compiled timing and refuses a planted one; one fake-driven execution
of the per-cell runtime slice for each epoch (the suite otherwise never executes it); the fault controller's
pre-command / revert stamps, stamped readiness probes and CPU throttle; sealed sweep cells accepted by the cell
validator at every rate and regime, and rejected for planted defects; the 3.9 floor of every changed target file.

The sweep is exercised in a copy of the module tree with execution/study-epoch.json written into it, which is
exactly what the target sees after the selector is committed; the worktree itself stays on the frozen epoch.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules/teastore"
SWEEP = "teastore-traffic-sweep-v1"
FROZEN = "teastore-candidate-pilot-sys-v1"
BASE_COMMIT = "c1724b1"
RATES = (10.0, 1.0, 0.2, 0.05)
FRAMEWORK_COMMIT = "a" * 40
FRAMEWORK_TREE = "b" * 40
MEASUREMENT_REPO_GATES = ROOT.parent / "observability-placement/src/obsplacement/protocol_gates.py"
PROTOCOL_GATES_SHA256 = "1b3c8a3b1e9ea1f4013aa372beafc8fe0b2be14e835e114ebd9b65a69a416590"
# Frozen-epoch pins at c1724b1 (PORT_LOG 2026-09-29): descriptor file bytes and compiled plan.
FROZEN_DESCRIPTOR_FILE_SHA256 = "e4596b2587f90c43404540030906004aac2d0459901667b2445cb066de81dbb6"
FROZEN_PLAN_SHA256 = "0fee53e5a21566e7ca4bc3afd7013e5154c689e8a430a5b3fd963f9ddb6403a6"
CHANGED_TARGET_FILES = (
    "execution/study_epoch.py", "execution/candidate_sweep.py", "execution/performance_campaign.py",
    "execution/candidate_runtime_adapter.py", "execution/candidate_transport.py",
    "execution/candidate_remote_controller.py", "execution/candidate_release_installer.py",
    "execution/candidate_orchestrator.py", "validation/candidate_pilot.py", "validation/candidate_terminal.py",
    "validation/candidate_readiness.py", "validation/protocol_gates.py", "workload/fixed_load.py",
    "witness/extract_app_witness.py", "witness/extract_native_token_correlation.py",
    "validation/secret_scan.py",
)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sweep = load("teastore_sweep_compiler_test", MODULE / "execution/candidate_sweep.py")
frozen_compiler = load("teastore_sweep_frozen_compiler_test", MODULE / "execution/candidate_pilot.py")
study_epoch = load("teastore_sweep_study_epoch_test", MODULE / "execution/study_epoch.py")


def _git_blob(relative: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASE_COMMIT}:{relative}"], capture_output=True, check=True,
    ).stdout


def _copy_tree(destination: Path, selector: object = None) -> Path:
    """A copy of the TeaStore module tree, optionally with a study-epoch selector document written into it."""
    shutil.copytree(MODULE, destination / "modules/teastore",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (destination / "pipelines/campaigns").mkdir(parents=True)
    for path in (ROOT / "pipelines/campaigns").glob("teastore-*.json"):
        shutil.copyfile(path, destination / "pipelines/campaigns" / path.name)
    (destination / "src/obsplacement").mkdir(parents=True)
    for name in ("__init__.py", "selection.py"):
        shutil.copyfile(ROOT / "src/obsplacement" / name, destination / "src/obsplacement" / name)
    selector_path = destination / "modules/teastore/execution/study-epoch.json"
    selector_path.unlink(missing_ok=True)       # a copy is frozen unless this call names a selector
    if selector is not None:
        payload = selector if isinstance(selector, bytes) else (json.dumps(selector) + "\n").encode()
        selector_path.write_bytes(payload)
    return destination


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """Modules loaded from a tree copy with the selector committed: they run the sweep epoch."""
    root = _copy_tree(tmp_path_factory.mktemp("teastore-sweep-tree"),
                      {"schemaVersion": 1, "studyEpoch": SWEEP})
    module = root / "modules/teastore"
    tag = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    loaded = {"root": root}
    for key, relative in (
        ("epoch", "execution/study_epoch.py"),
        ("compiler", "execution/candidate_sweep.py"),
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
        loaded[key] = load(f"teastore_sweep_tree_{key}_{tag}", module / relative)
    return loaded


def _git_state(adapter):
    return lambda: adapter.GitRepositoryState(
        commit=FRAMEWORK_COMMIT, head_tree=FRAMEWORK_TREE, commit_tree=FRAMEWORK_TREE,
        tracked_dirty=False, status=b"", concealment_config=b"", index_concealment=(),
    )


# ------------------------------------------------------------------------------------------ 1. the sweep plan
def test_sweep_plan_is_12_cells_deterministic_and_pinned():
    descriptor = sweep.load_descriptor()
    assert sweep.canonical_sha256(descriptor) == sweep.EXPECTED_DESCRIPTOR_SHA256
    # The checked-in descriptor is the generator's output, byte for byte (regenerate, never hand-edit).
    assert sweep.DEFAULT_DESCRIPTOR.read_bytes() == sweep.descriptor_bytes()
    first, second = sweep.compile_plan(descriptor), sweep.compile_plan(copy.deepcopy(descriptor))
    assert first == second and sweep.canonical_sha256(first) == sweep.EXPECTED_PLAN_SHA256
    assert sweep.validate_plan(descriptor, first) is first
    assert descriptor["schedule"]["seed"] == sweep.SCHEDULE_SEED == 20261003
    cells = sweep.flatten_cells(first)
    assert len(cells) == first["runCount"] == sweep.TOTAL_RUNS == 12
    pairs = [(cell["runKey"]["regime"], cell["timing"]["journeysPerSecond"]) for cell in cells]
    assert sorted(pairs) == sorted((regime, rate) for regime in sweep.REGIMES for rate in RATES)
    assert pairs[0] == ("auth-freeze-effect", 10.0)            # lead cell
    assert [cell["ordinalPosition"] for cell in cells] == list(range(1, 13))
    assert {cell["runKey"]["posture"] for cell in cells} == {"full"}
    assert len({cell["runId"] for cell in cells}) == 12
    assert all(cell["runId"] == sweep.run_id_for(cell["runKey"]["regime"], cell["timing"]["journeysPerSecond"],
                                                 1, "full") for cell in cells)
    # The frozen top-level plan schema, with blocks in place of regimeRoots.
    assert "regimeRoots" not in first and len(first["blocks"]) == 1
    assert set(first["scheduleAllocation"]) == set(sweep.REGIMES)


def test_a_different_seed_reorders_the_block_but_keeps_the_lead_cell(monkeypatch):
    order = [(row["regime"], row["rate"]) for row in sweep.block_order(1)]
    monkeypatch.setattr(sweep, "SCHEDULE_SEED", 1)
    other = [(row["regime"], row["rate"]) for row in sweep.block_order(1)]
    assert other != order and other[0] == order[0] == ("auth-freeze-effect", 10.0)
    assert sorted(other) == sorted(order)


def test_offered_onset_and_floors_are_plan_values():
    plan = sweep.compile_plan(sweep.load_descriptor())
    for cell in sweep.flatten_cells(plan):
        timing = cell["timing"]
        rate = timing["journeysPerSecond"]
        assert timing["offered"] == round(rate * 180) == {10.0: 1800, 1.0: 180, 0.2: 36, 0.05: 9}[rate]
        assert timing["measurementSeconds"] == 180 and timing["faultHoldSeconds"] == 60
        assert timing["warmupSeconds"] == 30 and timing["warmupJourneysPerSecond"] == 10.0
        assert timing["warmupOffered"] == 300 and timing["concurrency"] == 240
        assert timing["requestTimeoutSeconds"] == 15.0 and timing["journeyKind"] == "login-only"
        assert 0.0 <= timing["faultOnsetPhaseOffsetSeconds"] < 1.0 / rate
        assert timing["faultOnsetSeconds"] == round(60 + timing["faultOnsetPhaseOffsetSeconds"], 6)
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"],
                                                 round(timing["faultOnsetSeconds"] + 60, 6)]
        assert timing["systemSampleCount"] == 37
        offsets = [index / rate for index in range(timing["offered"])]
        if timing["faultApplied"]:
            onset = timing["faultOnsetSeconds"]
            slots = {
                "before": sum(value < onset for value in offsets),
                "during": sum(onset <= value < onset + 60 for value in offsets),
                "after": sum(value >= onset + 62.0 for value in offsets),
            }
            floors = timing["minimumActualStartsByPhase"]
            assert all(1 <= floors[name] <= slots[name] for name in slots), (cell["runId"], floors, slots)
        else:
            assert timing["minimumActualStartsByPhase"] is None
        assert (timing["cpuThrottleNanoCpus"] == 100_000_000) is (timing["fault"] == "persistence-cpu-throttle")


def test_without_the_onset_offset_every_onset_falls_on_a_scheduled_request(monkeypatch):
    run_id = sweep.run_id_for("auth-freeze-effect", 0.05, 1, "full")
    assert sweep.onset_phase_offset(run_id, 0.05) > 0
    monkeypatch.setattr(sweep, "ONSET_PHASE_OFFSET", "none")
    for rate in RATES:
        onset = sweep.cell_timing(sweep.run_id_for("auth-freeze-effect", rate, 1, "full"),
                                  "auth-freeze-effect", rate)["faultOnsetSeconds"]
        assert abs(onset * rate - round(onset * rate)) < 1e-9


def test_budget_and_guards_are_derived_from_the_plan():
    assert sweep.CELL_PERIOD_ESTIMATE_SECONDS == 30 + 15 + 180 + sweep.CELL_OVERHEAD_SECONDS
    assert sweep.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS == (
        sweep.TOTAL_RUNS * sweep.CELL_PERIOD_ESTIMATE_SECONDS + sweep.CLEANUP_RESERVE_SECONDS)
    assert sweep.RUN_WINDOW_HOURS * 3600 >= (
        sweep.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + sweep.PREPARE_RESERVE_SECONDS)
    assert (sweep.RUN_WINDOW_HOURS - 1) * 3600 < (
        sweep.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS + sweep.PREPARE_RESERVE_SECONDS)
    assert sweep.CONCURRENCY >= max(RATES) * sweep.REQUEST_TIMEOUT_SECONDS


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_plan_digest_is_identical_under_python39(tmp_path):
    version = subprocess.run(["/usr/bin/python3", "-c", "import sys; print(sys.version_info[:2])"],
                             capture_output=True, text=True, check=True).stdout.strip()
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I",
         str(MODULE / "execution/candidate_sweep.py")],
        capture_output=True, text=True, check=True,
    )
    report = json.loads(result.stdout)
    assert report["planCanonicalSha256"] == sweep.EXPECTED_PLAN_SHA256, version
    assert report["descriptorCanonicalSha256"] == sweep.EXPECTED_DESCRIPTOR_SHA256


# ------------------------------------------------------------------------------- 2. the frozen epoch unchanged
def test_frozen_compiler_and_descriptor_are_byte_identical_to_the_base():
    for relative in ("modules/teastore/execution/candidate_pilot.py",
                     "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json"):
        assert (ROOT / relative).read_bytes() == _git_blob(relative), relative
    assert hashlib.sha256(
        (ROOT / "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json").read_bytes()
    ).hexdigest() == FROZEN_DESCRIPTOR_FILE_SHA256
    descriptor = frozen_compiler.strict_json_file(frozen_compiler.DEFAULT_DESCRIPTOR)
    assert frozen_compiler.canonical_sha256(frozen_compiler.compile_plan(descriptor)) == FROZEN_PLAN_SHA256
    assert not (MODULE / "execution/study-epoch.json").exists(), "the selector is the activation step"


def _frozen_controller_keys() -> set:
    tree = ast.parse(_git_blob("modules/teastore/execution/candidate_runtime_adapter.py").decode())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "CONTROLLER_PATHS" for t in node.targets):
            return {key.value for key in node.value.keys}
    raise AssertionError("no CONTROLLER_PATHS at the base")


def test_frozen_runtime_constants_without_a_selector():
    assert study_epoch.selected_epoch() == FROZEN and study_epoch.active() == study_epoch.FROZEN
    adapter = load("teastore_sweep_frozen_adapter", MODULE / "execution/candidate_runtime_adapter.py")
    transport = load("teastore_sweep_frozen_transport", MODULE / "execution/candidate_transport.py")
    controller = load("teastore_sweep_frozen_controller", MODULE / "execution/candidate_remote_controller.py")
    producer = load("teastore_sweep_frozen_producer", MODULE / "execution/performance_campaign.py")
    validator = load("teastore_sweep_frozen_validator", MODULE / "validation/candidate_pilot.py")
    terminal = load("teastore_sweep_frozen_terminal", MODULE / "validation/candidate_terminal.py")
    readiness = load("teastore_sweep_frozen_readiness", MODULE / "validation/candidate_readiness.py")
    orchestrator = load("teastore_sweep_frozen_orchestrator", MODULE / "execution/candidate_orchestrator.py")
    assert (adapter.STUDY_EPOCH, adapter.RUN_COUNT, adapter.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS) == (
        FROZEN, 27, 29_100)
    assert set(adapter.CONTROLLER_PATHS) == _frozen_controller_keys()
    assert adapter.OUTER_LEASE_SCOPE == "entire-27-cell-one-shot"
    assert "application.log" not in adapter.COMMON_ARTIFACTS
    assert (transport.RUN_COUNT, transport.MINIMUM_FIRST_MUTATION_SECONDS) == (27, 29_100)
    assert (controller.RUN_COUNT, controller.MINIMUM_FIRST_MUTATION_SECONDS) == (27, 29_100)
    assert producer.CANDIDATE_STUDY_EPOCH == FROZEN
    assert "application.log" not in producer.CANDIDATE_COMMON_ARTIFACTS
    assert validator.SWEEP is False and validator.STUDY_EPOCH == FROZEN
    assert validator.REGIMES == ("no-fault-cost", "auth-freeze-effect", "persistence-crash-effect")
    assert "application.log" not in validator.REQUIRED_FILES
    assert terminal.RUN_COUNT == 27 and "application.log" not in terminal.COMMON_ARTIFACTS
    assert readiness.SEAM_EXPECTED_VALUES["none-selected-full-materialization"]["compiledRunCount"] == 27
    assert readiness.SEAM_EXPECTED_VALUES["candidate-terminal-validation"]["expectedRunRoots"] == 27
    assert orchestrator.DEFAULT_DESCRIPTOR == ROOT / "pipelines/campaigns/teastore-candidate-pilot-sys-v1.json"


def test_frozen_candidate_args_are_the_base_literals():
    producer = load("teastore_sweep_frozen_producer_args", MODULE / "execution/performance_campaign.py")
    for scenario in (None, "auth-freeze", "persistence-crash"):
        contract = {
            "runKey": {"studyEpoch": FROZEN, "regime": "x", "block": 1, "posture": "full", "attempt": 1},
            "faultGroundTruth": {"scenario": scenario}, "frameworkCommit": FRAMEWORK_COMMIT,
            "descriptorCanonicalSha256": "b" * 64, "window": {},
        }
        args = producer._candidate_args(contract, Path("out"))
        assert (args.warmup, args.duration, args.rate, args.concurrency, args.fault_at, args.outage) == (
            120, 600, 0.15, 8, 180, 150)
        assert args.fault == (scenario or "none") and not hasattr(args, "timing")


# ---------------------------------------------------------------------------------------------- 3. the selector
def test_the_selector_activates_the_sweep(tree):
    epoch = tree["epoch"].active(tree["root"])
    assert epoch["studyEpoch"] == SWEEP and epoch["runCount"] == 12 and epoch["sweep"] is True
    assert epoch["outerLeaseScope"] == "entire-12-cell-one-shot"
    assert epoch["minimumFirstMutationRemainingSeconds"] == sweep.MINIMUM_FIRST_MUTATION_REMAINING_SECONDS
    adapter = tree["adapter"]
    assert (adapter.STUDY_EPOCH, adapter.RUN_COUNT) == (SWEEP, 12)
    assert set(adapter.CONTROLLER_PATHS) - _frozen_controller_keys() == {
        "frozen-compiler", "sweep-descriptor", "protocol-gates", "study-epoch-loader", "study-epoch-selector"}
    assert adapter.CONTROLLER_PATHS["candidate-compiler"] == "modules/teastore/execution/candidate_sweep.py"
    assert all((tree["root"] / path).is_file() for path in adapter.CONTROLLER_PATHS.values())
    assert "application.log" in adapter.COMMON_ARTIFACTS
    assert tree["transport"].RUN_COUNT == tree["controller"].RUN_COUNT == tree["terminal"].RUN_COUNT == 12
    assert tree["producer"].CANDIDATE_STUDY_EPOCH == SWEEP
    assert tree["validator"].SWEEP is True and "application.log" in tree["validator"].REQUIRED_FILES
    assert tree["readiness"].SEAM_EXPECTED_VALUES["none-selected-full-materialization"] == {
        "descriptorValidation": "pass", "compiledRunCount": 12,
        "regimes": sorted(sweep.REGIMES), "postures": ["full"],
    }
    assert tree["witness"].EFFECT_REGIMES == {"auth-freeze-effect", "persistence-cpu-throttle-effect"}
    assert tree["native_token"].EFFECT_REGIMES == tree["witness"].EFFECT_REGIMES


@pytest.mark.parametrize("selector", [
    {"schemaVersion": 1, "studyEpoch": FROZEN},
    {"schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-v2"},
    {"schemaVersion": True, "studyEpoch": SWEEP},
    {"schemaVersion": 1, "studyEpoch": SWEEP, "extra": 1},
    b'{"schemaVersion": 1, "schemaVersion": 1, "studyEpoch": "teastore-traffic-sweep-v1"}',
    b"not json",
])
def test_a_selector_naming_anything_else_refuses_to_load(tmp_path, selector):
    root = _copy_tree(tmp_path, selector)
    epoch = load("teastore_sweep_bad_selector_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)
    with pytest.raises(ValueError):
        load("teastore_sweep_bad_selector_adapter",
             root / "modules/teastore/execution/candidate_runtime_adapter.py")


def test_a_symlinked_selector_refuses_to_load(tmp_path):
    root = _copy_tree(tmp_path)
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps({"schemaVersion": 1, "studyEpoch": SWEEP}))
    (root / "modules/teastore/execution/study-epoch.json").symlink_to(target)
    epoch = load("teastore_sweep_symlink_epoch", root / "modules/teastore/execution/study_epoch.py")
    with pytest.raises(epoch.SelectorError):
        epoch.active(root)


# ----------------------------------------------------------- 4. materialize -> inspect -> contracts -> package
@pytest.fixture
def chain(tree, tmp_path, monkeypatch):
    adapter = tree["adapter"]
    monkeypatch.setattr(adapter, "_git_repository_state", _git_state(adapter))
    campaign_root = tmp_path / "campaign"
    tree["orchestrator"].materialize_campaign(campaign_root)
    bindings = adapter.inspect_campaign(campaign_root, FRAMEWORK_COMMIT)
    images = {service: f"repo/{service}@sha256:{index:064x}"
              for index, service in enumerate(adapter.IMAGE_SERVICES, 1)}
    release = {"gateSetupSha256": "1" * 64, "releaseManifestSha256": "2" * 64, "bundleSha256": "3" * 64}
    authorization = {
        "campaignId": SWEEP, "transportUser": "root", "executionUser": "stig", "executionUid": 1015,
        "executionGid": 1015, "executionMethod": "runuser",
        "releaseRoot": "/home/stig/.local/share/observability-placement/candidate-v4/teastore/releases/"
                       + "0" * 32 + "-" + "a" * 12 + "-" + "3" * 16,
        "resultsRoot": "/home/stig/.local/share/observability-placement/candidate-v4/teastore/results/" + "0" * 32,
        "exclusiveLeasePath": adapter.LEASE_PATH, "setupId": "0" * 32,
        "gateSetupSha256": "1" * 64, "releaseManifestSha256": "2" * 64, "bundleSha256": "3" * 64,
        "releaseInstalledAt": "2026-10-03T00:00:00Z", "notBefore": "2026-10-03T00:00:00Z",
        "authorizationDeadline": "2026-10-03T03:00:00Z", "cleanupReserveSeconds": 300,
        "authorizedRunIds": list(bindings.run_ids),
    }
    package = types.SimpleNamespace(
        bindings=bindings, gate_run={"authorization": authorization},
        gate_plan_sha256="4" * 64, readiness_sha256="5" * 64, gate_run_sha256="6" * 64,
        readiness={"imageDigests": images, "transport": {"implementationSha256": "7" * 64},
                   "release": release, "ingressArchiveSha256": "8" * 64,
                   "runtimePreflight": {"capturedAt": "2026-10-03T00:00:00Z"}},
    )
    contracts = [adapter.build_cell_contract(package, cell) for cell in bindings.cells]
    return {"bindings": bindings, "package": package, "contracts": contracts, "images": images}


def test_inspect_and_contracts_carry_the_compiled_timing(tree, chain):
    bindings, contracts = chain["bindings"], chain["contracts"]
    plan = sweep.compile_plan(sweep.load_descriptor())
    compiled = sweep.flatten_cells(plan)
    assert bindings.plan_sha256 == sweep.EXPECTED_PLAN_SHA256
    assert list(bindings.run_ids) == [cell["runId"] for cell in compiled]
    assert bindings.campaign["scheduleVersion"] == "sweep-schedule-v1" and bindings.campaign["runCount"] == 12
    paths = [row["path"] for row in bindings.campaign["runs"]]
    assert len(set(paths)) == 12 and paths[0] == "runs/auth-freeze-effect/b01-01-full"
    for contract, cell in zip(contracts, compiled):
        timing = cell["timing"]
        assert contract["window"]["timing"] == timing
        assert contract["window"]["measurementSeconds"] == 180 and contract["window"]["warmupSeconds"] == 30
        assert contract["workload"]["journeysPerSecond"] == timing["journeysPerSecond"]
        assert contract["workload"]["offeredJourneys"] == timing["offered"]
        assert contract["workload"]["id"] == "login-only-v1"
        assert contract["target"]["outerLeaseScope"] == "entire-12-cell-one-shot"
        assert "application.log" in contract["requiredArtifacts"]
        if timing["faultApplied"]:
            assert contract["faultGroundTruth"]["faultOnsetSeconds"] == timing["faultOnsetSeconds"]
            assert contract["faultGroundTruth"]["holdSeconds"] == 60
            assert "intervention.json" in contract["requiredArtifacts"]
        else:
            assert "resources.json" in contract["requiredArtifacts"]


def test_the_runtime_package_round_trips_through_the_transport(tree, chain, tmp_path):
    transport, adapter = tree["transport"], tree["adapter"]
    runtime_package = types.SimpleNamespace(
        bindings=chain["bindings"], gate_run=chain["package"].gate_run,
        gate_plan_sha256="4" * 64, readiness_sha256="5" * 64, gate_run_sha256="6" * 64,
        readiness={**chain["package"].readiness,
                   "release": {**chain["package"].readiness["release"]}},
    )
    original = adapter.build_cell_contract
    document = transport.build_runtime_package(runtime_package)
    assert adapter.build_cell_contract is original
    document["releaseBindingSha256"] = document["cells"][0]["runtimeInputs"]["releaseBindingSha256"]
    for cell in document["cells"]:
        cell["runtimeInputs"]["readinessArchiveSha256"] = document["readinessArchiveSha256"]
    validated = transport.validate_runtime_package(document)
    assert validated["runCount"] == 12 and len(validated["cells"]) == 12
    assert validated["outerLeaseScope"] == "entire-12-cell-one-shot"
    planted = copy.deepcopy(document)
    planted["cells"] = planted["cells"][:11]
    with pytest.raises(transport.TransportError, match="exactly 12 cells"):
        transport.validate_runtime_package(planted)


def _producer_in_tree(tree, monkeypatch):
    monkeypatch.chdir(tree["root"])
    return tree["producer"]


def _with_real_controller_digests(tree, contract):
    contract = copy.deepcopy(contract)
    digests = {name: hashlib.sha256((tree["root"] / relative).read_bytes()).hexdigest()
               for name, relative in tree["adapter"].CONTROLLER_PATHS.items()}
    contract["runtimeInputs"]["controllerDigests"] = digests
    contract["runtimeInputs"]["transportImplementationSha256"] = digests["bounded-candidate-transport"]
    return contract


def test_the_producer_accepts_every_compiled_contract_and_takes_its_numbers_from_timing(tree, chain, monkeypatch):
    producer = _producer_in_tree(tree, monkeypatch)
    for contract in chain["contracts"]:
        contract = _with_real_controller_digests(tree, contract)
        producer._validate_candidate_contract(contract)
        args = producer._candidate_args(contract, Path("out"))
        timing = contract["window"]["timing"]
        assert (args.warmup, args.duration, args.rate, args.concurrency) == (
            30, 180, timing["journeysPerSecond"], 240)
        assert (args.fault_at, args.outage) == (timing["faultOnsetSeconds"], 60)
        assert args.timing == timing


@pytest.mark.parametrize("plant", [
    "rate", "onset", "hold", "offered", "ordinal", "lease-scope", "other-cell-timing", "frozen-window",
])
def test_the_producer_refuses_a_contract_that_brings_its_own_numbers(tree, chain, monkeypatch, plant):
    producer = _producer_in_tree(tree, monkeypatch)
    contract = _with_real_controller_digests(tree, chain["contracts"][0])
    producer._validate_candidate_contract(copy.deepcopy(contract))
    timing = contract["window"]["timing"]
    if plant == "rate":
        timing["journeysPerSecond"] = 1.0
    elif plant == "onset":
        timing["faultOnsetSeconds"] = 60.0
        contract["faultGroundTruth"]["faultOnsetSeconds"] = 60.0
    elif plant == "hold":
        timing["faultHoldSeconds"] = 150
        contract["faultGroundTruth"]["holdSeconds"] = 150
    elif plant == "offered":
        contract["workload"]["offeredJourneys"] = 90
    elif plant == "ordinal":
        contract["ordinalPosition"] = 13
    elif plant == "lease-scope":
        contract["target"]["outerLeaseScope"] = "entire-27-cell-one-shot"
    elif plant == "other-cell-timing":
        contract["window"]["timing"] = copy.deepcopy(chain["contracts"][1]["window"]["timing"])
    elif plant == "frozen-window":
        del contract["window"]["timing"]
    with pytest.raises(RuntimeError):
        producer._validate_candidate_contract(contract)


# ------------------------------------------------------------------- 5. the fault controller (faked host calls)
class FakeClock:
    """Shared fake time: sleep and every faked command advance it; nothing waits for real."""

    def __init__(self, monotonic: float = 1000.0, wall: float = 1_790_000_000.0):
        self.mono, self.wall = monotonic, wall

    def monotonic(self) -> float:
        return self.mono

    def time(self) -> float:
        return self.wall

    def sleep(self, seconds: float) -> None:
        self.advance(max(0.0, float(seconds)))

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += seconds


class FakeDocker:
    """Container state that the faked docker / compose commands mutate; records every argv."""

    def __init__(self, clock: FakeClock, *, ncpu: int = 24, pre_nanocpus: int = 0):
        self.clock, self.ncpu = clock, ncpu
        self.paused, self.nanocpus = False, pre_nanocpus
        self.calls: list = []
        self.target = "c" * 64

    def __call__(self, args, *, output=None, check=True):
        args = list(args)
        self.calls.append((self.clock.monotonic(), args))
        stdout = ""
        if args[:2] == ["docker", "compose"] and "ps" in args:
            stdout, cost = self.target + "\n", 0.3
        elif args[:2] == ["docker", "compose"] and args[-2:] == ["pause", "auth"]:
            self.paused, cost = True, 0.25
        elif args[:2] == ["docker", "compose"] and args[-2:] == ["unpause", "auth"]:
            self.paused, cost = False, 0.2
        elif args[:3] == ["docker", "update", "--cpus"]:
            self.nanocpus, cost = int(round(float(args[3]) * 1_000_000_000)), 0.15
        elif args[:2] == ["docker", "inspect"]:
            stdout = json.dumps([{
                "State": {"Running": True, "Paused": self.paused,
                          "Status": "paused" if self.paused else "running"},
                "HostConfig": {"NanoCpus": self.nanocpus},
            }])
            cost = 0.05
        elif args[:2] == ["docker", "info"]:
            stdout, cost = f"{self.ncpu}\n", 0.05
        elif args[0] == "curl":
            stdout, cost = "OK " * 5, 0.1
        else:
            cost = 0.0
        self.clock.advance(cost)
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def _fault_kit(producer, monkeypatch, **docker):
    clock = FakeClock()
    fake = FakeDocker(clock, **docker)
    monkeypatch.setattr(producer, "time", clock)
    monkeypatch.setattr(producer, "command", fake)
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "teastore_candidate_0123456789abcdef")
    return clock, fake


def _target_image(target: str) -> dict:
    return {"containerId": target, "declaredImage": "descartesresearch/teastore-auth",
            "containerImageId": "sha256:" + "d" * 64, "imageInspectId": "sha256:" + "d" * 64,
            "repoDigests": []}


def _inject(producer, clock, fake, tmp_path, fault, timing=None, *, fault_at=180, outage=150):
    barrier = clock.monotonic() + 15.0
    kwargs = {} if timing is None else {"sweep_timing": timing}
    return producer.inject_fault(
        fault, fault_at if timing is None else timing["faultOnsetSeconds"],
        outage if timing is None else timing["faultHoldSeconds"], tmp_path, "full",
        measurement_barrier_epoch=clock.time() + 15.0, measurement_barrier_monotonic=barrier,
        measurement_barrier_id="barrier-" + "e" * 32, target_image=_target_image(fake.target), **kwargs,
    ), barrier


FROZEN_RECEIPT_KEYS = {
    "schemaVersion", "scenario", "service", "independentOfKieker", "intervalLabel", "functionalOutage",
    "measurementBarrier", "requestedHoldSeconds", "targetContainerId", "targetImage", "preState",
    "commandVector", "commandResult", "actualOnsetWall", "actualOnsetMonotonicOffsetSeconds",
    "actualOffsetWall", "actualOffsetMonotonicOffsetSeconds", "duringStateSamples", "recoveryAction",
    "sameTargetIdentity", "readiness", "postState", "interventionThreadJoined",
    "laterInterventionMutationObserved", "manifested", "recovered", "outageHeld", "successful", "error",
    "operational",
}


def _cell_timing(rate: float, regime: str) -> dict:
    run_id = sweep.run_id_for(regime, rate, 1, "full")
    return sweep.cell_timing(run_id, regime, rate)


def test_frozen_fault_receipt_is_unchanged_by_the_sweep_code(tmp_path, monkeypatch):
    producer = load("teastore_sweep_frozen_fault_producer", MODULE / "execution/performance_campaign.py")
    clock, fake = _fault_kit(producer, monkeypatch)
    receipt, barrier = _inject(producer, clock, fake, tmp_path, "auth-freeze")
    assert set(receipt) == FROZEN_RECEIPT_KEYS and receipt["successful"] is True, receipt["error"]
    assert receipt["measurementBarrier"]["scheduledOnsetSeconds"] == 180 and receipt["requestedHoldSeconds"] == 150
    assert not any(args[0] == "curl" and False for _, args in fake.calls)
    with pytest.raises(ValueError):
        producer.inject_fault("persistence-cpu-throttle", 60, 60, tmp_path, "full")


@pytest.mark.parametrize("rate", RATES)
def test_sweep_pause_stamps_the_onset_before_the_command_and_every_probe(tree, tmp_path, monkeypatch, rate):
    producer, gates = tree["producer"], tree["gates"]
    clock, fake = _fault_kit(producer, monkeypatch)
    timing = _cell_timing(rate, "auth-freeze-effect")
    receipt, barrier = _inject(producer, clock, fake, tmp_path, "auth-freeze", timing)
    assert receipt["successful"] is True, receipt["error"]
    assert set(receipt) == FROZEN_RECEIPT_KEYS | {"sweep"}
    stamps = receipt["sweep"]["commandStamps"]
    pause_at = next(at for at, args in fake.calls if args[-2:] == ["pause", "auth"]) - barrier
    unpause_at = next(at for at, args in fake.calls if args[-2:] == ["unpause", "auth"]) - barrier
    assert stamps["onsetCommandIssuedMonotonicOffsetSeconds"] == pause_at          # immediately before the command
    assert stamps["revertCommandIssuedMonotonicOffsetSeconds"] == unpause_at
    assert timing["faultOnsetSeconds"] - 1e-9 <= pause_at < timing["faultOnsetSeconds"] + 0.05
    assert (stamps["onsetCommandIssuedMonotonicOffsetSeconds"] < stamps["onsetCommandReturnedMonotonicOffsetSeconds"]
            <= receipt["actualOnsetMonotonicOffsetSeconds"] < receipt["actualOffsetMonotonicOffsetSeconds"]
            <= stamps["revertCommandIssuedMonotonicOffsetSeconds"]
            < stamps["revertCommandReturnedMonotonicOffsetSeconds"]
            <= receipt["readiness"]["observedAtMonotonicOffsetSeconds"])
    # The hold is timed from the first post-command sample (the samples' own durations are not added).
    samples = [row["observedAtMonotonicOffsetSeconds"] for row in receipt["duringStateSamples"]]
    assert abs(samples[1] - samples[0] - 30.0) < 1e-6 and abs(samples[2] - samples[0] - 60.0) < 1e-6
    probes = receipt["sweep"]["probes"]
    assert len(probes) == 1 and probes[0]["ready"] is True
    assert stamps["revertCommandReturnedMonotonicOffsetSeconds"] <= probes[0]["startMonotonicOffsetSeconds"]
    assert probes[0]["endMonotonicOffsetSeconds"] <= receipt["readiness"]["observedAtMonotonicOffsetSeconds"]
    hold = stamps["revertCommandIssuedMonotonicOffsetSeconds"] - stamps["onsetCommandIssuedMonotonicOffsetSeconds"]
    command = stamps["onsetCommandReturnedMonotonicOffsetSeconds"] - stamps["onsetCommandIssuedMonotonicOffsetSeconds"]
    assert 60 <= hold <= 60 + command + gates.HOLD_TOLERANCE_S


def test_sweep_cpu_throttle_sets_and_lifts_the_quota_on_the_target(tree, tmp_path, monkeypatch):
    producer = tree["producer"]
    clock, fake = _fault_kit(producer, monkeypatch, ncpu=24)
    timing = _cell_timing(1.0, "persistence-cpu-throttle-effect")
    receipt, _ = _inject(producer, clock, fake, tmp_path, "persistence-cpu-throttle", timing)
    assert receipt["successful"] is True, receipt["error"]
    assert receipt["service"] == "persistence"
    assert receipt["commandVector"] == ["docker", "update", "--cpus", "0.1", fake.target]
    assert receipt["recoveryAction"]["commandVector"] == ["docker", "update", "--cpus", "24", fake.target]
    assert receipt["preState"]["nanoCpus"] == 0 and receipt["postState"]["nanoCpus"] == 24_000_000_000
    assert all(sample["state"]["nanoCpus"] == 100_000_000 for sample in receipt["duringStateSamples"])
    assert receipt["sweep"]["throttle"] == {"cpus": "0.1", "nanoCpus": 100_000_000, "preNanoCpus": 0,
                                           "hostNanoCpus": 24_000_000_000, "revertCpus": "24"}
    assert [result["command"] for result in receipt["operational"]["commandResults"]] == [
        receipt["commandVector"], receipt["recoveryAction"]["commandVector"]]


def test_sweep_cpu_throttle_refuses_a_target_already_throttled(tree, tmp_path, monkeypatch):
    producer = tree["producer"]
    clock, fake = _fault_kit(producer, monkeypatch, pre_nanocpus=500_000_000)
    receipt, _ = _inject(producer, clock, fake, tmp_path, "persistence-cpu-throttle",
                         _cell_timing(1.0, "persistence-cpu-throttle-effect"))
    assert receipt["successful"] is False and "already set" in receipt["error"]
    assert not any(args[:3] == ["docker", "update", "--cpus"] for _, args in fake.calls)


# ------------------------------------------------------------- 6. one fake-driven execution of the runtime slice
class _SyncThread:
    """threading.Thread stand-in that runs its target on start(), so the fake clock stays deterministic."""

    def __init__(self, target=None, **_):
        self._target = target

    def start(self):
        self._target()

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return False


def _drive_slice(producer, root: Path, args, monkeypatch) -> dict:
    """Run _execute_candidate_runtime_slice with every host call faked; return the recorded calls."""
    monkeypatch.chdir(root)
    monkeypatch.setenv("OBSPLACEMENT_COMPOSE_PROJECT", "teastore_candidate_0123456789abcdef")
    compiled = root / ".local/compiled/teastore"
    compiled.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "aop.xml", "full.manifest.json", "full.aop.xml",
                 "none.manifest.json", "none.aop.xml"):
        (compiled / name).write_text(name)
    aop_sha = hashlib.sha256((compiled / "full.aop.xml").read_bytes()).hexdigest()
    clock = FakeClock()
    calls = {"commands": [], "popen": [], "inject": [], "serviceLogs": 0}

    def command(argv, *, output=None, check=True):
        argv = [str(value) for value in argv]
        calls["commands"].append(argv)
        stdout = ""
        if "modules/teastore/workload/fixed_load.py" in argv:
            options = dict(zip(argv[3::2], argv[4::2]))
            rate, duration = float(options["--rate"]), float(options["--duration"])
            offered = max(1, int(rate * duration + 1e-9))
            start = float(options.get("--start-at-epoch", clock.time()))
            clock.advance(duration)
            Path(options["--output"]).write_text(json.dumps({
                "schemaVersion": 2, "startedAtEpoch": start, "endedAtEpoch": clock.time(),
                "schedule": {"kind": "fixed-open-loop", "journeysPerSecond": rate, "durationSeconds": duration,
                             "barrierAtEpoch": start},
                "offered": offered, "completed": offered, "successful": offered, "failed": 0, "timedOut": 0,
                "settled": offered, "concurrency": int(options["--concurrency"]), "requests": offered,
                "latencyMs": {"denominator": "successful-journeys", "count": offered, "p50": 1.0,
                              "p95": 1.0, "p99": 1.0, "mean": 1.0},
                "journeyEvidence": {},
            }))
        if output is not None:
            Path(output).write_text(stdout)
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    class FakePopen:
        def __init__(self, argv, **_):
            self.args, self.pid, self.returncode = [str(value) for value in argv], 4242, 0
            calls["popen"].append(self.args)
            options = dict(zip(self.args[3::2], self.args[4::2]))
            if "modules/teastore/collectors/performance_probe_v3.py" in self.args:
                start = float(options["--start-at-epoch"])
                Path(options["--output"]).write_text(json.dumps({
                    "schemaVersion": 3, "nominalStartAtEpoch": start,
                    "nominalEndAtEpoch": start + float(options["--duration"]),
                    "requiredServices": sorted(producer.APP_SERVICES), "barrierId": options["--barrier-id"],
                    "applicationCpuSeconds": 1.0, "applicationMemoryPeakBytes": 1.0, "hostCpuSeconds": 1.0,
                    "contract": "x", "measurementDurationSeconds": float(options["--duration"]),
                    "sampling": {"intervalSeconds": 5.0},
                }))
            if "modules/teastore/collectors/system_probe.py" in self.args:
                Path(options["--output"]).write_text("{}")

    def inject(*positional, **keywords):
        calls["inject"].append((positional, keywords))
        return {"successful": True, "error": None}

    def capture_bytes(argv):
        argv = [str(value) for value in argv]
        calls["commands"].append(argv)
        # A non-UTF-8 byte in a service log must not lose the cell.
        return types.SimpleNamespace(returncode=0, stdout=b"auth-1  | 2026-10-03T00:00:00.000000001Z started \xff\n",
                                     stderr=b"")

    service_row = {"containerId": "c" * 64, "declaredImage": "x", "containerImageId": "sha256:" + "d" * 64,
                   "imageInspectId": "sha256:" + "d" * 64, "repoDigests": []}
    patches = {
        "time": clock, "command": command, "capture_bytes": capture_bytes,
        "project_resources": lambda: {"project": "p"},
        "resources_clean": lambda proof: True, "wait_broker": lambda posture: None, "wait_ready": lambda: None,
        "runtime_image_proof": lambda posture, expected_content_references=None: {
            "services": {service: dict(service_row) for service in producer.RUNTIME_SERVICES}},
        "posture_proof": lambda posture: {
            "closureGroups": [], "aopSha256": aop_sha,
            "services": {service: {"aopSha256": aop_sha, "configuration": "kieker.monitoring.enabled=true",
                                   "writerInitializationFailed": False} for service in producer.APP_SERVICES}},
        "validate_journey_evidence": lambda aggregate, path: {"planSha256": "p", "lastRecordSha256": "l"},
        "purge_queue": lambda posture: {"after": {"messages": 0}},
        "queue_state": lambda posture: {"messages": 0, "consumers": 1},
        "wait_consumer": lambda posture: {"messages": 0, "consumers": 1},
        "collector_barrier_acknowledgement": lambda posture, barrier: {"queueState": {"consumers": 1, "messages": 0}},
        "broker_proof": lambda posture: {},
        "inject_fault": inject,
        "join_child_process": lambda process, timeout, **_: (
            "", "{}", {"returnCode": 0, "timedOut": False, "communicationError": None, "joined": True}),
        "native_collector_module": lambda: types.SimpleNamespace(
            collector_heartbeat_path=lambda spool: spool.with_name("heartbeat"),
            entry_point_woven=lambda groups: True),
        "wait_queue_drained": lambda posture: {"messages": 0, "consumers": 0},
        "validate_queue_proof": lambda proof, **_: None,
        "collector_stats": lambda stderr, **_: {"records_bad": 0, "attribution_configuration_sha256": "a" * 64},
        "replay_spool_evidence": lambda spool, images: (_ for _ in ()).throw(RuntimeError("faked")),
        "collector_process_blockers": lambda *a, **k: calls.__setitem__("collectorKwargs", k) or [],
        "collector_event_blockers": lambda *a, **k: [],
        "resource_probe_module": lambda: types.SimpleNamespace(
            validate_resource_evidence=lambda *a, **k: {"verdict": "pass"}),
        "capture_candidate_service_logs": lambda *a, **k: calls.__setitem__(
            "serviceLogs", calls["serviceLogs"] + 1),
        "service_container": lambda posture, service: "c" * 64,
        "teardown_project": lambda posture, run_dir: ({"returnCode": 0}, {"project": "p"}),
        "bind_teardown": lambda *a, **k: None,
    }
    for name, value in patches.items():
        monkeypatch.setattr(producer, name, value)
    monkeypatch.setattr(producer.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(producer.threading, "Thread", _SyncThread)
    receipt = producer._execute_candidate_runtime_slice(
        root / "cell", ".operational", "full", args, expected_image_references={})
    calls["receipt"] = receipt
    calls["runDir"] = root / "cell/.operational"
    return calls


def _workload_argv(calls, output_name: str) -> list:
    return next(argv for argv in calls["commands"]
                if "modules/teastore/workload/fixed_load.py" in argv and argv[argv.index("--output") + 1]
                .endswith(output_name))


def test_the_frozen_runtime_slice_passes_the_base_literals(tmp_path, monkeypatch):
    root = _copy_tree(tmp_path)
    producer = load("teastore_sweep_frozen_slice_producer", root / "modules/teastore/execution/performance_campaign.py")
    contract = {"runKey": {"studyEpoch": FROZEN, "regime": "auth-freeze-effect", "block": 1, "posture": "full",
                           "attempt": 1},
                "faultGroundTruth": {"scenario": "auth-freeze"}, "frameworkCommit": FRAMEWORK_COMMIT,
                "descriptorCanonicalSha256": "b" * 64, "window": {}}
    calls = _drive_slice(producer, root, producer._candidate_args(contract, root / "cell"), monkeypatch)
    warmup = _workload_argv(calls, "warmup.json")
    workload = _workload_argv(calls, "workload.json")
    assert warmup[3:9] == ["--rate", "0.15", "--duration", "120", "--concurrency", "8"]
    assert workload[3:9] == ["--rate", "0.15", "--duration", "600", "--concurrency", "8"]
    assert "--timeout" not in warmup + workload and "--journey-kind" not in warmup + workload
    (positional, keywords), = calls["inject"]
    assert positional[:3] == ("auth-freeze", 180, 150) and "sweep_timing" not in keywords
    collector = next(argv for argv in calls["popen"] if "modules/teastore/collectors/kieker_native.py" in argv)
    assert collector[collector.index("--duration") + 1] == "630"
    system = next(argv for argv in calls["popen"] if "modules/teastore/collectors/system_probe.py" in argv)
    assert system[system.index("--duration") + 1] == "600"
    assert not any(argv[-3:] == ["logs", "--timestamps", "--no-color"] for argv in calls["commands"])
    assert calls["receipt"]["window"]["measurementSeconds"] == 600
    assert not (calls["runDir"] / "application.log").exists()
    assert calls["collectorKwargs"]["trace_completeness_deferred"] is False      # decision 25 is sweep-only


@pytest.mark.parametrize("regime,rate", [
    ("auth-freeze-effect", 10.0), ("persistence-cpu-throttle-effect", 0.05), ("no-fault-cost", 0.2),
])
def test_the_sweep_runtime_slice_takes_every_argument_from_the_cell_timing(tree, chain, tmp_path, monkeypatch,
                                                                            regime, rate):
    producer = tree["producer"]
    contract = next(row for row in chain["contracts"]
                    if row["runKey"]["regime"] == regime and row["window"]["timing"]["journeysPerSecond"] == rate)
    timing = contract["window"]["timing"]
    run_root = tmp_path / "run"
    shutil.copytree(tree["root"], run_root)
    calls = _drive_slice(producer, run_root, producer._candidate_args(contract, run_root / "cell"), monkeypatch)
    warmup = _workload_argv(calls, "warmup.json")
    workload = _workload_argv(calls, "workload.json")
    assert warmup[3:9] == ["--rate", "10.0", "--duration", "30", "--concurrency", "240"]
    assert warmup[-4:] == ["--timeout", "15.0", "--journey-kind", "login-only"]
    assert workload[3:9] == ["--rate", str(rate), "--duration", "180", "--concurrency", "240"]
    assert workload[-4:] == ["--timeout", "15.0", "--journey-kind", "login-only"]
    if timing["faultApplied"]:
        (positional, keywords), = calls["inject"]
        assert positional[:3] == (timing["fault"], timing["faultOnsetSeconds"], 60)
        assert keywords["sweep_timing"] == timing
    else:
        assert calls["inject"] == []
        probe = next(argv for argv in calls["popen"] if "modules/teastore/collectors/performance_probe_v3.py" in argv)
        assert probe[probe.index("--duration") + 1] == "180"
    collector = next(argv for argv in calls["popen"] if "modules/teastore/collectors/kieker_native.py" in argv)
    assert collector[collector.index("--duration") + 1] == "210"
    system = next(argv for argv in calls["popen"] if "modules/teastore/collectors/system_probe.py" in argv)
    assert system[system.index("--duration") + 1] == "180"
    logs = [argv for argv in calls["commands"] if argv[-3:] == ["logs", "--timestamps", "--no-color"]]
    assert len(logs) == 1 and logs[0][:2] == ["docker", "compose"]
    assert (calls["runDir"] / "application.log").read_bytes().startswith(b"auth-1  | 2026-10-03T")
    assert b"\xff" in (calls["runDir"] / "application.log").read_bytes()
    assert calls["receipt"]["window"]["measurementSeconds"] == 180
    assert calls["serviceLogs"] == 1
    assert calls["collectorKwargs"]["trace_completeness_deferred"] is True       # decision 25: the validator decides


# ------------------------------------------------------------------- 7. sealed sweep cells and the validator
BASE = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)
WARMUP = BASE
WARMUP_END = WARMUP + timedelta(seconds=30)
WARMUP_SETTLED = WARMUP + timedelta(seconds=29)
MEASUREMENT = WARMUP_END + timedelta(seconds=20)
BARRIER = "barrier-" + "a" * 32
APP = ("auth", "image", "persistence", "recommender", "webui")


def _t(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"),
                                     sort_keys=True).encode()).hexdigest()


def _json(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _rehash(tree, root: Path) -> None:
    receipt = json.loads((root / "receipt.json").read_text())
    receipt["artifacts"] = {
        name: {"sha256": _sha(root / name)}
        for name in (*tree["validator"].REQUIRED_FILES[1:], "intervention.json") if (root / name).is_file()
    }
    _json(root / "receipt.json", receipt)


def _operational_proofs(tree, root: Path, measurement: int) -> None:
    validator = tree["validator"]
    catalog_path = tree["root"] / "modules/teastore/activation/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    compiler = validator._selection_compiler()
    requested = sorted(row["id"] for row in catalog["logicalSensors"])
    compiled = compiler.compile_selection(catalog, requested)
    required = list(compiled["selectedActivationGroups"])
    aop_sha = hashlib.sha256(compiler.render_aop(compiled).encode()).hexdigest()
    _json(root / "posture-proof.json", {
        "schemaVersion": 3, "requested": "full", "catalogId": catalog["id"],
        "catalogSha256": _sha(catalog_path), "selectionId": "catalog-all", "goalLogicalSensors": requested,
        "closureGroups": required, "requiredGroups": required,
        "forbiddenGroups": sorted({row["id"] for row in catalog["activationGroups"]} - set(required)),
        "aopSha256": aop_sha,
        "manifestSha256": hashlib.sha256((json.dumps(compiled, indent=2, sort_keys=True) + "\n").encode()).hexdigest(),
        "monitoringEnabled": True,
        "services": {service: {"aopSha256": aop_sha, "configuration": "kieker.monitoring.enabled=true",
                               "writerInitializationFailed": False} for service in APP},
    })
    container = "f" * 64

    def state(messages: int, consumers: int) -> dict:
        argv = ["docker", "exec", container, "rabbitmqctl", "list_queues", "-q", "name", "messages", "consumers"]
        return {"containerId": container, "messages": messages, "consumers": consumers,
                "query": {"command": argv, "returnCode": 0, "stdout": f"kieker\t{messages}\t{consumers}\n",
                          "stderr": ""}}
    _json(root / "queue-proof.json", {
        "schemaVersion": 2, "composeProject": "teastore_candidate_fixture",
        "broker": {
            "schemaVersion": 2,
            "queries": {name: {"command": ["docker", "exec", container, "rabbitmqctl", name], "returnCode": 0,
                               "stdout": "", "stderr": ""} for name in ("heartbeat", "queueArguments", "connections")},
            "heartbeatSeconds": 0,
            "queueArguments": 'kieker\t[{"x-max-length",50000},{"x-overflow","reject-publish"}]',
            "connections": [{"user": "admin", "peerHost": "172.18.0.5", "timeoutSeconds": timeout,
                             "clientProperties": '[{"product","RabbitMQ"},{"platform","Java"}]'}
                            for timeout in (0, 900, 900, 900, 900, 900)],
            "connectionTimeouts": [0, 900, 900, 900, 900, 900],
        },
        "purge": {"before": state(0, 0),
                  "command": {"command": ["docker", "exec", container, "rabbitmqctl", "purge_queue", "kieker"],
                              "returnCode": 0, "stdout": "Purging queue 'kieker'\n", "stderr": ""},
                  "after": state(0, 0)},
        "measurement": {"before": state(0, 0), "consumerAtStart": state(0, 1), "after": state(0, 0),
                        "depthSamples": [{"monotonicOffsetSeconds": float(offset), "messages": 12, "consumers": 1}
                                         for offset in range(0, measurement, 5)]},
    })


def _cluster_records(kieker, trace_id: int, at: datetime) -> list:
    """An unattributable persistence trace with a repeated native identity (eoi 0 twice, different tin) and a
    child under it: the shape of the TeaStore attempt-1 cell-11 records (conflicting-native-identity, then
    ambiguous-parent-native-identity)."""
    tin = int(at.timestamp() * 1_000_000_000)
    op = "public void tools.descartes.teastore.persistence.Persistence.find()"
    return [
        {"class_name": kieker.OER_CLASS, "operationSignature": op, "sessionId": "sweep-fixture",
         "traceId": trace_id, "tin": tin, "tout": tin + 5_000_000, "hostname": "persistence", "eoi": 0, "ess": 0},
        {"class_name": kieker.OER_CLASS, "operationSignature": op, "sessionId": "sweep-fixture",
         "traceId": trace_id, "tin": tin + 1_000_000, "tout": tin + 6_000_000, "hostname": "persistence",
         "eoi": 0, "ess": 0},
        {"class_name": kieker.OER_CLASS, "operationSignature": op, "sessionId": "sweep-fixture",
         "traceId": trace_id, "tin": tin + 2_000_000, "tout": tin + 4_000_000, "hostname": "persistence",
         "eoi": 1, "ess": 1},
    ]


def _spool(tree, root: Path, starts: list, no_edge: set = frozenset(), clusters: list = ()) -> tuple:
    kieker = tree["kieker"]
    services = sorted(kieker.CANONICAL_RUNTIME_SERVICES)
    _json(root / "runtime-images.json", {"schemaVersion": 1, "services": {
        service: {"containerId": f"{index + 1:x}" * 64} for index, service in enumerate(services)}})
    spool = kieker.KiekerBodySpool(root / "kieker-amqp.spool")
    bodies = []
    deliveries = []
    for index, started in enumerate(starts):
        tin = int(started.timestamp() * 1_000_000_000)
        records = [
            {"class_name": kieker.OER_CLASS,
             "operationSignature": "public boolean tools.descartes.teastore.auth.Auth.login()",
             "sessionId": "sweep-fixture", "traceId": 10_000 + index, "tin": tin + 20_000_000,
             "tout": tin + 60_000_000, "hostname": "auth", "eoi": 0, "ess": 0},
            {"class_name": kieker.OER_CLASS,
             "operationSignature": "public void tools.descartes.teastore.persistence.Persistence.find()",
             "sessionId": "sweep-fixture", "traceId": 10_000 + index, "tin": tin + 30_000_000,
             "tout": tin + 50_000_000, "hostname": "persistence", "eoi": 1, "ess": 1},
        ]
        deliveries.append(records[:1] if index in no_edge else records)
    for number, at in enumerate(clusters):
        deliveries.append(_cluster_records(kieker, 900_000 + number, at))
    for index, records in enumerate(deliveries):
        raw = kieker.build_fixture(records)
        spool.append_delivery(raw, {
            "schemaVersion": 1,
            "method": {"consumerTag": "sweep", "deliveryTag": index + 1, "redelivered": False, "exchange": "",
                       "routingKey": "kieker"},
            "properties": {"content_type": None, "content_encoding": None, "headers": {}, "delivery_mode": 2,
                           "priority": 0, "correlation_id": None, "reply_to": None, "expiration": None,
                           "message_id": f"sweep-{index:05d}", "timestamp": None, "type": "kieker",
                           "user_id": None, "app_id": "teastore", "cluster_id": None},
        })
        bodies.append(raw)
    spool.seal()
    aliases = kieker.load_runtime_host_service_map(root / "runtime-images.json")
    configuration, configuration_sha256 = kieker.frozen_attribution_configuration(aliases)
    traces, summary, counts = kieker.replay_spooled_events(
        root / "kieker-amqp.spool", re.compile(kieker.DEFAULT_SERVICE_REGEX), kieker.DEFAULT_SERVICE_MAP,
        configuration["effectiveHostAliases"])
    collector = kieker.KiekerNativeCollector(runtime_images_path=root / "runtime-images.json")
    for raw in bodies:
        collector.n_messages += 1
        collector.handle_body(raw)
    collector._spool_report = summary
    return traces, collector.stats(), summary, configuration_sha256


def _resources(tree, measurement: int) -> dict:
    probe = load("teastore_sweep_fixture_probe", tree["root"] / "modules/teastore/collectors/performance_probe_v3.py")
    start, slots = MEASUREMENT.timestamp(), measurement // 5
    identities = {service: f"{index + 1:064x}" for index, service in enumerate(APP)}
    samples = [{
        "slot": slot, "scheduledAtEpoch": start + slot * 5.0, "startedAtEpoch": start + slot * 5.0 + 0.1,
        "completedAtEpoch": start + slot * 5.0 + 2.0, "scheduledMonotonicOffsetSeconds": slot * 5.0,
        "startedMonotonicOffsetSeconds": slot * 5.0 + 0.1, "completedMonotonicOffsetSeconds": slot * 5.0 + 2.0,
        "startLatenessSeconds": 0.1, "integrationWeightSeconds": 5.0, "applicationCpuPercent": 5.0,
        "applicationCpuSecondsContribution": 0.25, "applicationMemoryBytes": 500.0,
        "containers": [{"service": service, "containerId": identities[service], "name": f"candidate-{service}-1",
                        "cpuPercent": 1.0, "memoryBytes": 100.0} for service in APP],
    } for slot in range(slots)]
    end = start + measurement
    return probe, {
        "schemaVersion": 3, "contract": probe.CONTRACT, "barrierId": BARRIER, "requestedStartAtEpoch": start,
        "nominalStartAtEpoch": start, "nominalEndAtEpoch": end, "measurementDurationSeconds": float(measurement),
        "collectorStartedAtEpoch": start - 5.0, "collectorEndedAtEpoch": end + 0.1,
        "clock": {"semantics": probe.CLOCK_SEMANTICS, "anchorWallEpoch": start - 5.0,
                  "anchorMonotonicSeconds": 1000.0, "barrierMonotonicSeconds": 1005.0,
                  "collectorStartedMonotonicOffsetSeconds": -5.0,
                  "collectorEndedMonotonicOffsetSeconds": measurement + 0.1},
        "sampling": {"semantics": probe.SAMPLING_SEMANTICS, "intervalSeconds": 5.0, "commandTimeoutSeconds": 4.0,
                     "expectedSlots": slots, "completedSlots": slots, "missedSlots": [],
                     "maximumStartLatenessSeconds": 1.0},
        "excludedServices": ["db", "rabbitmq", "registry"], "requiredServices": list(APP),
        "containerIdentity": identities, "samples": samples,
        "applicationCpuSeconds": 0.25 * slots, "applicationMemoryPeakBytes": 500.0, "hostCpuSeconds": 1.0,
        "hostCpuScope": probe.HOST_CPU_SCOPE,
        "hostCpuAccounting": {"tickRateHz": 100,
                              "start": {"totalTicks": 100_000, "idleTicks": 50_000, "monotonicOffsetSeconds": 0.0},
                              "end": {"totalTicks": 100_000 + 100 * measurement,
                                      "idleTicks": 50_000 + 100 * measurement - 100,
                                      "monotonicOffsetSeconds": float(measurement)},
                              "busyTicks": 100},
    }


def _intervention(timing: dict, regime: str) -> dict:
    fault = timing["fault"]
    onset = timing["faultOnsetSeconds"]
    issued, returned = onset + 0.01, onset + 0.26
    first = returned + 0.001
    final = first + 60.0
    reverting, reverted = final + 0.06, final + 0.3
    probe_start, probe_end = reverted + 0.01, reverted + 0.12
    ready = probe_end + 0.001
    target = "c" * 64

    def wall(offset: float) -> str:
        return _t(MEASUREMENT + timedelta(seconds=offset))
    throttle = fault == "persistence-cpu-throttle"
    if throttle:
        onset_vector = ["docker", "update", "--cpus", "0.1", target]
        recovery_vector = ["docker", "update", "--cpus", "24", target]
        during = {"exists": True, "running": True, "paused": False, "status": "running", "returnCode": 0,
                  "nanoCpus": 100_000_000}
        pre = {"exists": True, "running": True, "paused": False, "status": "running", "returnCode": 0,
               "nanoCpus": 0}
        post = dict(pre, nanoCpus=24_000_000_000)
    else:
        onset_vector = ["docker", "compose", "pause", "auth"]
        recovery_vector = ["docker", "compose", "unpause", "auth"]
        during = {"exists": True, "running": True, "paused": True, "status": "paused", "returnCode": 0}
        pre = {"exists": True, "running": True, "paused": False, "status": "running", "returnCode": 0}
        post = dict(pre)
    onset_result = {"command": onset_vector, "returnCode": 0, "stdout": "", "stderr": ""}
    recovery_result = {"command": recovery_vector, "returnCode": 0, "stdout": "", "stderr": ""}
    return {
        "schemaVersion": 3, "scenario": fault, "service": "persistence" if throttle else "auth",
        "independentOfKieker": True, "intervalLabel": "intervention-exposure", "functionalOutage": None,
        "measurementBarrier": {"id": BARRIER, "wall": _t(MEASUREMENT), "scheduledOnsetSeconds": onset,
                               "scheduledOnsetWall": _t(MEASUREMENT + timedelta(seconds=onset))},
        "requestedHoldSeconds": 60, "targetContainerId": target,
        "targetImage": {"containerId": target, "declaredImage": "x", "containerImageId": "sha256:" + "d" * 64,
                        "imageInspectId": "sha256:" + "d" * 64, "repoDigests": []},
        "preState": pre, "commandVector": onset_vector, "commandResult": onset_result,
        "actualOnsetWall": wall(first), "actualOnsetMonotonicOffsetSeconds": first,
        "actualOffsetWall": wall(final), "actualOffsetMonotonicOffsetSeconds": final,
        "duringStateSamples": [
            {"phase": phase, "observedAtWall": wall(at), "observedAtMonotonicOffsetSeconds": at, "state": during}
            for phase, at in (("manifested", first), ("hold-midpoint", first + 30.0), ("hold-end", final))],
        "recoveryAction": {"commandVector": recovery_vector, "commandResult": recovery_result},
        "sameTargetIdentity": True,
        "readiness": {"predicate": "all-five-application-services-report-OK", "observedAtWall": wall(ready),
                      "observedAtMonotonicOffsetSeconds": ready, "successful": True},
        "postState": post, "interventionThreadJoined": True, "laterInterventionMutationObserved": False,
        "manifested": True, "recovered": True, "outageHeld": True, "successful": True, "error": None,
        "operational": {"controllerStartedAt": wall(0.0), "controllerEndedAt": wall(ready + 0.01),
                        "commandResults": [onset_result, recovery_result], "actualHoldSeconds": final - first,
                        "continuousTargetStateProven": False},
        "sweep": {
            "schemaVersion": 1, "onsetSource": "pre-command",
            "commandStamps": {
                "onsetCommandIssuedWall": wall(issued), "onsetCommandIssuedMonotonicOffsetSeconds": issued,
                "onsetCommandReturnedMonotonicOffsetSeconds": returned,
                "revertCommandIssuedWall": wall(reverting), "revertCommandIssuedMonotonicOffsetSeconds": reverting,
                "revertCommandReturnedMonotonicOffsetSeconds": reverted,
            },
            "probes": [{"phase": "post-revert-readiness", "request": "GET /tools.descartes.teastore.webui/status",
                        "startMonotonicOffsetSeconds": probe_start, "endMonotonicOffsetSeconds": probe_end,
                        "ready": True}],
            "throttle": {"cpus": "0.1", "nanoCpus": 100_000_000, "preNanoCpus": 0,
                         "hostNanoCpus": 24_000_000_000, "revertCpus": "24"} if throttle else None,
        },
    }


def make_sweep_run(tree, root: Path, cell: dict, failed: dict = None, no_edge: set = frozenset(),
                   clusters_at: list = (), log_extra: dict = None) -> Path:
    """One sealed sweep cell, as the producer writes it (before the controller adds cleanup and manifest).

    ``failed`` maps a journey index to whether its application witness and bridge lines are still logged: the
    journey times out at the client (15 s) either way.  ``no_edge`` journeys log only their auth record (the
    trace lacks the auth->persistence edge); ``clusters_at`` adds one unattributable cluster per offset (seconds
    after the barrier, or "readiness+<s>" relative to the fault receipt's readiness).  ``log_extra`` maps
    "auth" / "persistence" to raw text written into the middle of that service log (e.g. a stack trace).
    """
    failed = failed or {}
    validator, producer, witness, native_token = (
        tree["validator"], tree["producer"], tree["witness"], tree["native_token"])
    timing, key, regime = cell["timing"], cell["runKey"], cell["runKey"]["regime"]
    rate, measurement, offered = timing["journeysPerSecond"], timing["measurementSeconds"], timing["offered"]
    end = MEASUREMENT + timedelta(seconds=measurement)
    root.mkdir(parents=True)
    population = timing["workloadId"]
    opportunities, journeys, starts = [], [], []
    for index in range(offered):
        offset = index / rate
        started = MEASUREMENT + timedelta(seconds=offset + 0.001)
        starts.append(started)
        journey_id = f"journey-{index:032x}"
        opportunity = {
            "sequence": index, "journeyId": journey_id, "opportunityId": f"{population}:{index:06d}",
            "opaqueToken": journey_id, "tokenAllocatedAt": _t(WARMUP + timedelta(seconds=1)),
            "scheduledAt": _t(MEASUREMENT + timedelta(seconds=offset)), "scheduledMonotonicOffsetSeconds": offset,
        }
        opportunities.append(opportunity)
        took = 15.0 if index in failed else 0.08
        request = {"sequence": 0, "step": "login", "routeId": "login-action", "target": "/loginAction",
                   "actualStartMonotonic": offset + 0.001, "actualEndMonotonic": offset + 0.001 + took,
                   "startedAt": _t(started), "endedAt": _t(started + timedelta(seconds=took)),
                   "latencyMs": took * 1000, "statusCode": None if index in failed else 200,
                   "outcome": "failed" if index in failed else "succeeded",
                   "error": {"type": "TimeoutError"} if index in failed else None}
        journeys.append({**opportunity, "barrierId": BARRIER, "actualStartMonotonic": offset + 0.001,
                         "actualEndMonotonic": offset + 0.001 + took, "startedAt": _t(started),
                         "endedAt": _t(started + timedelta(seconds=took)),
                         "expectedPath": validator.EXPECTED_PATH, "requests": [request], "requestCount": 1,
                         "outcome": "timeout" if index in failed else "succeeded",
                         "errors": ([{"type": "TimeoutError", "scope": "request", "requestSequence": 0}]
                                    if index in failed else []),
                         "terminalSettled": True,
                         "endedAfterNominalWindow": offset + 0.001 + took > measurement})
    plan = {
        "artifactType": "teastore-expected-opportunity-plan", "schemaVersion": 1, "workloadId": population,
        "barrierId": BARRIER, "controllerStartedAt": _t(WARMUP), "barrierAt": _t(MEASUREMENT),
        "clock": {"wallClock": "UTC", "monotonicValues": "seconds-relative-to-barrier"},
        "schedule": {"kind": "fixed-open-loop", "journeysPerSecond": rate, "durationSeconds": float(measurement),
                     "offered": offered},
        "expectedPath": validator.EXPECTED_PATH, "tokenContract": validator.TOKEN_CONTRACT,
        "opportunities": opportunities,
    }
    plan_sha, previous, records = _canonical(plan), "0" * 64, []
    for sequence, journey in enumerate(journeys):
        record = {"artifactType": "teastore-journey-ledger-record", "schemaVersion": 1,
                  "recordType": "journey-terminal", "recordSequence": sequence, "previousRecordSha256": previous,
                  "planSha256": plan_sha, "workloadId": population, **journey}
        record["recordSha256"] = _canonical(record)
        previous = record["recordSha256"]
        records.append(record)
    reconciliation = {
        "artifactType": "teastore-journey-ledger-record", "schemaVersion": 1, "recordType": "reconciliation",
        "recordSequence": offered, "previousRecordSha256": previous, "planSha256": plan_sha,
        "workloadId": population, "barrierId": BARRIER, "state": "completed", "terminalReason": None,
        "expectedJourneys": offered, "terminalJourneys": offered,
        "terminalJourneyIdsSha256": _canonical(sorted(row["journeyId"] for row in journeys)),
        "terminalOpportunityIdsSha256": _canonical(sorted(row["opportunityId"] for row in journeys)),
        "finalizedAt": _t(end), "terminalSettled": True,
    }
    reconciliation["recordSha256"] = _canonical(reconciliation)
    records.append(reconciliation)
    _json(root / "journey-ledger.plan.json", plan)
    (root / "journey-ledger.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))
    readiness_offset = (_intervention(timing, regime)["readiness"]["observedAtMonotonicOffsetSeconds"]
                        if timing["fault"] is not None else None)
    cluster_times = [
        MEASUREMENT + timedelta(seconds=(readiness_offset + float(value.split("+", 1)[1]))
                                if isinstance(value, str) else float(value))
        for value in clusters_at]
    traces, stats, summary, attribution_sha256 = _spool(tree, root, starts, set(no_edge), cluster_times)
    for service, event in (("auth", "login-persistence-request"), ("persistence", "login-user-lookup")):
        lines = [witness.MARKER + json.dumps({
            "schema": witness.OBSERVATION_SCHEMA, "schemaVersion": 1,
            "observedAtUtc": _t(started + timedelta(milliseconds=20 if service == "auth" else 40)),
            "journeyId": row["opaqueToken"], "service": service, "event": event}, sort_keys=True) + "\n"
            for index, (started, row) in enumerate(zip(starts, journeys)) if failed.get(index, True)]
        if service == "auth":
            lines += [native_token.MARKER + json.dumps({"token": row["opaqueToken"],
                                                        "nativeTraceId": str(10_000 + index), "service": "auth"},
                                                       separators=(",", ":")) + "\n"
                      for index, row in enumerate(journeys) if failed.get(index, True)]
        if log_extra and service in log_extra:
            lines.insert(len(lines) // 2, log_extra[service])
        (root / f"{service}.log").write_text("".join(lines), encoding="utf-8")
    successful = [(row["actualEndMonotonic"] - row["actualStartMonotonic"]) * 1000 for row in journeys
                  if row["outcome"] == "succeeded"]
    stats_module = __import__("statistics")
    intervention = None if timing["fault"] is None else _intervention(timing, regime)
    probe, resources = _resources(tree, measurement)
    _json(root / "resources.json", resources)
    _json(root / "system-samples.json", {
        "schemaVersion": 1, "kind": validator.SYSTEM_SAMPLES_KIND, "project": "teastore_candidate_0123456789abcdef",
        "intervalSeconds": 5.0, "durationSeconds": float(measurement), "startAtEpoch": MEASUREMENT.timestamp(),
        "containers": {service: "c" * 64 for service in APP}, "requiredServices": sorted(APP),
        "requiredMissingAtStart": [],
        "samples": [{"epoch": MEASUREMENT.timestamp() + index * 5.0, "at": "x", "monotonic": 500.0 + index * 5.0,
                     "lateSeconds": 0.002, "daemons": {},
                     "services": {service: {"cpuUsageUsec": index, "memoryCurrent": 1, "rbytes": 0, "wbytes": 0,
                                            "psiCpuSomeTotalUsec": 0, "psiMemorySomeTotalUsec": 0,
                                            "psiIoSomeTotalUsec": 0} for service in APP}}
                    for index in range(timing["systemSampleCount"])],
    })
    (root / "application.log").write_text("".join(
        f"{service}-1  | {(MEASUREMENT + timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%S')}.123456789Z "
        f"started {service}\n" for service in APP))
    cost = regime == "no-fault-cost"
    receipt = {
        "schemaVersion": 2, "contract": validator.CONTRACT, "studyEpoch": SWEEP, "population": population,
        "selectionId": None,
        "source": {"sutCommit": validator.SUT_COMMIT, "frameworkCommit": FRAMEWORK_COMMIT, "frameworkDirty": False,
                   "host": "fb14srv5", "exclusiveLease": True,
                   "imageDigests": {"auth": "teastore-auth@sha256:" + "b" * 64},
                   "spoolSha256": _sha(root / "kieker-amqp.spool"),
                   "runtimeImagesSha256": _sha(root / "runtime-images.json"),
                   "collectorAttributionConfigurationSha256": attribution_sha256},
        "run": {"runId": cell["runId"], **{name: key[name] for name in ("regime", "block", "posture", "attempt")}},
        "analysisKind": "cost" if cost else "effect", "resourceUse": "cost-proxy" if cost else "diagnostic-only",
        "window": {"warmupStartedAt": _t(WARMUP), "warmupEndedAt": _t(WARMUP_END),
                   "warmupSettledAt": _t(WARMUP_SETTLED), "warmupDurationSeconds": 30,
                   "measurementStartedAt": _t(MEASUREMENT), "measurementEndedAt": _t(end),
                   "measurementStartMonotonic": 500.0, "measurementEndMonotonic": 500.0 + measurement,
                   "sharedBarrierId": BARRIER},
        "workload": {"offered": offered, "successful": offered - len(failed), "failed": 0,
                     "timedOut": len(failed), "requests": offered},
        "latencyMs": {"denominator": "successful-journeys", "count": len(successful),
                      "p50": validator._percentile(successful, 0.5), "p95": validator._percentile(successful, 0.95),
                      "p99": validator._percentile(successful, 0.99), "mean": stats_module.fmean(successful)},
        "resources": {
            "applicationCpuSeconds": resources["applicationCpuSeconds"],
            "applicationMemoryPeakBytes": 500.0, "hostCpuSeconds": 1.0, "contract": probe.CONTRACT,
            "artifactSha256": _sha(root / "resources.json"),
            "nominalStartAtEpoch": resources["nominalStartAtEpoch"],
            "nominalEndAtEpoch": resources["nominalEndAtEpoch"],
            "measurementDurationSeconds": float(measurement), "samplingIntervalSeconds": 5.0,
            "offeredJourneys": offered,
            "applicationCpuSecondsPerOfferedJourney": resources["applicationCpuSeconds"] / offered,
        } if cost else None,
        "intervention": intervention,
        "exposureTolerance": producer.exposure_tolerance(traces, intervention, fault=timing["fault"] or "none"),
        "telemetry": {"collectorStats": stats, "spool": summary},
        "artifacts": {},
        "timing": copy.deepcopy(timing),
    }
    _json(root / "traces.json", traces)
    _json(root / "capture-terminal.json", {
        "complete": True, "settled": True, "hashReconciled": True, "queuePurgedBefore": True,
        "queueMessagesAtBarrier": 0, "exclusiveCollector": True, "foreignWriters": 0, "unjoinedChildren": 0,
        "rawRecords": len(traces),
        "measurementRecords": sum(MEASUREMENT <= tree["validator"]._native_time(row) < end for row in traces),
        "uniqueNativeTraces": len({tree["validator"]._original_native_trace_id(row) for row in traces}),
        "uniqueSignatures": len({row.get("signature_sha1") for row in traces}),
        "uniqueMessageBodies": len({row.get("message_sha1") for row in traces}), "redeliveredMessageSha1": [],
    })
    _operational_proofs(tree, root, measurement)
    if intervention is not None:
        _json(root / "intervention.json", intervention)
    _json(root / "receipt.json", receipt)
    _json(root / "service-log-capture.json", {
        "schema": "teastore.service-log-capture-receipt", "schemaVersion": 1, "status": "complete",
        "runId": cell["runId"], "service": "auth", "containerId": "a" * 64,
        "source": "docker-container-stdout-stderr",
        "measurementWindow": {"startedAt": _t(MEASUREMENT), "endedAt": _t(end)},
        "capturedLog": {"scope": "measurement-window", "path": "auth.log", "sha256": _sha(root / "auth.log"),
                        "complete": True},
        "logParameters": {"name": "LOG_PARAMETERS", "inspectionSource": "container-config-env", "state": "absent",
                          "rawValue": None, "parameterLoggingEnabled": False},
    })
    witness.extract(auth_log=root / "auth.log", persistence_log=root / "persistence.log",
                    journey_ledger=root / "journey-ledger.jsonl", run_receipt=root / "receipt.json",
                    output=root / "app-witness.jsonl", extraction_receipt=root / "app-witness-extraction.json")
    native_token.extract(auth_log=root / "auth.log", journey_ledger=root / "journey-ledger.jsonl",
                         traces=root / "traces.json", run_receipt=root / "receipt.json",
                         service_log_capture_receipt=root / "service-log-capture.json",
                         posture_proof=root / "posture-proof.json", output=root / "native-token-correlation.json",
                         extraction_receipt=root / "native-token-correlation-extraction.json")
    _rehash(tree, root)
    return root


def _compiled_cells() -> list:
    return sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor()))


def _cell(regime: str, rate: float) -> dict:
    return next(cell for cell in _compiled_cells()
                if cell["runKey"]["regime"] == regime and cell["timing"]["journeysPerSecond"] == rate)


def _failed_gates(report) -> list:
    return [row["gate"] for row in report["validationTable"] if row["status"] == "fail"]


@pytest.mark.parametrize("regime,rate", [(regime, rate) for regime in sweep.REGIMES for rate in RATES])
def test_a_sealed_sweep_cell_is_accepted_at_every_rate_and_regime(tree, tmp_path, regime, rate):
    cell = _cell(regime, rate)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    report = tree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", _failed_gates(report)
    gates = report["protocolGates"]
    assert gates["failedGates"] == [] and gates["notEvaluated"] == ["P0", "R1", "R2"]
    assert gates["blocking"] == (["F1", "G1", "G2", "G4"] if cell["timing"]["faultApplied"] else ["G1", "G2", "G4"])


def _mutate(tree, root: Path, name: str, mutate, *, rehash: bool = True) -> None:
    value = json.loads((root / name).read_text())
    mutate(value)
    _json(root / name, value)
    if name == "intervention.json":
        receipt = json.loads((root / "receipt.json").read_text())
        receipt["intervention"] = value
        _json(root / "receipt.json", receipt)
    if rehash:
        _rehash(tree, root)


@pytest.mark.parametrize("rate", RATES)
def test_a_sweep_cell_with_one_journey_missing_is_rejected_at_every_rate(tree, tmp_path, rate):
    cell = _cell("no-fault-cost", rate)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    lines = (root / "journey-ledger.jsonl").read_text().splitlines(keepends=True)
    (root / "journey-ledger.jsonl").write_text("".join(lines[:3] + lines[4:]))
    _rehash(tree, root)
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert report["verdict"] == "blocked"
    assert {"pre-outcome-plan-and-ledger-chain", "offered-ledger-denominator"} <= set(_failed_gates(report))


def test_a_receipt_bringing_its_own_timing_is_rejected(tree, tmp_path):
    cell = _cell("auth-freeze-effect", 1.0)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    _mutate(tree, root, "receipt.json", lambda receipt: receipt["timing"].update(journeysPerSecond=2.0))
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert "sweep-compiled-timing" in _failed_gates(report)


def test_a_receipt_from_another_rate_of_the_same_run_key_is_rejected(tree, tmp_path):
    cell, other = _cell("auth-freeze-effect", 1.0), _cell("auth-freeze-effect", 0.2)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    report = tree["validator"].validate_run(root, expected={**other["runKey"], "runId": other["runId"]})
    assert cell["runKey"] == other["runKey"] and "campaign-run-binding" in _failed_gates(report)


@pytest.mark.parametrize("plant", ["early-onset-stamp", "post-command-stamp", "revert-before-hold-end",
                                   "probe-outside-recovery", "probe-missing", "throttle-record-on-pause"])
def test_planted_command_stamp_defects_are_rejected(tree, tmp_path, plant):
    cell = _cell("auth-freeze-effect", 0.2)
    root = make_sweep_run(tree, tmp_path / "run", cell)

    def mutate(intervention):
        stamps = intervention["sweep"]["commandStamps"]
        if plant == "early-onset-stamp":
            stamps["onsetCommandIssuedMonotonicOffsetSeconds"] -= 1.0
        elif plant == "post-command-stamp":
            stamps["onsetCommandIssuedMonotonicOffsetSeconds"] = (
                stamps["onsetCommandReturnedMonotonicOffsetSeconds"] + 0.01)
        elif plant == "revert-before-hold-end":
            stamps["revertCommandIssuedMonotonicOffsetSeconds"] = (
                intervention["actualOffsetMonotonicOffsetSeconds"] - 1.0)
        elif plant == "probe-outside-recovery":
            intervention["sweep"]["probes"][0]["startMonotonicOffsetSeconds"] = 1.0
        elif plant == "probe-missing":
            intervention["sweep"]["probes"] = []
        elif plant == "throttle-record-on-pause":
            intervention["sweep"]["throttle"] = {"cpus": "0.1"}
    _mutate(tree, root, "intervention.json", mutate)
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert "sweep-fault-command-stamps" in _failed_gates(report)


@pytest.mark.parametrize("gate,attribute,value", [
    ("F1", "ONSET_TOLERANCE_S", 0.001), ("F1", "HOLD_TOLERANCE_S", -5.0),
    ("G1", "G1_MIN_DISPATCHED", 10_000), ("G2", "PRE_FAIL_MAX", -1.0),
])
def test_each_blocking_protocol_gate_can_block_a_sweep_cell(tree, tmp_path, monkeypatch, gate, attribute, value):
    cell = _cell("auth-freeze-effect", 1.0)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    validator = tree["validator"]
    assert validator.validate_run(root, expected=cell["runKey"])["verdict"] == "pass"
    monkeypatch.setattr(validator._protocol_gates(), attribute, value)
    report = validator.validate_run(root, expected=cell["runKey"])
    assert _failed_gates(report) == ["protocol-gates"] and gate in report["protocolGates"]["failedGates"]


def test_a_pre_onset_failure_at_the_lowest_rate_fails_g2(tree, tmp_path):
    cell = _cell("persistence-cpu-throttle-effect", 0.05)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    report = tree["validator"].sweep_protocol_gates(
        run_id=cell["runId"], posture="full", timing=cell["timing"],
        plan=json.loads((root / "journey-ledger.plan.json").read_text()),
        journeys=[{**row, "outcome": "timeout" if row["sequence"] == 1 else row["outcome"]}
                  for row in (json.loads(line) for line in (root / "journey-ledger.jsonl").read_text().splitlines())
                  if row["recordType"] == "journey-terminal"],
        intervention=json.loads((root / "intervention.json").read_text()), harness_valid=True)
    assert report["failedGates"] == ["G2"]


def test_a_stray_byte_in_the_application_log_is_counted_not_fatal(tree, tmp_path):
    cell = _cell("no-fault-cost", 0.2)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    with (root / "application.log").open("ab") as stream:
        stream.write(b"db-1  | 2026-10-03T01:00:52.1Z binary \xff\xfe\n")
    _rehash(tree, root)
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert report["verdict"] == "pass", _failed_gates(report)
    row = next(row for row in report["validationTable"] if row["gate"] == "application-log-timestamps")
    assert row["observation"]["undecodableCharacters"] == 2


@pytest.mark.parametrize("plant", ["service-missing", "unstamped", "absent"])
def test_the_application_log_must_be_timestamped_for_every_service(tree, tmp_path, plant):
    cell = _cell("no-fault-cost", 0.2)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    log = root / "application.log"
    if plant == "service-missing":
        log.write_text("".join(line + "\n" for line in log.read_text().splitlines() if not line.startswith("webui")))
    elif plant == "unstamped":
        log.write_text(re.sub(r"\| \S+ ", "| ", log.read_text()))
    else:
        log.unlink()
    _rehash(tree, root)
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert "application-log-timestamps" in _failed_gates(report)


@pytest.mark.parametrize("plant", ["frozen-warmup", "frozen-system-samples", "frozen-schedule"])
def test_frozen_literals_inside_a_sweep_cell_are_rejected(tree, tmp_path, plant):
    cell = _cell("auth-freeze-effect", 0.05)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    if plant == "frozen-warmup":
        _mutate(tree, root, "receipt.json", lambda receipt: receipt["window"].update(warmupDurationSeconds=120))
        gate = "shared-window"
    elif plant == "frozen-system-samples":
        _mutate(tree, root, "system-samples.json", lambda samples: samples.update(durationSeconds=600.0))
        gate = "system-samples"
    else:
        _mutate(tree, root, "journey-ledger.plan.json",
                lambda plan: plan["schedule"].update(journeysPerSecond=0.15))
        gate = "pre-outcome-plan-and-ledger-chain"
    assert gate in _failed_gates(tree["validator"].validate_run(root, expected=cell["runKey"]))


def test_the_phase_floor_is_the_compiled_one_not_the_frozen_twenty(tree, tmp_path):
    cell = _cell("auth-freeze-effect", 0.05)
    root = make_sweep_run(tree, tmp_path / "run", cell)
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    row = next(row for row in report["validationTable"] if row["gate"] == "actual-phase-start-floor")
    assert row["status"] == "pass" and row["observation"]["floors"] == cell["timing"]["minimumActualStartsByPhase"]
    assert all(row["observation"]["observed"][phase] < 20 for phase in ("before", "during", "after"))


def test_the_sweep_campaign_replays_its_own_allocation(tree, tmp_path, monkeypatch):
    adapter = tree["adapter"]
    monkeypatch.setattr(adapter, "_git_repository_state", _git_state(adapter))
    root = tmp_path / "campaign"
    materialized = tree["orchestrator"].materialize_campaign(root)
    for row, cell in zip(materialized["campaign"]["runs"], materialized["cells"]):
        assert row["runId"] == cell["runId"]
        make_sweep_run(tree, root / row["path"], cell)
    report = tree["validator"].validate_campaign(root)
    assert report["verdict"] == "pass", [(r["runKey"], _failed_gates(r)) for r in report["runReports"]]
    assert len(report["runReports"]) == 12
    campaign = json.loads((root / "campaign.json").read_text())
    campaign["runs"][0], campaign["runs"][1] = campaign["runs"][1], campaign["runs"][0]
    _json(root / "campaign.json", campaign)
    assert "scheduled-cell-population" in _failed_gates(tree["validator"].validate_campaign(root))


def test_the_terminal_requires_the_application_log_and_the_throttle_intervention(tree):
    terminal = tree["terminal"]
    key = {"studyEpoch": SWEEP, "regime": "persistence-cpu-throttle-effect", "block": 1, "posture": "full",
           "attempt": 1}
    assert {"application.log", "intervention.json"} <= terminal._required_for(key)
    assert "resources.json" in terminal._required_for({**key, "regime": "no-fault-cost"})
    with pytest.raises(terminal.TerminalError):
        terminal._required_for({**key, "regime": "persistence-crash-effect"})


# ------------------------------------------------------------------------------------- 8. vendoring, 3.9 floor
def test_vendored_protocol_gates_are_byte_identical():
    vendored = MODULE / "validation/protocol_gates.py"
    assert hashlib.sha256(vendored.read_bytes()).hexdigest() == PROTOCOL_GATES_SHA256
    if MEASUREMENT_REPO_GATES.is_file():
        assert vendored.read_bytes() == MEASUREMENT_REPO_GATES.read_bytes()


@pytest.mark.parametrize("relative", CHANGED_TARGET_FILES)
def test_changed_target_files_parse_at_the_python39_floor(relative):
    source = (MODULE / relative).read_text()
    tree_ = ast.parse(source, feature_version=(3, 9))
    future = any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
                 and any(alias.name == "annotations" for alias in node.names) for node in tree_.body)
    if not future:   # without postponed annotations an X | None annotation is evaluated at import on 3.9
        for node in ast.walk(tree_):
            annotation = getattr(node, "annotation", None) or getattr(node, "returns", None)
            assert not (isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr)), relative


@pytest.mark.skipif(not Path("/usr/bin/python3").exists(), reason="no system python3 (3.9 on the hosts)")
def test_changed_target_files_import_under_system_python_isolated(tmp_path):
    root = _copy_tree(tmp_path / "tree", {"schemaVersion": 1, "studyEpoch": SWEEP})
    script = (
        "import importlib.util, sys\n"
        "root = sys.argv[1]\n"
        "for relative in sys.argv[2:]:\n"
        "    spec = importlib.util.spec_from_file_location('m_' + str(abs(hash(relative))), root + '/' + relative)\n"
        "    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module\n"
        "    spec.loader.exec_module(module)\n"
        "print('ok', sys.version_info[:2])\n"
    )
    relatives = [f"modules/teastore/{relative}" for relative in CHANGED_TARGET_FILES]
    result = subprocess.run(
        ["/usr/bin/python3", "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script,
         str(root), *relatives],
        capture_output=True, text=True, cwd=root,
    )
    assert result.returncode == 0 and result.stdout.startswith("ok"), result.stderr[-2000:]


# --------------------------------------------------------------------- 9. the login-only workload, for real
def _login_stub():
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        paths: list = []

        def do_POST(self):
            Handler.paths.append(("POST", self.path))
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>home</html>")

        def do_GET(self):
            Handler.paths.append(("GET", self.path))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'<a href="category=1">c</a><a href="product?id=7">p</a>')

        def log_message(self, *args):
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, Handler.paths


def test_the_login_only_journey_is_one_post_with_a_complete_ledger(tmp_path):
    fixed_load = load("teastore_sweep_fixed_load_real", MODULE / "workload/fixed_load.py")
    server, paths = _login_stub()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/tools.descartes.teastore.webui"
        result = fixed_load.run(base, 20.0, 0.5, 4, 2.0, tmp_path / "ledger.jsonl", journey_kind="login-only")
    finally:
        server.shutdown()
    assert result["offered"] == result["successful"] == 10 and result["requests"] == 10
    assert paths == [("POST", "/tools.descartes.teastore.webui/loginAction")] * 10
    validation = fixed_load.validate_journey_ledger(tmp_path / "ledger.plan.json", tmp_path / "ledger.jsonl")
    assert validation["terminalJourneys"] == 10
    plan = json.loads((tmp_path / "ledger.plan.json").read_text())
    assert plan["workloadId"] == "login-only-v1" and plan["schedule"]["offered"] == 10
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    terminal = [row for row in rows if row["recordType"] == "journey-terminal"]
    assert all([request["step"] for request in row["requests"]] == ["login"] for row in terminal)
    assert all(row["workloadId"] == "login-only-v1" and row["opportunityId"].startswith("login-only-v1:")
               and row["actualStartMonotonic"] >= row["scheduledMonotonicOffsetSeconds"] - 1e-6
               and row["outcome"] == "succeeded" for row in terminal)


def test_the_default_journey_is_still_the_frozen_login_browse(tmp_path):
    fixed_load = load("teastore_sweep_fixed_load_default", MODULE / "workload/fixed_load.py")
    server, paths = _login_stub()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/tools.descartes.teastore.webui"
        fixed_load.run(base, 10.0, 0.1, 1, 2.0, tmp_path / "ledger.jsonl")
    finally:
        server.shutdown()
    assert [method for method, _ in paths][:2] == ["POST", "GET"] and len(paths) > 2
    plan = json.loads((tmp_path / "ledger.plan.json").read_text())
    assert plan["workloadId"] == "login-browse-v1"
    with pytest.raises(ValueError):
        fixed_load.run("http://127.0.0.1:9", 1.0, 1.0, 1, 1.0, tmp_path / "other.jsonl", journey_kind="checkout")


# ------------------------------------------------- 10. Q3: the post-readiness drain allowance (user, 2026-10-03)
def _readiness_of(root: Path) -> float:
    return json.loads((root / "intervention.json").read_text())["readiness"]["observedAtMonotonicOffsetSeconds"]


def test_the_drain_allowance_is_the_plan_timeout_plus_two_seconds():
    for cell in _compiled_cells():
        timing = cell["timing"]
        if timing["faultApplied"]:
            assert timing["drainAllowanceSeconds"] == timing["requestTimeoutSeconds"] + 2.0 == 17.0
        else:
            assert timing["drainAllowanceSeconds"] is None


@pytest.mark.parametrize("witness_logged", [False, True])
def test_a_failure_inside_the_drain_allowance_seals_valid_and_is_recorded(tree, tmp_path, witness_logged):
    cell = _cell("auth-freeze-effect", 1.0)
    probe = make_sweep_run(tree, tmp_path / "probe", cell)
    readiness = _readiness_of(probe)
    index = next(i for i in range(cell["timing"]["offered"]) if readiness + 3.0 <= i + 0.001 < readiness + 4.0)
    root = make_sweep_run(tree, tmp_path / "run", cell, failed={index: witness_logged})
    report = tree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", _failed_gates(report)
    journey_id = f"journey-{index:032x}"
    assert report["drainAllowance"]["excusedFailures"] == 1
    assert report["drainAllowance"]["excusedJourneyIds"] == [journey_id]
    assert report["drainAllowance"]["allowanceSeconds"] == 17.0
    row = next(row for row in report["validationTable"] if row["gate"] == "effect-context")
    assert row["observation"]["drainExcusedJourneyIds"] == [journey_id] and row["observation"]["count"] == 0


def test_a_failure_just_outside_the_drain_allowance_still_invalidates(tree, tmp_path):
    cell = _cell("auth-freeze-effect", 1.0)
    probe = make_sweep_run(tree, tmp_path / "probe", cell)
    readiness = _readiness_of(probe)
    index = next(i for i in range(cell["timing"]["offered"]) if i + 0.001 >= readiness + 17.0)
    assert index + 0.001 - (readiness + 17.0) < 1.0                     # the first start past the edge
    root = make_sweep_run(tree, tmp_path / "run", cell, failed={index: True})
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert report["verdict"] == "blocked" and "effect-context" in _failed_gates(report)
    assert report["drainAllowance"]["excusedFailures"] == 0
    with pytest.raises(tree["witness"].WitnessError):                   # and without its witness it is required
        make_sweep_run(tree, tmp_path / "unwitnessed", cell, failed={index: False})


def test_a_failure_before_onset_is_never_excused(tree, tmp_path):
    cell = _cell("persistence-cpu-throttle-effect", 1.0)
    root = make_sweep_run(tree, tmp_path / "run", cell, failed={10: True})
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert "effect-context" in _failed_gates(report) and report["drainAllowance"]["excusedFailures"] == 0


def test_a_no_fault_cell_has_no_drain_allowance(tree, tmp_path):
    cell = _cell("no-fault-cost", 1.0)
    index = 125                                                         # where a fault cell's allowance would be
    root = make_sweep_run(tree, tmp_path / "run", cell, failed={index: True})
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert report["verdict"] == "blocked" and "no-fault-workload-context" in _failed_gates(report)
    assert "drainAllowance" not in report
    with pytest.raises(tree["witness"].WitnessError):
        make_sweep_run(tree, tmp_path / "unwitnessed", cell, failed={index: False})


def test_the_frozen_epoch_has_no_drain_allowance():
    validator = load("teastore_sweep_frozen_validator_q3", MODULE / "validation/candidate_pilot.py")
    journey = {"actualStartMonotonic": 335.0, "actualEndMonotonic": 350.0, "outcome": "timeout"}
    intervention = {"actualOnsetMonotonicOffsetSeconds": 180.0, "actualOffsetMonotonicOffsetSeconds": 330.0,
                    "readiness": {"observedAtMonotonicOffsetSeconds": 330.5}}
    assert validator._phase_for(journey, "auth-freeze-effect", intervention) == "after"
    assert validator._drain_excused(journey, "auth-freeze-effect", intervention,
                                    {"drainAllowanceSeconds": 17.0}) is False
    assert study_epoch.drain_allowance({"timing": {"drainAllowanceSeconds": 17.0}}) == 17.0
    assert study_epoch.drain_allowance({}) is None



# ------------------------------- 11. decision 25: shared trace-completeness rule, journey unit (2026-10-03)
def _completeness(report) -> dict:
    return report["traceCompleteness"]


def test_the_cell_11_incident_validates_and_is_recorded_in_window_one(tree, tmp_path):
    """Attempt 1, cell 11: unattributable persistence records with repeated native identities, logged a few
    milliseconds after readiness (inside the drain window).  9a4ea56 blocked the cell (producer: residual
    correlation errors; validator: integrity and tolerance residuals); decision 25 records them."""
    cell = _cell("persistence-cpu-throttle-effect", 10.0)
    root = make_sweep_run(tree, tmp_path / "run", cell, clusters_at=["readiness+0.003", "readiness+0.07"])
    receipt = json.loads((root / "receipt.json").read_text())
    assert receipt["exposureTolerance"]["residualCorrelationErrorEvents"] == 6      # what blocked attempt 1
    report = tree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", _failed_gates(report)
    completeness = _completeness(report)
    window = completeness["windows"]["fault-and-drain"]
    assert window["unattributableClusters"] == 2 and window["defectiveRecordsByLoggingTime"] == 6
    assert completeness["incompleteInRuleTwo"] == 0 and completeness["blocking"] is False
    assert completeness["windowIMonotonicSeconds"][1] - _readiness_of(root) == pytest.approx(17.0)


def test_the_producer_defers_trace_completeness_only_for_sweep_cells(tree):
    producer = tree["producer"]
    stats = json.loads(json.dumps({
        "acknowledgement_mode": "manual", "runtime_host_map_loaded": True, "messages": 1, "records_ok": 1,
        "records_bad": 0, "containers_bad": 0,
        "correlation": {"eventsWithUnwovenRootParent": 2, "eventsWithProbeOrphanRoot": 0,
                        "eventsWithCorrelationErrors": 500, "eventsWithCorrelationWarnings": 0,
                        "eventsWithServiceAttributionErrors": 0,
                        "traceCompleteness": {"tracesWithEoiGaps": 3, "missingEoiCount": 4}},
    }))
    tolerance = {"applied": True, "toleratedCorrelationErrorEvents": 2, "toleratedEoiGapTraces": 0,
                 "toleratedMissingEoiCount": 0, "toleratedContainerParseFailures": 0, "containerParseFailures": []}
    frozen = producer.collector_process_blockers(0, None, stats, None, effect_contract=True, tolerance=tolerance)
    deferred = producer.collector_process_blockers(0, None, stats, None, effect_contract=True, tolerance=tolerance,
                                                   trace_completeness_deferred=True)
    assert any("native parent correlation errors" in b for b in frozen)
    assert any("missing native trace roots" in b for b in frozen) and any("EOI" in b for b in frozen)
    assert deferred == []


@pytest.mark.parametrize("clusters", [1, 40])
def test_window_one_never_blocks(tree, tmp_path, clusters):
    cell = _cell("auth-freeze-effect", 1.0)
    root = make_sweep_run(tree, tmp_path / "run", cell,
                          clusters_at=[f"readiness+{0.2 * k:.1f}" for k in range(clusters)])
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert report["verdict"] == "pass", _failed_gates(report)
    assert _completeness(report)["windows"]["fault-and-drain"]["unattributableClusters"] == clusters


@pytest.mark.parametrize("extra,verdict", [(0, "pass"), (1, "blocked")])
def test_rule_two_boundary_at_ten_per_second(tree, tmp_path, extra, verdict):
    """(ii) allowance = max(1, floor(1% x successful pre-onset and after-drain journeys)); at 10/s about 10."""
    cell = _cell("auth-freeze-effect", 10.0)
    probe = make_sweep_run(tree, tmp_path / "probe", cell)
    allowance = _completeness(tree["validator"].validate_run(probe, expected=cell["runKey"]))["allowance"]
    assert allowance >= 9
    pre_onset = [5.0 + 0.5 * k for k in range(allowance + extra)]       # unattributable clusters before onset
    root = make_sweep_run(tree, tmp_path / "run", cell, clusters_at=pre_onset)
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    assert report["verdict"] == verdict
    assert _completeness(report)["incompleteInRuleTwo"] == allowance + extra
    assert ("trace-completeness" in _failed_gates(report)) is (verdict == "blocked")


@pytest.mark.parametrize("missing_edges,verdict", [(1, "pass"), (2, "blocked")])
def test_low_rate_cell_allows_exactly_one_incomplete_journey(tree, tmp_path, missing_edges, verdict):
    """0.05/s: about five successful journeys outside window (i), so the allowance is max(1, 0) = 1."""
    cell = _cell("auth-freeze-effect", 0.05)
    root = make_sweep_run(tree, tmp_path / "run", cell, no_edge=set(range(missing_edges)))
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    completeness = _completeness(report)
    assert completeness["allowance"] == 1 and completeness["successfulJourneysInRuleTwo"] <= 6
    assert completeness["windows"]["pre-onset"]["incompleteJourneys"] == missing_edges
    assert completeness["windows"]["pre-onset"]["reasons"] == {"missing-auth-persistence-edge": missing_edges}
    assert report["verdict"] == verdict


@pytest.mark.parametrize("clusters,verdict", [(1, "pass"), (2, "blocked")])
def test_no_fault_cells_use_rule_two_everywhere(tree, tmp_path, clusters, verdict):
    cell = _cell("no-fault-cost", 1.0)
    # where a fault cell's window (i) would lie: in a no-fault cell it is still rule (ii)
    root = make_sweep_run(tree, tmp_path / "run", cell, clusters_at=[121.0 + k for k in range(clusters)])
    report = tree["validator"].validate_run(root, expected=cell["runKey"])
    completeness = _completeness(report)
    assert completeness["windowIMonotonicSeconds"] is None and list(completeness["windows"]) == ["whole-measurement"]
    assert completeness["allowance"] == 1 and completeness["incompleteInRuleTwo"] == clusters
    assert report["verdict"] == verdict


def test_a_cluster_outside_window_one_counts_where_it_was_logged(tree, tmp_path):
    cell = _cell("auth-freeze-effect", 1.0)
    root = make_sweep_run(tree, tmp_path / "run", cell, clusters_at=["readiness+17.5", "readiness+5"])
    completeness = _completeness(tree["validator"].validate_run(root, expected=cell["runKey"]))
    assert completeness["windows"]["after-drain"]["unattributableClusters"] == 1
    assert completeness["windows"]["fault-and-drain"]["unattributableClusters"] == 1
    assert completeness["incompleteInRuleTwo"] == 1


def test_the_frozen_epoch_keeps_its_zero_tolerance(tmp_path):
    import inspect
    root = _copy_tree(tmp_path)                                         # no selector: the frozen epoch
    validator = load("teastore_sweep_frozen_validator_d25", root / "modules/teastore/validation/candidate_pilot.py")
    producer = load("teastore_sweep_frozen_producer_d25", root / "modules/teastore/execution/performance_campaign.py")
    assert validator.SWEEP is False
    assert inspect.signature(producer.collector_process_blockers).parameters[
        "trace_completeness_deferred"].default is False


# --------------------- 12. JVM stack frames in the witness logs (relaunch 1, cell 11, 2026-10-03; sweep only)
# Relaunch 1 stopped at cell 11 (throttle, 10/s): persistence.log held JVM stack frames of a package named
# "...internal.sessions"; the unquoted-assignment rule read "<class>.<method>(<File>.java" as a key, and the
# normalized key embeds "session".  The frames here are synthesized (no retained log text).
def _synthetic_trace() -> str:
    frames = [("org.example.internal.sessions", "SessionCache", "lookupSession", "java"),
              ("org.example.auth.password", "PasswordCheck", "verifyPassword", "kt"),
              ("org.example.credentials", "CredentialVault", "open", "scala"),
              ("org.example.web.cookie", "CookieFilter", "doFilter", "groovy")]
    return ("org.example.store.LockTimeoutError: lock wait exceeded\n"
            + "".join(f"\tat {package}.{clazz}.{method}({clazz}.{extension}:{41 + index})\n"
                      for index, (package, clazz, method, extension) in enumerate(frames))
            + "\t... 3 more\n")


@pytest.mark.parametrize("regime,rate", [("persistence-cpu-throttle-effect", 10.0), ("no-fault-cost", 1.0)])
def test_jvm_stack_frames_in_the_witness_logs_seal_a_sweep_cell(tree, tmp_path, regime, rate):
    cell = _cell(regime, rate)
    trace = _synthetic_trace() * 3
    root = make_sweep_run(tree, tmp_path / "run", cell, log_extra={"auth": trace, "persistence": trace})
    assert trace in (root / "persistence.log").read_text() and trace in (root / "auth.log").read_text()
    report = tree["validator"].validate_run(root, expected={**cell["runKey"], "runId": cell["runId"]})
    assert report["verdict"] == "pass", _failed_gates(report)


def _scanner_callers(modules: dict) -> list:
    """The three blocking callers of validation/secret_scan.py, each on one log file / payload."""
    return [
        ("witness", lambda path: modules["witness"]._read_observations(path, "persistence"),
         modules["witness"].WitnessError),
        ("native_token", lambda path: modules["native_token"]._bridge_rows(path.read_bytes()),
         modules["native_token"].CorrelationError),
        ("validator", lambda path: modules["validator"]._application_source_observations(path, "persistence"),
         ValueError),
    ]


def _frozen_tree(tmp_path: Path) -> dict:
    root = _copy_tree(tmp_path / "frozen-tree")                        # no selector: the frozen epoch
    tag = hashlib.sha256(str(root).encode()).hexdigest()[:8]
    return {key: load(f"teastore_jvm_frames_frozen_{key}_{tag}", root / "modules/teastore" / relative)
            for key, relative in (("witness", "witness/extract_app_witness.py"),
                                  ("native_token", "witness/extract_native_token_correlation.py"),
                                  ("validator", "validation/candidate_pilot.py"))}


def test_the_three_callers_share_one_scanner_and_scope_the_frame_rule_to_the_sweep(tree, tmp_path):
    log = tmp_path / "frames.log"
    log.write_text(_synthetic_trace(), encoding="utf-8")
    frozen = _frozen_tree(tmp_path)
    for modules, sweep_active in ((tree, True), (frozen, False)):
        assert modules["witness"].SWEEP_EPOCH_ACTIVE is sweep_active
        assert modules["native_token"].SWEEP_EPOCH_ACTIVE is sweep_active
        assert modules["validator"].SWEEP is sweep_active
        scanners = {Path(modules[key]._SECRET_SCAN.__file__).resolve() for key in ("witness", "native_token",
                                                                                     "validator")}
        assert len(scanners) == 1 and next(iter(scanners)).parts[-2:] == ("validation", "secret_scan.py")
        for name, call, error in _scanner_callers(modules):
            if sweep_active:
                assert call(log) == [], name
            else:
                with pytest.raises(error, match="secret-bearing"):
                    call(log)


@pytest.mark.parametrize("planted", [
    "\tat org.example.internal.sessions.Store.load(Store.java:abc)\n",
    "\tat org.example.internal.sessions.Store.load(Store.java=12)\n",
    "password=planted-not-a-real-secret\n",
    "session: planted-not-a-real-secret\n",
    '{"password": 1}\n',
    "Authorization: Bearer planted-not-a-real-token\n",
    "sessionToken: planted-not-a-real-secret\n",
    "\tat org.example.sessions.Store.load(Store.java:12) password=planted-not-a-real-secret\n",
])
def test_every_caller_still_blocks_non_frame_secrets_in_the_sweep(tree, tmp_path, planted):
    log = tmp_path / "planted.log"
    log.write_text(_synthetic_trace() + planted, encoding="utf-8")
    for name, call, error in _scanner_callers(tree):
        with pytest.raises(error, match="secret-bearing"):
            call(log)


def test_a_sweep_cell_with_a_non_frame_secret_in_the_persistence_log_is_refused(tree, tmp_path):
    cell = _cell("persistence-cpu-throttle-effect", 10.0)
    with pytest.raises(tree["witness"].WitnessError, match="persistence log contains secret-bearing raw text"):
        make_sweep_run(tree, tmp_path / "run", cell, log_extra={
            "persistence": _synthetic_trace() + "\tat org.example.sessions.Store.load(Store.java:x1)\n"})
