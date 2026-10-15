#!/usr/bin/env python3
"""Campaign C test scorer: the frozen placement sets' penalised time to detection on campaign C's episodes only.

BINDING. Protocol round 25 (research/PROTOCOL_DRAFT_20261002.md, decisions 88 and 89), adopted from the draft
research/protocol/TEST_SCORING_C_DRAFT.md (bffb3a0); placements frozen in 378e598 (BUDGET_PLACEMENT.md step 6). Every
number this module produces is scope **instance** (one SUT, one rate, campaign C's episodes of one readout).

    uv run python research/placement/score_test_v3.py <C readout sweep_analysis_v3.json> \
        --placement research/placement/out/<sut>-primary/placement.json \
        (--campaign-index N | --campaign <path as listed in the readout's "campaigns">) \
        --training-readout <the placement's training readout> --out <NEW file.json>

Writes <out>.json and <out>.md (both refused if either exists) and prints only the two paths: the output is committed
unedited before anyone reads it, as the placement outputs were (BUDGET_PLACEMENT.md step 4).

INPUTS. (1) A frozen v3.1 readout (scriptSha256 pinned) that pools the SUT's training campaigns plus a fault-only view
of C (decision 88 step 1); C's full campaign is its `--validation` and never enters `campaigns`. (2) The frozen
placement output of the SUT (sha256 pinned per SUT from 378e598; produced by the pinned celf_v3). (3) C's position in
the readout's `campaigns` list: episodes are kept by `episodes[].campaignIndex` (sweep_analysis_v3.py:963, the index
find_and_load3 assigns at :1532), never by harness tag, because C has campaign B's shape and may carry its tag.

OBJECTIVE. The frozen celf_v3 (sha256 pinned; imported, never modified, refused if it differs): `build_table` with
the primary rules (decision 72 `e-only`: a by-construction fire counts for the ledger only; decisions 79/84 `exclude`:
a fire on the fault target is a miss for the episodes of that class only, via the per-fire `own` flag), and
`Objective` with the `ttd` penalty (a miss charged the hold, decision 15; P(i) uniform over classes, then episodes;
the ledger E in every set, decision 1), restricted to C's episodes at the rate (decision 75: per rate).
D_C(S) = Objective(table, C's indices).D(S); g_C(S) = D_C(ledger alone) - D_C(S) >= 0 by construction.

SETS, all frozen, never re-solved (FROZEN_SETS): the primary arm at the named budgets 0, 3/T_r, 6/h, inf (the
points whose `names` carry them; decision 85); the comparators ledger alone, `full` (the frozen training ground set
V_r of the primary arm, placement.json `groundSet`) and the declared `selected` / `none` (placement.json comparator
`sensors`, i.e. already restricted to the training V_r; the ids outside it stay out and are counted); the modality
arms' 6/h sets (T; T+L; every collected family = the primary 6/h set, decision 81, not repeated).

ABSENT SENSORS. A member of a frozen set outside the C readout's ground set V_r at the rate (not placeable there, or
not in its sensor table) never fires, even where the readout records a fire for it, and is listed with the reason.

DECISION 89 (verdict). Only at OTel, rate 0.2, the primary 6/h set (must be decision 89's `span:frontend:GET`):
PASS iff g_C > 0 (celf_v3.positive) AND the set improves (penalised time strictly below the ledger's) at least 2 of
C's CPU-throttle episodes at that rate (expected 3); FAIL otherwise. Given E in every set, g_C > 0 whenever any
episode improves, so the count clause implies the sign clause; both are computed and reported. Everywhere else: no
verdict. Not testable, verdict `—`:
  decision 90: a member of the frozen 6/h set is absent from C's ground set at r0.2 (not placeable, or missing from
     the sensor table); the absent members and their reasons are carried into the verdict.
  decision 91: fewer than 3 valid throttle episodes, with the count. Valid = present in the readout, i.e. from a
     valid cell (v3 emits episodes of valid cells only, sweep_analysis_v3.py:952). v3 sets `calibrated` per rate
     (:954, :967), and a rate without calibration is `—` before any episode is scored, so it adds nothing here.

INPUT CHECKS beyond the pins: the readout's v24Sha256 / detectionTimeSha256 / v1Sha256 equal the installed
sweep_analysis_v2.py / detection_time.py / sweep_analysis.py; the readout has a `validation` block (C's full campaign,
decision 88), whose campaigns and the readout's provenance.input are copied into the output; the training readout is
required (pooling check); an episode key (regime, rate, block) twice within C is refused; a class count other than 3
per rate is recorded (`classCountFlags`), not refused.

FRESH FALSE ALARMS of the frozen sets on C's no-fault cells: `—` (decision 88): the frozen v3.1 `--validation`
accepts P4-shaped sets only and no validated path exists for an arbitrary frozen set.

Switches below are flipped only by tests/test_score_test_v3.py (a planted defect must make a check fail).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import celf_v3 as cv  # noqa: E402  frozen; digest checked by check_frozen_code() before any use

VERSION = "score-test-v3.1"
SCOPE = "instance"

# ----------------------------------------------------------------------------- switches (tests flip them)
C_ONLY = True                 # decision 88: only C's episodes are scored (False: every episode at the rate)
FROZEN_SETS = True            # decision 82/88: the frozen sets are scored as frozen (False: re-solved on the C readout)
ABSENT_NEVER_FIRES = True     # a frozen member outside C's V_r never fires (False: its recorded fires count)
LIST_ABSENT = True            # ... and is listed with the reason (False: silently not listed)
STRICT_IMPROVEMENT = True     # decision 89: improves = penalised time strictly below the ledger's (False: <=)
VERDICT_THROTTLE_ONLY = True  # decision 89: improvements counted on the throttle class only (False: every class)
VERDICT_NEEDS_VALID = True    # decision 89: fewer than 3 valid throttle episodes -> `—` (False: verdict regardless)
ENFORCE_PINS = True           # digests of celf_v3, the readout's v3.1 script and the placement enforced (False: not)
VERDICT_ABSENT_UNTESTABLE = True   # decision 90: a 6/h member absent from C's V_r -> `—` (False: scored as a miss)
REQUIRE_TRAINING = True       # P2-1: the training readout (pooling check) is required (False: optional)
REFUSE_DUPLICATE_EPISODES = True   # P2-2: an episode key twice within C is refused (False: both scored)
FLAG_CLASS_COUNTS = True      # P2-2: class counts other than 3 per rate recorded (False: not recorded)
CHECK_READER_DIGESTS = True   # P2-3: v24/detection-time/v1 digests of the readout equal the installed files (False: not)
REQUIRE_VALIDATION = True     # P2-4: a readout without its validation block is refused (False: accepted)
SCORE_BC = "e-only"           # decision 72 (planted: "count-all")
SCORE_OWN = "exclude"         # decisions 79/84 (planted: "include")

SWITCHES = ("C_ONLY", "FROZEN_SETS", "ABSENT_NEVER_FIRES", "LIST_ABSENT", "STRICT_IMPROVEMENT",
            "VERDICT_THROTTLE_ONLY", "VERDICT_NEEDS_VALID", "ENFORCE_PINS", "VERDICT_ABSENT_UNTESTABLE",
            "REQUIRE_TRAINING", "REFUSE_DUPLICATE_EPISODES", "FLAG_CLASS_COUNTS", "CHECK_READER_DIGESTS",
            "REQUIRE_VALIDATION", "SCORE_BC", "SCORE_OWN")

# ----------------------------------------------------------------------------- declared values
PINNED_CELF_SHA256 = "3823722125e9796e6716a830b01d12c69177c7ab6b0a0d7a5fa3984ab6205e97"
PINNED_V3_SHA256 = "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd"
PINNED_PLACEMENTS = {   # <sut>-primary/placement.json, sha256 as listed in the freeze commit 378e598
    "hotel": "86a0ceedb68de1f8859b0489c3de0f8cd9bbadda8a908285ceca4bc6553ee5c3",
    "otel": "175637b3b76ba3b3dd1aa56a29161b1ff64e106fa711d1dd420df7ea090fb3ea",
    "teastore": "45af1f6e09db0f9872e9c1c2d96aa221f8c3e98966852cf19da596e3c60d91c5",
}
DETECTION_TIME = REPO / "research" / "detection-time"
READER_DIGESTS = {"v24Sha256": DETECTION_TIME / "sweep_analysis_v2.py",      # readout field: installed file
                  "detectionTimeSha256": DETECTION_TIME / "detection_time.py",
                  "v1Sha256": DETECTION_TIME / "sweep_analysis.py"}
EXPECTED_PER_CLASS = 3        # C: 3 blocks x each fault class per rate (decision 82: campaign B's 36-cell shape)
NAMED = ("0", "3/T_r", "6/h", "inf")                      # decision 85
PRIMARY_ARM = "primary"
MODALITY_ARMS = (("modality-T (81a)", "T"), ("modality-T+L (81a)", "T+L"))
VERDICT = {"system": "otel", "rate": "0.2", "set": "primary 6/h", "frozenSet": ["span:frontend:GET"],
           "throttleRegime": "productcatalog-cpu-throttle-effect", "expectedThrottle": 3, "minImproved": 2}
NO_VERDICT = "no verdict (decision 89: a verdict only at OTel r0.2 for the primary 6/h set)"
FAR_NOTE = ("— (decision 88: fresh false alarms of the frozen sets on C's no-fault cells need a validated path; the "
            "frozen v3.1 --validation accepts P4-shaped sets only, so none exists)")
DASH = "—"
INF = math.inf


def refuse(msg):
    raise SystemExit("refusing: " + msg)


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# =========================================================================== input checks

def check_frozen_code():
    """celf_v3 is the frozen file next to this one and its digest is the pinned one; it pins the same v3.1."""
    path = Path(cv.__file__).resolve()
    if path != HERE / "celf_v3.py":
        refuse("celf_v3 imported from %s, not %s" % (path, HERE / "celf_v3.py"))
    got = sha256(path)
    if ENFORCE_PINS and got != PINNED_CELF_SHA256:
        refuse("celf_v3.py sha256 %s is not the frozen %s" % (got, PINNED_CELF_SHA256))
    if ENFORCE_PINS and cv.PINNED_V3_SHA256 != PINNED_V3_SHA256:
        refuse("celf_v3 pins v3.1 %s, this scorer %s" % (cv.PINNED_V3_SHA256, PINNED_V3_SHA256))
    return got


def check_readout(J):
    if ENFORCE_PINS and J.get("scriptSha256") != PINNED_V3_SHA256:
        refuse("readout scriptSha256 %r is not the frozen v3.1 %s" % (J.get("scriptSha256"), PINNED_V3_SHA256))
    if CHECK_READER_DIGESTS:
        for field, path in READER_DIGESTS.items():
            got = sha256(path)
            if J.get(field) != got:
                refuse("readout %s %r is not the installed %s (%s)" % (field, J.get(field), path.name, got))
    if REQUIRE_VALIDATION and not J.get("validation"):
        refuse("the readout has no validation block (decision 88: C's full campaign as --validation)")


def check_placement(P, placement_sha, J):
    system = P.get("system")
    if ENFORCE_PINS and PINNED_PLACEMENTS.get(system) != placement_sha:
        refuse("placement sha256 %s is not the frozen %s placement (%s)" % (placement_sha, system,
                                                                            PINNED_PLACEMENTS.get(system)))
    if ENFORCE_PINS and (P.get("inputs") or {}).get("scriptSha256") != PINNED_CELF_SHA256:
        refuse("the placement was not produced by the frozen celf_v3")
    if system != J.get("system"):
        refuse("placement system %r, readout system %r" % (system, J.get("system")))
    if PRIMARY_ARM not in (P.get("arms") or {}):
        refuse("the placement has no %r arm" % PRIMARY_ARM)


def campaign_index(J, index=None, path=None):
    """C's position in the readout's `campaigns` list: exactly one of the index or the path as listed."""
    camps = J.get("campaigns")
    if not isinstance(camps, list) or not camps:
        refuse("the readout has no `campaigns` list")
    if (index is None) == (path is None):
        refuse("give exactly one of --campaign-index and --campaign")
    if path is not None:
        hits = [i for i, c in enumerate(camps) if c == path]
        if len(hits) != 1:
            refuse("campaign %r is listed %d times in the readout's campaigns (exactly once expected)"
                   % (path, len(hits)))
        return hits[0]
    if not (isinstance(index, int) and 0 <= index < len(camps)):
        refuse("campaign index %r outside 0..%d" % (index, len(camps) - 1))
    return index


def check_training(J, ci, T, training_sha, P):
    """The readout pools exactly the placement's training campaigns plus C, and C is not one of them."""
    want = (P.get("inputs") or {}).get("readoutSha256")
    if training_sha != want:
        refuse("training readout sha256 %s is not the placement's input readout %s" % (training_sha, want))
    train, c = list(T.get("campaigns") or []), J["campaigns"][ci]
    if c in train:
        refuse("campaign %r is a training campaign of the placement" % c)
    rest = [x for i, x in enumerate(J["campaigns"]) if i != ci]
    if sorted(rest) != sorted(train):
        refuse("the readout's campaigns other than C %r are not the training campaigns %r" % (rest, train))
    return {"checked": True, "trainingCampaigns": train}


