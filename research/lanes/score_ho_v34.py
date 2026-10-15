#!/usr/bin/env python3
"""Score the Hotel off-path predictions HO-* of research/protocol/PREDICTIONS_OVERNIGHT_20261014.json on ONE v3.4 readout.

    uv run python research/lanes/score_ho_v34.py <sweep_analysis_v3_4.json of the hotel-offpath-v1 fetch> --out <new dir>

Written and tested BEFORE any cell of hotel-offpath-v1 was read (FREEZE_V34_20261015.md), so that the rules are applied by code and
not by a reader who has seen the numbers. It reads the readout JSON only (no raw cell), edits no existing file, refuses to write
into an existing directory, and refuses a readout that is not a v3.4 readout of the off-path epoch alone. Scope of every row:
**instance** (one SUT, one host, one campaign). Each rule is the one the prediction's own `rule` field declares; the
sha256 of each rule string is pinned below, so an edited prediction stops this script instead of being scored under old code.
`—` is a prediction whose precondition is absent (an id, a rate, a lane): never a miss, never 0.

Lane times are pooled_lanes.episode_lanes' (frozen post-hoc script, imported): seconds after the pre-command onset stamp, the
earliest USABLE fire (counts true) in the counted field (no BC flag), the by-construction field (BC flag) and either field
(`ttdAny`); the ledger lane is the E-family fires of celf_v3.E_RULES, own fires dropped. Ontology rows use compare.lane_cmp's rule
(a lane is detected if >= 1 episode fires in any field; a lane not collected is not comparable).

JUDGEMENTS made here, before reading (each could be wrong; each is recorded in the output):
* HO-L1's bands apply: candidate_offpath.py reads candidate_sweep.py as a library and takes route, warm-up, measurement, hold,
  client timeout, onset rule and the search pause from it (Hotel harness 9ad0b98, docstring); the declaration says the search pause
  is "the sweep's mechanism, unchanged". A band is checked only for a rate the readout has AND the prediction lists (1 and 10);
  0.05 and 0.2 are not in this run, so `—`.
* HO-C is true by construction of the lane rules (Hotel declares no coordinator and no lag lane, V34_LANE_RULES): a `hit` here is the
  rule's, labelled so; it would turn into a miss only if a readout carried a coordinator or lag fire, which v3.4's rules cannot
  produce. It is not a measurement of "no service observes consul".
* HO-L2: `—` iff no consul sensor was collected in any consul-pause episode; MISS iff an own-lane fire of a consul sensor is
  reported (either field); collected sensors that stayed silent are neither (the rule does not cover them): reported as
  `not covered`.
* HO-D1: medians over the episodes that detected; a lane with no detection at a rate makes that lane `—` and the row `—`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (HERE, REPO / "research" / "placement", REPO / "research"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import importlib.util  # noqa: E402
import pooled_lanes as pl  # noqa: E402  frozen post-hoc script; imported, never edited

_spec = importlib.util.spec_from_file_location("ontology_compare", REPO / "research" / "ontology" / "compare.py")
ont = importlib.util.module_from_spec(_spec)           # research/ontology/compare.py (lane_cmp); loaded by path, never edited
_spec.loader.exec_module(ont)

DASH = "—"
EPOCH = "hotel-offpath-v1"
PREDICTIONS = REPO / "research" / "protocol" / "PREDICTIONS_OVERNIGHT_20261014.json"
CP, SP = "consul-pause-effect", "search-pause-effect"
# HO-L1: pooled sweep r3 min-max bands of the median earliest own fire, per rate (req/s): the prediction's own numbers.
BANDS = {1.0: (0.70, 1.54), 10.0: (0.21, 0.28)}
DECLARED_EPISODES = 5           # episodes per (regime, rate): the descriptor's episodesPerRegimeAndRate
RATIO = 0.5                     # HO-D1: median(higher rate) <= 0.5 x median(lower rate)
GAP = 4.0                       # HO-D1: for rates at least 4x apart
RULE_SHA256 = {                 # sha256 of each prediction's `rule` string at the committed predictions (8b89d43)
    "HO-ONT-search": "ac83a9cfe8f74059", "HO-ONT-consul": "79e34ecae30d5807", "HO-C": "514639161182b152",
    "HO-L1": "615c774dffdabfac", "HO-L2": "95528fdd8abf6069", "HO-D1": "fe1a72e2ac194d76", "HO-D2": "fb4c5146487742e0"}

# Switches flipped only by tests/test_score_ho_v34.py (planted defects).
CHECK_RULE_PINS = True          # an edited prediction rule stops the script (False: scored under the old code)
EITHER_FIELD = True             # HO-L1/HO-D1/HO-L2 use the earliest fire in either field (False: counted field only)


def sha16(s):
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def load_predictions(path=PREDICTIONS):
    doc = json.loads(Path(path).read_text())
    ho = {p["id"]: p for p in doc["predictions"] if p["id"].startswith("HO-")}
    if CHECK_RULE_PINS:
        for pid, want in RULE_SHA256.items():
            if pid not in ho or sha16(ho[pid]["rule"]) != want:
                raise SystemExit("refusing: the rule of %s differs from the one this scorer was written for" % pid)
    return ho


def _time(lane, field="any"):
    """The lane's earliest fire time: either field (ttdAny) or, with the switch planted off, the counted field only."""
    if lane is None:
        return None
    return lane["ttdAny"] if (field == "any" and EITHER_FIELD) else lane["ttdCounted"]


