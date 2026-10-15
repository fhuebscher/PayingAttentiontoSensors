"""research/lanes/score_ho_v34.py: scoring of the Hotel off-path predictions HO-* (PREDICTIONS_OVERNIGHT_20261014.json) on a v3.4 readout.

Layer: unit (hand-built readout dicts, one rule at a time, with its boundary) + one end-to-end pass over a synthetic v3.4 readout
(tests/test_sweep_analysis_v3_4.py's fixture). No cell of hotel-offpath-v1 was read. Every rule and refusal has a planted defect
under which a check fails (test_planted_defects_are_caught), and the scorer's pins on the committed prediction rules and bands are
asserted against the committed JSON.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "lanes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import score_ho_v34 as sc  # noqa: E402

EPOCH, CP, SP = sc.EPOCH, sc.CP, sc.SP
HO = sc.load_predictions()


# ----------------------------------------------------------------------------- hand-built readouts

def fire(sensor, ttd, own=False, counts=True, bc=(), family="M", rule="spike"):
    return [family, sensor, rule, ttd, "up", own, True, counts, list(bc), 0.0]


def ledger(ttd):
    return fire("ledger:frontend:hotel-search-v1", ttd, family="E", rule="failed")


def own(sensor, ttd, **kw):
    return fire(sensor, ttd, own=True, **kw)


def episode(regime, rate, block, fires, studyEpoch=EPOCH):
    tgt = {CP: "consul", SP: "search"}[regime]
    return {"regime": regime, "rate": rate, "block": block, "target": tgt, "cell": "%s/r%g/b%02d" % (regime, rate, block),
            "fires": fires, "studyEpoch": studyEpoch}


def readout(eps, collected=None, coord=None, version="3.4", epochs=(EPOCH,), system="hotel", armed_consul=True):
    """A v3.4-shaped readout: the episodes and the lanes block (own collected sensors per cell; coordinator/lag `—`)."""
    collected = collected or {}
    regimes = {}
    for e in eps:
        lanes = {"own": {"collectedSensors": collected.get(e["regime"], 3)},
                 "coordinator": {"note": "no coordinator lane is declared for this system", "earliest": None, "countedFires": None},
                 "lag": {"note": "no lag lane is declared for this system", "earliest": None, "countedFires": None}}
        if coord:
            lanes["coordinator"] = {"earliest": {"ttd": coord}, "countedFires": 1, "byConstructionFires": 0}
        regimes.setdefault(e["regime"], {"episodes": []})["episodes"].append({"cell": e["cell"], "lanes": lanes})
    cal = {"%g" % rate: {"sensors": {"metric:consul:cpu": {"placeable": armed_consul}, "metric:search:cpu": {"placeable": True},
                                      "ledger:frontend:hotel-search-v1": {"placeable": True}}} for rate in (1.0, 10.0, 5.0, 2.0)}
    return {"version": version, "system": system, "scriptSha256": "x" * 64, "calibration": {"primary": {"perRate": cal}},
            "v34": {"hotelOffPathEpochsRead": list(epochs)}, "v33": {"lanes": {"regimes": regimes}}, "episodes": eps}


def search_eps(r1=(1.0, 1.1, 0.9), r10=(0.25, 0.24, 0.26), led1=(1.2, 1.1, 1.3), led10=(0.3, 0.25, 0.28), miss=None):
    out = []
    for rate, owns, leds in ((1.0, r1, led1), (10.0, r10, led10)):
        for b, (o, l) in enumerate(zip(owns, leds), start=1):
            fs = []
            if o is not None and (miss != (rate, b)):
                fs.append(own("metric:search:cpu", o))
            if l is not None:
                fs.append(ledger(l))
            out.append(episode(SP, rate, b, fs))
    return out


def consul_eps(own_times=(None, None, None), ledger_times=(None, None, None), bc=False, rates=(1.0, 10.0)):
    out = []
    for rate in rates:
        for b in (1, 2, 3):
            fs = []
            o, l = own_times[b - 1], ledger_times[b - 1]
            if o is not None:
                fs.append(own("metric:consul:cpu", o, bc=["BC-actuator-readback"] if bc else []))
            if l is not None:
                fs.append(ledger(l))
            out.append(episode(CP, rate, b, fs))
    return out


def S(J):
    return {r["id"]: r for r in sc.score(J, HO)["rows"]}


# ----------------------------------------------------------------------------- HO-L1

def chk_l1(_=None):
    ok = S(readout(search_eps() + consul_eps()))["HO-L1"]
    hi = S(readout(search_eps(r10=(0.25, 0.30, 0.26)) + consul_eps()))["HO-L1"]          # median 0.26: still inside
    out = S(readout(search_eps(r10=(0.5, 0.6, 0.55)) + consul_eps()))["HO-L1"]           # median 0.55: outside [0.21, 0.28]
    edge = S(readout(search_eps(r1=(1.54, 1.54, 1.54)) + consul_eps()))["HO-L1"]         # at the band edge: inside
    lost = S(readout(search_eps(miss=(10.0, 2)) + consul_eps()))["HO-L1"]                # one episode undetected: not 100 %
    return (ok["verdict"] == "hit" and hi["verdict"] == "hit" and out["verdict"] == "miss" and edge["verdict"] == "hit"
            and lost["verdict"] == "miss" and lost["evidence"]["detectedInEveryEpisode"] is False
            and out["evidence"]["perRate"]["10"]["inside"] is False and ok["evidence"]["perRate"]["1"]["inside"] is True)


def test_ho_l1_bands_detection_and_edges():
    assert chk_l1()


def test_ho_l1_a_rate_without_a_band_is_dash_and_only_detection_is_scored():
    eps = [episode(SP, 5.0, b, [own("metric:search:cpu", 2.0)]) for b in (1, 2, 3)]
    r = S(readout(eps))["HO-L1"]
    assert r["verdict"] == "hit (detection clause only)" and r["evidence"]["ratesWithoutBand"] == [5.0]
    assert r["evidence"]["perRate"]["5"]["inside"] is None and r["evidence"]["perRate"]["5"]["band"] is None


def test_ho_l1_counts_either_field():
    eps = [episode(SP, 1.0, b, [own("metric:search:cpu", 1.0, bc=["BC-actuator-readback"])]) for b in (1, 2, 3)]
    assert S(readout(eps))["HO-L1"]["verdict"] == "hit"           # the by-construction fire is a fire (either field)


# ----------------------------------------------------------------------------- HO-L2

def chk_l2(_=None):
    silent = S(readout(consul_eps() + search_eps()))["HO-L2"]
    fired = S(readout(consul_eps(own_times=(1.0, None, None)) + search_eps()))["HO-L2"]
    bc_only = S(readout(consul_eps(own_times=(2.0, 2.1, 2.2), bc=True) + search_eps()))["HO-L2"]
    unarmed = S(readout(consul_eps() + search_eps(), armed_consul=False))["HO-L2"]          # collected but not armed: `—`
    fire_unarmed = S(readout(consul_eps(own_times=(1.0, None, None)) + search_eps(), armed_consul=False))["HO-L2"]
    return (silent["verdict"].startswith("not covered") and fired["verdict"] == "miss (counted field)"
            and bc_only["verdict"].startswith("miss (by-construction field only") and unarmed["verdict"].startswith("—")
            and fire_unarmed["verdict"].startswith("miss") and bc_only["evidence"]["ownFiringIds"] == ["metric:consul:cpu"]
            and bc_only["evidence"]["earliestOwnFire"] == 2.0 and bc_only["evidence"]["episodesWithCountedOwnFire"] == 0
            and silent["evidence"]["armedOwnSensors"] == ["metric:consul:cpu"])


def test_ho_l2_dash_not_covered_and_miss():
    assert chk_l2()


# ----------------------------------------------------------------------------- HO-D1

def chk_d1(_=None):
    hit = S(readout(search_eps() + consul_eps()))["HO-D1"]
    boundary = S(readout(search_eps(r1=(1.0, 1.0, 1.0), r10=(0.5, 0.5, 0.5), led1=(1.0, 1.0, 1.0), led10=(0.5, 0.5, 0.5)) + consul_eps()))["HO-D1"]
    miss_own = S(readout(search_eps(r10=(0.7, 0.7, 0.7)) + consul_eps()))["HO-D1"]
    miss_led = S(readout(search_eps(led10=(0.9, 0.9, 0.9)) + consul_eps()))["HO-D1"]
    nolead = S(readout(search_eps(led10=(None, None, None)) + consul_eps()))["HO-D1"]
    known_miss = S(readout(search_eps(r10=(0.7, 0.7, 0.7), led10=(None, None, None)) + consul_eps()))["HO-D1"]   # own fails, ledger `—`
    zero = S(readout(search_eps(r1=(0.0, 0.0, 0.0), r10=(0.0, 0.0, 0.0)) + consul_eps()))["HO-D1"]            # 0 <= 0.5 x 0: holds
    return (hit["verdict"] == "hit" and boundary["verdict"] == "hit" and miss_own["verdict"] == "miss"
            and miss_led["verdict"] == "miss" and nolead["verdict"] == "—" and known_miss["verdict"] == "miss" and zero["evidence"]["own"][0]["holds"] is True
            and hit["evidence"]["own"][0]["pair"] == [1.0, 10.0] and abs(hit["evidence"]["own"][0]["ratio"] - 0.25) < 1e-9)


def test_ho_d1_ratio_boundary_both_lanes_and_dash():
    assert chk_d1()


def test_ho_d1_needs_rates_four_times_apart():
    eps = [episode(SP, r, b, [own("metric:search:cpu", 1.0), ledger(1.0)]) for r in (1.0, 2.0) for b in (1, 2, 3)]
    assert S(readout(eps))["HO-D1"]["verdict"] == "—"


# ----------------------------------------------------------------------------- HO-C, HO-D2

def chk_c(_=None):
    hit = S(readout(search_eps() + consul_eps()))["HO-C"]
    miss = S(readout(search_eps() + consul_eps(), coord=44.0))["HO-C"]
    return hit["verdict"] == "hit (by construction)" and miss["verdict"] == "miss" and miss["evidence"]["coordinatorOrLagFiresInAnyEpisode"] and \
        "by construction" in hit["label"]


def test_ho_c_hit_is_labelled_by_construction_and_a_fire_is_a_miss():
    assert chk_c()


def test_ho_d2_is_dash():
    assert S(readout(search_eps() + consul_eps()))["HO-D2"]["verdict"] == "—"


# ----------------------------------------------------------------------------- ontology rows (compare.py's rules)

def test_ontology_items():
    J = readout(search_eps() + consul_eps(ledger_times=(0.5, 0.6, 0.7)))
    r = S(J)
    s = r["HO-ONT-search"]["items"]
    assert s["lane:own"] == "disagree"                       # predicted no, measured 3/3 per rate (the sweep's own disagreement)
    assert s["lane:coordinator"] == s["lane:lag"] == s["CQ-C1 class"] == s["CQ-L2 window"] == "not comparable"
    assert s["CQ-B1 entry reached (proxy: ledger lane)"] == "agree"
    c = r["HO-ONT-consul"]["items"]
    assert c["lane:own"] == "agree"                          # predicted no, consul sensors collected and silent
    assert c["CQ-B1 entry reached (proxy: ledger lane)"] == "agree"
    quiet = S(readout(search_eps() + consul_eps()))["HO-ONT-consul"]["items"]
    assert quiet["CQ-B1 entry reached (proxy: ledger lane)"] == "disagree"       # predicted yes, the ledger never fired
    fired = S(readout(search_eps() + consul_eps(own_times=(1.0, 1.0, 1.0))))["HO-ONT-consul"]["items"]
    assert fired["lane:own"] == "disagree"
    notcol = S(readout(search_eps() + consul_eps(own_times=(1.0, 1.0, 1.0)), collected={CP: 0}))["HO-ONT-consul"]["items"]
    assert notcol["lane:own"] == "not comparable"            # an own lane that was not collected is not comparable


# ----------------------------------------------------------------------------- refusals and pins

def test_refuses_what_is_not_a_v34_readout_of_the_epoch_alone():
    base = search_eps() + consul_eps()
    for bad, text in ((readout(base, version="3.3"), "not a v3.4 readout"), (readout(base, epochs=()), "does not contain the epoch"),
                      (readout(base, epochs=(EPOCH, "x")), "does not contain the epoch"), (readout(base, system="otel"), "system")):
        with pytest.raises(SystemExit, match=text):
            sc.score(bad, HO)


def test_a_lanes_block_without_collected_counts_or_an_episode_is_refused():
    J = readout(search_eps() + consul_eps())
    first = next(iter(J["v33"]["lanes"]["regimes"].values()))["episodes"][0]
    first["lanes"]["own"]["collectedSensors"] = None
    with pytest.raises(SystemExit, match="collectedSensors"):
        sc.score(J, HO)
    J = readout(search_eps() + consul_eps())
    next(iter(J["v33"]["lanes"]["regimes"].values()))["episodes"].pop()
    with pytest.raises(SystemExit, match="no entry in the readout's lanes block"):
        sc.score(J, HO)


def test_shortfall_against_the_declared_five_is_reported():
    S_ = sc.score(readout(search_eps() + consul_eps()), HO)
    assert S_["episodesDeclaredPerRegimeAndRate"] == 5 and S_["shortfall"]["consul-pause-effect r1"] == 2
    assert S_["shortfall"]["search-pause-effect r10"] == 2 and "no-fault" not in " ".join(S_["shortfall"])


def test_episodes_of_another_epoch_are_not_scored():
    eps = search_eps() + consul_eps()
    eps.append(episode(SP, 1.0, 9, [own("metric:search:cpu", 9.0)], studyEpoch="hotel-traffic-sweep-v1"))
    assert sc.score(readout(eps), HO)["episodes"] == len(eps) - 1


def test_rule_pins_match_the_committed_predictions_and_a_changed_rule_is_refused(monkeypatch, tmp_path):
    ho = sc.load_predictions()
    assert set(sc.RULE_SHA256) == {i for i in ho if i != "HO-D2"} | {"HO-D2"}
    doc = json.loads(sc.PREDICTIONS.read_text())
    for p in doc["predictions"]:
        if p["id"] == "HO-L1":
            p["rule"] = p["rule"].replace("100 %", "90 %")
    edited = tmp_path / "p.json"
    edited.write_text(json.dumps(doc))
    with pytest.raises(SystemExit, match="HO-L1"):
        sc.load_predictions(edited)


def test_bands_equal_the_ones_in_the_prediction_text():
    claim = HO["HO-L1"]["claim"]
    got = {float(m.group(1)): (float(m.group(2)), float(m.group(3)))
           for m in re.finditer(r"(\d+(?:\.\d+)?): (\d+\.\d+)-(\d+\.\d+) s", claim)}
    assert got[1.0] == sc.BANDS[1.0] and got[10.0] == sc.BANDS[10.0] and set(sc.BANDS) <= set(got)
    assert sc.RATIO == 0.5 and sc.GAP == 4.0 and "0.5 x" in HO["HO-D1"]["claim"] and "4x" in HO["HO-D1"]["claim"]


def test_cli_writes_new_outputs_and_never_overwrites(tmp_path):
    J = readout(search_eps() + consul_eps())
    J["scriptSha256"] = "y" * 64
    f = tmp_path / "r.json"
    f.write_text(json.dumps(J))
    out = tmp_path / "out"
    assert sc.main([str(f), "--out", str(out)]) == 0
    S_ = json.loads((out / "HO_SCORE.json").read_text())
    assert S_["input"]["sha256"] and S_["input"]["scorerSha256"] and {r["id"] for r in S_["rows"]} >= {"HO-C", "HO-L1", "HO-L2", "HO-D1"}
    assert "| HO-L1 | hit |" in (out / "HO_SCORE.md").read_text()
    with pytest.raises(SystemExit):
        sc.main([str(f), "--out", str(out)])


# ----------------------------------------------------------------------------- end to end on a synthetic v3.4 readout

def test_scores_a_real_v34_readout_of_the_synthetic_fixture(tmp_path):
    import test_sweep_analysis_v3_4 as t34
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(t34.v32, "E_SPLIT", t34.NO_SPLIT)
        camps = [t34.offpath_campaign(tmp_path / "o", blocks=(1, 2, 3, 4))]
        R = t34.run(camps)
        J = json.loads(json.dumps(t34.v34.build_json34(R), default=sorted))
    S_ = sc.score(J, HO)
    rows = {r["id"]: r for r in S_["rows"]}
    assert S_["episodes"] == 8 and S_["episodesByRegimeRate"] == {"consul-pause-effect r1": 4, "search-pause-effect r1": 4}
    assert rows["HO-C"]["verdict"] == "hit (by construction)"
    assert rows["HO-L2"]["verdict"].startswith("miss (by-construction field only") and rows["HO-L2"]["evidence"]["ownFiringIds"] == ["metric:consul:cpu"]   # by-construction fire
    assert rows["HO-L1"]["verdict"] in ("hit", "miss") and rows["HO-L1"]["evidence"]["detectedInEveryEpisode"] is True
    assert rows["HO-D1"]["verdict"] == "—"                        # one rate only: no pair 4x apart
    assert rows["HO-ONT-consul"]["items"]["lane:own"] == "disagree"


# ----------------------------------------------------------------------------- planted defects

def test_planted_defects_are_caught(monkeypatch):
    assert chk_l1() and chk_l2() and chk_d1() and chk_c()
    monkeypatch.setattr(sc, "EITHER_FIELD", False)                # counted field only: the BC fires vanish
    assert not chk_l2()                                           # HO-L2's by-construction miss is no longer seen
    monkeypatch.setattr(sc, "EITHER_FIELD", True)
    monkeypatch.setattr(sc, "BANDS", {1.0: (0.0, 99.0), 10.0: (0.0, 99.0)})
    assert not chk_l1()                                           # bands too wide: the out-of-band episode is no longer a miss
    monkeypatch.setattr(sc, "BANDS", {1.0: (0.70, 1.54), 10.0: (0.21, 0.28)})
    monkeypatch.setattr(sc, "RATIO", 0.9)
    assert not chk_d1()                                           # a looser ratio: the 0.7 / 0.9 cases turn into hits
    monkeypatch.setattr(sc, "RATIO", 0.5)
    monkeypatch.setattr(sc, "CHECK_RULE_PINS", False)
    monkeypatch.setattr(sc, "RULE_SHA256", dict(sc.RULE_SHA256, **{"HO-C": "0" * 16}))
    sc.load_predictions()                                         # no refusal with the pins off
    monkeypatch.setattr(sc, "CHECK_RULE_PINS", True)
    with pytest.raises(SystemExit):
        sc.load_predictions()
