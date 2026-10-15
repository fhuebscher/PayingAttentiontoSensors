"""otel-traffic-sweep-v1: a second, parameterised OTel Demo epoch beside the frozen otel-demo-offpath-v1.

Covers: the 12-cell plan is deterministic from its seed and pinned; offered per cell is rate x measurement; the
onset offset is seeded per (regime, rate, block) and independent of the attempt; the frozen epoch's files, digests,
runtime constants, contracts and cell runner are unchanged; the committed selector activates the sweep (runtime,
setup controller set, adapter, driver config); the GATE chain derives 12 cells, the sweep budget and the run window;
one fake-driven execution of the target's per-cell runner for every regime (which no other test executes), with a
compressed clock and a fake SUT, whose artifacts the terminal validator then accepts; planted defects in those
artifacts are rejected; and the 3.9 floor of every changed target-side file.

The sweep is exercised in a copy of the module tree with execution/study-epoch.json written into it, which is
exactly what the target sees after the selector is committed; the worktree itself stays on the frozen epoch.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import threading
import time as real_time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
SWEEP = "otel-traffic-sweep-v1"
OFFPATH = "otel-demo-offpath-v1"
BASE_COMMIT = "92be2b7"
RATES = (10.0, 1.0, 0.2, 0.05)

# Pinned: the sweep's reviewed digests (attempt 1) and the frozen offpath epoch this change must leave alone.
SWEEP_DESCRIPTOR_SHA256 = "be5b0b4dcd212aaa47908a6dd533e5cb73a104ab22b1b9e04a147e21ccb2c86d"
SWEEP_PLAN_A1_SHA256 = "09b2563a7f15a0d50da49418b7aa9be203c4e1ecbfe95faf9edebf9729924865"
SWEEP_PLAN_A2_SHA256 = "fa770ccf62f3eca24081d0c9ca004c05104250da69ee3422bcf8a172b5349498"
OFFPATH_DESCRIPTOR_SHA256 = "1491657d8d3c2a3271aa37e837f28f73c4c4bad297e37cb899a28d9efd2742f6"
OFFPATH_PLAN_A1_SHA256 = "168699c4d78a50766655254a58612b9ef0caf1ad91480b79852752bc933a47cc"
FROZEN_CONTROLLER_KEYS = {
    "candidate-compiler", "runtime-admission", "remote-setup-controller", "remote-compose-controller",
    "candidate-terminal", "unsupported-disposition", "materializer", "workload", "posture-catalog",
    "target-contract", "base-compose-overlay", "candidate-posture-overlay",
}
SWEEP_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
}
NOW = datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sweep = load("otel_traffic_sweep_compiler_test", MODULE / "execution/candidate_sweep.py")
frozen_pilot = load("otel_traffic_sweep_frozen_pilot_test", MODULE / "execution/candidate_pilot.py")
frozen_runtime = load("otel_traffic_sweep_frozen_runtime_test", MODULE / "execution/candidate_runtime.py")
frozen_remote = load("otel_traffic_sweep_frozen_remote_test", MODULE / "execution/candidate_remote.py")
frozen_setup = load("otel_traffic_sweep_frozen_setup_test", MODULE / "execution/candidate_setup.py")


def _git_show(relative: str, commit: str = BASE_COMMIT) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative}"], capture_output=True, check=True,
    ).stdout


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------------------------------- the copied trees
def _copy_tree(root: Path, *, selector: str | None) -> Path:
    shutil.copytree(MODULE, root / "modules/otel-demo", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / "pipelines/campaigns").mkdir(parents=True)
    for path in (ROOT / "pipelines/campaigns").glob("otel-*.json"):
        shutil.copyfile(path, root / "pipelines/campaigns" / path.name)
    (root / "upstream").mkdir()
    (root / "upstream/opentelemetry-demo").symlink_to(ROOT / "upstream/opentelemetry-demo")
    if selector is not None:
        (root / "modules/otel-demo/execution/study-epoch.json").write_text(selector)
    return root


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """A copy of the module tree with the selector committed: modules loaded from it run the sweep epoch."""
    root = _copy_tree(
        tmp_path_factory.mktemp("sweep-tree"),
        selector=json.dumps({"schemaVersion": 1, "studyEpoch": SWEEP}) + "\n",
    )
    module = root / "modules/otel-demo"
    loaded = types.SimpleNamespace(root=root)
    loaded.runtime = load("otel_sweep_tree_runtime", module / "execution/candidate_runtime.py")
    loaded.remote = load("otel_sweep_tree_remote", module / "execution/candidate_remote.py")
    loaded.setup = load("otel_sweep_tree_setup", module / "execution/candidate_setup.py")
    loaded.compiler = load("otel_sweep_tree_compiler", module / "execution/candidate_sweep.py")
    loaded.terminal = load("otel_sweep_tree_terminal", module / "validation/candidate_terminal.py")
    # The terminal's own runtime and remote handles must be this tree's.
    sys.modules["otel_candidate_terminal_runtime"] = loaded.runtime
    sys.modules["otel_candidate_terminal_remote"] = loaded.remote
    return loaded


@pytest.fixture(autouse=True)
def _terminal_handles(request):
    """Every test that loads `tree` gets the terminal bound to that tree's runtime and remote; others leave the
    shared module names to whichever test module set them."""
    if "tree" in request.fixturenames:
        loaded = request.getfixturevalue("tree")
        saved = {name: sys.modules.get(name) for name in ("otel_candidate_terminal_runtime", "otel_candidate_terminal_remote")}
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


# ------------------------------------------------------------------------------------------ 1. the sweep plan
def test_sweep_plan_is_12_cells_pinned_and_deterministic_from_its_recorded_seed():
    descriptor = sweep.load_descriptor()
    assert sweep.canonical_sha256(descriptor) == sweep.EXPECTED_DESCRIPTOR_SHA256 == SWEEP_DESCRIPTOR_SHA256
    # The checked-in descriptor is the generator's output, byte for byte (regenerate, never hand-edit).
    assert sweep.DEFAULT_DESCRIPTOR.read_bytes() == sweep._pretty_bytes(sweep.derive_sweep_descriptor())
    first, second = sweep.compile_plan(descriptor), sweep.compile_plan(copy.deepcopy(descriptor))
    assert first == second
    assert sweep.canonical_sha256(first) == SWEEP_PLAN_A1_SHA256
    assert descriptor["schedule"]["seed"] == sweep.SCHEDULE_SEED == 20261003
    cells = sweep.flatten_cells(first)
    assert len(cells) == sweep.TOTAL_RUNS == 12 == first["runCount"] == first["uniqueRunCount"]
    pairs = [(cell["runKey"]["regime"], cell["runKey"]["requestsPerSecond"]) for cell in cells]
    assert sorted(pairs) == sorted((regime, rate) for regime in sweep.REGIMES for rate in RATES)
    assert pairs[0] == ("frontend-pause-effect", 10.0)            # the lead cell
    assert [cell["ordinalPosition"] for cell in cells] == list(range(1, 13))
    assert {cell["runKey"]["posture"] for cell in cells} == {"full"}
    # The order after the lead cell is the seeded shuffle, and another seed gives another order.
    original = [(row["regime"], row["rate"]) for row in sweep.block_order(1)]
    try:
        sweep.SCHEDULE_SEED = 1
        assert [(row["regime"], row["rate"]) for row in sweep.block_order(1)] != original
    finally:
        sweep.SCHEDULE_SEED = 20261003


def test_every_cell_offers_rate_times_measurement_with_a_seeded_onset_inside_one_inter_arrival():
    cells = sweep.flatten_cells(sweep.compile_plan(sweep.load_descriptor()))
    offsets = {}
    for cell in cells:
        timing = cell["timing"]
        rate = cell["runKey"]["requestsPerSecond"]
        assert timing["requestsPerSecond"] == rate
        assert timing["offered"] == round(rate * 180) and timing["measurementSeconds"] == 180
        assert timing["warmupSeconds"] == 30 and timing["warmupRequestsPerSecond"] == 10.0 and timing["warmupOffered"] == 300
        assert 0 <= timing["faultOnsetPhaseOffsetSeconds"] < 1 / rate
        assert timing["faultOnsetSeconds"] == round(60 + timing["faultOnsetPhaseOffsetSeconds"], 6)
        assert timing["faultHoldSeconds"] == 60
        assert timing["scoredWindowSeconds"] == [timing["faultOnsetSeconds"], round(timing["faultOnsetSeconds"] + 60, 6)]
        assert timing["requestTimeoutSeconds"] == 15.0 and timing["concurrency"] == 300
        assert timing["route"] == {"method": "GET", "path": "/api/products/66VCHSJNUP",
                                   "services": ["frontendproxy", "frontend", "productcatalogservice"]}
        assert timing["upstreamGeneratorsOff"] == ["loadgenerator"]
        assert timing["planRunCount"] == 12 and timing["planMinimumRemainingSeconds"] == sweep.MINIMUM_REMAINING_SECONDS
        assert timing["faultApplied"] == (cell["fault"] is not None)
        if cell["fault"] is None:
            assert timing["scheduledSlotsByPhase"] is None    # no-fault cells carry the pseudo window only
        else:
            assert min(timing["scheduledSlotsByPhase"].values()) >= 1
        offsets[(cell["runKey"]["regime"], rate)] = timing["faultOnsetPhaseOffsetSeconds"]
    # Distinct per (regime, rate): the offset is a draw, not a constant.
    assert len(set(offsets.values())) == len(offsets)


def test_the_onset_offset_and_timing_do_not_depend_on_the_attempt_but_run_ids_do():
    descriptor = sweep.load_descriptor()
    one = sweep.flatten_cells(sweep.compile_plan(descriptor, 1))
    two = sweep.flatten_cells(sweep.compile_plan(descriptor, 2))
    assert [cell["timing"] for cell in one] == [cell["timing"] for cell in two]
    assert {cell["runId"] for cell in one}.isdisjoint({cell["runId"] for cell in two})
    with pytest.raises(sweep.ProtocolError, match="mixes attempts"):
        mixed = sweep.compile_plan(descriptor, 1)
        mixed["blocks"][0]["cells"][3]["runKey"]["attempt"] = 2
        sweep.plan_attempt(mixed)


def test_without_the_onset_offset_every_low_rate_onset_falls_on_a_scheduled_request():
    for rate in RATES:
        assert (60 * rate) == int(60 * rate)                  # 60 s is a whole number of inter-arrivals
    try:
        sweep.ONSET_PHASE_OFFSET = "none"
        assert all(sweep.onset_phase_offset(regime, rate, 1) == 0.0 for regime in sweep.REGIMES for rate in RATES)
    finally:
        sweep.ONSET_PHASE_OFFSET = "seeded-stratified-within-one-inter-arrival"


def test_budget_and_run_window_are_derived_from_the_plan():
    assert sweep.TIMED_SECONDS_PER_CELL == 30 + 1 + 180
    assert sweep.CELL_PERIOD_ESTIMATE_SECONDS == sweep.TIMED_SECONDS_PER_CELL + sweep.CELL_OVERHEAD_SECONDS == 331
    assert sweep.MINIMUM_REMAINING_SECONDS == 12 * 331 + 900 + 600 == 5472
    assert sweep.RUN_WINDOW_HOURS == 3                         # ceil((5472 + 3600) / 3600)
    assert sweep.CONCURRENCY == 2 * 10 * 15


def test_a_planted_descriptor_or_plan_edit_is_refused():
    descriptor = sweep.load_descriptor()
    planted = copy.deepcopy(descriptor)
    planted["timing"]["measurementSeconds"] = 120
    with pytest.raises(sweep.ProtocolError, match="differs from its generator"):
        sweep.validate_descriptor(planted)
    plan = sweep.compile_plan(descriptor)
    planted_plan = copy.deepcopy(plan)
    planted_plan["blocks"][0]["cells"][5]["timing"]["offered"] += 1
    with pytest.raises(sweep.ProtocolError, match="differs from the frozen schedule"):
        sweep.validate_plan(descriptor, planted_plan)
    try:
        sweep.METRIC_EXPORT_INTERVAL_MILLISECONDS = 10000
        with pytest.raises(sweep.ProtocolError, match="emission change"):
            sweep.allocate_schedule()
    finally:
        sweep.METRIC_EXPORT_INTERVAL_MILLISECONDS = None


def test_the_route_is_one_frontend_backend_path_and_keeps_flagd_off():
    upstream = ROOT / "upstream/opentelemetry-demo"
    handler = (upstream / "src/frontend/pages/api/products/[productId]/index.ts").read_text()
    assert "ProductCatalogService.getProduct(productId as string, currencyCode as string)" in handler
    service = (upstream / "src/frontend/services/ProductCatalog.service.ts").read_text()
    assert "!!currencyCode && currencyCode !== defaultCurrencyCode" in service
    catalog = (upstream / "src/productcatalogservice/main.go").read_text()
    assert 'if id != "OLJCESPC7Z" {\n\t\treturn false' in catalog
    products = json.loads((upstream / "src/productcatalogservice/products/products.json").read_text())["products"]
    assert sweep.ROUTE_PRODUCT_ID in [row["id"] for row in products] and sweep.ROUTE_PRODUCT_ID != "OLJCESPC7Z"
    # The route's services are inside the producer's correlation clip, so the clip cannot hide one of them.
    assert set(sweep.ROUTE_SERVICES) <= set(frozen_remote.TARGET_PATH)


# --------------------------------------------------------------------------- 2. the frozen epoch is unchanged
@pytest.mark.parametrize("relative", (
    "modules/otel-demo/execution/candidate_pilot.py",
    "pipelines/campaigns/otel-demo-offpath-v1.json",
    "pipelines/campaigns/otel-demo-candidate-pilot-v1.json",
    "pipelines/campaigns/otel-demo-candidate-pilot-v2.json",
    "pipelines/campaigns/otel-demo-candidate-pilot-v3.json",
    "modules/otel-demo/postures/catalog.json",
    "modules/otel-demo/execution/candidate-target-allocation.json",
    "modules/otel-demo/deployment/compose.otel-placement.yml",
    "modules/otel-demo/deployment/compose.candidate-postures.yml",
    "modules/otel-demo/workload.py",
))
# materialize.py is not in this list since 2026-10-09 (campaign B, decision 66: the repeat epoch's collector config turns
# the collector log sampler off).  Its output for the frozen, sweep and quiet epochs is pinned instead, byte for byte
# against the materializer at the base commit, by tests/test_otel_repeat_episodes.py.
def test_frozen_epoch_files_are_byte_identical_to_the_base_commit(relative):
    assert (ROOT / relative).read_bytes() == _git_show(relative)


def test_frozen_epoch_digests_and_runtime_shape_are_unchanged_without_a_selector():
    assert not (MODULE / "execution/study-epoch.json").exists(), "the selector is the activation step; it is not committed here"
    document = frozen_pilot.load_descriptor()
    assert frozen_pilot.canonical_sha256(document) == OFFPATH_DESCRIPTOR_SHA256
    assert frozen_pilot.canonical_sha256(frozen_pilot.compile_plan(document, 1)) == OFFPATH_PLAN_A1_SHA256
    assert frozen_runtime.STUDY_EPOCH == frozen_runtime.FROZEN_STUDY_EPOCH == OFFPATH
    assert frozen_runtime.is_sweep_epoch() is False
    assert frozen_runtime.RUN_COUNT == 36 and frozen_runtime.MINIMUM_REMAINING_SECONDS == 36_000
    assert frozen_runtime.RUN_WINDOW_HOURS == 11
    assert set(frozen_runtime.CONTROLLER_PATHS) == FROZEN_CONTROLLER_KEYS
    assert frozen_runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_pilot.py"
    assert frozen_runtime.DESCRIPTOR == ROOT / "pipelines/campaigns/otel-demo-offpath-v1.json"
    assert frozen_setup.controller_paths(OFFPATH) == frozen_setup.FIXED_CONTROLLER_PATHS == frozen_runtime.CONTROLLER_PATHS
    # The tombstone names only the current epoch: activating the sweep is the governed tuple edit.
    assert frozen_setup.ADMITTED_STUDY_EPOCHS == frozen_remote.ADMITTED_STUDY_EPOCHS == (OFFPATH,)
    # The remote controller's frozen literals stand for an untimed package.
    assert frozen_remote.RUN_COUNT == 36 and frozen_remote.EXPECTED_MINIMUM_REMAINING_SECONDS == 36_000


def _strip_dispatch(function: ast.FunctionDef) -> ast.FunctionDef:
    """The function with its inserted `if is_timed(...)` / `if "timing" in ...` dispatch statement removed."""
    def is_dispatch(node: ast.stmt) -> bool:
        if not isinstance(node, ast.If):
            return False
        text = ast.unparse(node.test)
        return text.startswith("is_timed(") or text.startswith("'timing' in ")
    function = copy.deepcopy(function)
    function.body = [node for node in function.body if not is_dispatch(node)]
    return function


def _function(source: str, name: str) -> ast.FunctionDef:
    return next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name)


@pytest.mark.parametrize("relative,name", (
    ("modules/otel-demo/execution/candidate_remote.py", "run_cell"),
    ("modules/otel-demo/execution/candidate_remote.py", "inject_fault"),
    ("modules/otel-demo/execution/candidate_remote.py", "run_workload"),
    ("modules/otel-demo/execution/candidate_remote.py", "wait_ready"),
    ("modules/otel-demo/execution/candidate_remote.py", "workload_path_check"),
    ("modules/otel-demo/validation/candidate_terminal.py", "validate_cell"),
    ("modules/otel-demo/validation/candidate_terminal.py", "validate_lattice"),
    ("modules/otel-demo/validation/candidate_terminal.py", "_validate_intervention"),
    ("modules/otel-demo/validation/candidate_terminal.py", "_validate_workload_identity"),
    ("modules/otel-demo/execution/candidate_runtime.py", "build_cell_contract"),
    ("modules/otel-demo/execution/candidate_runtime.py", "operational_binding"),
    ("modules/otel-demo/execution/candidate_runtime.py", "run_binding"),
    ("modules/otel-demo/execution/candidate_runtime.py", "execution_package"),
))
def test_frozen_code_paths_are_ast_identical_apart_from_the_timed_dispatch(relative, name):
    """The frozen epoch's cell runner, fault worker, workload and validators execute the base commit's code: the
    only difference is the inserted dispatch to the timed branch, which an untimed contract never takes."""
    base = _strip_dispatch(_function(_git_show(relative).decode(), name))
    now = _strip_dispatch(_function((ROOT / relative).read_text(), name))
    assert ast.dump(now) == ast.dump(base)


@pytest.fixture(scope="module")
def base_tree(tmp_path_factory):
    """The base commit's module tree (git archive), so frozen outputs can be compared with the base code's."""
    root = tmp_path_factory.mktemp("base-tree")
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", BASE_COMMIT, "modules/otel-demo", "pipelines/campaigns"],
        capture_output=True, check=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(root)], input=archive, check=True)
    (root / "upstream").mkdir()
    (root / "upstream/opentelemetry-demo").symlink_to(ROOT / "upstream/opentelemetry-demo")
    module = root / "modules/otel-demo"
    return types.SimpleNamespace(
        root=root,
        runtime=load("otel_sweep_base_runtime", module / "execution/candidate_runtime.py"),
        pilot=load("otel_sweep_base_pilot", module / "execution/candidate_pilot.py"),
        remote=load("otel_sweep_base_remote", module / "execution/candidate_remote.py"),
    )


def _normalised_package(runtime, package) -> dict:
    """The execution package with every controller digest masked: the controller FILES changed by design (that is
    what forces a new GATE-PLAN), so only the structure and values derived from the plan are compared."""
    document = copy.deepcopy(runtime.execution_package(package))
    for holder in [document, *document["cells"]]:
        for key in ("controllerDigests", "installedControllerDigests"):
            if key in holder:
                holder[key] = sorted(holder[key])
        # The gate documents embed those digests, so their own digests move with them.
        for key in ("gatePlanSha256", "gateSetupSha256", "setupReceiptSha256", "runtimeReadinessSha256", "gateRunSha256"):
            if key in holder:
                holder[key] = "masked"
    return document


def test_frozen_execution_package_and_posture_proof_equal_the_base_codes(base_tree, tmp_path, monkeypatch):
    new = _package(frozen_runtime, frozen_pilot, tmp_path / "new", window_hours=11)
    old = _package(base_tree.runtime, base_tree.pilot, tmp_path / "old", window_hours=11)
    assert new.gate_plan_sha256 != old.gate_plan_sha256           # controller digests moved, so the plan is new
    assert _normalised_package(frozen_runtime, new) == _normalised_package(base_tree.runtime, old)
    assert new.bindings.run_ids == old.bindings.run_ids and len(new.bindings.run_ids) == 36
    document_new = frozen_runtime.execution_package(new)
    document_old = base_tree.runtime.execution_package(old)
    monkeypatch.setattr(frozen_remote, "ADMITTED_STUDY_EPOCHS", (OFFPATH,))
    monkeypatch.setattr(base_tree.remote, "ADMITTED_STUDY_EPOCHS", (OFFPATH,))
    assert frozen_remote.validate_package(document_new, clock=lambda: NOW)[0] == document_new["cells"]
    assert base_tree.remote.validate_package(document_old, clock=lambda: NOW)[0] == document_old["cells"]
    assert frozen_remote.require_path_check_before_faults(document_new["cells"]) == \
        base_tree.remote.require_path_check_before_faults(document_old["cells"])
    # The posture proof of a frozen full cell, from the same fake target, is identical under both controllers.
    contract = copy.deepcopy(next(c for c in document_new["cells"] if c["posture"]["id"] == "full"))
    source = tmp_path / "source"
    source.mkdir()
    (source / "candidate-posture-contract.json").write_bytes((MODULE / "postures/catalog.json").read_bytes())
    contract["remoteSourceRoot"] = str(source)
    target = FakeTarget(contract, FakeTime(real_time.time()))
    for module in (frozen_remote, base_tree.remote):
        monkeypatch.setattr(module, "command", target.command)
        monkeypatch.setattr(module, "container_id", lambda cell, service, environment: f"cid-{service}")
    collector = "otelcol-1  |      -> service.name: Str(frontend)\n"
    proofs = [module.posture_proof(contract, {}, collector, "c" * 64) for module in (frozen_remote, base_tree.remote)]
    assert proofs[0] == proofs[1] and "notStartedServices" not in proofs[0]


# ------------------------------------------------------------------------------- 3. the selector activates it
def test_the_selector_activates_the_sweep_in_every_reader(tree):
    runtime = tree.runtime
    assert runtime.STUDY_EPOCH == SWEEP and runtime.is_sweep_epoch() is True
    assert runtime.RUN_COUNT == 12 and runtime.MINIMUM_REMAINING_SECONDS == 5472 and runtime.RUN_WINDOW_HOURS == 3
    assert set(runtime.CONTROLLER_PATHS) == FROZEN_CONTROLLER_KEYS | SWEEP_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_sweep.py"
    assert runtime.DESCRIPTOR == tree.root / "pipelines/campaigns/otel-traffic-sweep-v1.json"
    # The target's installer binds exactly the runtime's controller set for this epoch (both directions).
    assert tree.setup.controller_paths(SWEEP) == runtime.CONTROLLER_PATHS
    assert tree.setup.EPOCH_CONTROLLER_PATHS[SWEEP] == runtime.EPOCH_CONTROLLER_PATHS[SWEEP]
    digests = runtime.controller_digests()
    assert digests["protocol-gates"] == hashlib.sha256((MODULE / "validation/protocol_gates.py").read_bytes()).hexdigest()
    # The frozen tables stay readable under the selector: the v1 ledger and the offpath readiness fixture.
    assert runtime.unsupported_evidence()["studyEpoch"] == "otel-demo-candidate-pilot-v1"
    assert runtime.unsupported_postures() == []


@pytest.mark.parametrize("selector,message", (
    ({"schemaVersion": 1, "studyEpoch": "otel-demo-offpath-v2"}, "names no declared non-frozen epoch"),
    ({"schemaVersion": 1, "studyEpoch": SWEEP, "extra": True}, "names no declared non-frozen epoch"),
    ({"schemaVersion": True, "studyEpoch": SWEEP}, "names no declared non-frozen epoch"),
))
def test_a_selector_naming_anything_else_refuses_to_load(tmp_path, selector, message):
    root = _copy_tree(tmp_path, selector=json.dumps(selector))
    with pytest.raises(Exception, match=message):
        load(f"otel_sweep_bad_selector_{abs(hash(json.dumps(selector)))}", root / "modules/otel-demo/execution/candidate_runtime.py")


def test_driver_config_and_adapter_follow_the_selector_of_the_tree_they_read(tree, tmp_path):
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    real = load("otel_sweep_driver_config_real", MODULE / "drivers/gate_driver_config.py")
    selector = MODULE / "execution/study-epoch.json"
    # 2026-10-04: the real tree's selector may name the quiet calibration epoch (its own tests pin it); the drivers
    # follow whichever epoch it names.
    windows = {SWEEP: 3, "otel-quiet-calibration-v1": 6, "otel-repeat-episodes-v1": 5, "otel-repeat-episodes-c-v1": 5,
               "otel-load-pilot-v1": 3, "otel-offpath-pilot-v1": 4,
               "otel-offpath-pilot-v2": 3, "otel-offpath-e-v1": 5, "otel-offpath-f-v1": 5}
    selected = json.loads(selector.read_text())["studyEpoch"] if selector.exists() else None
    expected = (selected, selected, windows[selected]) if selected else (OFFPATH, OFFPATH, 11)
    assert (real.CONFIG.study, real.CONFIG.campaign_id, real.CONFIG.run_window_hours) == expected
    copied = load("otel_sweep_driver_config_tree", tree.root / "modules/otel-demo/drivers/gate_driver_config.py")
    assert (copied.CONFIG.study, copied.CONFIG.campaign_id, copied.CONFIG.run_window_hours) == (SWEEP, SWEEP, 3)
    assert copied.CONFIG.root == tree.root          # ROOT is the tree the drivers ship; never rebound here
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_sweep_tree_adapter", tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == SWEEP
        # Attempt 1 ran on fb14srv6 (stopped at cell 8): spent, so the driver path refuses it and takes attempt 2.
        assert adapter.pilot.EPOCH == SWEEP and set(adapter.SPENT_ATTEMPTS) == {1}
        with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
            adapter.inspect_campaign(tmp_path / "plan-a1", "a" * 40)
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "2")
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 12
        assert bindings.plan_sha256 == SWEEP_PLAN_A2_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


# ------------------------------------------------------------------- 4. the gate chain on the selected tree
SETUP_STARTED = NOW - timedelta(minutes=4)
SETUP_COMPLETED = NOW - timedelta(minutes=3)
READINESS_NOW = NOW - timedelta(minutes=2)


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gate_documents(runtime, bindings, *, window_hours: float):
    """GATE-PLAN, GATE-SETUP, setup receipt, readiness and GATE-RUN for `bindings`, as the drivers derive them
    (the same construction as tests/test_otel_candidate_runtime.py, parameterised by the runtime module)."""
    binding = runtime.operational_binding(
        bindings, framework_commit="a" * 40, campaign_id=runtime.STUDY_EPOCH,
        repository_bundle_sha256="b" * 64, upstream_bundle_sha256="c" * 64,
        expected_materialized_source_sha256="d" * 64,
    )
    plan = {
        "schemaVersion": 1, "kind": runtime.PLAN_KIND, "gate": "GATE-PLAN", "decision": "approve-exact-plan",
        "typedApproval": runtime.expected_gate_plan_text(binding), "approvedBy": "auto-derived",
        "approvedAt": _iso(NOW - timedelta(hours=1)), "binding": binding,
        "runtimeAuthorized": False, "promotionAuthorized": False,
    }
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    setup_binding = runtime.setup_binding(checked, plan_sha)
    gate_setup = {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-one-shot-exact-setup", "typedApproval": runtime.expected_gate_setup_text(setup_binding),
        "approvedBy": "auto-derived", "approvedAt": _iso(NOW - timedelta(minutes=5)), "binding": setup_binding,
        "runtimeAuthorized": False, "promotionAuthorized": False,
    }
    setup_sha = runtime.validate_gate_setup(gate_setup, checked, plan_sha, now=NOW)
    images = {service: "sha256:" + hashlib.sha256(service.encode()).hexdigest() for service in runtime.posture_catalog()["applicationServices"]}
    inventory = {"composeProjects": [], "runningContainers": [], "volumes": []}
    receipt = {
        "schemaVersion": 1, "kind": "otel-demo-candidate-setup-receipt-v1", "campaignId": binding["campaignId"],
        "target": {"host": "fb14srv6", "transportUser": "root", "setupUser": "root"},
        "executionIdentity": copy.deepcopy(binding["target"]["executionIdentity"]),
        "frameworkCommit": binding["frameworkCommit"], "upstreamCommit": binding["upstreamCommit"],
        "gatePlanSha256": plan_sha, "gateSetupSha256": setup_sha,
        "targetContractSha256": binding["targetContractSha256"],
        "repositoryBundleSha256": binding["repositoryBundleSha256"],
        "upstreamBundleSha256": binding["upstreamBundleSha256"],
        "releaseRoot": binding["releaseRoot"], "repositoryRoot": binding["repositoryRoot"],
        "remoteSourceRoot": binding["remoteSourceRoot"], "remoteArtifactRoot": binding["remoteArtifactRoot"],
        "leasePath": binding["exclusiveLeasePath"], "composeProject": binding["compose"]["project"],
        "ports": copy.deepcopy(binding["compose"]["ports"]),
        "materializedSourceSha256": binding["expectedMaterializedSourceSha256"],
        "imageIds": images, "installedControllerDigests": copy.deepcopy(binding["controllerDigests"]),
        "dockerVersion": "29.6.1", "dockerGid": 998,
        "foreignInventoryBefore": copy.deepcopy(inventory), "foreignInventoryAfter": copy.deepcopy(inventory),
        "foreignVolumesPreserved": True, "activeForeignResourcesAbsent": True,
        "containersStarted": False, "cellsRun": 0, "runtimeAuthorized": False, "promotionAuthorized": False,
        "startedAt": _iso(SETUP_STARTED), "completedAt": _iso(SETUP_COMPLETED),
    }
    checked_receipt, receipt_sha = runtime.validate_setup_receipt(receipt, checked, plan_sha, setup_sha)
    observations = {
        "target-contract-projection": {
            "targetContractSha256": binding["targetContractSha256"],
            "projection": copy.deepcopy(binding["targetContractProjection"]),
        },
        "target-identity": {
            "host": "fb14srv6", "transportUser": "root", "setupUser": "root", "executionUser": "stig",
            "uid": 1016, "gid": 1016, "supplementalGids": [998], "architecture": "x86_64", "kernel": "Linux 6.8",
            "observedAt": _iso(READINESS_NOW),
        },
        "target-root-and-host-isolation": {
            "target": copy.deepcopy(binding["target"]), "releaseRoot": binding["releaseRoot"],
            "repositoryRoot": binding["repositoryRoot"], "remoteSourceRoot": binding["remoteSourceRoot"],
            "sourceRootOwner": "root", "sourceRootWritableByExecutionUser": False, "sourceRootIsSymlink": False,
            "remoteArtifactParent": "/home/stig/observability-placement-candidate-v4-runs",
            "artifactParentOwner": "root", "artifactParentTraversableByExecutionUser": True,
            "remoteArtifactRoot": binding["remoteArtifactRoot"], "artifactRootOwner": "stig",
            "artifactRootWritableByExecutionUser": True, "exclusiveLeasePath": binding["exclusiveLeasePath"],
            "leaseOwner": "root", "leaseGroup": 1016, "leaseMode": "0660", "observedAt": _iso(READINESS_NOW),
        },
        "toolchain-pins": {
            "dockerVersion": "29.6.1", "composeVersion": "5.3.1", "pythonVersion": "3.9.2",
            "tcpdumpVersion": "4.99.0", "tsharkVersion": "3.4.16", "tcpdumpNonInteractive": True,
            "availableCommands": ["docker", "flock", "python3", "runuser", "sha256sum", "sudo", "systemctl",
                                  "systemd-run", "tcpdump", "tshark"],
        },
        "source-image-bindings": {
            "upstreamCommit": binding["upstreamCommit"], "materializedSourceSha256": receipt["materializedSourceSha256"],
            "imageIds": copy.deepcopy(images), "controllerDigests": copy.deepcopy(binding["controllerDigests"]),
        },
        "installed-release-bindings": {
            "frameworkCommit": binding["frameworkCommit"], "releaseRoot": binding["releaseRoot"],
            "repositoryRoot": binding["repositoryRoot"], "remoteSourceRoot": binding["remoteSourceRoot"],
            "installedControllerDigests": copy.deepcopy(binding["controllerDigests"]),
            "sourceTreeImmutable": True, "sourceTreeSymlinks": [], "setupReceiptSha256": receipt_sha,
        },
        "foreign-inventory-preservation": {
            "runningContainers": [], "activeComposeProjects": [], "exitedComposeProjectsBefore": [],
            "exitedComposeProjectsAfter": [], "foreignVolumesBefore": [], "foreignVolumesAfter": [],
            "deletedForeignResources": [],
        },
        "project-port-lease-isolation": {
            "composeProject": binding["compose"]["project"], "ports": copy.deepcopy(binding["compose"]["ports"]),
            "preexistingResources": {"containers": [], "networks": [], "volumes": []}, "occupiedPorts": [],
            "leaseAvailable": True, "controllerRootPresent": True, "candidateResultEntries": [],
        },
    }
    observations.update(runtime.harness_contract_observations(binding))
    readiness = runtime.make_readiness(
        checked, plan_sha, setup_sha, checked_receipt, receipt_sha, observations, observed_at=_iso(READINESS_NOW),
    )
    readiness_sha = runtime.canonical_sha256(readiness)
    run_binding = runtime.run_binding(
        checked, plan_sha, readiness, readiness_sha,
        not_before=_iso(NOW - timedelta(minutes=1)), authorization_deadline=_iso(NOW + timedelta(hours=window_hours)),
    )
    gate_run = {
        "schemaVersion": 1, "kind": runtime.RUN_KIND, "gate": "GATE-RUN",
        "decision": "authorize-one-shot-exact-run", "typedApproval": runtime.expected_gate_run_text(run_binding),
        "approvedBy": "auto-derived", "approvedAt": _iso(NOW - timedelta(minutes=1)), "binding": run_binding,
        "promotionAuthorized": False,
    }
    return plan, gate_setup, receipt, readiness, gate_run


def _package(runtime, compiler, tmp_path: Path, *, window_hours: float):
    compiled = tmp_path / "compiled"
    compiler.materialize(compiled, attempt=1)
    bindings = runtime.inspect_compiled_plan(compiled)
    documents = _gate_documents(runtime, bindings, window_hours=window_hours)
    paths = []
    for name, value in zip(("plan.json", "setup.json", "setup-receipt.json", "readiness.json", "run.json"), documents):
        _write(tmp_path / name, value)
        paths.append(tmp_path / name)
    return runtime.authorize_from_files(compiled, *paths, clock=lambda: NOW)


@pytest.fixture(scope="module")
def sweep_package(tree, tmp_path_factory):
    return _package(tree.runtime, tree.compiler, tmp_path_factory.mktemp("sweep-package"), window_hours=3)


def test_gate_chain_derives_the_sweep_population_budget_and_sentences(tree, sweep_package, tmp_path):
    runtime, remote = tree.runtime, tree.remote
    plan_text = sweep_package.gate_plan["typedApproval"]
    assert f"study={SWEEP} " in plan_text and " runs=12 " in plan_text and f"campaign={SWEEP} " in plan_text
    assert " runs=12 " in sweep_package.gate_run["typedApproval"]
    assert sweep_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 5472
    binding = sweep_package.gate_plan["binding"]
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_traffic_sweep_v1"
    assert binding["remoteArtifactRoot"].endswith("/" + SWEEP)
    assert set(binding["controllerDigests"]) == FROZEN_CONTROLLER_KEYS | SWEEP_CONTROLLER_KEYS
    document = runtime.execution_package(sweep_package)
    assert document["runCount"] == 12 and len(document["cells"]) == 12
    plan_cells = sweep_package.bindings.cells
    for contract, cell in zip(document["cells"], plan_cells):
        assert contract["timing"] == cell["timing"] and contract["runId"] == cell["runId"]
        assert contract["workload"]["requestsPerSecond"] == cell["timing"]["requestsPerSecond"]
        assert contract["workload"]["offeredRequests"] == cell["timing"]["offered"]
        assert contract["workloadPathCheck"]["gatesCampaign"] is False
        assert runtime.sweep_cell_timing(contract) == cell["timing"]
    lead = document["cells"][0]
    assert (lead["runKey"]["regime"], lead["runKey"]["requestsPerSecond"]) == ("frontend-pause-effect", 10.0)
    assert lead["fault"] == {
        "scenario": "frontend-pause", "service": "frontend", "action": "pause",
        "entryRouteDuringFault": "must-be-unavailable", "nanoCpus": None,
        "onsetSeconds": lead["timing"]["faultOnsetSeconds"], "holdSeconds": 60,
        "manifestationAndRecoveryRequired": True,
    }
    throttle = next(c for c in document["cells"] if c["runKey"]["regime"] == "productcatalog-cpu-throttle-effect")
    assert throttle["fault"]["service"] == "productcatalogservice" and throttle["fault"]["nanoCpus"] == 100_000_000
    if SWEEP not in remote.ADMITTED_STUDY_EPOCHS:
        # Not admitted yet: the activation edit must name the sweep in the tombstone, or nothing reaches the target.
        with pytest.raises(runtime.GateError, match="not admitted by the installed target controllers"):
            runtime.refuse_unsupported("probe")
        with pytest.raises(remote.RuntimeFailure, match="UNSUPPORTED"):
            remote.refuse_unsupported("probe", SWEEP)
        with pytest.raises(remote.RuntimeFailure, match="unknown study epoch"):
            remote.validate_package(document, clock=lambda: NOW)
    else:
        # The activation edit is in this tree: the tombstone names the sweep and only the sweep.
        assert remote.ADMITTED_STUDY_EPOCHS == tree.setup.ADMITTED_STUDY_EPOCHS == (SWEEP,)
        runtime.refuse_unsupported("probe")
    # After the activation edit the target controller accepts the package and derives the same population and
    # budget from it.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (SWEEP,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
        remote.refuse_unsupported("probe", SWEEP)
    assert len(cells) == 12 and remote.expected_run_count(document) == 12
    assert remote.expected_minimum_remaining(document) == 5472
    assert remote.require_path_check_before_faults(cells) == -1


def test_gate_run_window_and_planted_package_defects_fail_closed(tree, sweep_package, tmp_path):
    runtime, remote = tree.runtime, tree.remote
    with pytest.raises(runtime.GateError, match="too little time for 12 cells"):
        _package(runtime, tree.compiler, tmp_path / "short", window_hours=1)
    document = runtime.execution_package(sweep_package)
    monkeypatch_admit = pytest.MonkeyPatch()
    monkeypatch_admit.setattr(remote, "ADMITTED_STUDY_EPOCHS", (SWEEP,))
    planted = copy.deepcopy(document)
    planted["cells"][4]["timing"]["planRunCount"] = 13
    with pytest.raises(remote.RuntimeFailure, match="disagree on planRunCount"):
        remote.validate_package(planted, clock=lambda: NOW)
    planted = copy.deepcopy(document)
    planted["minimumRemainingAtFirstMutationSeconds"] = 36_000
    with pytest.raises(remote.RuntimeFailure, match="identity or authority differs"):
        remote.validate_package(planted, clock=lambda: NOW)
    planted = copy.deepcopy(document)
    planted["cells"][2]["workloadPathCheck"]["gatesCampaign"] = True
    with pytest.raises(remote.RuntimeFailure, match="names a workload path check cell"):
        remote.require_path_check_before_faults(planted["cells"])
    # A frozen-epoch package may not smuggle a timed cell.
    planted = copy.deepcopy(document)
    planted["studyEpoch"] = OFFPATH
    with pytest.raises(remote.RuntimeFailure, match="frozen-epoch package carries timed cells"):
        remote.expected_run_count(planted)
    # A retained contract cannot bring its own numbers.
    contract = copy.deepcopy(document["cells"][1])
    contract["timing"]["faultOnsetSeconds"] += 1.0
    with pytest.raises(runtime.GateError, match="not the active compiled plan's timing"):
        runtime.sweep_cell_timing(contract)
    # A runtime without the selector refuses a timed contract outright.
    if not frozen_runtime.is_sweep_epoch():
        with pytest.raises(frozen_runtime.GateError, match="needs the epoch selector"):
            frozen_runtime.sweep_cell_timing(document["cells"][0])
    monkeypatch_admit.undo()


# ----------------------------------------------- 5. a fake-driven execution of the target's per-cell runner
# 30x: one real millisecond of thread wake-up jitter is 0.03 simulated seconds against F1's 1 s onset tolerance.
SCALE = 30.0
# Simulated seconds a fault command takes: longer than F1's 1 s onset tolerance, so an onset stamped after the
# command (F-ADH-085) fails F1 instead of passing unnoticed.
COMMAND_SECONDS = 1.5


class FakeTime:
    """Compressed wall and monotonic clocks: one real second is SCALE simulated seconds."""

    def __init__(self, epoch0: float) -> None:
        self.real0 = real_time.monotonic()
        self.epoch0 = epoch0

    def _elapsed(self) -> float:
        return (real_time.monotonic() - self.real0) * SCALE

    def monotonic(self) -> float:
        return 5000.0 + self._elapsed()

    def time(self) -> float:
        return self.epoch0 + self._elapsed()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            real_time.sleep(seconds / SCALE)


class FakeTarget:
    """A fake fb14srv6: the Docker/Compose CLI, the route through Envoy, and the collector and proxy logs."""

    def __init__(self, contract, clock: FakeTime, *, fail_first_request: bool = False, generator_container: bool = False,
                 drop_traces=(), lose_spans=(), oom_killed=(), restarted=()):
        self.contract = contract
        self.clock = clock
        self.lock = threading.Lock()
        self.frontend_running = threading.Event()
        self.frontend_running.set()
        self.nanocpus = {}
        # Upstream's compose limit and the daemon's default swap (twice the limit); other services unlimited.
        self.memory = {"frontendproxy": [50 * 1024 * 1024, 100 * 1024 * 1024]}
        self.oom_killed, self.restarted = set(oom_killed), set(restarted)   # planted, after the window
        self.oom_flags, self.restart_counts = set(), {}
        self.served = []          # (token, traceparent, ok, epoch)
        self.commands = []
        self.first_epoch = None
        self.fail_first_request = fail_first_request
        self.generator_container = generator_container
        self.drop_traces = set(drop_traces)     # request tokens whose spans below the proxy never reach the collector
        # 2026-10-04: request tokens whose productcatalogservice span alone never reaches the collector (the quiet run's
        # attempt-1 pattern, main repo research/traffic-sweep/STOP_QUIET_OTEL_A1.md: one lost batch of one service).
        self.lose_spans = set(lose_spans)
        self.stats = 0
        self.catalog = json.loads((MODULE / "postures/catalog.json").read_text())

    # -- HTTP ------------------------------------------------------------------------------------------------
    def http_get(self, url, headers, timeout):
        token = headers.get("x-obsplacement-request-token")
        if not self.frontend_running.is_set():
            if not self.frontend_running.wait(timeout / SCALE):
                self._serve(token, headers.get("traceparent"), False)
                return None, 0, "TimeoutError: timed out"
        with self.lock:
            fail = self.fail_first_request and token == self.contract["_firstToken"]
        self._serve(token, headers.get("traceparent"), not fail)
        return (500, 0, "HTTPError: HTTP Error 500: Internal Server Error") if fail else (200, 512, None)

    def post_json(self, url, body, headers, timeout):
        now = self.clock.time()
        return {"status": 200, "bytes": 10, "startedAtEpoch": now, "endedAtEpoch": now, "error": None}

    def _serve(self, token, traceparent, ok):
        with self.lock:
            self.served.append((token, traceparent, ok, self.clock.time()))

    # -- logs ------------------------------------------------------------------------------------------------
    # Every container log carries one stray non-UTF-8 byte (0xbf), the byte that aborted Hotel's sweep1 attempt 2:
    # the runner must retain logs as bytes and parse them with replacement.
    STRAY = "\udcbf"

    def collector_log(self) -> str:
        stamp = datetime.fromtimestamp(self.first_epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        lines = [f"otelcol-1  | Timestamp: {stamp}.123456789 +0000 UTC", f"otelcol-1  | Body: Str(stray {self.STRAY} byte)"]
        for token, traceparent, ok, _ in self.served:
            if not traceparent:
                continue
            trace = traceparent.split("-")[1]
            full = ok and token not in self.drop_traces
            for name in (("frontend-proxy", "frontend", "productcatalogservice") if full else ("frontend-proxy",)):
                if token in self.lose_spans and name == "productcatalogservice":
                    continue
                lines.append(f"otelcol-1  |      -> service.name: Str({name})")
                lines.append(f"otelcol-1  |     Trace ID       : {trace}")
        return "\n".join(lines) + "\n"

    def proxy_log(self) -> str:
        lines = [f"frontendproxy-1  | [warning] stray {self.STRAY} byte"]
        for token, traceparent, _, _ in self.served:
            row = {"obsplacement_kind": "application-request-witness", "request_token": token}
            if traceparent:
                parts = traceparent.split("-")
                row["traceparent"] = f"{parts[0]}-{parts[1]}-{'a' * 16}-{parts[3]}"
            lines.append("frontendproxy-1  | " + json.dumps(row))
        return "\n".join(lines) + "\n"

    def application_log(self) -> str:
        return "".join(
            f"{service}-1  | 2026-10-03T06:00:0{index % 10}.123456789Z started {self.STRAY}\n"
            for index, service in enumerate(("frontend", "frontendproxy", "productcatalogservice"))
        )

    # -- Docker ----------------------------------------------------------------------------------------------
    def _inspect(self, service):
        env = [f"{k}={v}" for k, v in self.contract["posture"]["environment"].items()]
        env += ["OTEL_SDK_DISABLED=false", "OTEL_TRACES_EXPORTER=otlp", "OTEL_PLACEMENT_ENABLED=true"]
        probe = self.catalog["serviceInstrumentation"].get(service, {}).get("runtimeProbe")   # otelcol: none
        if probe and probe["kind"] == "container-env" and probe["variable"] != "OTEL_PLACEMENT_ENABLED":
            env.append(f"{probe['variable']}={probe.get('loadedWhenEquals') or 'x' + probe['loadedWhenContains'] + 'y'}")
        paused = service == "frontend" and not self.frontend_running.is_set()
        memory, swap = self.memory.get(service, [0, 0])
        return [{
            "Id": f"cid-{service}",
            "Image": self.contract["imageIds"].get(service, "sha256:" + "0" * 64),
            "State": {"Running": True, "Paused": paused, "Status": "paused" if paused else "running",
                      "OOMKilled": service in self.oom_flags},
            "RestartCount": self.restart_counts.get(service, 0),
            "Config": {"Env": env, "Entrypoint": None, "Cmd": None,
                       "Labels": {"com.docker.compose.service": service}},
            "HostConfig": {"NanoCpus": self.nanocpus.get(service, 0), "Memory": memory, "MemorySwap": swap},
        }]

    def started_services(self):
        return [service for service in self.catalog["applicationServices"] if service != "loadgenerator"] + ["otelcol"]

    def command(self, argv, *, cwd=None, env=None, check=True, timeout=None, binary=False):
        argv = [str(item) for item in argv]
        self.commands.append(argv)
        out = ""
        if argv[:2] == ["docker", "compose"]:
            tail = argv[10:]          # docker compose -p P -f base -f placement -f postures <arguments>
            assert argv[2] == "-p" and argv[9].endswith("compose.candidate-postures.yml"), argv
            verb = tail[0]
            if verb == "config":
                out = json.dumps({"services": {s: {"image": f"img-{s}"} for s in self.contract["imageIds"]}})
            elif verb == "up":
                self.first_epoch = self.clock.time()
            elif verb == "rm":
                assert tail == ["rm", "--stop", "--force", "loadgenerator"], tail
            elif verb == "ps":
                out = f"cid-{tail[-1]}\n"
            elif verb == "pause":
                self.clock.sleep(COMMAND_SECONDS)      # the Compose CLI takes time: a post-command stamp is late
                self.frontend_running.clear()
            elif verb == "unpause":
                self.clock.sleep(COMMAND_SECONDS)
                self.frontend_running.set()
            elif verb == "logs":
                if not self.oom_flags and not self.restart_counts:   # planted defects surface once, after the window
                    self.oom_flags |= self.oom_killed
                    for service in self.restarted:
                        self.restart_counts[service] = self.restart_counts.get(service, 0) + 1
                services = [item for item in tail[1:] if not item.startswith("--")]
                out = (self.collector_log() if services == ["otelcol"] else
                       self.proxy_log() if services == ["frontendproxy"] else self.application_log())
        elif argv[:3] == ["docker", "image", "inspect"]:
            out = self.contract["imageIds"][argv[-1].removeprefix("img-")] + "\n"
        elif argv[:2] == ["docker", "inspect"]:
            out = json.dumps([row for item in argv[2:] for row in self._inspect(item.removeprefix("cid-"))])
        elif argv[:2] == ["docker", "info"]:
            out = "24\n"
        elif argv[:2] == ["docker", "update"] and "--memory" in argv:
            service = argv[-1].removeprefix("cid-")
            swap = argv[argv.index("--memory-swap") + 1] if "--memory-swap" in argv else self.memory.get(service, [0, 0])[1]
            self.memory[service] = [int(argv[argv.index("--memory") + 1]), int(swap)]
        elif argv[:2] == ["docker", "update"]:
            self.clock.sleep(COMMAND_SECONDS)
            cpus = argv[argv.index("--cpus") + 1]
            whole, _, fraction = cpus.partition(".")
            self.nanocpus[argv[-1].removeprefix("cid-")] = int(whole) * 1_000_000_000 + int(fraction.ljust(9, "0"))
        elif argv[:2] == ["docker", "ps"] and "--no-trunc" in argv:
            project = self.contract["compose"]["project"]
            assert f"label=com.docker.compose.project={project}" in argv, argv
            out = "".join(f"cid-{service}\n" for service in self.started_services())
        elif argv[:2] == ["docker", "ps"] and "label=com.docker.compose.service=loadgenerator" in argv:
            out = "deadbeef\n" if self.generator_container else ""
        elif argv[:2] in (["docker", "ps"], ["docker", "network"], ["docker", "volume"]):
            out = ""
        elif argv[:2] == ["docker", "exec"]:
            service, path = argv[2].removeprefix("cid-"), argv[-1]
            probe = self.catalog["serviceInstrumentation"][service]["runtimeProbe"]
            value = probe.get("loadedWhenEquals") or probe.get("loadedWhenContains")
            out = f"{probe['variable']}={value}\0" if path == "/proc/1/environ" else value
        elif argv[:2] == ["docker", "top"]:
            probe = self.catalog["serviceInstrumentation"][argv[2].removeprefix("cid-")]["runtimeProbe"]
            out = f"PID ARGS\n1 prog {probe['loadedWhenContains']} main\n"
        elif argv[0] == "tshark":
            out = "100\n200\n"
        else:
            raise AssertionError(f"unexpected target command {argv}")
        raw = out.encode("utf-8", errors="surrogateescape")       # the stray byte is a real 0xbf on the wire
        if binary:
            return subprocess.CompletedProcess(argv, 0, raw, b"")
        # Text mode as subprocess.run(text=True) decodes it under a UTF-8 locale: strictly (the old wrapper).
        return subprocess.CompletedProcess(argv, 0, raw.decode("utf-8"), "")

    def docker_stats(self, container):
        with self.lock:
            self.stats += 1
            return {"cpu_stats": {"cpu_usage": {"total_usage": 1_000_000 * self.stats}}}


def _contract_for(tree, sweep_package, regime: str, rate: float, tmp_path: Path) -> dict:
    document = tree.runtime.execution_package(sweep_package)
    contract = copy.deepcopy(next(
        c for c in document["cells"] if (c["runKey"]["regime"], c["runKey"]["requestsPerSecond"]) == (regime, rate)
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


def _execute(tree, contract, monkeypatch, **fake_options):
    remote = tree.remote
    clock = FakeTime(real_time.time())
    target = FakeTarget(contract, clock, **fake_options)
    target.contract["_firstToken"] = remote.request_identity(contract["runId"], 0)[0]
    monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (SWEEP,))    # the activation edit
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
    receipt = remote.run_cell(contract, datetime.now(timezone.utc) + timedelta(hours=3))
    return receipt, target


@pytest.mark.parametrize("regime,rate", (
    ("frontend-pause-effect", 10.0),
    ("frontend-pause-effect", 0.05),
    ("productcatalog-cpu-throttle-effect", 10.0),
    ("productcatalog-cpu-throttle-effect", 0.05),
    ("no-fault-calibration", 0.2),
))
def test_run_cell_executes_a_sweep_cell_from_its_timing_and_the_terminal_accepts_it(
    tree, sweep_package, tmp_path, monkeypatch, regime, rate,
):
    contract = _contract_for(tree, sweep_package, regime, rate, tmp_path)
    receipt, target = _execute(tree, contract, monkeypatch)
    root = Path(contract["remoteArtifactRoot"])
    assert receipt["state"] == "valid", receipt["error"]
    timing = contract["timing"]
    compose_verbs = [argv[10:] for argv in target.commands if argv[:2] == ["docker", "compose"]]
    up = compose_verbs.index(["up", "-d", "--no-build"])
    # The generator is removed right after `up` and before any readiness, warm-up or measured request.
    assert compose_verbs[up + 1] == ["rm", "--stop", "--force", "loadgenerator"]
    assert all("--scale" not in verb for verb in compose_verbs)
    assert any(argv[:2] == ["docker", "compose"] and "--timestamps" in argv for argv in target.commands)
    ledger = json.loads((root / "request-ledger.json").read_text())
    assert ledger["offered"] == timing["offered"] == len(ledger["requests"]) and ledger["ratePerSecond"] == rate
    assert ledger["durationSeconds"] == 180.0 and ledger["endedAtEpoch"] - ledger["startedAtEpoch"] >= 178
    gates = json.loads((root / "protocol-gates.json").read_text())
    assert gates["valid"] is True and gates["failedGates"] == []
    assert gates["blocking"] == (["F1", "G1", "G2", "G4"] if contract["fault"]["scenario"] else ["G1", "G2", "G4"])
    if contract["fault"]["scenario"]:
        intervention = json.loads((root / "intervention.json").read_text())
        onset = intervention["actualOnsetMonotonicOffsetSeconds"]
        assert timing["faultOnsetSeconds"] - 0.05 <= onset <= timing["faultOnsetSeconds"] + 1.0
        assert intervention["onsetSource"] == "pre-command" and intervention["probes"]
        assert {row["phase"] for row in intervention["probes"]} == {"during-fault", "post-revert"}
        if contract["fault"]["action"] == "pause":
            assert intervention["duringRouteAvailable"] is False
            assert any(argv[-2:] == ["pause", "frontend"] for argv in target.commands)
            assert any(argv[-2:] == ["unpause", "frontend"] for argv in target.commands)
        else:
            assert ["docker", "update", "--cpus", "0.100", "cid-productcatalogservice"] in target.commands
            assert ["docker", "update", "--cpus", "24.000", "cid-productcatalogservice"] in target.commands
            assert intervention["throttle"]["postNanoCpus"] == intervention["throttle"]["restoreNanoCpus"] == 24_000_000_000
    # The declared memory limit (compiled timing, not a literal) was applied right after up, and the guard passed.
    health = json.loads((root / "container-health.json").read_text())
    limit = timing["serviceMemoryLimitBytes"]["frontendproxy"]
    assert limit == 256 * 1024 * 1024 and health["valid"] is True
    assert health["memoryLimitUpdates"][0]["argv"] == [
        "docker", "update", "--memory", str(limit), "--memory-swap", str(2 * limit), "cid-frontendproxy"]
    assert {row["service"] for row in health["final"]} == set(target.started_services())
    # Logs are retained byte for byte, stray 0xbf included, and the terminal parses them with replacement.
    assert b"\xbf" in (root / "application.log").read_bytes() and b"\xbf" in (root / "otelcol.log").read_bytes()
    report = tree.terminal.validate_cell(root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    assert report["correlation"]["requiredPathServices"] == ["frontend", "frontendproxy", "productcatalogservice"]
    completeness = report["correlation"]["traceCompleteness"]
    assert completeness["incomplete"] == 0 and completeness["allowance"] >= 1
    assert completeness["successful"] == sum(
        completeness["windows"][name]["successful"] for name in completeness["blockingWindows"]
    ) > 0


# ------------------------ protocol decision 25 (user 2026-10-03): the shared trace-completeness rule, all sweeps
def _tokens(tree, contract, sequences):
    return {tree.remote.request_identity(contract["runId"], sequence)[0] for sequence in sequences}


def _completeness(contract):
    return json.loads((Path(contract["remoteArtifactRoot"]) / "trace-completeness.json").read_text())


def test_the_attempt1_incident_one_incomplete_trace_in_the_drain_after_a_pause_at_02_now_seals_valid(
    tree, sweep_package, tmp_path, monkeypatch,
):
    """OTel attempt 1 cell 8 (frontend-pause r0.2): 20/21 complete, the incomplete request started 9.8 s after the
    route was ready again.  Blocked under M1 (6380cce); recorded as the fault's effect now."""
    contract = _contract_for(tree, sweep_package, "frontend-pause-effect", 0.2, tmp_path)
    receipt, _ = _execute(tree, contract, monkeypatch, drop_traces=_tokens(tree, contract, [27]))   # scheduled 135 s
    record = _completeness(contract)
    assert receipt["state"] == "valid", receipt["error"]
    assert record["windows"]["fault-and-drain"]["incomplete"] == record["recordedFaultEffectIncomplete"] == 1
    assert set(record["windows"]["fault-and-drain"]["incompleteRequestTokens"]) == _tokens(tree, contract, [27])
    assert record["incomplete"] == 0 and record["valid"] is True
    window = record["faultAndDrainWindowSeconds"]
    assert window[1] - window[0] > 60 + record["drainSeconds"] - 1 and record["drainSeconds"] == 15.0 + 2.0
    report = tree.terminal.validate_cell(Path(contract["remoteArtifactRoot"]), contract)
    assert report["correlation"]["traceCompleteness"]["recordedFaultEffectIncomplete"] == 1


