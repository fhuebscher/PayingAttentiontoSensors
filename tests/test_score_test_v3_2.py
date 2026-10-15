"""Campaign E block-split scorer (research/placement/score_test_v3_2.py): frozen tiered sets scored on the TEST blocks.

Layer: unit + synthetic end-to-end, SYNTHETIC readouts only (the builders of tests/test_placement_v3.py): a training readout
of blocks 1-2, a scoring readout of blocks 1-4, the placement written by celf_v3_2.main from the training readout. D_E is
re-derived by hand in the test (independent of the objective code). Every switch has a check that passes and fails once the
switch is planted off. No E cell exists; the pass rule is not chosen (null), the rule form is exercised with sample rules.
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
import score_test_v3_2 as s2  # noqa: E402
import test_placement_v3 as tp  # noqa: E402

EFFORT_FILE = ROOT / "research" / "placement" / "declared" / "otel.effort.json"
A, B_, C_ = "span:svca:op", "span:svcb:op", "span:svcc:op"
ANY = c2.ANY
DET = ROOT / "research" / "detection-time"
HOLD = 60.0


EPOCH = "otel-offpath-e-v1"


NO_SPLIT = {"train": None, "test": None}


@pytest.fixture(autouse=True)
def _no_registry_split(monkeypatch):
    monkeypatch.setattr(c2, "E_SPLIT", NO_SPLIT)
    monkeypatch.setattr(s2, "E_SPLIT", NO_SPLIT)


def _versions(J, blocks, test_blocks=None):
    for e in J["episodes"]:
        e["studyEpoch"] = EPOCH
        e["heldOut"] = test_blocks is not None and e["block"] in test_blocks
    J.update(version="3.2", v31ScriptSha256=c2.PINNED_V31_SHA256, scriptSha256=c2.sha256(DET / "sweep_analysis_v3_2.py"),
             v24Sha256=c2.sha256(DET / "sweep_analysis_v2.py"), detectionTimeSha256=c2.sha256(DET / "detection_time.py"),
             v1Sha256=c2.sha256(DET / "sweep_analysis.py"), v32={"blockSelection": {"blocks": blocks, "applies": [EPOCH], "splitSha256": None,
                                                        "testBlocks": sorted(test_blocks) if test_blocks else None},
                                                "parametersV32Sha256": c2.sha256(c2.PARAMETERS_V32)}, campaigns=["/c/e"])
    return J


def readout(blocks, fires_of, selection=None, placeable=None, test_blocks=None):
    """Episodes of two classes in each block; fires_of(regime, block) -> [(sensor, ttd)]."""
    eps = []
    for b in blocks:
        for regime in ("c1", "c2"):
            eps.append(tp.ep(regime, 1.0, b, [tp.fire("T", s, t) for s, t in fires_of(regime, b)], hold=HOLD,
                             harness="B"))
    sensors = {s: tp.sensor("T", upper=0.5) for s in (A, B_, C_)}
    for s, ok in (placeable or {}).items():
        sensors[s]["placeable"] = ok
    return _versions(tp.readout(eps, sensors), selection if selection is not None else sorted(blocks), test_blocks)


def fires(regime, b):
    """Training (blocks 1-2): a catches c1 at 5, b catches c2 at 10. Test (3-4): a still catches c1 at 5 (block 3) or
    misses (block 4); b catches c2 at 30; c catches c1 at 2 in the test blocks only (never chosen in training)."""
    out = []
    if regime == "c1":
        if b != 4:
            out.append((A, 5.0))
        if b >= 3:
            out.append((C_, 2.0))
    else:
        out.append((B_, 10.0 if b <= 2 else 30.0))
    return out


TIERS_DOC = None


def tier_file(tmp_path):
    doc = json.loads(EFFORT_FILE.read_text())
    base = dict(doc["sensors"][1])
    doc["sensors"] = [dict(base, id=A), dict(base, id=B_, effortTier=1), dict(base, id=C_)]
    p = tmp_path / "tiers.json"
    p.write_text(json.dumps(doc))
    return p


@pytest.fixture()
def world(tmp_path):
    train = readout([1, 2], fires)
    full = readout([1, 2, 3, 4], fires, test_blocks={3, 4})
    tr, sc = tmp_path / "train.json", tmp_path / "score.json"
    tr.write_text(json.dumps(train))
    sc.write_text(json.dumps(full))
    pl = tmp_path / "placement.json"
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2], "test": [3, 4]}))
    assert c2.main([str(tr), "--tiers", str(tier_file(tmp_path)), "--tier-catalog", "postures", "--out", str(pl),
                    "--split", str(split), "--allow-unpinned"]) == 0
    return {"train": train, "full": full, "tr": tr, "sc": sc, "pl": pl, "tmp": tmp_path,
            "P": json.loads(pl.read_text()), "psha": c2.sha256(pl), "tsha": c2.sha256(tr)}


def run(w, J=None, P=None, test=(3, 4), training="ok", rule=None, psha=None, T=None):
    J = J or w["full"]
    P = P or w["P"]
    tr = (T or w["train"], w["tsha"]) if training == "ok" else ((w["full"], c2.sha256(w["sc"])) if training == "bad" else None)
    return s2.score(J, P, psha or w["psha"], list(test), tr, rule, allow_unpinned=True)


def hand_D(per_class_penalties):
    """D with the ledger absent: uniform over classes, then over a class's episodes."""
    return sum(sum(v) / len(v) for v in per_class_penalties.values()) / len(per_class_penalties)


