#!/usr/bin/env python3
"""Placement v3: lazy CELF on per-episode detection times over a frozen v3.1 readout (placement step, step 2 of
research/protocol/BUDGET_PLACEMENT.md).

BINDING. Design research/protocol/PLACEMENT_V3_DESIGN.md rev. 2 (frozen in d9638e1); protocol rounds 21-22
(research/PROTOCOL_DRAFT_20261002.md, decisions 72-81); budget and stop rule research/protocol/BUDGET_PLACEMENT.md
(40e818e). Every placement number this module produces is scope **instance** (one SUT, one rate, one readout).

    uv run python research/placement/celf_v3.py <readout sweep_analysis_v3.json> --out <NEW file.json> \
        [--schedule <cells_v3.py schedule output>] [--declared <comparator sets json>]

It prints only the path it wrote: the output is committed unedited before anyone reads it (BUDGET_PLACEMENT.md step 4).

OBJECTIVE (design §2; Leskovec et al., KDD 2007, §2). T(i,s) = min `ttd_s` over the counted fires of sensor s in
episode i (positional layout of `episodes[].fires[]`: sweep_analysis_v2.py:3611-3613), inf where none. T(i,A) =
min over A ∪ {E}: the ledger E is in every placement (decision 1). g(A) = R(A ∪ E) - R(E), R(A) = sum_i P(i)
[pi_i(inf) - pi_i(T(i,A))]; D(A) = sum_i P(i) pi_i(T(i, A ∪ E)) = D(E) - g(A). Penalties: `ttd` pi = min(t, H_i)
(primary, decision 15); `impact` pi = failed requests scheduled in [onset, onset + min(t, H_i)] (decision 77, the
P2 count, a miss charged the whole hold; denominator: episodes with >= 1 such request); `detection` pi = 1[t = inf].
P(i) uniform over fault classes (regimes) at the rate, then over the class's episodes (engineering default).

RULES, each a switch below that only tests/test_placement_v3.py flips (a planted defect must make a check fail):
  decision 72 (BC_SENSOR_MISS, BC_LEDGER_COUNTS): primary `e-only`: a by-construction (bcFlags != []) fire counts for
     the ledger E only; a sensor's BC fire is a miss. Arms `miss-all`, `count-all`.
  decision 73 (COST_NULL_RULE): primary cost = `honestUpperPerHour`; a sensor with no held-out evidence (null) costs
     the rate's largest evidenced `honestUpperPerHour` over V_r. Literal arm (decisions 67/71): `celfCost`
     (= honestPerHour; an evidenced 0 costs 0 and is pre-admitted), null -> 3/T_r, T_r = perRate[r].hours.
  decision 75 (PER_RATE): one placement per rate.
  decision 76: a Pareto sweep over the knapsack budget B on sum c(s); grid = 0, the cumulative costs along the
     cost-benefit order at B = inf, the named points 3/T_r and 6/h (decision 48's number in a new role) and inf.
  decision 79 (OWN_OUT): a fire on the fault target (`own`) is a miss in the primary; arms `include` and `only`
     (the X:own view).
  decision 80: every comparator and placement is a restriction of `full` cells, a declared deviation (labelled).
  decision 81: modality arms T; T + L; every collected family (= primary).
  solver (design §5): cost-0 sensors with positive gain pre-admitted greedily (PRE_ADMIT_ZERO; gain/0 never
     computed), then lazy greedy (LAZY_REEVALUATE) once at unit cost and once cost-benefit, the larger g kept
     (BEST_OF_UC_CB), ties to the canonical (smallest) sensor id (CANONICAL_TIES), stop at zero gain (STOP_AT_ZERO).
     Online bound (ONLINE_FRACTIONAL): g(OPT_B) <= g(A) + the fractional-knapsack sum of the marginal gains ordered
     by gain/cost up to B (Leskovec et al. 2007 §3; check the theorem number against the KDD PDF before citing). It is
     an additive certificate on mean TTD: D(OPT_B) >= D(A) - bound. (1 - 1/e) is never quoted for TTD.
  sufficient conditions of submodularity kept (design §2): (a) T(i,s) independent of A; (b) the detector per sensor
     fixed (the readout's OR of calibrated rules); (c) a miss charged a finite H_i (MISS_AT_HOLD); (d) scores per
     episode, then averaged (PER_EPISODE).
  held-out folds (FOLD_KEY): leave one (harness, block) out (BUDGET_PLACEMENT.md step 4; the design's
     (campaignIndex, block) is the same partition on all three training readouts, checked by structure only); the
     selection is re-run on the other folds and scored on the held-out one; the fold mean is the headline beside the
     in-sample value.
  false alarms: the honest nested union of a chosen set needs the cells (cells_v3.py `far`); here `—`.
"""
from __future__ import annotations

import argparse
import bisect
import heapq
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DETECTION_TIME = REPO / "research" / "detection-time"

VERSION = "placement-v3.0"
SCOPE = "instance"
DEVIATION_80 = ("scored by restriction of `full` cells: a declared deviation from protocol §3 (:102), decision 80; "
                "decision 46.3's live run of the chosen placement is the later check")

