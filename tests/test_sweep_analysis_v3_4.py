"""Analysis v3.4 (research/detection-time/sweep_analysis_v3_4.py, research/protocol/parameters_v3_4.json): admission of the Hotel
off-path epoch `hotel-offpath-v1` (consul pause as the declared off-path pause, search pause as the on-path control), consul as an
extra collected service, and Hotel's lane rules (own = the target's sensors, coordinator and lag `—`).

Layer: reader + synthetic end-to-end. Synthetic cells only: tests/test_sweep_analysis_v2.py's Hotel sweep cell (`make_cell`, the one v2.4's reader is tested on), post-edited
into the SHAPE the registry pins (parameters_v3_4.json, pinned to the Hotel harness commit 9ad0b98: candidate_offpath.py's regimes,
targets, rates, runKey; compose_pause.py's off-path receipt; consul rows in cpu.json, system-samples.json and application.log). No
cell of hotel-offpath-v1 was read. Every v3.4 change has a planted defect (its switch off) under which one of its checks fails
(test_check_passes_and_fails_with_its_switch_off), the frozen v3.3 chain is untouched (digests), and a v3.4 read of a legacy campaign
equals v3.1's (test_legacy_hotel_readout_is_v31s; checked once offline against the committed Hotel primary readout, see the freeze).
"""
from __future__ import annotations

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

import sweep_analysis_v3_4 as v34  # noqa: E402
import test_sweep_analysis_v2 as t1  # noqa: E402
import test_sweep_analysis_v22_systems as t22  # noqa: E402

v33, v32, v31, v24 = v34.v33, v34.v32, v34.v31, v34.v24
EPOCH = "hotel-offpath-v1"
QUIET_EPOCH = "hotel-quiet-calibration-v1"
SWEEP_EPOCH = "hotel-traffic-sweep-v1"
NF, SP, CT = t1.NF, t1.SP, t1.CT
CP = "consul-pause-effect"
HOLD = 60.0
NO_SPLIT = {"train": None, "test": None}


@pytest.fixture(autouse=True)
def _no_registry_split(monkeypatch):
    monkeypatch.setattr(v32, "E_SPLIT", NO_SPLIT)


# ----------------------------------------------------------------------------- synthetic campaigns

def _edit(path, fn):
    doc = json.loads(Path(path).read_text())
    out = fn(doc)
    Path(path).write_text(json.dumps(doc if out is None else out))


def _add_consul(d, paused_window=None, log="native"):
    """Consul's rows in a cell, as the off-path harness collects them (compose log prefix `consul-1`, docker stats `service`,
    cgroup sampler `services`): cpu 1.0 (a pause reads 0.0 inside `paused_window` = (lo, hi) seconds after the barrier), memory
    flat. log: "native" = consul 1.13's own lines (`<ISO> [INFO]  agent: ...`, no Hotel layout parses them), "json" = zerolog
    JSON lines (a layout the reader knows), None = no consul log lines."""
    def cpu(doc):
        for smp in doc["samples"]:
            t = smp["capturedAtEpoch"] - t1.T0
            paused = paused_window is not None and paused_window[0] <= t <= paused_window[1]
            smp["containers"].append({"service": "consul", "containerId": "c", "cpuPercent": 0.0 if paused else 1.0 + (0.01 if int(t) % 2 else 0.0)})
    _edit(d / "cpu.json", cpu)
    p = d / "system-samples.json"
    if p.exists():
        def sysm(doc):
            for i, smp in enumerate(doc["samples"]):
                smp["services"]["consul"] = {"cpuUsageUsec": int(1e6 * 0.01 * i * 5), "memoryCurrent": 20_000_000 + (7 if i % 2 else 0),
                                             "psiCpuSomeTotalUsec": 0, "psiIoSomeTotalUsec": 0, "psiMemorySomeTotalUsec": 0,
                                             "rbytes": 0, "wbytes": 0}
        _edit(p, sysm)
    if log:
        with (d / "application.log").open("a") as fh:
            for k in range(3):
                t = t1.T0 + 2.0 + k
                if log == "native":
                    fh.write("consul-1  | %s %s [INFO]  agent.server.raft: heartbeat line %d\n" % (
                        t1._dock(t + t1.RECEIPT), t1._iso(t)[:-4] + "Z", k))
                else:
                    fh.write("consul-1  | %s {\"level\":\"info\",\"time\":\"%s\",\"message\":\"consul line %d\"}\n" % (
                        t1._dock(t + t1.RECEIPT), t1._app(t), k))


def _restamp(d, epoch, regime=None, fault=None):
    def ct(doc):
        doc["studyEpoch"] = epoch
        doc["runKey"]["studyEpoch"] = epoch
        if regime is not None:
            doc["runKey"]["regime"] = regime
            doc["runId"] = doc["runId"].replace(doc["runId"].split("-r")[0], regime)
        if fault is not None:
            doc["fault"] = fault
            doc["timing"]["faultApplied"] = True
    _edit(d / "cell-contract.json", ct)