# ----------------------------------------------------------------------------- the scoring itself

def test_test_blocks_only_and_hand_derived_values(world):
    res = run(world)
    r = res["rates"]["1"]
    assert r["episodesScored"] == 4 and r["testBlocks"] == [3, 4] and r["classCounts"] == {"c1": 2, "c2": 2}
    led = r["sets"]["ledger alone"]
    assert led["D"] == pytest.approx(HOLD)                     # the ledger catches nothing: every episode a miss
    # the unrestricted frontier set at the inf budget is the training placement's: {a, b}
    S = r["sets"]["frontier (effort<=any, runtime<=any) @inf"]
    assert S["sensors"] == sorted([A, B_])
    # hand: c1 blocks 3, 4: a catches at 5 (block 3), misses block 4 (60); c2: b at 30 in both
    want = hand_D({"c1": [5.0, HOLD], "c2": [30.0, 30.0]})
    assert S["D"] == pytest.approx(want) and S["g"] == pytest.approx(HOLD - want)
    assert S["detectedEpisodes"] == [3, 4]
    # the full ground set holds c, which catches c1 at 2 in the test blocks: D(full) is lower than the frozen set's
    full = r["sets"]["full"]
    assert full["D"] == pytest.approx(hand_D({"c1": [2.0, 2.0], "c2": [30.0, 30.0]}))
    assert full["D"] < S["D"]
    # per-episode values compose to D
    eps = r["episodes"]
    lab = "frontier (effort<=any, runtime<=any) @inf"
    assert [x["sets"][lab]["penalised"] for x in eps if x["class"] == "c1"] == [5.0, HOLD]
    assert all(x["block"] in (3, 4) for x in eps)


def test_effort_cap_sets_are_frozen_as_they_were(world):
    """(effort <= 0) excluded b in training: the frozen set at that cell is {a}, scored as frozen."""
    r = run(world)["rates"]["1"]
    s0 = r["sets"]["frontier (effort<=0, runtime<=any) @inf"]
    assert s0["sensors"] == [A] or set(s0["sensors"]) <= {A, C_}
    assert B_ not in s0["sensors"]
    assert "out of the box" in r["sets"] and r["sets"]["out of the box"]["size"] == 2     # a and c (effort 0)
    same = [lab for lab, s in r["sets"].items() if s.get("sameAs")]
    assert same, "identical frozen sets are scored once and aliased"


def test_absent_member_never_fires_and_is_listed(world):
    J, T = not_placeable(world, A)
    r = run(world, J, T=T)["rates"]["1"]
    S = r["sets"]["frontier (effort<=any, runtime<=any) @inf"]
    assert A in S["absentFromScoringGroundSet"]["sensors"] and S["absentFromScoringGroundSet"]["count"] == 1
    assert S["D"] == pytest.approx(hand_D({"c1": [HOLD, HOLD], "c2": [30.0, 30.0]}))     # a never fires


# ----------------------------------------------------------------------------- input checks

