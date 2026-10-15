#!/usr/bin/env python3
"""Traffic-sweep analysis v3 (v3.1): per-(sensor, rule) zero-alarm calibration on quiet data with honest nested
false-alarm counts (protocol round 15, decisions 61-65, as amended by round 17, decision 67), on top of v2.4's readers
and rules, which it imports and never edits; with a reader for campaign B's freeze stamps.

BINDING. research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd), round 16 (decision 66, e12e98f:
otelcol.log a lossy carrier, a known limitation) and round 17 (decisions 67-68, d8df15d), design
research/protocol/ANALYSIS_V3_DESIGN.md (amendment v3.1 in its last section, 7997b32), the reason
research/traffic-sweep/SYNTHESIS_V2_4.md; everything else as v2.4
(sweep_analysis_v2.py, frozen 098f3e0, freeze record 891a4c3; its binding documents per system). Every value v3 adds
is in research/protocol/parameters_v3.json; every v2.4 value is read from research/protocol/parameters.json through
v2.4 (decision 37). tests/test_sweep_analysis_v3.py: a planted defect per decision, each v3 check shown failing on v2.4
loaded from git (891a4c3), the readers' end-to-end tests on tests/fixtures/sweep_v22, the literal and registry scans.

    uv run python research/detection-time/sweep_analysis_v3.py <campaign dir> [<campaign dir> ...] \
        [--system hotel|teastore|otel] --out <new dir> [--validation <no-fault campaign dir> ...]

STATUS: EXPLORATORY and NOT FROZEN. Every existing cell of Hotel, TeaStore and OTel was read under v2.4 before v3 was
written (round 15). Campaign B (BUDGET_B.md) and quiet run A2 (decision 68; pooled by passing its campaign directory
beside A's) are the first data to be read under v3, after its freeze and review.

ENGINEERING CHOICE (recorded): v3 is a module of its own that imports v2.4 (`import sweep_analysis_v2 as v24`) and
reuses its readers, fits, episode rules, P1-P3, exposure and reports. v2.4's script and registry stay byte-identical,
so every v2.4 readout stays reproducible with the digests its freeze record pins (a rerun of v2.4 on TeaStore on
2026-10-09 equals readout 6d8f095 except HEAD and the timestamp). v3's own values are in parameters_v3.json, not in
parameters.json, for the same reason. v2.4 runs inside `v24.use_system`; v3 reads v2.4's module-level names at call
time (v24.ENTRY, v24.FAULT_REGIMES, ...).

WHAT v3 CHANGES AGAINST v2.4 (each a switch below, flipped only by tests/test_sweep_analysis_v3.py):
  Decision 61 (PER_RULE_UNIT, LOCO_CAL, MAX_ALARMS). One threshold per (sensor, rule) and rate: the smallest grid value
     whose held-out alarm count on the rate's no-fault cells, each scored leave-one-cell-out (v2.4's fit, H1), is 0;
     bound = the exact 95 % bound for 0 events over the rate's held-out hours T. A sensor's detector is the OR of its
     calibrated rules. Replaces decision 53 (K per family) and decision 33's 15/h target; v2.4's family table is
     printed beside it (computed in process by v2.4's own operating_point).
  Decision 62 (RANGE_FALLBACK, CENSORED_SILENCES, ABSENT_M_SEARCH, APPEAR_CALIBRATED). Level rules: K_GRID, then a
     range fallback (fit min/max widened by one resolution step). `absent`: g = m x G, G the largest fault-free gap
     including the censored silences at the segment's start and end, m on V3_ABSENT_M_GRID. `appear` unchanged, its
     held-out count per stream checked. MIN_BASELINE_POOLED arms as before. Dropped and unarmed (sensor, rule) pairs
     are listed; a sensor with no calibrated rule is "not placeable at this quiet time".
  Decision 63 (FAILED_EXEMPT, LEDGER_CALIBRATED). The ledger's `failed` is exempt and its no-fault count reported;
     E's spike, run3, median and absent are calibrated like any sensor's.
  Decision 64 (UNION_FAR). placement_far(): the measured union alarm count of any sensor set with its exact bound
     (held-out or validation cells); printed for every P4-selected set and for all placeable sensors.
  Decision 65 (P4_OVER_PLACEABLE, VALIDATION_NO_REFIT; the ledger reading: decision 70, V3_P4_LEDGER_READING). P4 over placeable sensors (B1 gone), the
     dropped rules and non-placeable sensors of each class named; `—` where episodes are fewer than declared; the
     ledger is the OR of its calibrated rules, a dropped ledger rule listed (decision 70). --validation: the calibrated detectors' alarm counts on extra no-fault cells, without
     refitting. Sensitivity setting `atMostOne` (<= 1 held-out alarm) beside the primary, and the floor arm.
  Campaign B reader (FREEZE_EVENT_ONSET; V3_FREEZE_EVENTS_RULE, STUDY_EPOCHS_B, V3_B_RECORD_KEYS). A TeaStore/OTel
     fault cell whose H4 record (TeaStore sweep.freezeStamps at bbb6b11; OTel docker-events.json + intervention.json
     `freeze` at c4aa313; Hotel's docker-events.jsonl format still read) carries one usable Docker `pause` event of its
     target gets that event as its onset interval's upper bound; a missing or contradictory record keeps the sweep's
     bound and is counted (decision 69). Both B study epochs are admitted (teastore-traffic-sweep-b-v1,
     otel-repeat-episodes-v1).
  Review fixes (Fable, 2026-10-10; RANGE_DEGENERATE_GUARD, HONEST_EVALUATED_ONLY, CELL_KEY_POOL, V3_P4_LEDGER_READING):
     F1 a range with no instrument resolution is unarmed (never dropped with every sample an alarm, never re-armed in
     the optimistic bound); F2 honest counts and CELF costs over the evaluated folds only, — with none; F3 the
     decision-69 record schemas; F4 the ledger reading of P4 is a registry switch (a user decision pending).
  Decision 67 (v3.1; NESTED, INERT_STATUS, RANGE_MAD_ZERO, RANGE_LATENCY_UP_ONLY, SENSITIVITY_NO_RANGE,
     APPEAR_ONLY_APART, OPTIMISTIC_ARM). The selection above stays, but no false-alarm figure is its own zero: every
     (sensor, rule), sensor (the CELF cost) and sensor set carries its honest nested count (V3_NESTED_RULE: each
     held-out cell at the value re-selected without it, the inner fits excluding both cells). `inert` status (an
     `absent` whose gap exceeds the shortest hold), per-rule placeability, appear-only sensors listed apart, K = 100
     flagged at grid edge, the range fallback labelled discrete-in-effect (up-only for spans and the ledger, two-sided
     for metrics, applicable where MAD = 0 while decision 52 keeps K out; no <= 1 setting for it), P4's optimistic arm
     (dropped rules at K = 100 / m = 5) beside the calibrated arm, E's rule mix and B's fresh-check limit printed.
  Decision 66 (V3_KNOWN_LIMITATIONS): OTel's otelcol.log is a lossy carrier in the existing cells; printed.
  Decisions 49, 68, 69 (H4_FALLBACK, HARNESS_TAG, POOL_KEY_CAMPAIGN). The B reader reads TeaStore's
     sweep.freezeStamps and OTel's `freeze` block + docker-events.json object (epoch otel-repeat-episodes-v1); a missing
     or contradictory H4 record leaves the cell valid, keeps the sweep's bound and is counted (decision 69). The sweep's
     episode and B's three pool into 'k of 4' (decision 49), each episode tagged sweep / B with a per-harness breakdown
     beside every pooled verdict (V3_HARNESS_TAG_RULE; L-H10 / L-H4 limitations). A cell is (campaign, run path):
     quiet run A2 repeats A's run IDs under a new campaign (V3_POOL_KEY_RULE). The six engineering defaults the
     coordinator accepted on 2026-10-09 are in V3_ACCEPTED_DEFAULTS.
UNCHANGED (v2.4 functions reused): readers, pooled baselines (H1), relative and resolution floors, decision 52 (MAD = 0:
level rules unarmed), the episode window and probe rules, decisions 51, 54, 57, 58, 60 (same-request and onset rules),
event time primary, P1, P2, P3, exposure, the H3 judgement of a fold.
"""
import argparse
import bisect
import contextlib
import datetime as _dt
import hashlib
import json
import math
import platform
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sweep_analysis_v2 as v24  # noqa: E402  v2.4 (frozen 098f3e0), never edited

dt, v1 = v24.dt, v24.v1

PARAMETERS_V3 = REPO / "research" / "protocol" / "parameters_v3.json"
VERSION = "3"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V3.md", "sweep_analysis_v3.json"
LABEL = "exploratory, not frozen (every cell of this system was read under v2.4 before v3 was written)"
BINDING_V3 = ("research/PROTOCOL_DRAFT_20261002.md round 15 (decisions 61-65, 252cfcd)",
              "research/protocol/ANALYSIS_V3_DESIGN.md (252cfcd)", "research/traffic-sweep/SYNTHESIS_V2_4.md",
              "research/protocol/parameters_v3.json (decision 37)")


# =========================================================================== the v3 registry (decision 37)

def load_registry(path=PARAMETERS_V3):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY = load_registry()
PARAMS_USED = set()


def param3(name):
    """Every value v3 adds comes through here (the tests check the names used against their origin)."""
    PARAMS_USED.add(name)
    return REGISTRY[name]["value"]


MAX_ALARMS = param3("V3_MAX_HELD_OUT_ALARMS")
SENS_ALARMS = param3("V3_SENSITIVITY_MAX_HELD_OUT_ALARMS")
M_GRID = tuple(param3("V3_ABSENT_M_GRID"))
WIDEN = param3("V3_RANGE_WIDEN_STEPS")
UNIT = param3("V3_CALIBRATION_UNIT")
STUDY_EPOCHS_B = param3("STUDY_EPOCHS_B")
LIST_MAX = param3("V3_REPORT_LIST_MAX")
FREEZE_TOL = param3("V3_FREEZE_EVENT_TOLERANCE_S")
P4_LEDGER_READING = param3("V3_P4_LEDGER_READING")
B_RECORD_KEYS = param3("V3_B_RECORD_KEYS")
FREEZE_REPLAY_TOL = param3("V3_FREEZE_REPLAY_TOLERANCE_S")
B_SCHEMA_ADDITIONS = param3("V3_B_SCHEMA_ADDITIONS")
B_FRESH_HOURS = param3("V3_B_FRESH_HOURS")
KNOWN_LIMITATIONS_V3 = param3("V3_KNOWN_LIMITATIONS")
RULES_TEXT = {n: param3(n) for n in ("V3_LEVEL_GRID_RULE", "V3_RANGE_FALLBACK_RULE", "V3_ABSENT_CENSORED_RULE",
                                     "V3_APPEAR_RULE", "V3_LEDGER_RULE", "V3_CALIBRATION_SCOPE_RULE", "V3_STATUS_RULE",
                                     "V3_NESTED_RULE", "V3_TESTABLE_RULE", "V3_INERT_RULE", "V3_PLACEMENT_FAR_RULE", "V3_P4_RULE",
                                     "V3_OPTIMISTIC_ARM_RULE", "V3_VALIDATION_RULE", "V3_FREEZE_EVENTS_RULE",
                                     "V3_HARNESS_TAG_RULE", "V3_POOL_KEY_RULE", "V3_ACCEPTED_DEFAULTS")}
assert UNIT == "sensor-rule", "v3 implements the (sensor, rule) unit of decision 61"
assert list(M_GRID) == sorted(M_GRID)

# Switches flipped only by tests/test_sweep_analysis_v3.py (planted defects); the analysis never changes them.
PER_RULE_UNIT = True          # decision 61: the rule is the unit (False: a sensor with a dropped rule loses them all)
LOCO_CAL = True               # decision 61: a held-out cell is scored with a fit without it
RANGE_FALLBACK = True         # decision 62: level rules fall back to the fit range after K_GRID
CENSORED_SILENCES = True      # decision 62: G counts the censored silences at the segment's start and end
ABSENT_M_SEARCH = True        # decision 62: m searched on V3_ABSENT_M_GRID (False: v2.4's ABSENT_GAP_MULT only)
APPEAR_CALIBRATED = True      # decision 62: `appear` dropped where it fires on held-out cells
FAILED_EXEMPT = True          # decision 63: the ledger's `failed` is exempt (False: calibrated, dropped if it fires)
LEDGER_CALIBRATED = True      # decision 63: E's spike/run3/median/absent calibrated (False: armed at v2.4's K_REF / gap)
UNION_FAR = True              # decision 64: placement false alarms = the measured union (False: sum over sensors)
P4_OVER_PLACEABLE = True      # decision 65: no B1 (False: P4 — where a collected family has a dropped rule)
VALIDATION_NO_REFIT = True    # decision 65: validation cells never enter a fit (False: pooled into the scoring fit)
FREEZE_EVENT_ONSET = True     # campaign B: the Docker pause event bounds the onset interval where the cell has it
# decision 67 (v3.1, round 17)
NESTED = True                 # honest count: inner fits exclude the outer cell too (False: the inner LOCO fits, which
                              # contain it, and the selection not re-done per outer cell)
INERT_STATUS = True           # an `absent` with g > the shortest hold is inert, not calibrated, not placeable
RANGE_MAD_ZERO = True         # the range fallback may apply where MAD = 0 (decision 52 kept for K)
RANGE_LATENCY_UP_ONLY = True  # the range is up-only for spans and the ledger, two-sided for metrics
SENSITIVITY_NO_RANGE = True   # no "<= 1 alarm" setting for range-fallback rules (K_GRID only there)
APPEAR_ONLY_APART = True      # sensors placeable through `appear` alone are listed apart
OPTIMISTIC_ARM = True         # P4's optimistic arm (dropped rules at the largest grid value) beside the calibrated
TESTABLE_ONLY = True          # a held-out fold where the rule is unarmed is no evidence (False: it counts as 0 alarms)
# decisions 49, 68, 69 (round 18) and the coordinator's pooling request
H4_FALLBACK = True            # decision 69: a missing / contradictory H4 record keeps the sweep's bound (False: —)
HARNESS_TAG = True            # V3_HARNESS_TAG_RULE: each episode tagged sweep / B (False: every cell `sweep`)
POOL_KEY_CAMPAIGN = True      # V3_POOL_KEY_RULE: a cell is (campaign, run path) (False: the run path alone)
# the independent v3.1 review (Fable, 2026-10-10)
RANGE_DEGENERATE_GUARD = True # F1: a range with no instrument resolution or a threshold <= 0 is unarmed
HONEST_EVALUATED_ONLY = True  # F2: the honest count and its hours over the folds that evaluated the rule; none: —
CELL_KEY_POOL = True          # episodes, clocks and records keyed by (campaign, run path) (False: the cell path)
H4_RECORD_STATUS = True       # F3: the record's own status / verdict / stampCheck is read (False: ignored, rows used)
CONTAINER_FILTER = True       # F3/F11: only the target container's events (False: every container's)

LEVEL = ("spike", "run3", "median")
FIXED_EV, LEVEL_EV = 0, 1
SETTINGS = ("primary", "arm", "atMostOne", "optimistic")
CAL_SETTINGS = ("primary", "arm", "atMostOne")
KMAP_ALL = "calibrated per (sensor, rule)"
FREEZE_VERSION = "h4-h10-v1"            # TeaStore B harness draft FAULT_HARNESS["version"] (V3_FREEZE_EVENTS_RULE)
OTEL_EVENTS_KIND = "otel-demo-fault-docker-events-v1"     # OTel B draft docker-events.json kind
OTEL_FREEZE_KIND = "otel-demo-fault-freeze-stamps-v1"     # OTel B draft intervention.json `freeze` kind
DOCKER_EVENT_FILES = ("docker-events.json", "docker-events.jsonl")


# =========================================================================== small helpers

def sid_of(key):
    return "%s:%s:%s" % key


def rid(key, rule):
    return "%s/%s" % (sid_of(key), rule)


def rules_of(key):
    """The rules a sensor has (v2.4's): spans appear, absent and the level rules (error spans appear only); logs appear
    and absent; metrics the level rules; the ledger (per route) the level rules on ok latency, absent on completions
    (LEDGER_ABSENT) and failed."""
    ch, _, tok = key
    if ch == "ledger":
        return LEVEL + (("absent",) if v24.LEDGER_ABSENT else ()) + ("failed",)
    if ch == "metric":
        return LEVEL
    if ch == "span":
        return ("appear",) if tok.endswith(":error") else ("appear", "absent") + LEVEL
    if ch == "log":
        return "appear", "absent"
    return ()


def dirs_of(key, value=None):
    """A sensor's directions (v2.4's: metrics both, spans and the ledger up); the range fallback the same
    (RANGE_LATENCY_UP_ONLY False, planted defect: two-sided for every channel)."""
    if key[0] == "metric" or (value is not None and value[0] == "range" and not RANGE_LATENCY_UP_ONLY):
        return "up", "down"
    return ("up",)


