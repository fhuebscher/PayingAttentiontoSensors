"""Traffic-sweep analysis v3 / v3.1 (research/detection-time/sweep_analysis_v3.py): protocol decisions 61-65 as
amended by 67, the decision-66 limitation, decision 68's pooling and the campaign-B freeze-stamp reader.

Layer: unit + synthetic end-to-end. Synthetic fixtures only (v2.4's own Hotel cell generator, post-edited to plant one
feature per rule; the harness-written TeaStore and OTel cells of tests/fixtures/sweep_v22); no evidence is read. Every
v3 rule has a check that passes and a planted defect (MUTANTS: its switch off) under which one of its checks fails;
the checks that v2.4 can express are shown failing on v2.4 itself, loaded from git at the freeze record 891a4c3
(test_v3_checks_fail_on_v24). The honest nested count is compared with a brute-force re-run of the whole calibration
without each held-out cell. Also: no tunable literal in v3, every v3 registry entry used has an origin, v2.4's script
and registry are byte-identical to the frozen 098f3e0.
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_analysis_v3 as v3  # noqa: E402
import test_sweep_analysis_v2 as t24  # noqa: E402  v2.4's cell generator and scanners
import test_sweep_analysis_v22_systems as t22  # noqa: E402  the harness-written TeaStore / OTel fixtures

v24 = v3.v24
NF, SP, CT, ND = t24.NF, t24.SP, t24.CT, t24.ND
FREEZE_REV = "891a4c3"                  # v2.4 freeze record (code at 098f3e0)
V24_CODE_REV = "098f3e0"
OUTLIER_US = 10_000_000                 # one 10 s memcached span in no-fault b1: spike dropped
USER_SPREAD = (7, 1907)                 # user spans: MAD 7 us, an outlier 900 us above the median in every cell


# ----------------------------------------------------------------------------- the planted campaign

def _cpu_edit(d, fn):
    p = d / "cpu.json"
    doc = json.loads(p.read_text())
    for smp in doc["samples"]:
        t = round(smp["capturedAtMonotonic"] - t24.B0 - 0.25)
        for row in smp["containers"]:
            v = fn(t, row["service"])
            if v is not None:
                row["cpuPercent"] = v
    p.write_text(json.dumps(doc))


def _ledger_edit(d, fn):
    p = d / "opportunity-ledger.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    for r in rows:
        fn(r)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _log_append(d, lines):
    with (d / "application.log").open("a") as fh:
        for w, msg in lines:
            fh.write('frontend-1  | %s {"level":"info","time":"%s","message":"%s"}\n' % (
                t24._dock(w + t24.RECEIPT), t24._app(w), msg))


def _slow(r):
    if r["sequence"] == 40:
        r["actualEndMonotonic"] = r["actualStartMonotonic"] + 0.3
        r["endedAt"] = t24._iso(r["actualEndMonotonic"] + t24.OFF + t24.READ_GAP[1])


def _failed(r):
    if r["sequence"] == 50:
        r.update(outcome="transport-error", statusCode=None, error="timed out")


def plant(d, regime, block, extra=None):
    """The v3 features (each cell): rate cpu 50 at t = 30 (a two-state level only the range fallback
    calibrates; 60 at t = 90 in net-delay cells, the catch); user cpu constant 5 with 7 at t = 60 (MAD = 0, range); a
    5-line frontend burst at 30 + block s (a one-shot template: `absent` calibrated only through the censored silences,
    gap > hold, inert); no-fault cells: request 40 takes 300 ms (E spike by range), b3's request 50 fails (decision
    63)."""
    def cpu(t, svc):
        if svc == "rate":
            return 50.0 if t == 30 else (60.0 if (t == 90 and regime == ND) else None)
        if svc == "user":
            return 7.0 if t == 60 else 5.0
        return extra(t, svc) if extra else None
    _cpu_edit(d, cpu)
    _log_append(d, [(t24.T0 + 30 + block + 0.1 * k, "burst line") for k in range(5)])
    if regime == NF:
        _ledger_edit(d, _slow)
        if block == 3:
            _ledger_edit(d, _failed)


def make_v3(root):
    for b in (1, 2, 3, 4):
        for regime in (NF, SP, CT, ND):
            d = t24.make_cell(root, regime, 1.0, b, t24.OFFSETS[b - 1], user_spread=USER_SPREAD,
                              outlier=(100, OUTLIER_US) if (regime == NF and b == 1) else None,
                              extra_log="rare template" if (regime == NF and b == 2) else None)
            plant(d, regime, b)
    return root


def make_validation(root):
    """Two more no-fault cells: rate and search cpu both 99 at t = 120 (one instant, two sensors)."""
    for b in (5, 6):
        d = t24.make_cell(root, NF, 1.0, b, t24.OFFSETS[0], user_spread=USER_SPREAD)
        plant(d, NF, b, extra=lambda t, svc: 99.0 if (t == 120 and svc == "search") else None)
        _cpu_edit(d, lambda t, svc: 99.0 if (t == 120 and svc == "rate") else None)
    return root


@pytest.fixture(scope="module")
def camp(tmp_path_factory):
    base = tmp_path_factory.mktemp("sweep_v3")
    return {"main": make_v3(base / "main"), "val": make_validation(base / "val"), "base": base}


SWITCHES = ("RANGE_DEGENERATE_GUARD", "HONEST_EVALUATED_ONLY", "CELL_KEY_POOL", "H4_RECORD_STATUS",
            "CONTAINER_FILTER", "P4_LEDGER_READING", "TESTABLE_ONLY", "PER_RULE_UNIT", "LOCO_CAL", "MAX_ALARMS", "RANGE_FALLBACK", "CENSORED_SILENCES", "ABSENT_M_SEARCH",
            "APPEAR_CALIBRATED", "FAILED_EXEMPT", "LEDGER_CALIBRATED", "UNION_FAR", "P4_OVER_PLACEABLE",
            "VALIDATION_NO_REFIT", "FREEZE_EVENT_ONSET", "NESTED", "INERT_STATUS",
            "RANGE_MAD_ZERO", "RANGE_LATENCY_UP_ONLY", "SENSITIVITY_NO_RANGE", "APPEAR_ONLY_APART", "OPTIMISTIC_ARM")
_CACHE = {}


def _state():
    return tuple(repr(getattr(v3, s)) for s in SWITCHES)


def R(camp):
    key = ("v3", _state())
    if key not in _CACHE:
        _CACHE[key] = v3.finish(v3.run(camp["main"], validation_dirs=[camp["val"]], reference=False))
    return _CACHE[key]


def cr1(Rr, setting="primary"):
    return Rr["cal"][setting]["perRate"][1.0]


def row(Rr, sid, rule, setting="primary"):
    c = cr1(Rr, setting)
    return c["rules"][(c["keys"][sid], rule)]


MEMC = "span:rate:memcached_get"
MRCPU = "metric:rate:cpu"
USERCPU = "metric:user:cpu"
USERSPAN = "span:user:/user.User/CheckUser"
LEDGER = "ledger:frontend:hotel-search-v1"


def _burst(Rr):
    c = cr1(Rr)
    return next(k for k in c["keys"] if k.startswith("log:frontend:") and any(
        r == "absent" and row(Rr, k, "absent")["status"] in ("inert", "calibrated", "dropped") for r in ("absent",))
        and "burst" in (Rr["cells"][0]["logText"].get(c["keys"][k][1:], ("", ""))[1] or ""))


def _fires(Rr, regime, sid, rule=None, setting="primary"):
    eps = Rr["results"][setting]["eps"]
    return [f for e in eps if e["regime"] == regime for f in e["fires"]
            if "%s:%s:%s" % (f["ch"], f["svc"], f["tok"]) == sid and (rule is None or f["rule"] == rule)
            and f["counts"]]


# ----------------------------------------------------------------------------- checks per decision

def check_per_rule(Rr):
    """Decision 61: the memcached span's spike is dropped (one 10 s outlier in one no-fault cell), its run3 and median
    are calibrated, so the sensor stays placeable and catches the net-delay episodes."""
    s = cr1(Rr)["sensors"][cr1(Rr)["keys"][MEMC]]
    return (row(Rr, MEMC, "spike")["status"] == "dropped" and row(Rr, MEMC, "run3")["status"] == "calibrated"
            and s["placeable"] and bool(_fires(Rr, ND, MEMC)))


def check_dropped_by_loco(Rr):
    """Decision 61: the outlier is held out (leave-one-cell-out) and counted once at every grid value: dropped, held
    out 1 at the range fallback."""
    r = row(Rr, MEMC, "spike")
    return r["status"] == "dropped" and r["heldOut"] == 1


def check_range(Rr):
    """Decision 62: rate cpu (5 / 5.1 with 50 once per cell) fails every K, the range fallback calibrates it,
    and it catches the 60 in the net-delay episodes."""
    r = row(Rr, MRCPU, "spike")
    return r["status"] == "calibrated" and r["value"] == ("range", None) and bool(_fires(Rr, ND, MRCPU, "spike"))


def check_range_mad_zero(Rr):
    """Decision 67: user cpu (constant 5, MAD = 0): no K rule (decision 52), the range fallback applies, labelled."""
    r = row(Rr, USERCPU, "spike")
    return r["status"] == "calibrated" and r["value"] == ("range", None) and r.get("madZeroRange") is True


def check_range_directions(_Rr=None):
    """Decision 67: the range is up-only for spans and the ledger, two-sided for metrics."""
    return (v3.dirs_of(("span", "s", "o"), ("range", None)) == ("up",)
            and v3.dirs_of(("ledger", "frontend", "r"), ("range", None)) == ("up",)
            and v3.dirs_of(("metric", "s", "cpu"), ("range", None)) == ("up", "down"))


def _burst_sid(Rr):
    c = cr1(Rr)
    texts = {}
    for cell in Rr["cells"]:
        texts.update(cell["logText"])
    return next(s for s, k in c["keys"].items() if k[0] == "log" and "burst line" in str(texts.get(k[1:], "")))


def check_censored_inert(Rr):
    """Decision 62/67: the burst's silences are in the fit through the censored segment ends: its `absent` meets zero
    at m = 1.5 (m = 1 leaves the cell with the longest trailing silence), and its gap exceeds the hold: inert; the
    sensor is not placeable."""
    s = _burst_sid(Rr)
    r = row(Rr, s, "absent")
    return (r["status"] == "inert" and r["value"] == ("m", 1.5) and r["g"] > cr1(Rr)["hold"]
            and not cr1(Rr)["sensors"][cr1(Rr)["keys"][s]]["placeable"])


def check_appear(Rr):
    """Decision 62: the template only no-fault b2 has fires `appear` when b2 is held out: dropped (1); the error
    template written under the pause is never in no-fault data: calibrated, the sensor appear-only (listed apart,
    decision 67), and it catches."""
    c = cr1(Rr)
    texts = {}
    for cell in Rr["cells"]:
        texts.update(cell["logText"])
    rare = next(s for s, k in c["keys"].items() if k[0] == "log" and "rare template" in str(texts.get(k[1:], "")))
    err = [s for s, k in c["keys"].items() if k[0] == "log" and "request failed" in str(texts.get(k[1:], ""))]
    return (row(Rr, rare, "appear")["status"] == "dropped" and row(Rr, rare, "appear")["heldOut"] == 1
            and bool(err) and all(c["sensors"][c["keys"][s]]["appearOnly"] for s in err)
            and all(row(Rr, s, "appear")["status"] == "calibrated" for s in err)
            and set(err) <= set(c["summary"]["appearOnly"]) and bool(_fires(Rr, SP, err[0], "appear")))


def check_failed_exempt(Rr):
    """Decision 63: one failed request in no-fault b3: `failed` exempt, counted (1), and the ledger stays the reference
    (P4 search-pause r1 evaluable)."""
    r = row(Rr, LEDGER, "failed")
    p4 = Rr["predictions"]["P4"]["P4a"][SP]["perRate"]["1"]
    return r["status"] == "exempt" and cr1(Rr)["quietFailed"]["hotel-search-v1"] == 1 and p4["holds"] is not None


def check_ledger_calibrated(Rr):
    """Decision 63: E's spike (a 300 ms request in every no-fault cell) needs the range fallback; not K_REFERENCE."""
    return row(Rr, LEDGER, "spike")["value"] == ("range", None) and row(Rr, LEDGER, "spike")["status"] == "calibrated"


