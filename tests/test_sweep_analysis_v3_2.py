"""Analysis v3.2 (research/detection-time/sweep_analysis_v3_2.py): the reader for the off-path epochs, the multi-route
ledger, off-path classes, per-route exposure and the block split (BUDGET_E.md step 3).

Layer: reader + synthetic end-to-end. Synthetic cells only: the harness-written OTel cells of tests/fixtures/sweep_v22,
post-edited into the SHAPE DRAFTED in parameters_v3_2.json (the harness's mix ledger of kind otel-demo-mix-ledger-v1, the
off-path epochs, fraud and accounting pause cells cloned from the pause cell). No harness commit of these epochs
existed when this was written, so the shape is provisional (registry status `provisional`); the decision-92 lesson
holds regardless: a synthetic cell of EACH new epoch is driven through the loader (find_and_load32 -> load3), and an
epoch not in the registry stops the run. Every v3.2 change has a planted defect (switch off) under which one of its
checks fails (test_planted_defects), and v3.1 is untouched (digests).
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))
sys.path.insert(0, str(ROOT / "research" / "placement"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_analysis_v3_2 as v32  # noqa: E402
import test_sweep_analysis_v22_systems as t22  # noqa: E402
import test_sweep_analysis_v3 as t3  # noqa: E402

v31, v24 = v32.v31, v32.v24
PILOT, EPOCH_E = "otel-offpath-pilot-v1", "otel-offpath-e-v1"
FRAUD, ACCT = "fraud-pause-effect", "accounting-pause-effect"
R_PROD, R_REC, R_CHK = "GET /api/products/{id}", "GET /api/recommendations", "POST /api/checkout"
ROUTES = [R_PROD, R_REC, R_CHK]
TASK = {R_PROD: "browse_product", R_REC: "get_recommendations", R_CHK: "checkout"}
MULTI_KIND = "otel-demo-mix-ledger-v1"


# ----------------------------------------------------------------------------- the synthetic off-path campaign

def _edit(path, fn):
    doc = json.loads(path.read_text())
    out = fn(doc)
    path.write_text(json.dumps(out if isinstance(out, dict) else doc))


def _to_multi(led, routes=ROUTES, route_of=None):
    """A v1 ledger -> the harness's mix ledger (otel-demo-mix-ledger-v1, candidate_remote.run_mix_workload): the mix keys
    mixSha256 / taskCounts / routeCounts and, per row, route, task, taskIndex, step, method, target, bodySha256, dependsOn."""
    route_of = route_of or (lambda i: routes[2] if i % 5 == 4 else routes[i % 2])
    out = dict(led)
    rows = [dict(q, route=route_of(i), task=TASK.get(route_of(i), "task"), taskIndex=i, step=0, method="GET",
                 target="/x", bodySha256=None, dependsOn=None) for i, q in enumerate(led["requests"])]
    out["kind"], out["method"] = MULTI_KIND, "MIX"
    out["mixSha256"] = "0" * 64
    out["routeCounts"] = {r: sum(1 for q in rows if q["route"] == r) for r in sorted({q["route"] for q in rows})}
    out["taskCounts"] = {t: sum(1 for q in rows if q["task"] == t) for t in sorted({q["task"] for q in rows})}
    out["requests"] = rows
    return out


def _set_epoch(camp, epoch, multi=True):
    for rp in sorted((camp / "runs").rglob("receipt.json")):
        _edit(rp, lambda rc: rc["runKey"].__setitem__("studyEpoch", epoch))
        if multi:
            _edit(rp.parent / "request-ledger.json", _to_multi)


def _retarget(d, regime, service, scenario, block):
    """Clone-edit a pause cell into another pause class (the target's name everywhere the harness writes it)."""
    def rename(o):
        if isinstance(o, dict):
            return {k: rename(v) for k, v in o.items()}
        if isinstance(o, list):
            return [rename(v) for v in o]
        return {"frontend": service, "cid-frontend": "cid-" + service, "frontend-pause": scenario}.get(o, o)
    for name in ("intervention.json", "docker-events.json"):
        if (d / name).exists():
            _edit(d / name, rename)
    def rc(doc):
        doc["runKey"]["regime"], doc["runKey"]["block"] = regime, block
    _edit(d / "receipt.json", rc)


def offpath_campaign(dest, epoch=EPOCH_E, blocks=True, only_checkout_fails=False):
    """B-shaped fixture (decision-69 H4 records) in `epoch` with multi-route ledgers, plus a fraud-pause cell (block 2)
    and an accounting-pause cell (block 3) cloned from the frontend-pause cell."""
    camp = t3._ot_b_campaign(dest)
    pause = t22._cell_dir(camp, t22.OT_PAUSE)
    for regime, service, scenario, block in ((FRAUD, "frauddetectionservice", "fraud-pause", 2),
                                             (ACCT, "accountingservice", "accounting-pause", 3)):
        d = camp / "runs" / "effect" / scenario / pause.name
        shutil.copytree(pause, d)
        _retarget(d, regime, service, scenario, block if blocks else 1)
    if epoch == EPOCH_E:                     # E has no throttle regime (decision 108); its reader refuses one
        shutil.rmtree(t22._cell_dir(camp, t22.OT_THROTTLE).parent)
    _set_epoch(camp, epoch)
    if only_checkout_fails:                  # the fraud cell: every route answers except the checkout route
        d = t22._cell_dir(camp, FRAUD)

        def heal(led):
            for q in led["requests"]:
                if q["route"] != R_CHK and q["outcome"] != "ok":      # answered at once, as before the fault
                    q.update(outcome="ok", status=200, error=None, bytes=512,
                             endedMonotonic=q["startedMonotonic"] + 0.001, endedAtEpoch=q["startedAtEpoch"] + 0.001)
        _edit(d / "request-ledger.json", heal)
    return camp


def quiet(camp, dest, copies=9):
    return t22._quiet_campaign(camp, t22.OT_NF, dest, copies=copies, system="otel")


def cells_of(camps, blocks=None, system="otel"):
    with v24.use_system(system), v32.v32_context(system, None, blocks):
        return v31.find_and_load3(camps)[1]


NO_SPLIT = {"train": None, "test": None}


@pytest.fixture(autouse=True)
def _no_registry_split(monkeypatch):
    """The registry declares decision 100's 3+2 split; the synthetic campaigns use blocks 1-3, so every test starts with
    no split declared and the split tests set their own."""
    monkeypatch.setattr(v32, "E_SPLIT", NO_SPLIT)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("v32")
    camp = offpath_campaign(base / "e")
    return {"base": base, "camp": camp, "quiet": quiet(camp, base / "q")}


def _by_any(cells, regime):
    return next(c for c in cells if c["regime"] == regime)


def _by(cells, regime):
    return next(c for c in cells if c["valid"] and c["regime"] == regime)


# ----------------------------------------------------------------------------- 8.1 / 8.2: epochs are admitted explicitly

def test_a_throttle_cell_under_e_is_refused(tmp_path):
    """Planted: E's profile has no throttle regime (decision 108), so a throttle cell stamped with E's epoch stops the run."""
    camp = t3._ot_b_campaign(tmp_path / "c")
    _set_epoch(camp, EPOCH_E)
    with pytest.raises(v24.UnknownSchema, match="productcatalog-cpu-throttle-effect"):
        cells_of([camp])

@pytest.mark.parametrize("epoch", [PILOT, EPOCH_E])
def test_each_new_epoch_is_driven_through_the_loader(epoch, tmp_path):
    """Decision-92 lesson: a synthetic cell of each new epoch goes through find_and_load3 and is a valid,
    campaign-B-shaped cell with its routes, tasks and regimes."""
    camp = offpath_campaign(tmp_path / "c", epoch=epoch)
    cells = cells_of([camp])
    assert cells and all(c["valid"] for c in cells), [c.get("reason") for c in cells if not c["valid"]]
    assert {c["studyEpoch"] for c in cells} == {epoch} and {c["harness"] for c in cells} == {"B"}
    expected = {FRAUD, ACCT, t22.OT_PAUSE, t22.OT_NF} | ({t22.OT_THROTTLE} if epoch == PILOT else set())
    assert {c["regime"] for c in cells} == expected
    f = _by(cells, FRAUD)
    assert f["target"] == "frauddetectionservice" and f["faultKind"] == "pause"
    assert f["ledgerRoutes"] == ROUTES and set(r.route for r in f["ledger"]) == set(ROUTES)
    assert set(f["ledgerTasks"].values()) == set(TASK.values())
    assert f["h4"]["status"] == "used", f["h4"]


def test_unknown_epoch_stops_the_run(tmp_path):
    camp = offpath_campaign(tmp_path / "c", epoch="otel-offpath-x-v9")
    with pytest.raises(v24.UnknownSchema):
        cells_of([camp])


def test_epoch_names_come_from_the_registry_not_the_code():
    """The E epoch name is a registry parameter: renaming it there is what admits another name."""
    assert EPOCH_E in v32.e_epochs() and PILOT in v32.new_epochs() and PILOT not in v32.e_epochs()
    for name in ("V32_EPOCH_PROFILES", "V32_LEDGER_SCHEMAS", "V32_ROUTE_MODEL_OTEL"):   # re-pinned at the harness commit 6a5c2a9 (F1)
        assert v32.REGISTRY32[name]["status"] == "active" and "6a5c2a9" in v32.REGISTRY32[name]["origin_ref"], name
    assert "6a5c2a9" in v32.REGISTRY32["V32_P1P2_DEPENDS_RULE"]["origin_ref"]


def test_epochs_are_admitted_only_while_reading():
    with v24.use_system("otel"):
        before = list(v24.param("SYSTEM_OTEL")["studyEpochs"])
        with v32.v32_context("otel"), v31.admit_b_epochs():
            inside = list(v24.param("SYSTEM_OTEL")["studyEpochs"])
            assert v24.FAULT_REGIMES[-2:] == (FRAUD, ACCT) or {FRAUD, ACCT} <= set(v24.FAULT_REGIMES)
        after = list(v24.param("SYSTEM_OTEL")["studyEpochs"])
        assert PILOT in inside and EPOCH_E in inside and before == after and PILOT not in after
        assert FRAUD not in v24.FAULT_REGIMES and v31.STUDY_EPOCHS_B["otel"] == [
            "otel-repeat-episodes-v1", "otel-repeat-episodes-c-v1"]


def test_shape_mismatches_stop_the_run(tmp_path):
    # a legacy single-route ledger in a new epoch
    camp = offpath_campaign(tmp_path / "a")
    d = t22._cell_dir(camp, t22.OT_NF)
    legacy = json.loads((t22.OT_CAMP / "runs" / "calibration" / "r1-b01-06-full" / "request-ledger.json").read_text())
    (d / "request-ledger.json").write_text(json.dumps(legacy))
    with pytest.raises(v24.UnknownSchema, match="declares"):
        cells_of([camp])
    # a multi-route ledger in a legacy epoch (the B epoch)
    camp = offpath_campaign(tmp_path / "b")
    _set_epoch(camp, "otel-repeat-episodes-v1", multi=False)
    with pytest.raises(v24.UnknownSchema, match="declares"):
        cells_of([camp])
    # a regime of the off-path class in a legacy epoch
    camp = offpath_campaign(tmp_path / "c")
    for rp in (camp / "runs").rglob("receipt.json"):
        _edit(rp, lambda rc: rc["runKey"].__setitem__("studyEpoch", "otel-repeat-episodes-v1"))
        _edit(rp.parent / "request-ledger.json", lambda led: led.update(kind="otel-demo-route-ledger-v1", url="http://x/a")
              or {k: v for k, v in led.items() if k != "routes"})
    with pytest.raises(v24.UnknownSchema):
        cells_of([camp])


def test_ledger_key_sets_and_routes_are_pinned(tmp_path):
    for name, fn, match in (
            ("extra", lambda led: led.__setitem__("extra", 1), "keys"),
            ("nocounts", lambda led: led.__setitem__("routeCounts", {}), "non-empty object"),
            ("route", lambda led: led["requests"][3].__setitem__("route", "GET /nope"), "not in the ledger's declared"),
            ("rowkey", lambda led: led["requests"][0].pop("task"), "row 0:"),
            ("kind", lambda led: led.__setitem__("kind", "otel-demo-route-ledger-v3"), "declares")):
        camp = offpath_campaign(tmp_path / name)
        _edit(t22._cell_dir(camp, t22.OT_NF) / "request-ledger.json", fn)
        with pytest.raises(v24.UnknownSchema, match=match):
            cells_of([camp])


# ----------------------------------------------------------------------------- 4.1: one route per row, same reading

def test_single_route_multi_ledger_equals_the_legacy_reading(tmp_path):
    """A v2 ledger whose rows all carry the legacy route reads to exactly the Req rows v2.4 reads from the v1 ledger."""
    camp = offpath_campaign(tmp_path / "c")
    d = t22._cell_dir(camp, t22.OT_NF)
    led = json.loads((d / "request-ledger.json").read_text())
    legacy = json.loads((t22.OT_CAMP / "runs" / "calibration" / "r1-b01-06-full" / "request-ledger.json").read_text())
    path = "/api/products/66VCHSJNUP"
    _edit(d / "request-ledger.json", lambda x: _to_multi(legacy, routes=[path], route_of=lambda i: path))
    c = _by(cells_of([camp]), t22.OT_NF)
    with v24.use_system("otel"):
        old = v24.otel_ledger(legacy, __import__("collections").Counter())[0]
    assert [tuple(r) for r in c["ledger"]] == [tuple(r) for r in old]
    assert led["kind"] == MULTI_KIND


# ----------------------------------------------------------------------------- end to end

def _run(world, **kw):
    R = v32.run32([world["camp"], world["quiet"]], system="otel", reference=False, **kw)
    with v24.use_system("otel"):
        v31.finish(R)
    return R


@pytest.fixture(scope="module")
def result(world):
    return _run(world)


def test_end_to_end_off_path_classes_are_scored_like_the_others(result):
    eps = result["results"]["primary"]["eps"]
    classes = {e["regime"] for e in eps}
    assert {FRAUD, ACCT, t22.OT_PAUSE} <= classes and t22.OT_THROTTLE not in classes      # E has no throttle (decision 108)
    f = next(e for e in eps if e["regime"] == FRAUD)
    assert f["target"] == "frauddetectionservice" and f["calibrated"]
    # the declared affected path of an off-path target: the consumer and its broker
    assert set(f["affectedPath"]) == {"frauddetectionservice", "kafka"}
    # P4 and P1/P2 ran with three stopping regimes (v2.4's one-pause assertion would stop); P1 is the request-path pause's
    p4 = result["predictions"]["P4"]["P4a"]
    assert FRAUD in p4 and ACCT in p4 and t22.OT_PAUSE in p4
    p1 = result["predictions"]["P1"]["perEpisode"]
    assert p1 and all("frontend-pause" in x["cell"] for x in p1)


def own_per_class(R):
    """Decision 84: own = the fire's service is THIS episode's target. The same frontend sensors are own in the
    frontend-pause episode and not own in the cloned fraud-pause episode."""
    eps = R["results"]["primary"]["eps"]
    for e in eps:
        for f in e["fires"]:
            if f["family"] != "E" and f["own"] != (f["svc"] == e["target"]):
                return False
    key = lambda f: (f["ch"], f["svc"], f["tok"])
    fe = {key(f) for e in eps if e["regime"] == FRAUD for f in e["fires"] if f["svc"] == "frontend"}
    fe_own = {key(f) for e in eps if e["regime"] == t22.OT_PAUSE for f in e["fires"] if f["own"]}
    fraud_own = [f for e in eps if e["regime"] == FRAUD for f in e["fires"] if f["svc"] == "frontend" and f["own"]]
    # the cloned fraud cell has frontend fires, the same sensors are own in the frontend class and never in the fraud one
    return bool(fe) and bool(fe & fe_own) and not fraud_own


def test_own_exclusion_is_per_class(result, world, monkeypatch):
    assert own_per_class(result)
    targets = {r: t[0] for p in v32.EPOCH_PROFILES.values() for r, t in p["faultRegimes"].items()}

    def global_own(f, target, path, entry):          # planted: a sensor on ANY class's target is own everywhere
        own = (entry if f["ch"] == "ledger" else f["svc"]) in set(targets.values())
        return True, own
    monkeypatch.setattr(v32.dt, "scored", global_own)
    assert not own_per_class(_run(world))


def test_ledger_fires_on_any_route(tmp_path):
    """Only the checkout route fails in the fraud cell: the ledger E still catches it (a route other than the first)."""
    camp = offpath_campaign(tmp_path / "e", only_checkout_fails=True)
    q = quiet(camp, tmp_path / "q")
    R = v32.run32([camp, q], system="otel", reference=False)
    with v24.use_system("otel"):
        v31.finish(R)
    f = next(e for e in R["results"]["primary"]["eps"] if e["regime"] == FRAUD)
    led = [x for x in f["fires"] if x["family"] == "E" and x["rule"] == "failed"]
    assert {x["tok"] for x in led} == {R_CHK}, led               # the `failed` rule of the checkout route, only
    assert min(x["ttd"] for x in led) > 0 and not any(x["bc"] for x in led)     # off-path: no by-construction flag


def test_exposure_is_counted_per_route(result):
    ex = result["exposure"]
    assert ex["perRoute"]["routes"] == sorted(ROUTES)
    for cell, v in ex["episodes"].items():
        per = v["requestsStartedInWindowPerRoute"]
        assert set(per) == set(ROUTES) and sum(per.values()) == v["requestsStartedInWindow"], (cell, per)
    assert any(v["requestsStartedInWindowPerRoute"][R_CHK] > 0 for v in ex["episodes"].values())
    # a route's services are those with a span in the traces of that route's requests (the fixture's one trace shape)
    assert all(set(v) == {"frontendproxy", "frontend", "productcatalogservice"}
               for v in ex["perRoute"]["servicesByRoute"].values())


def test_json_and_markdown_carry_the_v32_block(world, tmp_path):
    out = tmp_path / "ro"
    assert v32.main([str(world["camp"]), str(world["quiet"]), "--system", "otel", "--out", str(out)]) == 0
    J = json.loads((out / v32.OUT_JSON).read_text())
    md = (out / v32.OUT_MD).read_text()
    assert J["version"] == "3.2" and J["scriptSha256"] == v32._sha(v32.__file__)
    assert J["v31ScriptSha256"] == v31._sha(v31.__file__) and J["v32"]["ledgerRoutes"] == sorted(ROUTES)
    assert J["v32"]["epochsAdmittedExplicitly"] == v32.new_epochs()
    assert J["v32"]["parametersV32Sha256"] == v32._sha(v32.PARAMETERS_V32)
    assert "## v3.2 additions (campaign E)" in md
    # the off-path classes are in v3.1's own tables too (the context is entered around build_json / render)
    cells_rows = [l for l in md.splitlines() if l.startswith("|") and "fraud-pause" in l and "valid/found" not in l]
    assert len(cells_rows) >= 3 and any("accounting-pause" in l for l in md.splitlines() if l.startswith("|"))
    assert all(e["studyEpoch"] == EPOCH_E for e in J["episodes"])
    assert J["absentGap"] and sum(v["stoppingEpisodesAbsentBeforeFirstFailed"][1] for v in J["absentGap"].values()) >= 3
    assert "edgesObservedNotDeclared" in J["v32"]
    with pytest.raises(SystemExit):
        v32.main([str(world["camp"]), "--system", "otel", "--out", str(out)])


# ----------------------------------------------------------------------------- 6.1 / 6.2: block selection, outcome-blind

def test_block_selection_reads_receipts_only(tmp_path):
    camp = offpath_campaign(tmp_path / "c")
    excluded = t22._cell_dir(camp, ACCT)                      # block 3
    (excluded / "request-ledger.json").write_text("{ not json")      # would stop the run if it were read
    unselected = cells_of([camp])                              # read whole, the broken ledger makes it not scored
    assert not _by_any(unselected, ACCT)["valid"]
    cells = cells_of([camp], blocks={1, 2})
    regimes = {c["regime"] for c in cells}
    assert ACCT not in regimes and FRAUD in regimes and t22.OT_NF in regimes
    st_blocks = {c["block"] for c in cells}
    assert st_blocks == {1, 2}


def test_block_selection_is_recorded(world, tmp_path):
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2], "test": [3]}))
    R = _run(world, blocks={1, 2}, split=split)
    b = R["v32"]["blockSelection"]
    assert b["blocks"] == [1, 2] and b["excludedCount"] == 1 and b["excluded" "Cells"][0]["block"] == 3
    assert b["splitSha256"] == hashlib.sha256(split.read_bytes()).hexdigest()
    assert ACCT not in {e["regime"] for e in R["results"]["primary"]["eps"]}


