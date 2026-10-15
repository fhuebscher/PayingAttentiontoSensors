"""Analysis v3.3 (research/detection-time/sweep_analysis_v3_3.py, research/protocol/parameters_v3_3.json, research/placement/
celf_v3_3.py, research/placement/score_test_v3_3.py): admission of OTel campaign F's epoch and the TeaStore off-path epoch, the
Kafka metric ids under service `kafka`, and the per-regime lanes report (BUDGET_F.md / BUDGET_TEASTORE_OFFPATH.md step 4).

Layer: reader + synthetic end-to-end. Synthetic cells only, modelled on tests/test_sweep_analysis_v3_2.py: the harness-written
OTel and TeaStore cells of tests/fixtures/sweep_v22, post-edited into the SHAPE the registry pins (parameters_v3_3.json,
re-pinned to the harness commits 715d57b and f74b29b; no real cell of either epoch was read). Every v3.3 change has a planted defect
(its switch off) under which one of its checks fails (test_check_passes_and_fails_with_its_switch_off), the frozen v3.2 chain is
untouched (digests), and a v3.3 read of E reproduces v3.2's (checked once offline against the committed E training readout; the
synthetic equivalent is test_legacy_readouts_are_v32s).
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))
sys.path.insert(0, str(ROOT / "research" / "placement"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_analysis_v3_3 as v33  # noqa: E402
import test_sweep_analysis_v22_systems as t22  # noqa: E402
import test_sweep_analysis_v3_2 as t32  # noqa: E402

v32, v31, v24 = v33.v32, v33.v31, v33.v24
EPOCH_E, EPOCH_F = "otel-offpath-e-v1", "otel-offpath-f-v1"
TS_EPOCH = "teastore-offpath-v1"
FRAUD, ACCT, FRONT = t32.FRAUD, t32.ACCT, t22.OT_PAUSE
REC, AUTH = "recommender-pause-effect", "auth-freeze-effect"
NO_SPLIT = {"train": None, "test": None}


@pytest.fixture(autouse=True)
def _no_registry_split(monkeypatch):
    """As in the v3.2 tests: the synthetic campaigns use blocks 1-3, so the registry's 3+2 split is switched off here."""
    monkeypatch.setattr(v32, "E_SPLIT", NO_SPLIT)


# ----------------------------------------------------------------------------- synthetic campaigns

