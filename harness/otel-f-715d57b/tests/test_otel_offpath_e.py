"""otel-offpath-e-v1: the OTel campaign-E epoch (main repo research/traffic-sweep/BUDGET_E.md, protocol decisions 95-102 and 108), built
while the off-path pilot v2 runs and NOT activated.

E is the off-path pilot v2's cell (the upstream task mix as an open loop, pauses of frauddetectionservice and accountingservice, the frontend
pause as the on-path control) in 5 blocks (blocks 1-3 training, 4-5 test, decision 100) at one rate with a kept set of faults.  The rate
(RATE: 25 or 50 req/s) and the kept faults (KEPT_FAULTS: one of 6 sets with at least one off-path pause) are the two module constants the
coordinator sets after the pilot's verdict.  Covers, each with a planted defect: the plan pin of the default variant and the pinned digests,
plan digest, run count and budget of all 12 prepared variants (3.9/3.13 identity); C-identity and v2-identity (mix, scenarios, criteria
fields); the split; the run order per block; the seeded onset strata over the 5 blocks; the two parameters (refused values, the switching
procedure on a tree copy, the gate chain and a cell end to end for the variants that differ most); the sizing; no run-ID reuse; the wiring in
the runtime, the controller sets and the tombstone (NOT activated); every regime end to end on the fake target; the rendered tree; the 3.9
floor.  The pilots' tests (tests/test_otel_offpath_pilot.py, _v2.py) exercise the shared code (mix, ledger, terminal replay, completeness).
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/otel-demo"
EPOCH = "otel-offpath-e-v1"
V2 = "otel-offpath-pilot-v2"
V1 = "otel-offpath-pilot-v1"
LOAD = "otel-load-pilot-v1"
C = "otel-repeat-episodes-c-v1"
REPEAT = "otel-repeat-episodes-v1"
QUIET = "otel-quiet-calibration-v1"
SWEEP = "otel-traffic-sweep-v1"
NO_FAULT = "no-fault-calibration"
FRONTEND = "frontend-pause-effect"
FRAUD = "fraud-pause-effect"
ACCOUNTING = "accounting-pause-effect"
SEED = 20261012
ALL3 = ("fraud-pause", "accounting-pause", "frontend-pause")
DEFAULT = (25.0, ALL3)
E_CONTROLLER_KEYS = {
    "candidate-descriptor", "frozen-compiler", "frozen-descriptor", "protocol-gates", "study-epoch-selector",
    "sweep-compiler", "sweep-descriptor", "quiet-compiler", "repeat-compiler", "repeat-descriptor",
    "repeat-c-compiler", "repeat-c-descriptor",
}
C_DESCRIPTOR_SHA256 = "6dd3cb7215db438cdf2f0618dd62eed583b86004f5f0254c565eabe93cc13721"
# Attempts that ran, or may still run, on fb14srv6, per epoch: their run IDs exist on the host or may be planned again and must never
# collide with E's.  v2 is running (attempt 1) and may relaunch once (attempt 2); attempt 3 is listed so that no relaunch count can reach E.
RAN = {SWEEP: (1, 2), QUIET: (1, 2, 3), REPEAT: (1,), C: (1,), LOAD: (1,), V1: (1,), V2: (1, 2, 3)}

# The 12 prepared variants, computed by the generator under /usr/bin/python3 -I (3.9) and by uv run python (3.13), identical, 2026-10-12.
VARIANTS = {
    (25.0, ('fraud-pause', 'accounting-pause', 'frontend-pause')): {
        "descriptor": 'a17ac3d676a85dd9b488bd100a925679322ff93ec6c4257e8f102acd700e4398',
        "plan1": '503bf014cfb51cc85c96010b2dc4632fe24bba644c804c21fbd405b7bb517661',
        "runCount": 20, "minimumRemaining": 11720, "window": 5,
        "concurrency": 750, "openFiles": 1774,
    },
    (25.0, ('fraud-pause', 'frontend-pause')): {
        "descriptor": '79671d364d5e52b97f44a3853a57c6fae1d44684cbaf3c501d9d7c3875d63d21',
        "plan1": '1c955f296cefd8d15b59a02d2f6d796b6e166836856085a5c64fb8a2aa0c47ce',
        "runCount": 15, "minimumRemaining": 9165, "window": 4,
        "concurrency": 750, "openFiles": 1774,
    },
    (25.0, ('accounting-pause', 'frontend-pause')): {
        "descriptor": 'a95d810721c07feed889bd1f243058c619afab665dd9983ea49f003c9fafd6df',
        "plan1": '5ce44991a28e6a13f677b3b2c7df941cbcb42a31c24b548797ad3a13d50cf642',
        "runCount": 15, "minimumRemaining": 9165, "window": 4,
        "concurrency": 750, "openFiles": 1774,
    },
    (25.0, ('fraud-pause', 'accounting-pause')): {
        "descriptor": '9380b7394683d7cc94158914c8f147181060aab7a74146e078fa71e10fc5fbe7',
        "plan1": 'b90cacdb423de0ee266e1b9fb10ab95b037768b8c0b95d6d4bb4a41891c9f138',
        "runCount": 15, "minimumRemaining": 9165, "window": 4,
        "concurrency": 750, "openFiles": 1774,
    },
    (25.0, ('fraud-pause',)): {
        "descriptor": 'cf3725de6f5733e935125015bd5c0d140cc305d322aa132625df1d73dec6a7c7',
        "plan1": 'e05333d615aa48ed66bcff231f8d1e54cab9bcd5c7bdaa28ccb7cf3eeae888da',
        "runCount": 10, "minimumRemaining": 6610, "window": 3,
        "concurrency": 750, "openFiles": 1774,
    },
    (25.0, ('accounting-pause',)): {
        "descriptor": '54cf4757a9167d662f4da3dd5bc4d23e9f9d41441fa97a36d569a92f107bd5e9',
        "plan1": '73653dc9e21e644e61b65c2e28c5e726cd35b3a13606c9d19ed1497de169ca8c',
        "runCount": 10, "minimumRemaining": 6610, "window": 3,
        "concurrency": 750, "openFiles": 1774,
    },
    (50.0, ('fraud-pause', 'accounting-pause', 'frontend-pause')): {
        "descriptor": '7ab00ab2d677653aad7dc509ca09dbf4b7521a11e2a58da119cfc3b83d844e0d',
        "plan1": 'edcb2f0e300adca19cfba5f52130d6cae9531a19f1a97d45329dbabd91ea8946',
        "runCount": 20, "minimumRemaining": 11720, "window": 5,
        "concurrency": 1500, "openFiles": 2524,
    },
    (50.0, ('fraud-pause', 'frontend-pause')): {
        "descriptor": '96ba7532fd1fb99c9cb5f81d7b5bd191b4486884ea505c78af588f490594e798',
        "plan1": '9dda74a66cae709f0f48cb612ee706c96aa4a06d8b01f0af55d53cf6c912bb69',
        "runCount": 15, "minimumRemaining": 9165, "window": 4,
        "concurrency": 1500, "openFiles": 2524,
    },
    (50.0, ('accounting-pause', 'frontend-pause')): {
        "descriptor": 'c6a49b6a22a142db453a1a706da7abdda7c2965888c72bd5cb32a5ae97a064b2',
        "plan1": '6774eff729b90e7368ea561b11e47a5d7fb9cd71b23669a219aa952ea5d77f2f',
        "runCount": 15, "minimumRemaining": 9165, "window": 4,
        "concurrency": 1500, "openFiles": 2524,
    },
    (50.0, ('fraud-pause', 'accounting-pause')): {
        "descriptor": 'd13c44401f5cae426f820346c3802e56d05ad5bcf30c3ec45c665ca77d51a691',
        "plan1": 'ebc097bc1721eecca0d4e93db56bd0e10b53cd689542f35ccf1cac1feb1b4181',
        "runCount": 15, "minimumRemaining": 9165, "window": 4,
        "concurrency": 1500, "openFiles": 2524,
    },
    (50.0, ('fraud-pause',)): {
        "descriptor": '863e910a87e6a6287814d35f1811a898bf137a94cf19b3410b5bc186f0725653',
        "plan1": '850d0f1bf6669e06bfe9cd0db1c750006d33a87f74701ee7219ffe6645e2b15a',
        "runCount": 10, "minimumRemaining": 6610, "window": 3,
        "concurrency": 1500, "openFiles": 2524,
    },
    (50.0, ('accounting-pause',)): {
        "descriptor": '4e08d93532239624b02c4635f68b19843369d834f789af2d5162f8f4445b0f54',
        "plan1": '36ac5f9de2183d781642d0334f66d58decf6028cb86e17cb6d9ac2f72eb52e3d',
        "runCount": 10, "minimumRemaining": 6610, "window": 3,
        "concurrency": 1500, "openFiles": 2524,
    },
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("otel_offpath_e_compiler_test", MODULE / "execution/candidate_offpath_e.py")
v1 = load("otel_offpath_e_v1_tests", ROOT / "tests/test_otel_offpath_pilot.py")      # v1's compiler, fake target, statistics and verdict
p1 = v1.p
p2 = load("otel_offpath_e_v2_compiler_test", MODULE / "execution/candidate_offpath_pilot_v2.py")
repeat_c = p.repeat_c
quiet = p.quiet
sweep = p.sweep
b_tests = v1.b_tests
helpers = v1.helpers
NOW = helpers.NOW
SOURCE = MODULE / "execution/candidate_offpath_e.py"


def _edit_parameters(text: str, rate, kept) -> str:
    """Exactly what the coordinator does: edit the two parameter lines (and nothing else)."""
    text, n_rate = re.subn(r"^RATE = .*$", f"RATE = {rate!r}", text, flags=re.M)
    text, n_kept = re.subn(r"^KEPT_FAULTS = .*$", f"KEPT_FAULTS = {tuple(kept)!r}", text, flags=re.M)
    assert (n_rate, n_kept) == (1, 1)
    return text


def _exec(text: str):
    """The compiler source, run as a fresh module that believes it lives at SOURCE (its siblings and ROOT resolve there)."""
    module = types.ModuleType("otel_offpath_e_variant")
    module.__file__ = str(SOURCE)
    exec(compile(text, str(SOURCE), "exec"), module.__dict__)
    return module


def _variant(rate, kept, text: str = None):
    return _exec(_edit_parameters(SOURCE.read_text() if text is None else text, rate, kept))


def _measure(module) -> dict:
    document = module.derive_e_descriptor()
    plan = module._compile(document, 1)
    return {
        "descriptor": module.canonical_sha256(document), "plan1": module.canonical_sha256(plan), "runCount": module.TOTAL_RUNS,
        "minimumRemaining": module.MINIMUM_REMAINING_SECONDS, "window": module.RUN_WINDOW_HOURS,
        "concurrency": module.CONCURRENCY, "openFiles": module.GENERATOR_OPEN_FILES_MINIMUM,
    }


@pytest.fixture(scope="module")
def measured():
    return {key: _measure(_variant(*key)) for key in VARIANTS}


def _tree(tmp_path_factory, label: str, rate=None, kept=None):
    """A tree copy whose selector names E.  With ``rate`` and ``kept`` the two parameter lines are edited and the descriptor is
    regenerated by the compiler's own --emit-descriptor (the coordinator's switching procedure)."""
    root = helpers._copy_tree(
        tmp_path_factory.mktemp(label), selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n",
    )
    module = root / "modules/otel-demo"
    compiler = module / "execution/candidate_offpath_e.py"
    if rate is not None:
        compiler.write_text(_edit_parameters(compiler.read_text(), rate, kept))
        descriptor = root / "pipelines/campaigns/otel-offpath-e-v1.json"
        descriptor.unlink()
        subprocess.run([sys.executable, "-I", str(compiler), "--emit-descriptor", str(descriptor)], check=True, capture_output=True)
    loaded = types.SimpleNamespace(root=root, epoch=EPOCH)
    loaded.runtime = load(f"otel_{label}_runtime", module / "execution/candidate_runtime.py")
    loaded.remote = load(f"otel_{label}_remote", module / "execution/candidate_remote.py")
    loaded.setup = load(f"otel_{label}_setup", module / "execution/candidate_setup.py")
    loaded.terminal = load(f"otel_{label}_terminal", module / "validation/candidate_terminal.py")
    loaded.compiler = load(f"otel_{label}_compiler", compiler)
    return loaded


@pytest.fixture(scope="module")
def e_tree(tmp_path_factory):
    return _tree(tmp_path_factory, "offpath-e-tree")


@pytest.fixture(scope="module")
def e_package(e_tree, tmp_path_factory):
    return helpers._package(e_tree.runtime, e_tree.compiler, tmp_path_factory.mktemp("offpath-e-package"), window_hours=5)


def _cell_block(tree, package, regime, rate, tmp_path, block):
    return b_tests._contract(tree, package, regime, rate, tmp_path, block)



def _plan(attempt: int = 1):
    return p.compile_plan(p.load_descriptor(), attempt)


def _strip(timing, keys):
    return {key: value for key, value in timing.items() if key not in keys}


# ------------------------------------------------------------------------------------- 1. the plan, its pin, the 12 variants
def test_the_default_variant_is_pinned_20_cells_in_5_blocks_with_the_split_in_the_descriptor():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    cells = p.flatten_cells(plan)
    assert (p.RATE, p.KEPT_FAULTS) == DEFAULT
    assert p.canonical_sha256(document) == VARIANTS[DEFAULT]["descriptor"] == p.EXPECTED_DESCRIPTOR_SHA256
    assert p.canonical_sha256(plan) == VARIANTS[DEFAULT]["plan1"]
    assert len(cells) == plan["runCount"] == plan["uniqueRunCount"] == p.TOTAL_RUNS == 20
    assert [block["block"] for block in plan["blocks"]] == [1, 2, 3, 4, 5]
    assert [cell["ordinalPosition"] for cell in cells] == list(range(1, 21))
    assert {cell["runKey"]["studyEpoch"] for cell in cells} == {EPOCH} and plan["studyEpoch"] == EPOCH
    assert {cell["fault"] for cell in cells} == {None, *ALL3}
    assert not any("throttle" in cell["runKey"]["regime"] or "throttle" in str(cell["fault"]) for cell in cells)
    assert {cell["runKey"]["requestsPerSecond"] for cell in cells} == {25.0}
    # the split is declared in the descriptor (three places) and in the plan
    for split in (document["design"]["split"], document["schedule"]["split"], document["analysis"]["split"], plan["split"]):
        assert split["trainingBlocks"] == [1, 2, 3] and split["testBlocks"] == [4, 5] and split["declaredBeforeLaunch"] is True
    assert [(b["block"], b["split"]) for b in plan["blocks"]] == [(1, "training"), (2, "training"), (3, "training"), (4, "test"), (5, "test")]
    assert [(r["block"], r["split"]) for r in document["schedule"]["blocks"]] == [(b["block"], b["split"]) for b in plan["blocks"]]
    assert "decision 99" in document["analysis"]["passRule"] and "g = D(ledger alone) - D(S_6/h) > 0" in document["analysis"]["passRule"]
    assert "training blocks (1-3) only" in document["analysis"]["calibration"]
    assert document["design"]["blocks"] == 5 and document["design"]["cellsPerBlock"] == 4 and document["design"]["totalRuns"] == 20
    assert (p.MINIMUM_REMAINING_SECONDS, p.RUN_WINDOW_HOURS) == (20 * (211 + 300) + 900 + 600, 5) == (11720, 5)


def test_planted_defect_an_edited_descriptor_or_plan_is_refused_and_moves_the_pin():
    document = p.load_descriptor()
    plan = p.compile_plan(document, 1)
    for mutate in (
        lambda d: d["schedule"].update(seed=20261013),
        lambda d: d["timing"].update(duringFaultProbe=True),                                # H10 off
        lambda d: d["workload"].update(concurrency=4500),                                   # v1's concurrency
        lambda d: d["design"].update(rates=[50.0]),
        lambda d: d["design"]["split"].update(testBlocks=[3, 4, 5]),
        lambda d: d["schedule"]["blocks"][3].update(split="training"),
        lambda d: d["analysis"].update(passRule="g > 0"),
        lambda d: d.update(declaration="research/traffic-sweep/DECLARATION_PILOT_OFFPATH_V2_OTEL.md"),
        lambda d: d["workload"]["mix"]["tasks"][1].update(weight=9),
        lambda d: d["faultDesign"]["scenarios"].update({"productcatalog-cpu-throttle": {"service": "productcatalogservice"}}),
        lambda d: d["faultDesign"]["scenarios"]["fraud-pause"].update(service="accountingservice"),
    ):
        planted = copy.deepcopy(document)
        mutate(planted)
        assert p.canonical_sha256(planted) != VARIANTS[DEFAULT]["descriptor"]
        with pytest.raises(p.ProtocolError, match="differs from its generator"):
            p.validate_descriptor(planted)
    for mutate in (
        lambda q: q["blocks"][1]["cells"][0]["timing"].update(faultOnsetSeconds=61.0),
        lambda q: q["blocks"][0]["cells"].pop(),
        lambda q: q["blocks"][0]["cells"][0]["timing"].update(concurrency=4500),
        lambda q: q["blocks"][1]["cells"][1]["timing"].update(generatorOpenFilesMinimum=1024),
        lambda q: q.update(blocks=list(reversed(q["blocks"]))),
        lambda q: q["blocks"][0]["cells"][0]["runKey"].update(studyEpoch=V2),
        lambda q: q["blocks"][4].update(split="training"),
        lambda q: q["split"].update(trainingBlocks=[1, 2]),
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
    path = ROOT / "pipelines/campaigns/otel-offpath-e-v1.json"
    assert path.read_bytes() == p._pretty_bytes(p.derive_e_descriptor())
    document, base = p.load_descriptor(), repeat_c.load_descriptor()
    assert document["id"] == EPOCH and document["declaration"].startswith("research/traffic-sweep/DECLARATION_E_OTEL.md ")
    assert document["derivedFrom"]["studyEpoch"] == C and document["derivedFrom"]["descriptorCanonicalSha256"] == C_DESCRIPTOR_SHA256
    top, nested = v1._descriptor_differences(document, base)
    assert top == set(p.REPLACED_DESCRIPTOR_KEYS) - {"amendments"}
    assert nested == {key: set(value) for key, value in p.REPLACED_DESCRIPTOR_SUBKEYS.items()}
    for key in ("protocolGates", "containerHealthGuard", "postureRealization", "workflow"):
        assert document[key] == base[key], key
    assert document["schedule"]["seed"] == SEED != base["schedule"]["seed"]
    # planted: a descriptor that drifts from C's outside the declared keys is found
    drifted = copy.deepcopy(document)
    drifted["protocolGates"] = {**drifted["protocolGates"], "extra": True}
    _, nested = v1._descriptor_differences(drifted, base)
    assert "protocolGates" in nested and "protocolGates" not in p.REPLACED_DESCRIPTOR_SUBKEYS


def test_e_is_pilot_v2s_cell_the_mix_the_scenarios_and_the_criteria_fields_are_v2s():
    assert p.MIX == p2.MIX == p1.MIX
    document, v2 = p.load_descriptor(), p2.load_descriptor()
    # sized by the rate, so concurrency and generatorOpenFilesMinimum differ from v2's 50 req/s cells (asserted in the sizing test)
    for path in (("workload", "mix"), ("workload", "routeServices"), ("workload", "routeDerivation"), ("workload", "ledger"), ("workload", "warmup"),
                 ("workload", "readiness"), ("workload", "traceContext"), ("workload", "arrivals"),
                 ("faultDesign", "scenarios"), ("analysis", "manifestationCriterion"), ("analysis", "manifestationCriterionDefaults"),
                 ("analysis", "traceCompleteness"), ("groundTruth",), ("timing", "workloadMix"),
                 ("protocolGates",), ("containerHealthGuard",), ("postureRealization",), ("workflow",)):
        a, b = document, v2
        for key in path:
            a, b = a[key], b[key]
        assert a == b, path
    assert set(document["faultDesign"]["scenarios"]) == set(ALL3) and "productcatalog-cpu-throttle" not in document["faultDesign"]["scenarios"]
    assert p.MANIFESTATION_CRITERION == p2.MANIFESTATION_CRITERION and p.MANIFESTATION_CRITERION_DEFAULTS == p2.MANIFESTATION_CRITERION_DEFAULTS
    assert p.SCENARIOS == {k: v for k, v in p2.SCENARIOS.items() if k in ALL3}
    assert (p.POSTURES, p.DURING_FAULT_PROBE, p.FREEZE_STAMPS) == (p2.POSTURES, p2.DURING_FAULT_PROBE, p2.FREEZE_STAMPS) == (("full",), False, True)
    assert p.TELEMETRY_BACKEND_MEMORY_LIMIT_BYTES == p2.TELEMETRY_BACKEND_MEMORY_LIMIT_BYTES
    assert (p.CELL_OVERHEAD_SECONDS, p.SCHEDULE_SEED) == (p2.CELL_OVERHEAD_SECONDS, p2.SCHEDULE_SEED) == (300, SEED)
    # planted: a mix weight changed in E's source is found by the identity (and by the descriptor's own reviewed pin)
    text = SOURCE.read_text().replace('{"id": "browse_product", "weight": 10,', '{"id": "browse_product", "weight": 9,')
    assert text != SOURCE.read_text() and _exec(text).MIX != p2.MIX


def test_all_12_prepared_variants_have_the_pinned_digests_run_counts_and_budgets(measured):
    assert set(VARIANTS) == {(rate, kept) for rate in (25.0, 50.0) for kept in p.ALLOWED_KEPT_FAULTS} and len(VARIANTS) == 12
    assert set(p.EXPECTED_DESCRIPTOR_SHA256_BY_VARIANT) == set(VARIANTS)
    for key, expected in VARIANTS.items():
        rate, kept = key
        assert measured[key] == expected, key
        assert p.EXPECTED_DESCRIPTOR_SHA256_BY_VARIANT[key] == expected["descriptor"]
        assert expected["runCount"] == 5 * (1 + len(kept))
        assert expected["concurrency"] == int(2 * rate * 15) and expected["openFiles"] == expected["concurrency"] + 1024
    assert len({row["descriptor"] for row in measured.values()}) == 12 and len({row["plan1"] for row in measured.values()}) == 12
    # the budget fits the 4-5 h a campaign may take: even the 20-cell variant's minimum remaining is under 4 h and its window is 5 h
    for key, row in measured.items():
        assert row["minimumRemaining"] <= 4 * 3600 and row["window"] <= 5, key
        assert row["minimumRemaining"] + p.APPROVAL_TO_FIRST_MUTATION_SECONDS <= row["window"] * 3600, key
        assert row["minimumRemaining"] == row["runCount"] * (211 + 300) + 900 + 600


def test_planted_defect_a_variant_outside_the_table_or_with_a_stale_pin_cannot_be_loaded():
    for pin in (None, VARIANTS[(50.0, ALL3)]["descriptor"]):
        text = SOURCE.read_text()
        key = f"    ({DEFAULT[0]!r}, {DEFAULT[1]!r}):\n        {VARIANTS[DEFAULT]['descriptor']!r},\n"
        assert text.count(key) == 1
        replaced = text.replace(key, "" if pin is None else f"    ({DEFAULT[0]!r}, {DEFAULT[1]!r}):\n        {pin!r},\n")
        module = _exec(replaced)
        with pytest.raises(Exception, match="differs from the reviewed pin"):
            module.load_descriptor()


def test_the_digests_of_all_12_variants_are_identical_under_python39_isolated(tmp_path):
    python39 = Path("/usr/bin/python3")
    if not python39.exists():
        pytest.skip("no /usr/bin/python3 on this machine")
    version = subprocess.run([str(python39), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout
    if "(3, 9)" not in version:
        pytest.skip(f"/usr/bin/python3 is {version.strip()}, not 3.9")
    script = (
        "import json, re, sys, types\n"
        f"SRC = {str(SOURCE)!r}\n"
        f"VARIANTS = {sorted(VARIANTS)!r}\n"
        "text0 = open(SRC).read()\n"
        "out = {}\n"
        "for rate, kept in VARIANTS:\n"
        "    text = re.sub(r'^RATE = .*$', 'RATE = %r' % rate, text0, flags=re.M)\n"
        "    text = re.sub(r'^KEPT_FAULTS = .*$', 'KEPT_FAULTS = %r' % (kept,), text, flags=re.M)\n"
        "    m = types.ModuleType('v'); m.__file__ = SRC\n"
        "    exec(compile(text, SRC, 'exec'), m.__dict__)\n"
        "    d = m.derive_e_descriptor()\n"
        "    out['%r|%r' % (rate, kept)] = [m.canonical_sha256(d), m.canonical_sha256(m._compile(d, 1)), m.TOTAL_RUNS, m.MINIMUM_REMAINING_SECONDS, m.RUN_WINDOW_HOURS]\n"
        "print(json.dumps(out))\n"
    )
    result = subprocess.run([str(python39), "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-I", "-c", script],
                            capture_output=True, text=True, check=True)
    expected = {f"{rate!r}|{kept!r}": [row["descriptor"], row["plan1"], row["runCount"], row["minimumRemaining"], row["window"]]
                for (rate, kept), row in VARIANTS.items()}
    assert json.loads(result.stdout) == expected


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
        assert (timing["planRunCount"], timing["planMinimumRemainingSeconds"]) == (20, 11720)
    drifted = copy.deepcopy(p.flatten_cells(_plan(1))[0]["timing"])
    drifted["faultHoldSeconds"] = 30
    assert _strip(drifted, p.REPLACED_TIMING_KEYS | p.NEW_TIMING_KEYS) != _strip(
        repeat_c.cell_timing(NO_FAULT, 50.0, 1), p.REPLACED_TIMING_KEYS)


# ------------------------------------------------------------------------------------- 2. the split
def test_the_split_is_blocks_1_to_3_training_and_4_and_5_test_and_a_plan_with_another_split_is_refused_by_the_rule():
    assert (p.BLOCKS, p.TRAINING_BLOCKS, p.TEST_BLOCKS) == (5, (1, 2, 3), (4, 5))
    assert [p.block_split(n) for n in range(1, 6)] == ["training"] * 3 + ["test"] * 2
    with pytest.raises(p.ProtocolError, match="outside 1..5"):
        p.block_split(6)
    document = p.load_descriptor()
    # planted: a compiler whose split is blocks 1-2 / 3-5 (descriptor and plan generated with it, the pin bypassed) is refused by the rule
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "TRAINING_BLOCKS", (1, 2))
        patch.setattr(p, "TEST_BLOCKS", (3, 4, 5))
        wrong = p.derive_e_descriptor()
        assert wrong != document
        wrong_plan = p._compile(wrong, 1)
        patch.setattr(p, "validate_descriptor", lambda d: d)
        patch.setattr(p, "TRAINING_BLOCKS", (1, 2, 3))              # the epoch's rule, against a plan built with the other split
        patch.setattr(p, "TEST_BLOCKS", (4, 5))
        patch.setattr(p, "_compile", lambda d, a: wrong_plan)
        with pytest.raises(p.ProtocolError, match="split is not blocks"):
            p.validate_plan(wrong, wrong_plan)
    # planted: a split that leaves a block out or lists one twice is refused at generation, not only by the pin
    for training, test in (((1, 2, 3), (4,)), ((1, 2, 3), (3, 4, 5))):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(p, "TRAINING_BLOCKS", training)
            patch.setattr(p, "TEST_BLOCKS", test)
            with pytest.raises(p.ProtocolError, match="do not partition blocks 1..5"):
                p.derive_e_descriptor()


# ------------------------------------------------------------------------------------- 3. the run order per block
def test_every_block_runs_no_fault_then_the_off_path_pauses_in_the_seeded_order_then_the_frontend_pause():
    plan = _plan(1)
    document = p.load_descriptor()
    for block in plan["blocks"]:
        regimes = [cell["runKey"]["regime"] for cell in block["cells"]]
        assert regimes[0] == NO_FAULT and regimes[-1] == FRONTEND and set(regimes[1:3]) == {FRAUD, ACCOUNTING}, regimes
        pauses = [r for r in p.block_cells(block["block"]) if r["regime"] in (FRAUD, ACCOUNTING)]
        expected = quiet.fisher_yates(pauses, SEED, EPOCH, block["block"], "offpath-e-schedule-v1-group1")
        assert regimes[1:3] == [r["regime"] for r in expected]
        assert document["schedule"]["blocks"][block["block"] - 1]["order"][1:3] == [p.cell_label(r) for r in expected]
    # the seeded order is a function of the seed and the block: another seed gives other block orders
    other = [quiet.fisher_yates([r for r in p.block_cells(1) if r["regime"] in (FRAUD, ACCOUNTING)], 20261013, EPOCH, n, "offpath-e-schedule-v1-group1")
             for n in range(1, 6)]
    assert [tuple(r["regime"] for r in o) for o in other] != [tuple(c["runKey"]["regime"] for c in b["cells"][1:3]) for b in plan["blocks"]]


def _planted_order(order_of):
    """A compiler whose block order is ``order_of(cells)``, its descriptor and plan generated with it and the pin bypassed."""
    document = p.load_descriptor()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "block_order", lambda block: order_of(p.block_cells(block)))
        wrong = p.derive_e_descriptor()
        wrong_plan = p._compile(wrong, 1)
        patch.setattr(p, "validate_descriptor", lambda d: d)
        patch.setattr(p, "_compile", lambda d, a: wrong_plan)
        p.validate_plan(wrong, wrong_plan)
    assert wrong != document


@pytest.mark.parametrize("name,order_of", [
    ("frontend pause first", lambda cells: [c for c in cells if c["regime"] == FRONTEND] + [c for c in cells if c["regime"] != FRONTEND]),
    ("no-fault cell last", lambda cells: [c for c in cells if c["regime"] != NO_FAULT] + [c for c in cells if c["regime"] == NO_FAULT]),
    ("frontend pause before the off-path pauses",
     lambda cells: [c for c in cells if c["regime"] == NO_FAULT] + [c for c in cells if c["regime"] == FRONTEND]
     + [c for c in cells if c["regime"] in (FRAUD, ACCOUNTING)]),
    ("off-path pause before the no-fault cell",
     lambda cells: [c for c in cells if c["regime"] == FRAUD] + [c for c in cells if c["regime"] == NO_FAULT]
     + [c for c in cells if c["regime"] in (ACCOUNTING, FRONTEND)]),
])
def test_planted_defect_a_block_order_other_than_nofault_offpath_frontend_is_refused_by_the_rule(name, order_of):
    with pytest.raises(p.ProtocolError, match="does not run its no-fault cell, then the off-path pauses, then the frontend pause"):
        _planted_order(order_of)


def test_planted_defect_a_block_that_loses_or_repeats_a_cell_is_refused():
    with pytest.raises(p.ProtocolError):
        _planted_order(lambda cells: [c for c in cells if c["regime"] != ACCOUNTING])
    with pytest.raises(p.ProtocolError):
        _planted_order(lambda cells: cells + [cells[0]])


# ------------------------------------------------------------------------------------- 4. onsets: C's strata rule over the 5 blocks
def _strata(regime: str, rate: float, offsets) -> list:
    inter_arrival = 1.0 / rate
    return [min(4, int(offset / (inter_arrival / 5))) for offset in offsets]


def test_the_onsets_take_cs_five_strata_one_per_block_for_every_regime_and_the_nofault_pseudo_onset():
    assert p.ONSET_STRATA == p.BLOCKS == 5
    for regime in (NO_FAULT, FRAUD, ACCOUNTING, FRONTEND):
        offsets = [p.onset_phase_offset(regime, 50.0, block) for block in range(1, 6)]
        assert offsets == [quiet.stratified_onset_offset(SEED, EPOCH, 5, regime, 50.0, block) for block in range(1, 6)]
        assert sorted(_strata(regime, 50.0, offsets)) == [0, 1, 2, 3, 4], (regime, offsets)       # a permutation: each stratum exactly once
        assert all(0 <= o < 1 / 50.0 for o in offsets)
    cells = p.flatten_cells(_plan(1))
    for cell in cells:
        timing, key = cell["timing"], cell["runKey"]
        assert timing["faultOnsetPhaseOffsetSeconds"] == p.onset_phase_offset(key["regime"], key["requestsPerSecond"], key["block"])
        assert timing["faultOnsetSeconds"] == round(60 + timing["faultOnsetPhaseOffsetSeconds"], 6) == timing["scoredWindowSeconds"][0]
    with pytest.raises(p.ProtocolError, match="outside 1..5"):
        p.onset_phase_offset(FRAUD, 50.0, 6)
    # planted: v2's one-stratum rule (every block draws the same stratum) fails the permutation check, and C's own 3 strata would not tile 5 blocks
    plant = [quiet.stratified_onset_offset(SEED, EPOCH, 1, FRAUD, 50.0, 1) for _ in range(5)]
    assert sorted(_strata(FRAUD, 50.0, plant)) != [0, 1, 2, 3, 4]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "ONSET_STRATA", 3)
        with pytest.raises(Exception, match="outside 1..3"):
            p.onset_phase_offset(FRAUD, 50.0, 4)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "ONSET_STRATA", 1)
        planted = p.derive_e_descriptor()
        assert p.canonical_sha256(planted) != VARIANTS[DEFAULT]["descriptor"] and planted["timing"]["faultOnsetStrata"] == 1
        with pytest.raises(Exception, match="outside 1..1"):
            p._compile(planted, 1)
    # the seed moves every onset
    before = [p.onset_phase_offset(FRAUD, 50.0, b) for b in range(1, 6)]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(p, "SCHEDULE_SEED", 20261013)
        assert [p.onset_phase_offset(FRAUD, 50.0, b) for b in range(1, 6)] != before


# ------------------------------------------------------------------------------------- 5. the two parameters
def test_the_two_parameters_are_two_module_constants_on_one_line_each_and_nothing_else_moves_between_variants(measured):
    text = SOURCE.read_text()
    assert len(re.findall(r"^RATE = .*$", text, flags=re.M)) == 1 and len(re.findall(r"^KEPT_FAULTS = .*$", text, flags=re.M)) == 1
    assert p.ALLOWED_RATES == (25.0, 50.0) and p.ALLOWED_KEPT_FAULTS == (
        ALL3, ("fraud-pause", "frontend-pause"), ("accounting-pause", "frontend-pause"), ("fraud-pause", "accounting-pause"),
        ("fraud-pause",), ("accounting-pause",))
    assert all(set(kept) & {"fraud-pause", "accounting-pause"} for kept in p.ALLOWED_KEPT_FAULTS)          # at least one off-path pause
    # the variant's regimes, cells and scenarios follow KEPT_FAULTS and its sizing follows RATE (the rest is the epoch's)
    for (rate, kept), row in measured.items():
        module = _variant(rate, kept)
        regimes = [p.REGIME_OF_FAULT[f] for f in kept]
        assert module.REGIMES == (NO_FAULT, *regimes) and set(module.SCENARIOS) == set(kept) and module.RATES == (rate,)
        assert module.BLOCKS == 5 and (module.TRAINING_BLOCKS, module.TEST_BLOCKS) == ((1, 2, 3), (4, 5)) and module.SCHEDULE_SEED == SEED
        document = module.derive_e_descriptor()
        plan = module._compile(document, 1)
        cells = module.flatten_cells(plan)
        assert len(cells) == row["runCount"] and {c["runKey"]["requestsPerSecond"] for c in cells} == {rate}
        assert {c["runKey"]["regime"] for c in cells} == {NO_FAULT, *regimes}
        assert [r["fault"] for r in document["design"]["regimes"]] == [None, *kept] and document["design"]["keptFaults"] == list(kept)
        # a single off-path pause has no seeded order to draw; two have one draw per block, in every variant that keeps both
        assert all(len(b["cells"]) == 1 + len(kept) for b in plan["blocks"])


@pytest.mark.parametrize("rate,kept,message", [
    (100.0, ALL3, "RATE 100.0 is not one of"),
    (37.5, ALL3, "RATE 37.5"),
    (50, ALL3, "RATE 50 is not one of"),                                   # an int: the rate token and every digest take a float
    (50.0, ("frontend-pause",), "KEPT_FAULTS"),                           # no off-path pause
    (50.0, ("accounting-pause", "fraud-pause"), "KEPT_FAULTS"),            # not the canonical order
    (50.0, ("fraud-pause", "productcatalog-cpu-throttle"), "KEPT_FAULTS"),
    (50.0, ["fraud-pause"], "KEPT_FAULTS"),                                # a list, not a tuple
    (50.0, (), "KEPT_FAULTS"),
])
def test_planted_defect_a_rate_or_fault_set_outside_the_prepared_ones_is_refused_at_import(rate, kept, message):
    text = SOURCE.read_text()
    text = re.sub(r"^RATE = .*$", f"RATE = {rate!r}", text, flags=re.M)
    text = re.sub(r"^KEPT_FAULTS = .*$", f"KEPT_FAULTS = {kept!r}", text, flags=re.M)
    with pytest.raises(Exception, match=message):
        _exec(text)


def test_changing_either_parameter_changes_the_digests_and_the_run_count(measured):
    base = measured[DEFAULT]
    for key, row in measured.items():
        if key != DEFAULT:
            assert row["descriptor"] != base["descriptor"] and row["plan1"] != base["plan1"], key
    assert measured[(50.0, ALL3)]["runCount"] == base["runCount"] and measured[(50.0, ALL3)]["concurrency"] != base["concurrency"]
    assert measured[(50.0, ("fraud-pause",))]["runCount"] == 10 != base["runCount"]
    # planted: the rate edited without regenerating the descriptor is refused ("differs from its generator"), not silently re-pinned
    module = _variant(50.0, ALL3)
    with pytest.raises(Exception, match="differs from its generator"):
        module.load_descriptor()


@pytest.fixture(scope="module")
def variant_trees(tmp_path_factory):
    """The coordinator's switching procedure on tree copies: the two lines edited, the descriptor regenerated with --emit-descriptor."""
    return {
        key: _tree(tmp_path_factory, "offpath-e-var%d%s" % (int(key[0]), "".join(f[0] for f in key[1])), *key)
        for key in ((25.0, ("fraud-pause",)), (50.0, ("accounting-pause", "frontend-pause")), (25.0, ("fraud-pause", "accounting-pause")))
    }