def test_two_new_epochs_in_one_run_are_refused(tmp_path):
    a = offpath_campaign(tmp_path / "a", epoch=PILOT)
    b = offpath_campaign(tmp_path / "b", epoch=EPOCH_E)
    with pytest.raises(SystemExit, match="different v3.2 epochs"):
        cells_of([a, b])


def test_legacy_epochs_are_read_as_before(tmp_path):
    """Sweep cells (v2.4's epochs, single-route ledger) read under v3.2 exactly as under v3.1."""
    with v24.use_system("otel"):
        old = v31.find_and_load3([t22.OT_CAMP])[1]
    new = cells_of([t22.OT_CAMP])
    strip = lambda cs: [{k: v for k, v in c.items() if k not in ("ledger", "_c")} for c in cs]
    assert [c["cell"] for c in old] == [c["cell"] for c in new]
    assert all(a["valid"] == b["valid"] and a.get("onset") == b.get("onset") and a["ledger"] == b["ledger"]
               for a, b in zip(old, new))


# ----------------------------------------------------------------------------- v3.1 is untouched, registry is scanned

def test_v31_and_v24_are_byte_identical_to_the_frozen_files():
    assert v31._sha(v31.__file__) == "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd"
    assert v31._sha(v24.__file__) == "075c43e5870170c8b59cdbe1a970b56dc03920d67514027b9a95e5de38d962e9"
    # the parameters digest after decision 92
    assert v31._sha(v31.PARAMETERS_V3) == "212830bec3e6669bc211d5cffa48d61fa3bf0f6d4dd5ceaf79d3e2bcc7c4d000"