def consul_cell(root, rate, block, offset, target="consul", scenario="consul-pause", regime=CP, outage=False, events=True,
                paused=True):
    """An off-path pause cell: the no-fault cell of the same (rate, block) cloned into effect/consul-pause, with compose_pause's
    receipt (faultKind pause, manifested = paused, outageObserved recorded), the pause and unpause docker events on consul's
    container, and consul's cpu at 0 inside the pause. Requests keep succeeding (the route stays up)."""
    nf = t1.make_cell(root, NF, rate, block, offset)
    rt = ("%g" % rate).replace(".", "p")
    d = root / "runs" / "effect" / "consul-pause" / ("r" + rt) / ("b%02d" % block) / ("p%02d-full" % block) / "attempt-01"
    shutil.copytree(nf, d)
    a_true = t1.B0 + 60.0 + offset + 0.1
    _restamp(d, SWEEP_EPOCH, regime=regime, fault=scenario)
    pre = (t1.B0 + 60.0 + offset + 0.01, t1.B0 + 60.0 + offset + 0.04)
    during = (a_true + 0.06, a_true + 0.07)
    t1._w(d / "fault-receipt.json", {
        "schemaVersion": 1, "faultKind": "pause", "scenario": scenario, "targetService": target,
        "scheduledAtSeconds": 60.0, "requestedOutageSeconds": HOLD, "manifested": paused, "outageObserved": outage,
        "recovered": True, "successful": True, "preState": {"exists": True, "running": True, "paused": False},
        "duringState": {"exists": True, "running": True, "paused": paused, "status": "paused"},
        "startedMonotonic": a_true, "appliedMonotonic": a_true + 0.05, "revertingMonotonic": a_true + HOLD,
        "unpausedAtMonotonic": a_true + HOLD + 0.05, "readyAtMonotonic": a_true + HOLD + 0.5,
        "endedMonotonic": a_true + HOLD + 0.6, "error": None,
        "probes": [{"phase": "pre", "startMonotonic": pre[0], "endMonotonic": pre[1], "available": True},
                   {"phase": "during", "startMonotonic": during[0], "endMonotonic": during[1], "available": not outage}]})
    if events:
        wall = lambda m: int((t1.T0 + (m - t1.B0)) * 1e9)    # noqa: E731  (the ledger fit maps wall to monotonic by T0 - B0)
        with (d / "docker-events.jsonl").open("w") as fh:
            for act, m in (("pause", a_true + 0.03), ("unpause", a_true + HOLD + 0.02)):
                fh.write(json.dumps({"Action": act, "Actor": {"Attributes": {"com.docker.compose.service": "consul"}},
                                     "timeNano": wall(m)}) + "\n")
    return d, a_true


def offpath_campaign(dest, blocks=(1, 2, 3), consul=True, search=True, consul_cell_kw=None, consul_log="native", rates=(1.0,)):
    """hotel-offpath-v1's shape: per block and rate a no-fault cell, a consul-pause cell and a search-pause cell (the on-path
    control, the sweep's own fixture), all restamped to the off-path epoch; consul's rows in every cell when `consul`."""
    root = Path(dest)
    for rate in rates:
        rt = ("%g" % rate).replace(".", "p")
        for b in blocks:
            off = t1.OFFSETS[b - 1] if rate == 1.0 else t1.off(rate, b)
            cd, a_true = consul_cell(root, rate, b, off, **(consul_cell_kw or {}))
            nf = root / "runs" / "calibration" / ("r" + rt) / ("b%02d" % b) / ("p%02d-full" % b) / "attempt-01"
            sp = t1.make_cell(root, SP, rate, b, off) if search else None
            _restamp(nf, EPOCH)
            _restamp(cd, EPOCH)
            if sp is not None:
                _restamp(sp, EPOCH)
            if consul:
                lo, hi = a_true - t1.B0, a_true - t1.B0 + HOLD
                _add_consul(nf, log=consul_log)
                _add_consul(cd, paused_window=(lo, hi), log=consul_log)
                if sp is not None:
                    _add_consul(sp, log=consul_log)
    return root


def quiet_campaign(dest, copies=3):
    """Legacy no-fault cells (the quiet run's shape), epoch hotel-quiet-calibration-v1 (refused beside the off-path epoch)."""
    root = Path(dest)
    for i in range(copies):
        d = t1.make_cell(root / ("c%d" % i), NF, 1.0, 1, t1.OFFSETS[0])
        _restamp(d, QUIET_EPOCH)
        shutil.copytree(root / ("c%d" % i) / "runs", root / "runs" / ("q%d" % i))
        shutil.rmtree(root / ("c%d" % i))
    return root


def legacy_campaign(root, blocks=(1,), epoch=None):
    """Legacy Hotel sweep cells (no-fault and search-pause at rate 1, v2.4's fixture), stamped with `epoch` when given."""
    root = Path(root)
    for b in blocks:
        for regime in (NF, SP):
            d = t1.make_cell(root, regime, 1.0, b, t1.OFFSETS[b - 1])
            if epoch is not None:
                _restamp(d, epoch)
    return root


def cells34(camps, active=True):
    camps = list(camps)
    epochs, regimes = v34.hotel_scan(camps)
    with v34._v34_wrapped(v34.hotel_is_active(epochs, regimes) if active else False), v24.use_system("hotel"), \
            v33._v33_wrapped(False), v32.v32_context("hotel"):
        return v31.find_and_load3(camps)[1]


def run(camps, **kw):
    R = v34.run34(camps, system="hotel", reference=False, **kw)
    with v24.use_system("hotel"):
        v31.finish(R)
    return R


def _refused(camps, match):
    with pytest.raises((v24.UnknownSchema, SystemExit), match=match):
        cells34(camps)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("v34")
    camp = offpath_campaign(base / "o")
    return {"base": base, "camp": camp}


@pytest.fixture(scope="module")
def result(world):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(v32, "E_SPLIT", NO_SPLIT)
        return run([world["camp"]])


# ----------------------------------------------------------------------------- 8.5: the off-path epoch is admitted

def chk_admitted(tmp_path, _w=None):
    camp = offpath_campaign(tmp_path / "c")
    cells = cells34([camp])
    cp = next(c for c in cells if c["valid"] and c["regime"] == CP)
    return (all(c["valid"] for c in cells) and {c["regime"] for c in cells} == {NF, CP, SP}
            and {c["studyEpoch"] for c in cells} == {EPOCH} and cp["target"] == "consul" and cp["faultKind"] == "pause"
            and cp["cmd"]["commandSeconds"] is not None)


def test_offpath_epoch_is_driven_through_the_loader(tmp_path):
    """A synthetic cell of the new epoch goes through v3.1's find_and_load3 inside the v3.4 context: valid, target consul, kind pause.
    The same cells under v3.3's own context are what v2.4 does to an unknown regime: listed `not scored`, silently (no error)."""
    assert chk_admitted(tmp_path / "v34")
    camp = offpath_campaign(tmp_path / "v33")
    with v24.use_system("hotel"), v33._v33_wrapped(False), v32.v32_context("hotel"):
        cells = v31.find_and_load3([camp])[1]
    dropped = [c for c in cells if not c["valid"]]
    assert len(dropped) == 3 and all("unknown regime" in c["reason"] for c in dropped)


