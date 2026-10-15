"""Campaign C test scorer (research/placement/score_test_v3.py, protocol decisions 88 and 89): C-only episodes, frozen
sets scored as frozen, the absent-sensor rule, the decision-89 verdict, the inherited celf_v3 rules and the refusals.

Layer: unit + synthetic end-to-end. SYNTHETIC instances only: hand-built readout and placement dicts. No readout of any
SUT, no campaign C cell and no C readout is read. Every rule has a check that passes and a planted defect (MUTANTS: a
module-level switch flipped, in the scorer or in the frozen celf_v3 whose rules it inherits) under which one of its
checks fails (the pattern of tests/test_placement_v3.py).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "research" / "placement", ROOT / "research" / "detection-time"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import celf_v3 as cv  # noqa: E402
import score_test_v3 as sm  # noqa: E402

INF = math.inf
TOL = 1e-9
H = 60.0
CELF_SHA = "3823722125e9796e6716a830b01d12c69177c7ab6b0a0d7a5fa3984ab6205e97"
V3_SHA = "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd"
PAUSE, THR = "frontend-pause-effect", "productcatalog-cpu-throttle-effect"
GET = "span:frontend:GET"
LEDGER = "ledger:frontendproxy:/api/products/X"
CAMPS = ["tmp/sweep/retained", "tmp/b-faultview/retained", "tmp/c-faultview/retained"]
C = 2
TRAIN_SHA = "f" * 64
READER = {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in sm.READER_DIGESTS.items()}


# ----------------------------------------------------------------------------- synthetic builders

def fire(fam, sid, ttd, own=False, counts=True, bc=(), rule="spike"):
    return [fam, sid, rule, ttd, "up", own, True, counts, list(bc), None]


def ep(regime, block, ci, fires=(), rate=0.2, harness="B", target=None, calibrated=True):
    target = target or ("frontend" if regime == PAUSE else "productcatalogservice")
    return {"cell": "%s :: %s/r%g-b%02d" % (CAMPS[ci], regime, rate, block), "regime": regime, "rate": rate,
            "block": block, "campaignIndex": ci, "harness": harness, "target": target, "holdSeconds": H,
            "onset": {"mono": 100.0}, "calibrated": calibrated, "fires": [list(f) for f in fires]}


def sensor(fam="T", placeable=True, upper=1.0):
    return {"family": fam, "placeable": placeable, "appearOnly": False, "calibrated": ["spike"] if placeable else [],
            "dropped": [], "unarmed": [], "inert": [] if placeable else ["spike"], "exempt": [], "celfCost": upper,
            "honestUpperPerHour": upper}


def readout(episodes, sensors, system="otel", rates=(0.2,)):
    per = {}
    for r in rates:
        s = copy.deepcopy(sensors)
        s.setdefault(LEDGER, sensor("E", upper=None))
        per[cv.rate_key(r)] = {"hours": 1.05, "cells": 10, "sensors": s}
    return {"system": system, "scriptSha256": V3_SHA, **READER, "campaigns": list(CAMPS), "episodes": episodes,
            "validation": {"campaigns": ["tmp/c-full/retained"], "input": {"files": 3}},
            "provenance": {"input": {"files": 9, "sha256": "a" * 64}},
            "campaignsRead": [{"campaign": c, "found": 1, "valid": 1} for c in CAMPS],
            "calibration": {"primary": {"perRate": per}}}


def point(names, S, budget):
    return {"names": list(names), "set": list(S), "budget": budget,
            "pointKind": "named" if set(names) & set(sm.NAMED) else "data-derived"}


def arm_rate(sets, ground):
    """sets: {named budget: frozen set}; ground: the frozen training V_r."""
    budgets = {"0": 0.0, "3/T_r": 2.857142857142857, "6/h": 6.0, "inf": "inf"}
    return {"pareto": [point([n], sets[n], budgets[n]) for n in sm.NAMED if n in sets], "groundSet": list(ground),
            "comparators": {"ledger alone": {"sensors": []}, "full": {"sensors": "V_r (%d)" % len(ground)},
                            "selected": {"sensors": [GET], "outsideGroundSet": ["span:x:unplaced"],
                                         "label": "restriction estimate (decision 78)"},
                            "none": {"sensors": [], "outsideGroundSet": [],
                                     "label": "restriction estimate (decision 78)"}}}


def placement(system="otel", rates=("0.2",), sets=None, ground=(GET, "log:frontendproxy:aa"), modality=None):
    sets = sets or {"0": [], "3/T_r": ["log:frontendproxy:aa"], "6/h": [GET], "inf": [GET, "log:frontendproxy:aa"]}
    modality = modality or {"0": [], "3/T_r": [], "6/h": [GET], "inf": [GET]}
    arms = {"primary": {rk: arm_rate(sets, ground) for rk in rates},
            "modality-T (81a)": {rk: arm_rate(modality, ground) for rk in rates},
            "modality-T+L (81a)": {rk: arm_rate(sets, ground) for rk in rates}}
    return {"system": system, "version": "placement-v3.0", "arms": arms,
            "inputs": {"scriptSha256": CELF_SHA, "readoutSha256": TRAIN_SHA}}


def sha_of(P):
    return hashlib.sha256(json.dumps(P, sort_keys=True).encode()).hexdigest()


DEFAULT = object()


def run(J, P, ci=C, training=DEFAULT):
    """score() with the synthetic placement's digest pinned for its system (restored afterwards); the training readout
    is the synthetic one matching the placement unless given."""
    if training is DEFAULT:
        training = ({"campaigns": CAMPS[:2]}, TRAIN_SHA)
    old = dict(sm.PINNED_PLACEMENTS)
    try:
        sm.PINNED_PLACEMENTS[P["system"]] = sha_of(P)
        return sm.score(J, P, ci, sha_of(P), training)
    finally:
        sm.PINNED_PLACEMENTS.clear()
        sm.PINNED_PLACEMENTS.update(old)


def expected_D(rows):
    """Independent re-implementation: rows = [(class, ttd or INF)]; mean over classes of the class mean of min(t, H)."""
    by = {}
    for cls, t in rows:
        by.setdefault(cls, []).append(H if t == INF else min(t, H))
    return sum(sum(v) / len(v) for v in by.values()) / len(by)


def otel_instance(c_thr_set=(5.0, 5.0, INF), c_thr_led=(INF, INF, INF), c_pause_set=(INF, INF, INF),
                  c_pause_led=(30.0, INF, INF), n_thr=3, extra_sensors=None, extra_c_fires=None):
    """Training episodes (sweep ci 0, B ci 1) where span:frontend:GET fires at 1 s everywhere; C (ci 2) as given."""
    eps = []
    for ci, harness, block in ((0, "sweep", 11), (1, "B", 12)):     # blocks apart from C's, so keys never collide
        for cls in (PAUSE, THR):
            eps.append(ep(cls, block, ci, [fire("T", GET, 1.0), fire("E", LEDGER, 50.0, rule="absent")], harness=harness))
    for cls, st, lt, n in ((THR, c_thr_set, c_thr_led, n_thr), (PAUSE, c_pause_set, c_pause_led, 3)):
        for b in range(n):
            f = []
            if st[b] < INF:
                f.append(fire("T", GET, st[b]))
            if lt[b] < INF:
                f.append(fire("E", LEDGER, lt[b], rule="absent"))
            f += (extra_c_fires or {}).get((cls, b + 1), [])
            eps.append(ep(cls, b + 1, C, f))
    sensors = {GET: sensor("T"), "log:frontendproxy:aa": sensor("L")}
    sensors.update(extra_sensors or {})
    return readout(eps, sensors)


def r02(res):
    return res["rates"]["0.2"]


# ----------------------------------------------------------------------------- checks (True = holds)

def check_c_only(ctx):
    """Only C's six episodes are scored; D_C equals the independent formula; training's early fires never enter."""
    J = otel_instance()
    r = r02(run(J, placement()))
    s = r["sets"]["primary 6/h"]
    want_set = expected_D([(THR, 5.0), (THR, 5.0), (THR, INF), (PAUSE, 30.0), (PAUSE, INF), (PAUSE, INF)])
    want_led = expected_D([(THR, INF)] * 3 + [(PAUSE, 30.0), (PAUSE, INF), (PAUSE, INF)])
    return (r["episodesScored"] == 6 and all(x["campaignIndex"] == C for x in r["episodes"])
            and abs(s["D"] - want_set) < TOL and abs(s["DLedger"] - want_led) < TOL
            and abs(s["g"] - (want_led - want_set)) < TOL and r["classes"] == {PAUSE: 3, THR: 3}
            and r["episodesAtRateInReadout"] == 10)


def check_class_weights(ctx):
    """P(i) uniform over classes, then episodes (inherited): 2 throttle and 3 pause episodes of C."""
    J = otel_instance(c_thr_set=(5.0, INF, INF), n_thr=2)
    s = r02(run(J, placement()))["sets"]["primary 6/h"]
    want = expected_D([(THR, 5.0), (THR, INF), (PAUSE, 30.0), (PAUSE, INF), (PAUSE, INF)])
    return abs(s["D"] - want) < TOL


def check_campaign_by_index_not_tag(ctx):
    """C carries B's harness tag; selection is by campaignIndex. --campaign path resolves to the same index."""
    J = otel_instance()
    by_path = sm.campaign_index(J, path=CAMPS[C])
    r = r02(run(J, placement(), ci=by_path))
    return by_path == C and r["harnessTags"] == ["B"] and r["episodesScored"] == 6