# ----------------------------------------------------------------------------- switches (tests flip them)
MISS_AT_HOLD = True           # (c) a miss is charged H_i (False: a miss charged 0)
PER_EPISODE = True            # (d) per-episode scores, then averaged (False: min over sensors of mean penalties)
CLASS_WEIGHTS = True          # P(i) uniform over classes, then episodes (False: uniform over episodes)
LEDGER_FIXED = True           # decision 1: E in every placement (False: g and D computed without E)
BC_SENSOR_MISS = True         # decision 72: a sensor's BC fire is a miss under `e-only` (False: it counts)
BC_LEDGER_COUNTS = True       # decision 72: E's BC fire counts under `e-only` (False: it is a miss)
OWN_OUT = True                # decision 79: an own fire is a miss in the primary (False: it counts)
COST_NULL_RULE = "largest-evidenced-upper"   # decision 73 (planted: "3/T", the inversion decision 73 removes)
PER_RATE = True               # decision 75: the instance holds the rate's episodes only (False: every rate's)
PRE_ADMIT_ZERO = True         # cost 0: pre-admitted, never divided by (False: cost-0 sensors enter the CB queue)
LAZY_REEVALUATE = True        # CELF: a stale queue head is re-evaluated before it is accepted (False: accepted stale)
BEST_OF_UC_CB = True          # the larger of unit-cost and cost-benefit greedy (False: cost-benefit only)
STOP_AT_ZERO = True           # greedy stops at zero marginal gain (False: zero-gain sensors are added while affordable)
CANONICAL_TIES = True         # ties to the smallest sensor id (False: the largest)
ONLINE_FRACTIONAL = True      # online bound with the fractional item (False: whole items that fit only)
FOLD_KEY = ("harness", "block")   # held-out unit (planted: ("block",), which merges OTel's sweep b1 with B b1)
FOLD_SELECT_TRAIN_ONLY = True     # a fold's selection sees the other folds only (False: all episodes, a leak)
TIE_TOLERANCE = True              # keys equal within KEY_REL_TOL are ties, broken canonically (False: exact floats;
                                  # a stale lazy key one ulp off a fresh one then picks a non-canonical sensor)
GRID_UNION = True                 # decision 81: every arm of a rate on the union of all arms' knots (False: own knots)

# ----------------------------------------------------------------------------- declared values
FAR_BUDGET_PER_HOUR = 6.0     # decision 76: 6/h named, the number from decision 48 in a new role
LITERAL_NULL_EVENTS = 3.0     # decision 71: "the zero-alarm upper bound 3/T of its rate", taken as written
KEY_REL_TOL = 1e-9            # engineering default: greedy keys / gains within this relative distance are ties
GAIN_ABS_TOL = 1e-12          # engineering default: a gain at or below this is zero (smallest real gain ~1e-8)
PINNED_V3_SHA256 = "2e7ec5c387fa906a02026f0d1a5212b974f17751c24f76526a1d8418b2fd4fdd"   # readout scriptSha256
FIRE = {"family": 0, "sensorId": 1, "rule": 2, "ttd": 3, "dir": 4, "own": 5, "onPath": 6, "counts": 7, "bc": 8,
        "movedBy": 9}         # sweep_analysis_v2.py:3611-3613 (episode_detail), reused by v3
LEDGER_FAMILY = "E"
BC_RULES = ("e-only", "miss-all", "count-all")
OWN_RULES = ("exclude", "include", "only")
COST_RULES = ("upper", "literal")
PENALTIES = ("ttd", "impact", "detection")
INF = math.inf

ARMS = {   # decision: single change from the primary
    "primary": {},
    "cost-literal (73)": {"cost": "literal"},
    "bc-miss-all (72)": {"bc": "miss-all"},
    "bc-count-all (72)": {"bc": "count-all"},
    "own-include (79a)": {"own": "include"},
    "own-only, X:own view (79)": {"own": "only"},
    "modality-T (81a)": {"families": ("T",)},
    "modality-T+L (81a)": {"families": ("T", "L")},
    "without-appearOnly (design §3)": {"appear_only": False},
    "impact (77, secondary row)": {"penalty": "impact"},
    "detection (secondary row)": {"penalty": "detection"},
}
PRIMARY = {"cost": "upper", "bc": "e-only", "own": "exclude", "families": None, "appear_only": True,
           "penalty": "ttd"}


def _e_rules():
    """The ledger rules v2.4/v3 read as E (sweep_analysis_v2.E_RULES; col_fire(e, "E", True) restricts to them)."""
    if str(DETECTION_TIME) not in sys.path:
        sys.path.insert(0, str(DETECTION_TIME))
    import sweep_analysis_v2 as v24  # noqa: E402  frozen 098f3e0, read only
    return tuple(v24.E_RULES)


E_RULES = _e_rules()


def rate_key(r):
    return "%g" % r


def tied(a, b):
    """Two greedy keys (or gains) are a tie: equal within KEY_REL_TOL (TIE_TOLERANCE; False: exact equality)."""
    if not TIE_TOLERANCE:
        return a == b
    return math.isclose(a, b, rel_tol=KEY_REL_TOL, abs_tol=GAIN_ABS_TOL)


def positive(g):
    return g > GAIN_ABS_TOL