@pytest.mark.parametrize("key", [
    (25.0, ("fraud-pause",)), (50.0, ("accounting-pause", "frontend-pause")), (25.0, ("fraud-pause", "accounting-pause"))])
def test_the_switching_procedure_gives_the_pinned_digests_and_the_gate_chain_derives_the_variants_cells(variant_trees, tmp_path_factory, key):
    tree = variant_trees[key]
    expected = VARIANTS[key]
    assert (tree.compiler.RATE, tree.compiler.KEPT_FAULTS) == key
    document = tree.compiler.load_descriptor()                       # the regenerated file passes the generator check and the table pin
    assert tree.compiler.canonical_sha256(document) == expected["descriptor"]
    assert tree.compiler.canonical_sha256(tree.compiler.compile_plan(document, 1)) == expected["plan1"]
    package = helpers._package(tree.runtime, tree.compiler, tmp_path_factory.mktemp("offpath-e-var-package"), window_hours=expected["window"])
    runtime, remote = tree.runtime, tree.remote
    assert runtime.STUDY_EPOCH == EPOCH
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (
        expected["runCount"], expected["minimumRemaining"], expected["window"])
    assert f"study={EPOCH} " in package.gate_plan["typedApproval"] and f" runs={expected['runCount']} " in package.gate_plan["typedApproval"]
    assert package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == expected["minimumRemaining"]
    assert remote.SAFE_NAME.fullmatch(package.gate_plan["binding"]["compose"]["project"])
    contracts = runtime.execution_package(package)["cells"]
    assert len(contracts) == expected["runCount"]
    assert {c["workload"]["concurrency"] for c in contracts} == {expected["concurrency"]}
    assert {c["timing"]["serviceMemoryLimitBytes"]["frontendproxy"] for c in contracts} == {256 * 1024 ** 2}
    assert {c["fault"]["scenario"] for c in contracts} == {None, *key[1]}
    assert all("docker-events.json" in c["requiredArtifacts"] for c in contracts if c["fault"]["scenario"] is not None)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (EPOCH,))
        cells, *_ = remote.validate_package(runtime.execution_package(package), clock=lambda: NOW)
    assert len(cells) == expected["runCount"] and remote.expected_minimum_remaining(runtime.execution_package(package)) == expected["minimumRemaining"]