def absent_key(key):
    """The count key whose records `absent` watches (the ledger: its route's completions)."""
    return ("ledger", key[1], key[2] + v24.COMPLETIONS) if key[0] == "ledger" else key


def bound(n, hours, conf=None):
    return v24.poisson_upper(n, conf) / hours if hours else None


def value_text(v):
    if v is None:
        return v24.DASH
    kind, x = v
    return {"K": "K %g" % x if x is not None else "K", "range": "range", "m": "m %g" % x if x is not None else "m",
            "none": "armed"}[kind]


# =========================================================================== fits (H1) with the v3 statistics

def censor_stats(c):
    """Decision 62: per log/span stream and per ledger route's completions, over the cell's fault-free segment (H1's,
    as v24.segment_stats cuts it): (records, largest internal gap, segment start -> first record, last record ->
    segment end). Streams with no record in the segment are not listed (they have no first or last record)."""
    closed = c["seg"]["closed"]
    out = {}

    def cut(times, lo, hi):
        return bisect.bisect_left(times, lo), (bisect.bisect_right(times, hi) if closed else
                                               bisect.bisect_left(times, hi))
    for key, (obs, _, meta) in c["prep"].items():
        ch = key[0]
        if ch not in c["chans"] or ch not in ("log", "span"):
            continue
        lo, hi = c["seg"][meta["clock"]]
        if ch == "log" and c["wsLogs"] and not closed:
            hi = math.floor(hi)
        i0, i1 = cut(obs, lo, hi)
        if i1 > i0:
            out[key] = (i1 - i0, v24.max_gap(obs[i0:i1]), obs[i0] - lo, hi - obs[i1 - 1])
    lo, hi = c["seg"]["mono"]
    for route in sorted({r.route for r in c["ledger"]}):
        ends = [r.end for r in c["ledger"] if r.route == route]
        i0, i1 = cut(ends, lo, hi)
        if i1 > i0:
            out[("ledger", v24.ENTRY, route + v24.COMPLETIONS)] = (i1 - i0, v24.max_gap(ends[i0:i1]), ends[i0] - lo,
                                                                    hi - ends[i1 - 1])
    c["segCensor"] = out
    return out


class Fit3(v24.Fit):
    """v2.4's pooled fit (H1) plus: per level sensor the pooled fault-free minimum and maximum (decision 62's range);
    per stream G = the largest fault-free gap including the censored silences (CENSORED_SILENCES)."""

    def __init__(self, cells, rate, exclude=None, res_cells=None):
        super().__init__(cells, rate, exclude=exclude, res_cells=res_cells)
        use = [c for c in cells if c["rate"] == rate and c is not exclude]
        lo, hi, G = {}, {}, {}
        for c in use:
            for k, v in c["segLevel"].items():
                if v:
                    lo[k] = min(lo.get(k, math.inf), min(v))
                    hi[k] = max(hi.get(k, -math.inf), max(v))
            for k, (_, g, head, tail) in (c.get("segCensor") or censor_stats(c)).items():
                parts = [x for x in ((g, head, tail) if CENSORED_SILENCES else (g,)) if x is not None]
                if parts:
                    G[k] = max(G.get(k, -math.inf), max(parts))
        self.range = {k: (lo[k], hi[k]) for k in lo}
        self.gmax = G

    def gap_m(self, key, m):
        """g = m x G for `absent` (None: unarmed, pooled n < MIN_BASELINE_POOLED or no positive G)."""
        n = self.count.get(key, (0, None, 0))[0]
        G = self.gmax.get(key)
        if G is None or G <= 0 or (v24.MIN_POOLED_CHECK and n < v24.MIN_POOLED):
            return None
        return m * G


def fits_for3(cells):
    valid = [c for c in cells if c["valid"]]
    assert v24.POOLED, "v3 scores with v2.4's pooled baseline (H1)"
    return {r: Fit3(valid, r, res_cells=valid) for r in sorted({c["rate"] for c in valid})}


def loco_fits3(cells):
    """Per no-fault cell, v2.4's leave-one-cell-out fit (LOCO_CAL False, planted defect: with the cell)."""
    valid = [c for c in cells if c["valid"]]
    return {id(X): Fit3(valid, X["rate"], exclude=X if LOCO_CAL else None, res_cells=valid)
            for X in valid if X["target"] is None}


# =========================================================================== thresholds and level rules

def thresholds(fit, key, lv, value, share, res):
    """{direction: threshold} of a level rule at a calibrated value: ("K", k) -> v2.4's max(k x SCALE x MAD, floor)
    in both directions; ("range", None) -> the fit range widened by WIDEN resolution steps (V3_RANGE_FALLBACK_RULE).
    None: no positive threshold."""
    m, mad, _ = lv
    if value[0] == "K":
        t = max(value[1] * v24.SCALE * mad, v24.floor_of(m, share, res))
        return {"up": t, "down": t} if t > 0 else None
    if value[0] == "range":
        lo, hi = fit.range[key]
        if RANGE_DEGENERATE_GUARD and not res:
            return None                     # F1: no instrument resolution in the fit: the range is degenerate
        w = WIDEN * (res or 0.0)
        thr = {"up": (hi + w) - m, "down": m - (lo - w)}
        if RANGE_DEGENERATE_GUARD and min(thr[d] for d in dirs_of(key, value)) <= 0:
            return None
        return thr
    raise ValueError("not a level value: %r" % (value,))


def level_rules_dir(obs, vals, m, thr, dirs):
    """dt.level_rules with a threshold per direction (the range fallback is asymmetric); identical to it when both
    thresholds are equal: {rule: (t, dir)} for spike, run3 (RUN_N consecutive beyond in one direction) and median (the
    running median of the window's samples beyond, after MEDIAN_MIN samples)."""
    out, run, prefix = {}, dict.fromkeys(dirs, 0), []
    for t, v in zip(obs, vals):
        for d in dirs:
            if dt.beyond(v, m, thr[d], d):
                out.setdefault("spike", (t, d))
                run[d] += 1
                if run[d] >= v24.RUN_N:
                    out.setdefault("run3", (t, d))
            else:
                run[d] = 0
        bisect.insort(prefix, v)
        if "median" not in out and len(prefix) >= v24.MEDIAN_MIN:
            pm = _median_sorted(prefix)
            for d in dirs:
                if dt.beyond(pm, m, thr[d], d):
                    out["median"] = (t, d)
                    break
        if len(out) == len(LEVEL):
            break
    return out


def _median_sorted(s):
    """statistics.median of an already sorted list (same arithmetic)."""
    h = len(s) // 2
    return s[h] if len(s) % 2 else (s[h - 1] + s[h]) / 2


# =========================================================================== held-out material

def level_material(X, key):
    """(times, values, instrument) of a level sensor's samples in X's [t0, end], as v24.quiet_material reads them
    (the ledger: ok latencies of the route, in ms, at their end)."""
    ch, svc, tok = key
    if ch == "ledger":
        t0, end = X["t0"]["mono"], X["end"]["mono"]
        ok = [r for r in X["ledger"] if r.route == tok and t0 <= r.end <= end and r.ok]
        return [r.end for r in ok], [(r.end - r.start) * v24.MS_PER_S for r in ok], ("ledger",)
    got = X["prep"].get(key)
    if got is None or ch not in X["chans"]:
        return [], [], None
    obs, vals, meta = got
    clk = meta["clock"]
    i0, i1 = bisect.bisect_left(obs, X["t0"][clk]), bisect.bisect_right(obs, X["end"][clk])
    return obs[i0:i1], vals[i0:i1], v24.instrument(ch, meta, tok)


def stream_material(X, key):
    """(all records, t0, end, whole-second?) of a stream `absent` / `appear` watches in X (the ledger: completions)."""
    ch, _, tok = key
    if ch == "ledger":
        return sorted(r.end for r in X["ledger"] if r.route == tok), X["t0"]["mono"], X["end"]["mono"], False
    got = X["prep"].get(key)
    if got is None or ch not in X["chans"]:
        return [], None, None, False
    clk = got[2]["clock"]
    return got[0], X["t0"][clk], X["end"][clk], ch == "log" and X["wsLogs"]


def level_stats(vs):
    """Per level rule, the (largest, smallest) statistic over a cell's samples, so that the rule fires somewhere in the
    cell at threshold thr iff the largest is beyond up or the smallest beyond down (no restart precedes the first fire):
    spike = the samples; run3 = the minima (up) / maxima (down) of every RUN_N consecutive samples; median = the
    running medians from MEDIAN_MIN samples on."""
    if not vs:
        return {}
    out = {"spike": (max(vs), min(vs))}
    n = v24.RUN_N
    if len(vs) >= n:
        win = [vs[j:j + n] for j in range(len(vs) - n + 1)]
        out["run3"] = (max(min(w) for w in win), min(max(w) for w in win))
    prefix, pms = [], []
    for v in vs:
        bisect.insort(prefix, v)
        if len(prefix) >= v24.MEDIAN_MIN:
            pms.append(_median_sorted(prefix))
    if pms:
        out["median"] = (max(pms), min(pms))
    return out


def stat_fires(st, m, thr, dirs):
    if st is None or thr is None:
        return False
    return ("up" in dirs and dt.beyond(st[0], m, thr["up"], "up")) or \
        ("down" in dirs and dt.beyond(st[1], m, thr["down"], "down"))


# =========================================================================== the restarted detector (exact)

class _State:
    __slots__ = ("epoch", "run", "prefix")

    def __init__(self, epoch, dirs):
        self.epoch, self.run, self.prefix = epoch, dict.fromkeys(dirs, 0), []


def simulate(X, F, items, share, info=None):
    """The union detector of `items` [(key, rule, value)] on one cell with fit F, restarted after each alarm (v2.4's
    restart semantics, restart_count): per rule its fire since the last restart (spike = a beyond sample, run3 =
    RUN_N consecutive beyond samples in one direction, median = the running median of the samples since the restart
    beyond after MEDIAN_MIN samples; appear / absent (re-armed) / failed at their instants). Returns the alarms
    [(t, rule id)], distinct instants. `info` (a dict) receives `armed`: how many items the fit arms in this cell (an
    armed item with no record still counts: it was evaluated and stayed silent)."""
    evs, spec = [], {}
    armed = 0
    for a, (key, rule, value) in enumerate(items):
        if rule in LEVEL:
            lv = lvl_for(F, key, value)
            ts, vs, inst = level_material(X, key)
            if lv is None:
                continue
            thr = thresholds(F, key, lv, value, share, F.res.get(inst if inst else ("ledger",)))
            if thr is None:
                continue
            armed += 1
            if not ts:
                continue
            spec[a] = (rule, vs, dirs_of(key, value), lv[0], thr, rid(key, rule))
            evs.extend((t, LEVEL_EV, a, j) for j, t in enumerate(ts))
            continue
        spec[a] = (rule, None, None, None, None, rid(key, rule))
        obs, t0, end, ws = stream_material(X, key)
        if t0 is None:
            continue
        if rule == "absent":
            g = F.gap_m(absent_key(key), value[1])
            if g is not None:
                armed += 1
                evs.extend((t, FIXED_EV, a, 0) for t in v24.silences(obs, t0, t0, end, g))
        elif rule == "appear":
            i0, i1 = bisect.bisect_left(obs, t0), bisect.bisect_right(obs, end)
            if F.novel(key):
                armed += 1
                if i1 > i0:
                    evs.append((v24.log_time(obs[i0], ws), FIXED_EV, a, 0))
        elif rule == "failed":
            armed += 1
            evs.extend((r.end, FIXED_EV, a, 0) for r in X["ledger"]
                       if r.route == key[2] and not r.ok and t0 <= r.end <= end)
    if info is not None:
        info["armed"] = armed
    evs.sort()
    alarms, t_r, epoch, state = [], -math.inf, 0, {}
    for t, kind, a, j in evs:
        if t <= t_r:
            continue
        rule, vs, dirs, m, thr, name = spec[a]
        if kind == LEVEL_EV:
            st = state.get(a)
            if st is None or st.epoch != epoch:
                st = state[a] = _State(epoch, dirs)
            v, fire = vs[j], False
            if rule == "spike":
                fire = any(dt.beyond(v, m, thr[d], d) for d in dirs)
            elif rule == "run3":
                for d in dirs:
                    st.run[d] = st.run[d] + 1 if dt.beyond(v, m, thr[d], d) else 0
                fire = any(st.run[d] >= v24.RUN_N for d in dirs)
            else:
                bisect.insort(st.prefix, v)
                if len(st.prefix) >= v24.MEDIAN_MIN:
                    pm = _median_sorted(st.prefix)
                    fire = any(dt.beyond(pm, m, thr[d], d) for d in dirs)
            if not fire:
                continue
        alarms.append((t, name))
        t_r, epoch = t, epoch + 1
    return alarms


# =========================================================================== decisions 61-63, 67: calibration

def universe(cells, rate):
    """Every sensor seen at the rate (any valid cell, any time): {key: (family, meta)}; the ledger's routes as
    ("ledger", ENTRY, route), family E."""
    out = {}
    for c in cells:
        if not c["valid"] or c["rate"] != rate:
            continue
        for key, (_, _, meta) in c["prep"].items():
            if key[0] in c["chans"] and key not in out:
                out[key] = (v24.family_of(c, key[0], meta), meta)
        for route in {r.route for r in c["ledger"]}:
            out.setdefault(("ledger", v24.ENTRY, route), ("E", None))
    return out


def lvl_for(F, key, value):
    """The level baseline a value needs: K -> v2.4's lvl (n >= MIN_BASELINE_POOLED, MAD > 0, decision 52); range ->
    the median and n >= MIN_BASELINE_POOLED only (decision 67: the range fallback may apply where MAD = 0)."""
    if value[0] == "K" or not RANGE_MAD_ZERO:
        return F.lvl(key)
    lv = F.level.get(key)
    if lv is None or (v24.MIN_POOLED_CHECK and lv[2] < v24.MIN_POOLED) or key not in F.range:
        return None
    return lv


def _unarmed_level(F, key):
    lv = F.level.get(key)
    if lv is None:
        return "no fault-free level data at this rate"
    if v24.MIN_POOLED_CHECK and lv[2] < v24.MIN_POOLED:
        return "pooled n = %d < MIN_BASELINE_POOLED" % lv[2]
    if v24.MAD_ZERO_DASH and lv[1] == 0:
        return "scale not estimable (MAD = 0, decision 52)"
    return "no level scale"


def _unarmed_absent(F, key):
    n = F.count.get(key, (0, None, 0))[0]
    if v24.MIN_POOLED_CHECK and n < v24.MIN_POOLED:
        return "pooled records n = %d < MIN_BASELINE_POOLED" % n
    return "no positive fault-free gap"


def _has_records(X, key):
    obs, t0, end, _ = stream_material(X, key)
    return t0 is not None and bisect.bisect_right(obs, end) > bisect.bisect_left(obs, t0)


def pair_fits(cells, rate):
    """V3_NESTED_RULE: per ordered pair (outer X, inner Y) of the rate's no-fault cells, the fit without both (NESTED
    False, planted defect: the inner cell's own leave-one-cell-out fit, which contains X)."""
    valid = [c for c in cells if c["valid"]]
    quiet = [X for X in valid if X["rate"] == rate and X["target"] is None]
    out = {}
    for X in quiet:
        for Y in quiet:
            if X is not Y:
                use = [c for c in valid if c is not X and c is not Y]
                out[(id(X), id(Y))] = Fit3(use, rate, res_cells=use)
    return out


def _select(nf, count_at, exclude, criterion, nvals):
    """(the first value index whose count summed over the folds other than `exclude` is within the criterion, whether
    any value was testable). A fold where the rule is unarmed (count None) is no evidence; a value with no armed fold
    is skipped (V3_TESTABLE_RULE), so a rule is never calibrated by folds that cannot evaluate it."""
    testable = False
    for vi in range(nvals):
        tot, armed = 0, 0
        for j in range(nf):
            if j == exclude:
                continue
            c = count_at(vi, j)
            if c is None:
                continue
            armed += 1
            tot += c
            if tot > criterion:
                break
        if armed == 0 and TESTABLE_ONLY:
            continue
        testable = True
        if tot <= criterion:
            return vi, True
    return None, testable