def test_split_checks(world):
    P2 = copy.deepcopy(world["P"])
    P2["split"]["test"] = [2, 3]                                 # a declared test set that overlaps the training blocks
    with pytest.raises(SystemExit, match="overlap"):
        run(world, P=P2, test=(2, 3))
    with pytest.raises(SystemExit, match="training readout"):
        run(world, training="none")
    with pytest.raises(SystemExit, match="not the placement's input readout"):
        run(world, training="bad")
    J = readout([1, 2, 3], fires, test_blocks={3})              # read without block 4
    with pytest.raises(SystemExit, match="recorded test blocks"):
        run(world, J)
    J = readout([1, 2, 3], fires, test_blocks={3, 4})           # claims test block 4 but did not read it
    with pytest.raises(SystemExit, match="do not hold every test block"):
        run(world, J)
    P = copy.deepcopy(world["P"])
    P["split"]["trainBlocks"] = None
    with pytest.raises(SystemExit, match="no training blocks"):
        run(world, P=P)
    with pytest.raises(SystemExit, match="not the declared test blocks"):
        run(world, test=(3,))                                    # a subset chosen after the fact
    P = copy.deepcopy(world["P"])
    P["split"]["test"] = None
    with pytest.raises(SystemExit, match="no declared test blocks"):
        run(world, P=P)
    T = copy.deepcopy(world["train"])                            # a training readout holding a test block's episode
    T["episodes"].append(copy.deepcopy(world["full"]["episodes"][-1]))
    with pytest.raises(SystemExit, match="holds episodes of test block"):
        s2.score(world["full"], world["P"], world["psha"], [3, 4], (T, world["tsha"]), None, allow_unpinned=True)
    with pytest.raises(SystemExit, match="differ in v32.parametersV32Sha256"):
        run(world, T=dict(world["train"], v32=dict(world["train"]["v32"], parametersV32Sha256="q" * 64)))
    with pytest.raises(SystemExit, match="differ in campaigns"):
        run(world, J=dict(world["full"], campaigns=["/c/other"]))


def test_rule_validation(world):
    base = {"set": "ledger alone", "rate": None}
    for bad in ({"set": "no such set"}, {"set": "ledger alone", "bogus": 1}, {"set": "ledger alone", "rate": 0.2},
                {"rate": None}, "x"):
        with pytest.raises(SystemExit):
            run(world, rule=bad)
    assert run(world, rule=dict(base, rate=1.0))["rates"]["1"]["sets"]["ledger alone"]["verdict"]["verdict"] in (
        "FAIL", s2.DASH, "PASS")


def test_pin_checks(world, monkeypatch):
    monkeypatch.setattr(c2, "PINNED_V32_SHA256", None)                  # the unpinned branch, as before the freeze
    with pytest.raises(SystemExit, match="frozen v3.1"):
        run(world, J=dict(world["full"], v31ScriptSha256="0" * 64))
    with pytest.raises(SystemExit, match="not v3.2"):
        run(world, J=dict(world["full"], version="3"))
    with pytest.raises(SystemExit, match="not frozen"):
        s2.score(world["full"], world["P"], world["psha"], [3, 4], (world["train"], world["tsha"]), None)
    P = copy.deepcopy(world["P"])
    P["inputs"]["celfSha256"] = "0" * 64
    with pytest.raises(SystemExit, match="frozen celf_v3"):
        run(world, P=P)
    with pytest.raises(SystemExit, match="system"):
        run(world, P=dict(world["P"], system="other"))


def test_duplicate_test_episode_is_refused(world):
    J = copy.deepcopy(world["full"])
    J["episodes"].append(copy.deepcopy(next(e for e in J["episodes"] if e["block"] == 3)))
    with pytest.raises(SystemExit, match="twice"):
        run(world, J)


# ----------------------------------------------------------------------------- the pass rule is the user's

def test_registry_rule_is_decision_99():
    rules = s2.pass_rule_registry()
    assert [r["class"] for r in rules] == ["fraud-pause-effect", "accounting-pause-effect"]
    assert all(r["minImprovedEpisodes"] == 2 and r["minEpisodes"] == 2 and r["set"].endswith("@6/T_r") for r in rules)      # decision 112 (110: @3/T_r)


def test_no_rule_gives_no_verdict(world):
    res = run(world)
    assert res["rates"]["1"]["verdicts"] == [] and "no pass rule declared" in res["passRuleNote"]


LAB = "frontier (effort<=any, runtime<=any) @inf"
BASE = {"set": LAB, "rate": None, "class": None, "minGain": None, "minImprovedEpisodes": None, "minEpisodes": None}


