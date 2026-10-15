"""research/lanes/posthoc_lanes_v33.py: POST HOC lane rows for OTel campaign F and the TeaStore off-path epoch (FREEZE_V33 addendum,
condition 2). Committed with its tests on E data before any F or TeaStore off-path cell is read.

Layers, stated per test:
  * REAL E (campaign E, tmp/otel-e-evidence): v3.3 readouts of E's training blocks 1-3 and scoring (test blocks 4-5) made by the FROZEN v3.3
    reader, cached in tmp/posthoc-lanes-e/ (made on first use: minutes), the frozen E placement and the committed v3.2 E scoring.
  * PLUMBING (TeaStore campaign C, tmp/teastorec1r1-evidence): recommender data does not exist yet, so the TeaStore parts are run on C's
    auth-freeze episodes as a stand-in regime. These tests prove the plumbing reads real fields; they say nothing about the recommender.
  * SYNTHETIC: hand-built readouts and ledgers for denominators, boundaries and the F-L3 armed branch.
Each part carries a planted defect (a module switch flipped; the same assertion is shown to fail).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "research" / "placement", ROOT / "research" / "detection-time"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_spec = importlib.util.spec_from_file_location("posthoc_lanes_v33", ROOT / "research" / "lanes" / "posthoc_lanes_v33.py")
ph = importlib.util.module_from_spec(_spec)
sys.modules["posthoc_lanes_v33"] = ph
_spec.loader.exec_module(ph)
cv = ph.cv

CACHE = ROOT / "tmp" / "posthoc-lanes-e"
E_EVIDENCE = ROOT / "tmp" / "otel-e-evidence" / "e1-fetch" / "x"
C_EVIDENCE = ROOT / "tmp" / "teastorec1r1-evidence" / "x"
READER = ROOT / "research" / "detection-time" / "sweep_analysis_v3_3.py"
SPLIT_E = ROOT / "research" / "protocol" / "split_e_otel.json"
PLACEMENT_E = ROOT / "research" / "placement" / "test-e" / "placement-e.json"
SCORING_E = ROOT / "research" / "placement" / "test-e" / "otel-e.json"
TIERS = ROOT / "research" / "placement" / "declared" / "otel.effort.json"
LEGACY_C_READOUT = ROOT / "research" / "traffic-sweep" / "readout-teastore-c-v3.1" / "sweep_analysis_v3.json"
FROZEN_DIGESTS = {   # FREEZE_V33_20261014.md digest table (the chain this script imports)
    "research/detection-time/sweep_analysis_v3_3.py": "c8cd5072ed4b22cae9360e6446f969c75b4e66b900a08d3cfe0efbdadcd36e18",
    "research/placement/celf_v3_3.py": "5d801f634d4d359a0b49c51faf390244eee99c09241c99bc778f0e20929d1ead",
    "research/placement/score_test_v3_3.py": "704cf341ae23e09a123915e14b4546dc1e3b02b3cf7bf2fa4808059acbd2e442",   # after freeze step 2 (F placement pin, bf8e24c)
    "research/protocol/parameters_v3_3.json": "a85daa482b487e4600d11c91dbdecac9a98b01fcd542b9ef051c06cf1268f4b7",
    "research/placement/celf_v3_2.py": "cc7157d858ce3a92fd236e0ce982a7421b4f2a69ad81b06a5ea59b7fb8b88e12",
    "research/placement/score_test_v3_2.py": "f9942b9138f1d1216ed3d3466949c727f6388980e24fff4ce40af994fbf64a07",
    "research/placement/celf_v3.py": "3823722125e9796e6716a830b01d12c69177c7ab6b0a0d7a5fa3984ab6205e97",
    "research/otel-offpath/adapter.py": "22f627dcd1bffdf3f92a151e0d9935f9e2b284a07c905737594d1e95f40bc0b9",
}


def _make(name, args, evidence):
    out = CACHE / name
    if out.exists():
        return out / "sweep_analysis_v3_3.json"
    if not evidence.exists():
        pytest.skip("evidence %s is not on this machine" % evidence)
    CACHE.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(READER)] + args + ["--out", str(out)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return out / "sweep_analysis_v3_3.json"


@pytest.fixture(scope="module")
def e_train_path():
    return _make("train", [str(E_EVIDENCE), "--system", "otel", "--blocks", "1", "2", "3", "--split", str(SPLIT_E)], E_EVIDENCE)


@pytest.fixture(scope="module")
def e_score_path():
    return _make("score", [str(E_EVIDENCE), "--system", "otel", "--split", str(SPLIT_E), "--test-blocks", "4", "5"], E_EVIDENCE)


@pytest.fixture(scope="module")
def c_ts_path():
    return _make("teastore-c", [str(C_EVIDENCE), "--system", "teastore"], C_EVIDENCE)


@pytest.fixture(scope="module")
def e_train(e_train_path):
    return json.loads(e_train_path.read_text())


@pytest.fixture(scope="module")
def e_score(e_score_path):
    return json.loads(e_score_path.read_text())


@pytest.fixture(scope="module")
def c_ts(c_ts_path):
    return json.loads(c_ts_path.read_text())


@pytest.fixture(scope="module")
def e_run(e_train_path, e_score_path, tmp_path_factory):
    """The whole OTel part on E: both placements built and scored once (module scope)."""
    out = tmp_path_factory.mktemp("posthoc") / "out"
    T = json.loads(e_train_path.read_text())
    S = json.loads(e_score_path.read_text())
    P = json.loads(PLACEMENT_E.read_text())
    za = ph.zero_alarm_part(T, ph.sha256(e_train_path), S, e_train_path, (PLACEMENT_E, ph.sha256(PLACEMENT_E), P), str(TIERS),
                            "postureCurrentCatalog", SPLIT_E, [4, 5], out)
    return {"za": za, "out": out}


def _set(za, which, budget, rk="25"):
    return za["placements"][which]["scoring"][rk]["sets"][ph.frontier_label(budget=budget)]


# =========================================================================== frozen chain untouched

def test_frozen_chain_digests_equal_the_freeze_table():
    """The script imports the frozen chain; none of it may differ from FREEZE_V33_20261014.md (read-only check of what the run used)."""
    for rel, want in FROZEN_DIGESTS.items():
        assert ph.sha256(ROOT / rel) == want, rel


def test_costs_of_is_restored_after_the_override():
    orig = cv.costs_of
    with ph.zero_alarm_costs() as wrapped:
        assert cv.costs_of is wrapped and wrapped is not orig
    assert cv.costs_of is orig


# =========================================================================== part 1: zero-alarm frontier (REAL E)

def test_part1_decision73_rerun_equals_the_frozen_e_placement(e_run):
    bc = e_run["za"]["baselineCheck"]
    assert bc["ratesEqualFrozen"] is True            # same code path, same sets, every key, as celf_v3_2's frozen E placement


def test_part1_scoring_of_the_rerun_equals_the_committed_e_scoring(e_run):
    """The decision-73 placement scored through score_test_v3_3 gives the numbers the committed v3.2 scoring of the frozen E placement has."""
    committed = json.loads(SCORING_E.read_text())["rates"]["25"]["sets"]
    for b in ph.BUDGETS:
        lab = ph.frontier_label(budget=b)
        mine, ref = _set(e_run["za"], "decision73", b), committed[lab]
        assert mine["D"] == pytest.approx(ref["D"], abs=1e-9) and mine["g"] == pytest.approx(ref["g"], abs=1e-9)
        assert mine["detectedEpisodes"] == ref["detectedEpisodes"]


def test_part1_zero_alarm_reprices_only_the_flagged_ids_and_changes_the_6_over_Tr_set(e_run, e_train):
    za = e_run["za"]
    r = za["rates"]["25"]
    cr = e_train["calibration"]["primary"]["perRate"]["25"]
    flagged = ph.zero_alarm_ids(cr)
    assert r["repricedIds"] == len(flagged) == 3743
    assert r["unevaluatedLeftAtFill"] == 5                        # placeable, foldsEvaluated 0 but not appear-only: stay at decision 73's fill
    assert r["zeroAlarmPricePerHour"] == pytest.approx(ph.ZERO_ALARM_FACTOR / cr["hours"])
    assert r["setsDifferByBudget"] == {"0": False, "3/T_r": False, "6/T_r": True, "6/h": False, "inf": False}
    mem = [m["id"] for m in r["membersUnrestrictedCell"]["6/T_r"]]
    assert mem == ["metric:flagd:http.server.duration~rate", "log:kafka:28ec81d9cba3"]
    kafka = [m for m in r["membersUnrestrictedCell"]["6/T_r"] if m["id"] == "log:kafka:28ec81d9cba3"][0]
    assert kafka["basis"].startswith("zero-alarm") and kafka["priceZeroAlarmRow"] == pytest.approx(ph.ZERO_ALARM_FACTOR / cr["hours"])
    assert kafka["priceDecision73"] == pytest.approx(r["decision73FillPerHour"])
    # the decision-73 frontier fits one zero-alarm sensor, the zero-alarm row two (budget 6/T_r = 40/h, 19.97/h each)
    assert _set(za, "decision73", "6/T_r")["size"] == 1 and _set(za, "zeroAlarm", "6/T_r")["size"] == 2


def test_part1_zero_alarm_test_numbers_on_e(e_run):
    z, d = _set(e_run["za"], "zeroAlarm", "6/T_r"), _set(e_run["za"], "decision73", "6/T_r")
    assert d["g"] == pytest.approx(0.0, abs=1e-12) and d["detectedEpisodes"] == [3, 6]
    assert z["g"] == pytest.approx(5.292, abs=5e-4) and z["detectedEpisodes"] == [5, 6]
    acc = z["perClass"]["accounting-pause-effect"]
    assert acc["improved"] == 2 and acc["episodes"] == 2 and acc["gClass"] == pytest.approx(15.875, abs=5e-4)
    assert z["perClass"]["fraud-pause-effect"]["improved"] == 0


def test_part1_planted_defect_no_repricing_is_seen(e_train_path, tmp_path, monkeypatch):
    """PRICE_ZERO_ALARM False: the 'zero-alarm' placement is the decision-73 placement; the sets-differ assertion would fail."""
    monkeypatch.setattr(ph, "PRICE_ZERO_ALARM", False)
    P = ph.run_celf(e_train_path, str(TIERS), "postureCurrentCatalog", SPLIT_E, tmp_path / "p.json", True)
    base = json.loads(PLACEMENT_E.read_text())
    assert ph._pt(P, "25", "6/T_r") == ph._pt(base, "25", "6/T_r")                        # defect: no change
    assert len(ph._pt(P, "25", "6/T_r")) == 1


def test_part1_planted_defect_three_over_Tr_price_is_seen(e_train_path, e_train, tmp_path, monkeypatch):
    """ZERO_ALARM_FACTOR 3.0 (celf_v3's test switch value) would price the flagged ids at 3.0/T_r, not 2.9957/T_r."""
    monkeypatch.setattr(ph, "ZERO_ALARM_FACTOR", 3.0)
    P = ph.run_celf(e_train_path, str(TIERS), "postureCurrentCatalog", SPLIT_E, tmp_path / "p.json", True)
    hours = e_train["calibration"]["primary"]["perRate"]["25"]["hours"]
    c = P["rates"]["25"]["costs"]["log:kafka:28ec81d9cba3"]
    assert c == pytest.approx(3.0 / hours) and c != pytest.approx(-ph.math.log(0.05) / hours)


def test_part1_scorer_pin_for_readouts_stays_enforced(e_train_path, e_score, e_train, tmp_path):
    """allow_unpinned waives the PLACEMENT pin only: a scoring readout of another reader digest is still refused."""
    P = ph.run_celf(e_train_path, str(TIERS), "postureCurrentCatalog", SPLIT_E, tmp_path / "p.json", True)
    bad = dict(e_score, scriptSha256="0" * 64)
    with pytest.raises(SystemExit):
        ph.score_placement(bad, P, ph.sha256(tmp_path / "p.json"), [4, 5], e_train, ph.sha256(e_train_path))


# =========================================================================== part 2: OTel lane predictions

def test_part2_real_e_predictions(e_score):
    preds = {p["id"]: p for p in ph.otel_predictions(e_score)}
    assert preds["F-L1"]["result"] == "hit" and preds["F-L1"]["numbers"]["k"] == 4 and preds["F-L1"]["numbers"]["n"] == 4
    assert all(e["earliest"]["field"] == "by-construction" and e["earliest"]["ttd"] < 2.0 for e in preds["F-L1"]["numbers"]["episodes"])
    n2 = preds["F-L2"]["numbers"]
    assert preds["F-L2"]["result"] == "hit" and n2["offpathInWindow"] == 4
    ts = sorted(e["countedEarliest"]["ttd"] for e in n2["episodes"])
    assert 43.0 < ts[0] and ts[-1] < 44.5                              # E: 43.4-44.3 s
    assert n2["frontendNoCountedFire"] and n2["frontendNoFireEitherField"]
    assert preds["F-L3"]["result"] == ph.DASH and preds["F-L3"]["numbers"]["lagIdsInCalibration"] == 0
    m = preds["F-M"]
    assert m["result"] == "miss" and m["numbers"]["placeableNonFlagdSdk"] == 0 and m["numbers"]["placeableNonFlagdSpanmetrics"] == 0
    assert m["numbers"]["placeableFlagd"] == 5


def test_part2_planted_defect_every_episode_instead_of_held_out_is_seen(e_score, monkeypatch):
    """HELD_OUT_ONLY False: training episodes join, the denominator is 10 off-path episodes, not the declared 4."""
    monkeypatch.setattr(ph, "HELD_OUT_ONLY", False)
    preds = {p["id"]: p for p in ph.otel_predictions(e_score)}
    assert preds["F-L1"]["numbers"]["n"] == 10 and preds["F-L1"]["result"] == ph.DASH


def test_part2_metric_class_rule():
    assert ph.metric_class("metric:cartservice:calls") == "spanmetrics"
    assert ph.metric_class("metric:cartservice:duration~rate") == "spanmetrics"
    assert ph.metric_class("metric:cartservice:duration~mean") == "spanmetrics"
    for sdk in ("metric:cartservice:rpc.server.duration~rate", "metric:x:http.server.duration~mean", "metric:x:jvm.cpu.time",
                "metric:kafka:kafka.consumer_group.lag"):
        assert ph.metric_class(sdk) == "sdk"


def _lane(collected, counted=None, bc=None, cf=0, bf=0):
    rec = lambda t: None if t is None else {"ttd": t, "ttdLo": t, "sensor": "x:y:z", "rule": "appear", "bcFlags": []}  # noqa: E731
    return {"collectedSensors": collected, "countedFires": cf if counted is None else max(cf, 1), "distinctSensors": 0,
            "earliest": rec(counted), "byConstructionFires": bf if bc is None else max(bf, 1), "earliestByConstruction": rec(bc)}


def _synthetic_scoring(lag_placeable=None, lag_in_calibration=False, metrics=(), own=1.0, coord=44.0, lag=30.0, fe_bc=0, extra_fraud=False):
    """Scoring readout shell: 2 test episodes per off-path class (4) and 2 frontend; each lane value overridable."""
    eps, rows = [], {}
    for regime in ph.OFFPATH_REGIMES_OTEL + (ph.CONTROL_REGIME_OTEL,):
        rows[regime] = {"target": "t", "episodes": []}
        for b in (4, 5):
            cell = "%s-b%d" % (regime, b)
            eps.append({"cell": cell, "regime": regime})
            fe = regime == ph.CONTROL_REGIME_OTEL
            rows[regime]["episodes"].append({
                "cell": cell, "rate": 25.0, "block": b, "heldOut": True, "target": "t",
                "lanes": {"own": _lane(5, bc=own), "coordinator": _lane(9, counted=None if fe else coord, bf=fe_bc if fe else 0,
                                                                          bc=0.5 if (fe and fe_bc) else None),
                          "lag": _lane(2 if lag_in_calibration else 0, counted=None if (fe or lag is None) else lag)}})
    sens = {"metric:kafka:kafka.consumer_group.lag": {"placeable": bool(lag_placeable), "family": "M"}} if lag_in_calibration else {}
    for m in metrics:
        sens[m] = {"placeable": True, "family": "M"}
    return {"episodes": eps, "calibration": {"primary": {"perRate": {"25": {"hours": 0.3, "sensors": sens}}}},
            "v33": {"lanes": {"rules": {"coordinator": {"service": "kafka", "channels": ["log"], "tokenPrefixes": [""]},
                                        "lag": {"service": "kafka", "channels": ["metric"], "tokenPrefixes": ["kafka.consumer_group.lag"]}},
                              "regimes": rows}}}


def test_part2_synthetic_f_l3_branches_and_boundaries():
    p = {x["id"]: x for x in ph.otel_predictions(_synthetic_scoring())}
    assert p["F-L1"]["result"] == "hit" and p["F-L2"]["result"] == "hit" and p["F-L3"]["result"] == ph.DASH and p["F-M"]["result"] == "miss"
    # lag ids present but unarmed -> —
    assert ph.otel_predictions(_synthetic_scoring(lag_in_calibration=True, lag_placeable=False))[2]["result"] == ph.DASH
    # armed and earlier than the coordinator in 4/4 -> hit; later than it -> miss
    assert ph.otel_predictions(_synthetic_scoring(lag_in_calibration=True, lag_placeable=True, lag=30.0))[2]["result"] == "hit"
    assert ph.otel_predictions(_synthetic_scoring(lag_in_calibration=True, lag_placeable=True, lag=50.0))[2]["result"] == "miss"
    # boundaries: F-L1 strict below 2.0, F-L2 window inclusive 42-47
    assert ph.otel_predictions(_synthetic_scoring(own=2.0))[0]["result"] == "miss"
    assert ph.otel_predictions(_synthetic_scoring(coord=41.9))[1]["result"] == "miss"
    assert ph.otel_predictions(_synthetic_scoring(coord=47.0))[1]["result"] == "hit"
    # a by-construction fire in a frontend episode negates 'no fire'
    assert ph.otel_predictions(_synthetic_scoring(fe_bc=1))[1]["result"] == "miss"
    # F-M: a non-flagd SDK metric and a spanmetrics metric are counted separately
    fm = ph.otel_predictions(_synthetic_scoring(metrics=("metric:a:rpc.server.duration~rate", "metric:b:calls", "metric:flagd:x")))[3]
    assert fm["result"] == "hit" and fm["numbers"]["placeableNonFlagdSdk"] == 1 and fm["numbers"]["placeableNonFlagdSpanmetrics"] == 1


# =========================================================================== part 3: TeaStore (PLUMBING on C, SYNTHETIC)

def test_part3_plumbing_on_c_auth_freeze_standin(c_ts):
    """PLUMBING: C has no recommender pause; its auth-freeze episodes stand in. Proves the fields are read, not the recommender."""
    preds = {p["id"]: p for p in ph.teastore_predictions(c_ts, "auth-freeze-effect", "auth", None)}
    tc = preds["T-C"]
    assert tc["result"] == "hit" and tc["numbers"]["k"] == 12 == tc["numbers"]["n"]
    t2 = preds["T-L2"]
    assert t2["numbers"]["n"] == 12 and t2["numbers"]["k"] == 12 and t2["result"] == "hit"
    for e in t2["numbers"]["episodes"]:
        assert e["inWindowFire"]["field"] == "by-construction" and 9.0 < e["inWindowFire"]["ttd"] < 12.0       # C: auth line 9.1-11.7 s
        rl = e["applicationLogRemovalLine"]
        assert rl["present"] and rl["lagSeconds"] == pytest.approx(e["inWindowFire"]["ttd"], abs=0.05)         # the log stamp agrees with the fire
    t1 = preds["T-L1"]["numbers"]["episodes"]
    assert [e["below5s"] for e in t1 if e["rate"] == 10.0] == [True, True, True]
    assert all(not e["below5s"] for e in t1 if e["rate"] != 10.0)
    assert all(e["earliest"]["ttd"] > 4.0 for e in t1 if e["earliest"] and e["rate"] == 10.0)                   # stamped at a 5 s sample
    off = preds["T-OFF"]
    assert off["result"] == "miss"                                       # n=12, expected_n None; the login route is ON the auth path
    assert off["numbers"]["okShareClause"]["k"] == 0
    assert all(e["started"] > 0 and e["share"] is not None and e["share"] < 0.05 for e in off["numbers"]["episodes"])


def test_part3_planted_defect_declared_denominator(c_ts):
    """With the declared denominator (10) the 12-episode stand-in regime is `—`, not hit: the denominator is checked."""
    preds = {p["id"]: p for p in ph.teastore_predictions(c_ts, "auth-freeze-effect", "auth", 10)}
    assert preds["T-L2"]["result"] == ph.DASH and preds["T-L1"]["result"] == ph.DASH and preds["T-OFF"]["result"] == ph.DASH


def _ledger(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _row(start, ok=True, wl="login-only-v1", seq=0):
    return {"recordType": "journey-terminal", "workloadId": wl, "actualStartMonotonic": start, "sequence": seq,
            "outcome": "succeeded" if ok else "failed", "requests": [{"statusCode": 200 if ok else 500}]}


def test_part3_t_off_window_and_ok_rule(tmp_path):
    rows = [_row(5.0, False), _row(59.9, False)] + [_row(60.0 + i, True) for i in range(19)] + [_row(80.0, False)] + [
        _row(120.0, True), _row(120.1, False), _row(300.0, False), {"recordType": "journey-start", "actualStartMonotonic": 70.0},
        _row(None, True), _row(70.5, True, wl="other")]
    f = tmp_path / "journey-ledger.jsonl"
    _ledger(f, rows)
    sh = ph.ledger_ok_share(f, 60.0, 60.0)                 # [60, 120]: 19 ok (60..78), 80.0 failed, 120.0 ok, 120.1 outside
    assert sh == {"started": 21, "ok": 20, "share": pytest.approx(20 / 21)}
    # a journey whose outcome is succeeded but one request is not 200 is not ok; an empty request list is not ok
    _ledger(f, [_row(61.0), dict(_row(62.0), requests=[{"statusCode": 200}, {"statusCode": 302}]), dict(_row(63.0), requests=[])])
    assert ph.ledger_ok_share(f, 60.0, 60.0)["ok"] == 1


def test_part3_planted_defect_whole_cell_window_is_seen(tmp_path, monkeypatch):
    f = tmp_path / "journey-ledger.jsonl"
    _ledger(f, [_row(10.0, False), _row(20.0, False), _row(70.0, True), _row(80.0, True)])
    assert ph.ledger_ok_share(f, 60.0, 60.0)["share"] == 1.0
    monkeypatch.setattr(ph, "HOLD_WINDOW_ONLY", False)
    assert ph.ledger_ok_share(f, 60.0, 60.0, not ph.HOLD_WINDOW_ONLY)["share"] == 0.5     # defect: failures outside the hold count


def _ts_fire(sid, rule, ttd, fam="S", dr="down", own=False, counts=True, bc=()):
    return [fam, sid, rule, ttd, dr, own, own, counts, list(bc), 0.0]


def _ts_synthetic(tmp_path, n=10, cpu=(1.0,), reg=(10.0,), ok_ledger=True, ledger_fire=False):
    eps = []
    for i in range(n):
        cell = tmp_path / ("cell%d" % i)
        cell.mkdir()
        _ledger(cell / "journey-ledger.jsonl", [_row(float(t), ok_ledger or t % 2 == 0, seq=t) for t in range(0, 130)])
        fires = [_ts_fire("metric:recommender:sys_cpu", "spike", cpu[i % len(cpu)], own=True, bc=["BC-idle-cpu"]),
                 _ts_fire("log:registry:abc", "appear", reg[i % len(reg)], fam="L", dr=None, bc=["BC-caller-log"])]
        if ledger_fire:
            fires.append(_ts_fire("ledger:webui:login-only-v1", "failed", 12.0, fam="E", dr="up"))
        eps.append({"regime": "recommender-pause-effect", "rate": 10.0 if i < 5 else 1.0, "block": i % 5 + 1, "holdSeconds": 60.0,
                    "onset": {"mono": 60.0, "wall": 1000.0}, "cell": "%s :: ." % cell, "fires": fires})
    return {"episodes": eps, "predictions": {"P1": {"holds": True, "k": 4, "n": 4, "perRate": {}}},
            "v33": {"lanes": {"rules": {"coordinator": {"service": "registry", "channels": ["log"], "tokenPrefixes": [""]}, "lag": None}}}}


def test_part3_synthetic_declared_recommender_run(tmp_path):
    p = {x["id"]: x for x in ph.teastore_predictions(_ts_synthetic(tmp_path))}
    assert [p[k]["result"] for k in ("T-L1", "T-L2", "T-OFF", "T-C")] == ["hit"] * 4
    assert p["T-L1"]["numbers"]["episodes"][0]["earliest"]["field"] == "by-construction"
    # strict < 5.0 s: one episode at 5.0 s is a miss for that episode; 2 misses of 10 -> overall miss (need 9)
    (tmp_path / "b").mkdir()
    p = {x["id"]: x for x in ph.teastore_predictions(_ts_synthetic(tmp_path / "b", cpu=(4.9, 5.0, 4.0, 4.0, 4.0)))}
    assert p["T-L1"]["numbers"]["k"] == 8 and p["T-L1"]["result"] == "miss"


def test_part3_synthetic_window_edges_denominator_and_ledger_fire(tmp_path):
    (tmp_path / "a").mkdir()
    p = {x["id"]: x for x in ph.teastore_predictions(_ts_synthetic(tmp_path / "a", reg=(7.5, 12.5, 7.4, 12.6, 10.0)))}
    assert p["T-L2"]["numbers"]["k"] == 6 and p["T-L2"]["result"] == "miss"            # 7.4 and 12.6 are outside, edges inclusive
    (tmp_path / "b").mkdir()
    p = {x["id"]: x for x in ph.teastore_predictions(_ts_synthetic(tmp_path / "b", n=9))}
    assert p["T-L1"]["result"] == ph.DASH and p["T-OFF"]["result"] == ph.DASH           # denominator 9, declared 10
    (tmp_path / "c").mkdir()
    p = {x["id"]: x for x in ph.teastore_predictions(_ts_synthetic(tmp_path / "c", ledger_fire=True))}
    assert p["T-OFF"]["numbers"]["okShareClause"]["k"] == 10 and p["T-OFF"]["numbers"]["noCountedLedgerFireClause"] is False
    assert p["T-OFF"]["result"] == "miss"                                                  # a counted ledger fire is attributable
    (tmp_path / "d").mkdir()
    p = {x["id"]: x for x in ph.teastore_predictions(_ts_synthetic(tmp_path / "d", ok_ledger=False))}
    assert p["T-OFF"]["result"] == "miss" and p["T-OFF"]["numbers"]["okShareClause"]["k"] == 0


# =========================================================================== part 4: condition 1 (one setup ID)

def _campaign(base, name, ids):
    d = base / name / "campaign-x"
    d.mkdir(parents=True)
    for i, sid in enumerate(ids):
        sub = base / name / ph.SETUP_DIRS[i % 3]
        sub.mkdir(exist_ok=True)
        (sub / ("r%d.json" % i)).write_text(json.dumps({"setupId": sid}))
    return str(d)


def test_part4_one_setup_on_c_and_refusals_on_real_and_synthetic(c_ts, tmp_path):
    rec = ph.check_one_setup(c_ts)
    assert rec["ok"] and rec["setupIds"] == ["8cafbe550f9b5d38272aa97f2b345347"]          # C relaunch 1, fetch_overnight.sh teastorec1r1
    assert ph.check_one_setup(c_ts, "8cafbe550f9b5d38272aa97f2b345347")["ok"]
    with pytest.raises(ph.Refused):
        ph.check_one_setup(c_ts, "0" * 32)
    if LEGACY_C_READOUT.exists():                                                         # real: six campaigns pooled (the attempt-1 + relaunch trap)
        J = {"campaignsRead": json.loads(LEGACY_C_READOUT.read_text())["campaignsRead"]}
        with pytest.raises(ph.Refused):
            ph.check_one_setup(J)
    two = {"campaignsRead": [{"campaign": _campaign(tmp_path, "a", ["s1"])}, {"campaign": _campaign(tmp_path, "b", ["s2"])}]}
    with pytest.raises(ph.Refused):
        ph.check_one_setup(two)
    two_ids = {"campaignsRead": [{"campaign": _campaign(tmp_path, "c", ["s1", "s2"])}]}
    with pytest.raises(ph.Refused):
        ph.check_one_setup(two_ids)
    none = {"campaignsRead": [{"campaign": str(tmp_path / "nowhere" / "x")}]}
    with pytest.raises(ph.Refused):
        ph.check_one_setup(none)                                                          # no receipt: cannot be shown to be one setup
    same = {"campaignsRead": [{"campaign": _campaign(tmp_path, "d", ["s1", "s1", "s1"])}]}
    assert ph.check_one_setup(same)["setupIds"] == ["s1"]                                 # the same ID in three receipts is one setup


def test_part4_planted_defect_enforcement_off_is_seen(tmp_path, monkeypatch):
    two = {"campaignsRead": [{"campaign": _campaign(tmp_path, "a", ["s1"])}, {"campaign": _campaign(tmp_path, "b", ["s2"])}]}
    monkeypatch.setattr(ph, "REQUIRE_ONE_SETUP", False)
    rec = ph.check_one_setup(two)                                                         # defect: no refusal
    assert rec["ok"] is False and len(rec["setupIds"]) == 2


def test_part4_run_teastore_refuses_before_reading_predictions(c_ts_path, tmp_path):
    """The CLI path checks condition 1 first: a bad expected setup ID stops the run and writes nothing."""
    out = tmp_path / "out"
    with pytest.raises(ph.Refused):
        ph.main(["teastore", "--readout", str(c_ts_path), "--regime", "auth-freeze-effect", "--expect-setup-id", "f" * 32,
                 "--out-dir", str(out)])
    assert not out.exists()


# =========================================================================== CLI end to end and the no-verdict rule

def _keys(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            acc.add(str(k))
            _keys(v, acc)
    elif isinstance(o, list):
        for v in o:
            _keys(v, acc)
    return acc


def test_cli_otel_on_e_writes_new_files_labelled_post_hoc_without_a_verdict(e_train_path, e_score_path, tmp_path):
    out = tmp_path / "o"
    assert ph.main(["otel", "--training-readout", str(e_train_path), "--scoring-readout", str(e_score_path), "--placement",
                    str(PLACEMENT_E), "--split", str(SPLIT_E), "--out-dir", str(out)]) == 0
    J = json.loads((out / "posthoc_lanes_v33_otel.json").read_text())
    md = (out / "posthoc_lanes_v33_otel.md").read_text()
    assert "POST HOC" in J["label"] and "POST HOC" in md and "POST HOC" in ph.__doc__
    assert not any("verdict" in k.lower() for k in _keys(J, set()))
    assert '"PASS"' not in json.dumps(J) and '"FAIL"' not in json.dumps(J)
    assert [p["id"] for p in J["predictions"]] == ["F-L1", "F-L2", "F-L3", "F-M"]
    for new in ("placements/decision73_rerun.json", "placements/zero_alarm.json"):
        assert (out / new).exists()
    with pytest.raises(ph.Refused):                                                       # an existing output dir is refused
        ph.main(["otel", "--training-readout", str(e_train_path), "--scoring-readout", str(e_score_path), "--placement",
                 str(PLACEMENT_E), "--split", str(SPLIT_E), "--out-dir", str(out)])


def test_cli_teastore_plumbing_on_c(c_ts_path, tmp_path):
    out = tmp_path / "t"
    assert ph.main(["teastore", "--readout", str(c_ts_path), "--regime", "auth-freeze-effect", "--out-dir", str(out)]) == 0
    J = json.loads((out / "posthoc_lanes_v33_teastore.json").read_text())
    assert J["plumbing"] is True and J["condition1"]["ok"] and [p["id"] for p in J["predictions"]] == ["T-L1", "T-L2", "T-OFF", "T-C"]
    assert not any("verdict" in k.lower() for k in _keys(J, set()))
    assert "PLUMBING" in (out / "posthoc_lanes_v33_teastore.md").read_text()


def test_planted_a_pinned_scorer_still_scores_a_post_hoc_placement(monkeypatch):
    """F's pin made the post hoc rescoring refuse; score_placement must empty the placement pin for its call only and restore it."""
    import posthoc_lanes_v33 as ph
    seen = {}
    monkeypatch.setattr(ph.s3, "PINNED_PLACEMENTS", {"otel": "f" * 64})
    def fake_score(*a, **k):
        seen["pins"] = dict(ph.s3.PINNED_PLACEMENTS)
        return {}
    monkeypatch.setattr(ph.s3, "score", fake_score)
    ph.score_placement({}, {}, "0" * 64, [4, 5], {}, "1" * 64)
    assert seen["pins"] == {} and ph.s3.PINNED_PLACEMENTS == {"otel": "f" * 64}
