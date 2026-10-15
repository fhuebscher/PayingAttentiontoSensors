"""Generic campaign gates (src/obsplacement/protocol_gates.py; research/protocol/GATES.md).

Each gate's planted defect must flip it; G1 counts scheduled opportunities, not completions; the module stays inside
the hosts' Python 3.9 floor; vendored copies are byte-identical; and a static scan lists the count literals the three
harness validators still carry (xfail: it documents today's state until the wiring commits remove them).
"""
import ast
import copy
import hashlib
import pathlib
import shutil
import subprocess
import sys

import pytest

from obsplacement import protocol_gates as pg

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "obsplacement" / "protocol_gates.py"


def by_gate(result):
    return {v["gate"]: v for v in result["verdicts"]}


def campaign(defect=None):
    cells, profile, firings = pg.synthetic_campaign(defect)
    return cells, profile, firings


# --------------------------------------------------------------------------- self-check and planted defects

def test_self_check_passes():
    lines = []
    assert pg.self_check(out=lines), "\n".join(lines)


@pytest.mark.parametrize("gate", ["P0", "R1", "R2", "F1", "G1", "G2", "G3", "G4"])
def test_a_dead_gate_makes_the_self_check_fail(gate):
    """Guard the guard: a gate forced to 'pass' must be reported as a miss."""
    assert not pg.self_check(broken=[gate])


def test_every_gate_has_a_planted_defect():
    planted = {gate.split(":")[0] for gate, _, _ in pg.PLANTED.values()}
    assert planted == {"P0", "R1", "R2", "F1", "G1", "G2", "G3", "G4"}


@pytest.mark.parametrize("defect", sorted(pg.PLANTED))
def test_planted_defect_flips_its_gate(defect):
    gate, index, _ = pg.PLANTED[defect]
    cells, profile, firings = campaign(defect)
    E = pg.evaluate_campaign(cells, profile, firings)
    if gate.startswith("G3"):
        assert {v["gate"]: v for v in E["g3"]}[gate]["verdict"] == "fail"
        assert E["stop"] is None, "G3 is analysis-side and never stops a campaign"
        return
    assert by_gate(E["cells"][index])[gate]["verdict"] == "fail"
    assert E["stop"] == {"action": "stop-and-ask", "cellId": cells[index]["cellId"],
                         "failedGates": [gate]}


def test_healthy_campaign_passes_every_gate():
    cells, profile, firings = campaign()
    E = pg.evaluate_campaign(cells, profile, firings)
    assert E["stop"] is None
    for r in E["cells"]:
        assert r["valid"], r["failedGates"]
        for v in r["verdicts"]:
            if v["gate"] in ("F1", "R2.recovery") and r["kind"] == "nofault":
                assert v["verdict"] == pg.UNKNOWN          # does not apply, and is not required
            else:
                assert v["verdict"] == "pass", v
    assert all(v["verdict"] == "pass" for v in E["g3"])


def test_verdict_records_carry_the_documented_keys():
    cells, profile, firings = campaign()
    E = pg.evaluate_campaign(cells, profile, firings)
    for v in [v for r in E["cells"] for v in r["verdicts"]] + E["g3"]:
        assert {"gate", "verdict", "value", "threshold", "reason"} <= set(v)
        assert v["verdict"] in ("pass", "fail", pg.UNKNOWN)


# --------------------------------------------------------------------------- G1 on scheduled opportunities

def test_stalled_concurrency_capped_generator_does_not_fail_g1():
    """OTel's cap stalls starts while the target is paused: every in-window opportunity is scheduled, none dispatched.
    That is the fault's effect, not missing traffic, so G1 passes; a G1 over starts would have failed it."""
    cells, profile, _ = campaign()
    pg._plant_stall(cells[0])
    v = by_gate(pg.evaluate_cell(cells[0], profile))["G1"]
    assert v["verdict"] == "pass"
    assert 1 <= v["detail"]["startedInWindow"] < v["threshold"], "the case must be one a start-based G1 rejects"