def calibrate_rate(cells, rate, share, criterion, fits_loco, F_sc, pairs, hold, allow_range=True):
    """One rate: the status of every (sensor, rule) (V3_STATUS_RULE) under `criterion` (0: decision 61; 1: the
    sensitivity setting of decisions 65/67, K_GRID only), with its honest nested count (V3_NESTED_RULE)."""
    valid = [c for c in cells if c["valid"]]
    quiet = [X for X in valid if X["rate"] == rate and X["target"] is None]
    nf = len(quiet)
    folds = [(X, fits_loco[id(X)]) for X in quiet]
    fold_hours = [(X["end"]["mono"] - X["t0"]["mono"]) / v24.S_PER_HOUR for X in quiet]
    hours = sum(fold_hours)
    keys = universe(valid, rate)
    cache = {}

    def stats(X, key):
        k = (id(X), key)
        if k not in cache:
            cache[k] = level_stats(level_material(X, key)[1])
        return cache[k]

    def fit_of(i, j):
        """Fold j's fit: leave-one-cell-out (i None) or nested without the outer cell i."""
        if i is None or not NESTED:
            return folds[j][1]
        return pairs[(id(quiet[i]), id(quiet[j]))]

    def make_count(key, rule, inst):
        """count(value, j, fit, exact) on held-out cell j: None where the rule is unarmed in that fit (no evidence)."""
        def count(value, j, F, exact):
            X = quiet[j]
            if rule in LEVEL:
                lv = lvl_for(F, key, value)
                if lv is None:
                    return None
                thr = thresholds(F, key, lv, value, share, F.res.get(inst))
                if thr is None:
                    return None
                if not stat_fires(stats(X, key).get(rule), lv[0], thr, dirs_of(key, value)):
                    return 0
                return len(simulate(X, F, [(key, rule, value)], share)) if exact else 1
            if rule == "absent":
                g = F.gap_m(absent_key(key), value[1])
                if g is None:
                    return None
                obs, t0, end, _ = stream_material(X, key)
                return len(v24.silences(obs, t0, t0, end, g)) if t0 is not None else 0
            if rule == "appear":
                if not F.novel(key):
                    return None                       # a record in this fold's fit: `appear` cannot fire here
                return 1 if _has_records(X, key) else 0
            if rule == "failed":
                return sum(1 for r in X["ledger"] if r.route == key[2] and not r.ok
                           and X["t0"]["mono"] <= r.end <= X["end"]["mono"])
            return 0
        return count

    def calibrate_values(row, key, rule, values, count, fixed=None):
        """Selection on the LOCO folds, the nested re-selection per outer fold, the honest count."""
        exact_sel = criterion > 0
        memo = {}

        def at(i):
            def f(vi, j):
                k = (i, vi, j)
                if k not in memo:
                    memo[k] = count(values[vi], j, fit_of(i, j), exact_sel)
                return memo[k]
            return f
        chosen, testable = (fixed, True) if fixed is not None else _select(nf, at(None), None, criterion, len(values))
        nested = []
        for i in range(nf):
            vi = fixed if fixed is not None else (_select(nf, at(i), i, criterion, len(values))[0] if NESTED
                                                  else chosen)
            if vi is not None and rule == "absent" and INERT_STATUS and hold is not None:
                g = folds[i][1].gap_m(absent_key(key), values[vi][1])
                vi = None if (g is not None and g > hold) else vi
            nested.append(vi)
        per = [count(values[vi], i, folds[i][1], True) if vi is not None else None for i, vi in enumerate(nested)]
        ev = [i for i, x in enumerate(per) if x is not None]          # F2: folds where the rule was evaluated
        hrs = sum(fold_hours[i] for i in ev)
        n = sum(per[i] for i in ev)
        if not HONEST_EVALUATED_ONLY:                                  # planted defect: 0 for unevaluated folds
            ev, hrs, n = list(range(nf)), hours, sum(x or 0 for x in per)
        row.update(values=values, nested=nested, honestPerFold=per, foldsEvaluated=len(ev),
                   nestedOutOfDetector=sum(1 for vi in nested if vi is None),
                   honest=n if ev else None, honestHours=hrs if ev else None,
                   honestPerHour=(n / hrs) if (ev and hrs) else None,
                   honestUpperPerHour=bound(n, hrs) if (ev and hrs) else None)
        armed = sum(1 for j in range(nf) if count(values[chosen if chosen is not None else -1], j, folds[j][1],
                                                   False) is not None)
        row["foldsArmed"] = armed
        row["selected"] = chosen is not None
        row["selectedValue"] = values[chosen] if chosen is not None else None
        if chosen is not None:
            n = sum(count(values[chosen], j, folds[j][1], True) or 0 for j in range(nf))
            row.update(status="calibrated", value=values[chosen], heldOut=n,
                       gridEdge=values[chosen] == ("K", v24.K_GRID[-1]))
        elif not testable:
            row.update(status="unarmed", value=None, heldOut=0,
                       reason="not testable: unarmed in every held-out fold's fit (V3_TESTABLE_RULE)")
        else:
            n = sum(count(values[-1], j, folds[j][1], True) or 0 for j in range(nf))
            row.update(status="dropped", value=None, heldOut=n, lastValue=values[-1],
                       reason="%d held-out alarm(s) at the last grid value (%s)" % (n, value_text(values[-1])))

    rules, quiet_failed = {}, {}
    for key, (fam, meta) in sorted(keys.items(), key=lambda kv: sid_of(kv[0])):
        ch = key[0]
        inst = ("ledger",) if ch == "ledger" else v24.instrument(ch, meta, key[2])
        for rule in rules_of(key):
            row = {"family": fam, "sensor": sid_of(key), "rule": rule, "status": None, "value": None,
                   "heldOut": None, "reason": None, "honest": None, "nested": None, "gridEdge": False}
            count = make_count(key, rule, inst)
            if rule == "failed":
                n = sum(count(None, j, folds[j][1], True) or 0 for j in range(nf))
                quiet_failed[key[2]] = n
                row.update(heldOut=n, value=("none", None))
                if FAILED_EXEMPT:
                    row.update(status="exempt", reason="decision 63: the client's definition of failure, exempt")
                else:
                    calibrate_values(row, key, rule, [("none", None)], count)
            elif rule == "appear":
                calibrate_values(row, key, rule, [("none", None)], count)
                if row["status"] == "dropped" and APPEAR_CALIBRATED:
                    row["reason"] = "appears in %d held-out no-fault cell(s) with no record in the fold's fit" % (
                        row["heldOut"])
                elif not F_sc.novel(key):
                    row.update(status="unarmed", value=None, reason="a record in the pooled fault-free data at this "
                                                                    "rate (its nested count stays: in a held-out "
                                                                    "cell's own fit the stream may be new)")
                else:
                    row.update(status="calibrated", value=("none", None))
            elif fam == "E" and not LEDGER_CALIBRATED:                   # planted defect: v2.4's values, unchecked
                v = ("K", v24.K_REF) if rule in LEVEL else ("m", v24.ABSENT_GAP_MULT)
                armed = lvl_for(F_sc, key, v) if rule in LEVEL else F_sc.gap_m(absent_key(key), v[1])
                if armed is None:
                    row.update(status="unarmed", reason="v2.4's value unarmed")
                else:
                    calibrate_values(row, key, rule, [v], count, fixed=0)
                    row.update(status="calibrated", value=v)
            elif rule in LEVEL:
                values = [("K", k) for k in v24.K_GRID] if F_sc.lvl(key) is not None else []
                degenerate = False
                lvr = lvl_for(F_sc, key, ("range", None))
                if RANGE_FALLBACK and allow_range and lvr is not None:
                    if thresholds(F_sc, key, lvr, ("range", None), share, F_sc.res.get(inst)) is None:
                        degenerate = True               # F1: never a value, never re-armed in the optimistic arm
                    else:
                        values.append(("range", None))
                if not values:
                    row.update(status="unarmed", reason="range degenerate: no instrument resolution in the fit"
                               if degenerate else _unarmed_level(F_sc, key))
                else:
                    calibrate_values(row, key, rule, values, count)
                    if F_sc.lvl(key) is None:
                        row["madZeroRange"] = True
            elif rule == "absent":
                if F_sc.gap_m(absent_key(key), M_GRID[0]) is None:
                    row.update(status="unarmed", reason=_unarmed_absent(F_sc, absent_key(key)))
                else:
                    values = [("m", m) for m in (M_GRID if ABSENT_M_SEARCH else (v24.ABSENT_GAP_MULT,))]
                    calibrate_values(row, key, rule, values, count)
                    if row["status"] == "calibrated":
                        row["g"] = F_sc.gap_m(absent_key(key), row["value"][1])
                        if INERT_STATUS and hold is not None and row["g"] > hold:
                            row.update(status="inert", reason="calibrated gap g = %.3f s > the shortest hold %.3f s: "
                                                              "cannot fire inside the hold" % (row["g"], hold))
            row["placeable"] = row["status"] == "calibrated"
            rules[(key, rule)] = row
    if not PER_RULE_UNIT:                         # planted defect: the sensor, not the rule, is the unit
        bad = {k for (k, r), row in rules.items() if row["status"] == "dropped"}
        for (k, r), row in rules.items():
            if k in bad and row["status"] == "calibrated":
                row.update(status="dropped", placeable=False, reason="another rule of the sensor is dropped (sensor "
                                                                     "unit)")
    sensors = {}
    for (key, rule), row in rules.items():
        s = sensors.setdefault(key, {"family": row["family"], "sensor": sid_of(key), "calibrated": [], "dropped": [],
                                     "unarmed": [], "exempt": [], "inert": []})
        s[row["status"]].append(rule)
    for s in sensors.values():
        s["placeable"] = bool(s["calibrated"])
        s["appearOnly"] = s["calibrated"] == ["appear"] if APPEAR_ONLY_APART else False
    score = {(key, rule): row["value"] for (key, rule), row in rules.items()
             if row["status"] in ("calibrated", "exempt")}
    vocab = Counter()
    for (key, rule), row in rules.items():
        if rule == "appear" and row["heldOut"]:
            vocab[key[1]] += row["heldOut"]
    cr = {"rate": rate, "share": share, "criterion": criterion, "cells": nf, "hours": hours, "hold": hold,
          "rules": rules, "sensors": sensors, "score": score, "keys": {sid_of(k): k for k in keys},
          "quietFailed": quiet_failed, "appearVocabulary": dict(vocab), "folds": folds}
    for key, s in sensors.items():                # the honest per-sensor rate: the CELF cost (decision 67)
        h = placement_far([s["sensor"]], cr, share, "nested") if key[0] != "ledger" else None
        s["honest"] = h["alarms"] if h else None
        s["honestPerHour"] = h["perHour"] if h else None
        s["honestUpperPerHour"] = h["upperPerHour"] if h else None
        s["honestHours"] = h["hours"] if h else None
        s["foldsEvaluated"] = h["foldsEvaluated"] if h else None
        # F2: the CELF cost is the honest rate where some fold evaluated the sensor; none: — (no evidence), never 0
        s["celfCost"] = s["honestPerHour"]
    return cr


def calibrate(cells, share, criterion, fits_loco=None, fits_sc=None, pairs=None, hold=None, allow_range=True):
    valid = [c for c in cells if c["valid"]]
    fits_loco = fits_loco if fits_loco is not None else loco_fits3(cells)
    fits_sc = fits_sc if fits_sc is not None else fits_for3(cells)
    rates = sorted({c["rate"] for c in valid if c["target"] is None}, reverse=True)
    pairs = pairs if pairs is not None else {r: pair_fits(cells, r) for r in rates}
    if hold is None:
        holds = [c["cmd"]["B"]["mono"] - c["cmd"]["A"]["mono"] for c in valid if c["target"] is not None]
        hold = min(holds) if holds else None
    return {"share": share, "criterion": criterion, "hold": hold,
            "perRate": {r: calibrate_rate(cells, r, share, criterion, fits_loco, fits_sc[r], pairs[r], hold,
                                          allow_range) for r in rates}}


def optimistic(cal):
    """V3_OPTIMISTIC_ARM_RULE: the calibrated detector plus every dropped (sensor, rule) at the largest grid value."""
    out = {"share": cal["share"], "criterion": cal["criterion"], "hold": cal["hold"], "perRate": {}}
    for r, cr in cal["perRate"].items():
        score = dict(cr["score"])
        added = []
        for (key, rule), row in cr["rules"].items():
            if row["status"] == "dropped" and rule in LEVEL + ("absent",):
                v = ("K", v24.K_GRID[-1]) if rule in LEVEL else ("m", M_GRID[-1])
                if rule in LEVEL and row.get("madZeroRange"):
                    v = ("range", None)
                score[(key, rule)] = v
                added.append(rid(key, rule))
        out["perRate"][r] = dict(cr, score=score, optimisticAdded=sorted(added))
    return out


# =========================================================================== scoring one episode at the calibrated values

def eval_episode3(c, fit, calr, share, ws_logs):
    """v24.eval_episode with each (sensor, rule) at its calibrated value (calr {(key, rule): value}; a rule not in it
    is dropped or unarmed and never fires). Everything else is v2.4's: window, probe exclusion and moving, log timing,
    decision 57/58's silence tokens."""
    A, B = c["cmd"]["A"], c["cmd"]["B"]
    scope = {v24.ENTRY, c["target"]}
    fires, straddle, moved_out = [], [], []
    for key, (obs, vals, meta) in c["prep"].items():
        ch, svc, tok = key
        if ch not in c["chans"]:
            continue
        cal = {r: calr[(key, r)] for r in rules_of(key) if (key, r) in calr}
        if not cal:
            continue
        fam = v24.family_of(c, ch, meta)
        clk = meta["clock"]
        wins = c["probes"][clk] if (svc in scope and ch in ("log", "metric")) else ()
        obs_all = obs
        obs, vals, _ = v1.exclude(obs, vals, wins)
        a, b = A[clk], B[clk]
        a_in = math.floor(a) if (ch == "log" and ws_logs) else a
        ia, ib = bisect.bisect_left(obs, a_in), bisect.bisect_right(obs, b)
        got, ender, starter, g = {}, None, None, None
        if "appear" in cal and fit.novel(key) and ib > ia:
            got["appear"] = (obs[ia], None)
        if "absent" in cal:
            g = fit.gap_m(key, cal["absent"][1])
            if g is not None:
                t, ender, starter = v24.first_silence_bounds(obs_all, c["t0"][clk], a_in, b, g)
                if t is not None:
                    got["absent"] = (t, None)
        if ib > ia:
            res = fit.res.get(v24.instrument(ch, meta, tok))
            for rule in LEVEL:
                lv = lvl_for(fit, key, cal[rule]) if rule in cal else None
                if lv is not None:
                    thr = thresholds(fit, key, lv, cal[rule], share, res)
                    hit = level_rules_dir(obs[ia:ib], vals[ia:ib], lv[0], thr,
                                          dirs_of(key, cal[rule])).get(rule) if thr else None
                    if hit:
                        got[rule] = hit
        for rule, (t, d) in got.items():
            t_orig = t
            t, moved = v1.move_out(t, wins)
            if moved and t > b:
                moved_out.append("%s/%s" % (sid_of(key), rule))
                continue
            if ch == "log":
                lt = dt.log_ttd(t, a, ws_logs, b)
                if lt is None:
                    straddle.append("%s/%s" % (sid_of(key), rule))
                    continue
                tlo, ttd = lt
            else:
                tlo = ttd = max(0.0, t - a)
            fires.append({"ch": ch, "svc": svc, "tok": tok, "rule": rule, "ttd": ttd, "ttdLo": tlo, "dir": d,
                          "level": meta.get("level"), "family": fam, "moved": moved, "movedBy": t - t_orig,
                          "tObs": t_orig, "clock": clk, "collector": meta.get("collector"),
                          "calibratedValue": value_text(cal[rule])})
            if rule == "absent":
                toks, src = v24.silence_tokens(c, ch, svc, tok, ender)
                stoks, ssrc = v24.silence_tokens(c, ch, svc, tok, starter)
                fires[-1].update(silenceEndedBy=ender, silenceTokens=toks, silenceTokenSource=src,
                                 silenceStartedBy=starter, silenceStartTokens=stoks, silenceStartTokenSource=ssrc,
                                 silenceGap=g)
    unknown = []
    for route in sorted({r.route for r in c["ledger"]}):
        key = ("ledger", v24.ENTRY, route)
        rr = [r for r in c["ledger"] if r.route == route]
        led, silence = {}, None
        if (key, "failed") in calr:
            fl = [r.end for r in rr if not r.ok and A["mono"] <= r.end <= B["mono"]]
            if fl:
                led["failed"] = min(fl)
        if fit.level.get(key) is None and any(r.ok and A["mono"] <= r.end <= B["mono"] for r in rr):
            unknown.append(route)
        for rule in LEVEL:
            lv = lvl_for(fit, key, calr[(key, rule)]) if (key, rule) in calr else None
            if lv is not None:
                thr = thresholds(fit, key, lv, calr[(key, rule)], share, fit.res.get(("ledger",)))
                if thr:
                    out, _, _ = dt.ledger_rules(c["ledger"], A["mono"], B["mono"], rules=(rule,),
                                                base={route: (lv[0], thr["up"])})
                    if (route, rule) in out:
                        led[rule] = out[(route, rule)]
        if (key, "absent") in calr:
            g = fit.gap_m(absent_key(key), calr[(key, "absent")][1])
            if g is not None:
                t, ender, starter = v24.first_silence_bounds(sorted(r.end for r in rr), c["t0"]["mono"], A["mono"],
                                                             B["mono"], g)
                if t is not None:
                    led["absent"] = t
                    silence = (ender, sorted({r.token for r in rr if r.end == ender and r.token})
                               if ender is not None else [], starter,
                               sorted({r.token for r in rr if r.end == starter and r.token}), g)
        for rule, t in led.items():
            f = {"ch": "ledger", "svc": v24.ENTRY, "tok": route, "rule": rule, "ttd": max(0.0, t - A["mono"]),
                 "ttdLo": max(0.0, t - A["mono"]), "dir": "up", "level": None, "family": "E", "moved": False,
                 "movedBy": 0.0, "tObs": t, "clock": "mono", "collector": "workload-ledger",
                 "calibratedValue": value_text(calr[(key, rule)])}
            if rule == "absent":
                (f["silenceEndedBy"], f["silenceTokens"], f["silenceStartedBy"], f["silenceStartTokens"],
                 f["silenceGap"]) = silence
            fires.append(f)
    return fires, sorted(unknown), straddle, moved_out