def canonical_order(keys):
    """Sensors by key, descending, ties (`tied` to the group's leader) to the smallest id."""
    out, rest = [], sorted(keys, key=lambda s: (-keys[s], s))
    while rest:
        lead = rest[0]
        group = [s for s in rest if tied(keys[s], keys[lead])]
        out += sorted(group)
        gs = set(group)
        rest = [s for s in rest if s not in gs]
    return out


# =========================================================================== readout -> detection-time table

def counted(fire, bc, own):
    """Does this fire define T(i, s) under the BC rule `bc` (decision 72) and the own rule `own` (decision 79)?
    The ledger mirrors the frozen reading col_fire(e, "E", True) = family_ttd(E, own=False, bc=True, E_RULES)."""
    fam, rule, cnt, is_own, flags = (fire[FIRE["family"]], fire[FIRE["rule"]], fire[FIRE["counts"]],
                                     fire[FIRE["own"]], fire[FIRE["bc"]])
    if not cnt:
        return False
    is_bc = bool(flags)
    if fam == LEDGER_FAMILY:
        if rule not in E_RULES or is_own:
            return False
        if bc == "miss-all":
            return not is_bc
        if bc == "e-only":
            return (not is_bc) or BC_LEDGER_COUNTS
        return True
    if own == "exclude" and is_own and OWN_OUT:
        return False
    if own == "only" and not is_own:
        return False
    if bc == "miss-all":
        return not is_bc
    if bc == "e-only":
        return (not is_bc) or not BC_SENSOR_MISS
    return True


def rate_episodes(J, rate):
    """The rate's fault episodes (decision 75), in the readout's order."""
    rk = rate_key(rate)
    return [e for e in J["episodes"] if rate_key(e["rate"]) == rk or not PER_RATE]


def ground_set(J, rate, families=None, appear_only=True):
    """V_r = {s : placeable at r, family != E} (decision 67 pt 3), restricted to `families` (decision 81) and without
    appear-only sensors when appear_only is False. Returns (sorted V, {excluded sensor: reason})."""
    sensors = J["calibration"]["primary"]["perRate"][rate_key(rate)]["sensors"]
    V, out = [], {}
    for sid, s in sorted(sensors.items()):
        if s["family"] == LEDGER_FAMILY:
            continue
        if not s["placeable"]:
            out[sid] = "not placeable: " + "; ".join(
                "%s %s" % (k, ",".join(s.get(k) or [])) for k in ("dropped", "unarmed", "inert") if s.get(k)) \
                if any(s.get(k) for k in ("dropped", "unarmed", "inert")) else "not placeable: no calibrated rule"
        elif families is not None and s["family"] not in families:
            out[sid] = "family %s outside the arm %s" % (s["family"], "+".join(families))
        elif not appear_only and s.get("appearOnly"):
            out[sid] = "appear-only (arm without them)"
        else:
            V.append(sid)
    return V, out


def costs_of(J, rate, rule="upper"):
    """{sensor: cost} and {sensor: label} over the full V_r (every family, appear-only included), so that every arm
    shares one cost table (decision 81: same costs). `upper` (decision 73) / `literal` (decisions 67, 71)."""
    cr = J["calibration"]["primary"]["perRate"][rate_key(rate)]
    V, _ = ground_set(J, rate)
    sensors = cr["sensors"]
    costs, label = {}, {}
    if rule == "upper":
        ev = [sensors[s]["honestUpperPerHour"] for s in V if sensors[s]["honestUpperPerHour"] is not None]
        if COST_NULL_RULE == "largest-evidenced-upper":
            if not ev:
                raise ValueError("rate %s: no sensor of V_r has held-out evidence; decision 73's fill is — "
                                 % rate_key(rate))
            fill, fill_label = max(ev), "no evidence: the rate's largest evidenced upper bound (decision 73)"
        else:                                              # planted defect: decision 71's 3/T inside the upper arm
            fill, fill_label = LITERAL_NULL_EVENTS / cr["hours"], "no evidence: 3/T_r (planted)"
        for s in V:
            u = sensors[s]["honestUpperPerHour"]
            costs[s], label[s] = (u, "honestUpperPerHour") if u is not None else (fill, fill_label)
    elif rule == "literal":
        for s in V:
            c = sensors[s]["celfCost"]
            if c is None:
                costs[s], label[s] = LITERAL_NULL_EVENTS / cr["hours"], "bound, no evidence (3/T_r, decision 71)"
            else:
                costs[s], label[s] = c, ("evidenced 0: pre-admitted (decision 67)" if c == 0 else "celfCost")
    else:
        raise ValueError(rule)
    for s, c in costs.items():
        if c is None or not (c >= 0) or math.isnan(c):
            raise ValueError("sensor %s: cost %r" % (s, c))
    return costs, label


class Table:
    """Per-episode detection times of one rate under one (bc, own) reading, plus each episode's failed-request
    schedule when given (cells_v3.py `schedule`)."""

    def __init__(self, episodes, te, times, schedule=None):
        self.episodes, self.te, self.times = episodes, te, times
        self.failed = schedule

    def T(self, s):
        return self.times.get(s) or [INF] * len(self.episodes)


def episode_key(e):
    return (e["regime"], rate_key(e["rate"]), e["block"], e.get("campaignIndex", 0), e.get("harness", "sweep"))