def test_incomplete_traces_in_the_fault_and_drain_window_never_block(tree, sweep_package, tmp_path, monkeypatch):
    contract = _contract_for(tree, sweep_package, "productcatalog-cpu-throttle-effect", 10.0, tmp_path)
    onset = contract["timing"]["faultOnsetSeconds"]
    inside = [sequence for sequence in range(1800) if onset + 1 <= sequence / 10.0 <= onset + 59][:300]
    receipt, _ = _execute(tree, contract, monkeypatch, drop_traces=_tokens(tree, contract, inside))
    record = _completeness(contract)
    assert receipt["state"] == "valid", receipt["error"]
    assert record["recordedFaultEffectIncomplete"] == 300 and record["incomplete"] == 0
    assert set(record["blockingWindows"]) == {"pre-onset", "after-drain"}


@pytest.mark.parametrize("dropped,valid", ((18, True), (19, False)))
def test_no_fault_cells_allow_exactly_max_1_or_1_percent_over_their_whole_window(
    tree, sweep_package, tmp_path, monkeypatch, dropped, valid,
):
    contract = _contract_for(tree, sweep_package, "no-fault-calibration", 10.0, tmp_path)
    receipt, _ = _execute(tree, contract, monkeypatch, drop_traces=_tokens(tree, contract, range(100, 100 + dropped)))
    record = _completeness(contract)
    assert list(record["windows"]) == ["whole-measurement"] and record["blockingWindows"] == ["whole-measurement"]
    assert (record["successful"], record["allowance"], record["incomplete"]) == (1800, 18, dropped)
    assert set(record["windows"]["whole-measurement"]["incompleteRequestTokens"]) == _tokens(
        tree, contract, range(100, 100 + dropped))
    assert (receipt["state"] == "valid") is valid
    if not valid:
        assert "19 incomplete of 1800 successful requests outside the fault-and-drain window exceeds the allowance 18" in receipt["error"]