def check_per_episode(ctx):
    J = otel_instance()
    r = r02(run(J, placement()))
    x = next(e for e in r["episodes"] if e["class"] == THR and e["block"] == 1)
    y = next(e for e in r["episodes"] if e["class"] == PAUSE and e["block"] == 1)
    s, led = x["sets"]["primary 6/h"], x["ledger"]
    return (s["ttd"] == 5.0 and s["penalised"] == 5.0 and s["improvesOnLedger"] and led["ttd"] is None
            and led["penalised"] == H and y["ledger"]["ttd"] == 30.0 and y["sets"]["primary 6/h"]["ttd"] == 30.0
            and not y["sets"]["primary 6/h"]["improvesOnLedger"] and x["episode"].startswith(CAMPS[C])
            and x["sets"]["ledger alone"]["penalised"] == H)


def check_frozen_reuse(ctx):
    """A cheaper sensor that catches everything in C would be chosen by a re-solve; the frozen set is scored instead
    and celf_v3.solve is never called."""
    better = "span:frontend:better"
    J = otel_instance(extra_sensors={better: sensor("T", upper=0.1)},
                      extra_c_fires={(c, b): [fire("T", better, 0.5)] for c in (PAUSE, THR) for b in (1, 2, 3)})
    J["system"] = "teastore"                 # outside decision 89's verdict, which refuses a non-frozen 6/h set
    P = placement(system="teastore")
    calls = []
    orig = cv.solve

    def spy(*a, **k):
        calls.append(1)
        return orig(*a, **k)

    cv.solve = spy
    try:
        r = r02(run(J, P))
    finally:
        cv.solve = orig
    sets = r["sets"]
    return (not calls and sets["primary 6/h"]["sensors"] == [GET] and sets["primary 3/T_r"]["sensors"] ==
            ["log:frontendproxy:aa"] and sets["primary inf"]["sensors"] == sorted([GET, "log:frontendproxy:aa"])
            and sets["modality T 6/h"]["sensors"] == [GET] and sets["full"]["size"] == 2
            and sets["selected"]["sensors"] == [GET] and sets["selected"]["outsideTrainingGroundSet"] == 1)