def test_rebinding_is_restored_on_exit():
    before = (v24.FAULT_TARGETS, v32._STATE.get("read"), v24.FAULT_REGIMES, v24.RATES, v24.otel_ledger, v24._read_json, v24.exposure, v31.find_and_load3,
              v31.STUDY_EPOCHS_B, v31.eval_episode3, v24.make_ctx, v24.v1.path_of, v24.pause_regime)
    with v24.use_system("otel"), v32.v32_context("otel", {50.0}, {1}):
        assert 50.0 in v24.RATES and v24.otel_ledger is not before[4]
    with pytest.raises(RuntimeError):
        with v24.use_system("otel"), v32.v32_context("otel"):
            raise RuntimeError("x")
    after = (v24.FAULT_TARGETS, v32._STATE.get("read"), v24.FAULT_REGIMES, v24.RATES, v24.otel_ledger, v24._read_json, v24.exposure, v31.find_and_load3,
             v31.STUDY_EPOCHS_B, v31.eval_episode3, v24.make_ctx, v24.v1.path_of, v24.pause_regime)
    assert all(a is b for a, b in zip(before, after))


def test_registry_entries_have_origins_and_every_used_one_exists():
    for n, p in v32.REGISTRY32.items():
        assert p["origin_ref"] and p["origin_type"] in ("decision", "literature", "measured", "upstream",
                                                       "engineering default", "unknown"), n
    assert v32.PARAMS_USED32 <= set(v32.REGISTRY32)
    rules = v32.REGISTRY32["V32_PASS_RULE"]["value"]                   # decision 99: per off-path class, >= 2 episodes
    assert [r["class"] for r in rules] == [FRAUD, ACCT] and all(
        r["minImprovedEpisodes"] == 2 and r["minEpisodes"] == 2 and r["minGain"] is None
        and r["set"] == "frontier (effort<=any, runtime<=any) @6/T_r" for r in rules)      # decision 112 (110: @3/T_r)
    rec = v32.REGISTRY32["V32_RECURRENCE_RULE"]                          # decision 112
    assert rec["value"] == {"minEpisodesPerClass": 2} and rec["origin_type"] == "decision" and rec["status"] == "active"
    assert "AMENDED by decision 112" in v32.REGISTRY32["V32_PASS_RULE"]["origin_ref"] and "decision 110" in (
        v32.REGISTRY32["V32_PASS_RULE"]["origin_ref"])
    assert "evaluated in every training fold" in v32.REGISTRY32["V32_PASS_RULE"]["origin_ref"]   # F6 wording
    assert "zero-alarm sensor costs 2.996/T_r" not in v32.REGISTRY32["V32_PASS_RULE"]["origin_ref"]
    assert v32.REGISTRY32["V32_E_SPLIT"]["value"] == {"train": [1, 2, 3], "test": [4, 5]}    # decision 100