def test_the_quiet_runs_lost_batch_still_blocks_a_sweep_no_fault_cell(tree, sweep_package, tmp_path, monkeypatch):
    """Protocol decision 56 (2026-10-04) changes the quiet calibration epoch only.  The quiet run's attempt-1 pattern
    (50 consecutive requests at 10/s, scheduled 134.9-139.8 s, each without its productcatalogservice span), which
    seals valid there now, still blocks a sweep cell under decision 25, with the decision-25 record."""
    contract = _contract_for(tree, sweep_package, "no-fault-calibration", 10.0, tmp_path)
    assert "traceCompletenessRule" not in contract["timing"] and contract["studyEpoch"] == SWEEP
    receipt, _ = _execute(tree, contract, monkeypatch, lose_spans=_tokens(tree, contract, range(1349, 1399)))
    record = _completeness(contract)
    assert receipt["state"] == "invalid"
    assert ("trace completeness: 50 incomplete of 1800 successful requests outside the fault-and-drain window "
            "exceeds the allowance 18") in receipt["error"]
    assert (record["schemaVersion"], record["kind"], record["rule"]) == (
        2, "otel-demo-sweep-trace-completeness-v2", "protocol-decision-25")
    assert (record["successful"], record["incomplete"], record["allowance"], record["valid"]) == (1800, 50, 18, False)
    assert set(record["windows"]["whole-measurement"]) == {
        "requests", "successful", "complete", "incomplete", "incompleteRequestTokens", "unsuccessful",
        "unsuccessfulIncomplete",
    }