def episode_records(J):
    """One record per fault episode of the readout: regime, rate, block, target, the lanes of pooled_lanes, and the own lane's
    number of collected sensors from the readout's lanes block (matched by cell)."""
    if J.get("version") != "3.4" or "v34" not in J:
        raise SystemExit("refusing: not a v3.4 readout (version %r)" % J.get("version"))
    if J["v34"].get("hotelOffPathEpochsRead") != [EPOCH]:
        raise SystemExit("refusing: the readout does not contain the epoch %s alone (%s)" % (
            EPOCH, J["v34"].get("hotelOffPathEpochsRead")))
    if J.get("system") != "hotel":
        raise SystemExit("refusing: system %r" % J.get("system"))
    blk = J["v33"]["lanes"]["regimes"]
    collected = {}
    coord_fire = []
    perrate = J["calibration"]["primary"]["perRate"]
    for regime, x in blk.items():
        for ep in x["episodes"]:
            n = ep["lanes"]["own"]["collectedSensors"]
            if n is None:
                raise SystemExit("refusing: the lanes block has no collectedSensors for the own lane of %s" % ep["cell"])
            collected[ep["cell"]] = n
            for lane in ("coordinator", "lag"):
                L = ep["lanes"][lane]
                if L.get("earliest") is not None or L.get("earliestByConstruction") is not None or (L.get("countedFires") or 0) > 0 \
                        or (L.get("byConstructionFires") or 0) > 0:
                    coord_fire.append((regime, ep["cell"], lane))
    recs = []
    for e in J["episodes"]:
        if e.get("studyEpoch") != EPOCH:
            continue
        lanes = pl.episode_lanes(e, "hotel", set(), set())
        sensors = (perrate.get(pl.cv.rate_key(e["rate"])) or {}).get("sensors") or {}
        armed = sorted(k for k, v in sensors.items() if k.split(":")[1:2] == [e["target"]] and v.get("placeable"))
        if e["cell"] not in collected:
            raise SystemExit("refusing: episode %s has no entry in the readout's lanes block" % e["cell"])
        recs.append({"armedOwn": armed, "regime": e["regime"], "rate": float(e["rate"]), "block": e["block"], "target": e["target"],
                     "cell": e["cell"], "lanes": lanes, "ownCollected": collected.get(e["cell"])})
    return recs, coord_fire


def _med(ts):
    ts = [t for t in ts if t is not None]
    return statistics.median(ts) if ts else None


def _rows(recs, regime, lane, field="any"):
    return [(r["rate"], _time(r["lanes"][lane], field)) for r in recs if r["regime"] == regime and r["lanes"][lane] is not None]


def score_C(recs, coord_fire, ho):
    fired = [x for x in coord_fire]
    v = "hit (by construction)" if not fired else "miss"
    return {"id": "HO-C", "verdict": v,
            "evidence": {"coordinatorOrLagFiresInAnyEpisode": fired, "episodes": len(recs),
                         "coordinatorLaneInPooledLanes": "none (Hotel: structural)", "lagLane": "none"},
            "label": "true by construction of the lane rules (V34_LANE_RULES declares no coordinator or lag lane for Hotel); a hit "
                     "is the rule's, not a measurement that no service observes consul"}