def test_no_dispatched_request_in_the_window_fails_g1():
    """Draft 3 section 5 challenge 'no traffic in the window': every slot is pre-allocated in the ledger, so only the
    dispatch condition can reject it (review 2026-10-02: scheduled-only G1 is true by construction given G4)."""
    cell = pg.synthetic_cell("c", "fault")
    for r in cell["ledger"]:
        if 100.0 <= r["scheduled"] <= 131.0:
            r["started"], r["ended"], r["status"] = None, None, "dropped"
    v = pg.g1(cell)
    assert v["verdict"] == "fail" and v["value"] >= v["threshold"] and v["detail"]["startedInWindow"] == 0
    assert "offeredEqualsPlan" not in pg.g4(cell, pg.SYNTH_PROFILE)["value"], "G4 cannot catch it"


def test_min_dispatched_zero_restores_the_literal_draft3_rule(monkeypatch):
    cell = pg.synthetic_cell("c", "fault")
    for r in cell["ledger"]:
        if 100.0 <= r["scheduled"] <= 131.0:
            r["started"], r["ended"], r["status"] = None, None, "dropped"
    monkeypatch.setattr(pg, "G1_MIN_DISPATCHED", 0)
    assert pg.g1(cell)["verdict"] == "pass"


def test_g1_fails_on_a_rate_floor_miss():
    """PLAN part 4: a 10/s plan whose window holds only 4/s scheduled fails G1."""
    cell = pg.synthetic_cell("c", "nofault")
    cell["plan"]["rate"] = 10.0
    cell["plan"]["window"] = [100.0, 130.0]
    v = pg.g1(cell)
    assert v["verdict"] == "fail" and v["value"] == 121 and v["threshold"] == 150


def test_stall_before_onset_is_caught_by_g2_not_g1():
    """A generator that cannot dispatch while the system is healthy is unhealthy: dropped rows are failures."""
    cell = pg.synthetic_cell("c", "fault")
    for r in cell["ledger"]:
        if 50.0 <= r["scheduled"] < 60.0:
            r["started"], r["ended"], r["status"] = None, None, "dropped"
    assert pg.g1(cell)["verdict"] == "pass"
    assert pg.g2(cell)["verdict"] == "fail"


def test_pre_onset_timeouts_ending_after_onset_still_fail_g2():
    """Review 2026-10-02: excluding rows that end after onset hid 120 slow pre-onset timeouts (share 0.0)."""
    cell = pg.synthetic_cell("c", "fault")
    for r in cell["ledger"]:
        if 70.0 <= r["scheduled"] < 100.0:
            r["ended"], r["status"] = r["started"] + 30.0, "timeout"
    v = pg.g2(cell)
    assert v["verdict"] == "fail" and v["value"]["failureShare"] > pg.PRE_FAIL_MAX


def test_generator_crash_fails_g1_and_g4():
    cell = pg.synthetic_cell("c", "fault")
    cell["ledger"] = [r for r in cell["ledger"] if r["scheduled"] < 90.0]
    assert pg.g1(cell)["verdict"] == "fail"
    assert "offeredEqualsPlan" in pg.g4(cell, pg.SYNTH_PROFILE)["value"]


def test_g1_window_is_command_bounded_not_planned():
    cell = pg.synthetic_cell("c", "fault")
    assert pg.g1(cell)["detail"]["window"] == [100.01, 130.32]


# --------------------------------------------------------------------------- unknown is not zero, need()

def test_missing_ledger_is_unknown_and_blocks():
    cell = pg.synthetic_cell("c", "fault")
    cell["ledger"], cell["ledgerKind"] = None, None
    r = pg.evaluate_cell(cell, pg.SYNTH_PROFILE)
    g = by_gate(r)
    assert g["G1"]["verdict"] == pg.UNKNOWN and g["G2"]["verdict"] == pg.UNKNOWN
    assert g["G4"]["verdict"] == "fail", "G4 is a presence gate: absence is its failure"
    assert not r["valid"] and {"G1", "G2", "G4"} <= set(r["failedGates"])


def test_all_unknown_outcomes_leave_g2_unknown():
    cell = pg.synthetic_cell("c", "fault")
    for r in cell["ledger"]:
        r["status"] = "unknown"
    assert pg.g2(cell)["verdict"] == pg.UNKNOWN


def test_unknown_kind_is_invalid():
    cell = pg.synthetic_cell("c", "fault")
    cell["kind"] = "Fault"
    r = pg.evaluate_cell(cell, pg.SYNTH_PROFILE)
    assert not r["valid"] and "kind" in r["failedGates"]