def chk_shape(tmp_path, _w=None):
    """A regime outside the epoch's declared set stops the run: cpu-throttle under the off-path epoch, consul under a legacy
    epoch, and a typo (which v2.4 would drop) even under an otherwise legacy campaign."""
    refused = 0
    camp = offpath_campaign(tmp_path / "a")
    cell = next(camp.glob("runs/effect/search-pause/r1/b01/*/attempt-01"))
    _edit(cell / "cell-contract.json", lambda ct: ct["runKey"].__setitem__("regime", CT))
    try:
        cells34([camp])
    except v24.UnknownSchema as exc:
        refused += CT in str(exc) and EPOCH in str(exc)
    camp = offpath_campaign(tmp_path / "b")
    cd = next(camp.glob("runs/effect/consul-pause/r1/b01/*/attempt-01"))
    _restamp(cd, SWEEP_EPOCH)
    try:
        cells34([camp])
    except v24.UnknownSchema as exc:
        refused += "not a regime of Hotel epoch 'hotel-traffic-sweep-v1'" in str(exc)
    legacy = tmp_path / "c"
    legacy_campaign(legacy, blocks=(1,))
    for p in legacy.glob("runs/**/cell-contract.json"):
        _restamp(p.parent, SWEEP_EPOCH)
    cell = next(legacy.glob("runs/effect/search-pause/r1/b01/*/attempt-01"))
    _edit(cell / "cell-contract.json", lambda ct: ct["runKey"].__setitem__("regime", "consol-pause-effect"))
    try:
        cells34([legacy])
    except v24.UnknownSchema as exc:
        refused += "consol-pause-effect" in str(exc)
    return refused == 3


def test_regimes_outside_the_epoch_stop_the_run(tmp_path):
    assert chk_shape(tmp_path)


def chk_target(tmp_path, _w=None):
    camp = offpath_campaign(tmp_path / "c")
    cd = next(camp.glob("runs/effect/consul-pause/r1/b01/*/attempt-01"))
    _edit(cd / "fault-receipt.json", lambda fr: fr.__setitem__("targetService", "search"))     # the consul regime, but `search` froze
    try:
        cells34([camp])
    except v24.UnknownSchema as exc:
        return "declares 'consul'" in str(exc)
    return False


def test_a_pause_cell_naming_another_target_stops_the_run(tmp_path):
    assert chk_target(tmp_path)
    camp = offpath_campaign(tmp_path / "kind")                     # right target, wrong kind
    cd = next(camp.glob("runs/effect/consul-pause/r1/b01/*/attempt-01"))
    _edit(cd / "fault-receipt.json", lambda fr: fr.__setitem__("faultKind", "degradation"))
    _refused([camp], "kind 'degradation'")


def chk_design(tmp_path, _w=None):
    """Rate, block and posture outside the declared design stop the run."""
    refused = 0
    for key, val, text in (("requestsPerSecond", 5.0, "rate 5.0"), ("block", 6, "block 6"), ("posture", "none", "posture 'none'")):
        camp = offpath_campaign(tmp_path / key)
        cd = next(camp.glob("runs/effect/consul-pause/r1/b01/*/attempt-01"))
        _edit(cd / "cell-contract.json", lambda ct: ct["runKey"].__setitem__(key, val))
        try:
            cells34([camp])
        except v24.UnknownSchema as exc:
            refused += text in str(exc)
    camp = offpath_campaign(tmp_path / "timing")                  # the rate v2.4 actually reads is timing.requestsPerSecond
    cd = next(camp.glob("runs/effect/consul-pause/r1/b01/*/attempt-01"))
    _edit(cd / "cell-contract.json", lambda ct: ct["timing"].__setitem__("requestsPerSecond", 5.0))
    try:
        cells34([camp])
    except v24.UnknownSchema as exc:
        refused += "rate 5.0" in str(exc)
    return refused == 4


def test_a_cell_outside_the_declared_design_stops_the_run(tmp_path):
    assert chk_design(tmp_path)


def chk_epoch(tmp_path, _w=None):
    """An epoch the registry does not know, beside the off-path epoch, stops the run (a no-fault cell of another Hotel epoch
    is not silently pooled)."""
    camp = offpath_campaign(tmp_path / "c")
    q = quiet_campaign(tmp_path / "q", copies=1)
    for p in q.glob("runs/**/cell-contract.json"):
        _restamp(p.parent, "hotel-mystery-v9")
    try:
        cells34([camp, q])
    except v24.UnknownSchema as exc:
        return "hotel-mystery-v9" in str(exc) and "not a Hotel epoch this reader knows" in str(exc)
    return False


def test_an_unknown_epoch_beside_the_offpath_epoch_stops_the_run(tmp_path):
    assert chk_epoch(tmp_path)


def test_a_legacy_campaign_is_not_subject_to_the_new_checks(tmp_path):
    """No off-path cell and no unknown regime: the v3.4 Hotel rules are off, so an epoch name nobody registered is read as v2.4
    reads it (nothing refuses a legacy readout)."""
    legacy = tmp_path / "l"
    legacy_campaign(legacy, blocks=(1,))
    epochs, regimes = v34.hotel_scan([legacy])
    assert not v34.hotel_is_active(epochs, regimes)
    cells = cells34([legacy])
    assert all(c["valid"] for c in cells) and {c.get("studyEpoch") for c in cells} == {None}


def test_the_scan_reads_contracts_only_and_survives_a_missing_runs_dir(tmp_path):
    e, r = v34.hotel_scan([tmp_path / "nowhere"])
    assert not e and not r


# ----------------------------------------------------------------------------- 8.6: legacy cells of any kind beside the off-path epoch

def chk_extra_alone(tmp_path, _w=None):
    """Legacy cells beside the off-path epoch are refused, fault cells (another design) and no-fault cells alike: a quiet cell never
    collected consul, and v3.1 reads a fold without data as zero false alarms (review B1)."""
    refused = 0
    for kind, bld in (("fault", lambda d: legacy_campaign(d, blocks=(1,), epoch=SWEEP_EPOCH)),
                      ("nofault", lambda d: quiet_campaign(d, copies=2))):
        camp = offpath_campaign(tmp_path / ("c" + kind))
        other = bld(tmp_path / ("o" + kind))
        try:
            cells34([camp, other])
        except SystemExit as exc:
            refused += "legacy Hotel epoch" in str(exc) and "Read the off-path epoch alone" in str(exc)
    return refused == 2