def build_table(J, rate, V, bc="e-only", own="exclude", schedule=None):
    """T(i, E) and T(i, s) for s in V at the rate; fires of sensors outside V are ignored (counted). schedule:
    cells_v3.py output; joined on (regime, rate, block, campaignIndex, harness) and checked on onset and hold."""
    if bc not in BC_RULES or own not in OWN_RULES:
        raise ValueError((bc, own))
    eps = rate_episodes(J, rate)
    Vs = set(V)
    te, times, outside = [], defaultdict(lambda: [INF] * len(eps)), Counter()
    for i, e in enumerate(eps):
        best_e = INF
        for f in e["fires"]:
            sid = f[FIRE["sensorId"]]
            if f[FIRE["family"]] == LEDGER_FAMILY:
                if counted(f, bc, own):
                    best_e = min(best_e, f[FIRE["ttd"]])
                continue
            if sid not in Vs:
                outside[sid] += 1
                continue
            if counted(f, bc, own):
                times[sid][i] = min(times[sid][i], f[FIRE["ttd"]])
        te.append(best_e)
    failed = None
    if schedule is not None:
        rows = {}
        for r in schedule["episodes"]:
            k = episode_key(r)
            if k in rows:
                raise ValueError("schedule: episode %r given twice" % (k,))
            rows[k] = r
        failed = []
        for e in eps:
            r = rows.get(episode_key(e))
            if r is None:
                raise ValueError("schedule: no row for episode %r" % (episode_key(e),))
            if r["onsetMono"] != e["onset"]["mono"] or r["holdSeconds"] != e["holdSeconds"]:
                raise ValueError("schedule: episode %r onset/hold differ from the readout" % (episode_key(e),))
            failed.append((r["onsetMono"], sorted(r["failedScheduled"])))
    t = Table(eps, te, dict(times), failed)
    t.outside = dict(outside)
    return t


def tie_margin(table, margins):
    """Decision 35's arm as a per-(i, s) transform (design §2): T'(i,s) = T(i,E) where T(i,E) - m_i <= T(i,s) <
    T(i,E). margins: per-episode m_i (MARGIN_RULE). Keeps the facility-location form. Returns a new Table."""
    new = {}
    for s, ts in table.times.items():
        row = []
        for i, t in enumerate(ts):
            e = table.te[i]
            row.append(e if (e < INF and e - margins[i] <= t < e) else t)
        new[s] = row
    out = Table(table.episodes, table.te, new, table.failed)
    out.outside = getattr(table, "outside", {})
    return out


# =========================================================================== the objective

class Objective:
    """g and D over the episodes `idx` of a table under one penalty."""

    def __init__(self, table, idx=None, penalty="ttd"):
        if penalty not in PENALTIES:
            raise ValueError(penalty)
        if penalty == "impact" and table.failed is None:
            raise ValueError("impact needs the failed-request schedule (cells_v3.py schedule)")
        idx = list(range(len(table.episodes))) if idx is None else list(idx)
        self.table, self.penalty = table, penalty
        if penalty == "impact":       # denominator: episodes with >= 1 failed request in the hold (design §2)
            idx = [i for i in idx if self._pi(i, INF) > 0]
        self.idx = idx
        self.w = self._weights(idx)
        self.miss = [self._pi(i, INF) for i in idx]
        self.pe = [self._pi(i, table.te[i]) if LEDGER_FIXED else self._pi(i, INF) for i in idx]
        self._pen = {}

    def _weights(self, idx):
        if not idx:
            return []
        eps = self.table.episodes
        if not CLASS_WEIGHTS:
            return [1.0 / len(idx)] * len(idx)
        per = Counter(eps[i]["regime"] for i in idx)
        return [1.0 / len(per) / per[eps[i]["regime"]] for i in idx]

    def _pi(self, i, t):
        e = self.table.episodes[i]
        H = e["holdSeconds"]
        if self.penalty == "ttd":
            if t == INF:
                return H if MISS_AT_HOLD else 0.0
            return min(t, H)
        if self.penalty == "detection":
            return 1.0 if t == INF else 0.0
        a, sched = self.table.failed[i]
        t_end = a + (t if t < H else H)            # v2.4: a + (ttd if caught else holdSeconds), capped at the hold
        return float(bisect.bisect_right(sched, t_end) - bisect.bisect_left(sched, a))

    def pen(self, s):
        if s not in self._pen:
            T = self.table.T(s)
            self._pen[s] = [self._pi(i, T[i]) for i in self.idx]
        return self._pen[s]

    def D(self, S):
        """Penalised mean over the episodes, E in the set (LEDGER_FIXED)."""
        if not self.idx:
            return None
        if not PER_EPISODE:                            # planted: min over members of their mean penalties
            means = [sum(w * p for w, p in zip(self.w, self.pe))]
            means += [sum(w * min(p, q) for w, p, q in zip(self.w, self.pe, self.pen(s))) for s in S]
            return min(means)
        m = list(self.pe)
        for s in S:
            m = [min(a, b) for a, b in zip(m, self.pen(s))]
        return sum(w * x for w, x in zip(self.w, m))

    def D_ledger(self):
        return self.D(())

    def value(self, S):
        """g(S) = D({E}) - D(S ∪ E) (= R(S ∪ E) - R(E)); with LEDGER_FIXED off, R(S) = D(∅) - D(S)."""
        if not self.idx:
            return 0.0
        return self.D_ledger() - self.D(S)