def check_absent(ctx):
    """A frozen member not placeable in C's readout (but with a recorded fire there) never fires and is listed; a
    member missing from C's sensor table is listed with its own reason."""
    gone, missing = "span:frontend:gone", "span:frontend:missing"
    J = otel_instance(extra_sensors={gone: sensor("T", placeable=False)},
                      extra_c_fires={(THR, 3): [fire("T", gone, 2.0)], (PAUSE, 2): [fire("T", gone, 2.0)]})
    J["system"] = "teastore"
    P = placement(system="teastore", sets={"0": [], "3/T_r": [gone, missing], "6/h": [GET],
                                           "inf": [GET, gone, missing]})
    r = r02(run(J, P))
    s, s3 = r["sets"]["primary inf"], r["sets"]["primary 3/T_r"]
    ab = s["absentFromCGroundSet"]
    return (ab is not None and ab["count"] == 2 and ab["sensors"][missing] ==
            "not in the C readout's sensor table at this rate" and ab["sensors"][gone].startswith("not placeable")
            and abs(s["D"] - r["sets"]["primary 6/h"]["D"]) < TOL          # gone never fires
            and abs(s3["D"] - s3["DLedger"]) < TOL and abs(s3["g"]) < TOL
            and s3["detectedEpisodes"] == r["sets"]["ledger alone"]["detectedEpisodes"])