# ----------------------------------------------------------------------------- planted defects

def _fraud_eps(R):
    return [e for e in R["results"]["primary"]["eps"] if e["regime"] == FRAUD]


def chk_admit(tmp_path, world):
    cells = cells_of([offpath_campaign(tmp_path / "ca")])
    return bool(cells) and all(c["valid"] for c in cells)


def chk_shape(tmp_path, world):
    camp = offpath_campaign(tmp_path / "cs")
    legacy = json.loads((t22.OT_CAMP / "runs" / "calibration" / "r1-b01-06-full" / "request-ledger.json").read_text())
    (t22._cell_dir(camp, t22.OT_NF) / "request-ledger.json").write_text(json.dumps(legacy))
    try:
        cells_of([camp])
    except v24.UnknownSchema:
        return True
    return False


def chk_routes(tmp_path, world):
    f = _by(cells_of([offpath_campaign(tmp_path / "cr")]), FRAUD)
    return {r.route for r in f["ledger"]} == set(ROUTES)


def chk_blocks(tmp_path, world):
    return ACCT not in {c["regime"] for c in cells_of([offpath_campaign(tmp_path / "cb")], blocks={1})}


def chk_one_epoch(tmp_path, world):
    try:
        cells_of([offpath_campaign(tmp_path / "a", epoch=PILOT), offpath_campaign(tmp_path / "b", epoch=EPOCH_E)])
    except SystemExit:
        return True
    return False