def test_r1_without_declared_routes_is_unknown():
    profile = dict(pg.SYNTH_PROFILE, routes=[])
    assert pg.r1(pg.synthetic_cell("c", "nofault"), profile)["verdict"] == pg.UNKNOWN


def test_harness_invalid_cell_is_invalid_even_if_every_gate_passes():
    cell = pg.synthetic_cell("c", "nofault")
    cell["valid"] = False
    r = pg.evaluate_cell(cell, pg.SYNTH_PROFILE)
    assert not r["valid"] and r["failedGates"] == ["harness"]


@pytest.mark.parametrize("rate,seconds,expected", [
    (10.0, 15.0, 75), (0.15, 60.0, 5), (4.0, 0.0, 1), (None, 10.0, None), (1.0, 600.0, 300)])
def test_need(rate, seconds, expected):
    assert pg.need(rate, seconds) == expected


def test_cost_cell_g2_uses_the_whole_measurement():
    cell = pg.synthetic_cell("c", "nofault")
    cell["plan"]["window"] = None
    v = pg.g2(cell)
    assert v["verdict"] == "pass" and v["detail"]["costCell"] and v["threshold"]["successes"] == 600
    assert pg.entry_rule_can_fire(cell) is None, "a cost cell is not a false-alarm window"


# --------------------------------------------------------------------------- F1, R1, R2, P0, G4 detail

@pytest.mark.parametrize("mutate,check", [
    (lambda f: f.update({"onsetSource": "post-command"}), "onsetCommandBounded"),
    (lambda f: f.update({"onsetSource": "scheduled"}), "onsetCommandBounded"),
    (lambda f: f.update({"onsetCommandIssued": 102.5}), "onsetOnSchedule"),
    (lambda f: f.update({"revertCommandIssued": 120.0}), "holdBounded"),
    (lambda f: f.update({"revertCommandIssued": 135.0, "revertCommandReturned": 135.2}), "holdBounded"),
    (lambda f: f.update({"manifested": False}), "manifested"),
    (lambda f: f.update({"reverted": False}), "reverted"),
    (lambda f: f.update({"revertCommandReturned": 400.0}), "insideMeasurement"),
])
def test_f1_rejects(mutate, check):
    cell = pg.synthetic_cell("c", "fault")
    mutate(cell["fault"])
    v = pg.f1(cell)
    assert v["verdict"] == "fail" and check in v["value"]


def test_f1_hold_allows_a_slow_stop_command():
    """A `compose stop` takes ~11 s; the hold bound grows by the onset command's own duration."""
    cell = pg.synthetic_cell("c", "fault")
    cell["fault"].update({"onsetCommandReturned": 111.0, "revertCommandIssued": 141.0, "revertCommandReturned": 141.5})
    assert pg.f1(cell)["verdict"] == "pass"


def test_f1_missing_timing_fails_and_does_not_apply_to_no_fault():
    cell = pg.synthetic_cell("c", "fault")
    del cell["fault"]["revertCommandIssued"]
    assert pg.f1(cell)["verdict"] == "fail"
    assert pg.f1(pg.synthetic_cell("n", "nofault"))["verdict"] == pg.UNKNOWN


def test_r1_channel_with_zero_records_fails():
    cell = pg.synthetic_cell("c", "nofault")
    cell["channels"]["logs"]["recordsAfterWarmup"] = 0
    v = pg.r1(cell, pg.SYNTH_PROFILE)
    assert v["verdict"] == "fail" and v["value"] == ["channel:logs"]


def test_r1_unreported_channel_is_unknown():
    cell = pg.synthetic_cell("c", "nofault")
    del cell["channels"]["logs"]
    assert pg.r1(cell, pg.SYNTH_PROFILE)["verdict"] == pg.UNKNOWN


def test_readiness_restarts_once_then_stops_and_asks():
    cell = pg.synthetic_cell("c", "nofault")
    cell["readiness"]["routeStatus"]["/a"] = 503
    v = pg.r1(cell, pg.SYNTH_PROFILE)
    assert pg.readiness_action(v, 1) == "restart"
    assert pg.readiness_action(v, 2) == "stop-and-ask"
    assert pg.readiness_action(pg.r1(pg.synthetic_cell("d", "nofault"), pg.SYNTH_PROFILE), 1) == "proceed"