def verdict_of(J):
    return r02(run(J, placement()))["sets"]["primary 6/h"]["verdict"]


def check_verdict_pass(ctx):
    v = verdict_of(otel_instance(c_thr_set=(5.0, 5.0, 5.0)))
    return (v["verdict"] == "PASS" and v["throttleEpisodesValid"] == 3 and v["throttleEpisodesImproved"] == 3
            and v["gPositive"] and v["gC"] > 0)


def check_verdict_pass_at_two(ctx):
    v = verdict_of(otel_instance(c_thr_set=(5.0, INF, 5.0)))
    return v["verdict"] == "PASS" and v["throttleEpisodesImproved"] == 2


def check_verdict_fail_sign(ctx):
    """The set catches nothing earlier than the ledger: g_C = 0, FAIL on the sign (and, implied, on the count)."""
    v = verdict_of(otel_instance(c_thr_set=(INF, INF, INF), c_pause_set=(INF, INF, INF)))
    return (v["verdict"] == "FAIL" and "g_C = 0 <= 0" in v["reason"] and v["gC"] == 0 and not v["gPositive"]
            and "improves 0 of 3" in v["reason"])


def check_verdict_fail_count(ctx):
    """g_C > 0 through the pause class and one throttle episode; the second throttle episode ties the ledger (not
    strictly earlier), the third is a miss for both: FAIL on the count."""
    v = verdict_of(otel_instance(c_thr_set=(5.0, 10.0, INF), c_thr_led=(INF, 10.0, INF),
                                 c_pause_set=(1.0, 2.0, INF), c_pause_led=(30.0, INF, INF)))
    return (v["verdict"] == "FAIL" and v["gPositive"] and v["throttleEpisodesImproved"] == 1
            and "improves 1 of 3" in v["reason"] and "<= 0" not in v["reason"])


def check_verdict_too_few(ctx):
    """Only 2 valid throttle episodes of C at r0.2 (a blocked cell is absent from the readout): `—` with the count."""
    v = verdict_of(otel_instance(c_thr_set=(5.0, 5.0, INF), n_thr=2))
    return (v["verdict"] == "—" and v["throttleEpisodesValid"] == 2 and "2 valid throttle" in v["reason"]
            and "decision 91" in v["reason"])


def check_verdict_absent(ctx):
    """Decision 90 (the review's probe tmp/score-review/probe_absent_verdict.py): GET not placeable in C's readout, or
    missing from its sensor table: `—`, the absence in the verdict and its reason, not a misattributed FAIL."""
    J = otel_instance(c_thr_set=(5.0, 5.0, 5.0))
    J["calibration"]["primary"]["perRate"]["0.2"]["sensors"][GET] = sensor("T", placeable=False)
    J2 = otel_instance(c_thr_set=(5.0, 5.0, 5.0))
    del J2["calibration"]["primary"]["perRate"]["0.2"]["sensors"][GET]
    v, v2 = verdict_of(J), verdict_of(J2)
    return (v["verdict"] == "—" and "decision 90" in v["reason"] and GET in v["reason"]
            and v["absentFromCGroundSet"][GET].startswith("not placeable") and "<= 0" not in v["reason"]
            and v2["verdict"] == "—" and v2["absentFromCGroundSet"][GET] ==
            "not in the C readout's sensor table at this rate" and "decision 90" in v2["reason"]
            and verdict_of(otel_instance(c_thr_set=(5.0, 5.0, 5.0)))["absentFromCGroundSet"] == {})