def chk_p1p2(tmp_path, world):
    try:
        R = _run(world)
    except AssertionError:
        return False
    rows = R["predictions"]["P1"]["perEpisode"]
    return bool(rows) and all("frontend-pause" in x["cell"] for x in rows)          # P1 is the request-path pause's


def chk_path(tmp_path, world):
    return set(_fraud_eps(_run(world))[0]["affectedPath"]) == {"frauddetectionservice", "kafka"}


def chk_edges(tmp_path, world):
    e = next(e for e in _run(world)["results"]["primary"]["eps"] if e["regime"] == t22.OT_PAUSE)
    return "adservice" in e["affectedPath"]


def chk_anyroute(tmp_path, world):
    camp = offpath_campaign(tmp_path / "ce", only_checkout_fails=True)
    R = v32.run32([camp, quiet(camp, tmp_path / "qe")], system="otel", reference=False)
    return any(x["family"] == "E" and x["rule"] == "failed" and x["tok"] == R_CHK for x in _fraud_eps(R)[0]["fires"])


def chk_exposure(tmp_path, world):
    return "perRoute" in _run(world)["exposure"]


def chk_new_alone(tmp_path, world):
    """Legacy FAULT cells beside a v3.2 epoch are refused; legacy no-fault cells (quiet runs) may be pooled."""
    camp = offpath_campaign(tmp_path / "cn")
    try:
        cells_of([camp, t22.OT_CAMP])
    except SystemExit:
        refused = True
    else:
        refused = False
    legacy_quiet = t22._quiet_campaign(t22.OT_CAMP, t22.OT_NF, tmp_path / "lq", system="otel")
    cells_of([camp, legacy_quiet])                                       # pooled, no exception
    return refused