# =========================================================================== frozen sets

def named_points(arm_rate):
    """{named budget: point} over the frozen Pareto points (a point may carry several names)."""
    out = {}
    for p in arm_rate.get("pareto") or []:
        for n in p.get("names") or []:
            if n in NAMED:
                if n in out:
                    refuse("named budget %s on two points" % n)
                out[n] = p
    return out


def frozen_sets(P, rk):
    """[(label, kind, members or None, info)] for one rate, all read from the frozen placement."""
    arms = P["arms"]
    prim = arms[PRIMARY_ARM].get(rk) or {}
    rows = []
    pts = named_points(prim)
    for n in NAMED:
        p = pts.get(n)
        rows.append(("primary %s" % n, "primary", None if p is None else list(p["set"]),
                     {"budgetName": n, "budget": None if p is None else p["budget"],
                      "note": None if p is not None else "— (no frozen point named %s)" % n}))
    comps = prim.get("comparators") or {}
    rows.append(("ledger alone", "comparator", [], {}))
    if "groundSet" in prim:
        rows.append(("full", "comparator", list(prim["groundSet"]),
                     {"source": "the frozen training ground set V_r of the primary arm (placement.json groundSet)"}))
    for name in sorted(comps):
        if name in ("ledger alone", "full"):
            continue
        c = comps[name]
        S = c.get("sensors")
        rows.append((name, "comparator", None if S is None else list(S),
                     {"label": c.get("label"), "outsideTrainingGroundSet": len(c.get("outsideGroundSet") or []),
                      "note": c.get("note")}))
    for arm, fam in MODALITY_ARMS:
        ar = (arms.get(arm) or {}).get(rk) or {}
        p = named_points(ar).get("6/h")
        rows.append(("modality %s 6/h" % fam, "modality", None if p is None else list(p["set"]),
                     {"arm": arm, "budgetName": "6/h",
                      "note": None if p is not None else "— (no frozen 6/h point in %s)" % arm}))
    return rows