def check_grid_edge(Rr):
    """Decision 67: the user span's outlier (900 us over a 7 us MAD) clears K = 80, not K = 100: K = 100, flagged."""
    r = row(Rr, USERSPAN, "spike")
    return r["value"] == ("K", 100.0) and r["gridEdge"] and v3.rid(cr1(Rr)["keys"][USERSPAN], "spike") in \
        cr1(Rr)["summary"]["gridEdge"]


def check_honest(Rr):
    """Decision 67: the honest nested count of the dropped memcached spike is 1 (without b1 a small K is selected and
    b1's outlier fires), and the T family's honest union carries it; the naive selection count is never 0-reported as
    a false-alarm claim (it is not in the readout)."""
    r = row(Rr, MEMC, "spike")
    fam = Rr["far"]["primary"]["families"][1.0]["T"]
    return r["honest"] == 1 and r["nested"][0] is not None and fam["union"] >= 1


def check_nested_brute_force(Rr, camp):
    """V3_NESTED_RULE against a brute force: for each held-out no-fault cell X, the whole calibration re-run on the
    cells without X; its selected value equals the nested value, for every rule of three sensors."""
    cells = [c for c in Rr["cells"]]
    quiet = [c for c in cells if c["valid"] and c["target"] is None and c["rate"] == 1.0]
    c1 = cr1(Rr)
    sids = (MEMC, MRCPU, _burst_sid(Rr), LEDGER)
    with v24.use_system("hotel"):
        for i, X in enumerate(quiet):
            rest = [c for c in cells if c is not X]
            cal = v3.calibrate(rest, v24.ARMS["primary"], 0, hold=c1["hold"])["perRate"][1.0]
            for s in sids:
                key = c1["keys"][s]
                for rule in v3.rules_of(key):
                    mine = c1["rules"][(key, rule)]
                    if mine.get("nested") is None:
                        continue
                    other = cal["rules"].get((key, rule))
                    want = other.get("selectedValue") if other and other["status"] != "inert" else None
                    vi = mine["nested"][i]
                    got = mine["values"][vi] if vi is not None else None
                    if got != want:
                        return False
    return True