def test_r2_recovery_is_recorded_not_blocking():
    cell = pg.synthetic_cell("c", "fault")
    for r in cell["ledger"]:
        if r["scheduled"] >= 240.0:
            r["status"] = "failed"
    res = pg.evaluate_cell(cell, pg.SYNTH_PROFILE)
    rec = by_gate(res)["R2.recovery"]
    assert rec["verdict"] == "fail" and rec["detail"]["blocking"] is False
    assert res["valid"]


@pytest.mark.parametrize("observed", [{}, {"frontend": 0, "search": 0, "geo": 0}, {"frontend": 3, "search": 2}])
def test_p0_rejects_an_empty_or_incomplete_proof(observed):
    cell = pg.synthetic_cell("c", "nofault")
    cell["provenance"]["postureProof"]["observed"] = observed
    v = pg.p0(cell, pg.SYNTH_PROFILE)
    assert v["verdict"] == "fail" and v["value"] == ["postureProofObserved"]


def test_p0_reports_but_does_not_block_one_silent_expected_emitter():
    cell = pg.synthetic_cell("c", "nofault")
    cell["provenance"]["postureProof"]["observed"]["geo"] = 0
    v = pg.p0(cell, pg.SYNTH_PROFILE)
    assert v["verdict"] == "pass" and v["detail"]["silentExpectedEmitters"] == ["geo"]


def test_p0_rejects_tag_only_image_and_text_proof():
    cell = pg.synthetic_cell("c", "nofault")
    cell["provenance"]["imageDigests"]["geo"] = "registry/geo:latest"
    cell["provenance"]["postureProof"]["method"] = "config-text"
    v = pg.p0(cell, pg.SYNTH_PROFILE)
    assert v["verdict"] == "fail"
    assert {"imagesByDigest", "postureProofObserved"} <= set(v["value"])


@pytest.mark.parametrize("mutate,check", [
    (lambda c, p: c["plan"].update({"rate": 5.0}), "rateEqualsProfile"),
    (lambda c, p: c["plan"].update({"offered": 1300}), "planConsistent"),
    (lambda c, p: c["channels"]["traces"].update({"recordsInCell": 900}), "scope"),
    (lambda c, p: c.update({"ledgerKind": "proxy"}), "ledger"),
    (lambda c, p: c.update({"valid": None}), "validityRecorded"),
    (lambda c, p: p.update({"rate": None}), "rateEqualsProfile"),
    (lambda c, p: c["channels"]["logs"].pop("recordsTotal"), "scope"),
    (lambda c, p: c["channels"].pop("traces"), "scope"),
])
def test_g4_rejects(mutate, check):
    cell, profile = pg.synthetic_cell("c", "nofault"), copy.deepcopy(pg.SYNTH_PROFILE)
    mutate(cell, profile)
    v = pg.g4(cell, profile)
    assert v["verdict"] == "fail" and check in v["value"]


def test_g4_offered_comes_from_the_plan_not_a_literal():
    """1200, 90 and 600 are each correct for their own plan (Hotel, TeaStore, OTel)."""
    for offered, rate, duration in ((1200, 10.0, 120.0), (90, 0.15, 600.0), (600, 1.0, 600.0)):
        cell = pg.synthetic_cell("c", "nofault")
        cell["plan"].update({"offered": offered, "rate": rate, "durationSeconds": duration, "window": None})
        cell["measurement"] = [0.0, duration]
        cell["ledger"] = [{"scheduled": k / rate, "started": k / rate, "ended": k / rate + 0.01, "status": "ok"}
                          for k in range(offered)]
        profile = dict(pg.SYNTH_PROFILE, rate=rate)
        assert pg.g4(cell, profile)["verdict"] == "pass", (offered, pg.g4(cell, profile))


# --------------------------------------------------------------------------- G3

def test_g3_idle_no_fault_windows_give_n_eff_zero():
    cells, profile, _ = campaign()
    for c in cells[2:]:
        c["ledger"] = [r for r in c["ledger"] if r["scheduled"] < 50.0]
    E = pg.evaluate_campaign(cells, profile, {"log": []})
    g3 = {v["gate"]: v for v in E["g3"]}
    assert g3["G3"]["verdict"] == "fail" and g3["G3"]["value"] == 0
    assert g3["G3:log"]["verdict"] == "fail", "a rate over zero eligible windows cannot fail, so it is not a pass"