def resolve_on_c(J, rate, obj, V, budget):
    """Planted defect only (FROZEN_SETS False): the set re-solved on the C readout at the frozen budget."""
    costs_all, _ = cv.costs_of(J, rate)
    b = INF if budget == "inf" else budget
    sol = cv.solve(obj, V, {s: costs_all[s] for s in V}, b)
    return sol["preAdmitted"] + sol["chosen"]


# =========================================================================== scoring

def absent_reasons(J, rk, members, Vset, excluded):
    sensors = J["calibration"]["primary"]["perRate"][rk]["sensors"]
    out = {}
    for s in sorted(set(members)):
        if s in Vset:
            continue
        if s not in sensors:
            out[s] = "not in the C readout's sensor table at this rate"
        else:
            out[s] = excluded.get(s, "outside the C readout's ground set at this rate")
    return out


def tt(x):
    return None if x == INF else x


def score_rate(J, P, rk, ci):
    prim = P["arms"][PRIMARY_ARM].get(rk) or {}
    if "pareto" not in prim:
        return {"note": "— (no frozen placement at this rate: %s)" % prim.get("note")}
    if rk not in J["calibration"]["primary"]["perRate"]:
        return {"note": "— (no calibration at this rate in the C readout)"}
    rate = float(rk)
    V, excluded = cv.ground_set(J, rate)                 # primary: every family, appear-only kept
    Vset = set(V)
    rows = frozen_sets(P, rk)
    members_all = sorted({s for _, _, S, _ in rows if S for s in S})
    universe = V if ABSENT_NEVER_FIRES else sorted(Vset | set(members_all))
    table = cv.build_table(J, rate, universe, SCORE_BC, SCORE_OWN)
    idx = [i for i, e in enumerate(table.episodes) if e.get("campaignIndex", 0) == ci or not C_ONLY]
    if not idx:
        return {"note": "— (no episode of C at this rate)"}
    seen = {}
    for i in idx:
        e = table.episodes[i]
        k = (e["regime"], cv.rate_key(e["rate"]), e["block"])
        if k in seen and REFUSE_DUPLICATE_EPISODES:
            refuse("episode key %r twice within C (%r and %r)" % (k, seen[k], e.get("cell")))
        seen[k] = e.get("cell")
    obj = cv.Objective(table, idx, "ttd")
    if not FROZEN_SETS:                                   # planted defect: re-solve instead of the frozen set
        rows = [(lab, kind, resolve_on_c(J, rate, obj, V, info["budget"]) if (kind == "primary" and S is not None)
                 else S, info) for lab, kind, S, info in rows]
    eps = table.episodes
    pe = obj.pe
    episodes = []
    for k, i in enumerate(idx):
        e = eps[i]
        episodes.append({"episode": e.get("cell"), "episodeKey": list(cv.episode_key(e)), "class": e["regime"],
                         "block": e["block"], "campaignIndex": e.get("campaignIndex", 0),
                         "harness": e.get("harness", "sweep"), "holdSeconds": e["holdSeconds"],
                         "calibrated": e.get("calibrated") is True,
                         "ledger": {"ttd": tt(table.te[i]), "penalised": pe[k]}, "sets": {}})
    D_led = obj.D_ledger()
    sets = {}
    for lab, kind, S, info in rows:
        row = dict(info, kind=kind, freshFalseAlarms=FAR_NOTE)
        if S is None:
            row.update(sensors=None, D=None, DLedger=D_led, g=None, verdict=NO_VERDICT)
            row["note"] = row.get("note") or "— (not declared)"
            sets[lab] = row
            continue
        absent = absent_reasons(J, rk, S, Vset, excluded)
        m = list(pe)
        for s in S:
            m = [min(a, b) for a, b in zip(m, obj.pen(s))]
        D = obj.D(S)
        # internal consistency only (same pen arrays and weights as Objective.D, not an independent check): the
        # per-episode values reported below must compose to the D reported beside them
        if abs(D - sum(w * x for w, x in zip(obj.w, m))) > 1e-9 * max(1.0, abs(D)):
            raise AssertionError("the reported per-episode values do not compose to the reported D for %s" % lab)
        for k, i in enumerate(idx):
            raw = min([table.te[i]] + [table.T(s)[i] for s in S])
            better = (m[k] < pe[k]) if STRICT_IMPROVEMENT else (m[k] <= pe[k])
            episodes[k]["sets"][lab] = {"ttd": tt(raw), "penalised": m[k], "improvesOnLedger": better}
        row["_absent"] = absent
        row.update(sensors=sorted(S) if kind != "comparator" or lab != "full" else "V_r frozen (%d)" % len(S),
                   size=len(S), D=D, DLedger=D_led, g=D_led - D,
                   detectedEpisodes=[sum(1 for k, i in enumerate(idx) if episodes[k]["sets"][lab]["ttd"] is not None),
                                     len(idx)],
                   absentFromCGroundSet={"count": len(absent), "sensors": absent} if LIST_ABSENT else None,
                   verdict=NO_VERDICT)
        sets[lab] = row
    v = verdict(J.get("system"), rk, sets, episodes)
    if v is not None:
        sets[VERDICT["set"]]["verdict"] = v
    for row in sets.values():
        row.pop("_absent", None)
    classes = {}
    for x in episodes:
        classes[x["class"]] = classes.get(x["class"], 0) + 1
    flags = ({c: n for c, n in sorted(classes.items()) if n != EXPECTED_PER_CLASS} if FLAG_CLASS_COUNTS else None)
    return {"rate": rate, "episodesScored": len(idx), "classes": dict(sorted(classes.items())),
            "classCountFlags": flags, "expectedPerClass": EXPECTED_PER_CLASS,
            "harnessTags": sorted({x["harness"] for x in episodes}), "groundSetSize": len(V),
            "episodesAtRateInReadout": len(eps), "sets": sets, "episodes": episodes,
            "rules": {"bc": SCORE_BC, "own": SCORE_OWN, "penalty": "ttd", "missAtHold": cv.MISS_AT_HOLD}}