def chk_validation_selected(tmp_path, world):
    camp = offpath_campaign(tmp_path / "cv")
    val = offpath_campaign(tmp_path / "vv")
    R = v32.run32([camp, quiet(camp, tmp_path / "qv")], system="otel", reference=False, blocks={1},
                  validation_dirs=[val])
    ex = R["v32"]["blockSelection"]["excludedCells"]
    return {x["call"] for x in ex} == {1, 2} and len(ex) == 4


def chk_require_e(tmp_path, world):
    try:
        cells_of([t22.OT_CAMP], blocks={1})
    except SystemExit:
        return True
    return False


SPLIT = {"train": [1, 2], "test": [3]}


def _split_campaigns(tmp_path, tag):
    """E campaign (fraud block 2, accounting block 3 = the test block), its train quiet cells, and a quiet campaign of two
    block-3 no-fault cells, the second carrying a log template no training cell has."""
    camp = offpath_campaign(tmp_path / ("e" + tag))
    q = quiet(camp, tmp_path / ("q" + tag))
    qt = quiet(camp, tmp_path / ("t" + tag), copies=2)
    for rp in sorted((qt / "runs").rglob("receipt.json")):
        _edit(rp, lambda rc: rc["runKey"].__setitem__("block", 3))
    return camp, q, qt


def _cal(R):
    return json.dumps(v31.cal_json(R["cal"]["primary"]), sort_keys=True, default=str)


def chk_train_only(tmp_path, world):
    """Decision 102: the detectors calibrated with the test-block cells held out are the training readout's, bit for bit,
    and the held-out episode is still scored with them."""
    camp, q, qt = _split_campaigns(tmp_path, "a")
    v32.E_SPLIT = SPLIT
    try:
        Rt = v32.run32([camp, q], system="otel", reference=False, blocks={1, 2})
        Rf = v32.run32([camp, q, qt], system="otel", reference=False, blocks={1, 2, 3}, test_blocks={3})
    finally:
        v32.E_SPLIT = NO_SPLIT
    ef = {e["cell"]: e for e in Rf["results"]["primary"]["eps"]}
    held = [e for e in ef.values() if e["regime"] == ACCT]
    same = [(e["cell"], [(f["ch"], f["svc"], f["tok"], f["rule"], f["ttd"]) for f in e["fires"]])
            for e in Rt["results"]["primary"]["eps"]]
    again = [(c, [(f["ch"], f["svc"], f["tok"], f["rule"], f["ttd"]) for f in ef[c]["fires"]]) for c, _ in same]
    return (_cal(Rt) == _cal(Rf) and same == again and len(held) == 1 and held[0]["calibrated"]
            and all(c["heldOut"] for c in Rf["cells"] if c.get("block") == 3 and c["valid"]))


def chk_held_out_required(tmp_path, world):
    camp, q, qt = _split_campaigns(tmp_path, "b")
    v32.E_SPLIT = SPLIT
    try:
        cells_of([camp], blocks={1, 2, 3})
    except SystemExit:
        return True
    finally:
        v32.E_SPLIT = NO_SPLIT
    return False


def chk_depends(tmp_path, world):
    """Rows that wait on a predecessor are out of P1/P2 and in for detection: with every row of the pause cell marked
    dependent, P1 sees no ledger (observed None) while the ledger E still fires."""
    camp = offpath_campaign(tmp_path / "cd")
    d = t22._cell_dir(camp, t22.OT_PAUSE)
    _edit(d / "request-ledger.json", lambda led: [q.__setitem__("dependsOn", max(i - 1, 0))
                                                  for i, q in enumerate(led["requests"])] and None)
    R = v32.run32([camp, quiet(camp, tmp_path / "qd")], system="otel", reference=False)
    p1 = [x for x in R["predictions"]["P1"]["perEpisode"] if "frontend-pause" in x["cell"]]
    ep = next(e for e in R["results"]["primary"]["eps"] if e["regime"] == t22.OT_PAUSE)
    flagged = R["v32"]["dependsOnRows"]
    return (p1 and all(x["observed"] is None for x in p1) and any(f["family"] == "E" for f in ep["fires"])
            and sum(flagged.values()) == 180)


CHECKS = {"TRAIN_ONLY_CALIBRATION": chk_train_only, "HELD_OUT_REQUIRED": chk_held_out_required,
          "P1P2_EXCLUDE_DEPENDS": chk_depends, "NEW_EPOCH_ALONE": chk_new_alone, "VALIDATION_SELECTED": chk_validation_selected,
          "REQUIRE_E_FOR_BLOCKS": chk_require_e, "ADMIT_OFFPATH_EPOCHS": chk_admit, "EPOCH_SHAPE_CHECK": chk_shape, "MULTI_ROUTE_LEDGER": chk_routes,
          "BLOCK_SELECT": chk_blocks, "ONE_NEW_EPOCH": chk_one_epoch, "P1_P2_ONE_REGIME": chk_p1p2,
          "OFFPATH_PATHS": chk_path, "ROUTE_EDGES": chk_edges, "LEDGER_ANY_ROUTE": chk_anyroute,
          "PER_ROUTE_EXPOSURE": chk_exposure}