def test_g3_excludes_invalid_no_fault_windows():
    cells, profile, _ = campaign()
    cells[3]["valid"] = False
    g3 = {v["gate"]: v for v in pg.evaluate_campaign(cells, profile, {"log": []})["g3"]}
    assert g3["G3"]["value"] == 1 and g3["G3"]["threshold"] == 2


def test_g3_without_no_fault_cells_is_unknown():
    cells, profile, _ = campaign()
    E = pg.evaluate_campaign(cells[:2], profile, {"log": []})
    assert all(v["verdict"] == pg.UNKNOWN for v in E["g3"])


def test_g3_counts_only_eligible_windows():
    cells, profile, _ = campaign()
    cells[3]["ledger"] = [r for r in cells[3]["ledger"] if not 100.0 <= r["scheduled"] <= 130.0]
    E = pg.evaluate_campaign(cells, profile, {"log": ["nofault-1"]})
    g3 = {v["gate"]: v for v in E["g3"]}
    assert g3["G3"]["value"] == 1 and g3["G3"]["threshold"] == 2
    assert g3["G3:log"]["verdict"] == "pass" and g3["G3:log"]["detail"]["partial"]


# --------------------------------------------------------------------------- Python 3.9 floor

def _tree():
    return ast.parse(MODULE.read_text(encoding="utf-8"), filename=str(MODULE), feature_version=(3, 9))


def _annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for a in args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]:
                if a is not None and a.annotation is not None:
                    yield a.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def test_module_parses_with_the_39_grammar():
    _tree()


def test_no_pep604_annotation_fstring_or_dataclass():
    """py_compile does not catch an eager `X | None` on 3.9 (CLAUDE.md); f-strings and dataclasses are excluded
    outright so no 3.12 f-string grammar or `slots=` keyword can slip in."""
    tree = _tree()
    for ann in _annotations(tree):
        assert not any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(ann)), \
            ast.dump(ann)
    assert not any(isinstance(n, ast.JoinedStr) for n in ast.walk(tree))
    assert not any(isinstance(n, (ast.Name, ast.Attribute)) and "dataclass" in getattr(n, "id", getattr(n, "attr", ""))
                   for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Match) for n in ast.walk(tree))


def test_stdlib_only_and_no_package_relative_import():
    tree = _tree()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "vendored copy runs as a standalone file"
            names.add(node.module.split(".")[0])
    assert names and names <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)


def _py39():
    for candidate in ("/usr/bin/python3", shutil.which("python3.9")):
        if not candidate:
            continue
        try:
            out = subprocess.run([candidate, "-c", "import sys;print(sys.version_info[:2])"], capture_output=True,
                                 timeout=60, text=True)
        except OSError:
            continue
        if out.returncode == 0 and out.stdout.strip() == "(3, 9)":
            return candidate
    return None


PY39 = _py39()


