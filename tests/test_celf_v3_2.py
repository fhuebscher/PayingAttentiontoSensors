"""Placement v3.2 (research/placement/celf_v3_2.py): the tiered-budget frontier over celf_v3's unchanged objective.

Layer: unit + synthetic end-to-end. SYNTHETIC instances only (the builders of tests/test_placement_v3.py) and the tier file
committed in 1fff401 for the schema and derivation checks; no E readout exists. Every switch of celf_v3_2 has a check that
passes and fails once the switch is planted off (CHECKS, the pattern of tests/test_placement_v3.py); celf_v3 itself is
shown unchanged (digest) and its answer is reproduced by the unrestricted cell.
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "research" / "placement", ROOT / "research" / "detection-time", Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import celf_v3 as cv  # noqa: E402
import celf_v3_2 as c2  # noqa: E402
import test_placement_v3 as tp  # noqa: E402

NO_SPLIT = {"train": None, "test": None}
REGISTRY_MIN = c2.RECURRENCE_MIN        # the registry's V32_RECURRENCE_RULE value (decision 112), read before any test patches it


@pytest.fixture(autouse=True)
def _no_registry_split(monkeypatch):
    monkeypatch.setattr(c2, "E_SPLIT", NO_SPLIT)
    # The tier / frontier tests below use ONE episode per class, so decision 112's >= 2 would empty their ground set. With
    # the threshold at 1 the rule is "has a counted fire", which changes no objective value (a sensor without a counted fire
    # has zero gain). The recurrence tests set the registry's value themselves (_min).
    monkeypatch.setattr(c2, "RECURRENCE_MIN", 1)


def _min(n=None):
    """Context: the recurrence threshold at the registry's value (decision 112) or at n."""
    import contextlib

    @contextlib.contextmanager
    def cm():
        saved = c2.RECURRENCE_MIN
        c2.RECURRENCE_MIN = REGISTRY_MIN if n is None else n
        try:
            yield
        finally:
            c2.RECURRENCE_MIN = saved
    return cm()


EFFORT_FILE = ROOT / "research" / "placement" / "declared" / "otel.effort.json"
ANY = c2.ANY
EPOCH = "otel-offpath-e-v1"
SIDS = {k: "span:svc%s:op" % k for k in "abcd"}


def tiers_syn():
    return {SIDS["a"]: {"effort": 0, "runtime": "<1%"}, SIDS["b"]: {"effort": 1, "runtime": "<1%"},
            SIDS["c"]: {"effort": 0, "runtime": ">10%"}, SIDS["d"]: {"effort": None, "runtime": None}}


def readout_syn(extra_sensors=None, upper=None):
    """Three classes, one episode each (blocks 1-3): a catches ep1 at 5 s, b ep2 at 5 s, c ep3 at 5 s, d ep1 at 1 s."""
    eps = [tp.ep("c1", 1.0, 1, [tp.fire("T", SIDS["a"], 5.0), tp.fire("T", SIDS["d"], 1.0)]),
           tp.ep("c2", 1.0, 2, [tp.fire("T", SIDS["b"], 5.0)]),
           tp.ep("c3", 1.0, 3, [tp.fire("T", SIDS["c"], 5.0)])]
    up = upper or {}
    sensors = {SIDS[k]: tp.sensor("T", upper=up.get(k, 0.5)) for k in "abcd"}
    sensors.update(extra_sensors or {})
    return tp.readout(eps, sensors)


def cell(res, e, r):
    return next(c for c in res["grid"] if c["maxEffort"] == e and c["maxRuntime"] == r)


def D(res, e, r, budget="inf"):
    return cell(res, e, r)["points"][budget]["D"]


# ----------------------------------------------------------------------------- the checks (each with a plant)

def chk_null_unknown():
    r = c2.frontier_rate(readout_syn(), 1.0, tiers_syn(), with_held_out=False)
    # d (unknown tiers) is admitted only under the `any` caps: (0, any) holds a and c only
    return (SIDS["d"] not in cell(r, 0, ANY)["points"]["inf"]["set"] and SIDS["d"] not in cell(r, ANY, "<1%")["points"]["inf"]["set"]
            and SIDS["d"] in cell(r, ANY, ANY)["points"]["inf"]["set"] and cell(r, 0, ANY)["admitted"] == 2)


def chk_cap_filter():
    r = c2.frontier_rate(readout_syn(), 1.0, tiers_syn(), with_held_out=False)
    return D(r, 0, ANY) > D(r, 1, ANY) > D(r, ANY, ANY) and cell(r, 0, "<1%")["admitted"] == 1