def test_planted_defect_a_variant_tree_with_the_rate_edited_but_the_descriptor_not_regenerated_is_refused(tmp_path_factory):
    root = helpers._copy_tree(tmp_path_factory.mktemp("offpath-e-stale"), selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    compiler = root / "modules/otel-demo/execution/candidate_offpath_e.py"
    compiler.write_text(_edit_parameters(compiler.read_text(), 25.0, ("fraud-pause",)))
    module = load("otel_offpath_e_stale_compiler", compiler)
    with pytest.raises(module.ProtocolError, match="differs from its generator"):
        module.load_descriptor()


def test_the_variant_in_a_fraud_only_tree_executes_a_cell_end_to_end_at_25_req_per_second(variant_trees, tmp_path_factory, monkeypatch):
    tree = variant_trees[(25.0, ("fraud-pause",))]
    package = helpers._package(tree.runtime, tree.compiler, tmp_path_factory.mktemp("offpath-e-fraud25-package"), window_hours=3)
    base = tmp_path_factory.mktemp("offpath-e-fraud25-cell")
    contract = _cell_block(tree, package, FRAUD, 25.0, base, 4)
    assert contract["studyEpoch"] == EPOCH and contract["runKey"]["block"] == 4
    receipt, target, limits = v1._run(tree, contract, monkeypatch)
    assert receipt["state"] == "valid", receipt["error"]
    assert limits.calls == [(1774, 524288)] and v1._CappedPool.asked.count(750) == 2
    health = v1._read(contract, "container-health.json")
    assert {r["service"]: r["after"]["memory"] for r in health["memoryLimitUpdates"]} == {"frontendproxy": 256 * 1024 ** 2, "otelcol": 1024 ** 3, "jaeger": 1024 ** 3}
    report = v1._validate(tree, Path(contract["remoteArtifactRoot"]), contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    assert json.loads((Path(contract["remoteArtifactRoot"]) / "docker-events.json").read_text())["service"] == "frauddetectionservice"


# ------------------------------------------------------------------------------------- 6. the sizing
def test_the_generator_and_proxy_are_sized_by_the_rate_and_only_the_proxy_and_the_telemetry_backend_have_a_limit(measured):
    for cell in p.flatten_cells(_plan(1)):
        timing = cell["timing"]
        assert timing["concurrency"] == 750 >= 2 * 25 * timing["requestTimeoutSeconds"]
        assert timing["generatorOpenFilesMinimum"] == 750 + 1024
        assert timing["serviceMemoryLimitBytes"] == {"frontendproxy": 256 * 1024 ** 2, "otelcol": 1024 ** 3, "jaeger": 1024 ** 3}
    # the literal rule at 25 req/s is 128 MiB; the floor at C's own 256 MiB (the sweep's value, the pilot v2's) is what the cells get
    assert p.FRONTENDPROXY_RULE_BYTES == 112_500_000 and p.FRONTENDPROXY_RULE_POWER_OF_TWO_BYTES == 128 * 1024 ** 2
    assert p.FRONTENDPROXY_MEMORY_LIMIT_BYTES == 256 * 1024 ** 2 and p.CONCURRENCY == 750
    high = _variant(50.0, ALL3)
    assert high.FRONTENDPROXY_RULE_BYTES == 225_000_000 and high.FRONTENDPROXY_RULE_POWER_OF_TWO_BYTES == 256 * 1024 ** 2
    assert high.FRONTENDPROXY_MEMORY_LIMIT_BYTES == 256 * 1024 ** 2 and high.CONCURRENCY == 1500
    sut = set(json.loads((MODULE / "postures/catalog.json").read_text())["applicationServices"]) - {"frontendproxy"}
    assert not set(p.SERVICE_MEMORY_LIMIT_BYTES) & sut                       # every SUT limit stays upstream's
    rows = {r["service"]: r for r in p.load_descriptor()["sutDeviations"] if r["setting"] == "memory limit (HostConfig.Memory)"}
    assert set(rows) == {"frontendproxy", "otelcol", "jaeger"}
    # planted: a C-sized (300) generator is refused, and a SUT limit (productcatalogservice) smuggled in is found
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
    # planted: the 25 req/s sizing kept at 50 req/s (the rate edited, the concurrency left) is a different descriptor, found by the pin
    text = _edit_parameters(SOURCE.read_text(), 50.0, ALL3).replace(
        "CONCURRENCY = int(math.ceil(sweep.CONCURRENCY_MARGIN * RATE * REQUEST_TIMEOUT_SECONDS))", "CONCURRENCY = 750")
    assert _measure(_exec(text))["descriptor"] != VARIANTS[(50.0, ALL3)]["descriptor"]


# ------------------------------------------------------------------------------------- 7. no run-ID reuse
def _ran_run_ids() -> dict:
    compilers = {SWEEP: sweep, QUIET: quiet, REPEAT: p.repeat_c.repeat_b, C: repeat_c, LOAD: v1.load_pilot, V1: p1, V2: p2}
    ids = {}
    for epoch, attempts in RAN.items():
        compiler = compilers[epoch]
        document = compiler.load_descriptor()
        for attempt in attempts:
            ids[(epoch, attempt)] = {cell["runId"] for cell in compiler.flatten_cells(compiler.compile_plan(document, attempt))}
    return ids


def test_no_run_id_of_any_variant_equals_one_of_an_earlier_epoch_including_pilot_v2_and_the_planted_reuse_is_found(measured):
    ran = _ran_run_ids()
    assert len(ran[(V2, 1)]) == 8 and len(ran[(V1, 1)]) == 10
    for attempt in (1, 2, 3):
        ids = {cell["runId"] for cell in p.flatten_cells(_plan(attempt))}
        assert len(ids) == 20 and v1._reused(ids, ran) == {}
    for key in VARIANTS:
        module = _variant(*key)
        for attempt in (1, 2):
            ids = {cell["runId"] for cell in module.flatten_cells(module._compile(module.derive_e_descriptor(), attempt))}
            assert len(ids) == VARIANTS[key]["runCount"] and v1._reused(ids, ran) == {}, (key, attempt)
    # planted: E under pilot v2's epoch id reuses v2's run IDs (blocks 1 of the four regimes at 25 req/s), and the check finds them
    text = SOURCE.read_text().replace(f'EPOCH = "{EPOCH}"', f'EPOCH = "{V2}"')
    assert text != SOURCE.read_text()
    module = _variant(25.0, ALL3, text)
    reused = {cell["runId"] for cell in module.flatten_cells(module._compile(module.derive_e_descriptor(), 1))}
    assert v1._reused(reused, ran) == {(V2, 1): 4}
    # planted: E under v1's epoch id at 50 req/s ... v1 ran 100 and 150 req/s, so nothing is reused there (the check is not trivially true)
    module = _variant(50.0, ALL3, SOURCE.read_text().replace(f'EPOCH = "{EPOCH}"', f'EPOCH = "{V1}"'))
    assert v1._reused({c["runId"] for c in module.flatten_cells(module._compile(module.derive_e_descriptor(), 1))}, ran) == {}


def test_e_attempt_1_and_pilot_v2_attempt_1_are_recorded_spent_in_the_adapter():
    # 2026-10-13: E attempt 1 ran (harness 6a5c2a9, plan 503bf014, 20/20 valid, fetched and byte-verified 357/357).
    table = v1._spent_table_in_source()
    assert set(table[EPOCH]) == {1} and "6a5c2a9" in table[EPOCH][1] and "503bf014" in table[EPOCH][1]
    assert VARIANTS[DEFAULT]["plan1"].startswith("503bf014")                         # the plan that ran
    assert set(table[V1]) == {1}
    assert set(table[V2]) == {1} and "ff29b93" in table[V2][1] and "a929b4d9" in table[V2][1]


# ------------------------------------------------------------- 8. the epoch in the runtime, the gate chain and the target (NOT activated)
def test_e_is_terminal_the_selector_and_the_tombstone_name_campaign_f_not_e():
    selector = json.loads((MODULE / "execution/study-epoch.json").read_text())
    assert selector == {"schemaVersion": 1, "studyEpoch": "otel-offpath-f-v1"}
    for name in ("candidate_remote.py", "candidate_setup.py"):
        tree_ = ast.parse((MODULE / "execution" / name).read_text())
        values = [ast.literal_eval(n.value) for n in tree_.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "ADMITTED_STUDY_EPOCHS"]
        assert values == [("otel-offpath-f-v1",)], name
    assert EPOCH not in (MODULE / "execution/study-epoch.json").read_text()


def test_a_selector_naming_e_activates_it_in_every_reader_and_the_gate_chain_derives_20_cells(e_tree, e_package, tmp_path):
    runtime, remote = e_tree.runtime, e_tree.remote
    assert runtime.STUDY_EPOCH == EPOCH and runtime.is_sweep_epoch() is True
    assert (runtime.RUN_COUNT, runtime.MINIMUM_REMAINING_SECONDS, runtime.RUN_WINDOW_HOURS) == (20, 11720, 5)
    assert set(runtime.CONTROLLER_PATHS) == helpers.FROZEN_CONTROLLER_KEYS | E_CONTROLLER_KEYS
    assert runtime.CONTROLLER_PATHS["candidate-compiler"] == "modules/otel-demo/execution/candidate_offpath_e.py"
    assert runtime.DESCRIPTOR == e_tree.root / "pipelines/campaigns/otel-offpath-e-v1.json"
    assert e_tree.setup.controller_paths(EPOCH) == runtime.CONTROLLER_PATHS
    assert runtime.timed_cell_timing_keys(True) == runtime.SWEEP_TIMING_KEYS | {
        "duringFaultProbe", "freezeStamps", "generatorOpenFilesMinimum", "workloadMix"}
    assert EPOCH in remote.REPEAT_STUDY_EPOCHS and EPOCH in remote.TIMED_STUDY_EPOCHS and V2 in remote.REPEAT_STUDY_EPOCHS
    binding = e_package.gate_plan["binding"]
    assert f"study={EPOCH} " in e_package.gate_plan["typedApproval"] and " runs=20 " in e_package.gate_plan["typedApproval"]
    assert e_package.gate_run["binding"]["minimumRemainingAtFirstMutationSeconds"] == 11720
    assert binding["compose"]["project"] == "otel_candidate_v4_otel_offpath_e_v1" and remote.SAFE_NAME.fullmatch(binding["compose"]["project"])
    earlier = (SWEEP, QUIET, REPEAT, C, LOAD, V1, V2)
    other = (["/home/stig/observability-placement-candidate-v4-runs/" + e for e in earlier]
             + ["/home/stig/observability-placement-candidate-v4-runs/.setup-" + e for e in earlier]
             + ["/home/stig/observability-placement-candidate-v4-otel-srv6/" + e + "-" for e in earlier])
    for key in ("remoteArtifactRoot", "releaseRoot", "remoteSourceRoot", "repositoryRoot"):
        assert EPOCH in binding[key] and not any(binding[key].startswith(path) for path in other), key
    document = runtime.execution_package(e_package)
    assert document["runCount"] == 20 and len(document["cells"]) == 20
    for contract, cell in zip(document["cells"], e_package.bindings.cells):
        assert contract["timing"] == cell["timing"] and runtime.sweep_cell_timing(contract) == cell["timing"]
        assert ("docker-events.json" in contract["requiredArtifacts"]) is (contract["fault"]["action"] == "pause")
        assert contract["workload"]["concurrency"] == 750 and contract["fault"]["service"] != "productcatalogservice"
    assert sum("docker-events.json" in c["requiredArtifacts"] for c in document["cells"]) == 15
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (EPOCH,))
        cells, *_ = remote.validate_package(document, clock=lambda: NOW)
    assert len(cells) == 20 and remote.expected_minimum_remaining(document) == 11720
    for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
        sys.modules.pop(name, None)
    try:
        adapter = load("otel_offpath_e_tree_adapter", e_tree.root / "modules/otel-demo/execution/candidate_runtime_adapter.py")
        assert adapter.CAMPAIGN_ID == adapter.STUDY_EPOCH == EPOCH and set(adapter.SPENT_ATTEMPTS) == {1}      # attempt 1 ran and is spent
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv(adapter.pilot.ATTEMPT_ENVIRONMENT, "1")
            with pytest.raises(adapter.runtime.GateError, match="attempt 1 is spent"):
                adapter.inspect_campaign(tmp_path / "plan-a1", "a" * 40)
            patch.delitem(adapter.SPENT_ATTEMPTS, 1)
            bindings = adapter.inspect_campaign(tmp_path / "plan", "a" * 40)
        assert len(bindings.run_ids) == 20 and bindings.plan_sha256 == VARIANTS[DEFAULT]["plan1"]
    finally:
        for name in ("otel_candidate_runtime_orchestrator", "otel_candidate_pilot_compiler"):
            sys.modules.pop(name, None)


def test_planted_defect_a_selector_naming_e_without_its_controller_set_or_family_membership_is_refused(tmp_path_factory, e_tree, e_package):
    root = helpers._copy_tree(tmp_path_factory.mktemp("offpath-e-no-paths"), selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    runtime_path = root / "modules/otel-demo/execution/candidate_runtime.py"
    text = runtime_path.read_text()
    marker = '    OFFPATH_E_STUDY_EPOCH: {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_e.py",'
    assert text.count(marker) == 1
    runtime_path.write_text(text.replace(marker, '    "otel-offpath-e-v0": {\n        "candidate-compiler": "modules/otel-demo/execution/candidate_offpath_e.py",'))
    with pytest.raises(Exception, match="names no declared non-frozen epoch"):
        load("otel_offpath_e_no_paths_runtime", runtime_path)
    remote = e_tree.remote
    cells = e_tree.runtime.execution_package(e_package)["cells"]
    fault = next(x for x in cells if x["fault"]["scenario"] == "fraud-pause")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(remote, "REPEAT_STUDY_EPOCHS", (REPEAT, C, LOAD, V1, V2))
        with pytest.raises(remote.RuntimeFailure, match="H10"):
            remote.require_harness_flags_consistent(fault)


# ------------------------------------------------------------------------------------- 9. every regime, end to end (default variant, 25 req/s)
CELL_KEYS = [(NO_FAULT, 1), (FRAUD, 4), (ACCOUNTING, 5), (FRONTEND, 2)]


@pytest.fixture(scope="module")
def cells(e_tree, e_package, tmp_path_factory):
    """One valid cell per regime at 25 req/s (4,500 requests): a training block's no-fault and frontend pause, a test block's fraud and accounting pause."""
    out = {}
    for regime, block in CELL_KEYS:
        with pytest.MonkeyPatch.context() as patch:
            base = tmp_path_factory.mktemp(f"offpath-e-cell-{regime}-{block}")
            contract = _cell_block(e_tree, e_package, regime, 25.0, base, block)
            assert contract["studyEpoch"] == EPOCH
            receipt, target, limits = v1._run(e_tree, contract, patch, pool_cap=2048 if regime == FRONTEND else 256)
            assert receipt["state"] == "valid", (regime, block, receipt["error"])
            out[(regime, block)] = types.SimpleNamespace(
                contract=contract, root=Path(contract["remoteArtifactRoot"]), target=target, limits=limits,
                asked=list(v1._CappedPool.asked))
    return out


@pytest.mark.parametrize("key", CELL_KEYS)
def test_run_cell_executes_an_e_cell_and_the_terminal_accepts_it(e_tree, cells, key):
    cell = cells[key]
    contract, root, target = cell.contract, cell.root, cell.target
    regime, block = key
    assert contract["runKey"]["block"] == block and contract["timing"]["faultOnsetSeconds"] == p.cell_timing(regime, 25.0, block)["faultOnsetSeconds"]
    assert cell.limits.calls == [(1774, 524288)] and cell.asked.count(750) == 2
    assert {path.name for path in root.iterdir()} == set(contract["requiredArtifacts"])
    ledger = json.loads((root / "request-ledger.json").read_text())
    assert ledger["kind"] == "otel-demo-mix-ledger-v1" and ledger["offered"] == 4500 == len(ledger["requests"]) and ledger["concurrency"] == 750
    health = v1._read(contract, "container-health.json")
    assert health["valid"] is True and {r["service"] for r in health["memoryLimitUpdates"]} == {"frontendproxy", "otelcol", "jaeger"}
    report = v1._validate(e_tree, root, contract)
    assert report["state"] == "valid" and report["protocolGates"]["valid"] is True
    assert not any(argv[:2] == ["docker", "update"] and "--cpus" in argv for argv in target.commands)
    if contract["fault"]["scenario"] is None:
        return
    intervention = v1._read(contract, "intervention.json")
    assert intervention["throttle"] is None and intervention["manifested"] is True and intervention["freeze"]["stampCheck"]["status"] == "ok"
    assert b_tests._probes_inside_the_fault(target, contract) == []                         # H10
    record = json.loads((root / "docker-events.json").read_text())
    assert record["service"] == contract["fault"]["service"] and record["verdict"]["status"] == "ok"


def test_each_kept_fault_manifests_by_the_pilots_declared_criterion_on_the_fake_cells(cells):
    quiet_stats = v1.statistics_of(cells[(NO_FAULT, 1)].root, cells[(NO_FAULT, 1)].contract)
    for fault, regime, block in (("fraud-pause", FRAUD, 4), ("accounting-pause", ACCOUNTING, 5), ("frontend-pause", FRONTEND, 2)):
        stats = v1.statistics_of(cells[(regime, block)].root, cells[(regime, block)].contract)
        assert v1.verdict(fault, stats, quiet_stats) == "manifests", (fault, stats)


def test_planted_defect_a_consumer_that_ignores_its_pause_does_not_manifest_in_a_test_block(e_tree, e_package, cells, tmp_path, monkeypatch):
    contract = _cell_block(e_tree, e_package, FRAUD, 25.0, tmp_path, 5)
    receipt, _, _ = v1._run(e_tree, contract, monkeypatch, consumers_ignore_pause=True)
    assert receipt["state"] == "valid", receipt["error"]
    stats = v1.statistics_of(Path(contract["remoteArtifactRoot"]), contract)
    quiet_stats = v1.statistics_of(cells[(NO_FAULT, 1)].root, cells[(NO_FAULT, 1)].contract)
    assert v1.verdict("fraud-pause", stats, quiet_stats) == "does not manifest"


# ------------------------------------------------------------------------------------- 10. the rendered tree
@pytest.fixture(scope="module")
def materialized(tmp_path_factory):
    out = {}
    for label, epoch in (("e", EPOCH), ("v2", V2), ("c", C)):
        tree = helpers._copy_tree(tmp_path_factory.mktemp("materialize-e-" + label),
                                  selector=json.dumps({"schemaVersion": 1, "studyEpoch": epoch}) + "\n")
        out[label] = tree / "out"
        out[label + "-digest"] = b_tests._materialize(tree, out[label])
    return out


def test_e_renders_the_pilots_tree_collector_sampler_off_and_proxy_retention(materialized):
    materialize = load("otel_offpath_e_materialize_module", MODULE / "materialize.py")
    assert EPOCH in materialize.COLLECTOR_LOG_SAMPLING_OFF_EPOCHS and EPOCH in materialize.FRONTENDPROXY_LOG_RETENTION_EPOCHS
    assert b_tests._log_sampling_enabled(b_tests._collector_config(materialized["e"])) is False
    assert materialized["e-digest"] == materialized["v2-digest"] != materialized["c-digest"]
    assert v1._overlay(materialized["e"])["services"]["frontendproxy"]["logging"] == {
        "driver": "json-file", "options": {"max-size": "4g", "max-file": "1"}}


def test_planted_defect_without_e_in_the_sampling_tuple_the_collector_keeps_its_log_sampler(tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    marker = '\n    "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, '\n    "otel-offpath-pilot-v2")'))
    b_tests._materialize(tree, tree / "out")
    assert b_tests._log_sampling_enabled(b_tests._collector_config(tree / "out")) is None


def test_planted_defect_without_e_in_the_retention_tuple_frontendproxy_keeps_upstreams_rotation(tmp_path):
    tree = helpers._copy_tree(tmp_path / "tree", selector=json.dumps({"schemaVersion": 1, "studyEpoch": EPOCH}) + "\n")
    script = tree / "modules/otel-demo/materialize.py"
    text = script.read_text()
    marker = 'FRONTENDPROXY_LOG_RETENTION_EPOCHS = ("otel-load-pilot-v1", "otel-offpath-pilot-v1", "otel-offpath-pilot-v2", "otel-offpath-e-v1", "otel-offpath-f-v1")'
    assert text.count(marker) == 1
    script.write_text(text.replace(marker, 'FRONTENDPROXY_LOG_RETENTION_EPOCHS = ("otel-load-pilot-v1", "otel-offpath-pilot-v1", "otel-offpath-pilot-v2")'))
    b_tests._materialize(tree, tree / "out")
    assert "logging" not in v1._overlay(tree / "out")["services"]["frontendproxy"]


# ------------------------------------------------------------------------------------- 11. the 3.9 floor
E_TARGET_FILES = (
    "modules/otel-demo/execution/candidate_offpath_e.py",
    "modules/otel-demo/execution/candidate_remote.py",
    "modules/otel-demo/execution/candidate_runtime.py",
    "modules/otel-demo/execution/candidate_setup.py",
    "modules/otel-demo/execution/candidate_runtime_adapter.py",
    "modules/otel-demo/materialize.py",
)


@pytest.mark.parametrize("relative", E_TARGET_FILES)
def test_touched_target_files_parse_as_python39_and_read_no_name_bound_nowhere(relative):
    tree_ = ast.parse((ROOT / relative).read_text(), feature_version=(3, 9))
    assert b_tests._unbound_names(tree_) == []
    assert any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names) for n in tree_.body)