def verdicts(w, J=None, **kw):
    return run(w, J, rule=[dict(BASE, **kw)])["rates"]["1"]["verdicts"]


def test_sample_rules_are_evaluated_per_class(world):
    # frozen {a, b}: class c1 penalised [5, 60] vs ledger [60, 60]; class c2 [30, 30]
    (v,) = verdicts(world, **{"class": "c2"}, minImprovedEpisodes=2, minEpisodes=2)
    assert v["verdict"] == "PASS" and v["gE"] == pytest.approx(30.0) and v["improved"] == 2
    (v,) = verdicts(world, **{"class": "c1"}, minImprovedEpisodes=2, minEpisodes=2)
    assert v["verdict"] == "FAIL" and v["gE"] == pytest.approx(27.5) and "improves 1 of 2" in v["reason"]
    assert verdicts(world, **{"class": "c1"})[0]["verdict"] == "PASS"                  # no improvement count required
    assert verdicts(world, **{"class": "c1"}, minGain=100.0)[0]["verdict"] == "FAIL"
    assert verdicts(world, **{"class": "c2"}, minEpisodes=3)[0]["verdict"] == s2.DASH   # decision 91
    assert verdicts(world, **{"class": "other"})[0]["verdict"] == s2.DASH              # no valid episode of the class
    J, T = not_placeable(world, A)
    d = run(world, J, T=T, rule=[dict(BASE, **{"class": "c2"})])["rates"]["1"]["verdicts"][0]
    assert d["verdict"] == s2.DASH and "absent from the scoring" in d["reason"]         # decision 90


def not_placeable(world, sensor):
    """(scoring readout, training readout) with `sensor` not placeable in the SAME calibration (decision 102: the scoring
    readout's calibration is the training one)."""
    J, T = copy.deepcopy(world["full"]), copy.deepcopy(world["train"])
    for x in (J, T):
        x["calibration"]["primary"]["perRate"]["1"]["sensors"][sensor]["placeable"] = False
    return J, T


def test_class_g_is_over_the_rules_class(world):
    """Class c1 is never improved in the test blocks (a does not fire there) while class c2 is: the pooled g is positive,
    the class g is not."""
    def fires2(regime, b):
        return [] if (regime == "c1" and b >= 3) else fires(regime, b)
    J = readout([1, 2, 3, 4], fires2, test_blocks={3, 4})
    (v,) = verdicts(world, J, **{"class": "c1"})
    assert v["verdict"] == "FAIL" and v["gE"] == pytest.approx(0.0) and not v["gPositive"]
    assert run(world, J)["rates"]["1"]["sets"][LAB]["g"] > 0


def test_rule_validation(world):
    for bad in ([{"set": "no such set"}], [{"set": "ledger alone", "bogus": 1}], [{"set": "ledger alone", "rate": 0.2}],
                [{"rate": None}], "x", []):
        with pytest.raises(SystemExit):
            run(world, rule=bad)
    ok = run(world, rule=[{"set": "ledger alone", "rate": 1.0, "class": "c1"}])["rates"]["1"]["verdicts"]
    assert ok and ok[0]["rule"]["rate"] == "1"


# ----------------------------------------------------------------------------- planted defects

def _try(f):
    try:
        return bool(f())
    except (SystemExit, AssertionError):
        return False


def chk_test_only(w):
    return run(w)["rates"]["1"].get("episodesScored") == 4


def chk_block_by_number(w):
    """The planted alternative (the campaign-B tag) selects every episode of the readout, training blocks included."""
    r = run(w)["rates"]["1"]
    return r.get("episodesScored") == 4 and r.get("testBlocks") == [3, 4]


def chk_frozen(w):
    S = run(w)["rates"]["1"]["sets"]["frontier (effort<=any, runtime<=any) @inf"]
    return S["sensors"] == sorted([A, B_])


def chk_absent(w):
    J, T = not_placeable(w, A)
    J["episodes"][4]["fires"].append(tp.fire("T", A, 1.0))        # a recorded fire of the absent member in test block 3
    S = run(w, J, T=T)["rates"]["1"]["sets"]["frontier (effort<=any, runtime<=any) @inf"]
    return math.isclose(S["D"], hand_D({"c1": [HOLD, HOLD], "c2": [30.0, 30.0]}))