def check_union(Rr):
    """Decision 64: two sensors alarming at one instant on two validation cells: union 2, their sum 4."""
    cr = cr1(Rr)
    vf = [(X, Rr["fits"][1.0]) for X in _val_cells(Rr)]
    x = v3.placement_far([MRCPU, "metric:search:cpu"], cr, v24.ARMS["primary"], "calibrated", vf)
    return x["alarms"] == 2 and x["union"] == 2 and x["sumOverSensors"] == 4


_VAL = {}


def _val_cells(Rr):
    if "cells" not in _VAL:
        with v24.use_system("hotel"):
            _VAL["cells"] = v3.find_and_load3([_VAL["path"]])[1]
    return _VAL["cells"]


def check_validation(Rr):
    """Decision 65: the calibrated rate range rule on the validation cells, no refit: 99 > 50 fires once in
    each (2)."""
    v = Rr["validation"]["primary"]["perRate"][1.0]
    return v["rulesAlarming"].get(MRCPU + "/spike") == 2 and v["cells"] == 2


def check_p4_over_placeable(Rr):
    """Decision 65: P4 is evaluated although families T, L, M have dropped rules (B1 gone), and names them."""
    p = Rr["predictions"]["P4"]["P4a"][ND]["perRate"]["1"]
    return p["holds"] is not None and MEMC + "/spike" in p["droppedOnPath"]


def check_ledger_dash(Rr):
    """Decision 70: the ledger is the OR of its calibrated rules: with an armed ledger rule dropped at the rate P4 is
    still evaluated, the dropped rule listed (reading (a), `—` there, is the planted defect)."""
    p = _ledger_dropped_rows(Rr)[SP]["perRate"]["1"]
    return (p["holds"] is not None and LEDGER + "/spike" in p["ledgerDropped"]
            and p["ledgerReading"] == "calibrated-ledger")


def check_sensitivity(Rr):
    """Decisions 65/67: <= 1 held-out alarm admits the memcached spike (1 alarm) at K = 2.5 and tries no range: the
    rate range rule is dropped there."""
    return (row(Rr, MEMC, "spike", "atMostOne")["status"] == "calibrated"
            and row(Rr, MRCPU, "spike", "atMostOne")["status"] == "dropped")


def check_optimistic(Rr):
    """Decision 67: the optimistic arm arms the dropped memcached spike at K = 100; it fires there, not in the
    calibrated arm."""
    return ("optimistic" in Rr["results"] and bool(_fires(Rr, ND, MEMC, "spike", "optimistic"))
            and not _fires(Rr, ND, MEMC, "spike"))


def check_readout(Rr):
    """Readout: never the naive bound as a false-alarm claim; honest table, E's rule mix, `failed` exempt labelled,
    B's fresh-check limit, the campaigns read."""
    J = v3.build_json(Rr)
    md = v3.render(Rr, J)
    return ("bound, 0 alarms" not in md and "## Honest false alarms" in md and "E's catching rule in the episodes" in md
            and "`failed` **exempt**" in md and "certify at best" in md and "Campaigns pooled" in md
            and "Optimistic bound (not evidence)" in md
            and not any("optimistic bound (not evidence)" in ln and "**" in ln for ln in md.splitlines())
            and json.dumps(J, default=sorted) and J["version"] == "3")


def check_testable(_Rr=None):
    """V3_TESTABLE_RULE: folds that cannot arm the rule are no evidence: with every fold unarmed no value is selected
    and the rule is not testable; one armed fold with 0 alarms selects the value."""
    none = v3._select(3, lambda vi, j: None, None, 0, 2)
    one = v3._select(3, lambda vi, j: 0 if j == 1 else None, None, 0, 2)
    skip = v3._select(3, lambda vi, j: None if vi == 0 else 0, None, 0, 2)
    return none == (None, False) and one == (0, True) and skip == (1, True)


def check_range_degenerate(Rr):
    """F1: sys_io / sys_psi_io are 0.0 in every cell (no instrument resolution): their level rules are unarmed with the
    degenerate-range reason, never dropped with an alarm per sample, never re-armed in the optimistic bound."""
    c = cr1(Rr)
    rows = [(rid_, r) for rid_, r in ((v3.rid(k, rule), row) for (k, rule), row in c["rules"].items())
            if rid_.split("/")[0].split(":")[-1] in ("sys_io", "sys_psi_io")]
    added = set(Rr["cal"]["optimistic"]["perRate"][1.0]["optimisticAdded"])
    return bool(rows) and all(r["status"] == "unarmed" and "range degenerate" in (r["reason"] or "")
                              for _, r in rows) and not any(n in added for n, _ in rows)


CHECKS = {
    "range-degenerate": check_range_degenerate,
    "testable": check_testable,
    "per-rule": check_per_rule, "dropped-loco": check_dropped_by_loco, "range": check_range,
    "range-mad-zero": check_range_mad_zero, "range-directions": check_range_directions,
    "censored-inert": check_censored_inert, "appear": check_appear, "failed-exempt": check_failed_exempt,
    "ledger-calibrated": check_ledger_calibrated, "grid-edge": check_grid_edge, "honest": check_honest,
    "union": check_union, "validation": check_validation, "p4-placeable": check_p4_over_placeable,
    "ledger-dash": check_ledger_dash, "sensitivity": check_sensitivity, "optimistic": check_optimistic,
    "readout": check_readout,
}

MUTANTS = {   # label: (switch, planted value, checks of which at least one must fail)
    "sensor as the unit (61)": ("PER_RULE_UNIT", False, ["per-rule"]),
    "held-out cell in its own fit (61)": ("LOCO_CAL", False, ["dropped-loco", "appear"]),
    "one held-out alarm admitted in the primary (61)": ("MAX_ALARMS", 1, ["dropped-loco", "per-rule"]),
    "no range fallback (62)": ("RANGE_FALLBACK", False, ["range"]),
    "gap without the censored silences (62)": ("CENSORED_SILENCES", False, ["censored-inert"]),
    "m fixed at v2.4's 2 (62)": ("ABSENT_M_SEARCH", False, ["censored-inert"]),
    "appear never dropped (62)": ("APPEAR_CALIBRATED", False, ["appear"]),
    "failed calibrated (63)": ("FAILED_EXEMPT", False, ["failed-exempt"]),
    "ledger at K_REFERENCE, uncalibrated (63)": ("LEDGER_CALIBRATED", False, ["ledger-calibrated"]),
    "placement count = sum over sensors (64)": ("UNION_FAR", False, ["union"]),
    "B1 back (65)": ("P4_OVER_PLACEABLE", False, ["p4-placeable"]),
    "P4 — where a ledger rule is dropped, reading (a) (70)": ("P4_LEDGER_READING", "dash-if-ledger-rule-dropped",
                                                                ["ledger-dash"]),
    "validation cells refitted (65)": ("VALIDATION_NO_REFIT", False, ["validation"]),
    "naive count as the honest one (67)": ("NESTED", False, ["honest"]),
    "inert absent called calibrated (67)": ("INERT_STATUS", False, ["censored-inert"]),
    "no range under MAD = 0 (67)": ("RANGE_MAD_ZERO", False, ["range-mad-zero"]),
    "two-sided range on latency (67)": ("RANGE_LATENCY_UP_ONLY", False, ["range-directions"]),
    "range in the <= 1 setting (67)": ("SENSITIVITY_NO_RANGE", False, ["sensitivity"]),
    "appear-only not listed apart (67)": ("APPEAR_ONLY_APART", False, ["appear"]),
    "no optimistic arm (67)": ("OPTIMISTIC_ARM", False, ["optimistic", "readout"]),
    "unarmed folds read as zero alarms (V3_TESTABLE_RULE)": ("TESTABLE_ONLY", False, ["testable"]),
    "degenerate range armed (F1)": ("RANGE_DEGENERATE_GUARD", False, ["range-degenerate"]),
}