def check_training_required(ctx):
    J, P = otel_instance(), placement()
    try:
        run(J, P, training=None)
        return False
    except SystemExit as exc:
        if "no training readout" not in str(exc):
            return False
    d = ctx["tmp"]
    jp, pp = d / "tr-readout.json", d / "tr-placement.json"
    jp.write_text(json.dumps(J))
    pp.write_text(json.dumps(P))
    try:                                                   # the CLI: argparse refuses before anything is read
        sm.main([str(jp), "--placement", str(pp), "--campaign-index", "2", "--out", str(d / "tr-out.json")])
        return False
    except SystemExit as exc:
        return exc.code == 2 and not (d / "tr-out.json").exists()


def check_duplicates(ctx):
    J = otel_instance()
    dup = copy.deepcopy(next(e for e in J["episodes"] if e["campaignIndex"] == C and e["regime"] == THR))
    dup["cell"] += "-again"
    J["episodes"].append(dup)
    try:
        run(J, placement())
        return False
    except SystemExit as exc:
        return "twice within C" in str(exc)


def check_class_counts(ctx):
    r2 = r02(run(otel_instance(n_thr=2), placement()))
    r3 = r02(run(otel_instance(), placement()))
    return r2["classCountFlags"] == {THR: 2} and r3["classCountFlags"] == {} and r2["episodesScored"] == 5


def check_reader_digests(ctx):
    out = []
    for field in sm.READER_DIGESTS:
        J = otel_instance()
        J[field] = "0" * 64
        try:
            run(J, placement())
            out.append(False)
        except SystemExit as exc:
            out.append("refusing" in str(exc) and field in str(exc))
    return all(out) and len(out) == 3


def check_validation(ctx):
    J = otel_instance()
    res = run(J, placement())
    rec = res["readoutRecords"]
    Jn = otel_instance()
    Jn["validation"] = None
    try:
        run(Jn, placement())
        refused = False
    except SystemExit as exc:
        refused = "validation" in str(exc)
    return (refused and rec["validationCampaigns"] == ["tmp/c-full/retained"]
            and rec["provenanceInput"] == {"files": 9, "sha256": "a" * 64})


def check_verdict_scope(ctx):
    """No verdict at other rates, on other sets, or on other systems."""
    J = otel_instance(c_thr_set=(5.0, 5.0, 5.0))
    for e in list(J["episodes"]):
        e2 = copy.deepcopy(e)
        e2["rate"] = 1.0
        J["episodes"].append(e2)
    J["calibration"]["primary"]["perRate"]["1"] = copy.deepcopy(J["calibration"]["primary"]["perRate"]["0.2"])
    res = run(J, placement(rates=("0.2", "1")))
    on = [lab for rk, r in res["rates"].items() for lab, s in r["sets"].items() if isinstance(s["verdict"], dict)]
    Jt = copy.deepcopy(J)
    Jt["system"] = "teastore"
    rt = run(Jt, placement(system="teastore", rates=("0.2", "1")))
    on_t = [lab for r in rt["rates"].values() for lab, s in r["sets"].items() if isinstance(s["verdict"], dict)]
    return (on == ["primary 6/h"] and res["rates"]["1"]["sets"]["primary 6/h"]["verdict"] == sm.NO_VERDICT
            and not on_t and [r["episodesScored"] for r in res["rates"].values()] == [6, 6])


def check_verdict_refuses_other_set(ctx):
    J = otel_instance()
    P = placement(sets={"0": [], "3/T_r": [], "6/h": ["log:frontendproxy:aa"], "inf": ["log:frontendproxy:aa"]})
    try:
        run(J, P)
    except SystemExit as exc:
        return "decision 89" in str(exc)
    return False