@pytest.mark.parametrize("dropped,valid", ((1, True), (2, False)))
def test_at_005_per_second_the_allowance_is_one_incomplete_trace(tree, sweep_package, tmp_path, monkeypatch, dropped, valid):
    """n is about 5 at 0.05/s (4 slots before onset, 1 after the drain): max(1, floor(0.05)) = 1."""
    contract = _contract_for(tree, sweep_package, "frontend-pause-effect", 0.05, tmp_path)
    receipt, _ = _execute(tree, contract, monkeypatch, drop_traces=_tokens(tree, contract, range(dropped)))
    record = _completeness(contract)
    assert record["windows"]["pre-onset"]["successful"] + record["windows"]["after-drain"]["successful"] == 5
    assert (record["allowance"], record["incomplete"]) == (1, dropped)
    assert (receipt["state"] == "valid") is valid, receipt["error"]


# --------------------------------- container-health guard (user 2026-10-03, with option A: proxy memory 256M)
@pytest.mark.parametrize("planted,reason", (
    ({"oom_killed": ("frontendproxy",)}, "container health: OOMKilled: frontendproxy"),
    ({"oom_killed": ("otelcol",)}, "container health: OOMKilled: otelcol"),
    ({"restarted": ("frontend",)}, "container health: application container restarted during the cell: frontend"),
))
def test_an_oom_kill_or_an_application_restart_invalidates_the_cell(tree, sweep_package, tmp_path, monkeypatch, planted, reason):
    contract = _contract_for(tree, sweep_package, "no-fault-calibration", 0.05, tmp_path)
    receipt, _ = _execute(tree, contract, monkeypatch, **planted)
    health = json.loads((Path(contract["remoteArtifactRoot"]) / "container-health.json").read_text())
    assert receipt["state"] == "invalid" and reason in receipt["error"]
    assert health["valid"] is False and health["reasons"]