def chk_strict(w):
    r = run(w)["rates"]["1"]
    lab = "frontier (effort<=any, runtime<=any) @inf"
    return [x["sets"][lab]["improvesOnLedger"] for x in r["episodes"] if x["class"] == "c1"] == [True, False]


def chk_overlap(w):
    P2 = copy.deepcopy(w["P"])
    P2["split"]["test"] = [2, 3]
    saved, s2.REQUIRE_TRAINING = s2.REQUIRE_TRAINING, False         # isolate the overlap guard from the training-readout one
    try:
        run(w, P=P2, test=(2, 3), training="none")
    except SystemExit as exc:
        return "overlap" in str(exc)
    finally:
        s2.REQUIRE_TRAINING = saved
    return False


def chk_training(w):
    try:
        run(w, training="bad")
    except SystemExit:
        return True
    return False


def chk_duplicates(w):
    J = copy.deepcopy(w["full"])
    J["episodes"].append(copy.deepcopy(next(e for e in J["episodes"] if e["block"] == 3)))
    try:
        run(w, J)
    except SystemExit:
        return True
    return False


def chk_pins(w):
    P2 = copy.deepcopy(w["P"])
    P2["inputs"]["celfSha256"] = "0" * 64
    try:
        run(w, P=P2)
    except SystemExit:
        return True
    return False


def chk_no_rule(w):
    return run(w)["rates"]["1"]["verdicts"] == []


def chk_class_g(w):
    def fires2(regime, b):
        return [] if (regime == "c1" and b >= 3) else fires(regime, b)
    J = readout([1, 2, 3, 4], fires2, test_blocks={3, 4})
    return verdicts(w, J, **{"class": "c1"})[0]["verdict"] == "FAIL"


def chk_held_out_flag(w):
    J = copy.deepcopy(w["full"])
    J["v32"]["blockSelection"]["testBlocks"] = None            # read without --test-blocks
    try:
        run(w, J)
    except SystemExit:
        return True
    return False


def chk_same_calibration(w):
    J = copy.deepcopy(w["full"])
    J["calibration"]["primary"]["perRate"]["1"]["sensors"][C_]["placeable"] = False
    try:
        run(w, J)
    except SystemExit:
        return True
    return False


def chk_declared_test(w):
    J = readout([1, 2, 3, 4], fires, test_blocks={3})             # consistent with --test-blocks 3, not with the declaration
    try:
        run(w, J, test=(3,))
    except SystemExit:
        return True
    return False


def chk_epoch_select(w):
    J = copy.deepcopy(w["full"])
    extra = copy.deepcopy(next(e for e in J["episodes"] if e["block"] == 3))
    extra.update(studyEpoch="otel-traffic-sweep-v1", regime="legacy-class", cell="legacy/b3", harness="sweep")
    J["episodes"].append(extra)                                  # a legacy epoch's block-3 episode
    return run(w, J)["rates"]["1"].get("episodesScored") == 4


CHECKS = {"CLASS_G": chk_class_g, "REQUIRE_HELD_OUT": chk_held_out_flag, "SAME_CALIBRATION": chk_same_calibration,
          "REQUIRE_DECLARED_TEST": chk_declared_test, "EPOCH_SELECT": chk_epoch_select, "TEST_ONLY": chk_test_only, "BLOCK_BY_NUMBER": chk_block_by_number, "FROZEN_SETS": chk_frozen,
          "ABSENT_NEVER_FIRES": chk_absent, "STRICT_IMPROVEMENT": chk_strict, "REFUSE_OVERLAP": chk_overlap,
          "REQUIRE_TRAINING": chk_training, "REFUSE_DUPLICATE_EPISODES": chk_duplicates, "ENFORCE_PINS": chk_pins,
          "NO_PASS_RULE_DASH": chk_no_rule}


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, world, monkeypatch):
    assert _try(lambda: CHECKS[flag](world)), flag
    monkeypatch.setattr(s2, flag, False)
    assert not _try(lambda: CHECKS[flag](world)), flag


def test_every_switch_has_a_check():
    assert set(s2.SWITCHES) == set(CHECKS)


# ----------------------------------------------------------------------------- CLI, frozen code