# =========================================================================== solver

def _fits(chosen_costs, c, budget):
    return budget == INF or math.fsum(chosen_costs + [c]) <= budget


def greedy(obj, cands, costs, budget, mode, base=()):
    """Lazy greedy (CELF, Leskovec et al. 2007 §3) from `base` over `cands`: mode `UC` picks the largest marginal
    gain, `CB` the largest gain/cost, both among the affordable (sum of the chosen cands' costs <= budget). Keys
    within KEY_REL_TOL are ties to the canonical id: before a fresh head is accepted every stale entry tied with it is
    re-evaluated, so the lazy pick equals the plain greedy pick. Stops at zero gain. Returns {order, g, cost}."""
    if mode not in ("UC", "CB"):
        raise ValueError(mode)
    rank = {s: i for i, s in enumerate(sorted(cands, reverse=not CANONICAL_TIES))}
    S, order, spent = list(base), [], []
    cur = obj.value(S)

    def entry(s, rnd):
        gain = obj.value(S + [s]) - cur
        return [gain if mode == "UC" else gain / costs[s], s, rnd, gain]

    pool = [entry(s, 0) for s in cands if _fits([], costs[s], budget)]
    heap = [(-e[0], rank[e[1]], i) for i, e in enumerate(pool)]
    heapq.heapify(heap)
    rnd = 0
    while heap:
        _, _, i = heap[0]
        key, s, r, gain = pool[i]
        if not _fits(spent, costs[s], budget):
            heapq.heappop(heap)                         # never affordable again: spending only grows
            continue
        if r != rnd and LAZY_REEVALUATE:
            heapq.heappop(heap)
            pool[i] = entry(s, rnd)
            heapq.heappush(heap, (-pool[i][0], rank[s], i))
            continue
        # the head is fresh (or LAZY_REEVALUATE is off): its tie group, stale members refreshed first
        group = [h for h in heap if tied(pool[h[2]][0], key) or pool[h[2]][0] > key]
        stale = [h for h in group if pool[h[2]][2] != rnd and LAZY_REEVALUATE
                 and _fits(spent, costs[pool[h[2]][1]], budget)]
        if stale:
            for h in stale:
                j = h[2]
                pool[j] = entry(pool[j][1], rnd)
            heap = [(-pool[h[2]][0], rank[pool[h[2]][1]], h[2]) for h in heap]
            heapq.heapify(heap)
            continue
        live = [h for h in group if _fits(spent, costs[pool[h[2]][1]], budget)]
        best = max(pool[h[2]][0] for h in live)
        pick = min((h for h in live if tied(pool[h[2]][0], best)), key=lambda h: h[1])
        key, s, r, gain = pool[pick[2]]
        if not positive(gain) and STOP_AT_ZERO:
            break
        heap.remove(pick)
        heapq.heapify(heap)
        S.append(s)
        order.append(s)
        spent.append(costs[s])
        cur = obj.value(S)
        rnd += 1
    return {"order": order, "g": cur, "cost": math.fsum(spent)}


def active(obj, V):
    """The sensors whose penalty is below a miss's in some episode of the objective. Every other sensor has zero
    marginal gain on every set (pi_i(T(i,s)) = pi_i(inf) >= the current minimum), so leaving it out of the queues is
    exact; it only keeps the sweep fast (V_r has ~1100 sensors on OTel, <= 19 with a counted fire)."""
    return [s for s in V if any(p < m for p, m in zip(obj.pen(s), obj.miss))]


def pre_admit(obj, V, costs):
    """Cost-0 sensors with positive marginal gain, added greedily until none has any (stop at zero gain): the same g
    as admitting every cost-0 sensor, because a cost-0 sensor left out has zero marginal gain."""
    zero = [s for s in active(obj, V) if costs[s] == 0]
    return greedy(obj, zero, {s: 1.0 for s in zero}, INF, "UC")["order"]


def online_bound(obj, A, cands, costs, budget):
    """g(OPT_B) - g(A) <= sum of the fractional knapsack over the marginal gains delta_s = g(A ∪ s) - g(A) of the
    cands not in A, ordered by delta/cost, up to B (Leskovec et al. 2007 §3). Cost-0 cands with delta > 0 are added
    whole (never divided by). B = inf: every positive delta."""
    A = list(A)
    cur = obj.value(A)
    inA = set(A)
    free, items = 0.0, []
    for s in sorted(active(obj, cands)):
        if s in inA:
            continue
        d = obj.value(A + [s]) - cur
        if not positive(d):
            continue
        if costs[s] == 0:
            free += d
        else:
            items.append((-(d / costs[s]), s, d, costs[s]))
    items.sort()
    total, used = free, []
    for _, s, d, c in items:
        if _fits(used, c, budget):
            total += d
            used.append(c)
            continue
        if ONLINE_FRACTIONAL:
            total += d * (budget - math.fsum(used)) / c
        break
    return total