def test_a_restart_of_infrastructure_is_recorded_but_does_not_invalidate(tree, sweep_package, tmp_path, monkeypatch):
    contract = _contract_for(tree, sweep_package, "no-fault-calibration", 0.05, tmp_path)
    receipt, _ = _execute(tree, contract, monkeypatch, restarted=("otelcol",))
    health = json.loads((Path(contract["remoteArtifactRoot"]) / "container-health.json").read_text())
    assert receipt["state"] == "valid", receipt["error"]
    assert [row["restartCount"] for row in health["final"] if row["service"] == "otelcol"] == [1]


def test_a_pre_onset_failure_at_low_rate_fails_g2_on_the_target_and_stops_the_cell(tree, sweep_package, tmp_path, monkeypatch):
    contract = _contract_for(tree, sweep_package, "frontend-pause-effect", 0.05, tmp_path)
    receipt, _ = _execute(tree, contract, monkeypatch, fail_first_request=True)
    assert receipt["state"] == "invalid" and "protocol gate(s) G2 did not pass" in receipt["error"]
    retained = json.loads((Path(contract["remoteArtifactRoot"]) / "protocol-gates.json").read_text())
    assert retained["valid"] is False and retained["failedGates"] == ["G2"]


def test_an_upstream_generator_container_invalidates_the_cell_before_any_traffic(tree, sweep_package, tmp_path, monkeypatch):
    contract = _contract_for(tree, sweep_package, "no-fault-calibration", 0.05, tmp_path)
    receipt, target = _execute(tree, contract, monkeypatch, generator_container=True)
    assert receipt["state"] == "invalid" and "upstream generator" in receipt["error"]
    assert target.served == []