def test_main_writes_json_and_markdown_once(world, monkeypatch, tmp_path):
    monkeypatch.setattr(c2, "PINNED_V32_SHA256", None)
    out = tmp_path / "o" / "score.json"
    argv = [str(world["sc"]), "--placement", str(world["pl"]), "--training-readout", str(world["tr"]),
            "--test-blocks", "3", "4", "--out", str(out), "--allow-unpinned"]
    assert s2.main(argv) == 0
    res = json.loads(out.read_text())
    md = out.with_suffix(".md").read_text()
    assert res["version"] == s2.VERSION and res["inputs"]["placementSha256"] == world["psha"]
    assert "Campaign E test scoring" in md and "decision 99" in md and res["passRule"] == s2.pass_rule_registry()
    assert res["inputs"]["parametersV32Sha256"] == c2.sha256(c2.PARAMETERS_V32)
    assert all(v["verdict"] == s2.DASH and v["episodesInPool"] == 0                 # c1/c2 are not the off-path classes
               for r in res["rates"].values() for v in r["verdicts"])
    with pytest.raises(SystemExit, match="existing path"):
        s2.main(argv)
    with pytest.raises(SystemExit, match="end in .json"):
        s2.main(argv[:-3] + ["--out", str(tmp_path / "x.txt"), "--allow-unpinned"])


def test_frozen_files_are_unchanged():
    assert c2.sha256(ROOT / "research" / "placement" / "celf_v3.py") == c2.PINNED_CELF_SHA256
    assert c2.sha256(ROOT / "research" / "placement" / "score_test_v3.py") == (      # frozen at 1a8d924
        "66befafa36f1de371cc6ae79cb09886357fa31215595f6753e706081fca81b53")


# ----------------------------------------------------------------------------- decision 112: end to end, 6/T_r

FR, AC = "fraud-pause-effect", "accounting-pause-effect"
K_FR, K_AC = "log:kafka:member-failed-fraud", "log:kafka:member-failed-accounting"
EARLY_FR, EARLY_AC = "log:appear:fraud-b1", "log:appear:accounting-b1"
T_R = 0.15                                                   # training no-fault hours of the synthetic rate


def e2e_readout(blocks, test_blocks=None):
    """Two off-path classes, one episode each per block. Training blocks 1-3: the class's recurring Kafka sensor (fraud 43.5 s,
    accounting 44.0 s) in every episode, plus a one-episode early `appear` id (0.4 s) in block 1 only. Test blocks 4-5: only
    the two recurring sensors fire. Every sensor costs 2.9957 / T_r per hour: 3/T_r affords one, 6/T_r two."""
    up = 2.9957 / T_R
    eps = []
    for b in blocks:
        for regime, key, t, early in ((FR, K_FR, 43.5, EARLY_FR), (AC, K_AC, 44.0, EARLY_AC)):
            f = [tp.fire("T", key, t)]
            if b == 1:
                f.append(tp.fire("T", early, 0.4))
            eps.append(tp.ep(regime, 1.0, b, f, hold=HOLD, harness="B"))
    sensors = {s: tp.sensor("T", upper=up) for s in (K_FR, K_AC, EARLY_FR, EARLY_AC)}
    return _versions(tp.readout(eps, sensors, hours=T_R), sorted(blocks), test_blocks)


def e2e_world(tmp_path, tag="a"):
    train, full = e2e_readout([1, 2, 3]), e2e_readout([1, 2, 3, 4, 5], {4, 5})
    d = tmp_path / tag
    d.mkdir()
    tr, sc, pl, split = d / "train.json", d / "score.json", d / "placement.json", d / "split.json"
    tr.write_text(json.dumps(train))
    sc.write_text(json.dumps(full))
    split.write_text(json.dumps({"train": [1, 2, 3], "test": [4, 5]}))
    tier = d / "tiers.json"
    doc = json.loads(EFFORT_FILE.read_text())
    doc["sensors"] = [dict(doc["sensors"][1], id=K_FR)]
    tier.write_text(json.dumps(doc))
    assert c2.main([str(tr), "--tiers", str(tier), "--tier-catalog", "postures", "--out", str(pl), "--split", str(split),
                    "--allow-unpinned"]) == 0
    return {"train": train, "full": full, "P": json.loads(pl.read_text()), "psha": c2.sha256(pl), "tsha": c2.sha256(tr)}


def e2e_score(w, label_budget):
    rules = [dict(r, set="frontier (effort<=any, runtime<=any) @%s" % label_budget) for r in s2.pass_rule_registry()]
    return s2.score(w["full"], w["P"], w["psha"], [4, 5], (w["train"], w["tsha"]), rules, allow_unpinned=True)["rates"]["1"]