def solve(obj, V, costs, budget):
    """Pre-admit cost 0, then the better of UC and CB lazy greedy on the residual problem under `budget`, with the
    online bound. Ties between UC and CB: the smaller cost, then UC (engineering default)."""
    Z = pre_admit(obj, V, costs) if PRE_ADMIT_ZERO else []
    zs = set(Z)
    resid = [s for s in active(obj, V) if s not in zs and (costs[s] > 0 or not PRE_ADMIT_ZERO)]
    uc = greedy(obj, resid, costs, budget, "UC", Z)
    cb = greedy(obj, resid, costs, budget, "CB", Z)
    if BEST_OF_UC_CB:                                  # larger g; tied g: smaller cost; tied cost: UC
        if tied(uc["g"], cb["g"]):
            pick, mode = (cb, "CB") if (cb["cost"] < uc["cost"] and not tied(cb["cost"], uc["cost"])) else (uc, "UC")
        else:
            pick, mode = (uc, "UC") if uc["g"] > cb["g"] else (cb, "CB")
    else:
        pick, mode = cb, "CB"
    chosen = Z + pick["order"]
    bound = online_bound(obj, chosen, resid, costs, budget)
    D = obj.D(chosen)
    return {"preAdmitted": Z, "chosen": pick["order"], "mode": mode, "g": pick["g"], "gUC": uc["g"], "gCB": cb["g"],
            "charged": pick["cost"], "D": D, "DLedger": obj.D_ledger(), "onlineBound": bound,
            "DOptLowerBound": (D - bound) if D is not None else None}


def top_k(obj, V, k):
    """Up to k sensors with the largest positive singleton gain (ties canonical): the 'individually best'
    comparator. Never padded with zero-gain sensors: k' <= k, the shortfall recorded by the caller."""
    gain = {s: obj.value([s]) for s in active(obj, V)}
    return canonical_order({s: g for s, g in gain.items() if positive(g)})[:k]


def top_k_row(obj, table, V, k, costs):
    tk = top_k(obj, V, k)
    return {"sensors": tk, "requested": k, "shortfall": k - len(tk), "describe": describe(table, tk),
            "charged": math.fsum(costs[s] for s in tk)}


def budget_grid(obj, V, costs, hours):
    """Decision 76: 0, the cumulative charged costs along the CB order at B = inf, 3/T_r, 6/h, inf; with names."""
    Z = pre_admit(obj, V, costs) if PRE_ADMIT_ZERO else []
    zs = set(Z)
    resid = [s for s in active(obj, V) if s not in zs and (costs[s] > 0 or not PRE_ADMIT_ZERO)]
    cb = greedy(obj, resid, costs, INF, "CB", Z)
    pts = {0.0: ["0"]}
    for j in range(1, len(cb["order"]) + 1):
        pts.setdefault(math.fsum(costs[s] for s in cb["order"][:j]), [])
    named = {"3/T_r": LITERAL_NULL_EVENTS / hours if hours else None, "6/h": FAR_BUDGET_PER_HOUR}
    for name, b in named.items():
        if b is not None:
            pts.setdefault(b, []).append(name)
    pts.setdefault(INF, []).append("inf")
    return sorted(pts.items())


# =========================================================================== evaluation

FOLD_DEFAULTS = {"harness": "sweep", "campaignIndex": 0}     # v3's own defaults (analyse3)


def fold_of(e):
    return tuple(e.get(k, FOLD_DEFAULTS.get(k)) for k in FOLD_KEY)


def folds(table):
    """{fold key: [episode index]} (FOLD_KEY)."""
    out = defaultdict(list)
    for i, e in enumerate(table.episodes):
        out[fold_of(e)].append(i)
    return dict(sorted(out.items(), key=lambda kv: tuple(str(x) for x in kv[0])))


def fold_merges(table):
    """Fold keys holding episodes of more than one campaign (printed; a (harness, block) fold of two campaigns of one
    harness is still a coherent leave-out, just a larger one)."""
    out = {}
    for k, idx in folds(table).items():
        camps = sorted({table.episodes[i].get("campaignIndex", 0) for i in idx})
        if len(camps) > 1:
            out[str(k)] = camps
    return out


def evaluate(table, S, penalty):
    o = Objective(table, penalty=penalty)
    if not o.idx:
        return None
    return {"D": o.D(S), "DLedger": o.D_ledger(), "g": o.value(S), "episodes": len(o.idx)}


def describe(table, S):
    """D / detection / impact of a set (E always in), each over its own denominator."""
    out = {}
    for p in PENALTIES:
        if p == "impact" and table.failed is None:
            out[p] = None
            continue
        out[p] = evaluate(table, S, p)
    det = Objective(table, penalty="detection")
    m = list(det.pe)
    for s in S:
        m = [min(a, b) for a, b in zip(m, det.pen(s))]
    out["detectedEpisodes"] = [sum(1 for x in m if x == 0), len(m)]
    return out