def analyse3(cells, ctx, fits, cal, share):
    """v24.analyse at the calibrated values: fault episodes with scored fires (path filter, BC flags as v2.4)."""
    eps = []
    kmap = dict.fromkeys(v24.FAMILIES, KMAP_ALL)
    for c in cells:
        if not c["valid"] or c["target"] is None:
            continue
        cr = cal["perRate"].get(c["rate"])
        fires, unknown, straddle, moved_out = eval_episode3(c, fits[c["rate"]], cr["score"] if cr else {}, share,
                                                            v1.ws_of(c, ctx))
        path = v1.path_of(c["target"], ctx)
        for f in fires:
            counts, own = dt.scored(f, c["target"], path, v24.ENTRY)
            f.update({"own": own, "onPath": f["svc"] in path, "counts": counts, "admissible": True,
                      "bc": v24.bc_of(f, c, ctx, c["regime"])})
        eps.append({"cell": c.get("cellKey", c["cell"]), "regime": c["regime"], "rate": c["rate"], "block": c["block"],
                    "campaignIndex": c.get("campaignIndex", 0), "harness": c.get("harness", "sweep"),
                    "target": c["target"], "faultKind": c["faultKind"],
                    "onset": c["cmd"]["A"], "end": c["cmd"]["B"],
                    "holdSeconds": c["cmd"]["B"]["mono"] - c["cmd"]["A"]["mono"], "g3n": 1,
                    "kmap": dict(kmap) if cr else {}, "calibrated": cr is not None, "affectedPath": sorted(path),
                    "fires": fires, "ledgerRoutesWithoutBaseline": unknown, "logStraddlesHoldEnd": straddle,
                    "movedPastHoldEnd": moved_out, "_c": c})
    eps.sort(key=lambda e: (e["regime"], -e["rate"]) + v24.episode_order(e))
    return eps


# =========================================================================== decision 65: P4 over placeable sensors

def ledger_dropped(cr):
    """Armed ledger rules that are dropped at this rate (the ledger's compared rule not calibrated)."""
    if cr is None:
        return []
    return sorted(rid(k, r) for (k, r), row in cr["rules"].items() if k[0] == "ledger" and row["status"] == "dropped")


def on_path_names(cr, path):
    """Dropped (sensor, rule) pairs and non-placeable sensors (family L, M, S, T) on services of the class's path."""
    if cr is None:
        return {"droppedOnPath": [], "notPlaceableOnPath": [], "placeable": 0, "familiesWithDropped": []}
    drop = sorted(rid(k, r) for (k, r), row in cr["rules"].items()
                  if k[0] != "ledger" and row["status"] == "dropped" and k[1] in path)
    notp = sorted(s["sensor"] for k, s in cr["sensors"].items()
                  if k[0] != "ledger" and not s["placeable"] and k[1] in path)
    fams = sorted({row["family"] for (k, r), row in cr["rules"].items()
                   if k[0] != "ledger" and row["status"] == "dropped"})
    return {"droppedOnPath": drop, "notPlaceableOnPath": notp, "familiesWithDropped": fams,
            "placeable": sum(1 for k, s in cr["sensors"].items() if k[0] != "ledger" and s["placeable"])}


def p4_3(eps, scope_own, bc_view, cal, ctx):
    """v24.p4 over the placeable sensors (every fire comes from a calibrated rule; no family is muted, B1 gone), then
    decision 65's `—`: an armed ledger rule dropped at the rate. Each row names the class's dropped rules and
    non-placeable sensors on its affected path."""
    rows = v24.p4(eps, scope_own, bc_view)
    for regime, x in rows.items():
        target = v24.FAULT_TARGETS[regime][0]
        path = v1.path_of(target, ctx) | {target}
        per = {}
        for rk, v in x["perRate"].items():
            rate = float(rk)
            if v is not None:
                cr = cal["perRate"].get(rate)
                info = on_path_names(cr, path)
                v = dict(v, **info)
                led = ledger_dropped(cr)
                v["ledgerReading"] = P4_LEDGER_READING
                v["ledgerDropped"] = led
                why = None
                if cr is None:
                    why = "— (not evaluable): no no-fault cell at this rate, nothing calibrated"
                elif led and P4_LEDGER_READING == "dash-if-ledger-rule-dropped":     # reading (a), not decision 70
                    why = ("— (not evaluable): the ledger's compared rule is not calibrated at this rate (%s; reading (a), "
                           "not decision 70)" % ", ".join("`%s`" % x_ for x_ in led))
                elif not P4_OVER_PLACEABLE and info["familiesWithDropped"]:
                    why = ("— (not evaluable): family %s has a dropped rule (B1)" % ", ".join(info["familiesWithDropped"]))
                if why:
                    v = {"n": v["n"], "wins": None, "holds": None, "folds": [], "notEvaluable": True, "note": why,
                         "ledgerDropped": led, "singleEpisode": v.get("singleEpisode"), **info}
                x["perRate"][rk] = v
            per[rate] = v
        x["highestRate"] = v24.highest_rate(per)
    return rows


def p4_sets(p4rows):
    """{(view, regime, rate): sorted sensor ids}: the sensors P4 selected over the folds (n >= 2), or, with one
    episode, the candidates judged a win (descriptive)."""
    out = {}
    for view, rows in p4rows.items():
        for regime, x in rows.items():
            for rk, v in x["perRate"].items():
                if not v:
                    continue
                s = {fo["sensor"] for fo in v.get("folds") or [] if fo.get("sensor")}
                se = v.get("singleEpisode")
                if se:
                    s |= {r["sensor"] for r in se["sensors"] if r["win"]}
                if s:
                    out[(view, regime, rk)] = sorted(s)
    return out


# =========================================================================== decision 64: placement-level false alarms

def items_of(cr, sids, fold=None):
    """[(key, rule, value)] of the sensors: the calibrated values (fold None), or the values re-selected without the
    held-out cell `fold` (V3_NESTED_RULE; a rule with no such value is not in that cell's detector). The ledger's
    exempt `failed` never enters a false-alarm count."""
    out = []
    for s in sids:
        key = cr["keys"].get(s)
        if key is None:
            continue
        for r in rules_of(key):
            if fold is None:
                if (key, r) in cr["score"] and cr["rules"][(key, r)]["status"] != "exempt":
                    out.append((key, r, cr["score"][(key, r)]))
                continue
            row = cr["rules"].get((key, r))
            nested = (row or {}).get("nested")
            if row is None or row["status"] == "exempt" or not nested or nested[fold] is None:
                continue
            out.append((key, r, row["values"][nested[fold]]))
    return out


def placement_far(sids, cr, share, mode="nested", folds=None):
    """Decision 64 as amended by 67 (V3_PLACEMENT_FAR_RULE): the union alarm count of the sensors' rules, the union
    detector restarted after each alarm. mode `nested`: each held-out no-fault cell of the rate with its leave-one-
    cell-out fit and the values re-selected without it (the honest count); `calibrated`: the calibrated values on
    `folds` [(cell, fit)] (validation). F2: only folds where at least one of the set's rules is in the detector and
    armed count, alarms and hours alike (`hours`; the rate's whole time `totalHours` beside); with no such fold the
    count is None (—, not 0). The per-sensor counts and their sum beside (UNION_FAR False, planted defect: the sum is
    reported as the placement's count)."""
    folds = cr["folds"] if mode == "nested" else folds
    total = sum((X["end"]["mono"] - X["t0"]["mono"]) / v24.S_PER_HOUR for X, _ in folds)
    union, per, rules_, hours, evaluated = 0, Counter(), set(), 0.0, 0
    for i, (X, F) in enumerate(folds):
        items = items_of(cr, sids, i if mode == "nested" else None)
        rules_.update(rid(k, r) for k, r, _ in items)
        info = {}
        alarms = simulate(X, F, items, share, info) if items else []
        if not info.get("armed") and HONEST_EVALUATED_ONLY:
            continue
        evaluated += 1
        hours += (X["end"]["mono"] - X["t0"]["mono"]) / v24.S_PER_HOUR
        union += len(alarms)
        if len(sids) > 1:
            for s in sids:
                key = cr["keys"].get(s)
                its = [x for x in items if x[0] == key]
                if its:
                    per[s] += len(simulate(X, F, its, share))
    if len(sids) == 1:
        per[sids[0]] = union
    n = (union if UNION_FAR else sum(per.values())) if evaluated else None
    return {"sensors": list(sids), "mode": mode, "rules": sorted(rules_), "alarms": n, "union": union if evaluated
            else None, "sumOverSensors": sum(per.values()) if evaluated else None, "perSensor": dict(per),
            "cells": len(folds), "foldsEvaluated": evaluated, "hours": hours if evaluated else None,
            "totalHours": total, "perHour": (n / hours) if (evaluated and hours) else None,
            "upperPerHour": bound(n, hours) if (evaluated and hours) else None}


def family_honest(cr, share):
    """Per family at a rate: the honest nested union of all its sensors' rules (the procedure: every rule re-selected
    without each held-out cell), and the sum of the per-rule honest counts of its fully calibrated rules (the
    reviewer's tally, tmp/v3review/v3_feasibility.py nestedUnionAlarms, for the cross-check)."""
    out = {}
    for f in sorted({s["family"] for s in cr["sensors"].values()}):
        sids = sorted(s["sensor"] for s in cr["sensors"].values() if s["family"] == f)
        u = placement_far(sids, cr, share, "nested")
        rows = [row for row in cr["rules"].values() if row["family"] == f and row["status"] == "calibrated"]
        tally = sum(row["honest"] or 0 for row in rows)
        out[f] = {"union": u["alarms"], "perHour": u["perHour"], "upperPerHour": u["upperPerHour"],
                  "sumCalibratedRuleHonest": tally, "hours": u["hours"], "totalHours": u["totalHours"],
                  "calibratedWithoutEvidence": sum(1 for row in rows if row["honest"] is None),
                  "placeableWithoutCost": sum(1 for s in cr["sensors"].values() if s["family"] == f
                                              and s["placeable"] and s.get("celfCost") is None)}
    return out


def held_out_folds(cells, fits_loco, rate):
    return [(X, fits_loco[id(X)]) for X in cells if X["valid"] and X["target"] is None and X["rate"] == rate]


# =========================================================================== decision 65: out-of-sample check

def validation(val_cells, cal, cells, fits_sc, share, sets):
    """V3_VALIDATION_RULE: the calibrated detectors on extra no-fault cells with the main cells' pooled fit (no
    refit; VALIDATION_NO_REFIT False, planted defect: the validation cells pooled into the fit)."""
    out = {"notUsed": [{"cell": c["cell"], "reason": c.get("reason") or "a fault cell (validation uses no-fault cells "
                                                                          "only)"}
                       for c in val_cells if not c["valid"] or c["target"] is not None], "perRate": {}}
    use = [c for c in val_cells if c["valid"] and c["target"] is None]
    for rate in sorted({c["rate"] for c in use}, reverse=True):
        xs = [c for c in use if c["rate"] == rate]
        cr = cal["perRate"].get(rate)
        if cr is None:
            out["perRate"][rate] = {"cells": len(xs), "note": "no calibration at this rate: —"}
            continue
        if VALIDATION_NO_REFIT:
            F = fits_sc[rate]
        else:
            F = Fit3([c for c in cells if c["valid"]] + xs, rate, res_cells=[c for c in cells if c["valid"]] + xs)
        folds = [(X, F) for X in xs]
        hours = sum((X["end"]["mono"] - X["t0"]["mono"]) / v24.S_PER_HOUR for X in xs)
        per_rule = {}
        for (key, rule), value in sorted(cr["score"].items(), key=lambda kv: rid(*kv[0])):
            n = sum(len(simulate(X, F, [(key, rule, value)], share)) for X in xs)
            if n:
                per_rule[rid(key, rule)] = n
        placeable = sorted(s["sensor"] for k, s in cr["sensors"].items() if k[0] != "ledger" and s["placeable"])
        per_sensor = {}
        for s in placeable:
            n = placement_far([s], cr, share, "calibrated", folds)["alarms"]
            if n:
                per_sensor[s] = n
        out["perRate"][rate] = {
            "cells": len(xs), "hours": hours, "boundZeroPerHour": bound(0, hours), "rulesAlarming": per_rule,
            "rulesCalibrated": len(cr["score"]), "sensorsAlarming": per_sensor, "sensorsPlaceable": len(placeable),
            "allPlaceable": placement_far(placeable, cr, share, "calibrated", folds),
            "freshLimitZeroPerHour": bound(0, hours),
            "sets": {"%s %s r%s" % k: placement_far(v, cr, share, "calibrated", folds) for k, v in sets.items()
                     if float(k[2]) == rate}}
    return out


# =========================================================================== campaign B reader: freeze stamps

@contextlib.contextmanager
def admit_b_epochs():
    """STUDY_EPOCHS_B: the system's campaign-B study epochs admitted beside SYSTEM_<SUT>.studyEpochs while cells are
    read (v2.4's registry entry is restored on exit; v2.4's file is not touched)."""
    name = "SYSTEM_" + v24.SYSTEM.upper()
    extra = STUDY_EPOCHS_B.get(v24.SYSTEM) or []
    if name not in v24.REGISTRY or not extra:
        yield
        return
    entry = v24.REGISTRY[name]
    saved = entry["value"]
    entry["value"] = dict(saved, studyEpochs=list(saved["studyEpochs"]) + [e for e in extra
                                                                          if e not in saved["studyEpochs"]])
    try:
        yield
    finally:
        entry["value"] = saved


def study_epoch_of(d):
    """The cell's study epoch as its receipt names it (TeaStore receipt.json studyEpoch, OTel runKey.studyEpoch)."""
    try:
        rc = json.loads((Path(d) / "receipt.json").read_text())
    except (OSError, ValueError):
        return None
    return rc.get("studyEpoch") or (rc.get("runKey") or {}).get("studyEpoch")


def harness_of(epoch):
    """V3_HARNESS_TAG_RULE: `B` for a campaign-B epoch (H10 and H4 in the harness), else `sweep`."""
    return "B" if (HARNESS_TAG and epoch in (STUDY_EPOCHS_B.get(v24.SYSTEM) or [])) else "sweep"


@contextlib.contextmanager
def admit_b_schema(d):
    """V3_B_SCHEMA_ADDITIONS: a campaign-B cell's intervention.json carries keys the pinned sweep schema does not (OTel:
    `freeze`); admitted for that cell only, v2.4's entry restored on exit (a sweep cell keeps the exact key set)."""
    add = (B_SCHEMA_ADDITIONS.get(v24.SYSTEM) or {}).get("intervention.json") or []
    sch = (v24.SCHEMAS.get(v24.SYSTEM) or {}).get("intervention.json")
    if not add or harness_of(study_epoch_of(d)) != "B" or not isinstance(sch, dict) or "keys" not in sch:
        yield
        return
    saved = sch["keys"]
    sch["keys"] = sorted(set(saved) | set(add))
    try:
        yield
    finally:
        sch["keys"] = saved


def _keys_or_stop(obj, pinned, where):
    """V3_B_RECORD_KEYS: a record whose key set is not the pinned one is a schema the reader does not know (stop);
    a record of the known shape whose content is wrong is a decision-69 problem, not a stop."""
    if not isinstance(obj, dict) or set(obj) != set(pinned):
        raise v24.UnknownSchema("%s: keys %s, the pinned harness writes %s" % (
            where, sorted(obj) if isinstance(obj, dict) else type(obj).__name__, sorted(pinned)))


def _verdict_problems(status_ok, status, failures, reasons, where):
    """Decision 69's record: status / failures / reasons must agree; any reason of a non-ok record is a problem, and a
    record that disagrees with itself is contradictory (a problem, never a stop)."""
    out = []
    if not H4_RECORD_STATUS:
        return out
    if status != status_ok:
        out += ["%s: %s" % (where, r) for r in reasons] or ["%s: status %r with no reason (contradictory record)" % (
            where, status)]
    elif reasons:
        out.append("%s: status %r with %d reason(s) (contradictory record)" % (where, status, len(reasons)))
    if failures != len(reasons):
        out.append("%s: failures %r is not the number of reasons %d (contradictory record)" % (
            where, failures, len(reasons)))
    return out