def _passes(chk, tmp_path, world):
    try:
        return bool(chk(tmp_path, world))
    except (v24.UnknownSchema, SystemExit, AssertionError, StopIteration, KeyError):
        return False


@pytest.mark.parametrize("flag", sorted(CHECKS))
def test_check_passes_and_fails_with_its_switch_off(flag, world, tmp_path, monkeypatch):
    """Each v3.2 switch has a check that passes, and fails (or stops) once the switch is planted off."""
    assert _passes(CHECKS[flag], tmp_path / "on", world), flag
    monkeypatch.setattr(v32, flag, False)
    assert not _passes(CHECKS[flag], tmp_path / "off", world), flag


def test_every_switch_has_a_check():
    switches = {k for k, v in vars(v32).items() if k.isupper() and isinstance(v, bool)}
    assert switches == set(CHECKS), switches ^ set(CHECKS)


def test_edges_reach_the_path_of_an_on_path_target(result):
    e = next(e for e in result["results"]["primary"]["eps"] if e["regime"] == t22.OT_PAUSE)
    assert {"adservice", "checkoutservice", "frontendproxy"} <= set(e["affectedPath"])
    # the asynchronous Kafka edges are not walked: the request path of a frontend pause has no consumer on it
    assert not {"kafka", "accountingservice", "frauddetectionservice"} & set(e["affectedPath"])
    assert v32.ASYNC_EDGES and not v32.ASYNC_EDGES & v32.SYNC_EDGES


def test_legacy_campaign_context_is_v31s(tmp_path):
    """A v3.2 read of legacy single-route cells builds v3.1's graph and paths (no declared edges applied)."""
    with v24.use_system("otel"):
        cells = v31.find_and_load3([t22.OT_CAMP])[1]
        base = v24.make_ctx([c for c in cells if c["valid"]])
        with v32.v32_context("otel"):
            mine = v24.make_ctx([c for c in cells if c["valid"]])
            assert v24.v1.path_of("frontend", mine) == _ORIG_PATH("frontend", base)
    assert mine["edges"] == base["edges"] and mine["onRoute"] == base["onRoute"]


def _ORIG_PATH(target, ctx):
    return v32._ORIG["path_of"](target, ctx)


# ----------------------------------------------------------------------------- the whole chain on the synthetic campaign

def test_reader_to_placement_to_scorer_chain(world, tmp_path, monkeypatch):
    """Reader (--blocks train) -> celf_v3_2 -> reader (all blocks) -> score_test_v3_2, on the synthetic E campaign: every
    stage accepts the previous stage's file and the split is carried through (blocks 1-2 train, block 3 test)."""
    import celf_v3_2 as c2
    import score_test_v3_2 as s2
    for mod in (v32, c2, s2):                                 # the registry split of this synthetic campaign
        monkeypatch.setattr(mod, "E_SPLIT", {"train": [1, 2], "test": [3]})
    monkeypatch.setattr(s2, "PINNED_PLACEMENTS", {})        # the unpinned branch; E's placement pin (40209da) binds real E only
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [1, 2], "test": [3]}))
    tr, full = tmp_path / "train", tmp_path / "full"
    base = [str(world["camp"]), str(world["quiet"]), "--system", "otel", "--split", str(split)]
    assert v32.main(base + ["--out", str(tr), "--blocks", "1", "2"]) == 0
    with pytest.raises(SystemExit, match="without --test-blocks"):          # decision 102: no unflagged test block
        v32.main(base + ["--out", str(tmp_path / "bad")])
    assert v32.main(base + ["--out", str(full), "--test-blocks", "3"]) == 0
    Jt = json.loads((tr / v32.OUT_JSON).read_text())
    assert Jt["v32"]["blockSelection"]["blocks"] == [1, 2] and Jt["v32"]["blockSelection"]["excludedCount"] == 1
    assert {e["block"] for e in Jt["episodes"]} <= {1, 2} and not any(e["heldOut"] for e in Jt["episodes"])
    Jf = json.loads((full / v32.OUT_JSON).read_text())
    assert Jf["v32"]["blockSelection"]["testBlocks"] == [3] and Jf["v32"]["heldOutCells"]
    assert [e["cell"] for e in Jf["episodes"] if e["heldOut"]] and all(e["block"] == 3 for e in Jf["episodes"] if e["heldOut"])
    assert Jf["calibration"] == Jt["calibration"]                         # detectors applied unchanged
    tiers = tmp_path / "tiers.json"
    tiers.write_text(json.dumps({"schemaVersion": 1, "system": "otel", "postureCatalogs": {"v3": {}, "current": {}},
                                 "postureCostEvidence": {"steps": {k: {"share_of_none_level": s} for k, s in (
                                     ("none_to_selected", 0.17), ("selected_to_async", 0.058), ("async_to_full", 0.06))}},
                                 "sensors": [{"id": "span:frontend:x", "effortTier": 0,
                                              "postures": ["none", "selected", "async", "full"],
                                              "postureCurrentCatalog": ["none", "selected", "async", "full"]}]}))
    pl = tmp_path / "placement.json"
    assert c2.main([str(tr / v32.OUT_JSON), "--tiers", str(tiers), "--tier-catalog", "postureCurrentCatalog", "--out",
                    str(pl), "--split", str(split), "--allow-unpinned"]) == 0
    P = json.loads(pl.read_text())
    assert P["split"]["trainBlocks"] == [1, 2] and P["rates"]
    for rk, r in P["rates"].items():
        assert "grid" in r or "note" in r
    # the unsplit readout is refused by the placement (decision 95)
    with pytest.raises(SystemExit, match="every block"):
        c2.main([str(full / v32.OUT_JSON), "--tiers", str(tiers), "--tier-catalog", "postureCurrentCatalog",
                 "--out", str(tmp_path / "p2.json"), "--split", str(split), "--allow-unpinned"])
    with pytest.raises(SystemExit, match="calls? for postureCurrentCatalog"):          # the epoch binds the catalog
        c2.main([str(tr / v32.OUT_JSON), "--tiers", str(tiers), "--tier-catalog", "postures",
                 "--out", str(tmp_path / "p3.json"), "--split", str(split), "--allow-unpinned"])
    out = tmp_path / "score.json"
    assert any("grid" in r for r in P["rates"].values()), {k: r.get("note") for k, r in P["rates"].items()}
    if True:
        assert s2.main([str(full / v32.OUT_JSON), "--placement", str(pl), "--training-readout", str(tr / v32.OUT_JSON),
                        "--test-blocks", "3", "--out", str(out), "--allow-unpinned"]) == 0
        res = json.loads(out.read_text())
        assert res["splitCheck"]["trainBlocks"] == [1, 2] and res["splitCheck"]["testBlocks"] == [3]