def score_L1(recs, ho):
    es = [r for r in recs if r["regime"] == SP]
    rates = sorted({r["rate"] for r in es})
    per, ok, any_band = {}, True, False
    det_all = all(_time(r["lanes"]["own"], "any") is not None for r in es) if es else None
    for rt in rates:
        ts = [_time(r["lanes"]["own"], "any") for r in es if r["rate"] == rt]
        med = _med(ts)
        band = BANDS.get(rt)
        inside = None if (band is None or med is None) else (band[0] <= med <= band[1])
        per["%g" % rt] = {"episodes": len(ts), "detected": sum(t is not None for t in ts), "median": med,
                          "band": list(band) if band else None, "inside": inside}
        if band is not None:
            any_band = True
            ok = ok and bool(inside)
    if not es:
        return {"id": "HO-L1", "verdict": DASH, "evidence": {"reason": "no search-pause episode"}}
    verdict = "hit" if (det_all and ok) else "miss"
    if not any_band:
        verdict = "hit (detection clause only)" if det_all else "miss"
    return {"id": "HO-L1", "verdict": verdict,
            "evidence": {"detectedInEveryEpisode": det_all, "perRate": per,
                         "ratesWithoutBand": [r for r in rates if r not in BANDS]},
            "label": "bands apply because candidate_offpath.py reads the sweep's workload and pause form (judgement recorded in the docstring)"}


def score_L2(recs, ho):
    es = [r for r in recs if r["regime"] == CP]
    if not es:
        return {"id": "HO-L2", "verdict": DASH, "evidence": {"reason": "no consul-pause episode"}}
    armed = sorted({k for r in es for k in r["armedOwn"]})
    coll = [r["ownCollected"] for r in es]
    anyt = [_time(r["lanes"]["own"], "any") for r in es]
    cnt = [r["lanes"]["own"]["ttdCounted"] if r["lanes"]["own"] else None for r in es]
    ids = sorted({i for r in es for i in (r["lanes"]["own"] or {}).get("ids", [])})
    fired = any(t is not None for t in anyt)
    if fired:
        v = ("miss (counted field)" if any(t is not None for t in cnt)
             else "miss (by-construction field only; counted field silent: the fire is the paused target's own idle signal)")
    elif not armed:
        v = "— (no armed consul own sensor)"
    else:
        v = "not covered (armed consul own sensors, none fired: neither `—` nor a fire)"
    return {"id": "HO-L2", "verdict": v,
            "evidence": {"episodes": len(es), "armedOwnSensors": armed, "ownCollectedSensorsPerEpisode": coll,
                         "episodesWithOwnFire": sum(t is not None for t in anyt),
                         "episodesWithCountedOwnFire": sum(t is not None for t in cnt), "ownFiringIds": ids,
                         "earliestOwnFire": min([t for t in anyt if t is not None], default=None)}}


def score_D1(recs, ho):
    es = [r for r in recs if r["regime"] == SP]
    rates = sorted({r["rate"] for r in es})
    pairs = [(lo, hi) for lo in rates for hi in rates if hi / lo >= GAP]
    if not pairs:
        return {"id": "HO-D1", "verdict": DASH, "evidence": {"reason": "no two search-pause rates >= %gx apart" % GAP}}
    out, verdicts = {}, []
    for name, lane in (("own", "own"), ("ledger", "ledger")):
        rows = []
        for lo, hi in pairs:
            m = {rt: _med([_time(r["lanes"][lane], "any") for r in es if r["rate"] == rt]) for rt in (lo, hi)}
            if m[lo] is None or m[hi] is None:
                rows.append({"pair": [lo, hi], "medians": m, "ratio": None, "holds": None})
                verdicts.append(None)
            else:
                ratio = m[hi] / m[lo] if m[lo] else None
                holds = m[hi] <= RATIO * m[lo]
                rows.append({"pair": [lo, hi], "medians": m, "ratio": ratio, "holds": holds})
                verdicts.append(holds)
        out[name] = rows
    v = "miss" if any(x is False for x in verdicts) else (DASH if any(x is None for x in verdicts) else "hit")
    return {"id": "HO-D1", "verdict": v, "evidence": out}


def score_D2(recs, ho):
    return {"id": "HO-D2", "verdict": DASH, "evidence": {"reason": "the rule is `—`: no prediction"}}


def _measured(recs, regime, lane):
    es = [r for r in recs if r["regime"] == regime and r["lanes"][lane] is not None]
    if not es:
        return None
    ts = [r["lanes"][lane]["ttdAny"] for r in es]
    ct = [r["lanes"][lane]["ttdCounted"] for r in es]
    det = [t for t in ts if t is not None]
    return {"any": len(det), "counted": sum(t is not None for t in ct), "episodes": len(es),
            "range": [round(min(det), 2), round(max(det), 2)] if det else None}