def read_docker_events_file(p, c, target_id=None):
    """docker-events.json / .jsonl: (events [{action, service, tMono, timeNano, source}], problems, record). Two shapes:
    Hotel's (one Docker event object per line, or a JSON array of them; time = timeNano mapped wall -> the ledger clock
    by the cell's fit) and OTel B's object (kind otel-demo-fault-docker-events-v1, decision 69: verdict {status ok |
    missing | contradictory, failures, reasons [{kind, reason}]}, stream error / exitedBeforeStop, parseProblems; the
    events of the target container only, their monotonic re-derived as the producer does, bm + (timeNano/1e9 - be),
    F7). Any other shape: UnknownSchema."""
    text = p.read_text()
    try:
        doc = json.loads(text)
    except ValueError:
        try:
            doc = [json.loads(x) for x in text.splitlines() if x.strip()]
        except ValueError as exc:
            raise v24.UnknownSchema("%s: neither JSON nor JSON lines: %s" % (p.name, exc))
    if isinstance(doc, dict):
        if doc.get("kind") != OTEL_EVENTS_KIND or doc.get("schemaVersion") != 1:
            raise v24.UnknownSchema("%s: kind %r schemaVersion %r; the reader knows Hotel's lines and %s / 1" % (
                p.name, doc.get("kind"), doc.get("schemaVersion"), OTEL_EVENTS_KIND))
        pins = B_RECORD_KEYS["otel"]
        _keys_or_stop(doc, pins["dockerEvents"], p.name)
        verdict, stream, clock = doc["verdict"], doc["stream"] or {}, doc["clock"] or {}
        _keys_or_stop(verdict, pins["verdict"], p.name + " verdict")
        reasons = ["%s: %s" % (r.get("kind"), r.get("reason")) if isinstance(r, dict) else str(r)
                   for r in verdict["reasons"] or []]
        problems = _verdict_problems("ok", verdict["status"], verdict["failures"], reasons, "docker events verdict")
        if verdict["status"] not in ("ok", "missing", "contradictory"):
            problems.append("docker events verdict status %r unknown (contradictory record)" % verdict["status"])
        surfaced = {"streamError": stream.get("error"), "exitedBeforeStop": stream.get("exitedBeforeStop"),
                    "parseProblems": list(doc["parseProblems"] or [])}
        if verdict["status"] == "ok" and (surfaced["streamError"] is not None or surfaced["exitedBeforeStop"]
                                          is not False or surfaced["parseProblems"]):
            problems.append("docker events verdict ok but the stream reports %s (contradictory record)" % surfaced)
        if target_id is not None and doc["containerId"] != target_id:
            problems.append("docker events containerId %r is not the receipt's target %r" % (doc["containerId"],
                                                                                            target_id))
        bm, be = clock.get("barrierMonotonic"), clock.get("barrierEpoch")
        out, foreign = [], 0
        for e in doc["events"] or []:
            _keys_or_stop(e, pins["event"], p.name + " event")
            if CONTAINER_FILTER and e["containerId"] != doc["containerId"]:
                foreign += 1
                continue
            if bm is None or be is None or abs((bm + (e["timeNano"] / v24.NS_PER_S - be)) - e["monotonic"]) > \
                    FREEZE_REPLAY_TOL:
                problems.append("event monotonic does not replay bm + (timeNano/1e9 - be)")
            out.append({"action": e["action"], "service": c["target"], "timeNano": e["timeNano"],
                        "tMono": float(e["monotonic"]),
                        "source": "%s (%s, the producer's mapping bm + (timeNano/1e9 - be))" % (p.name,
                                                                                               OTEL_EVENTS_KIND)})
        rec = dict(surfaced, verdictStatus=verdict["status"], verdictFailures=verdict["failures"],
                   otherContainerEvents=foreign)
        return out, problems, rec
    rows = doc if isinstance(doc, list) else None
    if rows is None:
        raise v24.UnknownSchema("%s: a JSON %s" % (p.name, type(doc).__name__))
    out = []
    for r in rows:
        act = (r.get("Action") or r.get("status")) if isinstance(r, dict) else None
        tn = r.get("timeNano") if isinstance(r, dict) else None
        if not isinstance(act, str) or not isinstance(tn, (int, float)) or isinstance(tn, bool):
            raise v24.UnknownSchema("%s: an event without Action/status or timeNano: %r" % (p.name, r))
        attrs = (r.get("Actor") or {}).get("Attributes") or {}
        out.append({"action": act, "service": attrs.get("com.docker.compose.service"), "timeNano": tn,
                    "tMono": tn / v24.NS_PER_S - c["align"]["offset"],
                    "source": "%s (timeNano, wall -> ledger clock by the cell's fit)" % p.name})
    return out, [], {}


def _validator_h4(d):
    """The TeaStore validator's own h4 observation (candidate-validation.json, sweep-fault-command-stamps), if any."""
    try:
        doc = json.loads((d / "candidate-validation.json").read_text())
    except (OSError, ValueError):
        return None
    stack = [doc]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            h = x.get("h4")
            if isinstance(h, dict) and "status" in h:
                return h
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return None


def read_freeze_stamps(d, c):
    """TeaStore B (intervention.json sweep.freezeStamps, version h4-h10-v1, decision 69 at bbb6b11): (events, record,
    problems). status `recorded` | `missing` with failures and failureCount; a status other than recorded makes its
    failures the problems; failures and failureCount must agree, and `missing` with no failure is contradictory;
    rows of another container or type are left out (F11); the validator's own h4 status is cross-read. A B cell whose
    record is null: a problem ('freezeStamps null'). None: the cell carries no freezeStamps key (a sweep cell)."""
    p = d / "intervention.json"
    if v24.SYSTEM != "teastore" or not p.exists():
        return None
    sweep = json.loads(p.read_text()).get("sweep") or {}
    if "freezeStamps" not in sweep:
        return None
    fs = sweep["freezeStamps"]
    if fs is None:
        return [], {"status": None}, ["freezeStamps null"]
    if not isinstance(fs, dict) or fs.get("version") != FREEZE_VERSION or fs.get("schemaVersion") != 1:
        raise v24.UnknownSchema("%s intervention.json sweep.freezeStamps: version %r schemaVersion %r, the reader "
                                "knows %s / 1" % (d.name, fs.get("version") if isinstance(fs, dict) else fs,
                                                  fs.get("schemaVersion") if isinstance(fs, dict) else None,
                                                  FREEZE_VERSION))
    pins = B_RECORD_KEYS["teastore"]
    _keys_or_stop(fs, pins["freezeStamps"], d.name + " freezeStamps")
    failures = list(fs["failures"] or [])
    problems = []
    if not H4_RECORD_STATUS:
        pass
    elif fs["status"] not in ("recorded", "missing"):
        problems.append("freezeStamps status %r is neither recorded nor missing (contradictory record)" % fs["status"])
    if H4_RECORD_STATUS and fs["status"] != "recorded":
        problems += ["freezeStamps: %s" % f for f in failures] or [
            "freezeStamps status %r with no failure (contradictory record)" % fs["status"]]
    elif H4_RECORD_STATUS and failures:
        problems.append("freezeStamps recorded with %d failure(s) (contradictory record)" % len(failures))
    if H4_RECORD_STATUS and fs["failureCount"] != len(failures):
        problems.append("freezeStamps failureCount %r is not the number of failures %d (contradictory record)" % (
            fs["failureCount"], len(failures)))
    vh = _validator_h4(d)
    if vh is not None and vh.get("status") != fs["status"]:
        problems.append("the validator's h4 status %r differs from the record's %r" % (vh.get("status"), fs["status"]))
    shift = c["receiptAlign"]["offset"] if (v24.RECEIPT_CLOCK_MAP and c.get("receiptAlign")) else 0.0
    ev = fs["events"] or {}
    out, foreign = [], 0
    for r in ev.get("rows") or []:
        _keys_or_stop(r, pins["row"], d.name + " freezeStamps row")
        if CONTAINER_FILTER and (r["containerId"] != fs["targetContainerId"] or r["type"] != "container"):
            foreign += 1
            continue
        out.append({"action": r["action"], "service": c["target"], "timeNano": r["timeNano"],
                    "tMono": shift + float(r["monotonicOffsetSeconds"]),
                    "source": "intervention.json sweep.freezeStamps (monotonicOffsetSeconds, producer clock mapped "
                              "to the ledger's)"})
    rec = {"version": fs["version"], "status": fs["status"], "failureCount": fs["failureCount"],
           "commands": fs["commands"], "readbacks": len(fs["readbacks"] or []), "foreignRows": foreign,
           "validatorH4": vh, "toleranceSeconds": fs["toleranceSeconds"]}
    return out, rec, problems


def read_otel_freeze(d, c):
    """OTel B (intervention.json `freeze`, kind otel-demo-fault-freeze-stamps-v1, decision 69 at c4aa313): (record,
    problems, target container id). Its stampCheck {status ok | missing | contradictory, failures, reasons} as a
    decision-69 record; the command-issued stamp must replay the receipt's startedMonotonic. A null `freeze`: a
    problem. None: the receipt carries no `freeze` key (a sweep cell)."""
    p = d / "intervention.json"
    if v24.SYSTEM != "otel" or not p.exists():
        return None
    iv = json.loads(p.read_text())
    if "freeze" not in iv:
        return None
    fz, target_id = iv["freeze"], iv.get("targetContainerId")
    if fz is None:
        return {"status": None}, ["intervention freeze null"], target_id
    if not isinstance(fz, dict) or fz.get("kind") != OTEL_FREEZE_KIND or fz.get("schemaVersion") != 1:
        raise v24.UnknownSchema("%s intervention.json freeze: kind %r schemaVersion %r, the reader knows %s / 1" % (
            d.name, fz.get("kind") if isinstance(fz, dict) else fz,
            fz.get("schemaVersion") if isinstance(fz, dict) else None, OTEL_FREEZE_KIND))
    pins = B_RECORD_KEYS["otel"]
    _keys_or_stop(fz, pins["freeze"], d.name + " freeze")
    sc = fz["stampCheck"]
    _keys_or_stop(sc, pins["stampCheck"], d.name + " freeze stampCheck")
    reasons = ["%s: %s" % (r.get("kind"), r.get("reason")) if isinstance(r, dict) else str(r)
               for r in sc["reasons"] or []]
    problems = _verdict_problems("ok", sc["status"], sc["failures"], reasons, "freeze stampCheck")
    issued = fz["commandIssuedMonotonic"]
    if issued is None or abs(float(issued) - c["cmd"]["A"]["mono"]) > FREEZE_REPLAY_TOL:
        problems.append("commandIssuedMonotonic %r does not replay startedMonotonic %r" % (issued,
                                                                                         c["cmd"]["A"]["mono"]))
    rec = {k: fz[k] for k in ("action", "commandIssuedMonotonic", "commandReturnedMonotonic",
                              "stateReadbackMonotonic", "dockerEventsFile")}
    rec["stampCheckStatus"] = sc["status"]
    return rec, problems, target_id


def apply_freeze_events(c, d):
    """V3_FREEZE_EVENTS_RULE (decisions 54, 69): a TeaStore/OTel fault cell whose H4 record carries exactly one Docker
    `pause` event of its target, inside [command issued - tol, the cell's v2.4 upper bound + tol] and with no problem
    recorded, gets that event as its onset interval's upper bound. Otherwise its H4 record is `missing` with the reasons
    (decision 69): the cell stays valid and keeps the sweep's bound (v2.4's: TeaStore command returned, OTel
    appliedMonotonic, F6), and it is counted. Sweep cells carry no record (`not recorded`); throttle cells keep v2.4's
    bound, the record kept."""
    events, sources, problems, recs = [], [], [], {}
    oz = read_otel_freeze(d, c)
    target_id = oz[2] if oz is not None else None
    for name in DOCKER_EVENT_FILES:
        if (d / name).exists():
            ev, pr, rec = read_docker_events_file(d / name, c, target_id)
            events += ev
            problems += pr
            recs[name] = rec
            sources.append(name)
    fs = read_freeze_stamps(d, c)
    if fs is not None:
        events += fs[0]
        recs["freezeStamps"] = fs[1]
        problems += fs[2]
        sources.append("intervention.json sweep.freezeStamps")
    if oz is not None:
        recs["freeze"] = oz[0]
        problems += oz[1]
        sources.append("intervention.json freeze")
    if recs:
        c["freezeStamps"] = recs
    expected = c.get("harness") == "B"
    h4 = {"expected": expected, "sources": sources, "reasons": list(problems), "status": None}
    c["h4"] = h4
    if not sources:
        h4["status"] = "missing" if expected else "not recorded (sweep harness)"
        if expected:
            h4["reasons"].append("no freeze record in a campaign-B cell")
        return c
    c["dockerEvents"] = events
    if c["faultKind"] not in dt.STOPPING or not c.get("onset"):
        h4["status"] = "missing" if problems else "recorded (throttle: command and readback stamps; v2.4's bound kept)"
        return c
    on = c["onset"]
    before = {"hi": on["hi"], "hiSource": on["hiSource"]}
    ev = [e for e in events if e["action"] == c["faultKind"] and e["service"] == c["target"]]
    if len(ev) != 1:
        h4["reasons"].append("%d `%s` events of %s (exactly one expected)" % (len(ev), c["faultKind"], c["target"]))
    elif before["hi"] is not None and not (on["lo"] - FREEZE_TOL <= ev[0]["tMono"] <= before["hi"] + FREEZE_TOL):
        h4["reasons"].append("the `%s` event at %.6f s lies outside [command issued - %g, upper bound + %g]" % (
            c["faultKind"], ev[0]["tMono"] - on["lo"], FREEZE_TOL, FREEZE_TOL))
    if not h4["reasons"]:
        e = ev[0]
        on.update(hi=e["tMono"], hiKind="docker-event", commandReturnedBound=before,
                  hiSource="Docker `%s` event of %s, %s" % (c["faultKind"], c["target"], e["source"]))
        h4["status"] = "used"
    elif H4_FALLBACK:
        h4["status"] = "missing"
        on.update(commandReturnedBound=before, h4Missing=list(h4["reasons"]),
                  hiSource="%s (H4 record missing: %s; decision 69 fallback)" % (before["hiSource"],
                                                                                 "; ".join(h4["reasons"])))
    else:                                                   # planted defect: Hotel's — instead of the fallback
        h4["status"] = "missing"
        on.update(hi=None, hiKind="docker-event", commandReturnedBound=before,
                  hiSource="no usable Docker `%s` event: —" % c["faultKind"])
    return c


def load3(load, d):
    with admit_b_schema(d):
        c = load(d)
    if c.get("valid"):
        c["studyEpoch"] = c.get("studyEpoch") or study_epoch_of(d)
        c["harness"] = harness_of(c["studyEpoch"]) if v24.SYSTEM != "hotel" else "sweep"
        if c.get("target") is not None and v24.SYSTEM != "hotel" and FREEZE_EVENT_ONSET:
            apply_freeze_events(c, Path(d))
        censor_stats(c)
    return c


def pool_key(root, d):
    """V3_POOL_KEY_RULE (decisions 68, 69): a cell is (its campaign directory, its path inside it). Quiet run A2 repeats
    A's plan and run IDs under a new campaign, so the run path alone is not an identity (POOL_KEY_CAMPAIGN False,
    planted defect)."""
    rel = Path(d).resolve().relative_to(Path(root).resolve()).as_posix()
    return (str(Path(root).resolve()), rel) if POOL_KEY_CAMPAIGN else rel


def find_and_load3(campaigns):
    find, load = v24.system_io()
    found, cells, seen = [], [], {}
    with admit_b_epochs():
        for i, campaign in enumerate(campaigns):
            root, dirs = find(campaign)
            found.append((root, dirs))
            for d in dirs:
                k = pool_key(root, d)
                if k in seen:
                    raise SystemExit("cell %s given twice (campaigns %d and %d): pooling keys on (campaign, run path)" % (
                        k, seen[k], i))
                seen[k] = i
                c = load3(load, d)
                c["campaignIndex"] = i
                c["poolKey"] = k
                c["cellKey"] = ("%s :: %s" % k) if (CELL_KEY_POOL and isinstance(k, tuple)) else c["cell"]
                cells.append(c)
    return found, cells


def input_digest3(root, dirs):
    files = tuple(v24.READ_FILES) + tuple(f for f in DOCKER_EVENT_FILES if f not in v24.READ_FILES)
    rows = []
    for p in [root / "runtime-admission.json"] + [d / f for d in dirs for f in files]:
        if p.is_file():
            rows.append("%s\t%d" % (p.relative_to(root).as_posix(), p.stat().st_size))
    rows.sort()
    return {"files": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}


def input_digest_multi3(found):
    per = [input_digest3(r, d) for r, d in found]
    return {"files": sum(x["files"] for x in per),
            "sha256": hashlib.sha256("\n".join(x["sha256"] for x in per).encode()).hexdigest(), "perCampaign": per}


# =========================================================================== whole campaign

def run(campaign, system="hotel", validation_dirs=(), reference=True):
    """campaign: one directory or a list (one system, pooled, H1). validation_dirs: no-fault campaigns for the
    out-of-sample check (decision 65), never pooled. reference False skips v2.4's family table (tests)."""
    with v24.use_system(system):
        return _run(campaign, list(validation_dirs), reference)