def held_out(table, V, costs, budget, penalty):
    """Leave one fold out: the selection on the other folds, scored on the held-out one; the top-k comparator
    selected the same way. Returns per-fold rows and the fold means (`—` where no fold is scorable)."""
    rows = []
    fl = folds(table)
    for key, test in fl.items():
        train = [i for f, idx in fl.items() if f != key or not FOLD_SELECT_TRAIN_ONLY for i in idx]
        tr = Objective(table, train, penalty)
        te = Objective(table, test, penalty)
        if not tr.idx or not te.idx:
            rows.append({"fold": list(key), "episodes": len(test), "D": None, "note": "— (no scorable episode)"})
            continue
        sol = solve(tr, V, costs, budget)
        S = sol["preAdmitted"] + sol["chosen"]
        tk = top_k(tr, V, len(S))
        rows.append({"fold": list(key), "episodes": len(te.idx), "chosen": S, "D": te.D(S), "DLedger": te.D_ledger(),
                     "g": te.value(S), "topK": tk, "topKShortfall": len(S) - len(tk), "DTopK": te.D(tk)})
    ok = [r for r in rows if r.get("D") is not None]
    mean = (lambda k: (sum(r[k] for r in ok) / len(ok)) if ok else None)
    return {"key": list(FOLD_KEY), "folds": rows, "foldMeanD": mean("D"), "foldMeanDLedger": mean("DLedger"),
            "foldMeanG": mean("g"), "foldMeanDTopK": mean("DTopK"), "foldsScored": [len(ok), len(rows)]}


def restrict(S, V):
    Vs = set(V)
    return sorted(s for s in S if s in Vs), sorted(s for s in S if s not in Vs)


NAMED = ("0", "3/T_r", "6/h", "inf")


def arm_setup(J, rate, arm, schedule):
    """(arm, V, excluded, costs, labels, table, objective or None) of one arm at one rate."""
    a = dict(PRIMARY, **(arm or {}))
    V, excluded = ground_set(J, rate, a["families"], a["appear_only"])
    costs_all, labels = costs_of(J, rate, a["cost"])
    costs = {s: costs_all[s] for s in V}
    table = build_table(J, rate, V, a["bc"], a["own"], schedule)
    obj = None if (a["penalty"] == "impact" and table.failed is None) else Objective(table, penalty=a["penalty"])
    return a, V, excluded, costs, labels, table, obj


def arm_knots(J, rate, arm, schedule):
    a, V, _, costs, _, _, obj = arm_setup(J, rate, arm, schedule)
    if obj is None:
        return []
    return budget_grid(obj, V, costs, J["calibration"]["primary"]["perRate"][rate_key(rate)].get("hours"))


def union_grid(per_arm):
    """{arm: [(budget, names)]} -> [(budget, names, arms whose own grid has the knot)] (GRID_UNION, decision 81)."""
    pts = {}
    for name, grid in per_arm.items():
        for b, names in grid:
            x = pts.setdefault(b, [set(), set()])
            x[0].update(names)
            x[1].add(name)
    return [(b, sorted(n), sorted(arms)) for b, (n, arms) in sorted(pts.items())]


def place_rate(J, rate, arm=None, schedule=None, declared=None, k_max=None, grid=None):
    """One arm at one rate: ground set, costs, the Pareto sweep (each point with folds and top-k), comparators.
    grid: [(budget, names, source arms)] shared by the rate's arms (run(): the union of every arm's knots); None: the
    arm's own knots. Each point is labelled named (0, 3/T_r, 6/h, inf) or data-derived (a cumulative cost along some
    arm's in-sample CB order: its held-out rows are at an in-sample-indexed budget)."""
    a, V, excluded, costs, labels, table, obj = arm_setup(J, rate, arm, schedule)
    cr = J["calibration"]["primary"]["perRate"][rate_key(rate)]
    if obj is None:
        return {"arm": a, "note": "— (impact needs cells_v3.py schedule)"}
    if grid is None:
        grid = [(b, n, ["this arm"]) for b, n in budget_grid(obj, V, costs, cr.get("hours"))]
    points = []
    for b, names, src in grid:
        sol = solve(obj, V, costs, b)
        S = sol["preAdmitted"] + sol["chosen"]
        named = [n for n in names if n in NAMED]
        points.append(dict(sol, budget=("inf" if b == INF else b), names=names, set=S,
                           pointKind="named" if named else "data-derived",
                           dataDerived=bool(set(names) - set(NAMED)) or not named, knotFromArms=src,
                           costs={s: costs[s] for s in S}, describe=describe(table, S),
                           topK=top_k_row(obj, table, V, len(S), costs),
                           heldOut=held_out(table, V, costs, b, a["penalty"]),
                           placementFar="— (cells_v3.py far: honest nested union, with and without E)"))
    comps = {"ledger alone": {"sensors": [], "describe": describe(table, [])},
             "full": {"sensors": "V_r (%d)" % len(V), "describe": describe(table, V),
                      "charged": math.fsum(costs.values())}}
    for name, S in sorted((declared or {}).items()):
        if S is None:
            comps[name] = {"sensors": None, "describe": None, "note": "— (not declared)"}
            continue
        inV, out = restrict(S, V)
        comps[name] = {"sensors": inV, "outsideGroundSet": out, "describe": describe(table, inV),
                       "charged": math.fsum(costs[s] for s in inV), "label": "restriction estimate (decision 78)"}
    card = None
    if k_max:
        unit = {s: 1.0 for s in V}
        card = [dict(solve(obj, V, unit, k), k=k) for k in range(1, k_max + 1)]
    fires = sorted(s for s, ts in table.times.items() if any(t < INF for t in ts))
    return {"arm": {k: (list(v) if isinstance(v, tuple) else v) for k, v in a.items()}, "rate": rate,
            "hours": cr.get("hours"), "groundSet": V, "excluded": excluded, "sensorsWithCountedFire": fires,
            "firesOutsideGroundSet": table.outside, "costs": costs, "costLabels": {s: labels[s] for s in V},
            "episodes": [episode_key(e) for e in table.episodes], "folds": [list(k) for k in folds(table)],
            "foldsMergingCampaigns": fold_merges(table), "pareto": points, "comparators": comps,
            "cardinality": card, "deviation": DEVIATION_80, "scope": SCOPE}