# --------------------------------------------------- 6. planted defects in retained artifacts are rejected
@pytest.fixture(scope="module")
def sealed(tree, sweep_package, tmp_path_factory):
    """One valid frontend-pause cell at 1/s and one throttle cell at 0.2/s, executed once and copied per plant."""
    cells = {}
    with pytest.MonkeyPatch.context() as patch:
        for regime, rate in (("frontend-pause-effect", 1.0), ("productcatalog-cpu-throttle-effect", 0.2)):
            base = tmp_path_factory.mktemp("sealed")
            contract = _contract_for(tree, sweep_package, regime, rate, base)
            receipt, _ = _execute(tree, contract, patch)
            assert receipt["state"] == "valid", receipt["error"]
            cells[regime] = (Path(contract["remoteArtifactRoot"]), contract)
    return cells


def _plant(tree, cell_root: Path, contract, name: str, mutate) -> None:
    path = cell_root / name
    if name.endswith(".json"):
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    else:
        # Logs are raw bytes (a stray 0xbf included): edit them losslessly.
        text = path.read_bytes().decode("utf-8", errors="surrogateescape")
        path.write_bytes(mutate(text).encode("utf-8", errors="surrogateescape"))
    (cell_root / "content-manifest.json").write_text(
        json.dumps(tree.remote.content_manifest(cell_root, contract["requiredArtifacts"]), indent=2, sort_keys=True) + "\n"
    )