def verdict(system, rk, sets, episodes):
    """Decision 89, or None where no verdict applies."""
    if not (system == VERDICT["system"] and rk == VERDICT["rate"]):
        return None
    row = sets.get(VERDICT["set"])
    if row is None or row.get("D") is None:
        return {"verdict": DASH, "reason": "the frozen 6/h set is missing"}
    members = row["sensors"]
    if sorted(members) != sorted(VERDICT["frozenSet"]):
        refuse("the frozen OTel r0.2 6/h set %r is not decision 89's %r" % (members, VERDICT["frozenSet"]))
    lab = VERDICT["set"]
    thr = [x for x in episodes if x["class"] == VERDICT["throttleRegime"]]     # valid: in the readout (decision 91)
    pool = thr if VERDICT_THROTTLE_ONLY else episodes
    improved = sum(1 for x in pool if x["sets"][lab]["improvesOnLedger"])
    g = row["g"]
    absent = row.get("_absent") or {}
    out = {"rule": "PASS iff g_C > 0 and the set improves >= %d of C's CPU-throttle episodes at r0.2 (expected %d)"
                   % (VERDICT["minImproved"], VERDICT["expectedThrottle"]),
           "throttleEpisodesValid": len(thr), "throttleEpisodesImproved": improved if VERDICT_THROTTLE_ONLY else None,
           "improvedCounted": improved, "gC": g, "gPositive": cv.positive(g), "absentFromCGroundSet": absent}
    if VERDICT_ABSENT_UNTESTABLE and absent:
        out.update(verdict=DASH, reason="not testable (decision 90): frozen 6/h member(s) absent from C's ground set "
                   "at r0.2: %s" % "; ".join("%s (%s)" % kv for kv in sorted(absent.items())))
        return out
    if VERDICT_NEEDS_VALID and len(thr) < VERDICT["expectedThrottle"]:
        out.update(verdict=DASH, reason="not testable (decision 91): %d valid throttle episode(s) of C at r0.2, "
                   "fewer than %d"
                   % (len(thr), VERDICT["expectedThrottle"]))
        return out
    reasons = []
    if not cv.positive(g):
        reasons.append("g_C = %.6g <= 0" % g)
    if improved < VERDICT["minImproved"]:
        reasons.append("improves %d of %d throttle episodes (< %d)" % (improved, len(thr), VERDICT["minImproved"]))
    out.update(verdict="FAIL" if reasons else "PASS", reason="; ".join(reasons) if reasons else
               "g_C = %.6g > 0; improves %d of %d throttle episodes (>= %d)" % (g, improved, len(thr),
                                                                                VERDICT["minImproved"]))
    return out