def _run(campaign, validation_dirs, reference):
    campaigns = [campaign] if isinstance(campaign, (str, Path)) else list(campaign)
    located, cells = find_and_load3(campaigns)
    single = len(located) == 1
    valid = [c for c in cells if c["valid"]]
    ctx = v24.make_ctx(valid)
    fits = fits_for3(cells)
    lf = loco_fits3(cells)
    rates = sorted({c["rate"] for c in valid}, reverse=True)
    pairs = {r: pair_fits(cells, r) for r in sorted({c["rate"] for c in valid if c["target"] is None})}
    shares = {"primary": v24.ARMS["primary"], "arm": v24.ARMS["arm"], "atMostOne": v24.ARMS["primary"],
              "optimistic": v24.ARMS["primary"]}
    cal = {"primary": calibrate(cells, shares["primary"], MAX_ALARMS, lf, fits, pairs),
           "arm": calibrate(cells, shares["arm"], MAX_ALARMS, lf, fits, pairs),
           "atMostOne": calibrate(cells, shares["atMostOne"], SENS_ALARMS, lf, fits, pairs,
                                  allow_range=not SENSITIVITY_NO_RANGE)}
    if OPTIMISTIC_ARM:
        cal["optimistic"] = optimistic(cal["primary"])
    res = {}
    for s in [x for x in SETTINGS if x in cal]:
        eps = analyse3(cells, ctx, fits, cal[s], shares[s])
        p4 = {"P4a": p4_3(eps, False, False, cal[s], ctx), "P4b": p4_3(eps, True, False, cal[s], ctx),
              "P4a withBC": p4_3(eps, False, True, cal[s], ctx), "P4b withBC": p4_3(eps, True, True, cal[s], ctx)}
        res[s] = {"eps": eps, "primary": v24.primary_table(eps, None), "P4": p4}
    prim = res["primary"]["eps"]
    expo = v24.exposure(cells, prim)
    pred = {"P1": v24.predictions_p1(prim), "P2": v24.predictions_p2(prim), "P3": v24.predictions_p3(prim),
            "P4": {k: res["primary"]["P4"][k] for k in ("P4a", "P4b")}}
    far = {}
    for s in ("primary", "atMostOne"):
        sets = p4_sets({k: res[s]["P4"][k] for k in ("P4a", "P4b")})
        rows = {}
        for (view, regime, rk), sids in sorted(sets.items()):
            cr = cal[s]["perRate"].get(float(rk))
            if cr:
                rows["%s %s r%s" % (view, regime, rk)] = placement_far(sids, cr, shares[s], "nested")
        allp, fam = {}, {}
        for r, cr in cal[s]["perRate"].items():
            placeable = sorted(x["sensor"] for k, x in cr["sensors"].items() if k[0] != "ledger" and x["placeable"])
            allp[r] = placement_far(placeable, cr, shares[s], "nested")
            fam[r] = family_honest(cr, shares[s])
        far[s] = {"sets": rows, "allPlaceable": allp, "families": fam, "_sets": sets}
    val = None
    if validation_dirs:
        vlocated, vcells = find_and_load3(validation_dirs)
        val = {"campaigns": [str(r) for r, _ in vlocated],
               "input": input_digest_multi3(vlocated),
               "primary": validation(vcells, cal["primary"], cells, fits, shares["primary"], far["primary"]["_sets"])}
    ref = None
    if reference:
        op = v24.operating_point(cells, v24.ARMS["primary"], v24.loco_fits(cells), ctx)
        ref = {"op": op, "kmap": v24.kmaps_from(op, rates)}
    found = Counter((c["regime"], c["rate"]) for c in cells)
    vcount = Counter((c["regime"], c["rate"]) for c in valid)
    root = located[0][0]
    hc = v1.harness_commit(root) if v24.SYSTEM == "hotel" else (
        ", ".join(sorted({c["harnessCommit"] for c in cells if c.get("harnessCommit")})) or None)
    prov = {"harnessCommit": hc,
            "planSha256": sorted({c["planSha256"] for c in cells if c.get("planSha256")}),
            "input": input_digest3(root, located[0][1]) if single else input_digest_multi3(located)}
    return {"system": v24.SYSTEM, "campaign": root if single else [r for r, _ in located],
            "campaigns": [str(r) for r, _ in located], "cells": cells, "ctx": ctx, "fits": fits, "cal": cal,
            "results": res, "predictions": pred, "exposure": expo, "far": far, "validation": val, "reference": ref,
            "found": found, "valid": vcount, "provenance": prov, "secondary": v24.secondary_table(prim),
            "perSensor": v24.per_sensor(prim, expo), "decision57": v24.decision57_summary(pred)}


# =========================================================================== summaries

def cal_summary(cr):
    """Counts of a rate's calibration: rules per family by status and calibrated kind (range under MAD = 0 apart, K =
    100 at grid edge); sensors placeable (appear-only apart) / not; degrees of freedom (calibrated rules carrying a
    value: K, range, m); the honest nested count per family (sum of rule counts) is in the placement report."""
    fam = defaultdict(Counter)
    for (key, rule), row in cr["rules"].items():
        f = fam[row["family"]]
        f[row["status"]] += 1
        if row["status"] == "calibrated":
            f["kind:" + row["value"][0]] += 1
            f["gridEdge"] += bool(row.get("gridEdge"))
            f["noNestedEvidence"] += row.get("honest") is None
            f["outOfDetectorEveryFold"] += row.get("nestedOutOfDetector") == cr["cells"]
            f["rangeMadZero"] += bool(row.get("madZeroRange") and row["value"][0] == "range")
    sens = defaultdict(Counter)
    for key, s in cr["sensors"].items():
        sens[s["family"]]["appearOnly" if s.get("appearOnly") else "placeable" if s["placeable"] else
                          "notPlaceable"] += 1
    dof = sum(1 for row in cr["rules"].values() if row["status"] == "calibrated" and row["value"][0] != "none")
    armed = [row["foldsArmed"] for row in cr["rules"].values() if row["status"] == "calibrated"
             and row.get("foldsArmed") is not None]
    return {"rules": {f: dict(c) for f, c in fam.items()}, "sensors": {f: dict(c) for f, c in sens.items()},
            "degreesOfFreedom": dof, "hold": cr["hold"],
            "foldsArmedMedian": statistics.median(armed) if armed else None,
            "placeableWithoutCost": sorted(s["sensor"] for s in cr["sensors"].values() if s["family"] != "E"
                                           and s["placeable"] and s.get("celfCost") is None),
            "appearOnly": sorted(s["sensor"] for s in cr["sensors"].values() if s.get("appearOnly")),
            "inert": sorted(rid(k, r) for (k, r), row in cr["rules"].items() if row["status"] == "inert"),
            "gridEdge": sorted(rid(k, r) for (k, r), row in cr["rules"].items() if row.get("gridEdge")
                               and row["status"] == "calibrated")}


def ledger_mix(eps):
    """E's catching rule per (class, rate) in the primary episodes (decision 67: E's rule mix printed)."""
    out = {}
    for e in eps:
        f = v24.col_fire(e, "E", True)
        out.setdefault("%s r%g" % (short(e["regime"]), e["rate"]), Counter())[
            v24.DASH if f in (None, "absent") else f["rule"]] += 1
    return {k: dict(v) for k, v in sorted(out.items())}


def absent_gap3(R):
    """The ledger's calibrated `absent` gap against the client timeout per rate, and in the pause episodes how often
    `absent` came before the first `failed` (v2.4's minor, at v3's calibrated gap)."""
    out = {}
    eps = R["results"]["primary"]["eps"]
    stopping = [g for g in v24.FAULT_REGIMES if v24.FAULT_TARGETS[g][1] in dt.STOPPING]
    for rate, cr in sorted(R["cal"]["primary"]["perRate"].items(), reverse=True):
        cells = [c for c in R["cells"] if c["valid"] and c["rate"] == rate]
        T = sorted({float(c["timing"]["requestTimeoutSeconds"]) for c in cells
                    if c["timing"].get("requestTimeoutSeconds") is not None})
        gaps = {}
        for (key, rule), row in cr["rules"].items():
            if key[0] == "ledger" and rule == "absent":
                gaps[key[2]] = {"status": row["status"], "value": value_text(row["value"]), "g": row.get("g")}
        pe = [e for e in eps if e["regime"] in stopping and e["rate"] == rate]
        before = 0
        for e in pe:
            ab = [x["ttd"] for x in e["fires"] if x["family"] == "E" and x["rule"] == "absent"]
            fa = [x["ttd"] for x in e["fires"] if x["family"] == "E" and x["rule"] == "failed"]
            before += bool(ab) and (not fa or min(ab) < min(fa))
        out["%g" % rate] = {"routes": gaps, "timeoutSeconds": T, "stoppingEpisodesAbsentBeforeFirstFailed":
                            [before, len(pe)]}
    return out


def reference_table(R):
    """v2.4's family operating point (decision 53, 15/h) beside v3, from v2.4's own operating_point."""
    ref = R.get("reference")
    if not ref:
        return None
    op, km = ref["op"], ref["kmap"]
    out = {}
    for regime in v24.FAULT_REGIMES:
        for f in v24.FAMILIES:
            row = {}
            for r, m in km[regime].items():
                if op["fitted"][f].get("notCollected"):
                    row["%g" % r] = "n/c"
                else:
                    row["%g" % r] = ("ok (K %g)" % m[f]) if m[f] is not None else "no"
            out["%s %s" % (regime, f)] = row
    return {"table": out, "K": {g: op["fitted"][g]["K"] for g in list(v24.FAMILIES) + ["system"]}}


def harness_breakdown(R):
    """V3_HARNESS_TAG_RULE: beside the pooled verdicts, per harness (sweep / B): P4 folds by the held-out episode's
    harness (wins / folds) in every view and arm, P2 episodes within the bound, P1 episodes holding, and the H4 record
    status of every valid fault cell."""
    eps = R["results"]["primary"]["eps"]
    tags = sorted({e["harness"] for e in eps} | {c.get("harness", "sweep") for c in R["cells"] if c["valid"]})
    out = {"tags": tags, "episodes": {}, "P4": {}, "P2": {}, "P1": {}, "H4": {}}
    for e in eps:
        k = "%s r%g" % (short(e["regime"]), e["rate"])
        out["episodes"].setdefault(k, Counter())[e["harness"]] += 1
    out["episodes"] = {k: dict(v) for k, v in out["episodes"].items()}
    for arm in [a for a in ("primary", "optimistic") if a in R["results"]]:
        for view in ("P4a", "P4b"):
            for regime, x in R["results"][arm]["P4"][view].items():
                for rk, v in x["perRate"].items():
                    if not v or not v.get("folds"):
                        continue
                    es = sorted(v24.eps_of(R["results"][arm]["eps"], regime, float(rk)), key=v24.episode_order)
                    per = {}
                    for fo in v["folds"]:
                        t = es[fo["heldOut"]]["harness"]
                        w, n = per.get(t, (0, 0))
                        per[t] = (w + bool(fo["win"]), n + 1)
                    out["P4"]["%s %s %s r%s" % (arm, view, short(regime), rk)] = {t: list(x_) for t, x_ in per.items()}
    for rk, v in R["predictions"]["P2"].items():
        if not v:
            continue
        es = sorted(v24.eps_of(eps, v24.pause_regime(), float(rk)), key=v24.episode_order)
        per = {}
        for e, n in zip(es, v["perEpisode"]):
            k_, m = per.get(e["harness"], (0, 0))
            per[e["harness"]] = (k_ + (n <= v["threshold"]), m + 1)
        out["P2"]["r" + rk] = {t: list(x_) for t, x_ in per.items()}
    tag_of = {c.get("cellKey", c["cell"]): c.get("harness", "sweep") for c in R["cells"] if c["valid"]}
    per = {}
    for x in R["predictions"]["P1"]["perEpisode"]:
        t = tag_of.get(x["cell"], "sweep")
        k_, n = per.get(t, (0, 0))
        per[t] = (k_ + bool(x["ok"]), n + (x["ok"] is not None))
    out["P1"] = {t: list(x_) for t, x_ in per.items()}
    h4 = defaultdict(Counter)
    reasons = defaultdict(Counter)
    for c in R["cells"]:
        if c["valid"] and c["target"] is not None:
            st = (c.get("h4") or {}).get("status") or ("not recorded (sweep harness)" if v24.SYSTEM != "hotel" else
                                                       "Hotel: docker-events.jsonl (v2.4)")
            h4[c.get("harness", "sweep")][st] += 1
            for r in (c.get("h4") or {}).get("reasons") or []:
                reasons[c.get("harness", "sweep")][r] += 1
    out["H4"] = {t: dict(v) for t, v in h4.items()}
    out["H4reasons"] = {t: dict(v) for t, v in reasons.items()}
    return out


def clocks_report3(cells):
    """v24.clocks_report with its per-cell rows keyed by (campaign, run path) (CELL_KEY_POOL), so two campaigns whose
    cells share a name (quiet A and A2) cannot overwrite each other's clock row."""
    out = v24.clocks_report(cells)
    rows = {}
    for c in cells:
        if c["valid"]:
            one = v24.clocks_report([c])["perCell"]
            rows[c.get("cellKey", c["cell"]) if CELL_KEY_POOL else c["cell"]] = next(iter(one.values()))
    out["perCell"] = rows
    return out


def campaigns_read(R):
    """Decision 68: every campaign directory pooled, with its valid / found cells per regime (A and A2 together)."""
    out = []
    for i, name in enumerate(R["campaigns"]):
        cs = [c for c in R["cells"] if c.get("campaignIndex") == i]
        out.append({"campaign": name, "found": len(cs), "valid": sum(1 for c in cs if c["valid"]),
                    "byRegime": dict(Counter(c["regime"] for c in cs if c["valid"]))})
    return out


# =========================================================================== output

def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _rk(d):
    return {"%g" % r: x for r, x in d.items()}


def _row_json(row):
    out = {x: y for x, y in row.items() if x not in ("value", "lastValue", "values", "nested", "selectedValue")}
    out["value"] = value_text(row["value"])
    if row.get("lastValue"):
        out["lastValue"] = value_text(row["lastValue"])
    if row.get("nested") is not None:
        out["nestedValues"] = [value_text(row["values"][vi]) if vi is not None else None for vi in row["nested"]]
    if row.get("value") and row["value"][0] == "range":
        out["label"] = "range fallback (discrete in effect)" + (" under MAD = 0" if row.get("madZeroRange") else "")
    if row["status"] == "exempt":
        out["label"] = "exempt (decision 63): the client's definition of failure, never calibrated"
    return out


def cal_json(cal):
    out = {"share": cal["share"], "criterion": cal["criterion"], "hold": cal.get("hold"), "perRate": {}}
    for r, cr in cal["perRate"].items():
        out["perRate"]["%g" % r] = {
            "cells": cr["cells"], "hours": cr["hours"], "quietFailed": cr["quietFailed"],
            "appearVocabulary": cr["appearVocabulary"], "summary": cr.get("summary"),
            "optimisticAdded": cr.get("optimisticAdded"),
            "rules": {rid(k, rule): _row_json(row)
                      for (k, rule), row in sorted(cr["rules"].items(), key=lambda kv: rid(*kv[0]))},
            "sensors": {s["sensor"]: {x: y for x, y in s.items() if x != "sensor"}
                        for _, s in sorted(cr["sensors"].items(), key=lambda kv: sid_of(kv[0]))}}
    return out


def far_json(f):
    return {"sets": f["sets"], "allPlaceable": _rk(f["allPlaceable"]), "families": _rk(f["families"])}


def build_json(R):
    with v24.use_system(R.get("system", "hotel")):
        return _build_json(R)


