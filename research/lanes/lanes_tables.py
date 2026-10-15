#!/usr/bin/env python3
"""POST HOC, EXPLORATORY lane tables (plan: research/PLAN_LANES_20261014.md, section "Directions", offline O1-O5).

    uv run python research/lanes/lanes_tables.py --out research/lanes/out-20261013

NOTHING HERE IS PREREGISTERED. Every number is scope **instance** (one SUT, one host, one campaign per row), computed after the
readouts were seen, from the frozen readouts (read-only) and the retained raw cells (read-only). No frozen file is edited; the
readers are imported and called, never changed. The output directory must not exist (new evidence never overwrites old).

O1  lane 1, own silence: episodes detected / episodes, min/median/max time, cheapest own sensor and its price.
O2  lane 2, coordinator side: OTel Kafka group-coordinator log ids, TeaStore registry heartbeat-removal ids (found by service and
    by template text in the raw logs), detection counts/times, price as charged (decision 73) and price if evaluated at zero alarms.
O3  lane 3, lag/backlog metrics of E: arming status and pooled n (descriptive; the frozen reader is NOT re-run).
O4  shared-fate silence sensor per container: "no record of any kind from this service for longer than w seconds".
O5  price-vs-detection table per system and lane.

Counting rules (the point of the carefulness): a fire is a list [family, sensor, rule, ttd, dir, own, onPath, counts, bc, movedBy]
(research/detection-time/sweep_analysis_v2.py:3611-3613, celf_v3.FIRE). A fire counts only through celf_v3.counted(), the function
the placement and the scorer (score_test_v3_2.py -> celf_v3.build_table) use:
  * placement-style rows (ledger alone, frozen, inf, out of the box, full): bc `e-only`, own `exclude`, the scorer's reading;
  * lane 1 (own silence): own `only`, bc `count-all`: an own `absent` fire is by construction (BC-downstream-absent) and the
    scorer would read it as a miss (decision 72) and exclude it as own (decisions 79/84/111); the lane is exactly that signal;
  * lane 2 (coordinator): bc `count-all` (the TeaStore registry fire carries BC-caller-log; the scorer reads it as a miss).
`counts` False is never counted in any reading (switch COUNTED_ONLY; a planted defect in tests/test_lanes_tables.py).

Prices: `honestUpperPerHour` of the readout's calibration; a sensor evaluated in 0 folds has none and is charged decision 73's fill
(the rate's largest evidenced bound over V_r, celf_v3.costs_of). "Evaluated at zero alarms" = -ln(0.05)/T_r = 2.9957/T_r.
Absence is `—`, never 0.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO / "research" / "placement", REPO / "research" / "detection-time", REPO / "research"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import celf_v3 as cv  # noqa: E402  frozen; imported, never edited

O3_READER_TEXT = ("Not re-run: MIN_BASELINE_POOLED is read from research/protocol/parameters.json by the frozen v2.4 reader at import "
                  "(sweep_analysis_v2.py:216; the registry digest is recorded in every readout) and the reader offers no override, so a lowered value needs "
                  "an edit to that registry or an in-process monkeypatch of a frozen module, and it would change the arming of every level rule, not only the "
                  "lag metrics. Reported instead: arming status, pooled n from the cells' own segLevel (the Fit's input), and a descriptive look at the pause window.")
POST_HOC = "POST HOC, EXPLORATORY (not preregistered; computed after the readouts were seen)"
SCOPE = "instance"
DASH = "—"
INF = math.inf
ZERO_ALARM_FACTOR = -math.log(0.05)            # 2.9957: exact Poisson 95 % upper bound after 0 events

# ---------------------------------------------------------------------------- switches (tests/test_lanes_tables.py flips them)
COUNTED_ONLY = True          # a fire with counts False is never counted (False: planted defect)
STRICT_GAP = True            # a silence alarm needs a gap strictly longer than w (False: >=, planted defect)
VIRTUAL_EDGES = True         # the window start and end are virtual records for gap measurement (False: first/last record only)

FIRE = cv.FIRE
READOUTS = {
    "otel": REPO / "research/traffic-sweep/readout-otel-e-score-v3.2/sweep_analysis_v3_2.json",
    "otel-train": REPO / "research/traffic-sweep/readout-otel-e-train-v3.2/sweep_analysis_v3_2.json",
    "teastore": REPO / "research/traffic-sweep/readout-teastore-c-v3.1/sweep_analysis_v3.json",
    "hotel": REPO / "research/traffic-sweep/readout-hotel-primary-v3.1/sweep_analysis_v3.json",
    "hotel-v24": REPO / "research/traffic-sweep/readout-hotel-r3-v2.4/sweep_analysis_v2_4.json",
}
OTEL_E_JSON = REPO / "research/placement/test-e/otel-e.json"
OTEL_E_PLACEMENT = REPO / "research/placement/test-e/placement-e.json"
TEASTORE_C_JSON = REPO / "research/placement/test-c/teastore-c.json"
PAUSE_REGIMES = {"otel": ("accounting-pause-effect", "fraud-pause-effect"),
                 "teastore": ("auth-freeze-effect",), "hotel": ("search-pause-effect",)}
CONTROL_REGIMES = {"otel": ("frontend-pause-effect",)}
E_TRAIN_BLOCKS, E_TEST_BLOCKS = (1, 2, 3), (4, 5)


# ============================================================================ small pure helpers

def norm(name):
    """Service-name normal form shared by compose container names and the readers' service names."""
    return re.sub(r"[-_]", "", str(name).lower())


def fmt(x, nd=2):
    if x is None:
        return DASH
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        if math.isinf(x):
            return "inf"
        return ("%." + str(nd) + "f") % x
    return str(x)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(fmt(c) for c in r) + " |")
    return "\n".join(out)


def tstats(ts):
    ts = [t for t in ts if t is not None and not math.isinf(t)]
    if not ts:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {"n": len(ts), "min": min(ts), "median": statistics.median(ts), "max": max(ts)}


def fire_counts(f, bc, own):
    """Does fire `f` count under the reading (bc, own)? The scorer's celf_v3.counted, plus the `counts` guard."""
    if COUNTED_ONLY:
        return cv.counted(f, bc, own)
    if own == "only":                                  # planted defect: the `counts` flag is not consulted
        return bool(f[FIRE["own"]]) and f[FIRE["family"]] != cv.LEDGER_FAMILY
    return True


def poisson_cdf(k, lam):
    term = math.exp(-lam)
    s = term
    for i in range(1, k + 1):
        term *= lam / i
        s += term
    return s