def _zap(e):
    return datetime.datetime.fromtimestamp(e, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _utc(e):
    whole = int(e)
    return datetime.datetime.fromtimestamp(whole, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + \
        ".%09d +0000 UTC" % int(round((e - whole) * 1e9))


def kafka_metric_lines(barrier, value_of, name="kafka.consumer_group.lag", service="kafka", step=5, n=36, group="g"):
    """debug-exporter text (collector 0.108) of a kafkametrics gauge, one data point every `step` s from the barrier; the
    resource carries service.name=`service` (None: no service.name, as a receiver without the upsert)."""
    out = []
    for i in range(n):
        t = barrier + i * step + 0.5
        out += ["otelcol-1  | %s\tinfo\tResourceMetrics #0" % _zap(t), "otelcol-1  | Resource SchemaURL: ",
                "otelcol-1  | Resource attributes:"]
        if service:
            out.append("otelcol-1  |      -> service.name: Str(%s)" % service)
        out += ["otelcol-1  | ScopeMetrics #0", "otelcol-1  | ScopeMetrics SchemaURL: ",
                "otelcol-1  | InstrumentationScope kafkametricsreceiver 0.108.0", "otelcol-1  | Metric #0",
                "otelcol-1  | Descriptor:", "otelcol-1  |      -> Name: %s" % name, "otelcol-1  |      -> Description: d",
                "otelcol-1  |      -> Unit: 1", "otelcol-1  |      -> DataType: Gauge", "otelcol-1  | NumberDataPoints #0",
                "otelcol-1  | Data point attributes:", "otelcol-1  |      -> group: Str(%s)" % group,
                "otelcol-1  | StartTimestamp: 1970-01-01 00:00:00 +0000 UTC", "otelcol-1  | Timestamp: %s" % _utc(t),
                "otelcol-1  | Value: %f" % value_of(i, t - barrier)]
    return out


def add_kafka(d, onset_after=None):
    """Kafka lag gauges into a cell's otelcol.log: 3..5 (jitter) before the fault, 5000 from `onset_after` s after the barrier."""
    barrier = json.loads((d / "request-ledger.json").read_text())["barrierEpoch"]
    lines = kafka_metric_lines(barrier, lambda i, rel: 5000.0 if (onset_after is not None and rel >= onset_after)
                               else 3.0 + (i % 3))
    with (d / "otelcol.log").open("a") as fh:
        fh.write("\n".join(lines) + "\n")
    return barrier


def f_campaign(dest, epoch=EPOCH_F):
    """The v3.2 off-path fixture (E's shape, no throttle) restamped to F's epoch, with Kafka lag gauges in every cell (a spike
    in the fraud cell 75 s after the barrier) and one Kafka log line inside the fraud cell's fault window."""
    camp = t32.offpath_campaign(dest)
    t32._set_epoch(camp, epoch, multi=False)
    add_kafka(t22._cell_dir(camp, t22.OT_NF))
    for regime in (ACCT, FRONT):
        add_kafka(t22._cell_dir(camp, regime))
    fr = t22._cell_dir(camp, FRAUD)
    b = add_kafka(fr, onset_after=75)
    with (fr / "application.log").open("a") as fh:
        fh.write("kafka-1  | %s [GroupCoordinator 1]: Member consumer-fraud-detection-1 in group fraud-detection has "
                 "failed\n" % _zap(b + 80))
    return camp


def ts_campaign(dest, epoch=TS_EPOCH, keep_throttle=False, rec_service="recommender", rec_regime=REC):
    """The TeaStore fixture restamped to the off-path epoch, without the throttle cell (unless kept), plus a recommender-pause
    cell cloned from the auth-freeze cell (block 2) and one registry log line inside its fault window."""
    camp = t22._copy(t22.TS_CAMP, dest)
    if not keep_throttle:
        shutil.rmtree(t22._cell_dir(camp, t22.TS_THROTTLE).parent)
    auth = t22._cell_dir(camp, AUTH)
    d = camp / "runs" / rec_regime / auth.name
    shutil.copytree(auth, d)
    t22._edit_json(d / "receipt.json", lambda rc: rc["run"].update(regime=rec_regime, block=2))
    t22._edit_json(d / "intervention.json", lambda iv: iv.update(service=rec_service))
    for rp in sorted((camp / "runs").rglob("receipt.json")):
        t22._edit_json(rp, lambda rc: rc.__setitem__("studyEpoch", epoch))
    barrier = v24.dt.epoch(json.loads((d / "receipt.json").read_text())["window"]["measurementStartedAt"])
    with (d / "application.log").open("a") as fh:
        fh.write("registry-1  | %s 05-Oct-2026 06:00:01.123 INFO [main] org.example.fixture.Registry.remove removed "
                 "heartbeat instance\n" % t22._docker_stamp(barrier + 80.0))
    return camp


def cells33(camps, system="otel", blocks=None):
    camps = list(camps)
    with v24.use_system(system), v33._v33_wrapped(bool(v33.epochs_present(camps, system))), \
            v32.v32_context(system, None, blocks):
        return v31.find_and_load3(camps)[1]


def run(camps, system="otel", **kw):
    R = v33.run33(camps, system=system, reference=False, **kw)
    with v24.use_system(system):
        v31.finish(R)
    return R


@pytest.fixture(scope="module")
def f_world(tmp_path_factory):
    base = tmp_path_factory.mktemp("v33f")
    camp = f_campaign(base / "f")
    return {"base": base, "camp": camp, "quiet": t32.quiet(camp, base / "q")}


@pytest.fixture(scope="module")
def f_result(f_world):
    with pytest.MonkeyPatch.context() as mp:           # module-scoped: the autouse per-test patch is not yet in force
        mp.setattr(v32, "E_SPLIT", NO_SPLIT)
        return run([f_world["camp"], f_world["quiet"]])


@pytest.fixture(scope="module")
def ts_world(tmp_path_factory):
    base = tmp_path_factory.mktemp("v33ts")
    camp = ts_campaign(base / "t")
    return {"base": base, "camp": camp,
            "quiet": t22._quiet_campaign(camp, t22.TS_NF, base / "q", system="teastore")}


# ----------------------------------------------------------------------------- 8.3: OTel F is admitted like E

def chk_f_admitted(tmp_path, _world=None):
    camp = f_campaign(tmp_path / "c")
    cells = cells33([camp])
    f = next(c for c in cells if c["valid"] and c["regime"] == FRAUD)
    return (all(c["valid"] for c in cells) and {c["studyEpoch"] for c in cells} == {EPOCH_F}
            and {c["harness"] for c in cells} == {"B"} and {c["regime"] for c in cells} == {FRAUD, ACCT, FRONT, t22.OT_NF}
            and f["target"] == "frauddetectionservice" and f["h4"]["status"] == "used")


def test_f_epoch_is_driven_through_the_loader(tmp_path):
    """Decision-92 lesson: a synthetic cell of the new epoch goes through find_and_load3 (the v3.3 context) and is a valid
    campaign-B-shaped cell with E's regimes; the same cells under v3.2's own context are an unknown epoch."""
    assert chk_f_admitted(tmp_path / "v33")
    camp = f_campaign(tmp_path / "v32")
    with pytest.raises(v24.UnknownSchema):
        t32.cells_of([camp])


def test_f_has_the_campaign_e_role_so_the_split_machinery_applies(tmp_path):
    """F is a campaign-E-role epoch: --blocks selects its cells by receipt only, and E and F are never read in one run."""
    assert EPOCH_F in v33.profiles_for("otel") and v33.profiles_for("otel")[EPOCH_F]["role"] == "campaign-E"
    camp = f_campaign(tmp_path / "c")
    cells = cells33([camp], blocks={1, 2})
    assert {c["block"] for c in cells} == {1, 2} and ACCT not in {c["regime"] for c in cells}
    e = t32.offpath_campaign(tmp_path / "e", epoch=EPOCH_E)
    with pytest.raises(SystemExit, match="different v3.2 epochs"):
        cells33([camp, e])


def test_f_has_no_throttle_regime(tmp_path):
    camp = t32.t3._ot_b_campaign(tmp_path / "c")
    t32._set_epoch(camp, EPOCH_F)
    with pytest.raises(v24.UnknownSchema, match="productcatalog-cpu-throttle-effect"):
        cells33([camp])


def test_f_two_no_fault_cells_of_a_block_stay_two_calibration_cells(tmp_path):
    """F has two no-fault cells per block, same regime, rate and block, told apart by runKey.replicate (1, 2) and by their
    directory (r<rate>-b<BB>-<NN>-full). The reader keeps them as two cells: two cell keys, two valid no-fault cells in the
    (regime, rate) count, two entries in the calibration's no-fault hours. (A reader keying cells by (regime, rate, block) would
    show one.)"""
    camp = f_campaign(tmp_path / "c")
    nf = t22._cell_dir(camp, t22.OT_NF)
    t22._edit_json(nf / "receipt.json", lambda rc: rc["runKey"].__setitem__("replicate", 1))
    twin = nf.parent / "r1-b01-99-full"
    shutil.copytree(nf, twin)
    t22._edit_json(twin / "receipt.json", lambda rc: rc["runKey"].__setitem__("replicate", 2))
    cells = [c for c in cells33([camp]) if c["regime"] == t22.OT_NF]
    assert len(cells) == 2 and all(c["valid"] for c in cells) and {c["block"] for c in cells} == {1}
    assert len({c["cellKey"] for c in cells}) == 2 and len({c["cell"] for c in cells}) == 2
    R = run([camp])
    assert R["valid"][(t22.OT_NF, 1.0)] == 2 and R["found"][(t22.OT_NF, 1.0)] == 2
    one = run([f_campaign(tmp_path / "one")])
    cal = lambda r: r["cal"]["primary"]["perRate"][1.0]
    assert cal(one)["cells"] == 1 and cal(R)["cells"] == 2                    # two calibration cells, not merged
    assert abs(cal(R)["hours"] - 2 * cal(one)["hours"]) < 1e-9                 # two cells' no-fault time


# ----------------------------------------------------------------------------- 2: Kafka metric ids under service `kafka`

def kafka_admitted(_tmp=None):
    """The reader's own metric parser (v2.4's otel_metrics -> adapter.parse_otelcol), kafkametrics-shaped resources."""
    lines = kafka_metric_lines(1790000000.0, lambda i, rel: 3.0 + i % 3, n=6)
    lines += kafka_metric_lines(1790000000.0, lambda i, rel: 1.0, name="kafka.consumer_group.members", n=6)
    lines += kafka_metric_lines(1790000000.0, lambda i, rel: 7.0, name="kafka.consumer_group.lag_sum", service=None, n=6)
    ev, res = v24.otel_metrics(lines, "full", __import__("collections").Counter())
    ids = {(e[1], e[2]) for e in ev or ()}
    return (("kafka", "kafka.consumer_group.lag") in ids and ("kafka", "kafka.consumer_group.members") in ids
            and not any(t == "kafka.consumer_group.lag_sum" for _, t in ids) and res == 5.0)


def test_kafkametrics_resources_are_admitted_under_service_kafka_without_adapter_edits():
    """service.name=kafka is in APP_SERVICES: lag and members become metric sensors of service `kafka`; a resource the receiver
    left without service.name (no upsert) is dropped by the adapter, which is why BUDGET_F upserts the name."""
    assert kafka_admitted()
    assert v33.LANE_RULES["otel"]["lag"]["service"] in v24.otel_adapter().APP_SERVICES


def test_removing_kafka_from_the_catalog_would_drop_the_ids(monkeypatch):
    A = v24.otel_adapter()
    monkeypatch.setattr(A, "APP_SERVICES", tuple(s for s in A.APP_SERVICES if s != "kafka"))
    assert not kafka_admitted()


def test_min_baseline_pooled_is_unchanged_and_the_fixture_arms_the_lag_sensor(f_result):
    """Item 2 of the brief: with a 5 s export the metric sensors reach the pooled minimum; the constant is not touched (v2.4's
    registry value, 20), and the lag sensor of the F fixture (36 points x 10 no-fault cells) is armed, so it can fire."""
    assert v24.MIN_POOLED == 20
    eps = f_result["results"]["primary"]["eps"]
    fr = next(e for e in eps if e["regime"] == FRAUD)
    assert any(f["svc"] == "kafka" and f["ch"] == "metric" for f in fr["fires"])


# ----------------------------------------------------------------------------- 8.4 / group 4: the TeaStore off-path epoch

def chk_ts_admitted(tmp_path, _world=None):
    camp = ts_campaign(tmp_path / "c")
    cells = cells33([camp], "teastore")
    rec = next(c for c in cells if c["valid"] and c["regime"] == REC)
    return (all(c["valid"] for c in cells) and {c["regime"] for c in cells} == {t22.TS_NF, AUTH, REC}
            and {c["studyEpoch"] for c in cells} == {TS_EPOCH} and {c["harness"] for c in cells} == {"B"}
            and rec["target"] == "recommender" and rec["faultKind"] == "pause")


def test_teastore_offpath_epoch_is_driven_through_the_loader(tmp_path):
    assert chk_ts_admitted(tmp_path / "ok")
    camp = ts_campaign(tmp_path / "v32")
    with pytest.raises(v24.UnknownSchema):                    # v3.2 reads TeaStore as v2.4 does: an unknown epoch stops
        with v24.use_system("teastore"), v32.v32_context("teastore"):
            v31.find_and_load3([camp])


def chk_ts_shape(tmp_path, _world=None):
    """A regime outside its epoch's declared set stops the run: the throttle regime under the off-path epoch, and the
    recommender regime under a legacy epoch (v2.4 would drop the first silently and read the second)."""
    refused = 0
    camp = ts_campaign(tmp_path / "a", keep_throttle=True)
    try:
        cells33([camp], "teastore")
    except v24.UnknownSchema as exc:
        refused += "persistence-cpu-throttle-effect" in str(exc)
    camp = ts_campaign(tmp_path / "b")                      # the recommender cell restamped with a legacy B epoch
    t22._edit_json(t22._cell_dir(camp, REC) / "receipt.json",
                   lambda rc: rc.__setitem__("studyEpoch", "teastore-traffic-sweep-b-v1"))
    try:
        cells33([camp], "teastore")
    except v24.UnknownSchema as exc:
        refused += REC in str(exc)
    return refused == 2


def test_teastore_regimes_outside_the_epoch_stop_the_run(tmp_path):
    assert chk_ts_shape(tmp_path)


def chk_ts_target(tmp_path, _world=None):
    camp = ts_campaign(tmp_path / "c", rec_service="auth")           # the recommender regime, but the harness froze `auth`
    try:
        cells33([camp], "teastore")
    except v24.UnknownSchema as exc:
        return "declares target 'recommender'" in str(exc)
    return False


def test_a_pause_cell_naming_another_target_stops_the_run(tmp_path):
    assert chk_ts_target(tmp_path)


def chk_ts_two_pause(tmp_path, _world=None):
    """P1/P2 run with the declared pair of pause regimes; a third stopping regime or a changed target is refused."""
    camp = ts_campaign(tmp_path / "c")
    R = run([camp, t22._quiet_campaign(camp, t22.TS_NF, tmp_path / "q", system="teastore")], "teastore")
    p1 = R["predictions"]["P1"]["perEpisode"]
    if not (p1 and all(AUTH in x["cell"] for x in p1)):
        return False
    with v24.use_system("teastore"), v33._v33_wrapped(True), v32.v32_context("teastore"):
        bad = dict(v24.FAULT_TARGETS)
        bad["other-pause-effect"] = ("persistence", "pause")
        v24.FAULT_TARGETS, v24.FAULT_REGIMES = bad, v24.FAULT_REGIMES + ("other-pause-effect",)
        try:
            v24.pause_regime()
        except v24.UnknownSchema as exc:
            return "declared pair" in str(exc)
    return False


def test_teastore_accepts_the_two_declared_pause_regimes_and_refuses_anything_else(tmp_path):
    assert chk_ts_two_pause(tmp_path)


def test_a_changed_pause_target_is_refused(tmp_path):
    with v24.use_system("teastore"), v33._v33_wrapped(True), v32.v32_context("teastore"):
        v24.FAULT_TARGETS = dict(v24.FAULT_TARGETS, **{REC: ("registry", "pause")})
        with pytest.raises(v24.UnknownSchema, match="declared pair"):
            v24.pause_regime()


def test_teastore_end_to_end(ts_world, tmp_path):
    R = run([ts_world["camp"], ts_world["quiet"]], "teastore")
    eps = R["results"]["primary"]["eps"]
    assert {e["regime"] for e in eps} == {AUTH, REC}
    rec = next(e for e in eps if e["regime"] == REC)
    assert rec["target"] == "recommender" and rec["calibrated"] and rec["affectedPath"] == ["recommender"]
    assert R["v32"]["offPathClasses"] == {REC: "recommender"} and R["v32"]["edgesDeclaredNotObserved"] in (None, [])
    assert {x["cell"].split("/")[-2] for x in R["predictions"]["P1"]["perEpisode"]} == {"auth-freeze-effect"}
    J = v33.build_json33(R)
    md = v33.render33(R, J)
    assert J["version"] == "3.3" and J["v33"]["teastorePauseRegimes"] == {REC: "recommender", AUTH: "auth"}
    assert J["v33"]["epochsAddedByV33"] == [TS_EPOCH] and "## v3.3 additions" in md
    # lanes: the registry log id fires in the recommender episode (coordinator lane); TeaStore has no lag lane
    lane = J["v33"]["lanes"]["regimes"][REC]["episodes"][0]["lanes"]
    assert lane["coordinator"]["earliest"]["sensor"].startswith("log:registry:") and lane["lag"]["note"]
    assert lane["own"]["collectedSensors"] > 0
    assert "no lag lane is declared for this system" in md


def test_legacy_readouts_are_v32s(tmp_path):
    """No off-path cell in the campaigns: the TeaStore regimes are not extended, and a v3.3 read of the legacy TeaStore sweep
    equals v3.2's (same episodes, same predictions)."""
    a = v32.run32(t22.TS_CAMP, system="teastore", reference=False)
    b = v33.run33(t22.TS_CAMP, system="teastore", reference=False)
    assert b["_v33ctx"]["teastoreOffPath"] == []
    ka = [(e["regime"], e["rate"], e["block"], [(f["ch"], f["svc"], f["tok"], f["rule"]) for f in e["fires"]])
          for e in a["results"]["primary"]["eps"]]
    kb = [(e["regime"], e["rate"], e["block"], [(f["ch"], f["svc"], f["tok"], f["rule"]) for f in e["fires"]])
          for e in b["results"]["primary"]["eps"]]
    assert ka == kb and a["predictions"]["P1"]["perEpisode"] == b["predictions"]["P1"]["perEpisode"]
    with v24.use_system("teastore"), v33._v33_wrapped(False), v32.v32_context("teastore"):
        assert REC not in v24.FAULT_REGIMES


def test_rebinding_is_restored_on_exit():
    before = (v24.FAULT_TARGETS, v24.FAULT_REGIMES, v24.pause_regime, v24.teastore_load_or_invalid, v31.STUDY_EPOCHS_B,
              v31.find_and_load3, v32.EPOCH_PROFILES, v32.ROUTE_MODEL, v32.SYNC_EDGES, v32.ASYNC_EDGES, v32.v32_context,
              v24.otel_ledger, v24.make_ctx)
    with v24.use_system("teastore"), v33._v33_wrapped(True), v32.v32_context("teastore"):
        assert REC in v24.FAULT_REGIMES and v32.EPOCH_PROFILES.keys() == {TS_EPOCH}
        assert v24.pause_regime is not before[2] and v32.v32_context is v33.v33_context
    with pytest.raises(RuntimeError):
        with v24.use_system("otel"), v33._v33_wrapped(False), v32.v32_context("otel"):
            assert EPOCH_F in v32.EPOCH_PROFILES and TS_EPOCH not in v32.EPOCH_PROFILES
            raise RuntimeError("x")
    after = (v24.FAULT_TARGETS, v24.FAULT_REGIMES, v24.pause_regime, v24.teastore_load_or_invalid, v31.STUDY_EPOCHS_B,
             v31.find_and_load3, v32.EPOCH_PROFILES, v32.ROUTE_MODEL, v32.SYNC_EDGES, v32.ASYNC_EDGES, v32.v32_context,
             v24.otel_ledger, v24.make_ctx)
    assert all(a is b for a, b in zip(before, after)) and v32.EPOCH_PROFILES == v33.V32_PROFILES


# ----------------------------------------------------------------------------- 3: the lanes report

def fire(ch, svc, tok, ttd, own=False, counts=True, rule="appear"):
    return {"ch": ch, "svc": svc, "tok": tok, "ttd": ttd, "ttdLo": ttd, "own": own, "counts": counts, "rule": rule,
            "family": "L"}


def episode(fires, target, keys):
    return {"target": target, "fires": fires, "_c": {"prep": {k: None for k in keys}}}


KEYS = [("log", "kafka", "aaa"), ("metric", "kafka", "kafka.consumer_group.lag"),
        ("metric", "kafka", "kafka.consumer_group.members"), ("log", "frauddetectionservice", "bbb"),
        ("metric", "kafka", "kafka.broker.requests")]
RULES = v33.LANE_RULES["otel"]


def chk_lanes_by_rule(_tmp=None, _world=None):
    """Lane membership is by service, channel and metric-name prefix, never by id: any kafka log id is coordinator-side, only
    consumer_group.lag* metrics are lag, the target's sensors are own, the ledger is none of them."""
    fs = [fire("log", "kafka", "ffffffffffff", 44.0), fire("log", "kafka", "0123456789ab", 43.0),
          fire("metric", "kafka", "kafka.consumer_group.lag_sum", 12.0, rule="spike"),
          fire("metric", "kafka", "kafka.consumer_group.members", 5.0, rule="spike"),
          fire("log", "frauddetectionservice", "cccccccccccc", 1.0, own=True),
          fire("ledger", "frontendproxy", "route", 0.5, rule="failed")]
    lanes = v33.lanes_episode(episode(fs, "frauddetectionservice", KEYS), RULES)
    return (lanes["coordinator"]["earliest"]["ttd"] == 43.0 and lanes["coordinator"]["countedFires"] == 2
            and lanes["lag"]["earliest"]["sensor"] == "metric:kafka:kafka.consumer_group.lag_sum"
            and lanes["lag"]["countedFires"] == 1                    # `members` is a kafka metric, not a lag metric
            and lanes["own"]["earliest"]["ttd"] == 1.0 and lanes["own"]["countedFires"] == 1
            and lanes["coordinator"]["collectedSensors"] == 1 and lanes["lag"]["collectedSensors"] == 1)


def test_lanes_are_assigned_by_rule():
    assert chk_lanes_by_rule()


def chk_lanes_counted_only(_tmp=None, _world=None):
    """A fire the spike path filter dropped (counts False) is no lane fire."""
    fs = [fire("metric", "kafka", "kafka.consumer_group.lag", 3.0, counts=False, rule="spike"),
          fire("metric", "kafka", "kafka.consumer_group.lag", 9.0, counts=True, rule="spike")]
    lanes = v33.lanes_episode(episode(fs, "frontend", KEYS), RULES)
    return lanes["lag"]["earliest"]["ttd"] == 9.0 and lanes["lag"]["countedFires"] == 1


def test_only_counted_fires_enter_a_lane():
    assert chk_lanes_counted_only()


def chk_lanes_own_separate(_tmp=None, _world=None):
    """Own fires are reported in `own` only: with the target a lane's own service, its fire is not also coordinator-side."""
    fs = [fire("log", "kafka", "aaa", 2.0, own=True)]
    lanes = v33.lanes_episode(episode(fs, "kafka", KEYS), RULES)
    return lanes["own"]["countedFires"] == 1 and lanes["coordinator"]["countedFires"] == 0


def test_an_own_fire_is_in_its_own_lane_only():
    assert chk_lanes_own_separate()


def chk_lanes_bc_separate(_tmp=None, _world=None):
    """A BC-flagged fire (the TeaStore registry heartbeat-removal line is BC-caller-log) is not a counted fire: the counted field
    reads miss by rule, `earliestByConstruction` carries it with its flags and the label; counting is otherwise unchanged."""
    keys = [("log", "registry", "1b6e1f5f63fc"), ("log", "registry", "other")]
    ts = v33.LANE_RULES["teastore"]
    fs = [dict(fire("log", "registry", "1b6e1f5f63fc", 10.2), bc=["BC-caller-log"]),
          dict(fire("log", "registry", "1b6e1f5f63fc", 9.4), bc=["BC-caller-log", "BC-caller-span"]),
          dict(fire("log", "registry", "other", 30.0), bc=[]),
          dict(fire("log", "registry", "dropped", 1.0, counts=False), bc=["BC-caller-log"])]       # the path filter's, not BC's
    lanes = v33.lanes_episode(episode(fs, "auth", keys), ts)
    co = lanes["coordinator"]
    bc = co["earliestByConstruction"]
    return (co["earliest"]["ttd"] == 30.0 and co["countedFires"] == 1
            and bc["ttd"] == 9.4 and bc["bcFlags"] == ["BC-caller-log", "BC-caller-span"]
            and bc["label"] == "by construction, not counted" and co["byConstructionFires"] == 2
            and lanes["own"]["earliestByConstruction"] is None)


def test_a_bc_flagged_fire_is_reported_beside_the_counted_one_not_in_it():
    assert chk_lanes_bc_separate()
    ts = v33.LANE_RULES["teastore"]
    only_bc = [dict(fire("log", "registry", "1b6e1f5f63fc", 9.1 + i), bc=["BC-caller-log"]) for i in range(3)]
    rows = [{"lanes": v33.lanes_episode(episode([f], "auth", [("log", "registry", "1b6e1f5f63fc")]), ts)} for f in only_bc]
    s = v33._summ(rows, "coordinator")
    assert s["withFire"] == 0 and s["ttdMedian"] is None                     # counted-only: a miss by rule
    assert s["withByConstructionFire"] == 3 and s["byConstructionTtdMedian"] == 10.1 and s["byConstructionTtdMin"] == 9.1
    assert s["byConstructionLabel"] == "by construction, not counted"


def test_lane_absence_is_a_dash_not_a_zero():
    """No sensor collected -> collectedSensors 0 and the summary's denominator leaves the episode out; no lag lane declared
    (TeaStore) -> a note and None, never 0."""
    e = episode([], "frauddetectionservice", [("log", "frauddetectionservice", "bbb")])
    lanes = v33.lanes_episode(e, RULES)
    assert lanes["lag"]["collectedSensors"] == 0 and lanes["lag"]["earliest"] is None
    s = v33._summ([{"lanes": lanes}], "lag")
    assert s["withCollectedSensors"] == 0 and s["withFire"] == 0 and s["ttdMedian"] is None
    ts = v33.lanes_episode(e, v33.LANE_RULES["teastore"])
    assert ts["lag"]["collectedSensors"] is None and ts["lag"]["note"]
    assert v33._summ([{"lanes": ts}], "lag")["withFire"] is None


def test_lanes_end_to_end_on_the_f_fixture(f_result):
    """Through the whole reader: the injected Kafka lag spike and Kafka log line fire in the fraud episode (lanes b and c),
    the frontend control has Kafka metrics collected and no fire, and the fraud target has no own sensors in this fixture."""
    J = v33.build_json33(f_result)
    L = J["v33"]["lanes"]["regimes"]
    fr = L[FRAUD]["episodes"][0]["lanes"]
    assert fr["coordinator"]["earliest"]["sensor"].startswith("log:kafka:")
    assert fr["lag"]["earliest"]["sensor"] == "metric:kafka:kafka.consumer_group.lag"
    assert fr["lag"]["earliest"]["rule"] == "spike" and fr["lag"]["countedFires"] >= 1
    assert fr["own"]["collectedSensors"] == 0
    fc = L[FRONT]["episodes"][0]["lanes"]
    assert fc["lag"]["collectedSensors"] == 1 and fc["lag"]["countedFires"] == 0 
    own = fc["own"]                                                  # the fixture's own frontend fires are all BC-flagged:
    assert own["earliest"] is None and own["earliestByConstruction"]["bcFlags"]      # a miss by rule, reported beside it
    assert own["earliestByConstruction"]["label"] == "by construction, not counted" and own["byConstructionFires"] >= 1
    assert L[FRAUD]["byRate"]["1"]["lag"]["withFire"] == 1 and L[ACCT]["byRate"]["1"]["lag"]["withFire"] == 0
    assert "kafka" in f_result["v32"]["offPathClasses"][FRAUD] or f_result["v32"]["offPathClasses"][FRAUD]


def test_json_and_markdown_carry_the_v33_block(f_world, tmp_path):
    out = tmp_path / "ro"
    assert v33.main([str(f_world["camp"]), str(f_world["quiet"]), "--system", "otel", "--out", str(out)]) == 0
    J = json.loads((out / v33.OUT_JSON).read_text())
    md = (out / v33.OUT_MD).read_text()
    assert J["version"] == "3.3" and J["scriptSha256"] == v33._sha(v33.__file__)
    assert J["v32ScriptSha256"] == v32._sha(v32.__file__) and J["v31ScriptSha256"] == v31._sha(v31.__file__)
    assert J["v33"]["parametersV33Sha256"] == v33._sha(v33.PARAMETERS_V33)
    assert J["v32"]["parametersV32Sha256"] == v32._sha(v32.PARAMETERS_V32) and J["v32"]["epochsRead"] == {EPOCH_F: 13}
    assert all(e["studyEpoch"] == EPOCH_F for e in J["episodes"])
    assert "## v3.2 additions (campaign E)" in md and "## v3.3 additions" in md and "### Lanes, `fraud-pause-effect`" in md
    with pytest.raises(SystemExit):
        v33.main([str(f_world["camp"]), "--system", "otel", "--out", str(out)])


# ----------------------------------------------------------------------------- the frozen files are untouched

FROZEN = {
    "research/detection-time/sweep_analysis_v3_2.py": "97eb0a1d4f3f7e0daecee447113fdd14bd14b84812f420ddb3903bfe16759465",
    "research/protocol/parameters_v3_2.json": "ab4a5af7243e776f536b09a39e649b1be968d23f1767ef2f5a166ac08e340a67",
    "research/placement/celf_v3_2.py": "cc7157d858ce3a92fd236e0ce982a7421b4f2a69ad81b06a5ea59b7fb8b88e12",
    "research/placement/score_test_v3_2.py": "f9942b9138f1d1216ed3d3466949c727f6388980e24fff4ce40af994fbf64a07",
    "research/detection-time/sweep_analysis_v3.py": "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd",
    "research/detection-time/sweep_analysis_v2.py": "075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9",
    "research/protocol/parameters_v3.json": "212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000",
    "research/otel-offpath/adapter.py": "22f627dcd1bffdf3f92a151e0d9935f9e2b284a07c905737594d1e95f40bc0b9",
}


def test_the_frozen_v32_chain_and_the_adapter_are_byte_identical():
    for rel, sha in FROZEN.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel


def test_status_and_label_are_the_freeze_ones():
    assert v33.LABEL == "frozen v3.3 for campaigns F and teastore-offpath-v1 (FREEZE_V33_20261014.md)"
    assert "STATUS: FROZEN by digest (research/protocol/FREEZE_V33_20261014.md)" in v33.__doc__
    assert all(p["status"] == "active" for p in v33.REGISTRY33.values())


def test_registry_entries_have_origins_and_every_used_one_exists():
    for n, p in v33.REGISTRY33.items():
        assert p["origin_ref"] and p["origin_type"] in ("decision", "literature", "measured", "upstream",
                                                        "engineering default", "unknown")
        assert p["status"] in ("active", "provisional", "superseded"), n
    assert v33.PARAMS_USED33 <= set(v33.REGISTRY33) and set(v33.REGISTRY33) == {
        "V33_EPOCH_PROFILES", "V33_ROUTE_MODEL_TEASTORE", "V33_LANE_RULES", "V33_LANES_REPORT_RULE"}


def test_v33_adds_epochs_and_never_redefines_v32s():
    assert not set(v33.ADDED_PROFILES) & set(v33.V32_PROFILES) and v33.V32_PROFILES == v32.EPOCH_PROFILES
    for e, p in v33.ADDED_PROFILES.items():
        assert p["system"] in v24.SYSTEMS and p["shape"] == "campaign-B"
    f = v33.ADDED_PROFILES[EPOCH_F]
    e = v32.EPOCH_PROFILES[EPOCH_E]
    assert {k: f[k] for k in ("faultRegimes", "noFaultRegime", "ledgerKind", "role")} == \
           {k: e[k] for k in ("faultRegimes", "noFaultRegime", "ledgerKind", "role")}
    ts = v33.ADDED_PROFILES[TS_EPOCH]
    assert ts["faultRegimes"] == {REC: ["recommender", "pause"], AUTH: ["auth", "pause"]}
    assert dict((r, t[0]) for r, t in ts["faultRegimes"].items()) == v33.TS_MODEL["pauseRegimes"]


def test_lane_rules_name_services_by_the_catalog():
    A = v24.otel_adapter()
    assert RULES["coordinator"]["service"] in A.APP_SERVICES and RULES["lag"]["service"] in A.APP_SERVICES
    assert not __import__("re").search(r"[0-9a-f]{12}", json.dumps(v33.LANE_RULES))       # no hash is hard-coded
    assert v33.LANE_RULES["teastore"]["lag"] is None and v33.LANE_RULES["teastore"]["coordinator"]["service"] == "registry"


# ----------------------------------------------------------------------------- planted defects: each switch has a check

CHECKS = {"ADMIT_NEW_EPOCHS": lambda tmp, w: chk_f_admitted(tmp) and chk_ts_admitted(tmp / "ts"),
          "TEASTORE_SHAPE_CHECK": chk_ts_shape, "TEASTORE_TARGET_CHECK": chk_ts_target,
          "TEASTORE_TWO_PAUSE": chk_ts_two_pause, "LANES_COUNTED_ONLY": chk_lanes_counted_only,
          "LANES_OWN_SEPARATE": chk_lanes_own_separate, "LANES_BC_SEPARATE": chk_lanes_bc_separate}


def _passes(chk, tmp_path):
    try:
        return bool(chk(tmp_path, None))
    except (v24.UnknownSchema, SystemExit, AssertionError, StopIteration, KeyError):
        return False


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, tmp_path, monkeypatch):
    """Each v3.3 switch has a check that passes, and fails (or stops) once the switch is planted off."""
    assert _passes(CHECKS[flag], tmp_path / "on"), flag
    monkeypatch.setattr(v33, flag, False)
    assert not _passes(CHECKS[flag], tmp_path / "off"), flag


def test_every_switch_has_a_check():
    switches = {k for k, v in vars(v33).items() if k.isupper() and isinstance(v, bool)}
    assert switches == set(CHECKS) == set(v33.SWITCHES), switches ^ set(CHECKS)


def test_a_lane_by_hash_would_miss_a_new_log_id():
    """The planted alternative the rule replaces: a hard-coded id set. A kafka log id it does not list is not coordinator-side
    there, and is under the rule (the id changes with the log text)."""
    listed = {"7e9cdd69a48a"}
    f = fire("log", "kafka", "123456789abc", 40.0)
    assert f["tok"] not in listed and v33.lane_of(f, "frauddetectionservice", RULES) == "coordinator"
