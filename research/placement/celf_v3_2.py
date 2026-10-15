#!/usr/bin/env python3
"""Placement v3.2: the tiered-budget frontier over a v3.2 readout (BUDGET_E.md step 3; decision 95 for the training split).

    uv run python research/placement/celf_v3_2.py <v3.2 readout sweep_analysis_v3_2.json> \
        --tiers research/placement/declared/otel.effort.json --tier-catalog postureCurrentCatalog --out <NEW file.json> \
        [--declared <comparator sets json>] [--split <split.json>] [--allow-unpinned] [--allow-unsplit]

STATUS: FROZEN with the reader and the registry (research/protocol/FREEZE_V32_20261013.md); its own digest is recorded
there. Scope of every number: **instance** (one SUT, one rate, one readout).

The objective is celf_v3's, imported and not copied (`import celf_v3 as cv`; its sha256 is checked against the frozen
digest before any use): T(i, s), g, D, the decision-72/73/75/79 rules, the lazy greedy (UC and CB, best of the two), the
online bound, the held-out folds by (harness, block). Nothing of it is changed. v3.2 adds an axis of CAPS, not a term:

  Per-sensor tiers. A sensor has an EFFORT tier (0 out of the box, 1 configuration, 2 code change) and a RUNTIME-COST tier
  ('<1%', '1-10%', '>10%' CPU overhead, CUMULATIVE: decision 101), or null on either axis (unknown). They are read from a declared JSON
  (schema below), never guessed. Unknown is not zero: a null tier is admissible only under the `any` cap of its axis.
  Frontier. For every (max effort, max runtime) in {0, 1, 2, any} x {'<1%', '1-10%', '>10%', any}: the ground set V_r
  restricted to the admitted sensors, then celf_v3's solve at the named budgets (0, 3/T_r, 6/T_r, 6/h, inf) on the SAME costs
  (the honest false-alarm upper bounds of the full V_r, so one cost table for every cell) and the SAME objective; each
  point carries its set, D, g, the charged cost, the online bound and the held-out fold means. The false-alarm budget
  axis of decision 76 is unchanged; the caps are a second, independent axis.
  Named budgets. 3/T_r = celf_v3.LITERAL_NULL_EVENTS / hours (decision 110: one zero-alarm sensor evaluated in every
  training fold fits), 6/T_r = 2 x that (decision 112: two such sensors fit; the budget of E's pass rule), 6/h =
  celf_v3.FAR_BUDGET_PER_HOUR, `inf`, `0`; hours = the rate's T_r (the training no-fault hours), the same for both knots.
  Recurrence rule (decision 112, V32_RECURRENCE_RULE, switch RECURRENCE_FILTER). A sensor is a candidate of every frontier
  cell and every budget point only if it has a COUNTED fire (celf_v3's `counted`, decisions 72/79/84, i.e. the entries of
  the objective's own detection-time table) in >= minEpisodesPerClass (2) training episodes of at least one class (fault
  regime) of the rate. One candidate set for all points. The costs stay the shared full-V_r table (a removed sensor still
  sets the no-evidence fill). The output records, per rate, how many ground-set sensors the rule removed, how many of
  them had a counted fire, and the recurring sensors per class (`recurrence`). The comparators `full` and `out of the
  box` are not filtered (they describe the unrestricted ground set).
  Non-monotone cells. Relaxing a cap can only enlarge the candidates, but the greedy is a heuristic, so a relaxed cell can
  come out worse than a stricter one. They are LISTED (nonMonotone), never repaired.
  Comparators, named: `ledger alone`; `full` (the training ground set); `out of the box` = every ground-set sensor of
  effort tier 0 (the upstream system as shipped; its D and charged cost), the starting posture the frontier is read
  against; plus any declared sets (decision 78, restriction estimates). The effort axis is reported as a RESULT:
  `effortAxis` counts the ground set and the sensors with a counted fire by tier; where no sensor with a counted fire
  has an effort tier above 0 or unknown, the axis is degenerate and `degenerate` says so; nothing is engineered around it.
  Training split (decision 95). The readout must come from the reader's `--blocks <training blocks>` (its
  v32.blockSelection names them) AND every episode of it must be an episode of the campaign-E epoch in those blocks (the
  label alone is not the split); the placement is solved on that readout only and records the blocks. `--split` is
  required (it records the declared test blocks the scorer later checks). A readout of every block is refused unless
  --allow-unsplit (exploration). `--tier-catalog` must be the catalog the readout's epochs call for (the current runtime
  catalog for the off-path epochs, else the v3 catalog) unless --allow-catalog-mismatch.
  Runtime-tier caveat: the tier is the cumulative share of the posture steps up to the one that first emits the sensor
  (decision 101, below); a step share belongs to a group of services, not to one sensor.

TIER FILE SCHEMA (version 1), the shape of research/placement/declared/otel.effort.json (1fff401), validated by
`load_tiers`; unknown extra keys are allowed, a violation of the following stops the run (TierError):
  schemaVersion == 1; system (str); postureCatalogs: an object describing the catalog requested by --tier-catalog (`postures` <-> key `v3`,
  `postureCurrentCatalog` <-> key `current`: the v3 catalog for evidence from existing campaigns, the current runtime catalog for
  the off-path epochs); postureCostEvidence.steps.{none_to_selected, selected_to_async, async_to_full}.share_of_none_level
  (numbers, the CPU share of each posture step); sensors: a list of objects with a unique string `id`; `effortTier` in
  {0, 1, 2, null}; the requested catalog key (`postures` or `postureCurrentCatalog`) a list of postures in
  {none, selected, async, full}, nested (a suffix of that order: a sensor emitted at a posture is emitted at every later
  one) or absent/empty = unknown; optional `runtimeTier` in {'<1%', '1-10%', '>10%', null} overriding the derivation.
  Runtime tier (decision 101, round 30; supersedes the coordinator's marginal default): the runtime cost of a SET is the
  cumulative share of the posture steps needed to emit all its members (none 0, selected 0.17, async 0.228, full 0.288 of
  none-level CPU, summed from postureCostEvidence), binned by V32_TIERS.runtimeBins ('<1%' below 0.01, '1-10%' to 0.10,
  '>10%' above). Postures are nested, so a sensor first emitted at `async` also pays the `selected` step. The set-level
  value is that of the latest first-emission step among the members, so the cap is applied as a filter on each candidate's
  cumulative value (exact, not an approximation); every frontier point reports its own `runtimeCost`. With these shares a
  '1-10%' cap admits no sensor beyond those present at `none` (every later step is above 10% cumulatively): a result of the
  numbers, not engineered around. A step share is a property of a group of services, not of one sensor, and a sensor with
  unknown posture membership has an unknown tier (admissible only under `any`).
  A ground-set sensor absent from the file has unknown effort and runtime. The ledger id is never a candidate.

Pins (F5): PINNED_CELF_SHA256, PINNED_V31_SHA256, PINNED_V32_SHA256 (the reader) and PINNED_PARAMETERS_V32_SHA256 (the registry).
With the registry pin set, the live registry and the readout's recorded parametersV32Sha256 must both equal it; unpinned (None),
the readout's digest must be the live registry's and --allow-unpinned is needed. The scorer applies the same check
(check_parameters_digest) to its scoring readout and to the placement it scores.

Switches (flipped only by tests/test_celf_v3_2.py, a planted defect each): TIER_NULL_UNKNOWN (a null tier is admitted only
under `any`; False: null counts as tier 0), SHARED_COSTS (one cost table over the full V_r; False: re-derived per cap, so the
no-evidence fill moves with the cap), CAP_FILTER (the cap restricts the ground set; False: no restriction),
RUNTIME_FROM_FIRST_STEP (False: the LAST step), CUMULATIVE_RUNTIME (False: each step's marginal share), REQUIRE_SPLIT, CHECK_PINS, VALIDATE_TIERS,
RECURRENCE_FILTER (decision 112; False: every sensor with a counted fire is a candidate, a one-episode sensor included).

DEVIATIONS FROM v3.1 (group 10 of DEVIATIONS_V2_TO_V3.md; placement step, outside the registry): the tier caps and the
frontier; the effort file and its derived runtime tier; the out-of-the-box comparator; the training-split requirement.
Hyperparameter groups 1-9 are the reader's (sweep_analysis_v3_2.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import celf_v3 as cv  # noqa: E402  frozen; digest checked by check_frozen_celf()

VERSION = "placement-v3.2"
SCOPE = "instance"
PINNED_CELF_SHA256 = "3823722125e9796e6716a830b01d12c69177c7ab6b0a0d7a5fa3984ab6205e97"
PINNED_V31_SHA256 = "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd"
PINNED_V32_SHA256 = "97eb0a1d4f3f7e0daecee447113fdd14bd14b84812f420ddb3903bfe16759465"   # the frozen reader (FREEZE_V32_20261013.md)
PINNED_PARAMETERS_V32_SHA256 = "ab4a5af7243e776f536b09a39e649b1be968d23f1767ef2f5a166ac08e340a67"   # the frozen registry (FREEZE_V32_20261013.md)
PARAMETERS_V32 = REPO / "research" / "protocol" / "parameters_v3_2.json"
INF = math.inf
DASH = "—"

TIER_NULL_UNKNOWN = True          # a null tier is admitted only under the `any` cap (False: null counts as the lowest tier)
SHARED_COSTS = True               # one cost table over the full V_r for every cap (False: re-derived on each cap's set)
CAP_FILTER = True                 # the caps restrict the ground set (False: every cell is the unrestricted problem)
RUNTIME_FROM_FIRST_STEP = True    # runtime tier = the step that first emits the sensor (False: the last step)
CUMULATIVE_RUNTIME = True         # decision 101: the tier bins the CUMULATIVE share of the steps (False: the step's own)
SPLIT_FROM_REGISTRY = True        # decision 100: --split and the readout's blocks must be the registry's (False: any)
REQUIRE_SPLIT = True              # a readout of every block is refused (False: accepted)
CHECK_PINS = True                 # frozen celf_v3 / v3.1 / v3.2 digests enforced (False: not)
VALIDATE_TIERS = True             # the tier file's schema is enforced (False: read as it comes)
RECURRENCE_FILTER = True          # decision 112: candidates need a counted fire in >= 2 training episodes of one class
SWITCHES = ("TIER_NULL_UNKNOWN", "SHARED_COSTS", "CAP_FILTER", "RUNTIME_FROM_FIRST_STEP", "CUMULATIVE_RUNTIME",
            "SPLIT_FROM_REGISTRY", "REQUIRE_SPLIT", "CHECK_PINS",
            "VALIDATE_TIERS", "RECURRENCE_FILTER")


def _registry():
    return {p["name"]: p["value"] for p in json.loads(PARAMETERS_V32.read_text())["parameters"]}


TIERS = _registry()["V32_TIERS"]
E_SPLIT = _registry()["V32_E_SPLIT"]
RECURRENCE_RULE = _registry()["V32_RECURRENCE_RULE"]
RECURRENCE_MIN = RECURRENCE_RULE["minEpisodesPerClass"]
EFFORT_TIERS = tuple(TIERS["effortTiers"])
RUNTIME_TIERS = tuple(TIERS["runtimeTiers"])
ANY = TIERS["any"]
POSTURES = tuple(TIERS["postureOrder"])
EFFORT_CAPS = EFFORT_TIERS + (ANY,)
RUNTIME_CAPS = RUNTIME_TIERS + (ANY,)


class TierError(ValueError):
    """The tier file is not the schema this module consumes."""


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def refuse(msg):
    raise SystemExit("refusing: " + msg)


# =========================================================================== the tier file

def _bin(share):
    for name, (lo, hi) in TIERS["runtimeBins"].items():
        if (lo is None or share >= lo) and (hi is None or share < hi):
            return name
    raise TierError("no runtime bin for share %r" % share)


def step_shares(doc):
    """{posture: (marginal share, cumulative share)} from postureCostEvidence (`none`: 0, 0)."""
    steps = ((doc.get("postureCostEvidence") or {}).get("steps"))
    if not isinstance(steps, dict):
        raise TierError("postureCostEvidence.steps missing")
    out, acc = {"none": (0.0, 0.0)}, 0.0
    for posture, key in TIERS["stepKeys"].items():
        share = (steps.get(key) or {}).get("share_of_none_level")
        if not isinstance(share, (int, float)) or isinstance(share, bool) or not (0 <= share <= 1):
            raise TierError("postureCostEvidence.steps.%s.share_of_none_level is %r, a fraction in [0, 1] expected "
                            "(a percentage would be misbinned)" % (key, share))
        acc += share
        out[posture] = (share, acc)
    return out


def step_tiers(doc):
    """{posture: runtime tier} of the posture steps: the bin of the CUMULATIVE share (decision 101; CUMULATIVE_RUNTIME
    False, planted: of the step's own share)."""
    return {p: _bin(cum if CUMULATIVE_RUNTIME else marg) for p, (marg, cum) in step_shares(doc).items()}


def _cumulative(doc):
    return {p: cum for p, (marg, cum) in step_shares(doc).items()}


def first_posture(postures):
    """The posture whose step first emits the sensor (the last one under the planted RUNTIME_FROM_FIRST_STEP False)."""
    if not postures:
        return None
    order = [p for p in POSTURES if p in postures]
    return order[0] if RUNTIME_FROM_FIRST_STEP else order[-1]


def runtime_tier(postures, by_posture):
    """The tier of the posture step that first (RUNTIME_FROM_FIRST_STEP) emits the sensor; None if unknown."""
    if not postures:
        return None
    return by_posture[first_posture(postures)]


def validate_tiers(doc, catalog):
    if catalog not in TIERS["postureCatalogs"]:
        raise TierError("--tier-catalog %r is not one of %s" % (catalog, TIERS["postureCatalogs"]))
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 1:
        raise TierError("schemaVersion must be 1")
    if not isinstance(doc.get("system"), str):
        raise TierError("system must be a string")
    cats, dk = doc.get("postureCatalogs"), TIERS["postureCatalogDocKeys"][catalog]
    if not isinstance(cats, dict) or dk not in cats:
        raise TierError("postureCatalogs does not describe the requested catalog %r (key %r)" % (catalog, dk))
    sensors = doc.get("sensors")
    if not isinstance(sensors, list) or not sensors:
        raise TierError("sensors must be a non-empty list")
    seen = set()
    for i, s in enumerate(sensors):
        where = "sensors[%d]" % i
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not s["id"]:
            raise TierError("%s: id must be a non-empty string" % where)
        if s["id"] in seen:
            raise TierError("%s: id %r twice" % (where, s["id"]))
        seen.add(s["id"])
        if "effortTier" not in s or s["effortTier"] not in EFFORT_TIERS + (None,) or isinstance(s["effortTier"], bool):
            raise TierError("%s (%s): effortTier %r not in %s or null" % (where, s["id"], s.get("effortTier"),
                                                                        list(EFFORT_TIERS)))
        if "runtimeTier" in s and s["runtimeTier"] not in RUNTIME_TIERS + (None,):
            raise TierError("%s (%s): runtimeTier %r not in %s or null" % (where, s["id"], s["runtimeTier"],
                                                                         list(RUNTIME_TIERS)))
        ps = s.get(catalog)
        if ps is not None:
            if not isinstance(ps, list) or any(p not in POSTURES for p in ps):
                raise TierError("%s (%s): %s must be a list of %s" % (where, s["id"], catalog, list(POSTURES)))
            if ps and ps != list(POSTURES[len(POSTURES) - len(ps):]):
                raise TierError("%s (%s): %s %s is not nested (a suffix of %s)" % (where, s["id"], catalog, ps,
                                                                                  list(POSTURES)))
    step_tiers(doc)
    return len(sensors)


def load_tiers(path, catalog):
    """{sensor id: {effort, runtime, runtimeBasis}} and the file's meta. The ledger id is dropped (never a candidate)."""
    doc = json.loads(Path(path).read_text())
    if VALIDATE_TIERS:
        n = validate_tiers(doc, catalog)
    else:
        n = len(doc["sensors"])
    by_posture = step_tiers(doc) if VALIDATE_TIERS else {"none": RUNTIME_TIERS[0], "selected": ">10%",
                                                        "async": "1-10%", "full": "1-10%"}
    cumulative = _cumulative(doc) if VALIDATE_TIERS else {"none": 0.0, "selected": 0.17, "async": 0.228, "full": 0.288}
    out = {}
    for s in doc["sensors"]:
        if s.get("family") == "ledger" or s["id"].startswith("ledger:"):
            continue
        rt, basis, fp, cum = s.get("runtimeTier"), "declared runtimeTier", None, None
        if "runtimeTier" not in s:
            rt = runtime_tier(s.get(catalog), by_posture)
            fp = first_posture(s.get(catalog))
            cum = None if fp is None else cumulative[fp]
            basis = ("cumulative share of the posture steps up to the one first emitting it, %s catalog (%s)" % (
                catalog, "/".join(s[catalog])) if rt is not None else
                "unknown: no posture membership in the %s catalog" % catalog)
        out[s["id"]] = {"effort": s["effortTier"], "runtime": rt, "runtimeBasis": basis, "firstPosture": fp,
                        "cumulativeShare": cum}
    meta = {"path": str(path), "sha256": sha256(path), "system": doc["system"], "sensors": n, "catalog": catalog,
            "stepTiers": by_posture, "stepShares": {k: (doc["postureCostEvidence"]["steps"].get(k) or {}).get(
                "share_of_none_level") for k in TIERS["stepKeys"].values()},
            "runtimeBasis": "a posture step's CPU share is a property of a group of services; the sensor's tier is "
                            "the tier of the step that first emits it (coordinator default), not a per-sensor "
                            "measurement",
            "runtimeCaveat": "decision 101: the tier is the CUMULATIVE share of the posture steps needed to emit the sensor "
                             "(an async sensor also pays the selected step); a set's runtime cost is the latest first-"
                             "emission step among its members, so a cap is a set-level deployment cost; each frontier "
                             "point reports it (runtimeCost)",
            "cumulativeStepShares": _cumulative(doc)}
    return out, meta


# =========================================================================== caps

def admits(tier, cap, order):
    """Is a sensor of `tier` on an axis admitted by `cap`? `any` admits everything, unknown included; a cap otherwise
    admits a KNOWN tier not above it (TIER_NULL_UNKNOWN False: null is read as the lowest tier)."""
    if cap == ANY:
        return True
    if tier is None:
        return not TIER_NULL_UNKNOWN
    return order.index(tier) <= order.index(cap)


def admitted(V, tiers, e_cap, r_cap):
    if not CAP_FILTER:
        return list(V)
    out = []
    for s in V:
        t = tiers.get(s) or {"effort": None, "runtime": None}
        if admits(t["effort"], e_cap, EFFORT_TIERS) and admits(t["runtime"], r_cap, RUNTIME_TIERS):
            out.append(s)
    return out


def tier_counts(V, tiers, active=None):
    """Counts of V (or of its `active` subset) by effort tier and by runtime tier, unknown as DASH."""
    rows = [s for s in V if active is None or s in active]
    eff = Counter(DASH if (tiers.get(s) or {}).get("effort") is None else str(tiers[s]["effort"]) for s in rows)
    run = Counter(DASH if (tiers.get(s) or {}).get("runtime") is None else tiers[s]["runtime"] for s in rows)
    return {"n": len(rows), "effort": dict(sorted(eff.items())), "runtime": dict(sorted(run.items()))}


# =========================================================================== the frontier

def named_budgets(hours):
    """The budget points, in order. 3/T_r (decision 110) and 6/T_r (decision 112, twice the zero-alarm knot) share T_r."""
    return {"0": 0.0, "3/T_r": (cv.LITERAL_NULL_EVENTS / hours) if hours else None,
            "6/T_r": (2 * cv.LITERAL_NULL_EVENTS / hours) if hours else None, "6/h": cv.FAR_BUDGET_PER_HOUR,
            "inf": INF}


def recurrence(table, V):
    """Decision 112. Returns (the candidates of V with a counted fire in >= RECURRENCE_MIN episodes of at least one class,
    the record). A counted fire = a finite entry of the objective's detection-time table (celf_v3.build_table applies
    `counted`: decision 72 bc, decision 79/84 own-per-class); the class is the episode's regime. RECURRENCE_FILTER False:
    V unchanged (the record says so)."""
    eps = table.episodes
    n_class = Counter(e["regime"] for e in eps)
    per = {}
    for s in V:
        c = Counter(eps[i]["regime"] for i, t in enumerate(table.times.get(s) or []) if t < INF)
        if c:
            per[s] = c
    fired = sorted(per)
    keep = sorted(s for s in fired if max(per[s].values()) >= RECURRENCE_MIN)
    by_class = {r: sorted(s for s in keep if per[s].get(r, 0) >= RECURRENCE_MIN) for r in sorted(n_class)}
    rec = {"rule": "V32_RECURRENCE_RULE (decision 112)", "minEpisodesPerClass": RECURRENCE_MIN,
           "switch": RECURRENCE_FILTER, "episodesPerClass": dict(sorted(n_class.items())),
           "groundSet": len(V), "withCountedFire": len(fired), "recurring": len(keep),
           "removedFromGroundSet": (len(V) - len(keep)) if RECURRENCE_FILTER else 0,
           "removedWithCountedFire": (len(fired) - len(keep)) if RECURRENCE_FILTER else 0,
           "removedWithCountedFireIds": sorted(set(fired) - set(keep)) if RECURRENCE_FILTER else [],
           "recurringByClass": by_class}
    return (keep if RECURRENCE_FILTER else list(V)), rec


def set_runtime(S, tiers):
    """The set-level runtime cost of decision 101: the largest cumulative share of the members' first steps, binned; None
    (unknown) when a member has no posture membership, 0 for the empty set."""
    shares = [(tiers.get(s) or {}).get("cumulativeShare") for s in S]
    unknown = sorted(s for s, x in zip(S, shares) if x is None)
    if unknown:
        return {"cumulativeShare": None, "tier": None, "unknownMembers": len(unknown),
                "note": "— (a member has no posture membership or only a declared tier)"}
    share = max(shares, default=0.0)
    return {"cumulativeShare": share, "tier": _bin(share), "unknownMembers": 0}


def point(obj, table, V_cap, costs, budget, penalty="ttd", with_held_out=True, tiers=None):
    sol = cv.solve(obj, V_cap, {s: costs[s] for s in V_cap}, budget)
    S = sol["preAdmitted"] + sol["chosen"]
    row = {"budget": "inf" if budget == INF else budget, "set": S, "size": len(S), "mode": sol["mode"], "D": sol["D"],
           "DLedger": sol["DLedger"], "g": sol["g"], "charged": sol["charged"], "onlineBound": sol["onlineBound"],
           "DOptLowerBound": sol["DOptLowerBound"], "describe": cv.describe(table, S)}
    if tiers is not None:
        row["runtimeCost"] = set_runtime(S, tiers)
    if with_held_out:
        row["heldOut"] = cv.held_out(table, V_cap, {s: costs[s] for s in V_cap}, budget, penalty)
    return row


def monotone_violations(cells):
    """cells: {(e_cap, r_cap): {budget name: D or None}}. A cap relaxed along either axis that gives a larger D than a
    stricter one at the same budget: a list of (stricter cell, relaxed cell, budget, D stricter, D relaxed)."""
    def lat(caps, order):
        return order.index(caps) if caps != ANY else len(order)
    out = []
    for a, da in cells.items():
        for b, db in cells.items():
            if a == b:
                continue
            if lat(a[0], EFFORT_TIERS) <= lat(b[0], EFFORT_TIERS) and lat(a[1], RUNTIME_TIERS) <= lat(b[1], RUNTIME_TIERS):
                for name, x in da.items():
                    y = db.get(name)
                    if x is not None and y is not None and y > x and not cv.tied(x, y):
                        out.append({"stricter": list(a), "relaxed": list(b), "budget": name, "DStricter": x,
                                    "DRelaxed": y})
    return out


def frontier_rate(J, rate, tiers, declared=None, schedule=None, with_held_out=True):
    """The frontier of one rate: one table and one objective (celf_v3's), the caps restrict only the candidates."""
    a, V, excluded, costs_all, labels, table, obj = cv.arm_setup(J, rate, None, schedule)
    cr = J["calibration"]["primary"]["perRate"][cv.rate_key(rate)]
    hours = cr.get("hours")
    budgets = named_budgets(hours)
    active = set(cv.active(obj, V))
    V_rec, rec = recurrence(table, V)
    V_rec = set(V_rec)
    cells, D_by_cell = [], {}
    for e_cap in EFFORT_CAPS:
        for r_cap in RUNTIME_CAPS:
            by_caps = admitted(V, tiers, e_cap, r_cap)
            V_cap = [s for s in by_caps if s in V_rec]
            if SHARED_COSTS:
                costs = costs_all
            else:                                        # planted: re-derived on the cap's set (the fill moves)
                costs = dict(costs_all)
                ev = [cr["sensors"][s]["honestUpperPerHour"] for s in V_cap
                      if cr["sensors"][s]["honestUpperPerHour"] is not None]
                fill = max(ev) if ev else 0.0
                for s in V_cap:
                    if cr["sensors"][s]["honestUpperPerHour"] is None:
                        costs[s] = fill
            pts = {}
            for name, b in budgets.items():
                pts[name] = (None if b is None else
                             point(obj, table, V_cap, costs, b, a["penalty"], with_held_out, tiers))
            D_by_cell[(e_cap, r_cap)] = {n: (p["D"] if p else None) for n, p in pts.items()}
            cells.append({"maxEffort": e_cap, "maxRuntime": r_cap, "admitted": len(V_cap), "admittedByCaps": len(by_caps),
                          "admittedWithCountedFire": len([s for s in V_cap if s in active]),
                          "points": {n: (p if p else {"note": "— (no %s: the rate has no hours)" % n})
                                     for n, p in pts.items()}})
    ootb = [s for s in V if (tiers.get(s) or {}).get("effort") == 0]
    comps = {"ledger alone": {"sensors": [], "describe": cv.describe(table, [])},
             "full": {"sensors": "V_r (%d)" % len(V), "describe": cv.describe(table, V),
                      "charged": math.fsum(costs_all.values())},
             "out of the box": {"sensors": "every ground-set sensor of effort tier 0 (%d of %d)" % (len(ootb), len(V)),
                                "size": len(ootb), "setMembers": sorted(ootb), "describe": cv.describe(table, ootb),
                                "charged": math.fsum(costs_all[s] for s in ootb),
                                "label": "the upstream system as shipped (effort tier 0), the starting posture; a "
                                         "restriction estimate of `full` cells (decision 80)"}}
    for name, S in sorted((declared or {}).items()):
        if S is None:
            comps[name] = {"sensors": None, "describe": None, "note": "— (not declared)"}
            continue
        inV, out = cv.restrict(S, V)
        comps[name] = {"sensors": inV, "outsideGroundSet": out, "describe": cv.describe(table, inV),
                       "charged": math.fsum(costs_all[s] for s in inV),
                       "label": "restriction estimate (decision 78)"}
    beyond = [s for s in active if (tiers.get(s) or {}).get("effort") != 0]
    axis = {"groundSet": tier_counts(V, tiers), "withCountedFire": tier_counts(V, tiers, active),
            "activeAboveTier0OrUnknown": sorted(beyond),
            "degenerate": not beyond,
            "note": ("no ground-set sensor with a counted fire has an effort tier above 0 or unknown: the effort axis does "
                     "not change any frontier cell (a result, not engineered around)") if not beyond else
                    "%d sensor(s) with a counted fire sit above tier 0 or have an unknown effort tier" % len(beyond)}
    return {"rate": rate, "hours": hours, "groundSet": V, "costs": {s: costs_all[s] for s in V},
            "episodes": [cv.episode_key(e) for e in table.episodes], "folds": [list(k) for k in cv.folds(table)],
            "effortAxis": axis, "runtimeAxis": {"groundSet": tier_counts(V, tiers),
                                                "withCountedFire": tier_counts(V, tiers, active)},
            "grid": cells, "nonMonotone": monotone_violations(D_by_cell),
            "tiersMissingForGroundSet": sorted(s for s in V if s not in tiers), "recurrence": rec, "comparators": comps,
            "deviation": cv.DEVIATION_80, "scope": SCOPE}


# =========================================================================== inputs and output

def check_frozen_celf():
    path = Path(cv.__file__).resolve()
    if path != HERE / "celf_v3.py":
        refuse("celf_v3 imported from %s, not %s" % (path, HERE / "celf_v3.py"))
    got = sha256(path)
    if CHECK_PINS and got != PINNED_CELF_SHA256:
        refuse("celf_v3.py sha256 %s is not the frozen %s" % (got, PINNED_CELF_SHA256))
    return got


def check_parameters_digest(recorded, what, allow_unpinned=False):
    """F5: the registry (parameters_v3_2.json) is pinned like the scripts. `recorded` is the registry digest an artefact
    carries (a readout's v32.parametersV32Sha256, a placement's inputs.parametersV32Sha256). With
    PINNED_PARAMETERS_V32_SHA256 set, the LIVE registry must equal it and so must `recorded`; None = unpinned: `recorded`
    must be the live registry's, and --allow-unpinned is needed, as for the reader's own digest."""
    live = sha256(PARAMETERS_V32)
    pin = PINNED_PARAMETERS_V32_SHA256
    if pin is not None and live != pin:
        refuse("the live registry %s has sha256 %s, not the frozen %s" % (PARAMETERS_V32.name, live, pin))
    if pin is None and not allow_unpinned:
        refuse("the v3.2 registry is not frozen (PINNED_PARAMETERS_V32_SHA256 is None): --allow-unpinned for exploration")
    want = pin or live
    if recorded != want:
        refuse("%s recorded parametersV32Sha256 %r is not %s %s" % (what, recorded, "the frozen" if pin else "the live", want))


def check_readout(J, allow_unpinned=False, allow_unsplit=False):
    """A v3.2 readout (its own script digest; the v3.1 digest it was built on) from a split read."""
    if J.get("version") != "3.2":
        refuse("the readout is not v3.2 (version %r); celf_v3.py takes v3.1 readouts" % J.get("version"))
    installed = sha256(REPO / "research" / "detection-time" / "sweep_analysis_v3_2.py")
    if CHECK_PINS:
        if J.get("v31ScriptSha256") != PINNED_V31_SHA256:
            refuse("the readout was not built on the frozen v3.1 (%r)" % J.get("v31ScriptSha256"))
        want = PINNED_V32_SHA256 or installed
        if J.get("scriptSha256") != want:
            refuse("readout scriptSha256 %r is not %s %s" % (J.get("scriptSha256"),
                                                              "the frozen v3.2" if PINNED_V32_SHA256 else
                                                              "the installed reader", want))
        if PINNED_V32_SHA256 is None and not allow_unpinned:
            refuse("the v3.2 reader is not frozen (PINNED_V32_SHA256 is None): --allow-unpinned for exploration")
        check_parameters_digest((J.get("v32") or {}).get("parametersV32Sha256"), "the readout", allow_unpinned)
    blocks = ((J.get("v32") or {}).get("blockSelection") or {}).get("blocks")
    if REQUIRE_SPLIT and blocks is None and not allow_unsplit:
        refuse("the readout read every block: decision 95 solves the placement on the training blocks only (reader "
               "--blocks <train>); --allow-unsplit for exploration")
    if REQUIRE_SPLIT and blocks is not None:
        applies = set(((J.get("v32") or {}).get("blockSelection") or {}).get("applies") or [])
        held = [e["cell"] for e in J["episodes"] if e.get("heldOut")]
        if held:
            refuse("the training readout holds held-out (test-block) episodes %s: the placement is solved on training "
                   "blocks only" % held[:3])
        stray = sorted({(e.get("studyEpoch"), e["block"]) for e in J["episodes"]
                        if e.get("studyEpoch") not in applies or e["block"] not in blocks}, key=str)
        if stray:
            refuse("the readout's recorded blocks %s do not describe its episodes: (epoch, block) %s is outside the "
                   "selection or not an episode of the campaign-E epoch(s) %s (the label alone is not the split)" % (
                       sorted(blocks), stray, sorted(applies)))
    return blocks


def check_split_registry(split):
    """Decision 100: the split file is the registry's (V32_E_SPLIT) once the registry declares one."""
    if SPLIT_FROM_REGISTRY and E_SPLIT["train"] is not None and (
            sorted(split.get("train") or []) != sorted(E_SPLIT["train"])
            or sorted(split.get("test") or []) != sorted(E_SPLIT["test"])):
        refuse("the split %s is not the registry split %s (V32_E_SPLIT, decision 100)" % (split, E_SPLIT))


def expected_catalog(J):
    """The posture catalog the evidence was produced under (coordinator default): the current runtime catalog for the
    off-path epochs, the v3 catalog for existing campaigns."""
    epochs = ((J.get("v32") or {}).get("epochsRead") or {})
    new = {e for e in epochs if e in _registry()["V32_EPOCH_PROFILES"]}
    return "postureCurrentCatalog" if new else "postures"


def run(J, tiers, declared=None, schedule=None, with_held_out=True):
    rates = sorted({e["rate"] for e in J["episodes"]})
    out = {}
    for r in rates:
        rk = cv.rate_key(r)
        if rk not in J["calibration"]["primary"]["perRate"]:
            out[rk] = {"note": "— (no calibration at this rate)"}
            continue
        try:
            out[rk] = frontier_rate(J, r, tiers, declared, schedule, with_held_out)
        except ValueError as exc:
            out[rk] = {"note": "— (%s)" % exc}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="v3.2 readout JSON (sweep_analysis_v3_2.json), read with --blocks <training>")
    ap.add_argument("--tiers", required=True, help="the declared effort/runtime tier file (schema in the docstring)")
    ap.add_argument("--tier-catalog", required=True, choices=TIERS["postureCatalogs"])
    ap.add_argument("--out", required=True, help="NEW output file; refused if it exists")
    ap.add_argument("--declared", help="JSON {comparator name: [sensor ids] | null} (decision 78)")
    ap.add_argument("--split", help="the declared split file {train: [...], test: [...]} (checked against the readout)")
    ap.add_argument("--allow-unpinned", action="store_true")
    ap.add_argument("--allow-unsplit", action="store_true")
    ap.add_argument("--allow-catalog-mismatch", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        refuse("to write into an existing path: %s" % out)
    celf_sha = check_frozen_celf()
    J = json.loads(Path(a.readout).read_text())
    blocks = check_readout(J, a.allow_unpinned, a.allow_unsplit)
    if CHECK_PINS and expected_catalog(J) != a.tier_catalog and not a.allow_catalog_mismatch:
        refuse("--tier-catalog %s, but the readout's epochs call for %s (the two catalogs disagree on 183 ids): "
               "--allow-catalog-mismatch to override" % (a.tier_catalog, expected_catalog(J)))
    if REQUIRE_SPLIT and not a.split and not a.allow_unsplit:
        refuse("--split is required: decision 95 fixes the training and test blocks before launch and the scorer "
               "checks its test blocks against the placement's recorded split")
    split = None
    if a.split:
        split = json.loads(Path(a.split).read_text())
        if set(split.get("train") or []) & set(split.get("test") or []):
            refuse("the split's train and test blocks overlap")
        check_split_registry(split)
        if blocks is not None and sorted(blocks) != sorted(split.get("train") or []):
            refuse("the readout's blocks %s are not the split's training blocks %s" % (sorted(blocks), split.get("train")))
        sha = ((J.get("v32") or {}).get("blockSelection") or {}).get("splitSha256")
        if sha is not None and sha != sha256(a.split):
            refuse("the split file's sha256 is not the one the readout recorded")
    tiers, meta = load_tiers(a.tiers, a.tier_catalog)
    dec = json.loads(Path(a.declared).read_text()) if a.declared else None
    res = {"version": VERSION, "scope": SCOPE, "system": J.get("system"),
           "split": {"trainBlocks": sorted(blocks) if blocks is not None else None,
                     "test": (split or {}).get("test"), "unsplit": blocks is None},
           "recurrenceRule": dict(RECURRENCE_RULE, switch=RECURRENCE_FILTER),
           "tiers": meta, "caps": {"effort": list(EFFORT_CAPS), "runtime": list(RUNTIME_CAPS)},
           "switches": {k: globals()[k] for k in SWITCHES}, "celfSwitches": {k: getattr(cv, k) for k in cv.SWITCHES},
           "rates": run(J, tiers, dec),
           "inputs": {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "tiers": a.tiers,
                      "tiersSha256": meta["sha256"], "declared": a.declared,
                      "declaredSha256": sha256(a.declared) if a.declared else None, "celfSha256": celf_sha,
                      "parametersV32Sha256": sha256(PARAMETERS_V32), "pinnedV32": PINNED_V32_SHA256,
                      "pinnedParametersV32": PINNED_PARAMETERS_V32_SHA256,
                      "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": sha256(__file__),
                      "python": sys.version}}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(res, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", out)                                    # no number printed: committed unedited before reading
    return 0


if __name__ == "__main__":
    sys.exit(main())