def _build_json(R):
    res = R["results"]
    val = R.get("validation")
    out = {
        "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(), "label": LABEL, "version": VERSION,
        "binding": list(BINDING_V3) + list(v24.BINDING), "system": v24.SYSTEM, "campaigns": R.get("campaigns"),
        "campaignsRead": campaigns_read(R),
        "scope": "instance (one SUT, one host, %s)" % (
            "one campaign" if len(R.get("campaigns") or [None]) == 1 else "%d campaigns pooled" % len(R["campaigns"])),
        "script": "research/detection-time/sweep_analysis_v3.py", "scriptSha256": _sha(__file__),
        "v24Sha256": _sha(HERE / "sweep_analysis_v2.py"), "parametersSha256": _sha(v24.PARAMETERS),
        "parametersV3Sha256": _sha(PARAMETERS_V3), "v1Sha256": _sha(HERE / "sweep_analysis.py"),
        "detectionTimeSha256": _sha(HERE / "detection_time.py"), "frameworkCommit": v24._git_head(),
        "python": platform.python_version(), "dashOutputs": dash_outputs3(R),
        "parameters": {n: v24.REGISTRY[n]["value"] for n in sorted(v24.PARAMS_USED)},
        "parametersV3": {n: REGISTRY[n]["value"] for n in sorted(PARAMS_USED)},
        "knownLimitations": {"v24": v24.KNOWN_LIMITATIONS, "v3": KNOWN_LIMITATIONS_V3.get(v24.SYSTEM, [])},
        "cells": {"found": {v1.rr_key(*k): n for k, n in sorted(R["found"].items(), key=lambda kv: v1.rr_key(*kv[0]))},
                  "valid": {v1.rr_key(*k): n for k, n in sorted(R["valid"].items(), key=lambda kv: v1.rr_key(*kv[0]))},
                  "notScored": [{"cell": c["cell"], "regime": c["regime"], "rate": c["rate"], "reason": c["reason"]}
                                for c in R["cells"] if not c["valid"]]},
        "provenance": R["provenance"], "clocks": clocks_report3(R["cells"]),
        "freezeStamps": {c.get("cellKey", c["cell"]): {"onset": c.get("onset"), "freezeStamps": c.get("freezeStamps"),
                                     "h4": c.get("h4"), "harness": c.get("harness")}
                         for c in R["cells"] if c["valid"] and c.get("h4")},
        "harnessBreakdown": harness_breakdown(R),
        "calibration": {s: cal_json(R["cal"][s]) for s in R["cal"]},
        "placementFalseAlarms": {s: far_json(R["far"][s]) for s in R["far"]},
        "bFreshCheckLimit": {"hours": B_FRESH_HOURS, "boundZeroPerHour": bound(0, B_FRESH_HOURS)},
        "validation": (None if val is None else {"campaigns": val["campaigns"], "input": val["input"],
                                                 "notUsed": val["primary"]["notUsed"],
                                                 "perRate": _rk(val["primary"]["perRate"])}),
        "v24Reference": reference_table(R), "ledgerRuleMix": ledger_mix(res["primary"]["eps"]),
        "settings": {s: {"primary": res[s]["primary"], "P4": res[s]["P4"]} for s in res},
        "predictions": R["predictions"], "secondary": R["secondary"], "perSensor": R["perSensor"],
        "exposure": R["exposure"], "absentGap": absent_gap3(R), "episodes": v24.episode_detail(res["primary"]["eps"]),
        "decision57": R.get("decision57"), "readerStats": v24.reader_stats(R["cells"]),
    }
    return dt.strip(out)


def dash_outputs3(R):
    """v2.4's list, with the Docker-event line stated from the cells (campaign B may carry the events)."""
    out = [x for x in v24.dash_outputs(R) if not x["output"].startswith(("Docker pause event", "v1 / v2"))]
    pause = [c for c in R["cells"] if c["valid"] and c.get("faultKind") in dt.STOPPING]
    with_ev = [c for c in pause if (c.get("onset") or {}).get("hiKind") == "docker-event"]
    if v24.SYSTEM != "hotel" and pause and len(with_ev) < len(pause):
        out.append({"output": "Docker pause event as the onset interval's upper bound (H4) in %d of %d pause "
                              "episodes" % (len(pause) - len(with_ev), len(pause)),
                    "reason": "those cells carry no freeze-event source (V3_FREEZE_EVENTS_RULE): the interval is "
                              "[command issued, command returned], v2.4's"})
    if not R.get("validation"):
        out.append({"output": "out-of-sample check (decision 65)",
                    "reason": "no --validation cells given (campaign B's no-fault cells are the declared source)"})
    out.append({"output": "a false-alarm figure from the zero-alarm selection itself",
                "reason": "never printed (decision 67): the selected value has 0 held-out alarms on the cells it was "
                          "chosen on by construction; every false-alarm count below is the honest nested one"})
    return out


def f2(x):
    return v24.DASH if x is None else "%.2f" % x


def f3(x):
    return v24.DASH if x is None else "%.3f" % x


def f1(x):
    return v24.DASH if x is None else "%.1f" % x


def short(regime):
    return regime.replace("-effect", "")


def listing(items):
    items = list(items)
    if not items:
        return "none"
    s = ", ".join("`%s`" % x for x in items[:LIST_MAX])
    return s + (" (+%d more in the JSON)" % (len(items) - LIST_MAX) if len(items) > LIST_MAX else "")


def honest_text(x):
    """An honest count as `n (rate/h [bound], over the evaluated hours of T)`; — where no fold evaluated it."""
    if not x or x.get("alarms") is None:
        return v24.DASH + " (no fold evaluated it)"
    return "%d (%s/h [%s], %.2f of %.2f h)" % (x["alarms"], f1(x["perHour"]), f1(x["upperPerHour"]), x["hours"],
                                              x["totalHours"])


def fh(n):
    return v24.DASH if n is None else "%d" % n


def render(R, J):
    with v24.use_system(R.get("system", "hotel")):
        return _render(R, J)


def _render(R, J):
    L = []
    w = L.append
    pred = R["predictions"]
    camp = R["campaign"] if isinstance(R["campaign"], list) else [R["campaign"]]
    w("# Traffic sweep, %s: analysis v%s (v3.1), %s (%s)" % (v24.TITLE, VERSION, LABEL, " + ".join(
        Path(str(x)).name for x in camp)))
    w("")
    w("**Exploratory, not frozen.** Protocol rounds 15 and 17 (decisions 61-65 as amended by 67) on v2.4's readers and "
      "rules; every cell read here was read under v2.4 first. **Scope: instance** (one SUT, one host). `—` = absent or "
      "not evaluable, never 0. Each (sensor, rule) is calibrated per rate by the zero-held-out-alarm selection; **no "
      "false-alarm figure here is that selection's own zero**: every count of false alarms is the honest nested "
      "leave-one-cell-out count (V3_NESTED_RULE), with its exact 95 % bound.")
    w("")
    w("Binding documents and inputs: " + "; ".join(J["binding"]) + ".")
    w("")
    w("Analysis: `%s` v%s (sha256 `%s`) on v2.4 `sweep_analysis_v2.py` (sha256 `%s`), parameters.json `%s`, "
      "parameters_v3.json `%s`, HEAD `%s`, Python %s." % (J["script"], VERSION, J["scriptSha256"], J["v24Sha256"],
                                                          J["parametersSha256"], J["parametersV3Sha256"],
                                                          J["frameworkCommit"], J["python"]))
    w("")
    w("## Outputs that are — by construction")
    w("")
    for x in J["dashOutputs"]:
        w("- %s: %s." % (x["output"], x["reason"]))
    w("")
    w("## What was read")
    w("")
    w("Campaigns pooled (H1; decision 68: quiet runs A and A2 pool with the sweep):")
    w("")
    for x in J["campaignsRead"]:
        w("- `%s`: %d valid of %d (%s)" % (x["campaign"], x["valid"], x["found"], ", ".join(
            "%s %d" % (short(k), v) for k, v in sorted(x["byRegime"].items())) or "none"))
    w("")
    w("| class | " + " | ".join("r%g valid/found" % r for r in v24.RATES) + " |")
    w("|---|" + "---|" * len(v24.RATES))
    for regime in (v24.NOFAULT,) + v24.FAULT_REGIMES:
        w("| %s | %s |" % (short(regime), " | ".join(
            ("%d/%d" % (R["valid"][(regime, r)], R["found"][(regime, r)])) if R["found"][(regime, r)] else v24.DASH
            for r in v24.RATES)))
    inv = J["cells"]["notScored"]
    w("")
    w("Cells not scored: %s." % ("; ".join("`%s` (%s)" % (x["cell"], x["reason"]) for x in inv) if inv else "none"))
    pv = R["provenance"]
    w("")
    w("Provenance: harness commit %s; input digest `%s` over %d files (v2.4's file set plus docker-events.json[l])." % (
        "`%s`" % pv["harnessCommit"] if pv["harnessCommit"] else v24.DASH, pv["input"]["sha256"], pv["input"]["files"]))
    hb = J["harnessBreakdown"]
    w("")
    w("H4 freeze record per harness and status (V3_FREEZE_EVENTS_RULE; decision 69: a missing or contradictory record "
      "keeps the sweep's bound and is counted): %s; reasons: %s." % (
          "; ".join("%s: %s" % (t, ", ".join("%s %d" % kv for kv in sorted(v.items()))) for t, v in
                    sorted(hb["H4"].items())) or v24.DASH,
          "; ".join("%s: %s" % (t, ", ".join("%s (%d)" % kv for kv in sorted(v.items()))) for t, v in
                    sorted(hb["H4reasons"].items())) or "none"))
    v24.render_reader_stats(w, R)
    w("")
    _render_calibration(w, R, J)
    _render_far(w, R, J)
    _render_reference(w, J)
    _render_predictions(w, R, J, pred)
    _render_validation(w, J)
    _render_tables(w, R, J, pred)
    return "\n".join(L)