def _shift_onset(value, seconds):
    for key in ("startedMonotonic", "appliedMonotonic"):
        value[key] += seconds
    for key in ("actualOnsetMonotonicOffsetSeconds", "appliedMonotonicOffsetSeconds"):
        value[key] += seconds


def _shift_fault(value, seconds):
    """The whole fault (every stamp and probe) moved later: internally consistent, but off its schedule."""
    for key in ("startedMonotonic", "appliedMonotonic", "revertingMonotonic", "revertedMonotonic", "readyAtMonotonic"):
        value[key] += seconds
    for key in ("actualOnsetMonotonicOffsetSeconds", "appliedMonotonicOffsetSeconds",
                "revertingMonotonicOffsetSeconds", "actualOffsetMonotonicOffsetSeconds"):
        value[key] += seconds
    for row in value["probes"]:
        row["startMonotonic"] += seconds
        row["endMonotonic"] += seconds


PLANTS = {
    "a-missing-request": ("frontend-pause-effect", "request-ledger.json",
                          lambda v: (v["requests"].pop(), v.__setitem__("offered", v["offered"] - 1)), "route ledger identity"),
    "a-rescheduled-request": ("frontend-pause-effect", "request-ledger.json",
                              lambda v: v["requests"][3].__setitem__("scheduledOffsetSeconds", 3.5), "identity or schedule"),
    "another-rate": ("frontend-pause-effect", "request-ledger.json",
                     lambda v: v.__setitem__("ratePerSecond", 10.0), "route ledger identity"),
    "an-outcome-not-replaying": ("frontend-pause-effect", "request-ledger.json",
                                 lambda v: v["requests"][2].__setitem__("outcome", "timeout"), "outcome does not replay"),
    "onset-1.5-s-late": ("frontend-pause-effect", "intervention.json",
                         lambda v: _shift_fault(v, 1.5),
                         # moving the fault moves the completeness windows too; either replay catches it first
                         "trace completeness record does not replay|protocol gate record does not replay"),
    "onset-moved-hold-short": ("frontend-pause-effect", "intervention.json",
                               lambda v: _shift_onset(v, 1.5), "hold was shorter than compiled"),
    "onset-before-its-schedule": ("frontend-pause-effect", "intervention.json",
                                  lambda v: _shift_fault(v, -(v["actualOnsetMonotonicOffsetSeconds"] - v["scheduledOnsetSeconds"]) - 0.5),
                                  "precedes its schedule"),
    "a-post-command-onset": ("frontend-pause-effect", "intervention.json",
                             lambda v: (v.__setitem__("startedMonotonic", v["appliedMonotonic"] + 0.01),
                                        v.__setitem__("actualOnsetMonotonicOffsetSeconds", v["appliedMonotonicOffsetSeconds"] + 0.01)),
                             "out of order"),
    "a-probe-outside-its-phase": ("frontend-pause-effect", "intervention.json",
                                  lambda v: v["probes"][0].__setitem__("startMonotonic", v["barrierMonotonic"] + 1.0),
                                  "outside its phase"),
    "no-probe-stamps": ("frontend-pause-effect", "intervention.json",
                        lambda v: v.__setitem__("probes", []), "probe stamps"),
    "the-route-stayed-up-in-the-pause": ("frontend-pause-effect", "intervention.json",
                                         lambda v: v.__setitem__("duringRouteAvailable", True), "entry route"),
    "a-barrier-other-than-the-ledger": ("frontend-pause-effect", "intervention.json",
                                        lambda v: v.__setitem__("barrierMonotonic", v["barrierMonotonic"] + 0.5), "barrier"),
    "a-throttle-not-restored": ("productcatalog-cpu-throttle-effect", "intervention.json",
                                lambda v: v["throttle"].__setitem__("postNanoCpus", 100_000_000), "not applied and restored"),
    "a-throttle-never-applied": ("productcatalog-cpu-throttle-effect", "intervention.json",
                                 lambda v: v["throttle"].__setitem__("duringNanoCpus", 24_000_000_000), "not applied and restored"),
    "a-gate-verdict-flipped": ("productcatalog-cpu-throttle-effect", "protocol-gates.json",
                               lambda v: v["verdicts"][1].__setitem__("verdict", "fail"), "does not replay"),
    "a-generator-container": ("productcatalog-cpu-throttle-effect", "upstream-generator.json",
                              lambda v: v["afterWindow"]["services"]["loadgenerator"].__setitem__("containers", ["x"]),
                              "was not absent"),
    "a-trace-dropped-after-sealing": ("productcatalog-cpu-throttle-effect", "trace-correlation.json",
                                      lambda v: (v["rows"][0].__setitem__("observedPathServices", ["frontendproxy"]),
                                                 v["rows"][0].__setitem__("observedTraceServices", ["frontendproxy"])),
                                      "trace completeness record does not replay"),
    "a-completeness-record-relabelled-valid": ("productcatalog-cpu-throttle-effect", "trace-completeness.json",
                                               lambda v: v.__setitem__("allowance", 999), "does not replay"),
    "an-incomplete-trace-moved-into-the-drain": ("productcatalog-cpu-throttle-effect", "trace-completeness.json",
                                                 lambda v: v.__setitem__("faultAndDrainWindowSeconds", [0.0, 180.0]),
                                                 "does not replay"),
    "an-oom-kill-hidden-in-the-health-record": ("productcatalog-cpu-throttle-effect", "container-health.json",
                                                lambda v: v["final"][0].__setitem__("oomKilled", True),
                                                "container health verdict does not replay"),
    "a-memory-limit-not-applied": ("productcatalog-cpu-throttle-effect", "container-health.json",
                                   lambda v: v["memoryLimitUpdates"][0]["after"].__setitem__("memory", 52428800),
                                   "declared memory limits were not applied"),
    "logs-without-timestamps": ("productcatalog-cpu-throttle-effect", "application.log",
                                lambda text: re.sub(r"\| \S+Z ", "| ", text), "no Docker sub-second timestamps"),
}