def chk_shared_costs():
    """No-evidence sensors cost the rate's largest evidenced bound over the FULL V_r in every cell: the charged cost of
    each point equals the sum of the rate's one cost table."""
    sens = {SIDS["d"]: tp.sensor("T", upper=None)}                  # d has no evidence: the fill
    J = readout_syn(sens, upper={"a": 0.2, "b": 0.3, "c": 7.0})    # the largest evidenced bound (c) is cap-dependent
    t = tiers_syn()
    t[SIDS["d"]]["runtime"] = "<1%"                                 # d admitted under (any, '<1%'), c (>10%) is not
    r = c2.frontier_rate(J, 1.0, t, with_held_out=False)
    ok = SIDS["d"] in cell(r, ANY, "<1%")["points"]["inf"]["set"] and SIDS["c"] not in cell(r, ANY, "<1%")["points"]["inf"]["set"]
    for c in r["grid"]:
        for p in c["points"].values():
            if "set" in p:
                ok &= math.isclose(p["charged"], math.fsum(r["costs"][s] for s in p["set"]), abs_tol=1e-12)
    return ok and r["costs"][SIDS["d"]] == 7.0


def chk_runtime_first_step():
    doc = json.loads(EFFORT_FILE.read_text())
    steps = c2.step_tiers(doc)
    return (c2.runtime_tier(["selected", "async", "full"], steps) == ">10%"
            and c2.runtime_tier(["none", "selected", "async", "full"], steps) == "<1%"
            and c2.runtime_tier([], steps) is None)


def chk_cumulative():
    """Decision 101: an async sensor also pays the selected step (0.17 + 0.058 = 0.228: '>10%', not the step's own
    '1-10%'), and a set costs its latest member's cumulative share."""
    doc = json.loads(EFFORT_FILE.read_text())
    steps = c2.step_tiers(doc)
    t = {"a": {"cumulativeShare": 0.0}, "b": {"cumulativeShare": 0.228}, "c": {"cumulativeShare": None}}
    two = c2.set_runtime(["a", "b"], t)
    return (steps["async"] == ">10%" and steps["full"] == ">10%" and steps["none"] == "<1%"
            and two["cumulativeShare"] == 0.228 and two["tier"] == ">10%" and c2.set_runtime([], t)["tier"] == "<1%"
            and c2.set_runtime(["a", "c"], t)["tier"] is None)


def chk_split_registry():
    saved = c2.E_SPLIT
    c2.E_SPLIT = {"train": [1, 2, 3], "test": [4, 5]}
    try:
        c2.check_split_registry({"train": [1, 2], "test": [3, 4, 5]})
    except SystemExit:
        return True
    finally:
        c2.E_SPLIT = saved
    return False


def chk_validate():
    doc = json.loads(EFFORT_FILE.read_text())
    bad = copy.deepcopy(doc)
    bad["sensors"][5]["effortTier"] = 3
    return _loads_refused(bad)


def _loads_refused(doc):
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as d:
        f = Path(d) / "t.json"
        f.write_text(json.dumps(doc))
        try:
            c2.load_tiers(f, "postures")
        except c2.TierError:
            return True
        return False


def _v32_with(selection):
    """A readout's v32 block with this blockSelection and the live registry digest (F5 refuses a readout without it)."""
    return {"blockSelection": selection, "parametersV32Sha256": c2.sha256(c2.PARAMETERS_V32)}


def _readout_doc(**kw):
    J = readout_syn()
    sha = c2.sha256(ROOT / "research" / "detection-time" / "sweep_analysis_v3_2.py")
    for e in J["episodes"]:
        e["studyEpoch"] = EPOCH
    J.update(version="3.2", v31ScriptSha256=c2.PINNED_V31_SHA256, scriptSha256=sha,
             v32={"blockSelection": {"blocks": [1, 2, 3], "applies": [EPOCH], "splitSha256": None},
                  "parametersV32Sha256": c2.sha256(c2.PARAMETERS_V32)})
    J.update(kw)
    return J


def chk_require_split():
    """An unsplit readout is refused, and so is a readout whose recorded blocks do not describe its episodes."""
    unsplit = _readout_doc(v32=_v32_with({"blocks": None}))
    stray = _readout_doc(v32=_v32_with({"blocks": [1, 2], "applies": [EPOCH]}))                 # it holds block 3
    other = _readout_doc()
    other["episodes"][0]["studyEpoch"] = "otel-traffic-sweep-v1"                               # a legacy epoch's episode
    out = []
    for J in (unsplit, stray, other):
        try:
            c2.check_readout(J, allow_unpinned=True)
            out.append(False)
        except SystemExit:
            out.append(True)
    return all(out)