def test_legacy_cells_beside_the_offpath_epoch_are_refused(tmp_path):
    assert chk_extra_alone(tmp_path / "x")


def test_pooling_a_quiet_cell_would_calibrate_consul_on_absence(tmp_path, monkeypatch):
    """The probe behind B1, kept as a test: with the refusal planted off, a quiet campaign (no consul rows) pooled beside the epoch
    still yields `calibrated` consul sensors evaluated on every fold; the refusal is what stops it."""
    camp = offpath_campaign(tmp_path / "c")
    q = quiet_campaign(tmp_path / "q", copies=3)
    monkeypatch.setattr(v34, "HOTEL_EXTRA_ALONE", False)
    R = run([camp, q])
    quiet_cells = [c for c in R["cells"] if c["valid"] and c.get("studyEpoch") == QUIET_EPOCH]
    assert quiet_cells and not any(k[1] == "consul" for c in quiet_cells for k in c["prep"])
    cons = [(k, v) for k, v in R["cal"]["primary"]["perRate"][1.0]["rules"].items() if k[0][1] == "consul"]
    assert cons and any(v.get("foldsEvaluated", 0) > sum(1 for c in R["cells"] if c["valid"] and c.get("studyEpoch") == EPOCH
                                                          and c["target"] is None and any(k[1] == "consul" for k in c["prep"]))
                        for _k, v in cons)
    monkeypatch.setattr(v34, "HOTEL_EXTRA_ALONE", True)
    with pytest.raises(SystemExit, match="legacy Hotel epoch"):
        run([camp, q])


def test_split_and_test_blocks_are_refused_for_hotel(world):
    with pytest.raises(SystemExit, match="not applied to Hotel"):
        v34.run34(world["camp"], system="hotel", reference=False, test_blocks={4, 5})
    with pytest.raises(SystemExit, match="not applied to Hotel"):
        v34.run34(world["camp"], system="hotel", reference=False, split="x.json")


def test_a_validation_campaign_is_scanned_too(tmp_path):
    """v2.4's silent drop must not return through --validation: an off-path campaign given as validation activates the rules, and the
    legacy primary beside it is refused (loud), not read with the consul cells listed `unknown regime`."""
    leg = legacy_campaign(tmp_path / "l", blocks=(1,), epoch=SWEEP_EPOCH)
    camp = offpath_campaign(tmp_path / "o", blocks=(1,))
    with pytest.raises(SystemExit, match="legacy Hotel epoch"):
        v34.run34(leg, system="hotel", reference=False, validation_dirs=[camp])
    e, r = v34.hotel_scan([leg, camp])
    assert v34.hotel_is_active(e, r)


def chk_unique(tmp_path, _w=None):
    """A relaunch of the epoch repeats the run IDs under another campaign directory: reading both would pool every cell twice."""
    a = offpath_campaign(tmp_path / "a", blocks=(1,))
    b = offpath_campaign(tmp_path / "b", blocks=(1,))
    try:
        cells34([a, b])
    except SystemExit as exc:
        return "read ONE fetch of the epoch" in str(exc)
    return False


def test_two_fetches_of_the_same_epoch_are_refused(tmp_path):
    assert chk_unique(tmp_path / "x")
    a = offpath_campaign(tmp_path / "a", blocks=(1,))
    b = offpath_campaign(tmp_path / "b", blocks=(2,))                      # different blocks: not a repeat, read as one
    assert len(cells34([a, b])) == 6


def test_two_rates_flow_through_calibration_and_lanes(tmp_path):
    """The epoch's two rates (10 and 1 req/s): per-rate calibration, episodes, lanes and manifestation rows for both."""
    camp = offpath_campaign(tmp_path / "c", blocks=(1, 2), rates=(10.0, 1.0))
    R = run([camp])
    eps = R["results"]["primary"]["eps"]
    assert {(e["regime"], e["rate"]) for e in eps} == {(CP, 10.0), (CP, 1.0), (SP, 10.0), (SP, 1.0)}
    J = v34.build_json34(R)
    assert sorted(J["v33"]["lanes"]["regimes"][CP]["byRate"]) == ["1", "10"]
    assert {r["rate"] for r in J["v34"]["manifestation"]["episodes"]} == {10.0, 1.0}
    md = v34.render34(R, J)
    assert "| 10 | own |" in md and "| 1 | own |" in md


# ----------------------------------------------------------------------------- P1 / P2: the declared pair of pause regimes

def chk_two_pause(tmp_path, _w=None):
    camp = offpath_campaign(tmp_path / "c")
    R = run([camp])
    p1 = R["predictions"]["P1"]["perEpisode"]
    if not (p1 and all(SP in x["cell"] or "search-pause" in x["cell"] for x in p1)):
        return False
    with v24.use_system("hotel"), v34._v34_wrapped(True), v33._v33_wrapped(False), v32.v32_context("hotel"):
        bad = dict(v24.FAULT_TARGETS)
        bad["other-pause-effect"] = ("reservation", "pause")
        v24.FAULT_TARGETS, v24.FAULT_REGIMES = bad, v24.FAULT_REGIMES + ("other-pause-effect",)
        try:
            v24.pause_regime()
        except v24.UnknownSchema as exc:
            return "declared pair" in str(exc)
    return False


def test_hotel_accepts_the_two_declared_pause_regimes_and_refuses_anything_else(tmp_path):
    assert chk_two_pause(tmp_path)


def test_a_changed_pause_target_is_refused():
    with v24.use_system("hotel"), v34._v34_wrapped(True), v33._v33_wrapped(False), v32.v32_context("hotel"):
        v24.FAULT_TARGETS = dict(v24.FAULT_TARGETS, **{CP: ("frontend", "pause")})
        with pytest.raises(v24.UnknownSchema, match="declared pair"):
            v24.pause_regime()