@pytest.mark.parametrize("plant", sorted(PLANTS))
def test_planted_artifact_defects_are_rejected_by_the_terminal(tree, sealed, tmp_path, plant):
    regime, name, mutate, message = PLANTS[plant]
    source, contract = sealed[regime]
    cell_root = tmp_path / "cell"
    shutil.copytree(source, cell_root)
    assert tree.terminal.validate_cell(cell_root, contract)["state"] == "valid"
    _plant(tree, cell_root, contract, name, mutate)
    with pytest.raises(tree.terminal.ValidationError, match=message):
        tree.terminal.validate_cell(cell_root, contract)


def test_target_command_wrappers_survive_a_non_utf8_byte(tree, monkeypatch):
    """The real subprocess wrappers of the target controllers: one 0xbf on stdout must not raise (it aborted Hotel's
    sweep1 attempt 2); text mode yields U+FFFD, binary mode the byte."""
    stray = ["/usr/bin/printf", "x\\277y"]
    for module in (tree.remote, frozen_remote):
        assert module.command(stray).stdout == "x\ufffdy"
        assert module.command(stray, binary=True).stdout == b"x\xbfy"
    assert tree.setup.command(stray).stdout == "x\ufffdy"
    assert tree.runtime._target_command(stray) == "x\ufffdy"


# -------------------------------------------------------------------------------- 7. vendoring and 3.9 floor
TARGET_FILES = (
    "modules/otel-demo/execution/candidate_sweep.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/validation/candidate_terminal.py",
    "modules/otel-demo/validation/protocol_gates.py",
)


def test_protocol_gates_are_vendored_byte_identically():
    vendored = MODULE / "validation/protocol_gates.py"
    assert hashlib.sha256(vendored.read_bytes()).hexdigest() == (
        "1b3c8a3b1e9ea1f4013aa372beafc8fe0b2be14e835e114ebd9b65a69a416590"
    )
    source = ROOT.parent / "observability-placement/src/obsplacement/protocol_gates.py"
    if source.is_file():
        assert vendored.read_bytes() == source.read_bytes()


@pytest.mark.parametrize("relative", TARGET_FILES)
def test_changed_target_files_parse_as_python39_and_defer_annotations(relative):
    text = (ROOT / relative).read_text()
    tree_ = ast.parse(text, feature_version=(3, 9))
    if relative.endswith("protocol_gates.py"):
        return
    assert any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__" and any(a.name == "annotations" for a in node.names)
        for node in tree_.body
    ), "a PEP 604 annotation would be evaluated eagerly on 3.9 (py_compile does not catch it)"


def test_plan_digest_is_identical_under_python39_isolated_and_this_interpreter(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('s', {str(MODULE / 'execution/candidate_sweep.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['s'] = m; spec.loader.exec_module(m)\n"
        "d = m.load_descriptor(); p = m.compile_plan(d, 1)\n"
        "print(json.dumps([m.canonical_sha256(d), m.canonical_sha256(p), m.MINIMUM_REMAINING_SECONDS, m.RUN_WINDOW_HOURS]))\n"
    )
    result = subprocess.run(
        [str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == [SWEEP_DESCRIPTOR_SHA256, SWEEP_PLAN_A1_SHA256, 5472, 3]