@pytest.mark.skipif(PY39 is None, reason="no CPython 3.9 found; the 3.9 execution check is UNVERIFIED")
def test_self_check_runs_under_python39_isolated():
    """The script is run as __main__ (never loaded from the Apple bytecode cache), as `python3 -I` on a host."""
    ok = subprocess.run([PY39, "-I", "-B", str(MODULE), "--self-check"], capture_output=True, timeout=120, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "python 3.9" in ok.stdout and "self-check: PASS" in ok.stdout
    broken = subprocess.run([PY39, "-I", "-B", str(MODULE), "--self-check", "--break", "G2"],
                            capture_output=True, timeout=120, text=True)
    assert broken.returncode == 1 and "MISSED" in broken.stdout


# --------------------------------------------------------------------------- vendoring

VENDORED = sorted(ROOT.parent.glob("observability-placement-runtime-*/modules/*/validation/protocol_gates.py"))


@pytest.mark.skipif(not VENDORED, reason="no vendored copy exists yet (GATES.md: wiring commits pending)")
@pytest.mark.parametrize("copy_path", VENDORED, ids=[str(p.relative_to(ROOT.parent)) for p in VENDORED])
def test_vendored_copy_is_byte_identical(copy_path):
    assert hashlib.sha256(copy_path.read_bytes()).hexdigest() == hashlib.sha256(MODULE.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- count literals in the harness validators

# The worktrees the wiring commits go to (created 2026-10-02 from the pinned commits e4fd4c7 / c1724b1 / 92be2b7).
# Every target-side Python file of the module is scanned (review 2026-10-02: validators alone missed
# workload/candidate_search.py, validation/candidate_readiness.py and execution/candidate_release_installer.py).
TARGET_DIRS = ("execution", "validation", "workload", "witness", "faults", "collectors")
LITERAL_TREES = {
    "hotel": "observability-placement-runtime-hotel-protocol/modules/hotel-reservation",
    "teastore": "observability-placement-runtime-teastore-protocol/modules/teastore",
    "otel": "observability-placement-runtime-otel-protocol/modules/otel-demo",
}
# PLAN part 4 lists 1200 / 600 / 20 / 24 / 27 / `>= 5`; 90 is added because TeaStore checks `offered == 90 == len(journeys)`
# (validation/candidate_pilot.py:1268, and six more 90s), a literal the plan missed.
COUNT_LITERALS = {1200, 600, 90, 20, 24, 27}
COUNT_KEY_WORDS = ("cells", "offered", "runs", "journeys", "requests")


def literal_files(sut):
    root = ROOT.parent / LITERAL_TREES[sut]
    return sorted(p for d in TARGET_DIRS for p in (root / d).glob("*.py"))


def count_literals(source):
    """(line, text) of every comparison against a count literal, every `>= 5`, every cell-count constant
    (EXPECTED_*/*_RUNS/*_CELLS = int, durations *_SECONDS excluded), and every dict entry whose key names a count (`"expectedCells": 27`) holding one
    of the literals. Slices (`errors[:20]`), keyword timeouts (`timeout=600`) and file modes (0o600) are not counted.
    String literals (Hotel's warm-up `"--rate", "10"`) are not scanned: an XPASS here is not proof of no literal."""
    tree = ast.parse(source)
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op, right in zip(node.ops, node.comparators):
                for side in (node.left, right):
                    if isinstance(side, ast.Constant) and type(side.value) is int:
                        if side.value in COUNT_LITERALS or (side.value == 5 and isinstance(op, (ast.GtE, ast.LtE))):
                            hits.append(node.lineno)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and type(node.value.value) is int:
            for t in node.targets:
                if isinstance(t, ast.Name) and not t.id.endswith("_SECONDS") and (
                        t.id.startswith("EXPECTED_") or t.id.endswith(("_RUNS", "_CELLS"))):
                    hits.append(node.lineno)
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (isinstance(k, ast.Constant) and isinstance(k.value, str) and isinstance(v, ast.Constant)
                        and type(v.value) is int and v.value in COUNT_LITERALS
                        and any(w in k.value.lower() for w in COUNT_KEY_WORDS)):
                    hits.append(v.lineno)
    lines = source.splitlines()
    return [(n, lines[n - 1].strip()) for n in sorted(set(hits))]


def test_literal_scanner_finds_planted_literals_and_ignores_modes():
    src = ("EXPECTED_RUNS = 24\nif offered != 1200: pass\nok = count >= 5\nerrs = e[:20]\nmode = 0o600\n"
           "x = n == plan['offered']\nd = {'expectedCells': 27, 'timeoutSeconds': 600}\nrun(timeout=600)\n")
    assert [n for n, _ in count_literals(src)] == [1, 2, 3, 7]


@pytest.mark.xfail(reason="documents today's state (2026-10-02): the three harnesses still check counts against "
                          "literals; GATES.md replaces them with plan-derived G4/G1/R1. An XPASS means these patterns "
                          "are gone, not that every literal is (string literals are not scanned).",
                   strict=False)
@pytest.mark.parametrize("sut", sorted(LITERAL_TREES))
def test_harness_modules_hold_no_count_literal(sut):
    files = literal_files(sut)
    if not files:
        pytest.skip("worktree absent: %s" % LITERAL_TREES[sut])
    hits = {}
    for path in files:
        found = count_literals(path.read_text(encoding="utf-8"))
        if found:
            hits[str(path.relative_to(ROOT.parent / LITERAL_TREES[sut]))] = found
    assert not hits, "\n".join("%s:%d  %s" % (rel, n, text) for rel, rows in hits.items() for n, text in rows)