def score(J, P, ci, placement_sha, training=None):
    """Every frozen rate of the placement on C's episodes. training: (readout dict, sha256) or None."""
    celf_sha = check_frozen_code()
    check_readout(J)
    check_placement(P, placement_sha, J)
    camps = J["campaigns"]
    if training is None and REQUIRE_TRAINING:
        refuse("no training readout: that the readout pools exactly the training campaigns plus C must be checked")
    tr = (check_training(J, ci, training[0], training[1], P) if training is not None else
          {"checked": False, "note": "— (no training readout: pooling not checked)"})
    rates = {}
    for rk in sorted(P["arms"][PRIMARY_ARM], key=float):
        rates[rk] = score_rate(J, P, rk, ci)
    read = J.get("campaignsRead")
    return {"version": VERSION, "scope": SCOPE, "system": J.get("system"),
            "campaign": {"index": ci, "path": camps[ci], "read": read[ci] if isinstance(read, list) and
                         ci < len(read) else None},
            "trainingCheck": tr, "deviation": cv.DEVIATION_80, "freshFalseAlarms": FAR_NOTE,
            "verdictRule": VERDICT, "switches": {k: globals()[k] for k in SWITCHES},
            "celfSha256": celf_sha, "rates": rates,
            "readoutRecords": {"validationCampaigns": (J.get("validation") or {}).get("campaigns"),
                               "provenanceInput": (J.get("provenance") or {}).get("input")}}