def test_decision_112_two_recurring_sensors_make_both_classes_pass_at_6_over_T_r(tmp_path, monkeypatch):
    w = e2e_world(tmp_path)
    cell_any = next(c for c in w["P"]["rates"]["1"]["grid"] if c["maxEffort"] == ANY and c["maxRuntime"] == ANY)
    assert sorted(cell_any["points"]["6/T_r"]["set"]) == sorted([K_FR, K_AC])             # the two recurring sensors
    assert cell_any["points"]["3/T_r"]["set"] == [K_FR]                           # one slot: the larger gain (fraud, 43.5 s)
    assert cell_any["points"]["6/T_r"]["budget"] == pytest.approx(2 * cv.LITERAL_NULL_EVENTS / T_R)
    rec = w["P"]["rates"]["1"]["recurrence"]
    assert rec["removedWithCountedFireIds"] == sorted([EARLY_FR, EARLY_AC]) and rec["removedFromGroundSet"] == 2
    assert rec["recurringByClass"] == {AC: [K_AC], FR: [K_FR]} and rec["episodesPerClass"] == {AC: 3, FR: 3}
    # the registry's rule is at 6/T_r: both off-path classes PASS (both test episodes of each class improve)
    reg = s2.pass_rule_registry()
    assert {r["set"] for r in reg} == {"frontier (effort<=any, runtime<=any) @6/T_r"}
    v = {x["rule"]["class"]: x for x in e2e_score(w, "6/T_r")["verdicts"]}
    assert v[FR]["verdict"] == "PASS" and v[AC]["verdict"] == "PASS" and v[FR]["improved"] == v[AC]["improved"] == 2
    assert v[FR]["gE"] == pytest.approx(HOLD - 43.5) and v[AC]["gE"] == pytest.approx(HOLD - 44.0)
    # at 3/T_r the one slot serves one class only: the other FAILs (decision 112's stated trade)
    v3 = {x["rule"]["class"]: x for x in e2e_score(w, "3/T_r")["verdicts"]}
    assert v3[FR]["verdict"] == "PASS" and v3[AC]["verdict"] == "FAIL" and v3[AC]["improved"] == 0
    # planted: without the rule the early one-episode ids take the slots, cannot fire in the test blocks, both classes FAIL
    monkeypatch.setattr(c2, "RECURRENCE_FILTER", False)
    w0 = e2e_world(tmp_path, "b")
    cell0 = next(c for c in w0["P"]["rates"]["1"]["grid"] if c["maxEffort"] == ANY and c["maxRuntime"] == ANY)
    assert set(cell0["points"]["6/T_r"]["set"]) == {EARLY_FR, EARLY_AC}
    v0 = {x["rule"]["class"]: x for x in e2e_score(w0, "6/T_r")["verdicts"]}
    assert v0[FR]["verdict"] == "FAIL" and v0[AC]["verdict"] == "FAIL"


def test_a_rate_that_cannot_be_scored_carries_dash_verdicts_for_both_classes(tmp_path):
    """Review finding N1: no frozen grid / no calibration / no test episode / no hours gave a bare note with no verdicts."""
    w = e2e_world(tmp_path)
    rules = s2.validate_rule(s2.pass_rule_registry(), w["P"])
    for rk, P in (("1", dict(w["P"], rates={"1": {"note": "— (no calibration at this rate)"}})),):
        r = s2.score_rate(w["full"], P, rk, {4, 5}, rules)
        assert "sets" not in r and [x["rule"]["class"] for x in r["verdicts"]] == [FR, AC]
        assert all(x["verdict"] == s2.DASH and "no frozen placement" in x["reason"] for x in r["verdicts"])
    J = copy.deepcopy(w["full"])
    J["calibration"]["primary"]["perRate"] = {}
    r = s2.score_rate(J, w["P"], "1", {4, 5}, rules)
    assert [x["verdict"] for x in r["verdicts"]] == [s2.DASH, s2.DASH] and "no calibration" in r["verdicts"][0]["reason"]
    r = s2.score_rate(w["full"], w["P"], "1", {9}, rules)                              # no test episode in blocks {9}
    assert [x["verdict"] for x in r["verdicts"]] == [s2.DASH, s2.DASH] and "no test episode" in r["verdicts"][0]["reason"]
    assert s2.score_rate(J, w["P"], "1", {4, 5}, None)["verdicts"] == []               # no declared rule: nothing to dash
    r = s2.score_rate(J, w["P"], "1", {4, 5}, [dict(rules[0], rate="2")])              # a rule of another rate does not apply
    assert r["verdicts"] == []
    # the markdown prints them
    res = {"version": "v", "scope": "s", "system": "x", "splitCheck": {"testBlocks": [4, 5], "trainBlocks": [1, 2, 3]},
           "passRuleNote": "n", "freshFalseAlarms": "f", "deviation": "d", "limitation": "l",
           "rates": {"1": s2.score_rate(J, w["P"], "1", {4, 5}, rules)}}
    md = s2.markdown(res)
    assert "**—**" in md and md.count("`fraud-pause-effect`") == 1 and md.count("`accounting-pause-effect`") == 1