def check_own(ctx):
    """Decisions 79/84: GET is on the pause class's target (own) and off it for throttle; per class only."""
    J = otel_instance(c_thr_set=(INF, INF, INF), c_pause_set=(INF, INF, INF),
                      extra_c_fires={(PAUSE, 1): [fire("T", GET, 3.0, own=True)], (THR, 1): [fire("T", GET, 4.0)]})
    r = r02(run(J, placement()))
    p = next(e for e in r["episodes"] if e["class"] == PAUSE and e["block"] == 1)["sets"]["primary 6/h"]
    t = next(e for e in r["episodes"] if e["class"] == THR and e["block"] == 1)["sets"]["primary 6/h"]
    return p["ttd"] == 30.0 and t["ttd"] == 4.0 and r["rules"]["own"] == "exclude"


def check_bc(ctx):
    """Decision 72 `e-only`: a sensor's by-construction fire is a miss; the ledger's counts."""
    J = otel_instance(c_thr_set=(INF, INF, INF), c_thr_led=(INF, INF, INF), c_pause_led=(INF, INF, INF),
                      extra_c_fires={(THR, 1): [fire("T", GET, 3.0, bc=["BC-downstream-absent"])],
                                     (THR, 2): [fire("E", LEDGER, 7.0, bc=["BC-downstream-absent"], rule="absent")]})
    r = r02(run(J, placement()))
    e1 = next(e for e in r["episodes"] if e["class"] == THR and e["block"] == 1)
    e2 = next(e for e in r["episodes"] if e["class"] == THR and e["block"] == 2)
    return (e1["sets"]["primary 6/h"]["ttd"] is None and e2["ledger"]["ttd"] == 7.0
            and e2["sets"]["primary 6/h"]["ttd"] == 7.0 and r["rules"]["bc"] == "e-only")


def check_far_dash(ctx):
    r = r02(run(otel_instance(), placement()))
    return all(s["freshFalseAlarms"].startswith("— (decision 88") for s in r["sets"].values())


def check_refusals(ctx):
    """Each bad input refused with `refusing`; the good one accepted."""
    J, P = otel_instance(), placement()
    out = []

    def refused(fn):
        try:
            fn()
        except SystemExit as exc:
            return "refusing" in str(exc)
        return False

    bad_j = copy.deepcopy(J)
    bad_j["scriptSha256"] = "0" * 64
    out.append(refused(lambda: run(bad_j, P)))
    out.append(refused(lambda: sm.score(J, P, C, "0" * 64, ({"campaigns": CAMPS[:2]}, TRAIN_SHA))))  # not pinned
    bad_p = copy.deepcopy(P)
    bad_p["inputs"]["scriptSha256"] = "1" * 64
    out.append(refused(lambda: run(J, bad_p)))                                    # placement not from frozen celf
    other = copy.deepcopy(P)
    other["system"] = "teastore"
    out.append(refused(lambda: run(J, other)))                                    # system mismatch
    old = sm.PINNED_CELF_SHA256
    try:
        sm.PINNED_CELF_SHA256 = "2" * 64
        out.append(refused(lambda: run(J, P)))                                    # celf_v3 digest
    finally:
        sm.PINNED_CELF_SHA256 = old
    out.append(refused(lambda: sm.campaign_index(J)))
    out.append(refused(lambda: sm.campaign_index(J, index=1, path=CAMPS[1])))
    out.append(refused(lambda: sm.campaign_index(J, path="tmp/nowhere")))
    out.append(refused(lambda: sm.campaign_index(J, index=3)))
    train = {"campaigns": CAMPS[:2]}
    out.append(refused(lambda: run(J, P, ci=1, training=(train, TRAIN_SHA))))     # scoring a training campaign
    out.append(refused(lambda: run(J, P, training=(train, "e" * 64))))            # not the placement's readout
    out.append(refused(lambda: run(J, P, training=({"campaigns": CAMPS[:1]}, TRAIN_SHA))))
    ok = run(J, P, training=(train, TRAIN_SHA))
    return all(out) and ok["trainingCheck"]["checked"] and len(out) == 12