def run(J, schedule=None, declared=None, arms=None, k_max=None):
    """Every arm at every rate of the readout (decision 75). A rate without calibration is `—`."""
    rates = sorted({e["rate"] for e in J["episodes"]})
    out = {}
    arms = arms or ARMS
    out = {name: {} for name in arms}
    grids = {}
    for r in rates:
        rk = rate_key(r)
        if rk not in J["calibration"]["primary"]["perRate"]:
            for name in arms:
                out[name][rk] = {"note": "— (no calibration at this rate)"}
            continue
        knots, failed = {}, {}
        for name, arm in arms.items():
            try:
                knots[name] = arm_knots(J, r, arm, schedule)
            except ValueError as exc:
                failed[name] = "— (%s)" % exc
        grid = union_grid(knots) if GRID_UNION else None
        grids[rk] = grid
        for name, arm in arms.items():
            if name in failed:
                out[name][rk] = {"note": failed[name]}
                continue
            out[name][rk] = place_rate(J, r, arm, schedule, declared, k_max, grid)
    return {"version": VERSION, "scope": SCOPE, "system": J.get("system"), "deviation": DEVIATION_80,
            "switches": {k: globals()[k] for k in SWITCHES}, "farBudgetPerHour": FAR_BUDGET_PER_HOUR,
            "tolerances": {"keyRelTol": KEY_REL_TOL, "gainAbsTol": GAIN_ABS_TOL},
            "budgetGrid": {"rule": "per rate, the union of every arm's knots (decision 81: one grid for all arms; "
                                   "engineering default for the non-modality arms too)" if GRID_UNION else
                                   "each arm's own knots (planted)",
                           "perRate": {rk: ([["inf" if b == INF else b, n, src] for b, n, src in g] if g else None)
                                       for rk, g in grids.items()}},
            "arms": out}


SWITCHES = ("MISS_AT_HOLD", "PER_EPISODE", "CLASS_WEIGHTS", "LEDGER_FIXED", "BC_SENSOR_MISS", "BC_LEDGER_COUNTS",
            "OWN_OUT", "COST_NULL_RULE", "PER_RATE", "PRE_ADMIT_ZERO", "LAZY_REEVALUATE", "BEST_OF_UC_CB",
            "STOP_AT_ZERO", "CANONICAL_TIES", "ONLINE_FRACTIONAL", "FOLD_KEY", "FOLD_SELECT_TRAIN_ONLY",
            "TIE_TOLERANCE", "GRID_UNION")


def _sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_inputs(J, schedule):
    """Refuse a readout not made by the frozen v3.1, and a schedule not checked against this readout's input."""
    if J.get("scriptSha256") != PINNED_V3_SHA256:
        raise SystemExit("refusing: readout scriptSha256 %r is not the frozen v3.1 %s" % (J.get("scriptSha256"),
                                                                                      PINNED_V3_SHA256))
    if schedule is not None:
        want = J["provenance"]["input"]["sha256"]
        if schedule.get("readoutInputChecked") != want:
            raise SystemExit("refusing: the schedule was not checked against this readout's input digest %s (run "
                             "cells_v3.py schedule with --readout)" % want)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="frozen v3.1 readout JSON (sweep_analysis_v3.json)")
    ap.add_argument("--out", required=True, help="NEW output file; refused if it exists")
    ap.add_argument("--schedule", help="cells_v3.py schedule output (impact arm)")
    ap.add_argument("--declared", help="JSON {comparator name: [sensor ids] | null} (decision 78)")
    ap.add_argument("--k-max", type=int, default=None, help="cardinality rows k = 1..K (secondary)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    J = json.loads(Path(a.readout).read_text())
    sch = json.loads(Path(a.schedule).read_text()) if a.schedule else None
    check_inputs(J, sch)
    dec = json.loads(Path(a.declared).read_text()) if a.declared else None
    res = run(J, sch, dec, k_max=a.k_max)
    res["inputs"] = {"readout": str(a.readout), "readoutSha256": _sha(a.readout),
                     "schedule": a.schedule, "scheduleSha256": _sha(a.schedule) if a.schedule else None,
                     "declared": a.declared, "declaredSha256": _sha(a.declared) if a.declared else None,
                     "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": _sha(__file__),
                     "python": sys.version}         # Objective.D uses builtin sum: compensated on 3.12+
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:            # exclusive create: never overwrites
        fh.write(json.dumps(res, indent=1, sort_keys=True, allow_nan=False))
    print("wrote", out)                                       # no number printed (step 4: committed before read)
    return 0


if __name__ == "__main__":
    sys.exit(main())
