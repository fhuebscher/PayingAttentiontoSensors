"""otel-offpath-pilot-v2: the second OTel off-path manifestation pilot (main repo research/traffic-sweep/BUDGET_E.md amendment 1,
protocol decision 108, user 2026-10-12).

Pilot v1 (otel-offpath-pilot-v1, attempt 1, harness 8c53cb2) stopped at its cell 2: productcatalogservice was memcg-OOM-killed at its
upstream 20 MiB limit at 100 req/s of the mix.  v2 is v1's cell (the same mix, scenarios, per-route completeness and gates) at 25 and
50 req/s, with the throttle dropped, SUT memory limits upstream's, otelcol and jaeger 1 GiB, and v1's criteria unchanged minus the
throttle row.  Covers, each with a planted defect: the plan pin (descriptor and attempt-1 plan digests, 3.9/3.13 identity); C-identity
and v1-identity (mix, criteria, scenarios); the sizing at 50 req/s; the group run order; no run-ID reuse (v1 attempt 1 included); the
epoch in the runtime, the gate chain and the target; every regime end to end on the fake target with the terminal's replay; the 20-item
minimums of the criteria still reachable at 25 req/s; no throttle anywhere; the rendered tree; the 3.9 floor.  v1's tests
(tests/test_otel_offpath_pilot.py) exercise the shared code (mix, ledger, terminal replay, completeness) and are not repeated.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
PILOT = "otel-offpath-pilot-v2"
V1 = "otel-offpath-pilot-v1"
LOAD = "otel-load-pilot-v1"
C = "otel-repeat-episodes-c-v1"
REPEAT = "otel-repeat-episodes-v1"
QUIET = "otel-quiet-calibration-v1"
SWEEP = "otel-traffic-sweep-v1"
RATES = (25.0, 50.0)
NO_FAULT = "no-fault-calibration"
FRONTEND = "frontend-pause-effect"
FRAUD = "fraud-pause-effect"
ACCOUNTING = "accounting-pause-effect"
THROTTLE = "productcatalog-cpu-throttle-effect"
REGIMES = (NO_FAULT, FRONTEND, FRAUD, ACCOUNTING)
SEED = 20261012

PILOT_DESCRIPTOR_SHA256 = "b22c4ee66526ba18dcfc2c6f372c3f74c127ad73273b6b7a8d98825b5bc8f6a9"
PILOT_PLAN_A1_SHA256 = "a929b4d92df25f71264057a535cd7bbe337155a746a8e0aa19ee3c6cd003f021"
C_DESCRIPTOR_SHA256 = "6dd3cb7215db438cdf2f0618dd62eed583b86004f5f0254c565eabe93cc13721"
V1_DESCRIPTOR_SHA256 = "2136639d30bfa33e4ea9f7f1a5a7dd1382841c9c9b5444725e58cb77ba7b557a"
V1_PLAN_A1_SHA256 = "8b3d7aa84e26c31de724c3686331b1f7347b9fd086a1debfefdea80799104814"
PILOT_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor", "quiet-compiler", "repeat-compiler", "repeat-descriptor",
    "repeat-c-compiler", "repeat-c-descriptor",
}
# Attempts that ran on fb14srv6, per epoch: their run IDs exist on the host and must never be planned again.
RAN = {SWEEP: (1, 2), QUIET: (1, 2, 3), REPEAT: (1,), C: (1,), LOAD: (1,), V1: (1,)}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("otel_offpath_v2_compiler_test", MODULE / "execution/candidate_offpath_pilot_v2.py")
v1 = load("otel_offpath_v2_v1_tests", ROOT / "tests/test_otel_offpath_pilot.py")      # v1's compiler, fake target, statistics and verdict
p1 = v1.p
repeat_c = p.repeat_c
quiet = p.quiet
sweep = p.sweep
b_tests = v1.b_tests
helpers = v1.helpers
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
    loaded.compiler = load(f"otel_{label}_compiler", module / "execution/candidate_offpath_pilot_v2.py")
    return loaded


@pytest.fixture(scope="module")
def pilot_tree(tmp_path_factory):
    return _tree(tmp_path_factory, PILOT, "offpath-v2-tree")


@pytest.fixture(scope="module")
def pilot_package(pilot_tree, tmp_path_factory):
    return helpers._package(pilot_tree.runtime, pilot_tree.compiler, tmp_path_factory.mktemp("offpath-v2-package"), window_hours=3)


def _plan(attempt: int = 1):
    return p.compile_plan(p.load_descriptor(), attempt)


def _strip(timing, keys):
    return {key: value for key, value in timing.items() if key not in keys}


# ------------------------------------------------------------------------------------- 1. the plan and its pin
def test_the_plan_is_pinned_8_cells_in_two_rate_ascending_segments_without_the_throttle():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    cells = p.flatten_cells(plan)
    assert p.canonical_sha256(document) == PILOT_DESCRIPTOR_SHA256 == p.EXPECTED_DESCRIPTOR_SHA256
    assert p.canonical_sha256(plan) == PILOT_PLAN_A1_SHA256
    assert len(cells) == plan["runCount"] == plan["uniqueRunCount"] == p.TOTAL_RUNS == 8
    assert [segment["rates"] for segment in plan["blocks"]] == [[25.0], [50.0], [25.0, 50.0]]
    assert [cell["ordinalPosition"] for cell in cells] == list(range(1, 9))
    assert sorted((c["runKey"]["regime"], c["runKey"]["requestsPerSecond"]) for c in cells) == sorted(
        (regime, rate) for regime in REGIMES for rate in RATES)
    assert {cell["fault"] for cell in cells} == {None, "frontend-pause", "fraud-pause", "accounting-pause"}
    assert not any("throttle" in cell["runKey"]["regime"] or "throttle" in str(cell["fault"]) for cell in cells)
    assert {cell["runKey"]["studyEpoch"] for cell in cells} == {PILOT} and plan["studyEpoch"] == PILOT
    assert (p.MINIMUM_REMAINING_SECONDS, p.RUN_WINDOW_HOURS) == (8 * (211 + 300) + 900 + 600, 3) == (5588, 3)


def test_planted_defect_an_edited_descriptor_or_plan_is_refused_and_moves_the_pin():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    for mutate in (
        lambda d: d["schedule"].update(seed=20261013),                                      # v1's seed
        lambda d: d["timing"].update(duringFaultProbe=True),                                # H10 off
        lambda d: d["workload"].update(concurrency=4500),                                   # v1's concurrency
        lambda d: d["design"].update(rates=[100.0, 150.0]),
        lambda d: d.update(declaration="research/traffic-sweep/DECLARATION_PILOT_OFFPATH_OTEL.md"),
        lambda d: d["workload"]["mix"]["tasks"][1].update(weight=9),
        lambda d: d["faultDesign"]["scenarios"].update({"productcatalog-cpu-throttle": {"service": "productcatalogservice"}}),
        lambda d: d["faultDesign"]["scenarios"]["fraud-pause"].update(service="accountingservice"),
    ):
        planted = copy.deepcopy(document)
        mutate(planted)
        assert p.canonical_sha256(planted) != PILOT_DESCRIPTOR_SHA256
        with pytest.raises(p.ProtocolError, match="differs from its generator"):
            p.validate_descriptor(planted)
    for mutate in (
        lambda q: q["blocks"][1]["cells"][0]["timing"].update(faultOnsetSeconds=61.0),
        lambda q: q["blocks"][0]["cells"].pop(),
        lambda q: q["blocks"][0]["cells"][0]["timing"].update(concurrency=4500),
        lambda q: q["blocks"][1]["cells"][1]["timing"].update(generatorOpenFilesMinimum=1024),
        lambda q: q.update(blocks=list(reversed(q["blocks"]))),
        lambda q: q["blocks"][0]["cells"][0]["runKey"].update(studyEpoch=V1),
    ):
        broken = copy.deepcopy(plan)
        mutate(broken)
        with pytest.raises(p.ProtocolError, match="differs from the frozen schedule"):
            p.validate_plan(document, broken)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "EXPECTED_DESCRIPTOR_SHA256", C_DESCRIPTOR_SHA256)
        with pytest.raises(p.ProtocolError, match="differs from the reviewed pin"):
            p.load_descriptor()


def test_the_descriptor_file_is_the_generators_output_and_is_cs_apart_from_the_declared_keys():
    path = ROOT / "pipelines/campaigns/otel-offpath-pilot-v2.json"
    assert path.read_bytes() == p._pretty_bytes(p.derive_pilot_descriptor())
    document, base = p.load_descriptor(), repeat_c.load_descriptor()
    assert document["id"] == PILOT and document["declaration"].startswith("research/traffic-sweep/DECLARATION_PILOT_OFFPATH_V2_OTEL.md ")
    assert document["derivedFrom"]["studyEpoch"] == C and document["derivedFrom"]["descriptorCanonicalSha256"] == C_DESCRIPTOR_SHA256
    top, nested = v1._descriptor_differences(document, base)
    assert top == set(p.REPLACED_DESCRIPTOR_KEYS) - {"amendments"}
    assert nested == {key: set(value) for key, value in p.REPLACED_DESCRIPTOR_SUBKEYS.items()}
    for key in ("protocolGates", "containerHealthGuard", "postureRealization", "workflow"):
        assert document[key] == base[key], key
    assert document["schedule"]["seed"] == SEED != base["schedule"]["seed"]


def test_v2_is_v1_without_the_throttle_the_mix_the_pauses_and_the_criteria_are_v1s():
    """The criteria are the frozen v1 declaration's, minus the throttle row (protocol decision 108); the mix and the pause scenarios are v1's."""
    assert p.MIX == p1.MIX
    document, document1 = p.load_descriptor(), p1.load_descriptor()
    assert document["workload"]["mix"] == document1["workload"]["mix"] and document["workload"]["routeServices"] == document1["workload"]["routeServices"]
    for scenario in ("fraud-pause", "accounting-pause", "frontend-pause"):
        assert document["faultDesign"]["scenarios"][scenario] == document1["faultDesign"]["scenarios"][scenario]
    assert set(document["faultDesign"]["scenarios"]) == {"fraud-pause", "accounting-pause", "frontend-pause"}
    defaults, defaults1 = document["analysis"]["manifestationCriterionDefaults"], document1["analysis"]["manifestationCriterionDefaults"]
    assert {k: v for k, v in defaults1.items() if not k.startswith("throttle")} == defaults
    assert not any("throttle" in key.lower() for key in defaults)
    assert document["analysis"]["traceCompleteness"] == document1["analysis"]["traceCompleteness"] or (
        document["analysis"]["traceCompleteness"]["faultCells"]["rule"] == document1["analysis"]["traceCompleteness"]["faultCells"]["rule"])
    # the frontend-pause and off-path rows, and the no-fault precondition, are v1's word for word
    for key in ("frontendPause", "offPathPause", "noFaultPrecondition", "noFaultCell", "minimumSpans", "onset", "hold", "preOnsetSegment"):
        assert defaults[key] == defaults1[key], key
    sentence = p.MANIFESTATION_CRITERION
    assert "throttle" not in sentence and "frontend pause manifests if at least 90 %" in sentence
    assert p1.MANIFESTATION_CRITERION.endswith(sentence.split("per fault and rate, one cell: ", 1)[1])


def test_the_digests_are_identical_under_python39_isolated_and_this_interpreter(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import importlib.util, json, sys\n"
        f"s = importlib.util.spec_from_file_location('p', {str(MODULE / 'execution/candidate_offpath_pilot_v2.py')!r})\n"
        "m = importlib.util.module_from_spec(s); sys.modules['p'] = m; s.loader.exec_module(m)\n"
        "d = m.load_descriptor()\n"
        "print(json.dumps([m.canonical_sha256(d), m.canonical_sha256(m.compile_plan(d, 1)), m.MINIMUM_REMAINING_SECONDS, m.RUN_WINDOW_HOURS]))\n"
    )
    result = subprocess.run([str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [PILOT_DESCRIPTOR_SHA256, PILOT_PLAN_A1_SHA256, 5588, 3]


def test_every_cell_is_cs_cell_at_the_same_regime_and_rate_apart_from_the_declared_keys():
    for cell in p.flatten_cells(_plan(1)):
        key, timing = cell["runKey"], cell["timing"]
        template = p.TIMING_TEMPLATE_REGIME.get(key["regime"], key["regime"])
        c_timing = repeat_c.cell_timing(template, key["requestsPerSecond"], 1)
        assert set(timing) == set(c_timing) | p.NEW_TIMING_KEYS
        assert _strip(timing, p.REPLACED_TIMING_KEYS | p.NEW_TIMING_KEYS) == _strip(c_timing, p.REPLACED_TIMING_KEYS), key
        assert 0 <= timing["faultOnsetPhaseOffsetSeconds"] < 1.0 / key["requestsPerSecond"]
        assert timing["offered"] == int(key["requestsPerSecond"] * 180) and timing["workloadMix"] == p.MIX
        assert (timing["duringFaultProbe"], timing["freezeStamps"]) == (False, True)
    drifted = copy.deepcopy(p.flatten_cells(_plan(1))[0]["timing"])
    drifted["faultHoldSeconds"] = 30
    assert _strip(drifted, p.REPLACED_TIMING_KEYS | p.NEW_TIMING_KEYS) != _strip(
        repeat_c.cell_timing(NO_FAULT, 25.0, 1), p.REPLACED_TIMING_KEYS)


# ------------------------------------------------------------------------------------- 2. the sizing at 50 req/s
def test_the_generator_is_sized_for_50_per_second_and_only_the_proxy_and_the_telemetry_backend_have_a_limit():
    for cell in p.flatten_cells(_plan(1)):
        timing = cell["timing"]
        assert timing["concurrency"] == 1500 >= 2 * 50 * timing["requestTimeoutSeconds"]
        assert timing["generatorOpenFilesMinimum"] == 1500 + 1024
        assert timing["serviceMemoryLimitBytes"] == {"frontendproxy": 256 * 1024 ** 2, "otelcol": 1024 ** 3, "jaeger": 1024 ** 3}
        assert p.FRONTENDPROXY_BYTES_PER_WAITING_REQUEST * 50 * 15 <= 256 * 1024 ** 2          # 225 MB
    sut = set(json.loads((MODULE / "postures/catalog.json").read_text())["applicationServices"]) - {"frontendproxy"}
    assert not set(p.SERVICE_MEMORY_LIMIT_BYTES) & sut                       # every SUT limit stays upstream's (decision 108)
    rows = {r["service"]: r for r in p.load_descriptor()["sutDeviations"] if r["setting"] == "memory limit (HostConfig.Memory)"}
    assert set(rows) == {"frontendproxy", "otelcol", "jaeger"}
    # planted: C-sized (300 < 50 x 15) generator is refused, and a SUT limit (productcatalogservice) smuggled in is found
    document = p.load_descriptor()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "CONCURRENCY", 300)
        planted = p._compile(document, 1)
    with pytest.raises(p.ProtocolError):
        p.validate_plan(document, planted)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "SERVICE_MEMORY_LIMIT_BYTES", {**p.SERVICE_MEMORY_LIMIT_BYTES, "productcatalogservice": 64 * 1024 ** 2})
        planted = p._compile(document, 1)
    with pytest.raises(p.ProtocolError, match="differs from the frozen schedule"):
        p.validate_plan(document, planted)


# ------------------------------------------------------------------------------------- 3. order, run IDs, spent attempts
def test_the_run_order_is_nf25_pauses25_nf50_pauses50_then_the_frontend_pauses_and_a_plan_that_does_not_is_refused():
    """Coordinator default S8 (2026-10-12): the on-path control last, each rate's baseline before its off-path pauses."""
    plan = _plan(1)
    cells = p.flatten_cells(plan)
    order = [(c["runKey"]["regime"], c["runKey"]["requestsPerSecond"]) for c in cells]
    assert order[0] == (NO_FAULT, 25.0) and {order[1][0], order[2][0]} == {FRAUD, ACCOUNTING} and {order[1][1], order[2][1]} == {25.0}
    assert order[3] == (NO_FAULT, 50.0) and {order[4][0], order[5][0]} == {FRAUD, ACCOUNTING} and {order[4][1], order[5][1]} == {50.0}
    assert order[6:] == [(FRONTEND, 25.0), (FRONTEND, 50.0)]
    document = p.load_descriptor()
    for number in (1, 2):
        receipt = document["schedule"]["segments"][number - 1]
        pauses = [r for r in p.segment_cells(number) if r["regime"] in (FRAUD, ACCOUNTING)]
        expected = quiet.fisher_yates(pauses, SEED, PILOT, number, "offpath-pilot-v2-schedule-v1-group1")
        assert receipt["order"][1:] == [p.cell_label(r) for r in expected]
    # planted: a compiler whose frontend-pause segment runs before the 50 req/s segment (and a descriptor generated with it) is refused
    # by the rule, not only by the pin; so is a no-fault cell not followed by its pauses; a descending rate list is refused
    for segments, message in (
        ((p.SEGMENTS[0], p.SEGMENTS[2], p.SEGMENTS[1]), "frontend-pause cells are not last"),
        (({"rates": (25.0,), "groups": (1, 0)}, p.SEGMENTS[1], p.SEGMENTS[2]), "does not run its no-fault cell|must be followed by the off-path pauses"),
        # the 50 req/s pauses before their baseline: every segment is sorted and the frontend pauses are last, only this rule fires
        ((p.SEGMENTS[0], {"rates": (50.0,), "groups": (1,)}, {"rates": (50.0,), "groups": (0,)}, p.SEGMENTS[2]),
         "must be followed by the off-path pauses"),
    ):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(p, "SEGMENTS", segments)
            wrong = p.derive_pilot_descriptor()
            wrong_plan = p._compile(wrong, 1)
            patch.setattr(p, "validate_descriptor", lambda d: d)
            patch.setattr(p, "_compile", lambda d, a: wrong_plan)
            with pytest.raises(p.ProtocolError, match=message):
                p.validate_plan(wrong, wrong_plan)
    # planted: the previous order (rate-ascending segments, frontend pause inside its rate) is not the one the pin holds
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "SEGMENTS", ({"rates": (25.0,), "groups": (0, 1, 2)}, {"rates": (50.0,), "groups": (0, 1, 2)}))
        previous = p.allocate_schedule()
    assert previous != document["schedule"]["segments"]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "RATES", (50.0, 25.0))
        with pytest.raises(p.ProtocolError, match="ascending"):
            p.allocate_schedule()