def check_main(ctx):
    """End to end: JSON + markdown written, verdict beside the numbers; neither file is ever overwritten."""
    d = ctx["tmp"]
    J, P = otel_instance(c_thr_set=(5.0, 5.0, 5.0)), placement()
    jp, pp, tp = d / "readout.json", d / "placement.json", d / "training.json"
    jp.write_text(json.dumps(J))
    tp.write_text(json.dumps({"campaigns": CAMPS[:2]}))
    P["inputs"]["readoutSha256"] = hashlib.sha256(tp.read_bytes()).hexdigest()
    pp.write_text(json.dumps(P))
    out, out2 = d / "score" / "c-otel.json", d / "score" / "c-otel-2.json"
    base = [str(jp), "--placement", str(pp), "--campaign", CAMPS[C], "--training-readout", str(tp), "--out"]

    def refused(target):
        try:
            sm.main(base + [str(target)])
        except SystemExit as exc:
            return "existing path" in str(exc)
        return False

    old = dict(sm.PINNED_PLACEMENTS)
    try:
        sm.PINNED_PLACEMENTS["otel"] = hashlib.sha256(pp.read_bytes()).hexdigest()
        sm.main(base + [str(out)])
        before = (out.read_bytes(), out.with_suffix(".md").read_bytes())
        again = refused(out)                                   # the JSON exists
        out2.with_suffix(".md").write_text("keep")
        md_only = refused(out2)                                # only the markdown exists
    finally:
        sm.PINNED_PLACEMENTS.clear()
        sm.PINNED_PLACEMENTS.update(old)
    res = json.loads(out.read_text())
    md = out.with_suffix(".md").read_text()
    v = res["rates"]["0.2"]["sets"]["primary 6/h"]["verdict"]
    return (v["verdict"] == "PASS" and "**PASS**" in md and "| primary 6/h |" in md and again and md_only
            and (out.read_bytes(), out.with_suffix(".md").read_bytes()) == before
            and out2.with_suffix(".md").read_text() == "keep" and not out2.exists()
            and res["trainingCheck"]["checked"] and res["campaign"]["index"] == C
            and res["inputs"]["placementSha256"] == hashlib.sha256(pp.read_bytes()).hexdigest())


CHECKS = {
    "c-only": check_c_only, "class-weights": check_class_weights, "campaign-by-index": check_campaign_by_index_not_tag, "per-episode": check_per_episode,
    "frozen-reuse": check_frozen_reuse, "absent": check_absent, "verdict-pass": check_verdict_pass,
    "verdict-pass-at-two": check_verdict_pass_at_two, "verdict-fail-sign": check_verdict_fail_sign,
    "verdict-fail-count": check_verdict_fail_count, "verdict-too-few": check_verdict_too_few,
    "verdict-scope": check_verdict_scope, "verdict-absent": check_verdict_absent,
    "training-required": check_training_required, "duplicates": check_duplicates, "class-counts": check_class_counts,
    "reader-digests": check_reader_digests, "validation": check_validation, "verdict-refuses-other-set": check_verdict_refuses_other_set,
    "own": check_own, "bc": check_bc, "far-dash": check_far_dash, "refusals": check_refusals, "main": check_main,
}