def score_ontology(recs, ho, pid, regime):
    p = ho[pid]
    a = p["answers"]
    own = _measured(recs, regime, "own")
    if own is not None:
        collected = [r["ownCollected"] for r in recs if r["regime"] == regime]
        if not any(collected):
            own = None                                 # the lane was not collected: not comparable
    ledger = _measured(recs, regime, "ledger")
    items = {"lane:own": ont.lane_cmp(a["ownLane"], own),
             "lane:coordinator": ont.lane_cmp(a["coordinatorLane"], None),
             "lane:lag": ont.lane_cmp(a["lagLane"], None),
             "CQ-C1 class": "not comparable", "CQ-L2 window": "not comparable",
             "CQ-B1 entry reached (proxy: ledger lane)": ont.lane_cmp(a["CQ-B1 entry service reached"], ledger)}
    return {"id": pid, "verdict": "per item", "items": items,
            "evidence": {"measuredOwn": own, "measuredLedger": ledger, "predicted": {k: a[k] for k in (
                "ownLane", "coordinatorLane", "lagLane", "CQ-C1 class", "CQ-B1 entry service reached")}},
            "label": "compare.py's rules (a lane is detected if any episode fires in any field); Hotel has no coordinator, so the "
                     "coordinator-based items are not comparable; a lane:own `disagree` whose measuredOwn.counted is 0 rests on "
                     "by-construction fires only (the paused target's own idle signal), not on a counted detection"}


def score(J, ho):
    recs, coord_fire = episode_records(J)
    rows = [score_ontology(recs, ho, "HO-ONT-search", SP), score_ontology(recs, ho, "HO-ONT-consul", CP),
            score_C(recs, coord_fire, ho), score_L1(recs, ho), score_L2(recs, ho), score_D1(recs, ho), score_D2(recs, ho)]
    return {"label": "POST-READING SCORE of preregistered predictions (committed 8b89d43 before any hotel-offpath cell was read); "
                     "rules applied by code (score_ho_v34.py), rule pins checked", "scope": "instance",
            "readoutScriptSha256": J.get("scriptSha256"), "episodes": len(recs),
            "episodesByRegimeRate": _count(recs), "episodesDeclaredPerRegimeAndRate": DECLARED_EPISODES,
            "shortfall": {"%s r%g" % (g, r): DECLARED_EPISODES - recs_n
                          for (g, r), recs_n in _count_keys(recs, J).items() if recs_n < DECLARED_EPISODES},
            "rows": rows}


def _count_keys(recs, J):
    """(regime, rate) -> episodes present, for every declared (regime, rate): an absent pair is 0, not missing."""
    out = {(g, float(r)): 0 for g in (CP, SP) for r in (1.0, 10.0)}
    for r in recs:
        out[(r["regime"], r["rate"])] = out.get((r["regime"], r["rate"]), 0) + 1
    return out


def _count(recs):
    out = {}
    for r in recs:
        out["%s r%g" % (r["regime"], r["rate"])] = out.get("%s r%g" % (r["regime"], r["rate"]), 0) + 1
    return dict(sorted(out.items()))


def to_md(S):
    L = ["# Hotel off-path predictions HO-*, scored by score_ho_v34.py", "", "**%s.** Scope: instance." % S["label"], "",
         "Episodes: %d (%s). Declared %d per (regime, rate); shortfall: %s." % (
             S["episodes"], ", ".join("%s %d" % kv for kv in S["episodesByRegimeRate"].items()), S["episodesDeclaredPerRegimeAndRate"],
             ", ".join("%s %d short" % kv for kv in S["shortfall"].items()) or "none"), "",
         "| id | verdict | evidence |", "|---|---|---|"]
    for r in S["rows"]:
        ev = r["verdict"] if r["verdict"] != "per item" else "; ".join("%s: %s" % kv for kv in r["items"].items())
        L.append("| %s | %s | %s |" % (r["id"], r["verdict"] if r["verdict"] != "per item" else "per item", ev if r["verdict"] == "per item"
                                       else "`%s`" % json.dumps(r["evidence"], sort_keys=True)))
        if r.get("label"):
            L.append("| | | label: %s |" % r["label"])
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="sweep_analysis_v3_4.json of the hotel-offpath-v1 fetch")
    ap.add_argument("--out", required=True, help="NEW output directory; refused if it exists")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    J = json.loads(Path(a.readout).read_text())
    S = score(J, load_predictions())
    S["input"] = {"path": str(a.readout), "sha256": hashlib.sha256(Path(a.readout).read_bytes()).hexdigest(),
                  "scorerSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "predictionsSha256": hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest()}
    out.mkdir(parents=True)
    (out / "HO_SCORE.json").write_text(json.dumps(S, indent=1, sort_keys=True) + "\n")
    (out / "HO_SCORE.md").write_text(to_md(S))
    print("wrote", out / "HO_SCORE.json", out / "HO_SCORE.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