def _run_check(name, Rr):
    try:
        return bool(CHECKS[name](Rr))
    except (KeyError, AttributeError, TypeError, StopIteration):
        return False


def test_checks_pass(camp):
    _VAL["path"] = camp["val"]
    Rr = R(camp)
    res = {n: _run_check(n, Rr) for n in CHECKS}
    assert all(res.values()), [k for k, v in res.items() if not v]


def test_nested_equals_brute_force(camp):
    _VAL["path"] = camp["val"]
    assert check_nested_brute_force(R(camp), camp)


def test_nested_planted_defect_fails_brute_force(camp, monkeypatch):
    _VAL["path"] = camp["val"]
    monkeypatch.setattr(v3, "NESTED", False)
    assert not check_nested_brute_force(R(camp), camp)


@pytest.mark.parametrize("label", sorted(MUTANTS))
def test_planted_defect_is_caught(label, camp, monkeypatch):
    _VAL["path"] = camp["val"]
    attr, val, names = MUTANTS[label]
    monkeypatch.setattr(v3, attr, val)
    Rr = R(camp)
    assert any(not _run_check(n, Rr) for n in names), "planted defect not caught: %s" % label


# ----------------------------------------------------------------------------- v2.4 itself, from git

def git_show(rev, rel):
    got = subprocess.run(["git", "-C", str(ROOT), "show", "%s:%s" % (rev, rel)], capture_output=True)
    if got.returncode != 0:
        pytest.skip("git history not available")
    return got.stdout.decode()


_OLD = {}


def v24_from_git():
    """sweep_analysis_v2.py and its registry at the freeze record 891a4c3, executed as their own module."""
    if "mod" not in _OLD:
        mod = types.ModuleType("sweep_analysis_v2_at_" + FREEZE_REV)
        mod.__file__ = str(ROOT / "research" / "detection-time" / "sweep_analysis_v2.py")
        mod.__dict__["__reg__"] = json.loads(git_show(FREEZE_REV, "research/protocol/parameters.json"))
        src = git_show(FREEZE_REV, "research/detection-time/sweep_analysis_v2.py").replace(
            "REGISTRY = load_registry()", "REGISTRY = {p['name']: p for p in __reg__['parameters']}")
        exec(compile(src, "v2.4@" + FREEZE_REV, "exec"), mod.__dict__)
        _OLD["mod"] = mod
    return _OLD["mod"]


V24_EXPRESSIBLE = ("per-rule", "range", "appear", "failed-exempt", "p4-placeable")   # through fires / P4 rows


def _v24_check(name, Rr):
    """A v3 check on v2.4's result, through what both share (episode fires, P4 rows): T, M, L catches, P4 evaluable."""
    if name == "per-rule":
        return bool(_fires(Rr, ND, MEMC))
    if name == "range":
        return bool(_fires(Rr, ND, MRCPU, "spike"))
    if name == "appear":
        return any(f["family"] == "L" and f["rule"] == "appear" and f["counts"] for e in Rr["results"]["primary"]["eps"]
                   if e["regime"] == SP for f in e["fires"])
    if name in ("failed-exempt", "p4-placeable"):
        reg = SP if name == "failed-exempt" else ND
        return Rr["predictions"]["P4"]["P4a"][reg]["perRate"]["1"]["holds"] is not None
    raise KeyError(name)


def test_v3_checks_fail_on_v24(camp):
    """Every v3 check fails on v2.4 at 891a4c3: the five v2.4 can express through its episodes and P4 rows (its
    family operating point mutes T, M, L and E on this campaign), and the others because v2.4 has no such structure
    (per-rule statuses, honest counts, placement function, validation, freeze reader)."""
    _VAL["path"] = camp["val"]
    old = v24_from_git()
    Rold = old.run(camp["main"], compare=False)
    Rnew = R(camp)
    for name in V24_EXPRESSIBLE:
        assert _v24_check(name, Rnew), name                     # holds on v3
        assert not _v24_check(name, Rold), name                 # fails on v2.4
    for name in sorted(set(CHECKS) - set(V24_EXPRESSIBLE) - {"range-directions", "testable", "range-degenerate"}):
        assert not _run_check(name, Rold), name
    assert not any(hasattr(old, n) for n in ("dirs_of", "placement_far", "apply_freeze_events", "_select"))


# ----------------------------------------------------------------------------- campaign B reader (TeaStore)

def _ts_copy(tmp_path, name):
    camp_ = t22._copy(t22.TS_CAMP, tmp_path / name)
    return camp_, t22._cell_dir(camp_, t22.TS_PAUSE)


def _ts_cell(d):
    with v24.use_system("teastore"):
        with v3.admit_b_epochs():
            return v3.load3(v24.teastore_load_or_invalid, d)


def _cmd_offsets(d):
    cs = json.loads((d / "intervention.json").read_text())["sweep"]["commandStamps"]
    return cs["onsetCommandIssuedMonotonicOffsetSeconds"], cs["onsetCommandReturnedMonotonicOffsetSeconds"]


TS_TARGET = "f" * 64


def plant_freeze_stamps(d, version="h4-h10-v1", b_epoch=True, status="recorded", failures=(), failure_count=None,
                        container=TS_TARGET, pause_delay=0.1, null=False):
    """The TeaStore B harness's record at bbb6b11 (build_freeze_stamps; decision 69): intervention.json
    sweep.freezeStamps with status / failures / failureCount and the target's pause row `pause_delay` s after the
    onset command's issue (producer clock), rows naming `container`; `null` writes the null record a failed build
    leaves; the B study epoch on the receipt."""
    a, ret = _cmd_offsets(d)
    p = d / "intervention.json"
    iv = json.loads(p.read_text())
    rows = [{"action": "pause", "type": "container", "containerId": container, "timeNano": 1,
             "monotonicOffsetSeconds": a + pause_delay},
            {"action": "unpause", "type": "container", "containerId": container, "timeNano": 2,
             "monotonicOffsetSeconds": a + 60.0}]
    iv["sweep"]["freezeStamps"] = None if null else {
        "schemaVersion": 1, "version": version, "scenario": "auth-freeze", "targetContainerId": TS_TARGET,
        "toleranceSeconds": 0.25, "commands": {"onsetIssuedMonotonicOffsetSeconds": a,
                                               "onsetReturnedMonotonicOffsetSeconds": ret},
        "readbacks": [], "clock": {}, "events": {"command": [], "returnCode": 0, "error": None, "rows": rows},
        "status": status, "failures": list(failures),
        "failureCount": len(failures) if failure_count is None else failure_count}
    p.write_text(json.dumps(iv))
    if b_epoch:
        rp = d / "receipt.json"
        rc = json.loads(rp.read_text())
        rc["studyEpoch"] = "teastore-traffic-sweep-b-v1"
        rp.write_text(json.dumps(rc))


def check_freeze_stamps(tmp_path):
    camp_, d = _ts_copy(tmp_path, "fs")
    plant_freeze_stamps(d)
    c = _ts_cell(d)
    on = c["onset"]
    return (c["valid"] and on["hiKind"] == "docker-event" and abs((on["hi"] - on["lo"]) - 0.1) < 1e-9
            and on["commandReturnedBound"]["hi"] > on["hi"] and c["freezeStamps"]["freezeStamps"]["version"] == "h4-h10-v1"
            and c["h4"]["status"] == "used")