def chk_pins():
    J = _readout_doc(v31ScriptSha256="0" * 64)
    try:
        c2.check_readout(J, allow_unpinned=True)
    except SystemExit:
        return True
    return False


EARLY, STEADY, TWO = "log:appear:early", "log:kafka:steady", "log:kafka:two"


def recurrence_readout():
    """The review's synthetic case: one class, three training episodes. EARLY appears at 0.4 s in ONE episode, STEADY fires
    at 43.5 s in all three, TWO at 50 s in two. Every sensor costs 2.9957/h at T_r = 1 h: 3/T_r affords one, 6/T_r two."""
    c = 2.9957
    eps = [tp.ep("c1", 1.0, 1, [tp.fire("T", EARLY, 0.4), tp.fire("T", STEADY, 43.5), tp.fire("T", TWO, 50.0)]),
           tp.ep("c1", 1.0, 2, [tp.fire("T", STEADY, 43.5), tp.fire("T", TWO, 50.0)]),
           tp.ep("c1", 1.0, 3, [tp.fire("T", STEADY, 43.5)])]
    return tp.readout(eps, {s: tp.sensor("T", upper=c) for s in (EARLY, STEADY, TWO)}, hours=1.0)


def chk_recurrence():
    """Decision 112: a sensor firing in exactly 1 training episode of a class is excluded and one firing in 2 is admitted,
    at every budget point; the 1-episode early `appear` would win a one-slot budget without the rule."""
    with _min():
        r = c2.frontier_rate(recurrence_readout(), 1.0, {}, with_held_out=False)
    sets = {n: p["set"] for n, p in cell(r, ANY, ANY)["points"].items()}
    rec = r["recurrence"]
    anywhere = {s for c in r["grid"] for p in c["points"].values() for s in p.get("set", [])}
    return (sets["3/T_r"] == [STEADY] and EARLY not in anywhere and TWO in rec["recurringByClass"]["c1"]
            and rec["recurringByClass"]["c1"] == sorted([STEADY, TWO]) and rec["removedWithCountedFire"] == 1
            and rec["removedWithCountedFireIds"] == [EARLY] and sets["inf"] == [STEADY])


CHECKS = {"RECURRENCE_FILTER": chk_recurrence, "CUMULATIVE_RUNTIME": chk_cumulative, "SPLIT_FROM_REGISTRY": chk_split_registry,
          "TIER_NULL_UNKNOWN": chk_null_unknown, "CAP_FILTER": chk_cap_filter, "SHARED_COSTS": chk_shared_costs,
          "RUNTIME_FROM_FIRST_STEP": chk_runtime_first_step, "VALIDATE_TIERS": chk_validate,
          "REQUIRE_SPLIT": chk_require_split, "CHECK_PINS": chk_pins}


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, monkeypatch):
    assert CHECKS[flag](), flag
    monkeypatch.setattr(c2, flag, False)
    assert not CHECKS[flag](), flag


def test_every_switch_has_a_check():
    assert set(c2.SWITCHES) == set(CHECKS)


# ----------------------------------------------------------------------------- frontier, comparators, objective

def test_frontier_monotone_and_named_points():
    r = c2.frontier_rate(readout_syn(), 1.0, tiers_syn())
    assert len(r["grid"]) == 16 and {c["maxEffort"] for c in r["grid"]} == {0, 1, 2, ANY}
    assert r["nonMonotone"] == []
    # more candidates, never a worse set here; the ledger-only budget 0 charges nothing
    assert D(r, ANY, ANY) <= D(r, 1, ANY) <= D(r, 0, ANY)
    assert cell(r, ANY, ANY)["points"]["0"]["set"] == [] and cell(r, ANY, ANY)["points"]["0"]["charged"] == 0
    for c in r["grid"]:
        assert list(c["points"]) == ["0", "3/T_r", "6/T_r", "6/h", "inf"]
        for p in c["points"].values():
            assert "heldOut" in p and p["DLedger"] >= p["D"] - 1e-12


def test_unrestricted_cell_is_celf_v3_unchanged():
    """The (any, any) cell reproduces celf_v3.run's primary arm: the objective, the solver and the costs are celf_v3's."""
    J = readout_syn()
    r = c2.frontier_rate(J, 1.0, tiers_syn(), with_held_out=False)
    base = cv.run(J, arms={"primary": cv.ARMS["primary"]})["arms"]["primary"]["1"]
    inf = next(p for p in base["pareto"] if p["budget"] == "inf")
    mine = cell(r, ANY, ANY)["points"]["inf"]
    assert sorted(mine["set"]) == sorted(inf["set"]) and math.isclose(mine["D"], inf["D"], abs_tol=1e-12)
    assert r["groundSet"] == base["groundSet"] and r["costs"] == base["costs"]