def test_split_arguments_are_bound_to_the_registry(monkeypatch):
    monkeypatch.setattr(v32, "E_SPLIT", {"train": [1, 2, 3], "test": [4, 5]})
    with pytest.raises(SystemExit, match="not the registry test blocks"):
        v32.check_split_args({1, 2, 3, 4, 5}, {4})
    with pytest.raises(SystemExit, match="outside the registry split"):
        v32.check_split_args({1, 6}, None)
    with pytest.raises(SystemExit, match="not among the blocks read"):
        v32.check_split_args({1, 2}, {4, 5})
    v32.check_split_args({1, 2, 3, 4, 5}, {4, 5})
    v32.check_split_args({1, 2, 3}, None)
    assert v32.REGISTRY32["V32_E_SPLIT"]["value"] == {"train": [1, 2, 3], "test": [4, 5]}   # decision 100


def test_held_out_leak_is_visible_in_the_calibration(tmp_path, monkeypatch):
    """The planted leak changes the calibration (the held-out cell's template becomes a known sensor)."""
    camp, q, qt = _split_campaigns(tmp_path, "c")
    monkeypatch.setattr(v32, "E_SPLIT", SPLIT)
    clean = v32.run32([camp, q, qt], system="otel", reference=False, blocks={1, 2, 3}, test_blocks={3})
    monkeypatch.setattr(v32, "TRAIN_ONLY_CALIBRATION", False)
    leak = v32.run32([camp, q, qt], system="otel", reference=False, blocks={1, 2, 3}, test_blocks={3})
    assert _cal(clean) != _cal(leak)


def _reference_cells_seen(tmp_path, monkeypatch, tag):
    """Run the reader with the v2.4 reference row ON and a held-out block; return what v2.4's reference fit was handed."""
    camp, q, qt = _split_campaigns(tmp_path, tag)
    monkeypatch.setattr(v32, "E_SPLIT", SPLIT)
    seen = {"op": [], "loco": []}
    orig_op, orig_loco = v32._ORIG["operating_point"], v32._ORIG["loco_fits"]

    def spy_op(cells, *a, **k):
        seen["op"].append([bool(c.get("heldOut")) for c in cells])
        return orig_op(cells, *a, **k)

    def spy_loco(cells):
        seen["loco"].append([bool(c.get("heldOut")) for c in cells])
        return orig_loco(cells)

    monkeypatch.setitem(v32._ORIG, "operating_point", spy_op)
    monkeypatch.setitem(v32._ORIG, "loco_fits", spy_loco)
    R = v32.run32([camp, q, qt], system="otel", reference=True, blocks={1, 2, 3}, test_blocks={3})
    return R, seen


def test_reference_fit_sees_no_held_out_cell(tmp_path, monkeypatch):
    """Review finding F2: v3's `_run` called v24.loco_fits / v24.operating_point on every cell, so the v2.4 reference row
    was fitted with the held-out test-block cells. The v3.2 context routes both through the train-only filter (cells of
    block 3 are held out here); the readout says so."""
    R, seen = _reference_cells_seen(tmp_path, monkeypatch, "r1")
    assert R["reference"] is not None and seen["op"] and seen["loco"]
    assert any(c.get("heldOut") for c in R["cells"])                         # the held-out cells exist ...
    assert not any(any(flags) for flags in seen["op"] + seen["loco"])         # ... and the reference never saw one
    assert "train-only" in R["v32"]["referenceFit"]


def test_reference_fit_leak_is_visible_when_the_filter_is_off(tmp_path, monkeypatch):
    """Planted: TRAIN_ONLY_CALIBRATION off hands the reference fit every cell, held-out ones included."""
    monkeypatch.setattr(v32, "TRAIN_ONLY_CALIBRATION", False)
    R, seen = _reference_cells_seen(tmp_path, monkeypatch, "r2")
    assert any(any(flags) for flags in seen["op"] + seen["loco"])
    assert "ALL cells" in R["v32"]["referenceFit"]