# =========================================================================== output

def fmt(x):
    return DASH if x is None else ("%.3f" % x)


def markdown(res):
    L = ["# Campaign C test scoring (%s, scope %s)" % (res["version"], res["scope"]), "",
         "System `%s`; campaign index %d (`%s`), C's episodes only. Penalty `ttd` (a miss charged the hold); "
         "D and g_C in seconds; g_C = D_C(ledger alone) - D_C(S)." % (res["system"], res["campaign"]["index"],
                                                                     res["campaign"]["path"]),
         "Fresh false alarms of every frozen set on C's no-fault cells: %s." % res["freshFalseAlarms"],
         "Deviation: %s." % res["deviation"], ""]
    for rk, r in res["rates"].items():
        L.append("## r%s" % rk)
        if "sets" not in r:
            L += ["", r["note"], ""]
            continue
        L += ["", "C episodes: %d (%s). Ground set of the C readout: %d sensors.%s" % (
            r["episodesScored"], ", ".join("%s %d" % kv for kv in r["classes"].items()), r["groundSetSize"],
            (" **Class counts other than %d: %s.**" % (r["expectedPerClass"], ", ".join(
                "%s %d" % kv for kv in r["classCountFlags"].items()))) if r.get("classCountFlags") else ""), "",
            "| set | sensors | absent from C's V_r | D_C(S) | D_C(ledger) | g_C | detected | verdict (decision 89) |",
            "|---|---|---|---|---|---|---|---|"]
        for lab, s in r["sets"].items():
            if s.get("D") is None:
                L.append("| %s | — | — | — | %s | — | — | %s |" % (lab, fmt(s["DLedger"]), s.get("note") or DASH))
                continue
            v = s["verdict"]
            vtxt = ("**%s**: %s" % (v["verdict"], v["reason"])) if isinstance(v, dict) else "—"
            ab = s["absentFromCGroundSet"]
            mem = s["sensors"] if isinstance(s["sensors"], str) else (", ".join(s["sensors"]) if len(
                s["sensors"]) <= 3 else "%d sensors" % len(s["sensors"]))
            L.append("| %s | %s | %s | %s | %s | %s | %d/%d | %s |" % (
                lab, mem or "(none)", DASH if ab is None else ab["count"], fmt(s["D"]), fmt(s["DLedger"]),
                fmt(s["g"]), s["detectedEpisodes"][0], s["detectedEpisodes"][1], vtxt))
        labs = [lab for lab, s in r["sets"].items() if s.get("D") is not None and lab != "ledger alone"]
        L += ["", "Per episode, penalised seconds (`*` = strictly earlier than the ledger):", "",
              "| episode | class | block | ledger | " + " | ".join(labs) + " |",
              "|---|---|---|---|" + "---|" * len(labs)]
        for x in r["episodes"]:
            cells = []
            for lab in labs:
                y = x["sets"][lab]
                cells.append(fmt(y["penalised"]) + ("*" if y["improvesOnLedger"] else ""))
            L.append("| %s | %s | %s | %s | %s |" % (x["episode"], x["class"], x["block"],
                                                     fmt(x["ledger"]["penalised"]), " | ".join(cells)))
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="frozen v3.1 readout: training campaigns + C's fault-only view")
    ap.add_argument("--placement", required=True, help="frozen research/placement/out/<sut>-primary/placement.json")
    ap.add_argument("--campaign-index", type=int, default=None, help="C's index in the readout's campaigns list")
    ap.add_argument("--campaign", default=None, help="C's path exactly as listed in the readout's campaigns")
    ap.add_argument("--training-readout", required=True, help="the placement's training readout (pooling check)")
    ap.add_argument("--out", required=True, help="NEW <file>.json; <file>.md beside it; refused if either exists")
    a = ap.parse_args(argv)
    out = Path(a.out)
    md = out.with_suffix(".md")
    if out.suffix != ".json":
        refuse("--out must end in .json")
    for p in (out, md):
        if p.exists() or p.is_symlink():
            refuse("to write into an existing path: %s" % p)
    check_frozen_code()
    J = json.loads(Path(a.readout).read_text())
    check_readout(J)
    P = json.loads(Path(a.placement).read_text())
    psha = sha256(a.placement)
    ci = campaign_index(J, a.campaign_index, a.campaign)
    training = (json.loads(Path(a.training_readout).read_text()), sha256(a.training_readout))
    res = score(J, P, ci, psha, training)
    res["inputs"] = {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "placement": str(a.placement),
                     "placementSha256": psha, "trainingReadout": a.training_readout,
                     "trainingReadoutSha256": training[1],
                     "validationCampaigns": res["readoutRecords"]["validationCampaigns"],
                     "readoutProvenanceInput": res["readoutRecords"]["provenanceInput"],
                     "script": str(Path(__file__).resolve().relative_to(REPO)) if Path(__file__).resolve().is_relative_to(
                         REPO) else str(Path(__file__).resolve()), "scriptSha256": sha256(__file__),
                     "python": sys.version}           # Objective.D uses builtin sum: compensated on 3.12+
    text_json = json.dumps(res, indent=1, sort_keys=True, allow_nan=False)
    text_md = markdown(res)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:         # exclusive create: never overwrites
        fh.write(text_json)
    with open(md, "x", encoding="utf-8") as fh:
        fh.write(text_md)
    print("wrote", out)                                    # no number printed: committed unedited before reading
    print("wrote", md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