def test_out_of_the_box_comparator_and_degenerate_axis():
    r = c2.frontier_rate(readout_syn(), 1.0, tiers_syn(), with_held_out=False)
    ootb = r["comparators"]["out of the box"]
    assert ootb["size"] == 2 and ootb["describe"]["ttd"]["D"] == pytest.approx(D(r, 0, ANY))  # a and c: same set as the cap
    assert not r["effortAxis"]["degenerate"] and SIDS["b"] in r["effortAxis"]["activeAboveTier0OrUnknown"]
    # every counted-fire sensor at tier 0: the effort axis is degenerate (reported, not engineered around)
    t0 = {k: dict(v, effort=0, runtime=v["runtime"] or "<1%") for k, v in tiers_syn().items()}
    r0 = c2.frontier_rate(readout_syn(), 1.0, t0, with_held_out=False)
    assert r0["effortAxis"]["degenerate"] and "does not change" in r0["effortAxis"]["note"]
    assert D(r0, 0, ANY) == D(r0, ANY, ANY)


def test_runtime_caveat_and_percentage_shares(tmp_path):
    tiers, meta = c2.load_tiers(EFFORT_FILE, "postures")
    cs = meta["cumulativeStepShares"]
    assert cs["selected"] == pytest.approx(0.17) and cs["async"] == pytest.approx(0.228) and cs["full"] == pytest.approx(0.288)
    assert "CUMULATIVE" in meta["runtimeCaveat"]
    doc = json.loads(EFFORT_FILE.read_text())
    doc["postureCostEvidence"]["steps"]["selected_to_async"]["share_of_none_level"] = 5.8        # a percentage
    p = tmp_path / "t.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(c2.TierError, match="fraction"):
        c2.load_tiers(p, "postures")


def test_missing_ground_set_sensors_have_unknown_tiers():
    t = tiers_syn()
    del t[SIDS["c"]]
    r = c2.frontier_rate(readout_syn(), 1.0, t, with_held_out=False)
    assert r["tiersMissingForGroundSet"] == [SIDS["c"]] and SIDS["c"] not in cell(r, 2, ">10%")["points"]["inf"]["set"]
    assert SIDS["c"] in cell(r, ANY, ANY)["points"]["inf"]["set"]


def test_monotone_violation_detector():
    cells = {(0, "<1%"): {"inf": 10.0}, (1, "<1%"): {"inf": 12.0}, (1, ANY): {"inf": 9.0}}
    v = c2.monotone_violations(cells)
    assert v == [{"stricter": [0, "<1%"], "relaxed": [1, "<1%"], "budget": "inf", "DStricter": 10.0, "DRelaxed": 12.0}]
    assert c2.monotone_violations({(0, "<1%"): {"inf": 10.0}, (1, ANY): {"inf": 10.0}}) == []


# ----------------------------------------------------------------------------- the tier file

def test_frontier_points_report_their_set_level_runtime_cost():
    t = tiers_syn()
    for k, (cum, tier) in {"a": (0.0, "<1%"), "b": (0.0, "<1%"), "c": (0.228, ">10%"), "d": (None, None)}.items():
        t[SIDS[k]]["cumulativeShare"] = cum
        t[SIDS[k]]["runtime"] = tier
    r = c2.frontier_rate(readout_syn(), 1.0, t, with_held_out=False)
    assert cell(r, ANY, ANY)["points"]["inf"]["runtimeCost"]["tier"] is None            # d unknown: no tier for the set
    assert cell(r, ANY, "<1%")["points"]["inf"]["runtimeCost"] == {"cumulativeShare": 0.0, "tier": "<1%",
                                                                    "unknownMembers": 0}
    p = cell(r, 0, ">10%")["points"]["inf"]["runtimeCost"]
    assert p["cumulativeShare"] == 0.228 and p["tier"] == ">10%"


def test_registry_split_binds_the_split_file(monkeypatch):
    monkeypatch.setattr(c2, "E_SPLIT", {"train": [1, 2, 3], "test": [4, 5]})
    c2.check_split_registry({"train": [3, 2, 1], "test": [5, 4]})
    with pytest.raises(SystemExit, match="registry split"):
        c2.check_split_registry({"train": [1, 2], "test": [3]})


def test_training_readout_with_held_out_episodes_is_refused():
    J = _readout_doc()
    J["episodes"][0]["heldOut"] = True
    with pytest.raises(SystemExit, match="held-out"):
        c2.check_readout(J, allow_unpinned=True)


