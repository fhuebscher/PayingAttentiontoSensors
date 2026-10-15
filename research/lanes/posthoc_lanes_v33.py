#!/usr/bin/env python3
"""POST HOC lane rows for OTel campaign F and the TeaStore off-path epoch (rows the frozen v3.3 chain does not produce).

    uv run python research/lanes/posthoc_lanes_v33.py otel --training-readout <v3.3 training readout.json> \
        --scoring-readout <v3.3 scoring readout.json> --placement <frozen celf_v3_3 placement.json> --out-dir <NEW dir>
    uv run python research/lanes/posthoc_lanes_v33.py teastore --readout <v3.3 readout of ONE fetch dir.json> --out-dir <NEW dir>

POST HOC, NOT PREREGISTERED AS A VERDICT. Written under FREEZE_V33_20261014.md, addendum "review conditions" (condition 2), and
committed with its tests on campaign E's data before any F or TeaStore off-path cell is read. Every number is scope **instance**.
Nothing here is a pass rule: no field of the output decides anything, the hit / miss / `—` of a lane prediction is a report, and
the frozen chain (readers, registries, celf and scorer wrappers, adapter) is imported and never edited or re-implemented where a
function exists. The output directory must not exist (new evidence never overwrites old).

PARTS
  1. Zero-alarm pricing frontier (OTel F, post hoc, no verdict; DECLARATION_F_OTEL.md "Decision 73 stays as frozen").
     The same tiered frontier as celf_v3_3 at the same named budgets (0, 3/T_r, 6/T_r, 6/h, inf), on the same training readout, but
     every ground-set sensor that decision 73 prices at the fill because the reader never evaluated it
     (calibration.primary.perRate.<rate>.sensors[id]: appearOnly True, foldsEvaluated 0, honestUpperPerHour None) is priced at the
     zero-alarm bound -ln(0.05)/T_r = 2.9957/T_r (T_r = the rate's training no-fault hours, `hours`) instead.
     REUSE. `celf_v3_3.main` is called unchanged (all its input checks, split checks, frontier, recurrence rule, held-out folds)
     twice, into the output directory: once as it is (the decision-73 rerun, which must equal the frozen placement) and once with ONE
     frozen-code function replaced for the duration of the call: `celf_v3.costs_of` (the cost table that celf_v3.arm_setup reads by
     module-global name) is wrapped to overwrite the cost of the sensors above after the frozen function returns, so decision 73's
     fill (the rate's largest evidenced upper bound) is still computed from evidenced sensors only. celf_v3.py's own test switch
     COST_NULL_RULE (which uses 3.0/T_r) is NOT flipped. `score_test_v3_3.score` (-> score_test_v3_2.score_rate) then scores both
     placements on the test blocks (heldOut episodes only), with the frozen objective, with no pass rule (rule None); the per-class
     g and improved-episode counts are computed here from the scorer's own per-episode rows by the formula score_test_v3_2.verdict
     uses, without its pass/fail. The scorer is run with allow_unpinned for the PLACEMENT pin only: a post hoc placement is by
     definition not the frozen one; the reader and registry pins stay enforced (their pins are not None).
     WHAT THE FLAG MEANS (stated because the declaration's gloss differs). foldsEvaluated 0 with appearOnly True is the reader's
     flag: the `appear` rule is evaluated in a leave-one-cell-out fold only if the sensor has NO scored record in that fold's fit
     (sweep_analysis_v3.py:650, v2.4 `Fit.novel`), and the fit pools every other valid cell of the rate, fault cells' fault-free
     segments included (`Fit3(valid, rate, exclude=X)`). So foldsEvaluated 0 = a record in the fit of every fold; it is NOT proven to
     equal "no record in any training no-fault cell". The script uses the reader's flag and records its count; it does not re-read
     raw cells.
  2. OTel lane predictions on test-block episodes only (heldOut true, blocks 4-5): F-L1, F-L2, F-L3, F-M of DECLARATION_F_OTEL.md,
     from the v3.3 readout's `v33.lanes` block and calibration. Rules: see `otel_predictions`.
  3. TeaStore lane predictions of DECLARATION_TEASTORE_OFFPATH.md: T-L1, T-L2, T-OFF, T-C, from the v3.3 readout, its episodes'
     fires, the cell's journey-ledger.jsonl (T-OFF) and the cell's application.log (T-L2 corroboration only).
  4. Condition 1 of the addendum: a TeaStore readout's `campaignsRead` must list exactly one campaign directory whose fetch carries
     exactly one setup ID (`setupId` of the .lease-receipts / .packages / .supervisor receipts beside the campaign directory);
     anything else is refused before any prediction is read.

Result words: `hit`, `miss`, `—` (not testable or not collected: unarmed or absent sensors, a denominator other than the declared
one, no episode). Unknown is never 0.

Switches (flipped only by tests/test_posthoc_lanes_v33.py, a planted defect each): PRICE_ZERO_ALARM, ZERO_ALARM_FACTOR,
HELD_OUT_ONLY, EITHER_FIELD, HOLD_WINDOW_ONLY, REQUIRE_ONE_SETUP.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import io
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO / "research" / "placement", REPO / "research" / "detection-time"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import celf_v3_3 as c3  # noqa: E402  frozen wrapper; main() is called as it is
import score_test_v3_3 as s3  # noqa: E402  frozen wrapper; score() is called as it is

cv = c3.cv          # celf_v3 (frozen); only its `costs_of` attribute is wrapped, inside a context manager
c2 = c3.c2          # celf_v3_2 (frozen)
s2 = s3.s2          # score_test_v3_2 (frozen)

POST_HOC = "POST HOC (not a preregistered verdict; written under FREEZE_V33_20261014.md addendum, condition 2)"
SCOPE = "instance"
DASH = "—"
VERSION = "posthoc-lanes-v33"
SCRIPT = "research/lanes/posthoc_lanes_v33.py"
PLACEMENT_SCOPE_NOTE = "reported without a pass or fail rule"

# ---------------------------------------------------------------------------- switches (tests flip them)
PRICE_ZERO_ALARM = True            # False: the "zero-alarm" frontier is the decision-73 frontier (no repricing)
ZERO_ALARM_FACTOR = -math.log(0.05)  # 2.9957 events (exact Poisson 95 % upper bound after 0); planted 3.0 = celf_v3's test switch
HELD_OUT_ONLY = True               # lane predictions use heldOut episodes only (False: every episode of the readout)
EITHER_FIELD = True                # counted OR by-construction fire is a fire (False: counted field only)
HOLD_WINDOW_ONLY = True            # T-OFF counts journeys started in [onset, onset + hold] (False: the whole cell)
REQUIRE_ONE_SETUP = True           # condition 1: exactly one campaign dir and one setup ID (False: not enforced)
SWITCHES = ("PRICE_ZERO_ALARM", "ZERO_ALARM_FACTOR", "HELD_OUT_ONLY", "EITHER_FIELD", "HOLD_WINDOW_ONLY", "REQUIRE_ONE_SETUP")

# ---------------------------------------------------------------------------- declared predictions (copied from the declarations)
OFFPATH_REGIMES_OTEL = ("fraud-pause-effect", "accounting-pause-effect")
CONTROL_REGIME_OTEL = "frontend-pause-effect"
OTEL_EXPECTED = {"offpath": 4, "frontend": 2}
F_L1_MAX_S = 2.0
F_L2_WINDOW_S = (42.0, 47.0)
F_L3_MIN_BEFORE = 3
F_M_NON_FLAGD = "flagd"
SPANMETRICS_BASES = ("calls", "duration")          # spanmetrics connector metrics; the adapter names a histogram `<name>~rate` / `~mean`
TS_REGIME, TS_TARGET = "recommender-pause-effect", "recommender"
TS_CONTROL_REGIME = "auth-freeze-effect"
TS_EXPECTED_N = 10
T_L1_MAX_S, T_L1_MIN_EPISODES = 5.0, 9
T_L2_WINDOW_S, T_L2_MIN_EPISODES = (7.5, 12.5), 9
T_OFF_MIN_SHARE, T_OFF_MIN_EPISODES = 0.95, 9
REMOVAL_RX = re.compile(r"Removed tools\.descartes\.teastore\.(\w+)@\S+ since it failed the heartbeat")
STAMP_RX = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z")
SETUP_DIRS = (".lease-receipts", ".packages", ".supervisor")
FIRE = cv.FIRE


class Refused(SystemExit):
    """A refusal: the run stops before anything is reported."""


def refuse(msg):
    raise Refused("refusing: " + msg)


def sha256(p):
    return c3.sha256(p)


def _num(x):
    """JSON-safe number: inf and nan become None."""
    if isinstance(x, float) and (math.isinf(x) or math.isnan(x)):
        return None
    return x


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return _num(o)


# =========================================================================== part 1: zero-alarm pricing frontier

def zero_alarm_ids(cr):
    """The ground-set sensors of one rate's calibration that decision 73 prices at the fill because the reader never evaluated
    them: placeable, family != E, appearOnly True, foldsEvaluated == 0 and no honest upper bound (the reader's own fields)."""
    out = []
    for sid, s in sorted(cr["sensors"].items()):
        if s.get("family") == cv.LEDGER_FAMILY or not s.get("placeable"):
            continue
        if s.get("appearOnly") and s.get("foldsEvaluated") == 0 and s.get("honestUpperPerHour") is None:
            out.append(sid)
    return out


def unevaluated_other(cr):
    """Placeable non-E sensors that stay at the fill under the zero-alarm row (no honest bound, not appear-only with 0 folds)."""
    za = set(zero_alarm_ids(cr))
    return sorted(sid for sid, s in cr["sensors"].items() if s.get("family") != cv.LEDGER_FAMILY and s.get("placeable")
                  and s.get("honestUpperPerHour") is None and sid not in za)


@contextlib.contextmanager
def zero_alarm_costs():
    """Replace `celf_v3.costs_of` by a wrapper for the duration of the block: the frozen function runs unchanged, then the cost of
    every zero_alarm_ids sensor is overwritten with ZERO_ALARM_FACTOR / hours (the rate's training no-fault hours). Restored on exit."""
    orig = cv.costs_of

    def wrapped(J, rate, rule="upper"):
        costs, label = orig(J, rate, rule)
        if rule == "upper" and PRICE_ZERO_ALARM:
            cr = J["calibration"]["primary"]["perRate"][cv.rate_key(rate)]
            hours = cr.get("hours")
            if hours:
                for sid in zero_alarm_ids(cr):
                    if sid in costs:
                        costs[sid] = ZERO_ALARM_FACTOR / hours
                        label[sid] = "post hoc: zero-alarm bound %.4f/T_r (appear-only, 0 folds evaluated)" % ZERO_ALARM_FACTOR
        return costs, label

    cv.costs_of = wrapped
    try:
        yield wrapped
    finally:
        cv.costs_of = orig


def run_celf(training_path, tiers, catalog, split, out_path, zero_alarm):
    """celf_v3_3.main on the training readout into out_path (a NEW file), with or without the cost override. Returns the placement."""
    argv = [str(training_path), "--tiers", str(tiers), "--tier-catalog", catalog, "--split", str(split), "--out", str(out_path)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if zero_alarm:
            with zero_alarm_costs():
                c3.main(argv)
        else:
            c3.main(argv)
    return json.loads(Path(out_path).read_text())


def score_placement(S, P, psha, test_blocks, T, tsha):
    """score_test_v3_3.score with no pass rule; the placement pin is waived (post hoc placement), the reader pins are not.
    The waiver covers a pinned scorer too: allow_unpinned only waives a missing pin, so PINNED_PLACEMENTS is emptied for this
    call only (deviation recorded in FREEZE_V33_20261014.md, found when F's pin was set)."""
    saved = s3.PINNED_PLACEMENTS
    s3.PINNED_PLACEMENTS = {}
    try:
        return s3.score(S, P, psha, list(test_blocks), (T, tsha), None, True)
    finally:
        s3.PINNED_PLACEMENTS = saved


def _class_rows(rate_res, label):
    """Per class g and improved episodes for one frozen-set label, by the formula score_test_v3_2.verdict uses (no pass/fail)."""
    eps = rate_res["episodes"]
    out = {}
    for cls in sorted({e["class"] for e in eps}):
        pool = [e for e in eps if e["class"] == cls]
        sets = [e["sets"].get(label) for e in pool]
        if any(x is None for x in sets):
            out[cls] = {"episodes": len(pool), "gClass": None, "improved": None}
            continue
        g = math.fsum(e["ledger"]["penalised"] - e["sets"][label]["penalised"] for e in pool) / len(pool)
        out[cls] = {"episodes": len(pool), "gClass": g,
                    "improved": sum(1 for e in pool if e["sets"][label]["improvesOnLedger"]),
                    "ttds": [e["sets"][label]["ttd"] for e in pool], "ledgerTtds": [e["ledger"]["ttd"] for e in pool]}
    return out


def summarise_scoring(res, costs_by_rate):
    """Compact per-rate summary of s3.score's result: every frontier set (members, D, g, detected), class rows, comparators."""
    out = {}
    for rk, r in res["rates"].items():
        if "sets" not in r:
            out[rk] = {"note": r.get("note")}
            continue
        sets = {}
        for lab, s in r["sets"].items():
            if s.get("D") is None:
                sets[lab] = {"note": s.get("note") or DASH}
                continue
            sets[lab] = {"sensors": s["sensors"], "size": s["size"], "D": s["D"], "DLedger": s["DLedger"], "g": s["g"],
                         "detectedEpisodes": s["detectedEpisodes"], "sameAs": s.get("sameAs"),
                         "absentFromScoringGroundSet": s["absentFromScoringGroundSet"]["count"],
                         "perClass": _class_rows(r, lab) if lab.startswith("frontier") else None}
        out[rk] = {"episodesScored": r["episodesScored"], "testBlocks": r["testBlocks"], "classCounts": r["classCounts"],
                   "groundSetSize": r["groundSetSize"], "sets": sets,
                   "episodes": [{"episode": e["episode"], "class": e["class"], "block": e["block"], "ledgerTtd": e["ledger"]["ttd"],
                                 "holdSeconds": e["holdSeconds"]} for e in r["episodes"]]}
    return out


def frontier_label(max_effort="any", max_runtime="any", budget="6/T_r"):
    return "frontier (effort<=%s, runtime<=%s) @%s" % (max_effort, max_runtime, budget)


BUDGETS = ("0", "3/T_r", "6/T_r", "6/h", "inf")


def zero_alarm_part(T, tsha, S, training_path, frozen_placement, tiers, catalog, split, test_blocks, out_dir):
    """Part 1. Returns the JSON block. Writes the two placements into out_dir/placements (new files)."""
    pdir = Path(out_dir) / "placements"
    pdir.mkdir(parents=True, exist_ok=True)
    p73_path, pza_path = pdir / "decision73_rerun.json", pdir / "zero_alarm.json"
    P73 = run_celf(training_path, tiers, catalog, split, p73_path, False)
    PZA = run_celf(training_path, tiers, catalog, split, pza_path, True)
    rows = {}
    for name, P, path in (("decision73", P73, p73_path), ("zeroAlarm", PZA, pza_path)):
        sc = score_placement(S, P, sha256(path), test_blocks, T, tsha)
        rows[name] = {"placement": str(path), "placementSha256": sha256(path), "scoring": summarise_scoring(sc, None)}
    rates = {}
    for rk, r in PZA["rates"].items():
        if "grid" not in r:
            rates[rk] = {"note": r.get("note")}
            continue
        cr = T["calibration"]["primary"]["perRate"][rk]
        za, other = zero_alarm_ids(cr), unevaluated_other(cr)
        base_costs = P73["rates"][rk]["costs"]
        za_costs = r["costs"]
        fill = max((v for k, v in base_costs.items() if k not in set(za) and cr["sensors"][k].get("honestUpperPerHour") is not None),
                   default=None)
        members = {}
        for b in BUDGETS:
            lab_cell = [c for c in r["grid"] if c["maxEffort"] == "any" and c["maxRuntime"] == "any"][0]["points"][b]
            if "set" not in lab_cell:
                members[b] = None
                continue
            members[b] = [{"id": s, "priceZeroAlarmRow": za_costs.get(s), "priceDecision73": base_costs.get(s),
                           "basis": ("zero-alarm bound (repriced)" if s in set(za) else
                                     "decision-73 fill (not repriced)" if s in set(other) else "evidenced honest upper bound")}
                          for s in lab_cell["set"]]
        rates[rk] = {"hours": r["hours"], "zeroAlarmPricePerHour": (ZERO_ALARM_FACTOR / r["hours"]) if r["hours"] else None,
                     "decision73FillPerHour": fill, "groundSetSize": len(r["groundSet"]), "repricedIds": len(za),
                     "unevaluatedLeftAtFill": len(other), "unevaluatedLeftAtFillIds": other[:50],
                     "membersUnrestrictedCell": members,
                     "setsDifferByBudget": {b: sorted(_pt(P73, rk, b)) != sorted(_pt(PZA, rk, b)) for b in BUDGETS
                                            if _pt(P73, rk, b) is not None}}
    baseline = None
    if frozen_placement is not None:
        baseline = {"frozenPlacement": str(frozen_placement[0]), "frozenPlacementSha256": frozen_placement[1],
                    "frozenInputReadoutSha256": (frozen_placement[2].get("inputs") or {}).get("readoutSha256"),
                    "trainingReadoutSha256": tsha,
                    "ratesEqualFrozen": frozen_placement[2].get("rates") == P73.get("rates"),
                    "note": "the decision-73 rerun through the same code path equals the frozen placement's `rates` (every key) when True"}
    return {"label": POST_HOC, "scope": SCOPE, "note": PLACEMENT_SCOPE_NOTE,
            "price": "sensors with appearOnly True, foldsEvaluated 0 and no honest upper bound are priced %.4f/T_r (T_r = the rate's "
                     "training no-fault hours) instead of decision 73's fill" % ZERO_ALARM_FACTOR,
            "flagMeaning": "foldsEvaluated 0 = the sensor had a scored record in the fit of every leave-one-cell-out fold (the fit "
                           "pools every other valid cell, fault cells' fault-free segments included); not proven equal to 'no record "
                           "in any training no-fault cell'",
            "reuse": "celf_v3_3.main run unchanged; celf_v3.costs_of wrapped (context manager) to overwrite the cost of the "
                     "flagged ids; score_test_v3_3.score unchanged with no pass rule and allow_unpinned for the placement pin only",
            "baselineCheck": baseline, "placements": rows, "rates": rates}


def _pt(P, rk, budget, max_effort="any", max_runtime="any"):
    r = P["rates"][rk]
    if "grid" not in r:
        return None
    for c in r["grid"]:
        if c["maxEffort"] == max_effort and c["maxRuntime"] == max_runtime:
            p = c["points"][budget]
            return p.get("set")
    return None


# =========================================================================== lane helpers shared by parts 2 and 3

def lane_rows(J, regime, rate=None, held_out=None):
    """The v33.lanes episode rows of one regime (rate filter optional; held_out True/False/None)."""
    x = ((J.get("v33") or {}).get("lanes") or {}).get("regimes", {}).get(regime)
    if not x:
        return []
    rows = []
    for e in x["episodes"]:
        if rate is not None and float(e["rate"]) != float(rate):
            continue
        if held_out is not None and bool(e.get("heldOut")) != held_out:
            continue
        rows.append(e)
    return rows


def fire_fields(lane):
    """[(field name, earliest record)] of a lane block: counted always, by-construction when EITHER_FIELD."""
    out = []
    if lane.get("earliest"):
        out.append(("counted", lane["earliest"]))
    if EITHER_FIELD and lane.get("earliestByConstruction"):
        out.append(("by-construction", lane["earliestByConstruction"]))
    return out


def earliest_any(lane):
    f = fire_fields(lane)
    if not f:
        return None
    name, rec = min(f, key=lambda x: x[1]["ttd"])
    return {"field": name, "ttd": rec["ttd"], "sensor": rec["sensor"], "rule": rec["rule"], "bcFlags": rec.get("bcFlags")}


def result_of(k, n, need, expected_n):
    """hit / miss / — for 'at least `need` of `n`', with the declared denominator `expected_n` (None: not checked)."""
    if n == 0:
        return DASH
    if expected_n is not None and n != expected_n:
        return DASH
    return "hit" if k >= need else "miss"


def _pred(pid, text, result, reason, numbers):
    return {"id": pid, "prediction": text, "result": result, "reason": reason, "numbers": _clean(numbers)}


# =========================================================================== part 2: OTel lane predictions

def lag_ids(J, rk):
    """(all lag ids in the calibration, the placeable ones) by the reader's lag-lane rule (service, channel, name prefix)."""
    rule = J["v33"]["lanes"]["rules"].get("lag")
    if not rule:
        return [], []
    sens = J["calibration"]["primary"]["perRate"][rk]["sensors"]
    allids = [sid for sid in sens if _matches_lane(sid, rule)]
    return sorted(allids), sorted(s for s in allids if sens[s].get("placeable"))


def _matches_lane(sid, rule):
    parts = sid.split(":", 2)
    if len(parts) != 3:
        return False
    ch, svc, tok = parts
    return svc == rule["service"] and ch in rule["channels"] and any(tok.startswith(p) for p in rule["tokenPrefixes"])


def metric_class(sid):
    """`spanmetrics` for the spanmetrics connector's metrics (`calls`, `duration`, with the adapter's `~rate` / `~mean` suffix),
    else `sdk`. Rule by metric name only (research/otel-offpath/adapter.py:395-396 names a histogram `<name>~rate` / `<name>~mean`)."""
    tok = sid.split(":", 2)[2]
    base = tok.split("~", 1)[0]
    return "spanmetrics" if base in SPANMETRICS_BASES else "sdk"


def f_m(J, rk):
    sens = J["calibration"]["primary"]["perRate"][rk]["sensors"]
    placeable = sorted(sid for sid, s in sens.items() if sid.startswith("metric:") and s.get("placeable")
                       and sid.split(":", 2)[1] != F_M_NON_FLAGD)
    by = {"sdk": [s for s in placeable if metric_class(s) == "sdk"],
          "spanmetrics": [s for s in placeable if metric_class(s) == "spanmetrics"]}
    flagd = sorted(sid for sid, s in sens.items() if sid.startswith("metric:") and s.get("placeable")
                   and sid.split(":", 2)[1] == F_M_NON_FLAGD)
    nums = {"rate": rk, "placeableNonFlagdSdk": len(by["sdk"]), "placeableNonFlagdSpanmetrics": len(by["spanmetrics"]),
            "sdkIds": by["sdk"][:40], "spanmetricsIds": by["spanmetrics"][:40], "placeableFlagd": len(flagd),
            "metricIdsInCalibration": sum(1 for s in sens if s.startswith("metric:")),
            "classRule": "metric name, `~rate`/`~mean` suffix stripped, in %s -> spanmetrics, else SDK" % (SPANMETRICS_BASES,)}
    res = "hit" if placeable else "miss"
    return _pred("F-M", ">= 1 non-flagd metric id placeable at the rate, counted separately for SDK and spanmetrics-derived ids",
                 res, "%d SDK + %d spanmetrics-derived non-flagd placeable metric ids at %s req/s" % (
                     len(by["sdk"]), len(by["spanmetrics"]), rk), nums)


def otel_predictions(S, rate=25.0):
    """F-L1, F-L2, F-L3, F-M on the heldOut (test-block) episodes of the scoring readout S. Rules:
    F-L1: every off-path test episode has an own-lane fire (counted or by-construction, the field named) earlier than 2.0 s.
    F-L2: every off-path test episode has a COUNTED coordinator fire in [42, 47] s; and the frontend test episodes have no fire
          (a by-construction fire in the frontend episodes is reported separately and also negates the 'no fire' clause).
    F-L3: `—` when the lag ids are absent or none is placeable, or an episode has no collected lag sensor; else a hit when the lag lane
          (counted or by-construction) fires before the coordinator's counted fire (or the coordinator is silent) in >= 3 of the 4.
    F-M: >= 1 non-flagd placeable metric id (calibration of the scoring readout, equal to the training one by the scorer's check).
    Denominators: 4 off-path and 2 frontend test episodes; another count gives `—` with the numbers."""
    rk = "%g" % rate
    held = True if HELD_OUT_ONLY else None
    off = {r: lane_rows(S, r, rate, held) for r in OFFPATH_REGIMES_OTEL}
    off_rows = [e for r in OFFPATH_REGIMES_OTEL for e in off[r]]
    fe_rows = lane_rows(S, CONTROL_REGIME_OTEL, rate, held)
    n_off, n_fe = len(off_rows), len(fe_rows)
    den_ok = n_off == OTEL_EXPECTED["offpath"] and n_fe == OTEL_EXPECTED["frontend"]
    den_note = "off-path test episodes %d (declared %d), frontend %d (declared %d)" % (
        n_off, OTEL_EXPECTED["offpath"], n_fe, OTEL_EXPECTED["frontend"])
    preds = []
    # F-L1
    per = []
    for e in off_rows:
        own = e["lanes"]["own"]
        er = earliest_any(own)
        per.append({"cell": e["cell"], "regime": _regime_of(S, e), "block": e["block"], "ownCollected": own["collectedSensors"],
                    "earliest": er, "below2s": bool(er and er["ttd"] < F_L1_MAX_S)})
    k = sum(1 for p in per if p["below2s"])
    nodata = [p for p in per if not p["ownCollected"]]
    res = DASH if (nodata or not den_ok or not per) else ("hit" if k == n_off else "miss")
    preds.append(_pred("F-L1", "own silence fires < 2.0 s after the pause command in 4/4 off-path test episodes", res,
                       den_note + ("; an episode has no collected own sensor" if nodata else ""),
                       {"k": k, "n": n_off, "maxS": F_L1_MAX_S, "episodes": per}))
    # F-L2
    per2 = []
    for e in off_rows:
        co = e["lanes"]["coordinator"]
        t = (co.get("earliest") or {}).get("ttd")
        per2.append({"cell": e["cell"], "regime": _regime_of(S, e), "block": e["block"], "coordinatorCollected": co["collectedSensors"],
                     "countedEarliest": co.get("earliest"), "byConstructionEarliest": co.get("earliestByConstruction"),
                     "inWindow": bool(t is not None and F_L2_WINDOW_S[0] <= t <= F_L2_WINDOW_S[1])})
    in_win = sum(1 for p in per2 if p["inWindow"])
    fe = [{"cell": e["cell"], "block": e["block"], "coordinatorCollected": e["lanes"]["coordinator"]["collectedSensors"],
           "countedFires": e["lanes"]["coordinator"]["countedFires"],
           "byConstructionFires": e["lanes"]["coordinator"]["byConstructionFires"]} for e in fe_rows]
    fe_counted_none = all(x["countedFires"] == 0 for x in fe)
    fe_any_none = all(x["countedFires"] == 0 and x["byConstructionFires"] == 0 for x in fe)
    nodata2 = [p for p in per2 if not p["coordinatorCollected"]]
    if nodata2 or not den_ok or not per2:
        res = DASH
    else:
        res = "hit" if (in_win == n_off and fe_any_none) else "miss"
    preds.append(_pred("F-L2", "coordinator: earliest counted fire 42-47 s in 4/4 off-path test episodes; no fire in the 2 frontend test episodes",
                       res, den_note, {"offpathInWindow": in_win, "n": n_off, "window": F_L2_WINDOW_S, "episodes": per2,
                                       "frontendEpisodes": fe, "frontendNoCountedFire": fe_counted_none,
                                       "frontendNoFireEitherField": fe_any_none}))
    # F-L3
    all_ids, armed = lag_ids(S, rk)
    if not all_ids:
        preds.append(_pred("F-L3", "lag lane armed and fires before F-L2's fire in >= 3/4", DASH,
                           "no kafka.consumer_group.lag* id in the calibration (absent: not collected or dropped by the adapter)",
                           {"lagIdsInCalibration": 0, "armed": 0}))
    elif not armed:
        preds.append(_pred("F-L3", "lag lane armed and fires before F-L2's fire in >= 3/4", DASH,
                           "%d lag id(s) in the calibration, none placeable (unarmed)" % len(all_ids),
                           {"lagIdsInCalibration": len(all_ids), "armed": 0, "ids": all_ids}))
    else:
        per3 = []
        for e in off_rows:
            lag, co = e["lanes"]["lag"], e["lanes"]["coordinator"]
            lt = earliest_any(lag)
            ct = (co.get("earliest") or {}).get("ttd")
            before = bool(lt is not None and (ct is None or lt["ttd"] < ct))
            per3.append({"cell": e["cell"], "regime": _regime_of(S, e), "lagCollected": lag["collectedSensors"], "lagEarliest": lt,
                         "coordinatorCountedTtd": ct, "lagBeforeCoordinator": before})
        k3 = sum(1 for p in per3 if p["lagBeforeCoordinator"])
        nodata3 = [p for p in per3 if not p["lagCollected"]]
        res = DASH if (nodata3 or not den_ok or not per3) else ("hit" if k3 >= F_L3_MIN_BEFORE else "miss")
        preds.append(_pred("F-L3", "lag lane armed and fires before F-L2's fire in >= 3/4", res,
                           den_note + ("; an episode has no collected lag sensor" if nodata3 else ""),
                           {"lagIdsInCalibration": len(all_ids), "armed": len(armed), "armedIds": armed[:20], "k": k3, "n": n_off,
                            "episodes": per3}))
    # F-M
    if rk not in S["calibration"]["primary"]["perRate"]:
        preds.append(_pred("F-M", "metric arming", DASH, "no calibration at rate %s" % rk, {}))
    else:
        preds.append(f_m(S, rk))
    return preds


def _regime_of(S, lane_row):
    for ep in S["episodes"]:
        if ep["cell"] == lane_row["cell"]:
            return ep["regime"]
    return None


# =========================================================================== part 3: TeaStore lane predictions

def cell_dir(cell):
    """The cell directory of an episode's `cell` ('<campaign dir> :: runs/...'), or None."""
    if " :: " not in cell:
        return None
    root, rel = cell.split(" :: ", 1)
    for base in (Path(root), REPO / root):
        d = base / rel
        if d.exists():
            return d
    return None


def ledger_ok_share(path, onset, hold, whole_cell=False):
    """Share of login journeys that are ok among those that STARTED in [onset, onset + hold] on the ledger's monotonic clock (the
    clock of the readout's episode onset). Row rule as sweep_analysis_v2.teastore_ledger: a `journey-terminal` row with an
    actualStartMonotonic; ok = outcome `succeeded`, at least one request, every request statusCode 200. Login rows: workloadId
    contains `login`. Returns {started, ok, share} (share None when nothing started)."""
    started = ok = 0
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("recordType") != "journey-terminal" or "login" not in str(r.get("workloadId", "")).lower():
            continue
        s = r.get("actualStartMonotonic")
        if s is None:
            continue
        if not whole_cell and not (onset <= float(s) <= onset + hold):
            continue
        q = r.get("requests") or []
        good = r.get("outcome") == "succeeded" and bool(q) and all(x.get("statusCode") == 200 for x in q)
        started += 1
        ok += 1 if good else 0
    return {"started": started, "ok": ok, "share": (ok / started) if started else None}


def removal_line(cell, target, onset_wall):
    """Corroboration only: the registry's 'Removed ...<target>... since it failed the heartbeat!' line in the cell's application.log
    and its Docker stamp minus the onset wall time. None when the cell or the line is not there."""
    d = cell_dir(cell)
    if d is None or not (d / "application.log").exists():
        return None
    for line in (d / "application.log").read_text(errors="replace").splitlines():
        m = REMOVAL_RX.search(line)
        if m and m.group(1) == target:
            st = STAMP_RX.search(line)
            lag = None
            if st:
                t = _dt.datetime.strptime(st.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt.timezone.utc).timestamp()
                lag = t + (float(st.group(2)) if st.group(2) else 0.0) - onset_wall
            return {"present": True, "lagSeconds": lag}
    return {"present": False, "lagSeconds": None}


def coordinator_fires(e, rules):
    """All registry-log fires (rule: service registry, channel log) of an episode that count (`counts` True), with their field."""
    rule = rules["coordinator"]
    out = []
    for f in e["fires"]:
        if f[FIRE["family"]] == cv.LEDGER_FAMILY or not f[FIRE["counts"]]:
            continue
        if f[FIRE["own"]]:
            continue
        if _matches_lane(f[FIRE["sensorId"]], rule):
            bc = bool(f[FIRE["bc"]])
            if bc and not EITHER_FIELD:
                continue
            out.append({"ttd": f[FIRE["ttd"]], "sensor": f[FIRE["sensorId"]], "rule": f[FIRE["rule"]],
                        "field": "by-construction" if bc else "counted", "bcFlags": list(f[FIRE["bc"]])})
    return sorted(out, key=lambda x: (x["ttd"], x["sensor"]))


def own_cpu_down(e, target):
    """The target's own CPU fires of family S going down (`metric:<target>:sys_cpu`, direction down), counted or by construction."""
    sid = "metric:%s:sys_cpu" % target
    out = []
    for f in e["fires"]:
        if f[FIRE["family"]] != "S" or f[FIRE["sensorId"]] != sid or f[FIRE["dir"]] != "down" or not f[FIRE["counts"]]:
            continue
        bc = bool(f[FIRE["bc"]])
        if bc and not EITHER_FIELD:
            continue
        out.append({"ttd": f[FIRE["ttd"]], "sensor": sid, "rule": f[FIRE["rule"]],
                    "field": "by-construction" if bc else "counted", "bcFlags": list(f[FIRE["bc"]])})
    return sorted(out, key=lambda x: x["ttd"])


def setup_ids_of(campaign_dir):
    """{setupId: [files]} of the receipts beside a campaign directory (<parent>/.lease-receipts|.packages|.supervisor/*.json)."""
    out = {}
    parent = Path(campaign_dir).parent
    for sub in SETUP_DIRS:
        for f in sorted((parent / sub).glob("*.json")) if (parent / sub).is_dir() else []:
            try:
                sid = json.loads(f.read_text()).get("setupId")
            except (OSError, ValueError):
                continue
            if isinstance(sid, str) and sid:
                out.setdefault(sid, []).append(str(f))
    return out


def check_one_setup(J, expect=None):
    """Condition 1 of the addendum: `campaignsRead` lists exactly one campaign directory and its receipts name exactly one setup ID.
    Refuses (Refused) otherwise. Returns the record."""
    camps = J.get("campaignsRead") or []
    dirs = [c.get("campaign") for c in camps]
    ids = {}
    for d in dirs:
        base = Path(d)
        if not base.is_absolute() and not base.exists():
            base = REPO / d
        for sid, files in setup_ids_of(base).items():
            ids.setdefault(sid, []).extend(files)
    rec = {"campaignsRead": dirs, "setupIds": sorted(ids), "files": ids, "expected": expect}
    if REQUIRE_ONE_SETUP:
        if len(dirs) != 1:
            refuse("the readout's campaignsRead lists %d campaign directories %s, exactly 1 is required (condition 1: relaunch 1's "
                   "fetch only)" % (len(dirs), dirs))
        if len(ids) != 1:
            refuse("the readout's campaign directory %s carries %d setup IDs %s, exactly 1 is required (condition 1)" % (
                dirs[0], len(ids), sorted(ids)))
        if expect is not None and sorted(ids) != [expect]:
            refuse("the readout's setup ID %s is not the expected %s" % (sorted(ids), expect))
    rec["ok"] = len(dirs) == 1 and len(ids) == 1 and (expect is None or sorted(ids) == [expect])
    return rec


def teastore_predictions(J, regime=TS_REGIME, target=TS_TARGET, expected_n=TS_EXPECTED_N):
    """T-L1, T-L2, T-OFF, T-C. Rules:
    T-L1: per episode the earliest down-going fire of the target's own cgroup CPU sensor (family S, `metric:<target>:sys_cpu`), counted or
          by-construction (field named), < 5.0 s; hit when >= 9 of the 10 episodes.
    T-L2: per episode any registry-log fire (counted or by-construction, field named) in [7.5, 12.5] s; hit when >= 9 of 10. The
          fire is by rule (service registry), not by message text; the cell's application.log removal line and its lag are listed
          as corroboration.
    T-OFF: (a) per episode ok / started of login journeys started in [onset, onset + hold] from the cell's journey-ledger.jsonl,
          episode ok when >= 95 %, hit when >= 9 of 10; (b) no ledger (family E) fire that counts under celf_v3's `e-only` rule in
          the episode (all episodes). The row is a hit when (a) and (b) hold; both clauses are listed.
    T-C: predictions.P1 (the on-path auth-freeze pause) holds with k == n; per-rate k/n listed.
    `expected_n` None skips the declared-denominator check (a plumbing run on a stand-in regime)."""
    rules = J["v33"]["lanes"]["rules"]
    eps = [e for e in J["episodes"] if e["regime"] == regime]
    n = len(eps)
    preds = []
    note = "%d episodes of %s%s" % (n, regime, "" if expected_n is None else " (declared %d)" % expected_n)
    # T-L1
    per1 = []
    for e in sorted(eps, key=lambda x: (-x["rate"], x["block"])):
        fs = own_cpu_down(e, target)
        per1.append({"cell": e["cell"], "rate": e["rate"], "block": e["block"], "earliest": fs[0] if fs else None,
                     "below5s": bool(fs and fs[0]["ttd"] < T_L1_MAX_S)})
    k1 = sum(1 for p in per1 if p["below5s"])
    preds.append(_pred("T-L1", "own silence: the target's cgroup CPU (family S) fires down < 5 s after the pause command in >= 9/10",
                       result_of(k1, n, T_L1_MIN_EPISODES, expected_n), note,
                       {"k": k1, "n": n, "need": T_L1_MIN_EPISODES, "episodes": per1,
                        "samplerCaveat": "system-samples.json is a cgroup v2 sampler every 5 s (teastore_samples): a fire is stamped at a "
                                         "sample time, 0-5 s after the command, so '< 5 s' can fail on sampling phase alone; the actual "
                                         "times are listed, none is rounded to the sampler period"}))
    # T-L2
    per2 = []
    for e in sorted(eps, key=lambda x: (-x["rate"], x["block"])):
        fs = [f for f in coordinator_fires(e, rules) if T_L2_WINDOW_S[0] <= f["ttd"] <= T_L2_WINDOW_S[1]]
        rl = removal_line(e["cell"], target, e["onset"]["wall"])
        per2.append({"cell": e["cell"], "rate": e["rate"], "block": e["block"], "inWindowFire": fs[0] if fs else None,
                     "inWindow": bool(fs), "allCoordinatorFires": len(coordinator_fires(e, rules)),
                     "applicationLogRemovalLine": rl})
    k2 = sum(1 for p in per2 if p["inWindow"])
    preds.append(_pred("T-L2", "registry-log fire 7.5-12.5 s after the pause command (either field, the field named) in >= 9/10",
                       result_of(k2, n, T_L2_MIN_EPISODES, expected_n), note,
                       {"k": k2, "n": n, "need": T_L2_MIN_EPISODES, "window": T_L2_WINDOW_S, "episodes": per2,
                        "byRate": _by_rate(per2, "inWindow")}))
    # T-OFF
    per3 = []
    for e in sorted(eps, key=lambda x: (-x["rate"], x["block"])):
        d = cell_dir(e["cell"])
        row = {"cell": e["cell"], "rate": e["rate"], "block": e["block"], "onset": e["onset"]["mono"], "hold": e["holdSeconds"]}
        if d is None or not (d / "journey-ledger.jsonl").exists():
            row.update(started=None, ok=None, share=None, okAtLeast95=None)
        else:
            sh = ledger_ok_share(d / "journey-ledger.jsonl", e["onset"]["mono"], e["holdSeconds"], not HOLD_WINDOW_ONLY)
            row.update(sh, okAtLeast95=(sh["share"] >= T_OFF_MIN_SHARE) if sh["share"] is not None else None)
        led = [f for f in e["fires"] if f[FIRE["family"]] == cv.LEDGER_FAMILY]
        counted = [f for f in led if cv.counted(f, "e-only", "exclude")]
        row.update(ledgerFiresAny=len(led), ledgerFiresCounted=len(counted),
                   ledgerFires=[{"sensor": f[FIRE["sensorId"]], "rule": f[FIRE["rule"]], "ttd": f[FIRE["ttd"]],
                                 "counts": f[FIRE["counts"]], "bcFlags": list(f[FIRE["bc"]])} for f in led])
        per3.append(row)
    unread = [p for p in per3 if p["okAtLeast95"] is None]
    ka = sum(1 for p in per3 if p["okAtLeast95"])
    clause_b = all(p["ledgerFiresCounted"] == 0 for p in per3) if per3 else None
    if unread or not per3 or (expected_n is not None and n != expected_n):
        res = DASH
        reason = note + ("; %d episode(s) without a readable journey ledger" % len(unread) if unread else "")
    else:
        res = "hit" if (ka >= T_OFF_MIN_EPISODES and clause_b) else "miss"
        reason = note
    preds.append(_pred("T-OFF", "login route stays off the fault: >= 95 % of login journeys ok during the hold in >= 9/10 episodes, and no "
                                "ledger fire attributable", res, reason,
                       {"okShareClause": {"k": ka, "n": n, "need": T_OFF_MIN_EPISODES, "minShare": T_OFF_MIN_SHARE},
                        "noCountedLedgerFireClause": clause_b, "episodes": per3,
                        "window": "journeys started in [onset, onset + hold] on the ledger monotonic clock" if HOLD_WINDOW_ONLY
                        else "whole cell (planted)"}))
    # T-C
    P1 = (J.get("predictions") or {}).get("P1") or {}
    if not P1 or not P1.get("n"):
        preds.append(_pred("T-C", "on-path control: auth-freeze detected by the ledger (P1)", DASH, "no P1 in the readout or n = 0", {}))
    else:
        res = "hit" if (P1.get("holds") and P1["k"] == P1["n"]) else "miss"
        preds.append(_pred("T-C", "on-path control: auth-freeze detected by the ledger (P1 holds, k == n)", res,
                           "predictions.P1 over the readout's auth-freeze episodes",
                           {"holds": P1.get("holds"), "k": P1["k"], "n": P1["n"], "notEvaluable": P1.get("notEvaluable"),
                            "perRate": P1.get("perRate")}))
    return preds


def _by_rate(rows, key):
    out = {}
    for r in rows:
        k = "%g" % r["rate"]
        a = out.setdefault(k, [0, 0])
        a[1] += 1
        a[0] += 1 if r[key] else 0
    return out


# =========================================================================== markdown and CLI

def _fmt(x, nd=2):
    if x is None:
        return DASH
    if isinstance(x, float):
        return ("%." + str(nd) + "f") % x
    return str(x)


def md_predictions(preds):
    L = ["| id | result | reason | key numbers |", "|---|---|---|---|"]
    for p in preds:
        n = p["numbers"]
        keys = {k: v for k, v in n.items() if k in ("k", "n", "need", "offpathInWindow", "frontendNoFireEitherField", "frontendNoCountedFire",
                                                     "armed", "lagIdsInCalibration", "placeableNonFlagdSdk", "placeableNonFlagdSpanmetrics",
                                                     "placeableFlagd", "holds", "okShareClause", "noCountedLedgerFireClause")}
        L.append("| %s | **%s** | %s | %s |" % (p["id"], p["result"], p["reason"], json.dumps(keys, sort_keys=True)))
    return L


def markdown_otel(out):
    L = ["# %s: OTel lane rows (%s, scope %s)" % (VERSION, out["label"], SCOPE), "",
         "Inputs: training readout `%s`, scoring readout `%s`, frozen placement `%s`. Test blocks %s (heldOut episodes). No pass or fail "
         "rule is applied to anything below." % (out["inputs"]["trainingReadout"], out["inputs"]["scoringReadout"],
                                                 out["inputs"]["placement"], out["inputs"]["testBlocks"]), "",
         "## 1. Zero-alarm pricing frontier (post hoc)", "", out["zeroAlarm"]["price"], "", "Flag meaning: " + out["zeroAlarm"]["flagMeaning"], ""]
    bc = out["zeroAlarm"].get("baselineCheck")
    if bc:
        L += ["Decision-73 rerun equals the frozen placement's `rates`: **%s**." % bc["ratesEqualFrozen"], ""]
    for rk, r in out["zeroAlarm"]["rates"].items():
        if "note" in r:
            L += ["Rate %s: %s" % (rk, r["note"]), ""]
            continue
        L += ["### Rate %s (T_r = %.4f h; zero-alarm price %.3f /h; decision-73 fill %s /h; repriced ids %d; unevaluated ids left at the fill %d)" % (
            rk, r["hours"], r["zeroAlarmPricePerHour"], _fmt(r["decision73FillPerHour"]), r["repricedIds"], r["unevaluatedLeftAtFill"]), "",
            "Unrestricted cell (effort<=any, runtime<=any); sets differ from decision 73's: %s." % r["setsDifferByBudget"], "",
            "| budget | set (zero-alarm row) | size | D_E | g_E (test) | detected | decision-73 set size | decision-73 g_E |", "|---|---|---|---|---|---|---|---|"]
        za = out["zeroAlarm"]["placements"]["zeroAlarm"]["scoring"][rk]["sets"]
        d73 = out["zeroAlarm"]["placements"]["decision73"]["scoring"][rk]["sets"]
        for b in BUDGETS:
            lab = frontier_label(budget=b)
            z, d = za.get(lab), d73.get(lab)
            mem = r["membersUnrestrictedCell"].get(b)
            ms = ", ".join("%s [%s]" % (m["id"], m["basis"].split(" ")[0]) for m in mem) if mem else DASH
            if z is None or "D" not in z:
                L.append("| %s | %s | — | — | — | — | — | — |" % (b, ms))
                continue
            L.append("| %s | %s | %s | %s | %s | %s/%s | %s | %s |" % (b, ms, z["size"], _fmt(z["D"], 3), _fmt(z["g"], 3),
                                                                      z["detectedEpisodes"][0], z["detectedEpisodes"][1],
                                                                      d["size"] if d and "size" in d else DASH,
                                                                      _fmt(d["g"], 3) if d and "g" in d else DASH))
        L.append("")
        for b in ("3/T_r", "6/T_r"):
            lab = frontier_label(budget=b)
            z = za.get(lab)
            if z and z.get("perClass"):
                L.append("Per class at %s (zero-alarm row): " % b + "; ".join(
                    "%s: g=%s, improved %s/%s" % (c, _fmt(v["gClass"], 3), v["improved"], v["episodes"]) for c, v in z["perClass"].items()))
        L.append("")
    L += ["## 2. Lane predictions on the test-block episodes (heldOut)", ""] + md_predictions(out["predictions"]) + [""]
    return "\n".join(L) + "\n"


def markdown_teastore(out):
    L = ["# %s: TeaStore lane rows (%s, scope %s)" % (VERSION, out["label"], SCOPE), "",
         "Readout `%s`; regime `%s`%s. Condition 1: campaignsRead %s, setup ID(s) %s." % (
             out["inputs"]["readout"], out["regime"], " (PLUMBING: stand-in regime, not the declared one)" if out["plumbing"] else "",
             out["condition1"]["campaignsRead"], out["condition1"]["setupIds"]), "",
         "No pass or fail rule is applied; hit / miss / `—` is a report.", ""] + md_predictions(out["predictions"]) + [""]
    for p in out["predictions"]:
        if p["id"] in ("T-L1", "T-L2", "T-OFF"):
            L += ["### %s per episode" % p["id"], ""]
            for e in p["numbers"].get("episodes", []):
                L.append("- `%s` rate %g block %s: %s" % (e["cell"].split(" :: ")[-1], e["rate"], e["block"], json.dumps(
                    {k: v for k, v in e.items() if k not in ("cell", "rate", "block", "ledgerFires")}, sort_keys=True)))
            if p["id"] == "T-L1":
                L += ["", "Sampler caveat: " + p["numbers"]["samplerCaveat"]]
            L.append("")
    return "\n".join(L) + "\n"


def write_new(path, text):
    p = Path(path)
    if p.exists() or p.is_symlink():
        refuse("to write into an existing path: %s" % p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "x", encoding="utf-8") as fh:
        fh.write(text)


def check_readout_pins(J, what):
    """The frozen v3.3 reader's digest and registry digest (celf_v3_3's v3.3 layer, pins enforced)."""
    c3.check_v33_layer(J, what, False)


def run_otel(a):
    out_dir = Path(a.out_dir)
    if out_dir.exists() or out_dir.is_symlink():
        refuse("to write into an existing path: %s" % out_dir)
    T = json.loads(Path(a.training_readout).read_text())
    S = json.loads(Path(a.scoring_readout).read_text())
    check_readout_pins(T, "the training readout")
    check_readout_pins(S, "the scoring readout")
    tsha = sha256(a.training_readout)
    frozen = None
    P = json.loads(Path(a.placement).read_text())
    frozen = (a.placement, sha256(a.placement), P)
    tiers = a.tiers or (P.get("inputs") or {}).get("tiers") or refuse("no --tiers and the placement records none")
    catalog = a.tier_catalog or (P.get("tiers") or {}).get("catalog") or refuse("no --tier-catalog and the placement records none")
    out_dir.mkdir(parents=True)
    za = zero_alarm_part(T, tsha, S, a.training_readout, frozen, tiers, catalog, a.split, a.test_blocks, out_dir)
    preds = otel_predictions(S, a.rate)
    out = {"version": VERSION, "label": POST_HOC, "scope": SCOPE, "system": "otel", "switches": {k: globals()[k] for k in SWITCHES},
           "inputs": {"trainingReadout": str(a.training_readout), "trainingReadoutSha256": tsha, "scoringReadout": str(a.scoring_readout),
                      "scoringReadoutSha256": sha256(a.scoring_readout), "placement": str(a.placement),
                      "placementSha256": frozen[1], "tiers": str(tiers), "tierCatalog": catalog, "split": str(a.split),
                      "testBlocks": list(a.test_blocks), "rate": a.rate, "script": SCRIPT, "scriptSha256": sha256(__file__),
                      "python": sys.version},
           "zeroAlarm": za, "predictions": preds}
    write_new(out_dir / "posthoc_lanes_v33_otel.json", json.dumps(_clean(out), indent=1, sort_keys=True, allow_nan=False))
    write_new(out_dir / "posthoc_lanes_v33_otel.md", markdown_otel(_clean(out)))
    print("wrote", out_dir / "posthoc_lanes_v33_otel.json", out_dir / "posthoc_lanes_v33_otel.md")
    return 0


def run_teastore(a):
    out_dir = Path(a.out_dir)
    if out_dir.exists() or out_dir.is_symlink():
        refuse("to write into an existing path: %s" % out_dir)
    J = json.loads(Path(a.readout).read_text())
    check_readout_pins(J, "the readout")
    cond = check_one_setup(J, a.expect_setup_id)                  # first: nothing else is read before this
    plumbing = a.regime != TS_REGIME
    target = a.target or (TS_TARGET if not plumbing else TS_CONTROL_REGIME.split("-")[0])
    preds = teastore_predictions(J, a.regime, target, None if plumbing else a.expected_n)
    out = {"version": VERSION, "label": POST_HOC, "scope": SCOPE, "system": "teastore", "regime": a.regime, "target": target,
           "plumbing": plumbing, "switches": {k: globals()[k] for k in SWITCHES}, "condition1": cond,
           "inputs": {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "script": SCRIPT, "scriptSha256": sha256(__file__),
                      "python": sys.version},
           "predictions": preds}
    out_dir.mkdir(parents=True)
    write_new(out_dir / "posthoc_lanes_v33_teastore.json", json.dumps(_clean(out), indent=1, sort_keys=True, allow_nan=False))
    write_new(out_dir / "posthoc_lanes_v33_teastore.md", markdown_teastore(_clean(out)))
    print("wrote", out_dir / "posthoc_lanes_v33_teastore.json", out_dir / "posthoc_lanes_v33_teastore.md")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("otel", help="OTel campaign F: zero-alarm frontier and F-L1..F-M")
    o.add_argument("--training-readout", required=True)
    o.add_argument("--scoring-readout", required=True)
    o.add_argument("--placement", required=True, help="the frozen celf_v3_3 placement of the training readout")
    o.add_argument("--tiers", default=None, help="default: the placement's recorded tier file")
    o.add_argument("--tier-catalog", default=None, help="default: the placement's recorded catalog")
    o.add_argument("--split", default=str(REPO / "research/protocol/split_f_otel.json"))
    o.add_argument("--test-blocks", nargs="+", type=int, default=[4, 5])
    o.add_argument("--rate", type=float, default=25.0)
    o.add_argument("--out-dir", required=True)
    t = sub.add_parser("teastore", help="TeaStore off-path epoch: T-L1, T-L2, T-OFF, T-C")
    t.add_argument("--readout", required=True)
    t.add_argument("--regime", default=TS_REGIME, help="a regime other than the declared one makes the run a PLUMBING run")
    t.add_argument("--target", default=None)
    t.add_argument("--expected-n", type=int, default=TS_EXPECTED_N)
    t.add_argument("--expect-setup-id", default=None)
    t.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    return run_otel(a) if a.cmd == "otel" else run_teastore(a)


if __name__ == "__main__":
    sys.exit(main())