def check_docker_events_file(tmp_path):
    """Hotel's format in docker-events.json: the pause event of auth (timeNano, wall) 0.1 s after the onset command."""
    camp_, d = _ts_copy(tmp_path, "de")
    c0 = _ts_cell(d)
    a, _ = _cmd_offsets(d)
    lo = c0["onset"]["lo"]
    wall = lo + 0.1 + c0["align"]["offset"]
    ev = [{"Type": "container", "Action": "pause", "Actor": {"ID": "c", "Attributes": {
        "com.docker.compose.service": "auth"}}, "time": int(wall), "timeNano": int(round(wall * 1e9))},
          {"Type": "container", "Action": "unpause", "Actor": {"ID": "c", "Attributes": {
              "com.docker.compose.service": "auth"}}, "time": int(wall + 60), "timeNano": int(round((wall + 60) * 1e9))}]
    (d / "docker-events.json").write_text("".join(json.dumps(x) + "\n" for x in ev))
    c = _ts_cell(d)
    Rr = v3.run(camp_, system="teastore", reference=False)
    p1 = Rr["predictions"]["P1"]["perEpisode"][0]
    return (c["onset"]["hiKind"] == "docker-event" and abs(c["onset"]["hi"] - (lo + 0.1)) < 1e-6
            and "dockerEventGranularity" in p1["toleranceParts"] and "docker-events.json" in p1["hiSource"])


def test_freeze_stamps_read(tmp_path):
    assert check_freeze_stamps(tmp_path)
    assert check_docker_events_file(tmp_path)


def test_freeze_reader_planted_off_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(v3, "FREEZE_EVENT_ONSET", False)
    assert not check_freeze_stamps(tmp_path)


def test_freeze_reader_fails_on_v24(tmp_path):
    """v2.4 at 891a4c3 ignores the events (command-returned bound) and refuses the B study epoch."""
    old = v24_from_git()
    camp_, d = _ts_copy(tmp_path, "old")
    plant_freeze_stamps(d, b_epoch=False)
    with old.use_system("teastore"):
        c = old.teastore_load_or_invalid(d)
    assert c["onset"].get("hiKind") == "command-returned"
    plant_freeze_stamps(d)
    with old.use_system("teastore"), pytest.raises(old.UnknownSchema):
        old.teastore_load_or_invalid(d)


@pytest.mark.parametrize("bad", ["version", "docker-file"])
def test_unknown_freeze_schema_stops(tmp_path, bad):
    camp_, d = _ts_copy(tmp_path, "bad-" + bad)
    if bad == "version":
        plant_freeze_stamps(d, version="h4-h10-v2")
    else:
        (d / "docker-events.json").write_text(json.dumps({"events": []}))
    with pytest.raises(v24.UnknownSchema):
        _ts_cell(d)


def test_b_epoch_admission_is_scoped():
    """STUDY_EPOCHS_B is admitted only while v3 reads cells; v2.4's registry entry is restored."""
    with v24.use_system("teastore"):
        before = list(v24.param("SYSTEM_TEASTORE")["studyEpochs"])
        with v3.admit_b_epochs():
            inside = list(v24.param("SYSTEM_TEASTORE")["studyEpochs"])
        after = list(v24.param("SYSTEM_TEASTORE")["studyEpochs"])
    assert "teastore-traffic-sweep-b-v1" in inside and before == after and "teastore-traffic-sweep-b-v1" not in after
    assert v3.STUDY_EPOCHS_B["otel"] == ["otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1"]  # decision 92


# ----------------------------------------------------------------------------- OTel B reader, decision 69, pooling

OT_B_EPOCH = "otel-repeat-episodes-v1"


def _ot_b_campaign(dest, status="ok", reasons=(), failures=None, pause_delay=0.1,
                   kind="otel-demo-fault-docker-events-v1", container=None, freeze_null=False, stamp_status="ok",
                   stamp_reasons=()):
    """The OTel fixture rewritten in the B harness's decision-69 shape (0ad9a2c / c4aa313): every receipt names the B
    epoch; every fault intervention carries `freeze` with its stampCheck {status, failures, reasons}; the pause cell keeps
    docker-events.json (docker_events_record: the events of `container` (default the target) with the producer's mapping
    monotonic = bm + (timeNano/1e9 - be), the pause `pause_delay` s after the command, the verdict {status, failures,
    reasons})."""
    camp_ = t22._copy(t22.OT_CAMP, dest)
    for rp in sorted((camp_ / "runs").rglob("receipt.json")):
        d = rp.parent
        rc = json.loads(rp.read_text())
        rc["runKey"]["studyEpoch"] = OT_B_EPOCH
        rp.write_text(json.dumps(rc))
        ip = d / "intervention.json"
        if not ip.exists():
            continue
        iv = json.loads(ip.read_text())
        led = json.loads((d / "request-ledger.json").read_text())
        bm, be = led["barrierMonotonic"], led["barrierEpoch"]
        a, applied = iv["startedMonotonic"], iv["appliedMonotonic"]
        sreasons = [{"kind": "contradictory", "reason": r} for r in stamp_reasons]
        iv["freeze"] = None if freeze_null else {
            "schemaVersion": 1, "kind": "otel-demo-fault-freeze-stamps-v1", "action": iv["action"],
            "commandIssuedMonotonic": a, "commandReturnedMonotonic": (a + applied) / 2,
            "stateReadbackMonotonic": applied, "commandIssuedOffsetSeconds": a - bm,
            "commandReturnedOffsetSeconds": (a + applied) / 2 - bm, "stateReadbackOffsetSeconds": applied - bm,
            "dockerEventsFile": "docker-events.json" if iv["action"] == "pause" else None,
            "stampCheck": {"status": stamp_status, "failures": len(sreasons), "reasons": sreasons}}
        ip.write_text(json.dumps(iv))
        if iv["action"] == "pause":
            cid = container or iv["targetContainerId"]

            def ev(action, mono):
                tn = int(round((mono - bm + be) * 1e9))
                off = tn / 1e9 - be
                return {"action": action, "containerId": cid, "service": iv["service"], "timeNano": tn,
                        "offsetSeconds": off, "monotonic": bm + off}
            rs = [{"kind": "contradictory" if status == "contradictory" else "missing", "reason": r} for r in reasons]
            doc = {"schemaVersion": 1, "kind": kind, "runId": "x", "service": iv["service"],
                   "containerId": iv["targetContainerId"],
                   "clock": {"barrierMonotonic": bm, "barrierEpoch": be, "mapping": "m", "stopPair": {}},
                   "stream": {"argv": [], "sinceEpoch": 0, "exitedBeforeStop": False, "returnCode": None,
                              "stderr": "", "error": None},
                   "raw": [], "parseProblems": [],
                   "events": [ev("pause", a + pause_delay), ev("unpause", iv["revertingMonotonic"] + 0.1)],
                   "verdict": {"pauseEvents": 1, "unpauseEvents": 1, "pauseOffsetSeconds": None,
                               "unpauseOffsetSeconds": None, "onsetIntervalSeconds": None, "otherContainerEvents": 0,
                               "status": status, "failures": len(rs) if failures is None else failures,
                               "reasons": rs}}
            (d / "docker-events.json").write_text(json.dumps(doc))
    return camp_