def test_real_effort_file_validates_and_derives_runtime_tiers():
    for catalog in c2.TIERS["postureCatalogs"]:
        tiers, meta = c2.load_tiers(EFFORT_FILE, catalog)
        assert meta["sensors"] == 1705 and len(tiers) == 1704          # the ledger id is never a candidate
        raw = json.loads(EFFORT_FILE.read_text())["sensors"]
        want = {"none": "<1%", "selected": ">10%", "async": ">10%", "full": ">10%"}      # decision 101: cumulative
        for s in raw:
            if s["id"].startswith("ledger:"):
                continue
            first = next(p for p in ("none", "selected", "async", "full") if p in s[catalog])
            assert tiers[s["id"]]["runtime"] == want[first], s["id"]
            assert tiers[s["id"]]["effort"] == s["effortTier"]
    t3, _ = c2.load_tiers(EFFORT_FILE, "postures")
    t_cur, _ = c2.load_tiers(EFFORT_FILE, "postureCurrentCatalog")
    assert sum(1 for k in t3 if t3[k]["firstPosture"] != t_cur[k]["firstPosture"]) > 0   # the catalogs disagree on some ids
    from collections import Counter
    assert Counter(v["effort"] for v in t3.values()) == Counter({0: 1587, 1: 117})


@pytest.mark.parametrize("edit", [
    lambda d: d["sensors"][3].__setitem__("effortTier", 3),
    lambda d: d["sensors"][3].__setitem__("effortTier", "0"),
    lambda d: d["sensors"][3].__setitem__("runtimeTier", "5%"),
    lambda d: d["sensors"][3].__setitem__("postures", ["selected", "full"]),
    lambda d: d["sensors"][3].__setitem__("postures", ["bogus"]),
    lambda d: d["sensors"][4].__setitem__("id", d["sensors"][3]["id"]),
    lambda d: d.__setitem__("schemaVersion", 2),
    lambda d: d["postureCatalogs"].pop("v3"),
    lambda d: d["postureCostEvidence"]["steps"]["none_to_selected"].__setitem__("share_of_none_level", "x"),
    lambda d: d.__setitem__("sensors", []),
    lambda d: d["sensors"][3].pop("effortTier")])
def test_bad_tier_files_are_refused(edit, tmp_path):
    doc = json.loads(EFFORT_FILE.read_text())
    edit(doc)
    p = tmp_path / "t.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(c2.TierError):
        c2.load_tiers(p, "postures")


def test_a_declared_runtime_tier_overrides_the_derivation(tmp_path):
    doc = json.loads(EFFORT_FILE.read_text())
    sid = doc["sensors"][3]["id"]
    doc["sensors"][3]["runtimeTier"] = ">10%"
    p = tmp_path / "t.json"
    p.write_text(json.dumps(doc))
    tiers, _ = c2.load_tiers(p, "postures")
    assert tiers[sid]["runtime"] == ">10%" and tiers[sid]["runtimeBasis"] == "declared runtimeTier"


def test_unknown_catalog_is_refused():
    with pytest.raises(c2.TierError):
        c2.load_tiers(EFFORT_FILE, "other")


# ----------------------------------------------------------------------------- inputs, pins, CLI

def test_v32_is_frozen_on_the_installed_reader_and_registry():
    """The freeze (FREEZE_V32_20261013.md): both pins equal the installed files; an edited reader or registry is refused."""
    assert c2.PINNED_V32_SHA256 == c2.sha256(ROOT / "research" / "detection-time" / "sweep_analysis_v3_2.py")
    assert c2.PINNED_PARAMETERS_V32_SHA256 == c2.sha256(c2.PARAMETERS_V32)
    J = _readout_doc()
    assert c2.check_readout(J) == [1, 2, 3]                            # frozen: no flag needed
    with pytest.raises(SystemExit, match="scriptSha256"):
        c2.check_readout(dict(J, scriptSha256="1" * 64))               # planted: a readout of another reader