def poisson_upper(k, conf=0.95):
    """Exact one-sided upper limit of a Poisson mean after k events (bisection), as the frozen reader's poisson_upper."""
    alpha = 1.0 - conf
    lo, hi = 0.0, 1.0
    while poisson_cdf(k, hi) > alpha:
        lo, hi = hi, hi + hi
    for _ in range(200):
        mid = (lo + hi) / 2
        if poisson_cdf(k, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def rkey(rate):
    return cv.rate_key(rate)


def episodes_at(J, rate):
    return cv.rate_episodes(J, rate)


def sensors_of(J, rate):
    return J["calibration"]["primary"]["perRate"][rkey(rate)]["sensors"]


def hours_of(J, rate):
    return J["calibration"]["primary"]["perRate"][rkey(rate)]["hours"]


class Prices:
    """Prices of one (readout, rate): honest bound, decision-73 charge, zero-alarm price."""

    def __init__(self, J, rate):
        self.rate = rate
        self.sensors = sensors_of(J, rate)
        self.hours = hours_of(J, rate)
        self.costs, _ = cv.costs_of(J, rate, "upper")           # V_r only: honest bound or the fill
        ev = [self.sensors[s]["honestUpperPerHour"] for s in self.costs
              if self.sensors[s]["honestUpperPerHour"] is not None]
        self.fill = max(ev) if ev else None
        self.V = set(self.costs)

    def info(self, sid):
        s = self.sensors.get(sid)
        if s is None:
            return {"id": sid, "inCalibration": False, "honest": None, "charged": None, "zeroAlarm": None,
                    "foldsEvaluated": None, "placeable": None, "family": sid.split(":")[0]}
        honest = s["honestUpperPerHour"]
        if sid in self.costs:
            charged = self.costs[sid]
        else:                                                   # not in V_r: decision 73's convention, flagged
            charged = honest if honest is not None else self.fill
        zero = honest if honest is not None else ZERO_ALARM_FACTOR / self.hours
        return {"id": sid, "inCalibration": True, "honest": honest, "charged": charged, "zeroAlarm": zero,
                "foldsEvaluated": s.get("foldsEvaluated"), "placeable": s.get("placeable"),
                "inV": sid in self.costs, "family": s.get("family")}

    def total(self, sids):
        rows = [self.info(s) for s in sids]
        ch = [r["charged"] for r in rows]
        zr = [r["zeroAlarm"] for r in rows]
        return {"charged": math.fsum(ch) if all(c is not None for c in ch) else None,
                "zeroAlarm": math.fsum(zr) if all(c is not None for c in zr) else None,
                "members": len(rows), "unevaluated": sum(1 for r in rows if r["honest"] is None)}


# ============================================================================ O1 / O2 / O5 from the readouts

def own_fires(e, rules=("absent",), bc="count-all"):
    """An episode's own-sensor fires the lane counts (own only, `counts` true, rule in `rules`; None = any rule)."""
    out = []
    for f in e["fires"]:
        if f[FIRE["family"]] == cv.LEDGER_FAMILY:
            continue
        if not fire_counts(f, bc, "only"):
            continue
        if rules is not None and f[FIRE["rule"]] not in rules:
            continue
        out.append(f)
    return out


def lane1_rows(J, system, subset=None):
    """O1 rows per (regime, rate): detected / episodes, min/median/max time, cheapest own sensor."""
    rows = []
    prices = {}
    by = defaultdict(list)
    for e in J["episodes"]:
        if subset is not None and not subset(e):
            continue
        by[(e["regime"], rkey(e["rate"]))].append(e)
    for (regime, rk), eps in sorted(by.items(), key=lambda kv: (kv[0][0], float(kv[0][1]))):
        rate = eps[0]["rate"]
        if rk not in prices:
            try:
                prices[rk] = Prices(J, rate)
            except KeyError:                              # a v2.4 readout carries no calibration: no prices
                prices[rk] = None
        pr = prices[rk]
        per_sensor = defaultdict(list)                  # sid -> [(episode index, ttd)]
        ttds, any_ttds = [], []
        for i, e in enumerate(eps):
            fs = own_fires(e, ("absent",))
            ttds.append(min((f[FIRE["ttd"]] for f in fs), default=None))
            fa = own_fires(e, None)
            any_ttds.append(min((f[FIRE["ttd"]] for f in fa), default=None))
            seen = {}
            for f in fs:
                seen[f[FIRE["sensorId"]]] = min(seen.get(f[FIRE["sensorId"]], INF), f[FIRE["ttd"]])
            for sid, t in seen.items():
                per_sensor[sid].append((i, t))
        st, sa = tstats(ttds), tstats(any_ttds)
        cheapest = None
        if per_sensor:
            cov = max(len(v) for v in per_sensor.values())
            cands = []
            for sid, v in per_sensor.items():
                if len(v) != cov:
                    continue
                inf_ = pr.info(sid) if pr else {"id": sid, "charged": None}
                cands.append((inf_["charged"] if inf_["charged"] is not None else INF,
                              statistics.median(t for _, t in v), sid, v))
            cands.sort(key=lambda c: (c[0], c[1], c[2]))
            _, med, sid, v = cands[0]
            cheapest = dict(pr.info(sid) if pr else {"id": sid, "honest": None, "charged": None, "foldsEvaluated": None},
                            coverage=len(v), medianTtd=med)
        rows.append({"system": system, "regime": regime, "rate": rate, "episodes": len(eps), "detected": st["n"],
                     "min": st["min"], "median": st["median"], "max": st["max"], "ttds": ttds,
                     "anyOwnRuleDetected": sa["n"], "anyOwnRuleMedian": sa["median"], "cheapest": cheapest,
                     "hours": pr.hours if pr else None, "fill": pr.fill if pr else None})
    return rows


def lane2_select(texts, system):
    """Lane-2 candidate ids by service and template text. texts: {(service, template id): masked message}."""
    out = {}
    for (svc, tid), msg in texts.items():
        if system == "otel" and svc == "kafka" and "GroupCoordinator" in msg:
            member = {"failed": "has failed, removing it from the group" in msg,
                      "rebalance": bool(re.search(r"Preparing to rebalance group .*\(reason: remo", msg)),   # the reader truncates the masked text inside "removing member"
                      "empty": bool(re.search(r"Group \S+ with generation <n> is now empty", msg))}
            grp = re.search(r"(?:in group|rebalance group|Group) (\S+)", msg)
            out[(svc, tid)] = {"message": msg, "group": grp.group(1) if grp else None,
                               "lane2": any(member.values()), "template": next((k for k, v in member.items() if v), None)}
        elif system == "teastore" and svc == "registry" and "since it failed the heartbeat" in msg:
            grp = re.search(r"teastore\.(\w+)@", msg)
            out[(svc, tid)] = {"message": msg, "group": grp.group(1) if grp else None, "lane2": True,
                               "template": "heartbeat-removal"}
    return out


def lane2_rows(J, system, cand, nofault_counts, target_group):
    """Per candidate id and per (regime, rate): detection counts and times (bc count-all), prices."""
    ids = sorted("log:%s:%s" % k for k, v in cand.items() if v["lane2"])
    meta = {"log:%s:%s" % k: v for k, v in cand.items()}
    by = defaultdict(list)
    for e in J["episodes"]:
        by[(e["regime"], rkey(e["rate"]))].append(e)
    rows = []
    for (regime, rk), eps in sorted(by.items(), key=lambda kv: (kv[0][0], float(kv[0][1]))):
        rate = eps[0]["rate"]
        pr = Prices(J, rate)
        tgt = target_group.get(regime)
        matched = [i for i in ids if tgt is None or meta[i]["group"] in (None, tgt)]
        other = [i for i in ids if i not in matched]
        det_m, det_o, det_e = [], [], []
        per_id = {i: [] for i in ids}
        for e in eps:
            tm, to, te = [], [], []
            for f in e["fires"]:
                if f[FIRE["family"]] == cv.LEDGER_FAMILY:
                    continue
                sid = f[FIRE["sensorId"]]
                if sid not in per_id:
                    continue
                if fire_counts(f, "count-all", "exclude"):
                    (tm if sid in matched else to).append(f[FIRE["ttd"]])
                    per_id[sid].append(f[FIRE["ttd"]])
                if fire_counts(f, "e-only", "exclude"):
                    te.append(f[FIRE["ttd"]])
            det_m.append(min(tm) if tm else None)
            det_o.append(min(to) if to else None)
            det_e.append(min(te) if te else None)
        sm, so, se = tstats(det_m), tstats(det_o), tstats(det_e)
        id_rows = []
        for i in ids:
            inf_ = pr.info(i)
            id_rows.append(dict(inf_, matched=i in matched, group=meta[i]["group"], template=meta[i]["template"],
                                episodesFired=len(per_id[i]),
                                medianTtd=statistics.median(per_id[i]) if per_id[i] else None,
                                noFaultRecords=nofault_counts.get(i[4:])))
        rows.append({"system": system, "regime": regime, "rate": rate, "episodes": len(eps), "matchedIds": matched,
                     "detected": sm["n"], "min": sm["min"], "median": sm["median"], "max": sm["max"], "ttds": det_m,
                     "detectedByOtherGroupIds": so["n"], "detectedUnderEOnly": se["n"], "ids": id_rows,
                     "setPrice": pr.total(matched[:1]) if matched else None,
                     "tripletPrice": pr.total(matched) if matched else None, "hours": pr.hours, "fill": pr.fill})
    return rows


def set_times(eps, members, bc="e-only", own="exclude", ledger=True):
    """Per-episode time of (ledger E) union (members) under the reading; INF = miss. The scorer's table, from the fires."""
    ms = set(members)
    out = []
    for e in eps:
        best = INF
        for f in e["fires"]:
            if f[FIRE["family"]] == cv.LEDGER_FAMILY:
                if ledger and cv.counted(f, "e-only", "exclude"):
                    best = min(best, f[FIRE["ttd"]])
                continue
            if f[FIRE["sensorId"]] in ms and fire_counts(f, bc, own):
                best = min(best, f[FIRE["ttd"]])
        out.append(best)
    return out


def summarise_times(times, holds):
    det = [t for t in times if not math.isinf(t)]
    pen = [min(t, h) if not math.isinf(t) else h for t, h in zip(times, holds)]
    return {"episodes": len(times), "detected": len(det), "min": min(det) if det else None,
            "median": statistics.median(det) if det else None,
            "meanPenalised": (sum(pen) / len(pen)) if pen else None}


# ============================================================================ O4 silence sensor (pure part)

def build_gaps(times, w0, w1):
    """Gaps between consecutive records inside [w0, w1], the window edges being virtual records: [(start, length)]."""
    ts = sorted(t for t in times if w0 <= t <= w1)
    pts = ([w0] + ts + [w1]) if VIRTUAL_EDGES else (ts if len(ts) > 1 else [w0, w1])
    return [(pts[i], pts[i + 1] - pts[i]) for i in range(len(pts) - 1)]


def max_gap(gaps):
    return max((g for _, g in gaps), default=None)


def alarm_times(gaps, w):
    """Alarm instants of a silence sensor with threshold w: start + w of every gap longer than w."""
    if STRICT_GAP:
        return [s + w for s, g in gaps if g > w]
    return [s + w for s, g in gaps if g >= w]


def calibrate_w(gap_lists):
    """w = the largest gap observed in the calibration cells (None if no cell: no sensor)."""
    mx = [max_gap(g) for g in gap_lists if g]
    return max(mx) if mx else None


# ============================================================================ raw stage (needs the frozen readers; slow)

SPANMETRICS = re.compile(r"^(calls|duration~.*)$")
LAG_RX = re.compile(r"(records_lag|kafka\.lag\.max|kafka\.request\.count|last_poll_seconds_ago|time_between_poll|"
                    r"records_lead|kafka\.message\.count|kafka\.partition\.underReplicated)")


def raw_stage(system, campaigns, log=print):
    """Load every valid cell the readout pooled and keep: per-service record times in the cell window (logs = raw compose-log
    lines with a Docker stamp; spans; OTel OTLP metric points without the spanmetrics connector's `calls`/`duration*`), the
    masked texts of the lane-2 candidate services, lane-2 id record counts, and (OTel) the lag metrics."""
    import sweep_analysis_v2 as v24
    import sweep_analysis_v3 as v31
    cells, texts = [], {}
    cm = contextlib.nullcontext()
    with v24.use_system(system):
        if system == "otel":
            import sweep_analysis_v3_2 as v32
            cm = v32.v32_context("otel", {25.0}, None, list(E_TEST_BLOCKS))
        with cm:
            find, load = v24.system_io()
            with v31.admit_b_epochs():
                for camp in campaigns:
                    root, dirs = find(REPO / camp)
                    for d in dirs:
                        c = v31.load3(load, d)
                        if not c.get("valid"):
                            continue
                        key = "%s :: %s" % v31.pool_key(root, d)
                        cells.append(cell_record(v24, c, Path(d), key, system, texts))
                    log("%s: %s -> %d cells so far" % (system, camp, len(cells)))
    return cells, texts


def cell_record(v24, c, d, key, system, texts):
    off = c["align"]["offset"]
    w0, w1 = c["t0"]["wall"], c["end"]["wall"]
    rec = defaultdict(list)
    containers = set()
    app = d / "application.log"
    if app.exists():
        for raw in app.read_text(errors="replace").splitlines():
            if " | " not in raw:
                continue
            prefix, payload = raw.split(" | ", 1)
            t, _rest = v24.v1.docker_stamp(payload)
            containers.add(norm(prefix.strip().rsplit("-", 1)[0]))
            if t is not None:
                rec[norm(prefix.strip().rsplit("-", 1)[0])].append(t)
    logids, lag = {}, {}
    for (ch, svc, tok), (obs, vals, meta) in c["prep"].items():
        add = 0.0 if meta["clock"] == "wall" else off
        if ch == "span" and not tok.endswith(":error"):
            rec[norm(svc)].extend(x + add for x in obs)
        elif (ch == "metric" and system == "otel" and meta.get("collector") == "otlp-debug-exporter"
              and not SPANMETRICS.match(tok)):
            rec[norm(svc)].extend(x + add for x in obs)
        if ch == "log" and svc in ("kafka", "registry"):
            logids["%s:%s" % (svc, tok)] = sum(1 for x in obs if w0 <= x + add <= w1)
        if system == "otel" and ch == "metric" and LAG_RX.search(tok) and svc in ("kafka", "frauddetectionservice"):
            lag["%s:%s" % (svc, tok)] = {"times": [x + add for x in obs], "vals": list(vals),
                                         "segValues": list(c["segLevel"].get((ch, svc, tok), []))}
    for k, (lv, msg) in c["logText"].items():
        if k[0] in ("kafka", "registry"):
            texts.setdefault(k, msg)
    return {"key": key, "regime": c["regime"], "rate": c["rate"], "block": c["block"], "posture": c["posture"],
            "target": c.get("target"), "w0": w0, "w1": w1,
            "records": {s: sorted(x for x in v if w0 <= x <= w1) for s, v in rec.items()},
            "containers": sorted(containers), "logIds": logids, "lag": lag}


# ============================================================================ O4 silence sensor (analysis)

def silence_analysis(system, J, cells, calib_filter, universe, log=print):
    """Per rate: calibrate w per service on the calibration cells, report fault episodes and held-out no-fault alarms.
    calib_filter(cell) -> 'train' | 'heldout' | None for no-fault cells (OTel: block split; others: leave-one-cell-out)."""
    ep_by_key = {e["cell"]: e for e in J["episodes"]}
    nofault = [c for c in cells if c["target"] is None]
    out = {}
    for rate in sorted({c["rate"] for c in cells}, reverse=True):
        nf = [c for c in nofault if c["rate"] == rate and c["posture"] == "full"]
        fault = [c for c in cells if c["rate"] == rate and c["target"] is not None and c["key"] in ep_by_key]
        loco = system != "otel"
        if loco:
            train_all = nf
            held = nf
        else:
            train_all = [c for c in nf if calib_filter(c) == "train"]
            held = [c for c in nf if calib_filter(c) == "heldout"]
        services = sorted({s for c in train_all for s, v in c["records"].items() if v})
        gaps = {c["key"]: {s: build_gaps(c["records"].get(s, []), c["w0"], c["w1"]) for s in services} for c in nf}
        w_all = {s: calibrate_w([gaps[c["key"]][s] for c in train_all]) for s in services}
        # held-out alarms
        alarms = Counter()
        hours = 0.0
        for X in held:
            if loco:
                tr = [c for c in train_all if c is not X]
                w = {s: calibrate_w([gaps[c["key"]][s] for c in tr]) for s in services}
            else:
                w = w_all
            hours += (X["w1"] - X["w0"]) / 3600.0
            for s in services:
                if w[s] is None:
                    continue
                alarms[s] += len(alarm_times(gaps[X["key"]][s], w[s]))
        per_service = {s: {"w": w_all[s], "heldOutAlarms": alarms.get(s, 0),
                           "upperPerHour": poisson_upper(alarms.get(s, 0)) / hours if hours else None}
                       for s in services}
        price_upper = math.fsum(v["upperPerHour"] for v in per_service.values()
                                if v["upperPerHour"] is not None) if hours else None
        eps = []
        for c in sorted(fault, key=lambda c: c["key"]):
            e = ep_by_key[c["key"]]
            onset, hold = e["onset"]["wall"], e["holdSeconds"]
            end = onset + hold
            tgt = norm(e["target"])
            res = {"cell": c["key"], "regime": e["regime"], "block": e["block"], "target": e["target"],
                   "heldOut": bool(e.get("heldOut")), "hold": hold, "targetTtd": None, "targetPreOnsetAlarms": None,
                   "anyTtd": None, "anyService": None, "servicesAlarmingInHold": 0}
            first_any = (INF, None)
            n_alarming = 0
            for s in services:
                if w_all[s] is None:
                    continue
                g = build_gaps(c["records"].get(s, []), c["w0"], end)
                al = alarm_times(g, w_all[s])
                post = sorted(a - onset for a in al if a >= onset)
                pre = [a for a in al if a < onset]
                if s == tgt:
                    res["targetTtd"] = post[0] if post else None
                    res["targetPreOnsetAlarms"] = len(pre)
                    res["targetW"] = w_all[s]
                if post:
                    n_alarming += 1
                    if post[0] < first_any[0]:
                        first_any = (post[0], s)
            res["servicesAlarmingInHold"] = n_alarming
            if first_any[1] is not None:
                res["anyTtd"], res["anyService"] = first_any
            res["targetHasSensor"] = tgt in services and w_all.get(tgt) is not None
            eps.append(res)
        out[rkey(rate)] = {"rate": rate, "services": services, "nServices": len(services),
                           "notCalibratable": sorted(set(universe) - set(services)), "universe": sorted(universe),
                           "calibrationCells": len(train_all), "heldOutCells": len(held), "heldOutHours": hours,
                           "calibrationScheme": ("leave-one-cell-out over the rate's no-fault cells (w for a held-out cell "
                                                 "from the others); fault episodes use all of them") if loco else
                                                "OTel: calibrate on no-fault blocks 1-3, held out blocks 4-5",
                           "perService": per_service, "heldOutAlarmsTotal": sum(alarms.values()),
                           "servicesWithAlarms": sorted(s for s in alarms if alarms[s]),
                           "priceUpperPerHourSum": price_upper, "episodes": eps}
        log("silence %s r%s: %d services, %d calibration cells, %d held-out cells (%.3f h), %d held-out alarms, %d episodes" % (
            system, rkey(rate), len(services), len(train_all), len(held), hours, sum(alarms.values()), len(eps)))
    return out


# ============================================================================ O3 (E lane 3)

def lane3(J, cells, prices):
    """Arming status and pooled n of E's lag/backlog metric ids; descriptive movement in the fraud pause windows."""
    sens = sensors_of(J, 25.0)
    ids = sorted(k for k in sens if k.startswith("metric:") and (
        re.search(r"records_lag|kafka\.lag\.max|kafka\.request\.count", k) or
        re.search(r"metric:(kafka|frauddetectionservice|accountingservice):.*(kafka|lag|queue)", k)))
    train = [c for c in cells if c["block"] in E_TRAIN_BLOCKS]
    fraud = [c for c in cells if c["regime"] == "fraud-pause-effect"]
    ep_of = {e["cell"]: e for e in J["episodes"]}
    rows = []
    for i in ids:
        s = sens[i]
        svc, tok = i.split(":", 2)[1], i.split(":", 2)[2]
        key = "%s:%s" % (svc, tok)
        pooled = [v for c in train for v in c["lag"].get(key, {}).get("segValues", [])]
        row = {"id": i, "family": s["family"], "calibrated": s["calibrated"], "unarmed": s["unarmed"],
               "dropped": s["dropped"], "inert": s["inert"], "placeable": s["placeable"],
               "foldsEvaluated": s["foldsEvaluated"], "honestUpperPerHour": s["honestUpperPerHour"],
               "pooledN": len(pooled) if key in {k for c in train for k in c["lag"]} else None,
               "pooledMedian": statistics.median(pooled) if pooled else None,
               "pooledMin": min(pooled) if pooled else None, "pooledMax": max(pooled) if pooled else None}
        row["fraudCellsWithSeries"] = sum(1 for c in fraud if key in c["lag"])
        pts_in, outside, n_ep = [], 0, 0
        for c in fraud:
            e = ep_of.get(c["key"])
            L = c["lag"].get(key)
            if e is None or L is None:
                continue
            n_ep += 1
            o, h = e["onset"]["wall"], e["holdSeconds"]
            inside = [v for t, v in zip(L["times"], L["vals"]) if o <= t <= o + h]
            pts_in.append(len(inside))
            if pooled and any(v < min(pooled) or v > max(pooled) for v in inside):
                outside += 1
        row["fraudEpisodes"] = n_ep
        row["pointsInHoldPerEpisode"] = pts_in
        row["episodesWithPointOutsidePooledRange"] = outside
        rows.append(row)
    return rows


# ============================================================================ assembly

def load_json(p):
    return json.loads(Path(p).read_text())


def build(out_dir, log=print):
    out_dir = Path(out_dir)
    if out_dir.exists() or out_dir.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s (new evidence never overwrites old)" % out_dir)
    R = {k: load_json(p) for k, p in READOUTS.items()}
    JE, JT, JH = R["otel"], R["teastore"], R["hotel"]
    campaigns = {"otel": JE["campaigns"], "teastore": JT["campaigns"], "hotel": JH["campaigns"]}
    raw, texts = {}, {}
    for system in ("otel", "teastore", "hotel"):
        raw[system], texts[system] = raw_stage(system, campaigns[system], log)
    result = {"label": POST_HOC, "scope": SCOPE, "inputs": {k: str(p.relative_to(REPO)) for k, p in READOUTS.items()},
              "campaigns": campaigns}

    # ---- O1
    J_of = {"otel": JE, "teastore": JT, "hotel": JH}
    o1 = []
    o1 += lane1_rows(JE, "otel")
    o1 += [dict(r, system="otel (test blocks 4-5 only)") for r in lane1_rows(JE, "otel", lambda e: e["block"] in E_TEST_BLOCKS)]
    o1 += lane1_rows(JT, "teastore")
    o1 += lane1_rows(JH, "hotel")
    o1 += [dict(r, system="hotel (v2.4 readout: the plan's numbers, no prices)") for r in lane1_rows(R["hotel-v24"], "hotel-v24")
           if r["regime"] == "search-pause-effect"]
    result["O1"] = o1

    # ---- O2
    o2 = {}
    cand_e = lane2_select(texts["otel"], "otel")
    cand_t = lane2_select(texts["teastore"], "teastore")
    nofault_counts = {}
    for system, cand in (("otel", cand_e), ("teastore", cand_t)):
        cnt = {}
        for k, v in cand.items():
            if v["lane2"]:
                key = "%s:%s" % k
                cnt[key] = sum(c["logIds"].get(key, 0) for c in raw[system] if c["target"] is None)
        nofault_counts[system] = cnt
    cells_nf = {s: sum(1 for c in raw[s] if c["target"] is None) for s in raw}
    o2 = {"candidatesOtel": [{"id": "log:%s:%s" % k, **v} for k, v in sorted(cand_e.items())],
          "candidatesTeaStore": [{"id": "log:%s:%s" % k, **v} for k, v in sorted(cand_t.items())],
          "noFaultRecordCounts": {s: dict(nofault_counts[s]) for s in nofault_counts}, "noFaultCells": cells_nf}
    grp = {"accounting-pause-effect": "accountingservice", "fraud-pause-effect": "frauddetectionservice",
           "frontend-pause-effect": None}
    o2["otel"] = lane2_rows(JE, "otel", cand_e, dict(nofault_counts["otel"]), grp)
    o2["teastore"] = lane2_rows(JT, "teastore", cand_t, dict(nofault_counts["teastore"]),
                                {"auth-freeze-effect": "auth", "persistence-cpu-throttle-effect": "persistence"})
    o2["hotel"] = DASH + " (Hotel registers services in consul without health checks; consul writes no log in the retained application.log)"
    result["O2"] = o2

    # ---- O3
    pr_e = Prices(JE, 25.0)
    o3 = {"rows": lane3(JE, raw["otel"], pr_e),
          "reader": O3_READER_TEXT}
    result["O3"] = o3

    # ---- O4
    def e_split(c):
        return "train" if c["block"] in E_TRAIN_BLOCKS else ("heldout" if c["block"] in E_TEST_BLOCKS else None)
    def universe(system, J):
        u = {norm(k.split(":")[1]) for k in J["calibration"]["primary"]["perRate"][next(iter(J["calibration"]["primary"]["perRate"]))]["sensors"]
             if not k.startswith("ledger:")}
        for c in raw[system]:
            u |= set(c["containers"])
        return sorted(u)
    result["O4"] = {"otel": silence_analysis("otel", JE, raw["otel"], e_split, universe("otel", JE), log),
                    "teastore": silence_analysis("teastore", JT, raw["teastore"], None, universe("teastore", JT), log),
                    "hotel": silence_analysis("hotel", JH, raw["hotel"], None, universe("hotel", JH), log)}

    # ---- O5 and cross-checks
    result["O5"], result["crossChecks"] = o5_and_checks(R, raw, result)
    JTR = R["otel-train"]
    same_cal = JTR["calibration"]["primary"]["perRate"]["25"]["sensors"] == JE["calibration"]["primary"]["perRate"]["25"]["sensors"]
    tr = {(e["regime"], e["block"]): e["fires"] for e in JTR["episodes"]}
    same_fires = all(tr[(e["regime"], e["block"])] == e["fires"] for e in JE["episodes"] if e["block"] in E_TRAIN_BLOCKS)
    result["crossChecks"].append({"check": "E training and scoring readouts: identical calibration and identical fires on blocks 1-3 (decision 102)",
                                  "ok": bool(same_cal and same_fires), "sameCalibration": same_cal, "sameFires": same_fires})
    out_dir.mkdir(parents=True)
    (out_dir / "lanes.json").write_text(json.dumps(result, indent=1, default=str))
    (out_dir / "LANES.md").write_text(render_md(result))
    log("wrote %s" % out_dir)
    return result


def o5_and_checks(R, raw, res):
    JE, JT, JH = R["otel"], R["teastore"], R["hotel"]
    out, checks = [], []
    O1 = res["O1"]
    e_json = load_json(OTEL_E_JSON)["rates"]["25"]
    placement = load_json(OTEL_E_PLACEMENT)["rates"]["25"]
    tc = load_json(TEASTORE_C_JSON)["rates"]

    def silence_times(system, rk, eps, mode):
        by_cell = {x["cell"]: x for x in res["O4"][system][rk]["episodes"]}
        out_ = []
        for e in eps:
            x = by_cell.get(e["cell"])
            t = None if x is None else (x["targetTtd"] if mode == "target" else x["anyTtd"])
            out_.append(INF if t is None else t)
        return out_

    def add(system, scope, rate, eps, name, lane, times, price, reading, note=""):
        holds = [e["holdSeconds"] for e in eps]
        s = summarise_times(times, holds)
        out.append({"system": system, "scope": scope, "rate": rate, "lane": lane, "set": name, "reading": reading,
                    "priceCharged": price["charged"] if price else None,
                    "priceZeroAlarm": price["zeroAlarm"] if price else None,
                    "members": price["members"] if price else None, "unevaluated": price["unevaluated"] if price else None,
                    "note": note, **s})

    # ------------------------------------------------------------------ OTel E
    pr = Prices(JE, 25.0)
    V = sorted(pr.V)
    sets_json = e_json["sets"]
    frozen = sets_json["frontier (effort<=any, runtime<=any) @6/T_r"]["sensors"]
    inf_set = sets_json["frontier (effort<=any, runtime<=any) @inf"]["sensors"]
    ootb = placement["comparators"]["out of the box"]["setMembers"]
    scopes = {"off-path pooled, blocks 1-5": lambda e: e["regime"] in PAUSE_REGIMES["otel"],
              "off-path test blocks 4-5": lambda e: e["regime"] in PAUSE_REGIMES["otel"] and e["block"] in E_TEST_BLOCKS}
    own_e = [r for r in O1 if r["system"] == "otel" and r["regime"] in PAUSE_REGIMES["otel"] and r["cheapest"]]
    own_set = sorted({r["cheapest"]["id"] for r in own_e})
    coord_rows = [r for r in res["O2"]["otel"] if r["regime"] in PAUSE_REGIMES["otel"]]
    coord_set = sorted({r["matchedIds"][0] for r in coord_rows if r["matchedIds"]})
    for scope, flt in scopes.items():
        eps = [e for e in JE["episodes"] if flt(e)]
        add("otel", scope, 25.0, eps, "ledger alone", "ledger", set_times(eps, []), {"charged": 0.0, "zeroAlarm": 0.0, "members": 0, "unevaluated": 0},
            "e-only/exclude", "request ledger E is in every set and is not priced here")
        add("otel", scope, 25.0, eps, "frozen set @6/T_r (1 sensor)", "frozen", set_times(eps, frozen), pr.total(frozen), "e-only/exclude")
        add("otel", scope, 25.0, eps, "inf set (%d sensors)" % len(inf_set), "inf", set_times(eps, inf_set), pr.total(inf_set), "e-only/exclude")
        add("otel", scope, 25.0, eps, "out of the box (%d)" % len(ootb), "out-of-the-box", set_times(eps, ootb), pr.total(ootb), "e-only/exclude")
        add("otel", scope, 25.0, eps, "full (V_r, %d)" % len(V), "full", set_times(eps, V), pr.total(V), "e-only/exclude")
        add("otel", scope, 25.0, eps, "own: cheapest full-coverage own sensor per class (%d)" % len(own_set), "own",
            set_times(eps, own_set, "count-all", "only"), pr.total(own_set), "count-all/own-only",
            "uses the injected target's own telemetry (decisions 84/111 exclude it from the rules)")
        add("otel", scope, 25.0, eps, "coordinator: one Kafka id per class (%d)" % len(coord_set), "coordinator",
            set_times(eps, coord_set, "count-all", "exclude"), pr.total(coord_set), "count-all/exclude")
        sp = res["O4"]["otel"]["25"]
        for mode, label in (("any", "silence: all services, earliest alarm anywhere"), ("target", "silence: the target's sensor only (target known)")):
            tm = silence_times("otel", "25", eps, mode)
            price = {"charged": sp["priceUpperPerHourSum"], "zeroAlarm": sp["priceUpperPerHourSum"],
                     "members": sp["nServices"] if mode == "any" else 1, "unevaluated": 0}
            if mode == "target":
                price = {"charged": None, "zeroAlarm": None, "members": 1, "unevaluated": 0}
            add("otel", scope, 25.0, eps, label, "silence", tm, price, "own records",
                ("price = sum over the %d services of the held-out Poisson 95 %% upper bound / held-out hours (blocks 4-5, 0.10 h); not the LOCO bound" % sp["nServices"])
                if mode == "any" else "needs the injected target's identity")
    # cross-checks against otel-e.json (test episodes) for the scorer's own sets
    names = {"frozen set @6/T_r (1 sensor)": "frontier (effort<=any, runtime<=any) @6/T_r",
             "inf set": "frontier (effort<=any, runtime<=any) @inf", "ledger alone": "ledger alone", "full": "full"}
    test_eps = [e for e in JE["episodes"] if e["block"] in E_TEST_BLOCKS]
    sc_eps = {tuple(x["episodeKey"][:3]): x for x in e_json["episodes"]}
    for label, members, jname in (("ledger alone", [], "ledger alone"), ("frozen @6/T_r", frozen, "frontier (effort<=any, runtime<=any) @6/T_r"),
                                  ("inf set", inf_set, "frontier (effort<=any, runtime<=any) @inf"), ("full (V_r)", V, "full")):
        mine = set_times(test_eps, members)
        bad = []
        for e, t in zip(test_eps, mine):
            ref = sc_eps[(e["regime"], rkey(e["rate"]), e["block"])]["sets"][jname]["ttd"]
            ref = INF if ref is None else ref
            if (math.isinf(ref) != math.isinf(t)) or (not math.isinf(t) and abs(ref - t) > 1e-6):
                bad.append((e["regime"], e["block"], t, ref))
        checks.append({"check": "recomputed %s equals otel-e.json ttd on the 6 test episodes" % label, "ok": not bad, "mismatches": bad})
    checks.append({"check": "full (V_r) charged price equals placement-e.json comparators.full.charged",
                   "ok": abs(pr.total(V)["charged"] - placement["comparators"]["full"]["charged"]) < 1e-6,
                   "mine": pr.total(V)["charged"], "reference": placement["comparators"]["full"]["charged"]})
    checks.append({"check": "inf set charged price equals placement-e.json grid inf point",
                   "ok": abs(pr.total(inf_set)["charged"] - 569.1826900886144) < 1e-6, "mine": pr.total(inf_set)["charged"]})
    acc = {(e["block"]): t for e, t in zip(test_eps, set_times(test_eps, frozen)) if e["regime"] == "accounting-pause-effect"}
    infa = {(e["block"]): t for e, t in zip(test_eps, set_times(test_eps, inf_set)) if e["regime"] == "accounting-pause-effect"}
    own_acc = {}
    for e in test_eps:
        if e["regime"] == "accounting-pause-effect":
            ts = [f[FIRE["ttd"]] for f in e["fires"] if f[FIRE["sensorId"]] == "span:accountingservice:orders_receive"
                  and f[FIRE["rule"]] == "absent" and fire_counts(f, "count-all", "only")]
            own_acc[e["block"]] = min(ts) if ts else None
    checks.append({"check": "accounting test blocks 4/5: frozen set misses, inf set detects at ~44.3/44.1 s, own orders_receive absent at ~1.0/1.45 s",
                   "ok": (all(math.isinf(v) for v in acc.values()) and abs(infa[4] - 44.3) < 0.1 and abs(infa[5] - 44.1) < 0.1
                          and own_acc[4] is not None and own_acc[5] is not None),
                   "frozen": acc, "inf": infa, "ownOrdersReceiveAbsent": own_acc})
    # poisson helper equals the frozen reader's
    import sweep_analysis_v2 as v24
    checks.append({"check": "poisson_upper equals the frozen reader's for k = 0..6",
                   "ok": all(abs(poisson_upper(k) - v24.poisson_upper(k)) < 1e-6 for k in range(7))})
    checks.append({"check": "zero-alarm price 2.9957/T_r equals the honest bound of a zero-alarm evaluated E sensor (19.9715/h at T_r = 0.15 h)",
                   "ok": abs(ZERO_ALARM_FACTOR / pr.hours - sensors_of(JE, 25.0)["metric:flagd:http.server.duration~rate"]["honestUpperPerHour"]) < 1e-6})

    # ------------------------------------------------------------------ TeaStore C and Hotel, per rate
    for system, J in (("teastore", JT), ("hotel", JH)):
        for rate in sorted({e["rate"] for e in J["episodes"]}, reverse=True):
            rk = rkey(rate)
            pr = Prices(J, rate)
            Vs = sorted(pr.V)
            eps = [e for e in episodes_at(J, rate) if e["regime"] in PAUSE_REGIMES[system]]
            scope = "%s pooled" % PAUSE_REGIMES[system][0]
            add(system, scope, rate, eps, "ledger alone", "ledger", set_times(eps, []), {"charged": 0.0, "zeroAlarm": 0.0, "members": 0, "unevaluated": 0},
                "e-only/exclude", "request ledger E is in every set and is not priced here")
            if system == "teastore":
                sets = tc[rk]["sets"]
                for nm, lane in (("primary 6/h", "frozen"), ("primary inf", "inf")):
                    mem = sets[nm]["sensors"]
                    add(system, scope, rate, eps, "%s (%d sensor(s); frozen before campaign C)" % (nm, len(mem)), lane,
                        set_times(eps, mem), pr.total(mem), "e-only/exclude",
                        "includes episodes of the placement's own training campaigns (in-sample for those)")
            add(system, scope, rate, eps, "full (V_r, %d)" % len(Vs), "full", set_times(eps, Vs), pr.total(Vs), "e-only/exclude")
            r1 = [r for r in O1 if r["system"] == system and r["regime"] in PAUSE_REGIMES[system] and rkey(r["rate"]) == rk and r["cheapest"]]
            own_ = sorted({r["cheapest"]["id"] for r in r1})
            add(system, scope, rate, eps, "own: cheapest full-coverage own sensor (%d)" % len(own_), "own",
                set_times(eps, own_, "count-all", "only"), pr.total(own_), "count-all/own-only",
                "uses the injected target's own telemetry (decisions 84/111 exclude it from the rules)")
            if system == "teastore":
                rows2 = [r for r in res["O2"]["teastore"] if r["regime"] in PAUSE_REGIMES[system] and rkey(r["rate"]) == rk]
                cs = sorted({r["matchedIds"][0] for r in rows2 if r["matchedIds"]})
                add(system, scope, rate, eps, "coordinator: registry heartbeat removal (%d)" % len(cs), "coordinator",
                    set_times(eps, cs, "count-all", "exclude"), pr.total(cs), "count-all/exclude")
            else:
                add(system, scope, rate, eps, "coordinator", "coordinator", [INF] * len(eps), None, DASH,
                    "none in Hotel: the lane does not exist (no row of detections, no price)")
                out[-1].update({"detected": None, "median": None, "min": None, "meanPenalised": None})
            sp = res["O4"][system].get(rk)
            if sp:
                tm_any = silence_times(system, rk, eps, "any")
                add(system, scope, rate, eps, "silence: all %d services, earliest alarm anywhere" % sp["nServices"], "silence", tm_any,
                    {"charged": sp["priceUpperPerHourSum"], "zeroAlarm": sp["priceUpperPerHourSum"], "members": sp["nServices"], "unevaluated": 0},
                    "own records", "price = sum over services of the leave-one-cell-out Poisson 95 % upper bound / held-out hours")
                add(system, scope, rate, eps, "silence: the target's sensor only (target known)", "silence", silence_times(system, rk, eps, "target"),
                    {"charged": None, "zeroAlarm": None, "members": 1, "unevaluated": 0}, "own records", "")
    return out, checks


# ============================================================================ rendering

def render_md(R):
    L = []
    w = L.append
    w("# Lane tables, 2026-10-13 (written 2026-10-14)\n")
    w("**%s.** Scope of every table: **%s** (one SUT, one host, one campaign family per row). Produced by `research/lanes/lanes_tables.py` "
      "from the frozen readouts and the retained raw cells, read-only; no frozen file was edited and no reader constant was changed. "
      "Plan: `research/PLAN_LANES_20261014.md`, Directions O1-O5.\n" % (POST_HOC, SCOPE))
    w("Inputs: OTel campaign E `%s` (20 cells: 15 fault episodes + 5 no-fault, 3 training no-fault cells calibrate, T_r = 0.15 h, train-only "
      "calibration for every episode); TeaStore C `%s` (6 campaigns pooled; 28 auth-freeze, 28 persistence-cpu-throttle, 101 no-fault cells); "
      "Hotel: `%s`, the v3.1 re-read of the same `tmp/hotelsweep3-evidence` cells as `readout-hotel-r3-v2.4` (16 search-pause episodes) plus the two Hotel "
      "quiet campaigns (96 no-fault cells in all: 16 in the sweep campaign, 80 in the quiet ones). v3.1 is used because v2.4 carries no calibration, so no prices; the 16 search-pause episodes are identical.\n"
      % (R["inputs"]["otel"], R["inputs"]["teastore"], R["inputs"]["hotel"]))
    w("Readings: a fire counts only through `celf_v3.counted` and only if its `counts` flag is true. Placement-style rows: bc `e-only`, own `exclude` "
      "(the scorer's). Lane 1: own `only`, bc `count-all`. Lane 2: bc `count-all`. Times are seconds after the pre-command onset stamp, "
      "a miss is `—` in the time columns and is charged the hold only in `mean (miss = hold)`.\n")

    w("## Cross-checks (computed here against the repository's own numbers)\n")
    w(md_table(["check", "ok"], [[c["check"], "PASS" if c["ok"] else "FAIL " + json.dumps(c.get("mismatches", c))[:200]] for c in R["crossChecks"]]))
    w("")

    # ---------------------------------------------------------------- O1
    w("\n## O1 lane 1: own silence (`absent` on the paused target's own sensors)\n")
    w("Scope: instance. Denominator: episodes of the regime and rate in the readout. `any own rule` counts own fires of every rule (S-family "
      "medians etc.), `absent` only the silence rule. Cheapest sensor = the cheapest of the own `absent` sensors with the largest coverage; "
      "price = honest upper bound per hour (`—` = evaluated in 0 folds, no bound) and the decision-73 charge.\n")
    rows = []
    for r in R["O1"]:
        ch = r["cheapest"]
        rows.append([r["system"], r["regime"], r["rate"], "%d/%d" % (r["detected"], r["episodes"]), r["min"], r["median"], r["max"],
                     "%d/%d, med %s" % (r["anyOwnRuleDetected"], r["episodes"], fmt(r["anyOwnRuleMedian"])),
                     (ch["id"] + " (%d/%d)" % (ch["coverage"], r["episodes"])) if ch else DASH,
                     ch["honest"] if ch else None, ch["charged"] if ch else None,
                     ("%s folds" % ch["foldsEvaluated"]) if ch and ch["foldsEvaluated"] is not None else DASH])
    w(md_table(["system", "regime", "rate", "detected (absent)", "min s", "median s", "max s", "any own rule", "cheapest own sensor",
                "honest upper /h", "charged /h", "evaluated"], rows))
    w("\nReader version matters for Hotel: the `hotel` rows are the v3.1 re-read (calibrated `absent` gap scale per sensor); the `hotel (v2.4 ...)` rows are "
      "`readout-hotel-r3-v2.4`, the source of the plan's table (v2.4: the gap scale is a fixed multiple of the pooled largest gap, so later and without prices). "
      "Same 16 cells, different detector, so the Hotel search-pause medians differ by reader version; v3.1 is the primary Hotel reading because it carries prices.\n")
    w("\n**What this cannot say.** The own sensors measure the injection (decisions 84/111): a pause of the service that emits is seen by that "
      "service's silence by construction (BC-downstream-absent), so this is a ceiling for a monitor that knows which service to watch, not a "
      "placement result. Lane 1 does not detect non-pause faults (cpu-throttle, net-delay rows show it). A frozen reading of E's own fires "
      "uses the readout's train-only calibration; the `absent` rule's gap scale is calibrated per rate.\n")

    # ---------------------------------------------------------------- O2
    w("\n## O2 lane 2: coordinator side\n")
    w("Ids found by service and template text in the raw `application.log` (the reader's masked message, `<n>` = a masked number).\n")
    w("**OTel, service `kafka`, GroupCoordinator templates seen in the 20 E cells:**\n")
    w(md_table(["id", "group", "lane-2 template", "message"],
               [[c["id"], c["group"], c["template"] if c["lane2"] else DASH, c["message"][:150]] for c in R["O2"]["candidatesOtel"]]))
    w("\n**TeaStore, service `registry`, templates containing `since it failed the heartbeat`:**\n")
    w(md_table(["id", "template", "message"], [[c["id"], c["template"], c["message"][:170]] for c in R["O2"]["candidatesTeaStore"]]))
    nf = R["O2"]["noFaultRecordCounts"]
    w("\nRecords of the lane-2 ids inside the measurement window of every retained no-fault cell of the readout (a template never seen counts 0): "
      "OTel %s over %d cells; TeaStore %s over %d cells. A zero here is why `foldsEvaluated` is 0 and decision 73 charges the fill.\n" % (
          json.dumps(nf["otel"]), R["O2"]["noFaultCells"]["otel"], json.dumps(nf["teastore"]), R["O2"]["noFaultCells"]["teastore"]))
    for system in ("otel", "teastore"):
        w("\n### %s\n" % system)
        rows = []
        for r in R["O2"][system]:
            sp = r["setPrice"] or {}
            tp = r["tripletPrice"] or {}
            rows.append([r["regime"], r["rate"], "%d/%d" % (r["detected"], r["episodes"]), r["min"], r["median"], r["max"],
                         r["detectedUnderEOnly"], r["detectedByOtherGroupIds"], len(r["matchedIds"]),
                         sp.get("charged"), sp.get("zeroAlarm"), tp.get("charged"), tp.get("zeroAlarm"),
                         r["ids"][0]["honest"] if r["ids"] else None])
        w(md_table(["regime", "rate", "detected (count-all)", "min s", "median s", "max s", "of which scorer-counted (e-only)", "fired by other group's ids",
                    "matched ids", "1 id charged /h", "1 id if zero alarms /h", "all matched ids charged /h", "all matched ids if zero alarms /h",
                    "honest bound of id 1"], rows))
    w("\nHotel: %s.\n" % R["O2"]["hotel"])
    w("**What this cannot say.** The coordinator ids never occur in a no-fault cell, so no honest bound exists and the price is a convention "
      "(decision 73's fill, or 2.9957/T_r if one assumes zero alarms); neither is an observed false-alarm rate. The Kafka lane is the "
      "session timeout (about 44 s) and the registry lane the 10 s heartbeat window: both are properties of those two SUTs' defaults, one SUT each. "
      "The two Kafka groups have disjoint ids (class-matched columns). The TeaStore fire is BC-caller-log flagged, which the scorer reads as a miss.\n")

    # ---------------------------------------------------------------- O3
    w("\n## O3 lane 3: backlog/lag metrics of E (arming status; the frozen reader was not re-run)\n")
    w(O3_READER_TEXT + "\n")
    rows = [[r["id"], ",".join(r["unarmed"]) or DASH, r["placeable"], r["foldsEvaluated"], r["pooledN"], r["pooledMedian"], r["pooledMin"], r["pooledMax"],
             ("%s of %d eps" % (r["pointsInHoldPerEpisode"], r["fraudEpisodes"])) if r.get("fraudEpisodes") else DASH,
             r.get("episodesWithPointOutsidePooledRange") if r.get("fraudEpisodes") else None]
            for r in R["O3"]["rows"] if re.search(r"records_lag|kafka\.lag\.max|kafka\.request\.count|queue\.(length|usage)|kafka\.message\.count|last_poll|time_between_poll|records_lead|queueSize", r["id"])]
    w(md_table(["metric id", "unarmed rules", "placeable", "folds evaluated", "pooled n (train cells' fault-free segments)", "pooled median", "min", "max",
                "points inside the pause hold, per fraud episode", "fraud episodes with a hold point outside the pooled range"], rows))
    w("\n%d of the %d kafka/lag/queue metric ids of E's ground set matched here are unarmed on `spike`, `run3` and `median` (these need pooled n >= MIN_BASELINE_POOLED = 20); "
      "the metrics exported at a 60 s cadence give n of a few points per cell. The last two columns are descriptive only (fraud pause cells): they show whether the "
      "metric exports anything at all inside the 60 s pause and whether such a point leaves the pooled fault-free range; no rule was applied.\n" % (
          sum(1 for r in R["O3"]["rows"] if set(r["unarmed"]) >= {"spike", "run3", "median"}), len(R["O3"]["rows"])))
    w("`metric:kafka:kafka.lag.max` is, by its OpenTelemetry Kafka-JMX name, the broker's follower-replica lag, not consumer-group lag (its description was not "
      "checked in this repository); only `frauddetectionservice`'s `kafka.consumer.*` ids are client-side consumer metrics, and E's ground set holds no `kafka.*` metric id for `accountingservice` (its consumer is rdkafka).\n")
    w("**What this cannot say.** Whether a lag metric would move in a pause is not answered here: no lowered-threshold reading was made. A paused JVM exports "
      "nothing, so the client-side lag metric is silent rather than high; group lag needs a broker-side source (the plan's S1). Pooled n here "
      "counts the fault-free segments of the nine training fault cells and three no-fault cells.\n")

    # ---------------------------------------------------------------- O4
    w("\n## O4 shared-fate silence sensor per container\n")
    w("A sensor per service: alarm at (last record + w) when no record of any kind arrives for longer than w. **Records**: every compose-log line with a "
      "Docker stamp in `application.log`; spans (the readers' kept spans, probe traces excluded; span times are the service-side start stamps, so a real "
      "monitor would see them later by the export delay, not measured here); for OTel also the OTLP metric points of the service (the spanmetrics connector's "
      "`calls` and `duration*` are the collector's, excluded). TeaStore/Hotel system samples (cgroup, docker stats) are excluded: the harness pulls them, "
      "the service does not emit them. OTLP log records and resource-only exports were not counted (more records would shorten gaps, so w here is conservative). "
      "**Window** per cell: the measurement window [barrier, barrier + 180 s]; its edges are virtual records, so a service silent for the whole window has a gap of 180 s.\n")
    w("**Calibration**: w = the largest gap of that service in calibration cells, so a calibration cell cannot alarm. OTel: no-fault blocks 1-3 train (3 cells, 0.15 h), "
      "blocks 4-5 held out (2 cells, 0.10 h). TeaStore/Hotel have no registry split: leave-one-cell-out over the rate's no-fault cells (posture full), "
      "so the held-out hours equal the calibration hours; fault episodes use w from all of them. Alarm bound: exact Poisson 95 % upper limit per service / held-out hours.\n")
    for system in ("otel", "teastore", "hotel"):
        w("\n### %s\n" % system)
        rows = []
        for rk, a in sorted(R["O4"][system].items(), key=lambda kv: float(kv[0])):
            eps = [e for e in a["episodes"] if e["regime"] in PAUSE_REGIMES[system] + CONTROL_REGIMES.get(system, ())]
            by = defaultdict(list)
            for e in eps:
                by[e["regime"]].append(e)
            for regime, es in sorted(by.items()):
                tt = [e["targetTtd"] for e in es]
                ta = [e["anyTtd"] for e in es]
                st, sa = tstats(tt), tstats(ta)
                ws = [e.get("targetW") for e in es if e.get("targetW") is not None]
                rows.append([rk, a["nServices"], "%d cells, %.3f h" % (a["heldOutCells"], a["heldOutHours"]), a["heldOutAlarmsTotal"],
                             a["priceUpperPerHourSum"], regime, len(es), "%d/%d" % (st["n"], len(es)), st["min"], st["median"], st["max"],
                             "%d/%d" % (sa["n"], len(es)), sa["median"], statistics.median(ws) if ws else None,
                             sum(e["targetPreOnsetAlarms"] or 0 for e in es)])
        w(md_table(["rate", "services (sensors)", "held-out", "held-out alarms (all services)", "sum of upper bounds /h", "regime", "episodes",
                    "target sensor detected", "min s", "median s", "max s", "any service detected", "median s", "target w (median s)",
                    "target pre-onset alarms"], rows))
        a0 = next(iter(R["O4"][system].values()))
        if system == "otel":
            w("\nw per service (s, from blocks 1-3): " + ", ".join("%s %.2f (held-out alarms %d)" % (k, v["w"], v["heldOutAlarms"])
                                                                  for k, v in a0["perService"].items()) + ".\n")
        w("\nServices with a sensor (%d): %s. Services of the universe (ground-set services plus every container with a compose-log line) "
          "with NO record inside any calibration window at the first rate listed, so no w and no sensor (they never emit in normal operation or emit "
          "outside the window) (%d): %s.\n" % (a0["nServices"], ", ".join(a0["services"]), len(a0["notCalibratable"]),
                                              ", ".join(a0["notCalibratable"]) or DASH))
    w("**What this cannot say.** w is the maximum of a few cells (OTel 3 cells, 540 s), an extreme-value estimate with no coverage guarantee (under leave-one-cell-out the cell holding the largest gap alarms when left out, so each service shows about one alarm per rate by exchangeability: the TeaStore and Hotel held-out counts are close to the number of services, which is that rule's false-alarm rate, 1 per n cells per service, not a defect); the held-out alarm "
      "count is a count over 0.10 h (OTel) and the Poisson bound on 0 alarms is 2.9957/H per service, 30/h per service at H = 0.10 h, so the summed bound "
      "is large however well the sensor behaves. The load is a deterministic constant-rate schedule, so at TeaStore and Hotel rates the calibrated w is about the request interval "
      "(Hotel: 20 / 5 / 1 / 0.1 s at 0.05 / 0.2 / 1 / 10 req/s) and the detection time is about w: the sensor watches the load schedule as much as the service. "
      "A silence sensor needs a service that emits during normal operation (see the services without a sensor). It detects the paused service, not a degraded one, and it does not distinguish the pause from a "
      "collector or host failure (shared fate). Records are service-side stamps for spans and metrics.\n")

    # ---------------------------------------------------------------- O5
    w("\n## O5 price versus detection (table only)\n")
    w("x = summed price per hour of the set's sensors. **Charged** = decision 73 (honest upper bound, the rate's largest evidenced bound for sensors "
      "evaluated in 0 folds). **If evaluated at zero alarms** = honest bound where one exists, else 2.9957/T_r. The ledger is in every set and is not priced "
      "(`0`). The silence lane's price is the sum of per-service held-out Poisson bounds (a different estimator; target-only row has no price). y = pause-type "
      "episodes detected / total by (ledger union set) under the reading in the `reading` column; median over detected; `mean (miss = hold)` is the objective's "
      "penalised mean. Frozen/inf/out-of-the-box rows exist only where a frozen set was scored (E, TeaStore C); Hotel has none.\n")
    cur = None
    for r in R["O5"]:
        key = (r["system"], r["scope"], r["rate"])
        if key != cur:
            cur = key
            w("\n**%s, %s, rate %s**\n" % (r["system"], r["scope"], fmt(r["rate"])))
            w("| lane | set | reading | x charged /h | x if zero alarms /h | detected | median s | min s | mean (miss = hold) | note |")
            w("|---|---|---|---|---|---|---|---|---|---|")
        det = DASH if r["detected"] is None else "%d/%d" % (r["detected"], r["episodes"])
        w("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (r["lane"], r["set"], r["reading"], fmt(r["priceCharged"]), fmt(r["priceZeroAlarm"]), det,
                                                                 fmt(r["median"]), fmt(r["min"]), fmt(r["meanPenalised"]), r["note"]))
    w("\n**What this cannot say.** One SUT, host and campaign per row; no row is a comparison across SUTs. The sets are not on a common footing: the frozen sets "
      "were chosen on training episodes by the repository's objective, the lane sets were chosen here after seeing all episodes (in-sample by construction; the own "
      "sensor is the injection itself); `full` is the ceiling and its price is a convention for 85 % of sensors (fill). Prices of different estimators "
      "(leave-one-out honest bound, held-out Poisson, fill) are shown side by side and are not comparable to one decimal. n is 10 off-path episodes (4 test) for E, "
      "28 (7 per rate) for TeaStore, 16 (4 per rate) for Hotel. TeaStore and Hotel faults are on the request path, so the ledger already detects most of them; "
      "no off-path TeaStore or Hotel episode exists.\n")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="NEW output directory (refused if it exists)")
    ap.add_argument("--rerender", help="rewrite only LANES.md of an existing output directory from its own lanes.json (the evidence json is untouched)")
    ap.add_argument("--from-json", help="re-render LANES.md from an earlier lanes.json (no raw stage); copies the json")
    a = ap.parse_args(argv)
    if a.rerender:
        d = Path(a.rerender)
        (d / "LANES.md").write_text(render_md(json.loads((d / "lanes.json").read_text())))
        return
    if not a.out:
        ap.error("--out is required")
    if a.from_json:
        out = Path(a.out)
        if out.exists():
            raise SystemExit("refusing to write into an existing path: %s" % out)
        R = json.loads(Path(a.from_json).read_text())
        out.mkdir(parents=True)
        (out / "lanes.json").write_text(json.dumps(R, indent=1, default=str))
        (out / "LANES.md").write_text(render_md(R))
        return
    build(Path(a.out))


if __name__ == "__main__":
    main()