def test_p1_and_p2_are_declared_for_the_on_path_control_only(result):
    p1 = result["predictions"]["P1"]["perEpisode"]
    assert p1 and {x["cell"].split("/")[-5] for x in p1} == {"search-pause"}
    p2 = result["predictions"]["P2"]
    assert len(p1) == 3 and p2["1"]["n"] == 3 and p2["10"] is None and p2["1"]["holds"] is None     # 3 search episodes, not 6
    assert all("consul" not in x["cell"] for x in p1)


# ----------------------------------------------------------------------------- the path declaration is checked, not assumed

def _fake_R(path):
    return {"results": {"primary": {"eps": [{"cell": "x", "target": "consul", "affectedPath": path}]}}}


def chk_path(tmp_path, _w=None):
    """The declaration is checked INSIDE run34 (deleting that call must fail this): with the declared path changed, the real run
    stops; with the declared path, the real run completes."""
    camp = offpath_campaign(tmp_path / "c", blocks=(1,))
    v34._check_paths(_fake_R(["consul"]))
    saved = v34.HOTEL_MODEL["affectedPath"]
    v34.HOTEL_MODEL["affectedPath"] = {"consul": ["consul", "frontend"]}
    try:
        try:
            v34.run34(camp, system="hotel", reference=False)
        except v24.UnknownSchema as exc:
            return "declares ['consul', 'frontend']" in str(exc)
        return False
    finally:
        v34.HOTEL_MODEL["affectedPath"] = saved


def test_the_declared_affected_path_of_consul_is_what_the_episodes_used(result):
    assert chk_path.__doc__ and chk_path(Path(__import__("tempfile").mkdtemp()))
    eps = [e for e in result["results"]["primary"]["eps"] if e["target"] == "consul"]
    assert eps and all(e["affectedPath"] == ["consul"] for e in eps)
    edges, on_route = v24.dt.call_graph("hotel")
    assert "consul" not in on_route and not any("consul" in e for e in edges)


# ----------------------------------------------------------------------------- end to end

def test_end_to_end_regimes_targets_and_epoch(result):
    eps = result["results"]["primary"]["eps"]
    assert {e["regime"] for e in eps} == {CP, SP} and {e["target"] for e in eps} == {"consul", "search"}
    assert len([e for e in eps if e["regime"] == CP]) == 3 and len([e for e in eps if e["regime"] == SP]) == 3
    assert result["_v34ctx"] == {"system": "hotel", "hotelActive": True, "hotelOffPath": [EPOCH]}
    assert {c["studyEpoch"] for c in result["cells"] if c["valid"]} == {EPOCH}


def test_extra_service_consul_is_a_metric_sensor_source(result):
    """consul's docker-stats and cgroup rows are read by the existing Hotel parser without any change: sensors of service consul
    exist in every cell of the epoch; no span sensor (consul is not Jaeger-traced)."""
    J = v34.build_json34(result)
    x = J["v34"]["extraCollectedServices"]["%s:consul" % EPOCH]
    assert x["validCellsOfEpoch"] == 9 and x["cellsWithAnySensor"] == 9 and x["collected"]
    assert x["cellsByChannel"] == {"metric": 9}
    keys = {k for c in result["cells"] if c["valid"] for k in c["prep"] if k[1] == "consul"}
    assert ("metric", "consul", "cpu") in keys and ("metric", "consul", "sys_memory") in keys and x["distinctSensors"] == len(keys)


def test_consul_native_log_lines_are_a_dead_channel_and_the_readout_says_so(result):
    """consul 1.13's own log format matches no Hotel layout: the lines are in application.log (27 = 3 per cell x 9), no log sensor
    of consul exists, and the readout names that instead of reporting an empty channel as nothing."""
    J = v34.build_json34(result)
    x = J["v34"]["extraCollectedServices"]["%s:consul" % EPOCH]
    assert x["logLinesInApplicationLog"] == 27 and x["cellsWithLogLines"] == 9 and x["logSensors"] == 0
    assert "no log sensor" in x["logNote"] and "dead channel" in x["logNote"]
    md = v34.render34(result, J)
    assert "no Hotel log layout" in md and "log sensors: 0" in md
    assert not any(k[0] == "log" and k[1] == "consul" for c in result["cells"] if c["valid"] for k in c["prep"])


def test_design_counts_and_the_exposure_note(result):
    blk = v34._v34_block(result)
    dc = blk["designCounts"]
    assert dc["consul-pause-effect r1"] == {"declaredPerRegimeAndRate": 5, "found": 3, "valid": 3}
    assert dc["consul-pause-effect r10"] == {"declaredPerRegimeAndRate": 5, "found": 0, "valid": 0}     # absent: 0 found, not omitted
    assert dc["no-fault-calibration r1"]["found"] == 3
    x = blk["extraCollectedServices"]["%s:consul" % EPOCH]
    assert x["cellsWithoutApplicationLog"] == 0 and x["listedAsNeverExposed"] in (True, False)
    md = v34.render34(result, v34.build_json34(result))
    assert "### Declared design against cells found" in md


def test_consul_native_lines_match_no_hotel_layout():
    """The finding behind the dead channel, pinned on the parser itself: lines in consul 1.13's documented default format (go-hclog:
    `<ISO 8601> [LEVEL]  <logger>: <msg>`, and the `==>` banner) yield no record under symptoms.HOTEL_LAYOUTS."""
    from sensor_rep.parsers import common
    S = common.symptoms()
    lines = ["==> Starting Consul agent...", "2026-10-14T12:34:56.789Z [INFO]  agent.server.raft: entering leader state",
             "2026-10-14T12:34:57.001Z [WARN]  agent: Check is now critical: check=x",
             '2026-10-14T12:34:58.000Z [ERROR] agent.http: Request error: method=GET url=/v1/x error="x"']
    recs, st = S.parse_stream(lines, S.HOTEL_LAYOUTS)
    assert recs == [] and st["unparsed"] == 4


def test_consul_log_lines_in_a_known_layout_are_log_sensors(tmp_path):
    """The parser admits a service by its compose prefix: the same lines as zerolog JSON become log sensors of consul (so the
    absence above is the layout's, not a limit of the extra-service admission)."""
    camp = offpath_campaign(tmp_path / "c", blocks=(1,), consul_log="json")
    cells = cells34([camp])
    assert all(c["valid"] for c in cells)
    assert all(any(k[0] == "log" and k[1] == "consul" for k in c["prep"]) for c in cells)
    R = run([camp])
    x = v34._v34_block(R)["extraCollectedServices"]["%s:consul" % EPOCH]
    assert x["cellsByChannel"].get("log") == 3 and x["logSensors"] >= 1 and "logNote" not in x