def test_frozen_celf_and_readout_checks(monkeypatch):
    assert c2.check_frozen_celf() == c2.PINNED_CELF_SHA256 == cv_sha()
    monkeypatch.setattr(c2, "PINNED_V32_SHA256", None)                  # the unpinned branch, as before the freeze
    J = _readout_doc()
    assert c2.check_readout(J, allow_unpinned=True) == [1, 2, 3]
    with pytest.raises(SystemExit, match="not frozen"):
        c2.check_readout(J)                                        # unpinned reader needs the flag
    with pytest.raises(SystemExit, match="not v3.2"):
        c2.check_readout(dict(J, version="3"), allow_unpinned=True)
    with pytest.raises(SystemExit, match="scriptSha256"):
        c2.check_readout(dict(J, scriptSha256="1" * 64), allow_unpinned=True)
    with pytest.raises(SystemExit, match="every block"):
        c2.check_readout(dict(J, v32=_v32_with({"blocks": None})), allow_unpinned=True)
    with pytest.raises(SystemExit, match="label alone"):
        c2.check_readout(dict(J, v32=_v32_with({"blocks": [1, 2], "applies": [EPOCH]})), allow_unpinned=True)
    assert c2.check_readout(dict(J, v32=_v32_with({"blocks": None})), allow_unpinned=True, allow_unsplit=True) is None


def cv_sha():
    return c2.sha256(ROOT / "research" / "placement" / "celf_v3.py")


def test_main_writes_once_and_checks_the_split(tmp_path, capsys):
    J = _readout_doc()
    rd = tmp_path / "readout.json"
    rd.write_text(json.dumps(J))
    tiers = tmp_path / "tiers.json"
    doc = json.loads(EFFORT_FILE.read_text())
    doc["sensors"] = [dict(doc["sensors"][1], id=SIDS["a"]), dict(doc["sensors"][1], id=SIDS["b"], effortTier=1),
                      dict(doc["sensors"][1], id=SIDS["c"]), dict(doc["sensors"][0])]
    tiers.write_text(json.dumps(doc))
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2, 3], "test": [4]}))
    out = tmp_path / "out" / "frontier.json"
    argv = [str(rd), "--tiers", str(tiers), "--tier-catalog", "postures", "--out", str(out), "--split", str(split),
            "--allow-unpinned"]
    assert c2.main(argv) == 0
    res = json.loads(out.read_text())
    assert res["split"] == {"trainBlocks": [1, 2, 3], "test": [4], "unsplit": False} and "1" in res["rates"]
    assert res["tiers"]["sha256"] == c2.sha256(tiers) and res["inputs"]["pinnedV32"] == c2.PINNED_V32_SHA256
    assert len(res["rates"]["1"]["grid"]) == 16
    with pytest.raises(SystemExit, match="existing path"):
        c2.main(argv)
    bad = tmp_path / "split2.json"
    bad.write_text(json.dumps({"train": [1, 3], "test": [3]}))
    with pytest.raises(SystemExit, match="--split is required"):
        c2.main([str(rd), "--tiers", str(tiers), "--tier-catalog", "postures", "--out", str(tmp_path / "o3.json"),
                 "--allow-unpinned"])
    rd2 = tmp_path / "readout2.json"
    rd2.write_text(json.dumps(dict(J, v32=dict(J["v32"], epochsRead={EPOCH: 5}))))
    with pytest.raises(SystemExit, match="calls? for postureCurrentCatalog"):
        c2.main([str(rd2), "--tiers", str(tiers), "--tier-catalog", "postures", "--out", str(tmp_path / "o4.json"),
                 "--split", str(split), "--allow-unpinned"])
    with pytest.raises(SystemExit, match="overlap"):
        c2.main([str(rd), "--tiers", str(tiers), "--tier-catalog", "postures", "--out", str(tmp_path / "o2.json"),
                 "--split", str(bad), "--allow-unpinned"])


def test_celf_v3_is_untouched():
    assert cv_sha() == c2.PINNED_CELF_SHA256 == "3823722125e9796e6716a830b01d12c69177c7ab6b0a0d7a5fa3984ab6205e97"


# ----------------------------------------------------------------------------- decision 112: recurrence rule, 6/T_r

def test_registry_value_is_decision_112_and_read_by_the_code():
    assert REGISTRY_MIN == 2 == c2.RECURRENCE_RULE["minEpisodesPerClass"]
    reg = c2._registry()["V32_RECURRENCE_RULE"]
    assert reg == {"minEpisodesPerClass": 2}
    entry = next(p for p in json.loads(c2.PARAMETERS_V32.read_text())["parameters"] if p["name"] == "V32_RECURRENCE_RULE")
    assert entry["origin_type"] == "decision" and entry["status"] == "active" and "Decision 112" in entry["origin_ref"]