def _render_calibration(w, R, J):
    w("## Calibration per (sensor, rule) on the no-fault cells (decisions 61-63, 67)")
    w("")
    w("Each armed (sensor, rule) takes the smallest grid value with zero held-out alarms over the rate's no-fault "
      "cells, each scored leave-one-cell-out (v2.4's fit, H1; class-independent). Level rules: K_GRID (<= 100; K = 100 "
      "flagged at grid edge), then the range fallback (discrete in effect; up-only for spans and the ledger; may apply "
      "where MAD = 0, decision 52 kept for K); `absent`: m x G on m in {%s}, G including the censored silences of cells "
      "with records; an `absent` whose gap exceeds the shortest hold (%s s) is **inert**; `appear` per stream; the "
      "ledger's `failed` exempt. **honest** = the nested count (each held-out cell at the value re-selected without "
      "it), the false-alarm figure; its rate per hour of no-fault time T." % (
          ", ".join("%g" % m for m in M_GRID), f3(R["cal"]["primary"].get("hold"))))
    w("")
    w("| rate | no-fault cells | T (h) | rules calibrated / dropped / inert / unarmed | at grid edge | range (of them MAD "
      "= 0) | sensors placeable / appear-only / not (L, M, S, T) | dof | E `failed` in no-fault (exempt) | calibrated "
      "rules: median folds armed of the rate's cells · out of the detector in every nested fold · honest — (no nested evidence) | "
      "placeable sensors with CELF cost — |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for rk, cr in J["calibration"]["primary"]["perRate"].items():
        sm = cr["summary"]
        tot = Counter()
        for c in sm["rules"].values():
            tot.update(c)
        sens = Counter()
        for f, c in sm["sensors"].items():
            if f != "E":
                sens.update(c)
        w("| r%s | %d | %.3f | %d / %d / %d / %d | %d | %d (%d) | %d / %d / %d | %d | %s | %s of %d · %d · %d | %d |" % (
            rk, cr["cells"], cr["hours"], tot["calibrated"], tot["dropped"], tot["inert"], tot["unarmed"],
            tot["gridEdge"], tot["kind:range"], tot["rangeMadZero"], sens["placeable"], sens["appearOnly"],
            sens["notPlaceable"], sm["degreesOfFreedom"],
            ", ".join("%s %d" % kv for kv in sorted(cr["quietFailed"].items())) or v24.DASH,
            v24.DASH if sm["foldsArmedMedian"] is None else "%g" % sm["foldsArmedMedian"], cr["cells"],
            tot["outOfDetectorEveryFold"], tot["noNestedEvidence"], len(sm["placeableWithoutCost"])))
    w("")
    w("Per family and rule (primary): calibrated / dropped / inert / unarmed.")
    w("")
    w("| rate | family | " + " | ".join(("appear", "absent") + LEVEL) + " |")
    w("|---|---|" + "---|" * (len(LEVEL) + 2))
    for rk, cr in J["calibration"]["primary"]["perRate"].items():
        by = defaultdict(Counter)
        for name, row in cr["rules"].items():
            by[(row["family"], row["rule"])][row["status"]] += 1
        for f in v24.FAMILIES:
            if not any(k[0] == f for k in by):
                continue
            w("| r%s | %s | %s |" % (rk, f, " | ".join(
                ("%d / %d / %d / %d" % (by[(f, r)]["calibrated"], by[(f, r)]["dropped"], by[(f, r)]["inert"],
                                        by[(f, r)]["unarmed"])) if by.get((f, r)) else v24.DASH
                for r in ("appear", "absent") + LEVEL)))
    w("")
    w("**The ledger E** per rate (route; `failed` **exempt**, decision 63: never calibrated, always compared; its "
      "no-fault count is reported):")
    w("")
    for rk, cr in J["calibration"]["primary"]["perRate"].items():
        parts = []
        for name, row in cr["rules"].items():
            if row["family"] != "E":
                continue
            r = name.split("/")[-1]
            if row["status"] == "calibrated":
                parts.append("`%s` calibrated (%s, honest %s)" % (r, row["value"], fh(row["honest"])))
            elif row["status"] == "dropped":
                parts.append("`%s` dropped (held-out %s at %s; honest %s)" % (r, row["heldOut"], row.get("lastValue"),
                                                                            fh(row["honest"])))
            elif row["status"] == "exempt":
                parts.append("`%s` exempt (no-fault count %d)" % (r, row["heldOut"]))
            else:
                parts.append("`%s` %s (%s)" % (r, row["status"], row.get("reason")))
        w("- r%s: %s." % (rk, "; ".join(parts)))
    mix = J.get("ledgerRuleMix") or {}
    w("- E's catching rule in the episodes (primary): %s." % ("; ".join(
        "%s: %s" % (k, ", ".join("`%s` %d" % kv for kv in sorted(v.items()))) for k, v in mix.items()) or v24.DASH))
    w("")
    w("**Dropped (sensor, rule) pairs** (held-out alarms at the last grid value; honest count beside), primary:")
    w("")
    for rk, cr in J["calibration"]["primary"]["perRate"].items():
        drops = sorted(((name, row) for name, row in cr["rules"].items() if row["status"] == "dropped"),
                       key=lambda kv: (-(kv[1]["heldOut"] or 0), kv[0]))
        w("- r%s (%d): %s" % (rk, len(drops), "none" if not drops else ", ".join(
            "`%s` %s (honest %s)" % (name, row["heldOut"], fh(row["honest"])) for name, row in drops[:LIST_MAX])
            + (" (+%d more in the JSON)" % (len(drops) - LIST_MAX) if len(drops) > LIST_MAX else "")))
    w("")
    w("**Inert** (calibrated by the selection, but the gap exceeds the hold; not placeable), **at grid edge** (K = 100) "
      "and **appear-only** sensors (placeable through `appear` alone, listed apart), primary:")
    w("")
    for rk, cr in J["calibration"]["primary"]["perRate"].items():
        sm = cr["summary"]
        w("- r%s: inert %d: %s; at grid edge %d: %s; appear-only %d: %s." % (
            rk, len(sm["inert"]), listing(sm["inert"]), len(sm["gridEdge"]), listing(sm["gridEdge"]),
            len(sm["appearOnly"]), listing(sm["appearOnly"])))
    w("")
    w("**Not placeable at this quiet time** (L, M, S, T sensors with no calibrated rule), by family (with a dropped "
      "rule / inert / unarmed only), then those with a dropped rule:")
    w("")
    for rk, cr in J["calibration"]["primary"]["perRate"].items():
        notp = [(s, x) for s, x in cr["sensors"].items() if x["family"] != "E" and not x["placeable"]]
        by = defaultdict(Counter)
        for s, x in notp:
            by[x["family"]]["dropped" if x["dropped"] else "inert" if x["inert"] else "unarmed"] += 1
        w("- r%s: %d sensors (%s); with a dropped rule: %s" % (
            rk, len(notp), ", ".join("%s %d/%d/%d" % (f, c["dropped"], c["inert"], c["unarmed"])
                                     for f, c in sorted(by.items())) or "none",
            listing(sorted(s for s, x in notp if x["dropped"]))))
    w("")
    w("- `appear` (V3_APPEAR_RULE): new streams in no-fault cells per service, summed over the held-out cells (they "
      "enter the honest counts): %s." % ("; ".join(
          "r%s %s" % (rk, ", ".join("%s %d" % kv for kv in sorted(cr["appearVocabulary"].items())) or "none")
          for rk, cr in J["calibration"]["primary"]["perRate"].items())))
    for s, label in (("arm", "floor arm (share %g)" % v24.ARMS["arm"]),
                     ("atMostOne", "sensitivity, <= %d held-out alarm (K_GRID only, no range fallback)" % SENS_ALARMS)):
        parts = []
        for rk, cr in J["calibration"][s]["perRate"].items():
            tot, sens = Counter(), Counter()
            for c in cr["summary"]["rules"].values():
                tot.update(c)
            for f, c in cr["summary"]["sensors"].items():
                if f != "E":
                    sens.update(c)
            parts.append("r%s %d/%d/%d/%d rules, %d placeable + %d appear-only sensors" % (
                rk, tot["calibrated"], tot["dropped"], tot["inert"], tot["unarmed"], sens["placeable"],
                sens["appearOnly"]))
        w("- **%s**: %s." % (label, "; ".join(parts)))
    w("")


def _render_far(w, R, J):
    w("## Honest false alarms (decisions 64, 67): nested leave-one-cell-out unions on the no-fault cells")
    w("")
    w("Union of the sensors' rules, each held-out no-fault cell scored at the values re-selected without it (its "
      "leave-one-cell-out fit), restarted after each alarm: count (/h [exact 95 %% bound]); per family also the sum "
      "of its calibrated rules' honest counts (the reviewer's tally). The honest per-sensor rate is the sensor's "
      "false-alarm cost for CELF (JSON calibration.*.sensors.*.honestPerHour). Campaign B's fresh check can certify at "
      "best %s/h (0 alarms in %g h per rate)." % (f1(J["bFreshCheckLimit"]["boundZeroPerHour"]), B_FRESH_HOURS))
    w("")
    w("| setting | rate | T (h) | " + " | ".join(v24.FAMILIES) + " | all placeable L, M, S, T |")
    w("|---|---|---|" + "---|" * len(v24.FAMILIES) + "---|")
    for s in ("primary", "atMostOne"):
        f = J["placementFalseAlarms"].get(s) or {}
        for rk, fam in (f.get("families") or {}).items():
            a = f["allPlaceable"][rk]
            w("| %s | r%s | %.3f | %s | %s |" % (s, rk, a["totalHours"], " | ".join(
                ("%s (%s/h [%s], %s of %.2f h) · sum %d · no evidence: %d rules, %d sensors" % (
                    fh(fam[x]["union"]), f1(fam[x]["perHour"]), f1(fam[x]["upperPerHour"]), f3(fam[x]["hours"]),
                    fam[x]["totalHours"], fam[x]["sumCalibratedRuleHonest"], fam[x]["calibratedWithoutEvidence"],
                    fam[x]["placeableWithoutCost"])) if x in fam else v24.DASH
                for x in v24.FAMILIES), honest_text(a)))
    w("")
    w("P4-selected sets (the sensors P4 selected over its folds, or with one episode the candidates judged a win), "
      "honest nested union, primary:")
    w("")
    for name, x in sorted(((J["placementFalseAlarms"].get("primary") or {}).get("sets") or {}).items()):
        w("- %s: %s -> %s · sum over the sensors %s" % (name, listing(x["sensors"]), honest_text(x),
                                                         fh(x["sumOverSensors"])))
    if not ((J["placementFalseAlarms"].get("primary") or {}).get("sets")):
        w("- none")
    w("")


def _render_reference(w, J):
    ref = J.get("v24Reference")
    w("## v2.4 reference row: family operating point (decision 53, 15/h, from v2.4's own code)")
    w("")
    if not ref:
        w("Not computed.")
        w("")
        return
    w("K per family: %s." % ", ".join("%s %s" % (g, v24.DASH if k is None else "%g" % k) for g, k in ref["K"].items()))
    w("")
    w("| class | family | " + " | ".join("r%g" % r for r in v24.RATES) + " |")
    w("|---|---|" + "---|" * len(v24.RATES))
    for k, row in ref["table"].items():
        regime, fam = k.rsplit(" ", 1)
        w("| %s | %s | %s |" % (short(regime), fam, " | ".join(row.get("%g" % r, v24.DASH) for r in v24.RATES)))
    w("")


def _p4_parts(x):
    parts = []
    for r in v24.RATES:
        v = x["perRate"]["%g" % r]
        if v is None:
            parts.append("r%g %s" % (r, v24.DASH))
        elif v.get("note"):
            parts.append("r%g %s (%s)" % (r, v24.DASH, v["note"].replace("— (not evaluable): ", "")))
        else:
            parts.append("r%g %d/%d (ledger missed, sensor caught: %d)" % (
                r, v["wins"], v["n"], v["ledgerMissedSensorCaught"]))
    return parts


def _render_predictions(w, R, J, pred):
    w("## Predictions (primary: calibrated arm, floor primary)")
    w("")
    p1 = pred["P1"]
    w("- **P1** (%s; decision 54's interval, observed = first `failed` catch): %d/%d; per rate %s; not evaluable %d; "
      "holds by branch: %s; verdict **%s**." % (
          short(v24.pause_regime()), p1["k"], p1["n"], ", ".join(
              "r%s %d/%d" % (r, a, b) if b else "r%s %s" % (r, v24.DASH) for r, (a, b) in p1["perRate"].items()),
          p1["notEvaluable"], ", ".join("%s %d" % kv for kv in sorted(p1.get("holdsByBranch", {}).items())) or v24.DASH,
          {True: "holds", False: "fails", None: v24.DASH}[p1["holds"]]))
    for r, v in pred["P2"].items():
        w("- **P2** r%s (failed before the first `failed` catch <= %.2f): %s." % (
            r, v24.p2_threshold(float(r)), v24.DASH if v is None else "%d/%d, counts %s, verdict %s" % (
                v["k"], v["n"], v["perEpisode"], {True: "holds", False: "fails", None: v24.DASH + " (n < %d)" %
                                                  v24.EPISODES}[v["holds"]])))
    for x in pred["P3"]:
        w("- **P3** %s: **%s**%s." % (short(x["regime"]), x["state"], (" (%s)" % x["reason"]) if x.get("reason") else ""))
    w("- **P4** compares against the ledger E as the OR of its calibrated rules, its `failed` rule exempt from "
      "calibration (decisions 63, 70; V3_P4_LEDGER_READING = `%s`): a dropped ledger rule is listed below, not a reason "
      "for `—`. Two arms (decision 67): calibrated (primary) and optimistic bound (dropped rules armed at K = %g / m = "
      "%g, beside, not evidence)." % (P4_LEDGER_READING, v24.K_GRID[-1], M_GRID[-1]))
    w("- Dropped ledger rules per rate (decision 70: listed; the ledger compares by its calibrated rules): %s." % (
        "; ".join("r%g %s" % (r, ", ".join("`%s`" % x for x in ledger_dropped(cr)) or "none")
                  for r, cr in sorted(R["cal"]["primary"]["perRate"].items(), reverse=True)) or v24.DASH))
    for scope in ("P4a", "P4b"):
        label = "outside the target, without BC" if scope == "P4a" else "the target's own sensors, without BC"
        for regime, x in pred["P4"][scope].items():
            w("- **%s** %s (%s; wins under H3 a-c, >= %d of %d): %s; highest rate **%s**." % (
                scope, short(regime), label, v24.P4_MIN, v24.EPISODES, "; ".join(_p4_parts(x)), x["highestRate"]))
            if "optimistic" in R["results"]:
                y = R["results"]["optimistic"]["P4"][scope][regime]
                w("  - optimistic bound (not evidence): %s; highest rate %s." % ("; ".join(_p4_parts(y)),
                                                                                  y["highestRate"]))
    w("")
    w("### P4 per class and rate: placeable sensors, dropped rules and non-placeable sensors on the affected path")
    w("")
    for regime, x in pred["P4"]["P4a"].items():
        for r in v24.RATES:
            v = x["perRate"]["%g" % r]
            if not v:
                continue
            w("- %s r%g: placeable sensors %d (candidates with a catch: %s); dropped on the path: %s; not placeable on "
              "the path: %s; dropped ledger rules (listed, decision 70): %s" % (
                  short(regime), r, v.get("placeable", 0), v.get("candidates", v24.DASH),
                  listing(v.get("droppedOnPath") or []), listing(v.get("notPlaceableOnPath") or []),
                  listing(v.get("ledgerDropped") or [])))
    w("")
    w("### P4 folds (sensor rule vs ledger rule; lead, margin; category)")
    w("")
    for arm in ("primary", "optimistic"):
        if arm not in R["results"]:
            continue
        w("**%s**" % ("Calibrated arm" if arm == "primary" else "Optimistic bound (not evidence)"))
        w("")
        for scope in ("P4a", "P4b"):
            for regime, x in R["results"][arm]["P4"][scope].items():
                for r in v24.RATES:
                    v = x["perRate"]["%g" % r]
                    if not v:
                        continue
                    if v.get("note"):
                        w("- %s %s r%g: %s" % (scope, short(regime), r, v["note"]))
                        v24.render_single(w, v.get("singleEpisode"))
                        continue
                    _render_folds(w, scope, regime, r, v)
        w("")
    hb = J["harnessBreakdown"]
    w("**Per harness** (decision 49 pools the sweep's episode with campaign B's three; V3_HARNESS_TAG_RULE; tags %s). "
      "Episodes per class and rate: %s." % (", ".join(hb["tags"]), "; ".join(
          "%s %s" % (k, ", ".join("%s %d" % kv for kv in sorted(v.items()))) for k, v in sorted(hb["episodes"].items()))))
    w("")
    w("- P1 holds per harness: %s; P2 within the bound per harness: %s." % (
        ", ".join("%s %d/%d" % (t, *x) for t, x in sorted(hb["P1"].items())) or v24.DASH,
        "; ".join("%s %s" % (r, ", ".join("%s %d/%d" % (t, *x) for t, x in sorted(v.items())))
                  for r, v in hb["P2"].items()) or v24.DASH))
    for k, v in sorted(hb["P4"].items()):
        w("- P4 %s: wins / folds by the held-out episode's harness: %s" % (k, ", ".join(
            "%s %d/%d" % (t, *x) for t, x in sorted(v.items()))))
    w("")
    w("**Beside the primary** (highest rate where P4 holds):")
    w("")
    arms = [s for s in SETTINGS if s in R["results"]]
    w("| verdict | " + " | ".join({"primary": "calibrated (primary)", "arm": "floor arm", "atMostOne": "<= %d held-out "
                                   "alarm" % SENS_ALARMS, "optimistic": "optimistic bound (not evidence)"}[s] for s in arms) + " |")
    w("|---|" + "---|" * len(arms))
    for scope in ("P4a", "P4b", "P4a withBC", "P4b withBC"):
        for regime in v24.FAULT_REGIMES:
            w("| %s %s | %s |" % (scope, short(regime), " | ".join(
                R["results"][s]["P4"][scope][regime]["highestRate"] for s in arms)))
    w("")


def _render_folds(w, scope, regime, r, v):
    pdiff = v["pairedDifferences"]
    w("- %s %s r%g (candidates %d; paired differences ledger - sensor: mean %s [%s, %s] s; availability-clock wins %d "
      "of %d evaluable):" % (scope, short(regime), r, v["candidates"], f3(pdiff["mean"]), f3(pdiff["min"]),
                             f3(pdiff["max"]), v["winsAvailability"], v["availabilityEvaluable"]))
    for fo in v["folds"]:
        w("  - ep%d b%s: %s `%s` %s vs E `%s` %s; lead %s, margin %s; tied %d (win share %s); **%s**%s" % (
            fo["heldOut"] + 1, fo["block"], fo["sensor"] or v24.DASH, fo["sensorRule"] or v24.DASH,
            f3(fo["sensorTtd"]), fo["ledgerRule"] or v24.DASH, f3(fo["ledgerTtd"]), f3(fo["lead"]),
            v24.fsmall(fo["margin"]), len(fo.get("tied") or []),
            "%d/%d" % tuple(fo["tiedWinShare"]) if fo.get("tiedWinShare") else v24.DASH, fo["category"],
            (" (%s)" % "; ".join(fo["unclassifiableBy"]) if fo.get("unclassifiableBy") else "")
            + (" [lead = %s start + %s gap + %s]" % (v24.fsmall(fo["decomposition"]["startDifference"]),
                                                    v24.fsmall(fo["decomposition"]["gapDifference"]),
                                                    v24.fsmall(fo["decomposition"]["residual"]))
               if fo.get("decomposition") else "")))


def _render_validation(w, J):
    w("## Out-of-sample check (decision 65, 67): calibrated detectors on --validation no-fault cells, no refit")
    w("")
    v = J.get("validation")
    if not v:
        w("Not computed (no --validation cells given; campaign B's no-fault cells are the declared source; at %g h per "
          "rate they can certify at best %s/h)." % (B_FRESH_HOURS, f1(J["bFreshCheckLimit"]["boundZeroPerHour"])))
        w("")
        return
    w("Validation campaigns: %s (input digest `%s`). Not used: %s." % (
        ", ".join("`%s`" % x for x in v["campaigns"]), v["input"]["sha256"],
        "; ".join("`%s` (%s)" % (x["cell"], x["reason"]) for x in v["notUsed"]) or "none"))
    w("")
    for rk, x in v["perRate"].items():
        if x.get("note"):
            w("- r%s: %d cells, %s" % (rk, x["cells"], x["note"]))
            continue
        a = x["allPlaceable"]
        w("- r%s: %d cells, %.3f h (limit of this check: %s/h for 0 alarms); rules alarming %d of %d calibrated: %s; "
          "sensors alarming %d of %d placeable; all placeable sensors' union %s" % (
              rk, x["cells"], x["hours"], f1(x["freshLimitZeroPerHour"]), len(x["rulesAlarming"]),
              x["rulesCalibrated"], listing("%s %d" % kv for kv in sorted(x["rulesAlarming"].items(),
                                                                          key=lambda kv: -kv[1])),
              len(x["sensorsAlarming"]), x["sensorsPlaceable"], honest_text(a)))
        for name, y in sorted(x["sets"].items()):
            w("  - %s: %s" % (name, honest_text(y)))
    w("")


def _render_tables(w, R, J, pred):
    w("## Primary outcome: time to detection at the calibrated values, misses charged at the hold end")
    w("")
    w("Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC. `—` = channel "
      "missing.")
    w("")
    cols = [c for c in v24.COLUMNS if c != "E:own"]
    w("| class | rate | n | " + " | ".join("%s | %s no BC" % (c, c) for c in cols) + " |")
    w("|---|---|---|" + "---|---|" * len(cols))
    for row in R["results"]["primary"]["primary"]:
        cells_ = []
        for c in cols:
            v = row["columns"].get(c)
            cells_ += [v1.fcol(v, "bc"), v1.fcol(v, "noBC") if c != "E" else "(= E)"]
        w("| %s | %g | %d | %s |" % (short(row["regime"]), row["rate"], row["n"], " | ".join(cells_)))
    w("")
    w("## P1 detail (H4, decision 54)")
    w("")
    for x in pred["P1"]["perEpisode"]:
        w("- r%g b%s: interval %s s (%s); expected [%s, %s] +- %s s; observed %s; %s" % (
            x["rate"], x["block"], f3(x["intervalSeconds"]), x["hiSource"], f3((x["expected"] or [None, None])[0]),
            f3((x["expected"] or [None, None])[1]), f3(x["tolerance"]), f3(x["observed"]),
            ("holds via **%s**" % x.get("branch")) if x["ok"] else ("✗" if x["ok"] is False else v24.DASH)))
    w("")
    ag = J["absentGap"]
    w("- The ledger's calibrated `absent` against the client timeout: %s." % ("; ".join(
        "r%s %s: %s g %s s vs timeout %s s; `absent` before the first `failed` in %d/%d pause episodes" % (
            r, rt, g["status"] + (" " + g["value"] if g["status"] == "calibrated" else ""), f3(g.get("g")),
            "/".join("%g" % t for t in x["timeoutSeconds"]) or v24.DASH, *x["stoppingEpisodesAbsentBeforeFirstFailed"])
        for r, x in ag.items() for rt, g in x["routes"].items()) or v24.DASH))
    w("")
    w("## Exposure (H5): recorded, the objective unchanged")
    w("")
    ex = R["exposure"]
    w("Route call path: %s. Episodes with no request started in the fault window: %d of %d. Never-exposed sensors: %d." % (
        ", ".join(ex["routePath"]), sum(1 for v in ex["episodes"].values() if v["requestsStartedInWindow"] == 0),
        len(ex["episodes"]), len(ex["neverExposedSensors"])))
    w("")
    w("## Defaults and declared limits (v3)")
    w("")
    for n, text in RULES_TEXT.items():
        w("- %s (parameters_v3.json): %s" % (n, text))
    for text in J["knownLimitations"]["v3"]:
        w("- Known limitation (parameters_v3.json V3_KNOWN_LIMITATIONS): %s" % text)
    for k, text in sorted(J["knownLimitations"]["v24"].items(), key=lambda kv: (kv[0][0], int(kv[0][1:]))):
        w("- Known limitation %s (v2.4, registry KNOWN_LIMITATIONS): %s" % (k, text))
    w("- Not frozen: v3.1 (decision 67) is built; its freeze and review come before campaign B is read.")
    w("")


def write_new(path, text):
    with open(path, "x", encoding="utf-8") as fh:           # exclusive create: never overwrites
        fh.write(text)


def finish(R):
    """Attach the per-rate summaries the JSON and the readout carry."""
    with v24.use_system(R.get("system", "hotel")):
        for s in R["cal"]:
            for cr in R["cal"][s]["perRate"].values():
                cr["summary"] = cal_summary(cr)
    return R


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory/ies of one system (pooled, H1)")
    ap.add_argument("--system", default="hotel", choices=v24.SYSTEMS)
    ap.add_argument("--out", required=True, help="NEW output directory; refused if it exists")
    ap.add_argument("--validation", nargs="+", default=[], help="no-fault campaign directory/ies for the "
                    "out-of-sample check (decision 65), never pooled")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    camp = [Path(x) for x in a.campaign]
    R = finish(run(camp[0] if len(camp) == 1 else camp, system=a.system, validation_dirs=[Path(x) for x in a.validation]))
    J = build_json(R)
    out.mkdir(parents=True)
    write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    write_new(out / OUT_MD, render(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