def _ot_pause(cells):
    return next(c for c in cells if c["valid"] and c["regime"] == t22.OT_PAUSE)


def _load(system, camps):
    with v24.use_system(system):
        return v3.find_and_load3(camps)[1]


def check_ot_b_used(tmp_path):
    """The OTel B pause cell: epoch admitted, `freeze` admitted for it only (the sweep cell keeps the exact key set), the
    pause event 0.1 s after the command is the onset's upper bound, H4 `used`, harness B; the sweep cell `sweep`."""
    cells = _load("otel", [t22.OT_CAMP, _ot_b_campaign(tmp_path / "otb")])
    b = next(c for c in cells if c["valid"] and c["regime"] == t22.OT_PAUSE and c["harness"] == "B")
    sw = next(c for c in cells if c["valid"] and c["regime"] == t22.OT_PAUSE and c["harness"] == "sweep")
    on = b["onset"]
    return (all(c["valid"] for c in cells) and (b.get("h4") or {}).get("status") == "used"
            and on["hiKind"] == "docker-event" and abs(on["hi"] - on["lo"] - 0.1) < 1e-6
            and (sw.get("h4") or {}).get("status") == "not recorded (sweep harness)"
            and sw["onset"]["hiKind"] == "command-returned")


def check_ot_b_fallback(tmp_path):
    """Decision 69: the harness verdict not valid (stream died): the cell stays valid, its H4 record is `missing` with the
    reason, the bound is the sweep's (appliedMonotonic), and it is counted in the breakdown."""
    camp_ = _ot_b_campaign(tmp_path / "otbad", status="missing", reasons=("stream died",))
    cells = _load("otel", [camp_])
    c = _ot_pause(cells)
    iv = json.loads((Path(c["cell"]) if Path(c["cell"]).is_absolute() else ROOT / c["cell"]).joinpath(
        "intervention.json").read_text())
    Rr = v3.run(camp_, system="otel", reference=False)
    hb = v3.harness_breakdown(Rr)
    return (c["valid"] and c["h4"]["status"] == "missing" and any("stream died" in r for r in c["h4"]["reasons"])
            and c["onset"]["hi"] == iv["appliedMonotonic"] and hb["H4"]["B"].get("missing") == 1)


def check_ot_b_late_event(tmp_path):
    """Decision 69: a pause event 10 s after the command is contradictory: missing, the sweep's bound kept."""
    c = _ot_pause(_load("otel", [_ot_b_campaign(tmp_path / "otlate", pause_delay=10.0)]))
    return c["h4"]["status"] == "missing" and c["onset"]["hiKind"] == "command-returned" and any(
        "outside" in r for r in c["h4"]["reasons"])


def check_ot_b_cases(tmp_path):
    """Decision 69 at c4aa313, OTel: verdict `missing` with plausible events (not used); failures disagreeing with the
    reasons; `freeze` null; only another container's events; a pause 4 s late with the verdict recomputed
    (contradictory); a throttle stampCheck contradiction (the throttle's record missing, its bound unchanged)."""
    def pause(name, **kw):
        return _ot_pause(_load("otel", [_ot_b_campaign(tmp_path / name, **kw)]))
    m = pause("vm", status="missing", reasons=("no unpause event of the target container",))
    n = pause("cnt", status="missing", reasons=("x",), failures=3)
    z = pause("fnull", freeze_null=True)
    f = pause("foreign", container="cid-other")
    late = pause("late4", status="contradictory", reasons=("the pause event (4.0 s) is outside the pause command",),
                 pause_delay=4.0)
    thr_cells = _load("otel", [_ot_b_campaign(tmp_path / "stamp", stamp_status="contradictory",
                                              stamp_reasons=("stateReadbackMonotonic differs",))])
    thr = next(c for c in thr_cells if c["valid"] and c["regime"] == t22.OT_THROTTLE)
    return (all(_fell_back(c) for c in (m, n, z, f, late))
            and any("no unpause event" in r for r in m["h4"]["reasons"])
            and any("failures 3" in r for r in n["h4"]["reasons"])
            and "intervention freeze null" in z["h4"]["reasons"]
            and any("0 `pause` events" in r for r in f["h4"]["reasons"])
            and any("outside" in r for r in late["h4"]["reasons"])
            and thr["h4"]["status"] == "missing" and thr["onset"]["hiKind"] == "command-returned")


def test_otel_b_reader(tmp_path):
    assert check_ot_b_used(tmp_path)
    assert check_ot_b_fallback(tmp_path)
    assert check_ot_b_late_event(tmp_path)
    assert check_ot_b_cases(tmp_path)


def test_replay_association_is_the_producers():
    """F7: the reader re-derives the event time as the producer does, bm + (timeNano/1e9 - be)."""
    src = V3_SRC.read_text()
    assert "(bm + (e[\"timeNano\"] / v24.NS_PER_S - be))" in src and "bm + e[\"timeNano\"] / v24.NS_PER_S - be" not in src


def test_otel_b_reader_planted_defects(tmp_path, monkeypatch):
    monkeypatch.setattr(v3, "H4_FALLBACK", False)
    assert not check_ot_b_fallback(tmp_path / "a")
    monkeypatch.setattr(v3, "H4_FALLBACK", True)
    monkeypatch.setattr(v3, "FREEZE_EVENT_ONSET", False)
    assert not check_ot_b_used(tmp_path / "b")


def test_otel_b_unknown_kind_stops(tmp_path):
    with pytest.raises(v24.UnknownSchema):
        _load("otel", [_ot_b_campaign(tmp_path / "otkind", kind="otel-demo-fault-docker-events-v2")])


def test_otel_b_fails_on_v24(tmp_path):
    """v2.4 at 891a4c3 refuses OTel B cells (unknown epoch; with the epoch admitted, the `freeze` key)."""
    old = v24_from_git()
    d = _ot_pause(_load("otel", [_ot_b_campaign(tmp_path / "otold")]))["cell"]
    d = Path(d) if Path(d).is_absolute() else ROOT / d
    with old.use_system("otel"), pytest.raises(old.UnknownSchema):
        old.otel_load_or_invalid(d)


def _ts_case(tmp_path, name, **kw):
    camp_, d = _ts_copy(tmp_path, name)
    plant_freeze_stamps(d, **kw)
    return _ts_cell(d)


def _fell_back(c):
    on = c["onset"]
    return (c["valid"] and c["h4"]["status"] == "missing" and on["hiKind"] == "command-returned"
            and on["hi"] == on["commandReturnedBound"]["hi"])


def check_ts_events_failed(tmp_path):
    """Decision 69 at bbb6b11, TeaStore: status `missing` with its failure, the rows still plausible: not used (the
    command-returned bound, the failure as the reason); a null record; failureCount disagreeing with the failures;
    `missing` with no failure; only another container's rows (F11); a pause row 4 s late."""
    c1 = _ts_case(tmp_path, "miss", status="missing", failures=["docker events query: timed out"])
    c2 = _ts_case(tmp_path, "null", null=True)
    c3 = _ts_case(tmp_path, "count", status="missing", failures=["x"], failure_count=2)
    c4 = _ts_case(tmp_path, "empty", status="missing", failures=[])
    c5 = _ts_case(tmp_path, "foreign", container="e" * 64)
    c6 = _ts_case(tmp_path, "late", pause_delay=4.0)
    return (all(_fell_back(c) for c in (c1, c2, c3, c4, c5, c6))
            and any("timed out" in r for r in c1["h4"]["reasons"]) and "freezeStamps null" in c2["h4"]["reasons"]
            and any("failureCount" in r for r in c3["h4"]["reasons"])
            and any("no failure" in r for r in c4["h4"]["reasons"])
            and c5["freezeStamps"]["freezeStamps"]["foreignRows"] == 2
            and any("outside" in r for r in c6["h4"]["reasons"]))