def test_one_episode_early_appear_loses_to_the_recurring_sensor_and_wins_without_the_rule(monkeypatch):
    """The review's case: EARLY at 0.4 s in one training episode vs STEADY at 43.5 s in three. With the rule, EARLY is no
    candidate anywhere and the one-slot set is STEADY; with the switch off EARLY takes the slot."""
    with _min():
        r = c2.frontier_rate(recurrence_readout(), 1.0, {}, with_held_out=False)
        pts = cell(r, ANY, ANY)["points"]
        assert pts["3/T_r"]["set"] == [STEADY] and pts["6/T_r"]["set"] == [STEADY] and pts["inf"]["set"] == [STEADY]
        assert r["recurrence"]["removedWithCountedFire"] == 1 and r["recurrence"]["removedFromGroundSet"] == 1
        assert r["recurrence"]["episodesPerClass"] == {"c1": 3} and r["recurrence"]["recurring"] == 2
        assert cell(r, ANY, ANY)["admittedByCaps"] == 3 and cell(r, ANY, ANY)["admitted"] == 2
        monkeypatch.setattr(c2, "RECURRENCE_FILTER", False)
        r0 = c2.frontier_rate(recurrence_readout(), 1.0, {}, with_held_out=False)
    p0 = cell(r0, ANY, ANY)["points"]
    assert p0["3/T_r"]["set"] == [EARLY] and set(p0["6/T_r"]["set"]) == {EARLY, STEADY}
    assert r0["recurrence"]["removedWithCountedFire"] == 0 and r0["recurrence"]["switch"] is False


def test_recurrence_counts_per_class_after_the_own_exclusion():
    """`counted` is celf_v3's: an own fire of the class does not count (decision 84), and episodes are counted within one
    class, not pooled: Y fires in one c1 and one c2 episode (not recurring); X's two c1 fires are own (not counted) and its
    one c2 fire is a single episode; Z's own c1 fires do not count but it fires in two c2 episodes (recurring, via c2)."""
    X, Y, Z = "span:x:op", "span:y:op", "span:z:op"
    eps = [tp.ep("c1", 1.0, 1, [tp.fire("T", X, 5.0, own=True), tp.fire("T", Y, 5.0), tp.fire("T", Z, 5.0, own=True)]),
           tp.ep("c1", 1.0, 2, [tp.fire("T", X, 5.0, own=True), tp.fire("T", Z, 5.0, own=True)]),
           tp.ep("c2", 1.0, 1, [tp.fire("T", X, 5.0), tp.fire("T", Y, 5.0), tp.fire("T", Z, 5.0)]),
           tp.ep("c2", 1.0, 2, [tp.fire("T", Z, 5.0)])]
    J = tp.readout(eps, {s: tp.sensor("T", upper=1.0) for s in (X, Y, Z)}, hours=1.0)
    with _min():
        r = c2.frontier_rate(J, 1.0, {}, with_held_out=False)
    rec = r["recurrence"]
    assert rec["recurringByClass"] == {"c1": [], "c2": [Z]} and rec["removedWithCountedFireIds"] == [X, Y]
    assert rec["withCountedFire"] == 3 and rec["recurring"] == 1


def test_a_sensor_in_exactly_two_episodes_is_admitted_one_in_one_is_not():
    with _min():
        r = c2.frontier_rate(recurrence_readout(), 1.0, {}, with_held_out=False)
    rec = r["recurrence"]
    assert TWO in rec["recurringByClass"]["c1"] and EARLY not in rec["recurringByClass"]["c1"]
    assert TWO in cell(r, ANY, ANY)["points"]["inf"]["set"] or TWO in r["recurrence"]["recurringByClass"]["c1"]
    assert cell(r, ANY, ANY)["admitted"] == 2                                   # STEADY and TWO


def test_6_over_T_r_is_twice_the_knot_and_has_the_same_hours():
    b = c2.named_budgets(0.2)
    assert b["3/T_r"] == pytest.approx(cv.LITERAL_NULL_EVENTS / 0.2) and b["6/T_r"] == pytest.approx(2 * b["3/T_r"])
    assert b["6/T_r"] == pytest.approx(2 * cv.LITERAL_NULL_EVENTS / 0.2) and b["6/h"] == cv.FAR_BUDGET_PER_HOUR
    assert list(b) == ["0", "3/T_r", "6/T_r", "6/h", "inf"]
    nb = c2.named_budgets(None)
    assert nb["3/T_r"] is None and nb["6/T_r"] is None and nb["0"] == 0.0


def test_a_rate_without_hours_has_no_knot_points_and_says_so():
    J = recurrence_readout()
    for x in J["calibration"]["primary"]["perRate"].values():
        x["hours"] = None
    with _min():
        r = c2.frontier_rate(J, 1.0, {}, with_held_out=False)
    pts = cell(r, ANY, ANY)["points"]
    assert "set" not in pts["3/T_r"] and "no 3/T_r" in pts["3/T_r"]["note"] and "no 6/T_r" in pts["6/T_r"]["note"]
    assert "set" in pts["6/h"]