MUTANTS = {   # label: (module, switch, planted value, checks of which at least one must fail[, expected failure])
    "every episode at the rate scored, training included": (sm, "C_ONLY", False, ["c-only"]),
    "sets re-solved on the C readout": (sm, "FROZEN_SETS", False, ["frozen-reuse"]),
    "absent sensors' recorded fires count": (sm, "ABSENT_NEVER_FIRES", False, ["absent"]),
    "absent sensors not listed": (sm, "LIST_ABSENT", False, ["absent"]),
    "a tie with the ledger counts as an improvement": (sm, "STRICT_IMPROVEMENT", False, ["verdict-fail-count"]),
    "improvements counted over every class": (sm, "VERDICT_THROTTLE_ONLY", False, ["verdict-fail-count"]),
    "verdict with fewer than 3 valid throttle episodes": (sm, "VERDICT_NEEDS_VALID", False, ["verdict-too-few"]),
    "digests not enforced": (sm, "ENFORCE_PINS", False, ["refusals"]),
    "absent 6/h member scored as a miss, verdict given (90)": (sm, "VERDICT_ABSENT_UNTESTABLE", False,
                                                               ["verdict-absent"]),
    "training readout optional": (sm, "REQUIRE_TRAINING", False, ["training-required"]),
    "an episode key twice within C scored": (sm, "REFUSE_DUPLICATE_EPISODES", False, ["duplicates"]),
    "class counts not recorded": (sm, "FLAG_CLASS_COUNTS", False, ["class-counts"]),
    "reader digests not compared": (sm, "CHECK_READER_DIGESTS", False, ["reader-digests"]),
    "readout without validation accepted": (sm, "REQUIRE_VALIDATION", False, ["validation"]),
    "a sensor's BC fire counts (72)": (sm, "SCORE_BC", "count-all", ["bc"]),
    "own fires count (79/84)": (sm, "SCORE_OWN", "include", ["own"]),
    # the frozen celf_v3 rules the scorer inherits (its switches; celf_v3.py itself is never edited)
    "inherited: a miss charged 0 (celf_v3 MISS_AT_HOLD)": (cv, "MISS_AT_HOLD", False, ["c-only"]),
    "inherited: P(i) uniform over episodes (celf_v3 CLASS_WEIGHTS)": (cv, "CLASS_WEIGHTS", False, ["class-weights"]),
    "inherited: a sensor's BC fire counts (celf_v3 BC_SENSOR_MISS)": (cv, "BC_SENSOR_MISS", False, ["bc"]),
    "inherited: the ledger's BC fire a miss (celf_v3 BC_LEDGER_COUNTS)": (cv, "BC_LEDGER_COUNTS", False, ["bc"]),
    "inherited: own fires count (celf_v3 OWN_OUT)": (cv, "OWN_OUT", False, ["own"]),
    "inherited: rates pooled (celf_v3 PER_RATE)": (cv, "PER_RATE", False, ["verdict-scope"]),
}


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    return {"tmp": tmp_path_factory.mktemp("score_test_v3")}


def _outcome(name, ctx):
    try:
        return bool(CHECKS[name](ctx))
    except (Exception, SystemExit) as exc:
        return exc


def test_checks_pass(ctx):
    res = {n: _outcome(n, ctx) for n in CHECKS}
    assert all(v is True for v in res.values()), {k: v for k, v in res.items() if v is not True}


@pytest.mark.parametrize("label", sorted(MUTANTS))
def test_planted_defect_is_caught(label, ctx, monkeypatch, tmp_path):
    mod, attr, val, names, *expect = MUTANTS[label]
    assert hasattr(mod, attr)
    monkeypatch.setattr(mod, attr, val)
    c = dict(ctx, tmp=tmp_path)
    got = [_outcome(n, c) for n in names]
    if expect:
        etype, text = expect[0]
        assert any(isinstance(g, etype) and text in str(g) for g in got), (label, got)
    else:
        assert any(g is False for g in got), (label, got)


def test_every_switch_has_a_mutant():
    assert {m[1] for m in MUTANTS.values() if m[0] is sm} == set(sm.SWITCHES)


def test_frozen_code_and_pins():
    assert hashlib.sha256((ROOT / "research" / "placement" / "celf_v3.py").read_bytes()).hexdigest() == CELF_SHA
    assert sm.PINNED_CELF_SHA256 == CELF_SHA and sm.PINNED_V3_SHA256 == V3_SHA == cv.PINNED_V3_SHA256
    assert sm.check_frozen_code() == CELF_SHA
    assert set(sm.PINNED_PLACEMENTS) >= {"otel", "teastore"}
    for sut, want in sm.PINNED_PLACEMENTS.items():      # the pins equal the frozen files (378e598)
        f = ROOT / "research" / "placement" / "out" / ("%s-primary" % sut) / "placement.json"
        assert hashlib.sha256(f.read_bytes()).hexdigest() == want, sut
    assert sm.VERDICT["frozenSet"] == ["span:frontend:GET"] and sm.VERDICT["rate"] == "0.2"
    text = (ROOT / "research" / "placement" / "score_test_v3.py").read_text()
    assert "import obsplacement" not in text and "from obsplacement" not in text