def test_teastore_failed_events_fall_back(tmp_path, monkeypatch):
    assert check_ts_events_failed(tmp_path / "a")
    monkeypatch.setattr(v3, "H4_FALLBACK", False)
    assert not check_ts_events_failed(tmp_path / "b")


def _ts_b_copies(tmp_path, n=3):
    """n copies of the TeaStore fixture as campaign-B cells (B epoch; the pause cell with its freeze stamps)."""
    out = []
    for i in range(n):
        camp_, d = _ts_copy(tmp_path, "b%d" % i)
        plant_freeze_stamps(d)
        for rp in (camp_ / "runs").rglob("receipt.json"):
            rc = json.loads(rp.read_text())
            rc["studyEpoch"] = "teastore-traffic-sweep-b-v1"
            rp.write_text(json.dumps(rc))
        out.append(camp_)
    return out


def check_pooled_harness(tmp_path):
    """Decision 49: the sweep's episode + 3 B episodes per (fault, rate) = 4, 'k of 4' evaluable (P2 and P4 with
    folds); the breakdown tags 1 sweep and 3 B episodes, P1 per harness, and P4 folds per harness sum to the pooled
    folds."""
    Rr = v3.finish(v3.run([t22.TS_CAMP] + _ts_b_copies(tmp_path), system="teastore", reference=False))
    hb = v3.harness_breakdown(Rr)
    p2 = Rr["predictions"]["P2"]["0.2"]
    p4 = Rr["predictions"]["P4"]["P4a"][t22.TS_PAUSE]["perRate"]["0.2"]
    k = "primary P4a %s r0.2" % t22.TS_PAUSE.replace("-effect", "")
    md = v3.render(Rr, v3.build_json(Rr))
    return (hb["episodes"]["auth-freeze r0.2"] == {"sweep": 1, "B": 3} and p2["n"] == 4 and p2["holds"] is not None
            and hb["P1"] == {"B": [3, 3], "sweep": [1, 1]} and len(p4.get("folds") or []) == 4
            and sum(x[1] for x in hb["P4"][k].values()) == 4 and hb["H4"]["B"].get("used") == 3
            and "**Per harness**" in md and "L-H4" in md)


def test_pooled_harness_breakdown(tmp_path, monkeypatch):
    assert check_pooled_harness(tmp_path / "a")
    monkeypatch.setattr(v3, "HARNESS_TAG", False)
    assert not check_pooled_harness(tmp_path / "b")


def check_pool_key(tmp_path):
    """Decision 68/69: Hotel quiet A and A2, same run IDs and paths under two campaign directories, both pooled (4 + 4
    no-fault cells beside the sweep's 4); the same directory twice stops the run."""
    main = t24.make_main(tmp_path / "main")
    qa, qa2 = tmp_path / "quietA" / "x", tmp_path / "quietA2" / "x"
    for root in (qa, qa2):
        for b in (1, 2, 3, 4):
            t24.make_cell(root, NF, 1.0, b, t24.OFFSETS[b - 1])
    cells = _load("hotel", [main, qa, qa2])
    nf = [c for c in cells if c["valid"] and c["target"] is None]
    keys = {c["poolKey"] for c in cells}
    try:
        _load("hotel", [main, qa, qa])
        twice = False
    except SystemExit:
        twice = True
    return len(nf) == 12 and len(keys) == len(cells) and twice


def test_pool_key(tmp_path, monkeypatch):
    assert check_pool_key(tmp_path / "a")
    monkeypatch.setattr(v3, "POOL_KEY_CAMPAIGN", False)
    with pytest.raises(SystemExit):
        check_pool_key(tmp_path / "b")


def test_accepted_defaults_recorded():
    """The coordinator's acceptance of the six defaults (2026-10-09) is in the registry, each rule naming it."""
    e = v3.REGISTRY["V3_ACCEPTED_DEFAULTS"]
    assert e["origin_type"] == "engineering default" and e["origin_ref"] == "engineering default (coordinator, 2026-10-09)"
    assert len(e["value"]) == 6
    for n in ("V3_NESTED_RULE", "V3_TESTABLE_RULE", "V3_INERT_RULE", "V3_P4_RULE", "V3_FREEZE_EVENTS_RULE",
              "V3_APPEAR_RULE", "V3_CALIBRATION_SCOPE_RULE"):
        assert "engineering default (coordinator, 2026-10-09)" in v3.REGISTRY[n]["origin_ref"], n
    assert "decision 69" in v3.REGISTRY["V3_FREEZE_EVENTS_RULE"]["origin_ref"]
    assert any("L-H10" in x for x in v3.REGISTRY["V3_KNOWN_LIMITATIONS"]["value"]["otel"])


# ----------------------------------------------------------------------------- system end-to-end (TeaStore, OTel fixtures)

@pytest.mark.parametrize("system", ["teastore", "otel"])
def test_system_end_to_end(system, tmp_path):
    """Sweep + two quiet campaigns (decision 68: A and A2 pooled) + a validation campaign through the CLI: the readout
    lists the three campaigns, calibrates, prints honest counts and no naive bound; OTel prints decision 66's
    limitation."""
    src, nf = (t22.TS_CAMP, t22.TS_NF) if system == "teastore" else (t22.OT_CAMP, t22.OT_NF)
    qa = t22._quiet_campaign(src, nf, tmp_path / "quietA", system=system)
    qa2 = t22._quiet_campaign(src, nf, tmp_path / "quietA2", copies=4)
    val = t22._quiet_campaign(src, nf, tmp_path / "val", copies=2)
    out = tmp_path / "readout"
    assert v3.main([str(src), str(qa), str(qa2), "--system", system, "--out", str(out), "--validation", str(val)]) == 0
    md = (out / v3.OUT_MD).read_text()
    J = json.loads((out / v3.OUT_JSON).read_text())
    assert md.startswith("# Traffic sweep, %s: analysis v3 (v3.1)" % ("TeaStore" if system == "teastore" else
                                                                       "OTel Demo"))
    assert len(J["campaignsRead"]) == 3 and all(x["campaign"] in md for x in J["campaignsRead"])
    assert J["calibration"]["primary"]["perRate"] and J["validation"]["perRate"]
    assert "## Honest false alarms" in md and "bound, 0 alarms" not in md and "certify at best" in md
    assert J["scriptSha256"] == v3._sha(v3.__file__) and J["v24Sha256"] == v3._sha(v24.__file__)
    assert ("L66" in md) == (system == "otel")
    with pytest.raises(SystemExit):
        v3.main([str(src), "--system", system, "--out", str(out)])


# ----------------------------------------------------------------------------- registry and literals

V3_SRC = ROOT / "research" / "detection-time" / "sweep_analysis_v3.py"


def test_no_tunable_literal_in_v3():
    assert t24.numeric_literals(V3_SRC.read_text()) == []