def test_main_records_the_rule_and_the_removal_count(tmp_path):
    J = _readout_doc()
    rd = tmp_path / "readout.json"
    rd.write_text(json.dumps(J))
    tiers = tmp_path / "tiers.json"
    doc = json.loads(EFFORT_FILE.read_text())
    doc["sensors"] = [dict(doc["sensors"][1], id=SIDS["a"])]
    tiers.write_text(json.dumps(doc))
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2, 3], "test": [4]}))
    out = tmp_path / "f.json"
    with _min():
        c2.main([str(rd), "--tiers", str(tiers), "--tier-catalog", "postures", "--out", str(out), "--split", str(split),
                 "--allow-unpinned"])
    res = json.loads(out.read_text())
    assert res["recurrenceRule"] == {"minEpisodesPerClass": 2, "switch": True} and res["switches"]["RECURRENCE_FILTER"] is True
    rec = res["rates"]["1"]["recurrence"]               # readout_syn: one episode per class, so every counted sensor is removed
    assert rec["recurring"] == 0 and rec["removedWithCountedFire"] == 4 and rec["removedFromGroundSet"] == 4
    assert all(p["set"] == [] for c in res["rates"]["1"]["grid"] for p in c["points"].values())


# ----------------------------------------------------------------------------- F5: the registry digest is pinned

def test_registry_digest_pin_in_both_states(monkeypatch):
    live = c2.sha256(c2.PARAMETERS_V32)
    monkeypatch.setattr(c2, "PINNED_PARAMETERS_V32_SHA256", None)      # the unpinned branch, as before the freeze
    monkeypatch.setattr(c2, "PINNED_V32_SHA256", None)
    J = _readout_doc()
    assert c2.check_readout(J, allow_unpinned=True) == [1, 2, 3]
    for bad in ("q" * 64, None):                                        # planted mismatch / a readout without the digest
        v = dict(J["v32"], parametersV32Sha256=bad)
        with pytest.raises(SystemExit, match="readout recorded parametersV32Sha256"):
            c2.check_readout(dict(J, v32=v), allow_unpinned=True)
    # unpinned needs --allow-unpinned for the registry as it does for the reader's digest
    monkeypatch.setattr(c2, "PINNED_V32_SHA256", c2.sha256(ROOT / "research" / "detection-time" / "sweep_analysis_v3_2.py"))
    with pytest.raises(SystemExit, match="registry is not frozen"):
        c2.check_readout(J)
    # pinned: the live registry and the readout's record both equal the pin
    monkeypatch.setattr(c2, "PINNED_PARAMETERS_V32_SHA256", live)
    assert c2.check_readout(J) == [1, 2, 3]
    with pytest.raises(SystemExit, match="readout recorded parametersV32Sha256"):
        c2.check_readout(dict(J, v32=dict(J["v32"], parametersV32Sha256="q" * 64)))
    monkeypatch.setattr(c2, "PINNED_PARAMETERS_V32_SHA256", "0" * 64)    # the live registry was edited after the freeze
    with pytest.raises(SystemExit, match="live registry .* not the frozen"):
        c2.check_readout(J)
    monkeypatch.setattr(c2, "CHECK_PINS", False)
    assert c2.check_readout(J) == [1, 2, 3]                              # the planted switch: not enforced


def test_main_records_the_registry_pin_state(tmp_path):
    J = _readout_doc()
    rd = tmp_path / "readout.json"
    rd.write_text(json.dumps(dict(J, v32=dict(J["v32"], parametersV32Sha256="q" * 64))))
    tiers = tmp_path / "tiers.json"
    doc = json.loads(EFFORT_FILE.read_text())
    doc["sensors"] = [dict(doc["sensors"][1], id=SIDS["a"])]
    tiers.write_text(json.dumps(doc))
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2, 3], "test": [4]}))
    with pytest.raises(SystemExit, match="readout recorded parametersV32Sha256"):
        c2.main([str(rd), "--tiers", str(tiers), "--tier-catalog", "postures", "--out", str(tmp_path / "x.json"),
                 "--split", str(split), "--allow-unpinned"])
    rd.write_text(json.dumps(J))
    out = tmp_path / "y.json"
    c2.main([str(rd), "--tiers", str(tiers), "--tier-catalog", "postures", "--out", str(out), "--split", str(split),
             "--allow-unpinned"])
    assert json.loads(out.read_text())["inputs"]["pinnedParametersV32"] == c2.PINNED_PARAMETERS_V32_SHA256