def test_manifestation_record_and_route_outage_not_required(result):
    J = v34.build_json34(result)
    rows = J["v34"]["manifestation"]["episodes"]
    assert len(rows) == 3 and all(r["target"] == "consul" for r in rows)
    assert all(r["manifested"] is True and r["duringStatePaused"] is True and r["outageObserved"] is False
               and r["dockerPauseEvents"] == 1 and r["dockerUnpauseEvents"] == 1 and r["offPathManifested"] is True for r in rows)
    assert "recorded, not required" in J["v34"]["manifestation"]["rule"] or "not required" in J["v34"]["manifestation"]["rule"]


def test_manifestation_unknown_fields_are_dash_not_false(tmp_path):
    camp = offpath_campaign(tmp_path / "c", blocks=(1,), consul_cell_kw={"events": False})
    R = run([camp])
    row = v34._v34_block(R)["manifestation"]["episodes"][0]
    assert row["dockerEventsRead"] is False and row["dockerPauseEvents"] is None and row["offPathManifested"] is None
    assert row["manifested"] is True


def test_an_unpaused_consul_is_not_manifested_by_rule(tmp_path):
    camp = offpath_campaign(tmp_path / "c", blocks=(1,), consul_cell_kw={"paused": False, "outage": True})
    R = run([camp])
    row = v34._v34_block(R)["manifestation"]["episodes"][0]
    assert row["offPathManifested"] is False and row["outageObserved"] is True      # the outage is recorded, never the verdict


def test_lanes_hotel_has_own_and_no_coordinator_or_lag(result):
    J = v34.build_json34(result)
    L = J["v33"]["lanes"]["regimes"]
    assert set(L) == {CP, SP} and J["v33"]["lanes"]["rules"]["coordinator"] is None and J["v33"]["lanes"]["rules"]["lag"] is None
    for regime in (CP, SP):
        for ep in L[regime]["episodes"]:
            lanes = ep["lanes"]
            assert lanes["coordinator"]["note"] and lanes["coordinator"]["earliest"] is None
            assert lanes["lag"]["note"] and lanes["lag"]["collectedSensors"] is None
        s = L[regime]["byRate"]["1"]
        assert s["coordinator"]["withFire"] is None and s["lag"]["withFire"] is None and s["coordinator"]["note"]
    consul = L[CP]["episodes"][0]["lanes"]["own"]
    assert consul["collectedSensors"] > 0                   # consul's own sensors were collected, so the lane is not `—`
    search = L[SP]["episodes"][0]["lanes"]["own"]
    assert search["collectedSensors"] > 0


def test_consul_not_collected_is_a_dash_not_a_zero(tmp_path):
    """An off-path epoch whose cells carry no consul rows: the extra service reads `collected` False and the own lane of consul
    has no collected sensor (the summary's denominator leaves the episode out), never a count of 0 fires over 3."""
    camp = offpath_campaign(tmp_path / "c", consul=False)
    R = run([camp])
    J = v34.build_json34(R)
    x = J["v34"]["extraCollectedServices"]["%s:consul" % EPOCH]
    assert x["collected"] is False and x["cellsWithAnySensor"] == 0 and x["distinctSensors"] == 0 and x["logLinesInApplicationLog"] == 0
    s = J["v33"]["lanes"]["regimes"][CP]["byRate"]["1"]["own"]
    assert s["withCollectedSensors"] == 0 and s["episodes"] == 3 and s["ttdMedian"] is None
    md = v34.render34(R, J)
    assert "with any sensor of the service: 0" in md


def test_a_consul_sensor_that_fires_is_an_own_lane_fire(tmp_path):
    """HO-L2's miss condition is observable: consul's docker-stats cpu falls to 0 inside the pause (fixture), after a calibration
    on enough no-fault cells; the own lane of consul reports that fire, by construction (decision 84/BC: the paused target's own
    silence), beside a counted field that reads a miss by rule. A collected own lane is never `—`."""
    base = tmp_path / "w"
    camps = [offpath_campaign(base / "o", blocks=(1, 2, 3, 4))]
    R = run(camps)
    J = v34.build_json34(R)
    own = [e["lanes"]["own"] for e in J["v33"]["lanes"]["regimes"][CP]["episodes"]]
    assert len(own) == 4 and all(o["collectedSensors"] == 7 for o in own)
    assert all(o["earliest"] is None and o["countedFires"] == 0 for o in own)                   # counted: a miss by rule
    assert all(o["earliestByConstruction"]["sensor"] == "metric:consul:cpu" and o["byConstructionFires"] >= 1 for o in own)
    assert all(o["earliestByConstruction"]["label"] == "by construction, not counted" for o in own)
    for e in R["results"]["primary"]["eps"]:
        if e["regime"] == CP:
            assert all(f["svc"] == "consul" for f in e["fires"] if f["own"]) and any(f["own"] for f in e["fires"])


def test_json_markdown_and_cli(world, tmp_path):
    out = tmp_path / "ro"
    assert v34.main([str(world["camp"]), "--system", "hotel", "--out", str(out)]) == 0
    J = json.loads((out / v34.OUT_JSON).read_text())
    md = (out / v34.OUT_MD).read_text()
    assert J["version"] == "3.4" and J["scriptSha256"] == v34._sha(v34.__file__) and J["label"] == v34.LABEL
    assert J["v33ScriptSha256"] == v33._sha(v33.__file__) and J["v32ScriptSha256"] == v32._sha(v32.__file__)
    assert J["v31ScriptSha256"] == v31._sha(v31.__file__)
    assert J["v34"]["parametersV34Sha256"] == v34._sha(v34.PARAMETERS_V34)
    assert J["v33"]["parametersV33Sha256"] == v33._sha(v33.PARAMETERS_V33)
    assert J["v34"]["hotelOffPathEpochsRead"] == [EPOCH] and J["v34"]["hotelPauseRegimes"] == v34.HOTEL_MODEL["pauseRegimes"]
    assert J["v34"]["hotelP1P2Regime"] == "search-pause-effect"
    assert "## v3.4 additions" in md and "### Lanes, `consul-pause-effect`" in md and "### Off-path manifestation record" in md
    assert "no coordinator lane is declared for this system" in md and "no lag lane is declared for this system" in md
    with pytest.raises(SystemExit):
        v34.main([str(world["camp"]), "--system", "hotel", "--out", str(out)])