def test_planted_literal_in_v3_is_caught():
    src = V3_SRC.read_text().replace('WIDEN = param3("V3_RANGE_WIDEN_STEPS")', "WIDEN = 1.5")
    assert src != V3_SRC.read_text() and any(v == 1.5 for _, v in t24.numeric_literals(src))


def test_v3_registry_entries_have_an_origin():
    """Every v3 entry: an origin type, a reference, active; the decided ones name their decision (61-68 or 49);
    nothing v3 reads is missing from the registry."""
    doc = json.loads(v3.PARAMETERS_V3.read_text())
    types_ = set(doc["originTypes"])
    names = {p["name"] for p in doc["parameters"]}
    assert v3.PARAMS_USED and v3.PARAMS_USED <= names
    assert t24.unknown_used(v3.REGISTRY, v3.PARAMS_USED) == []
    for p in doc["parameters"]:
        assert p["origin_type"] in types_ and p["origin_ref"] and p["status"] == "active", p["name"]
        if p["origin_type"] == "decision":
            assert any("decision %d" % n in p["origin_ref"] for n in (49, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70)), p["name"]
    assert "decision 67" in v3.REGISTRY["V3_NESTED_RULE"]["origin_ref"]
    assert "decision 66" in v3.REGISTRY["V3_KNOWN_LIMITATIONS"]["origin_ref"]


def test_planted_unknown_origin_in_v3_is_caught():
    reg = json.loads(json.dumps(v3.REGISTRY))
    reg["V3_ABSENT_M_GRID"]["origin_type"] = "unknown"
    assert t24.unknown_used(reg, v3.PARAMS_USED) == ["V3_ABSENT_M_GRID"]


def test_v24_unchanged_since_freeze():
    """v2.4's script and registry are byte-identical to the frozen 098f3e0, so every v2.4 readout stays reproducible."""
    for rel in ("research/detection-time/sweep_analysis_v2.py", "research/protocol/parameters.json"):
        assert (ROOT / rel).read_bytes().decode() == git_show(V24_CODE_REV, rel), rel
    assert v3.v24 is sys.modules["sweep_analysis_v2"]


# ----------------------------------------------------------------------------- the v3.1 review's fixes (F2, F3, F4, keys)

def check_no_nested_evidence(camp):
    """F2: search cpu's level rules calibrated on the leave-one-cell-out folds, but unarmed in every nested (pair) fit
    (its level data removed there): honest — with no evaluated fold, never 0; the sensor's CELF cost — (no evidence)."""
    Rr = R(camp)
    key = cr1(Rr)["keys"]["metric:search:cpu"]
    cells = Rr["cells"]
    with v24.use_system("hotel"):
        lf, fits = v3.loco_fits3(cells), v3.fits_for3(cells)
        pairs = v3.pair_fits(cells, 1.0)
        for F in pairs.values():
            F.level.pop(key, None)
        cr = v3.calibrate_rate(cells, 1.0, v24.ARMS["primary"], 0, lf, fits[1.0], pairs, 60.0)
    rows = [cr["rules"][(key, r)] for r in v3.LEVEL]
    s_ = cr["sensors"][key]
    return (all(r["status"] == "calibrated" and r["honest"] is None and r["foldsEvaluated"] == 0
                and r["nestedOutOfDetector"] == cr["cells"] for r in rows)
            and s_["placeable"] and s_["celfCost"] is None and s_["honest"] is None)


def test_no_nested_evidence_is_dash(camp, monkeypatch):
    _VAL["path"] = camp["val"]
    assert check_no_nested_evidence(camp)
    monkeypatch.setattr(v3, "HONEST_EVALUATED_ONLY", False)
    assert not check_no_nested_evidence(camp)


def test_record_status_and_container_planted(tmp_path, monkeypatch):
    """F3: ignoring the record's status uses a `missing` record's plausible rows; dropping the container filter uses
    another container's rows (F11): each caught."""
    monkeypatch.setattr(v3, "H4_RECORD_STATUS", False)
    assert not _fell_back(_ts_case(tmp_path, "st", status="missing", failures=["docker events query: timed out"]))
    monkeypatch.setattr(v3, "H4_RECORD_STATUS", True)
    monkeypatch.setattr(v3, "CONTAINER_FILTER", False)
    assert not _fell_back(_ts_case(tmp_path, "cf", container="e" * 64))
    assert not _fell_back(_ot_pause(_load("otel", [_ot_b_campaign(tmp_path / "ocf", container="cid-other")])))


def _ledger_dropped_rows(Rr):
    cal = copy.copy(Rr["cal"]["primary"])
    c = dict(cal["perRate"][1.0])
    c["rules"] = dict(c["rules"])
    k = (c["keys"][LEDGER], "spike")
    c["rules"][k] = dict(c["rules"][k], status="dropped")
    with v24.use_system("hotel"):
        return v3.p4_3(Rr["results"]["primary"]["eps"], False, False, dict(cal, perRate={1.0: c}), Rr["ctx"])


def test_p4_ledger_reading_switch(camp, monkeypatch):
    """Decision 70 sets (b) calibrated-ledger: with an armed ledger rule dropped P4 is evaluated and the rule listed;
    the alternative (a) dash-if-ledger-rule-dropped gives — there (kept as the planted defect); the readout lists the
    dropped ledger rules per rate."""
    _VAL["path"] = camp["val"]
    Rr = R(camp)
    b = _ledger_dropped_rows(Rr)[SP]["perRate"]["1"]
    monkeypatch.setattr(v3, "P4_LEDGER_READING", "dash-if-ledger-rule-dropped")
    a = _ledger_dropped_rows(Rr)[SP]["perRate"]["1"]
    assert b["holds"] is not None and b["ledgerReading"] == "calibrated-ledger" and LEDGER + "/spike" in b["ledgerDropped"]
    assert a["holds"] is None and "ledger's compared rule" in a["note"]
    e = v3.REGISTRY["V3_P4_LEDGER_READING"]
    assert e["value"] == "calibrated-ledger" and e["origin_type"] == "decision" and "decision 70" in e["origin_ref"]
    monkeypatch.setattr(v3, "P4_LEDGER_READING", "calibrated-ledger")
    md = v3.render(Rr, v3.build_json(Rr))
    assert "Dropped ledger rules per rate (decision 70" in md and "dropped ledger rules (listed, decision 70)" in md


def check_cell_keys(tmp_path):
    """Two campaigns whose cells share the cell name (A and A2): every clock row and episode stays, keyed by (campaign,
    run path)."""
    main = t24.make_main(tmp_path / "main")
    qa, qa2 = tmp_path / "quietA" / "x", tmp_path / "quietA2" / "x"
    for root in (qa, qa2):
        for b in (1, 2):
            t24.make_cell(root, NF, 1.0, b, t24.OFFSETS[b - 1])
    cells = _load("hotel", [main, qa, qa2])
    a_names = {c["cell"].split("quietA/")[-1]: c["cell"] for c in cells if "quietA/" in c["cell"]}
    for c in cells:
        if "quietA2/" in c["cell"]:
            c["cell"] = a_names[c["cell"].split("quietA2/")[-1]]        # the collision a reader could make
    with v24.use_system("hotel"):
        rows = v3.clocks_report3(cells)["perCell"]
    return len(rows) == sum(1 for c in cells if c["valid"])


def test_cell_keys(tmp_path, monkeypatch):
    assert check_cell_keys(tmp_path / "a")
    monkeypatch.setattr(v3, "CELL_KEY_POOL", False)
    assert not check_cell_keys(tmp_path / "b")