def _ran_run_ids() -> dict:
    compilers = {SWEEP: sweep, QUIET: quiet, REPEAT: p.repeat_b, C: repeat_c, LOAD: v1.load_pilot, V1: p1}
    ids = {}
    for epoch, attempts in RAN.items():
        compiler = compilers[epoch]
        document = compiler.load_descriptor()
        for attempt in attempts:
            ids[(epoch, attempt)] = {cell["runId"] for cell in compiler.flatten_cells(compiler.compile_plan(document, attempt))}
    return ids


def test_no_v2_run_id_equals_one_that_ran_including_v1_attempt_1_and_the_planted_reuse_is_found():
    ran = _ran_run_ids()
    assert len(ran[(V1, 1)]) == 10 and p1.canonical_sha256(p1.compile_plan(p1.load_descriptor(), 1)) == V1_PLAN_A1_SHA256
    for attempt in (1, 2, 3):
        ids = {cell["runId"] for cell in p.flatten_cells(_plan(attempt))}
        assert len(ids) == 8 and v1._reused(ids, ran) == {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "EPOCH", V1)
        patch.setattr(p, "RATES", (100.0,))
        reused = {p.run_id_for(p.run_key_for(regime, 100.0, 1, "full", 1)) for regime in (NO_FAULT, FRONTEND, FRAUD)}
    assert v1._reused(reused, ran) == {(V1, 1): 3}