def test_blocks_and_test_blocks_are_refused_for_hotel(world, tmp_path):
    """No registry split is declared for the Hotel epoch: --blocks reaches v3.2's REQUIRE_E_FOR_BLOCKS and stops."""
    with pytest.raises(SystemExit, match="no cell of a campaign-E epoch"):
        v34.run34(world["camp"], system="hotel", reference=False, blocks={1})


# ----------------------------------------------------------------------------- legacy readouts are v3.1's / v3.3's

def _fires(R):
    return [(e["regime"], e["rate"], e["block"], [(f["family"], f["ch"], f["svc"], f["tok"], f["rule"], f["ttd"]) for f in e["fires"]])
            for e in R["results"]["primary"]["eps"]]


def test_legacy_hotel_readout_is_v31s(tmp_path):
    """No off-path cell: v3.4's rules are off, and a v3.4 read of a legacy Hotel campaign equals v3.1's (episodes, fires,
    predictions, calibration), with the extra keys only in the v32/v33/v34 blocks; the committed Hotel primary readout is
    compared key by key offline (FREEZE_V34_20261015.md)."""
    camp = tmp_path / "l"
    legacy_campaign(camp, blocks=(1, 2, 3, 4))
    a = v31.run(camp, system="hotel", reference=False)
    b = v34.run34(camp, system="hotel", reference=False)
    assert b["_v34ctx"] == {"system": "hotel", "hotelActive": False, "hotelOffPath": []}
    assert _fires(a) == _fires(b) and a["predictions"]["P1"] == b["predictions"]["P1"]
    assert a["cal"]["primary"]["perRate"].keys() == b["cal"]["primary"]["perRate"].keys()
    with v24.use_system("hotel"):
        v31.finish(a)
        v31.finish(b)
    ja, jb = v31.build_json(a), v34.build_json34(b)
    for k, v in ja.items():
        if k in ("generatedAt", "script", "scriptSha256", "version", "label"):
            continue
        if k == "episodes":
            assert [{x: y for x, y in e.items() if x not in ("studyEpoch", "heldOut")} for e in jb[k]] == v
            continue
        assert jb[k] == v, k


def test_legacy_teastore_and_otel_readouts_are_v33s():
    a = v33.run33(t22.TS_CAMP, system="teastore", reference=False)
    b = v34.run34(t22.TS_CAMP, system="teastore", reference=False)
    assert _fires(a) == _fires(b) and a["predictions"]["P1"]["perEpisode"] == b["predictions"]["P1"]["perEpisode"]
    a = v33.run33(t22.OT_CAMP, system="otel", reference=False)
    b = v34.run34(t22.OT_CAMP, system="otel", reference=False)
    assert _fires(a) == _fires(b)


def test_rebinding_is_restored_on_exit():
    names = [(v24, "FAULT_TARGETS"), (v24, "FAULT_REGIMES"), (v24, "pause_regime"), (v24, "load_or_invalid"),
             (v31, "find_and_load3"), (v32, "v32_context"), (v33, "v33_context"), (v33, "LANE_RULES"), (v32, "EPOCH_PROFILES")]
    before = [getattr(m, n) for m, n in names]
    with v24.use_system("hotel"), v34._v34_wrapped(True), v33._v33_wrapped(False), v32.v32_context("hotel"):
        assert CP in v24.FAULT_REGIMES and v24.FAULT_TARGETS[CP] == ("consul", "pause")
        assert v24.load_or_invalid is v34.load_hotel34 and v24.pause_regime is v34.pause_regime34
        assert v32.v32_context is v34.v34_context and "hotel" in v33.LANE_RULES
    with pytest.raises(RuntimeError):
        with v24.use_system("hotel"), v34._v34_wrapped(True), v33._v33_wrapped(False), v32.v32_context("hotel"):
            raise RuntimeError("x")
    after = [getattr(m, n) for m, n in names]
    assert all(a is b for a, b in zip(before, after)) and "hotel" not in v33.LANE_RULES
    assert v34._ACTIVE == {"hotel": False}
    assert CP not in v24.FAULT_REGIMES and v24.FAULT_REGIMES == v24.v1.FAULT_REGIMES


# ----------------------------------------------------------------------------- the lanes engine on Hotel's rules

def fire(ch, svc, tok, ttd, own=False, counts=True, rule="appear"):
    return {"ch": ch, "svc": svc, "tok": tok, "ttd": ttd, "ttdLo": ttd, "own": own, "counts": counts, "rule": rule, "family": "L"}


def chk_lane_rules(_tmp=None, _w=None):
    """Hotel: a fire of consul's own sensor is `own`; a fire of any other service is no lane fire (there is no coordinator or lag
    service to match), and both absent lanes carry a note, never a 0."""
    rules = v34.lane_rules()["hotel"]
    keys = [("log", "consul", "aaa"), ("metric", "consul", "cpu"), ("log", "frontend", "bbb")]
    e = {"target": "consul", "fires": [fire("log", "consul", "aaa", 4.0, own=True), fire("log", "frontend", "bbb", 2.0),
                                       fire("ledger", "frontend", "route", 0.5, rule="failed")],
         "_c": {"prep": {k: None for k in keys}}}
    lanes = v33.lanes_episode(e, rules)
    return (lanes["own"]["earliest"]["ttd"] == 4.0 and lanes["own"]["countedFires"] == 1 and lanes["own"]["collectedSensors"] == 2
            and lanes["coordinator"]["note"] and lanes["lag"]["note"] and lanes["coordinator"]["earliest"] is None)


def test_hotel_lane_rules():
    assert chk_lane_rules()


# ----------------------------------------------------------------------------- the frozen files are untouched