def test_a_point_without_a_set_gives_a_dash_with_the_reason(tmp_path):
    """The rate has no hours, so 6/T_r has no set: the verdict is a dash naming the point's own note, per class."""
    w = e2e_world(tmp_path)
    P = copy.deepcopy(w["P"])
    for c in P["rates"]["1"]["grid"]:
        c["points"]["6/T_r"] = {"note": "— (no 6/T_r: the rate has no hours)"}
    out = s2.score(w["full"], P, w["psha"], [4, 5], (w["train"], w["tsha"]), s2.pass_rule_registry(), allow_unpinned=True)
    vs = out["rates"]["1"]["verdicts"]
    assert [v["rule"]["class"] for v in vs] == [FR, AC] and all(v["verdict"] == s2.DASH for v in vs)
    assert all("no 6/T_r: the rate has no hours" in v["reason"] for v in vs)


# ----------------------------------------------------------------------------- F5: the registry digest is pinned

def test_registry_digest_pin_in_both_states(world, monkeypatch):
    """Unpinned (None): the scoring readout and the placement must carry the LIVE registry digest and --allow-unpinned is
    needed; pinned: the live registry and both artefacts must equal the pin. A planted mismatch is refused either way."""
    live = c2.sha256(c2.PARAMETERS_V32)
    monkeypatch.setattr(c2, "PINNED_PARAMETERS_V32_SHA256", None)      # the unpinned branch, as before the freeze
    monkeypatch.setattr(c2, "PINNED_V32_SHA256", None)
    run(world)                                                                          # unpinned, matching: scores
    bad = dict(world["full"], v32=dict(world["full"]["v32"], parametersV32Sha256="q" * 64))
    with pytest.raises(SystemExit, match="scoring readout recorded parametersV32Sha256"):
        run(world, J=bad)
    nov = dict(world["full"], v32={k: v for k, v in world["full"]["v32"].items() if k != "parametersV32Sha256"})
    with pytest.raises(SystemExit, match="recorded parametersV32Sha256 None"):
        run(world, J=nov)
    P = copy.deepcopy(world["P"])
    P["inputs"]["parametersV32Sha256"] = "r" * 64                                       # a placement built under another registry
    with pytest.raises(SystemExit, match="the placement recorded parametersV32Sha256"):
        run(world, P=P)
    with pytest.raises(SystemExit, match="registry is not frozen"):
        monkeypatch.setattr(c2, "PINNED_V32_SHA256", c2.sha256(DET / "sweep_analysis_v3_2.py"))   # reader pinned, registry not
        s2.score(world["full"], world["P"], world["psha"], [3, 4], (world["train"], world["tsha"]), None)
    monkeypatch.setattr(c2, "PINNED_V32_SHA256", None)
    # pinned to the live digest: accepted; pinned to another digest: the live registry differs, refused; an artefact recorded
    # under another digest than the pin: refused
    monkeypatch.setattr(c2, "PINNED_PARAMETERS_V32_SHA256", live)
    run(world)
    with pytest.raises(SystemExit, match="scoring readout recorded parametersV32Sha256"):
        run(world, J=bad)
    monkeypatch.setattr(c2, "PINNED_PARAMETERS_V32_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match="live registry .* not the frozen"):
        run(world)
    monkeypatch.setattr(c2, "PINNED_PARAMETERS_V32_SHA256", None)
    monkeypatch.setattr(s2, "ENFORCE_PINS", False)                                      # the planted switch: not enforced
    run(world, P=P)