def test_v1_and_v2_attempt_1_are_recorded_spent():
    # 2026-10-12: v2 attempt 1 ran (harness ff29b93, plan a929b4d9, 8/8 valid, fetched and byte-verified 147/147).
    table = v1._spent_table_in_source()
    assert set(table[V1]) == {1} and "8c53cb2" in table[V1][1] and "OOM" in table[V1][1]
    assert set(table[PILOT]) == {1} and "ff29b93" in table[PILOT][1] and "a929b4d9" in table[PILOT][1]
    assert PILOT_PLAN_A1_SHA256.startswith("a929b4d9")                         # the plan that ran


# ------------------------------------------------------------- 4. the epoch in the runtime, the gate chain and the target
def test_the_selector_activates_v2_in_every_reader_and_the_gate_chain_derives_8_cells(pilot_tree, pilot_package, tmp_path):
    runtime, remote = pilot_tree.runtime, pilot_tree.remote
    assert runtime.STUDY_EPOCH == PILOT and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (8, 5588, 3)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | PILOT_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_offpath_pilot_v2.py"
    assert runtime.DESCRIPTOR == pilot_tree.root / "pipelines/campaigns/otel-offpath-pilot-v2.json"
    assert pilot_tree.setup.controller_paths(PILOT) == runtime.CONTROLLER_PATHS
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {
        "duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}
    assert PILOT in remote.REPEAT_STUDY_EPOCHS and PILOT in remote.TIMED_STUDY_EPOCHS and V1 in remote.REPEAT_STUDY_EPOCHS
    binding = pilot_package.gate_plan["binding"]
    assert f"study={PILOT} " in pilot_package.gate_plan["typedApproval"] and " runs=8 " in pilot_package.gate_plan["typedApproval"]
    assert pilot_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 5588
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_offpath_pilot_v2" and remote.SAFE_NAME.fullmatch(binding["compose"]["project"])
    earlier = (SWEEP, QUIET, REPEAT, C, LOAD, V1)
    other = (["/home/stig/observability-placement-candidate-v4-runs/" + e for e in earlier]
             + ["/home/stig/observability-placement-candidate-v4-runs/.setup-" + e for e in earlier]
             + ["/home/stig/observability-placement-candidate-v4-otel-srv6/" + e + "-" for e in earlier])
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert PILOT in binding[key] and not any(binding[key].startswith(path) for path in other), key
    document = runtime.execution_package(pilot_package)
    assert document["runCount"] == 8 and len(document["cells"]) == 8
    for contract, cell in zip(document["cells"], pilot_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and runtime.sweep_cell_timing(contract) == cell["timing"]
        assert ("docker-events.json" in contract["requiredArtifacts"]) is (contract["fault"]["action"] == "pause")
        assert contract["workload"]["concurrency"] == 1500 and contract["fault"]["service"] != "productcatalogservice"
    assert sum("docker-events.json" in c["requiredArtifacts"] for c in document["cells"]) == 6
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (PILOT,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
    assert len(cells) == 8 and remote.expected_minimum_remaining(document) == 5588
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_offpath_v2_tree_adapter", pilot_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == PILOT and set(adapter.SPENT_ATTEMPTS) == {1}      # attempt 1 ran and is spent
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
                adapter.inspect_campaign(tmp_path / "plan-a1", "a" * 40)
            patch.delitem(adapter.SPENT_ATTEMPTS, 1)
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 8 and bindings.plan_sha256 == PILOT_PLAN_A1_SHA256
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_planted_defect_a_selector_naming_v2_without_its_controller_set_or_family_membership_is_refused(tmp_path_factory, pilot_tree, pilot_package):
    root = helpers._copy_tree(tmp_path_factory.mktemp("offpath-v2-no-paths"), selector=json.dumps({"schemaVersion": 1, "studyEpoch": PILOT}) + "\n")
    runtime_path = root / "modules/otel-demo/execution/candidate_runtime.py"
    text = runtime_path.read_text()
    marker = '    OFFPATH_PILOT_V2_STUDY_EPOCH: {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_pilot_v2.py",'
    assert text.count(marker) == 1
    runtime_path.write_text(text.replace(marker, '    "otel-offpath-pilot-v0": {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_pilot_v2.py",'))
    with pytest.raises(Exception, match="names no declared non-frozen epoch"):
        load("otel_offpath_v2_no_paths_runtime", runtime_path)
    remote = pilot_tree.remote
    cells = pilot_tree.runtime.execution_package(pilot_package)["cells"]
    fault = next(x for x in cells if x["fault"]["scenario"] == "fraud-pause")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "REPEAT_STUDY_EPOCHS", (REPEAT, C, LOAD, V1))
        with pytest.raises(remote.RuntimeFailure, match="H10"):
            remote.require_harness_flags_consistent(fault)


# ------------------------------------------------------------------------------------- 5. every regime, end to end
@pytest.fixture(scope="module")
def cells(pilot_tree, pilot_package, tmp_path_factory):
    """One valid cell per regime at 25 req/s (4,500 requests) and a fraud pause at 50 req/s, on v1's fake target."""
    out = {}
    for regime, rate in [(r, 25.0) for r in REGIMES] + [(FRAUD, 50.0)]:
        with pytest.MonkeyPatch.context() as patch:
            base = tmp_path_factory.mktemp(f"offpath-v2-cell-{regime}-{int(rate)}")
            contract = v1._cell(pilot_tree, pilot_package, regime, rate, base)
            assert contract["studyEpoch"] == PILOT
            receipt, target, limits = v1._run(pilot_tree, contract, patch, pool_cap=1024 if regime == FRONTEND else 256)
            assert receipt["state"] == "valid", (regime, rate, receipt["error"])
            out[(regime, rate)] = types.SimpleNamespace(
                contract=contract, root=Path(contract["remoteArtifactRoot"]), target=target, limits=limits,
                asked=list(v1._CappedPool.asked))
    return out


@pytest.mark.parametrize("key", [(r, 25.0) for r in REGIMES] + [(FRAUD, 50.0)])
def test_run_cell_executes_a_v2_cell_and_the_terminal_accepts_it(pilot_tree, cells, key):
    cell = cells[key]
    contract, root, target = cell.contract, cell.root, cell.target
    rate = key[1]
    assert cell.limits.calls == [(2524, 524288)] and cell.asked.count(1500) == 2
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    ledger = json.loads((root / "request-ledger.json").read_text())
    assert ledger["kind"] == "otel-demo-mix-ledger-v1" and ledger["offered"] == int(rate * 180) == len(ledger["requests"])
    assert ledger["concurrency"] == 1500
    health = v1._read(contract, "container-health.json")
    assert health["valid"] is True and {r["service"] for r in health["memoryLimitUpdates"]} == {"frontendproxy", "otelcol", "jaeger"}
    limits = {r["service"]: r["after"]["memory"] for r in health["memoryLimitUpdates"]}
    assert limits == {"frontendproxy": 256 * 1024 ** 2, "otelcol": 1024 ** 3, "jaeger": 1024 ** 3}
    report = v1._validate(pilot_tree, root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    # the throttle is gone from every cell: no CPU-quota command, no throttle receipt
    assert not any(argv[:2] == ["docker", "update"] and "--cpus" in argv for argv in target.commands)
    if contract["fault"]["scenario"] is None:
        return
    intervention = v1._read(contract, "intervention.json")
    assert intervention["throttle"] is None and intervention["manifested"] is True and intervention["freeze"]["stampCheck"]["status"] == "ok"
    assert b_tests._probes_inside_the_fault(target, contract) == []                         # H10
    record = json.loads((root / "docker-events.json").read_text())
    assert record["service"] == contract["fault"]["service"] and record["verdict"]["status"] == "ok"


def test_the_20_item_minimums_are_reachable_at_25_req_per_second(cells):
    """The declaration's minimums (>= 20 spans or rows per segment) at the lowest rate: ~1.5 checkouts/s -> ~66 per 45 s, ~88 per 60 s;
    consumer spans per 60 s are several times 20; every share has >= 1,000 rows.  Measured on the fake cells' retained artifacts."""
    quiet_stats = v1.statistics_of(cells[(NO_FAULT, 25.0)].root, cells[(NO_FAULT, 25.0)].contract)
    assert quiet_stats["checkout"]["rows"] >= 60 and quiet_stats["rows"]["rows"] >= 1400
    for service in v1.CONSUMERS:
        assert quiet_stats["consumer"][service]["pre"] >= 60 and quiet_stats["consumer"][service]["hold"] >= 60
    for regime in (FRAUD, ACCOUNTING, FRONTEND):
        stats = v1.statistics_of(cells[(regime, 25.0)].root, cells[(regime, 25.0)].contract)
        assert stats["checkout"]["rows"] >= 60                                        # the 60 s hold
        assert stats["earlyRows"]["rows"] >= 1000 and stats["earlyCheckout"]["rows"] >= 40   # the 45 s window, by send time
        assert min(stats["earlyRows"]["rows"], stats["earlyCheckout"]["rows"], stats["checkout"]["rows"]) >= 20
        assert all(row["pre"] >= 60 for row in stats["consumer"].values())
    # the same arithmetic from the design: 5.9 % of 25 req/s
    assert 25 * 0.059 * 45 >= 60 and 25 * 0.059 * 60 >= 80


def test_each_fault_manifests_by_v1s_declared_criterion_at_25_and_50_req_per_second(cells):
    for rate in (25.0,):
        quiet_stats = v1.statistics_of(cells[(NO_FAULT, rate)].root, cells[(NO_FAULT, rate)].contract)
        for fault, regime in (("fraud-pause", FRAUD), ("accounting-pause", ACCOUNTING), ("frontend-pause", FRONTEND)):
            stats = v1.statistics_of(cells[(regime, rate)].root, cells[(regime, rate)].contract)
            assert v1.verdict(fault, stats, quiet_stats) == "manifests", (fault, stats)


def test_planted_defect_a_consumer_that_ignores_its_pause_does_not_manifest_at_25_req_per_second(pilot_tree, pilot_package, cells, tmp_path, monkeypatch):
    contract = v1._cell(pilot_tree, pilot_package, FRAUD, 25.0, tmp_path)
    receipt, _, _ = v1._run(pilot_tree, contract, monkeypatch, consumers_ignore_pause=True)
    assert receipt["state"] == "valid", receipt["error"]
    stats = v1.statistics_of(Path(contract["remoteArtifactRoot"]), contract)
    quiet_stats = v1.statistics_of(cells[(NO_FAULT, 25.0)].root, cells[(NO_FAULT, 25.0)].contract)
    assert v1.verdict("fraud-pause", stats, quiet_stats) == "does not manifest"


# ------------------------------------------------------------------------------------- 6. the rendered tree
@pytest.fixture(scope="module")
def materialized(tmp_path_factory):
    out = {}
    for label, epoch in (("v2", PILOT), ("v1", V1), ("c", C)):
        tree = helpers._copy_tree(tmp_path_factory.mktemp("materialize-v2-" + label),
                                  selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n")
        out[label] = tree / "out"
        out[label + "-digest"] = b_tests._materialize(tree, out[label])
    return out


def test_v2_renders_v1s_tree_collector_sampler_off_and_proxy_retention(materialized):
    materialize = load("otel_offpath_v2_materialize_module", MODULE / "materialize.py")
    assert PILOT in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS and PILOT in materialize.FRONTENDPROXY_LOG_RETENTION_EPOCHS
    assert b_tests._log_sampling_enabled(b_tests._collector_config(materialized["v2"])) is False
    assert materialized["v2-digest"] == materialized["v1-digest"] != materialized["c-digest"]
    assert v1._overlay(materialized["v2"])["services"]["frontendproxy"]["logging"] == {
        "driver": "json-file", "options": {"max-size": "4g", "max-file": "1"}}


def test_planted_defect_without_v2_in_the_sampling_tuple_the_collector_keeps_its_log_sampler(tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": PILOT}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    marker = '"otel-offpath-pilot-v1",\n    "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, '"otel-offpath-pilot-v1", "otel-offpath-e-v1", "otel-offpath-f-v1")'))
    b_tests._materialize(tree, tree / "out")
    assert b_tests._log_sampling_enabled(b_tests._collector_config(tree / "out")) is None


# ------------------------------------------------------------------------------------- 7. the 3.9 floor
V2_TARGET_FILES = (
    "modules/otel-demo/execution/candidate_offpath_pilot_v2.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/execution/candidate_runtime_adapter.py",
    "modules/otel-demo/materialize.py",
)


@pytest.mark.parametrize("relative", V2_TARGET_FILES)
def test_touched_target_files_parse_as_python39_and_read_no_name_bound_nowhere(relative):
    tree_ = ast.parse((ROOT / relative).read_text(), feature_version=(3, 9))
    assert b_tests._unbound_names(tree_) == []
    assert any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names) for n in tree_.body)