FROZEN = {
    "research/detection-time/sweep_analysis_v3_3.py": "c8cd5072ed4b22cae9360e6446f969c75b4e66b900a08d3cfe0efbdadcd36e18",
    "research/protocol/parameters_v3_3.json": "a85daa482b487e4600d11c91dbdecac9a98b01fcd542b9ef051c06cf1268f4b7",
    "research/placement/celf_v3_3.py": "5d801f634d4d359a0b49c51faf390244eee99c09241c99bc778f0e20929d1ead",
    "research/placement/score_test_v3_3.py": "704cf341ae23e09a123915e14b4546dc1e3b02b3cf7bf2fa4808059acbd2e442",
    "research/detection-time/sweep_analysis_v3_2.py": "97eb0a1d4f3f7e0daecee447113fdd14bd14b84812f420ddb3903bfe16759465",
    "research/protocol/parameters_v3_2.json": "ab4a5af7243e776f536b09a39e649b1be968d23f1767ef2f5a166ac08e340a67",
    "research/detection-time/sweep_analysis_v3.py": "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd",
    "research/protocol/parameters_v3.json": "212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000",
    "research/detection-time/sweep_analysis_v2.py": "075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9",
    "research/detection-time/sweep_analysis.py": "e4ad9ddf9239de4cda6d07e6570145333d02f894bd4bc6527c378a175d4f0760",
    "research/protocol/sensor_rep/parsers/hotel.py": "d22a3ea595474ec8655eeafc4cdd27d55d3be5b22ac1db2985117b345f1b1607",
    "research/project-map/project_map.json": "28b6bf54f0e5a7204802baa11b90c5efbe292ac6661b907932544ca9bd020ccb",
}


def test_the_frozen_v33_chain_and_the_hotel_parser_are_byte_identical():
    for rel, sha in FROZEN.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel


def test_status_and_label_are_the_freeze_ones():
    assert v34.LABEL == "frozen v3.4 for the Hotel off-path epoch hotel-offpath-v1 (FREEZE_V34_20261015.md)"
    assert "STATUS: FROZEN by digest (research/protocol/FREEZE_V34_20261015.md)" in v34.__doc__
    assert all(p["status"] == "active" for p in v34.REGISTRY34.values())


def test_registry_entries_have_origins_and_every_used_one_exists():
    for n, p in v34.REGISTRY34.items():
        assert p["origin_ref"] and p["origin_type"] in ("decision", "literature", "measured", "upstream",
                                                        "engineering default", "unknown")
        assert p["status"] in ("active", "provisional", "superseded"), n
    assert v34.PARAMS_USED34 <= set(v34.REGISTRY34) and set(v34.REGISTRY34) == {
        "V34_EPOCH_PROFILES", "V34_ROUTE_MODEL_HOTEL", "V34_LANE_RULES", "V34_REPORT_RULE"}


def test_the_registry_matches_the_harness_declaration():
    """The pins against the committed harness (9ad0b98): regimes, targets, rates and blocks as candidate_offpath.py declares them,
    and the legacy regime set as v1 declares it."""
    p = v34.HOTEL_PROFILES[EPOCH]
    assert p["faultRegimes"] == {CP: ["consul", "pause"], SP: ["search", "pause"]} and p["noFaultRegime"] == NF
    assert p["rates"] == [10.0, 1.0] and p["postures"] == ["full"] and p["extraCollectedServices"] == ["consul"]
    assert p["design"]["blocks"] * p["design"]["cellsPerBlock"] == p["design"]["cells"] == 30
    assert v34.legacy_regimes() == {NF, *v24.v1.FAULT_REGIMES} and set(v34.HOTEL_MODEL["pauseRegimes"]) == set(p["faultRegimes"])
    assert {r: t[0] for r, t in p["faultRegimes"].items()} == v34.HOTEL_MODEL["pauseRegimes"]
    assert v34.HOTEL_MODEL["p1p2Regime"] == SP and v34.HOTEL_MODEL["offPathRegime"] == CP
    assert set(p["rates"]) <= set(v24.RATES)
    assert v34.legacy_epochs() == [QUIET_EPOCH, SWEEP_EPOCH]


def test_v34_adds_epochs_and_lane_rules_and_never_redefines_v33s():
    assert not set(v34.HOTEL_PROFILES) & (set(v33.ADDED_PROFILES) | set(v33.V32_PROFILES))
    assert set(v34.LANE_RULES34) == {"hotel"} and not set(v34.LANE_RULES34) & set(v33.LANE_RULES)
    assert v34.LANE_RULES34["hotel"]["coordinator"] is None and v34.LANE_RULES34["hotel"]["lag"] is None
    assert "hotel" not in v33.LANE_RULES            # v3.3 is the frozen engine: Hotel's rules live in v3.4 only


# ----------------------------------------------------------------------------- planted defects: each switch has a check

CHECKS = {"ADMIT_HOTEL_OFFPATH": chk_admitted, "HOTEL_SHAPE_CHECK": chk_shape, "HOTEL_TARGET_CHECK": chk_target,
          "HOTEL_DESIGN_CHECK": chk_design, "HOTEL_EPOCH_CHECK": chk_epoch, "HOTEL_EXTRA_ALONE": chk_extra_alone, "HOTEL_UNIQUE_CELLS": chk_unique,
          "HOTEL_TWO_PAUSE": chk_two_pause, "HOTEL_PATH_CHECK": chk_path, "HOTEL_LANE_RULES": chk_lane_rules}


def _passes(chk, tmp_path):
    try:
        return bool(chk(tmp_path, None))
    except (v24.UnknownSchema, SystemExit, AssertionError, StopIteration, KeyError):
        return False


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, tmp_path, monkeypatch):
    """Each v3.4 switch has a check that passes, and fails (or stops) once the switch is planted off."""
    assert _passes(CHECKS[flag], tmp_path / "on"), flag
    monkeypatch.setattr(v34, flag, False)
    assert not _passes(CHECKS[flag], tmp_path / "off"), flag


def test_every_switch_has_a_check():
    switches = {k for k, v in vars(v34).items() if k.isupper() and isinstance(v, bool)}
    assert switches == set(CHECKS) == set(v34.SWITCHES), switches ^ set(CHECKS)
