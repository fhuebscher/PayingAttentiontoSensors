#!/usr/bin/env python3
"""Time to detection and impact before detection, ledger vs every sensor, on retained evidence (protocol draft 3,
decision 14: per fault, detected or not, time to detection, impact before detection; traffic per route as a parameter).

Offline and read-only on evidence. Existing modules are imported by path and never edited: the sensor_rep parsers
(`research/protocol/sensor_rep/`, events and streams), `research/visibility-map/visibility.py` (ledger readers),
`research/hotel-selected/ledger_check.py` (through visibility), the project map's call graph.

    rm -rf ~/Library/Caches/com.apple.python/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/research
    /usr/bin/python3 -B research/detection-time/detection_time.py --self-check   # planted timelines + mutants
    /usr/bin/python3 -B research/detection-time/detection_time.py                # writes out/detection_time.json, DETECTION_TIME.md

Populations: hotel-lmt2, hotel-sel1, hotel-int1 (`tmp/hotel{lmt2,sel1,int1}-evidence/x`), teastore-T16
(`tmp/teastore16-evidence/x/teastore-candidate-pilot-v1`), otel-v3 (`tmp/otel-v3-evidence/runs`, ledger only).
Valid cells only. Populations are never pooled.

ONSET (F-ADH-085: bounded by the scheduled command, never by a probe):
  Hotel   fault-receipt `startedMonotonic` (stamped before `compose pause` / the degradation command); end = `revertingMonotonic`.
  TeaStore intervention `measurementBarrier.scheduledOnsetSeconds` / `scheduledOnsetWall` (the command is issued there;
          `actualOnset*` is a post-command `docker inspect`); end = `actualOffset*` (the hold-end sample, before recovery).
  OTel    intervention `actualOnsetMonotonicOffsetSeconds` (stamped before `compose pause frontend`; the copy retained
          with the evidence, tmp/otel-v3-evidence/.controller/candidate_remote.py:679-680); end = `actualOffsetMonotonicOffsetSeconds` (after `unpause` returned: an upper bound).
  The command's own duration (Hotel applied - started, TeaStore actualOnset - scheduled) is reported per episode: the fault
  takes effect somewhere inside it, so a time to detection measured from the command bound includes it.

ONLINE RULES (engineering defaults, recorded; the baseline is the cell's OWN pre-window [t0, onset), per sample / per
request, decision round 4 "ledger spread per request"; K = 4, scale 1.4826, floors as sensor_rep/catch.py):
  observation time = when the record becomes available: span start + duration, request end, log stamp, metric sample stamp.
  level channels (metric value; span duration of a non-error op; ledger ok latency per route):
    spike   first in-window sample beyond median ± max(K·1.4826·MAD, floor) of the pre-window samples (>= 3 needed);
            metrics both directions, spans and ledger up only. Counts only if its service is on the affected call path:
            a SERVICE-LEVEL APPROXIMATION of round 4, decision 7 (the target, a transitive caller or a transitive callee
            in the project map's call graph). Decision 7 asks for placement via the requests on that path; that was not
            done, and metric samples cannot be attributed to requests. Off-path spikes are kept in the output, never scored.
    run3    3 consecutive in-window samples of the stream beyond the threshold in one direction; time of the third.
    median  the window rule evaluated online: median of the in-window samples observed so far (>= 3) beyond the threshold.
  count channels (log template; span op, its `:error` companion included):
    appear  first in-window record of a token with 0 records in the pre-window.
    absent  silence: the stream had >= 5 pre-window records; fires at last record + 2 x the longest pre-window gap, if no record
            arrives first and that instant is inside the window (a stream already silent at onset gives no verdict).
            Not for `:error` tokens.
  ledger (one sensor per route, entry service; requests from visibility's readers):
    failed  first request observed in the window (end in [onset, end]) whose outcome is not ok;
    spike / run3 / median as above on ok latencies, per route baseline (ok requests that ended before onset);
    watchdog (secondary, not in E): the instant an in-flight request's age crosses the latency threshold, or a failed
            request's end, whichever is first: what a monitor tracking requests in flight could know.
  E (the ledger family) = min over its admissible rules failed, spike, run3, median.
  Log stamps with whole-second resolution (Hotel): a record stamped s lies in [s, s + 1); it is timed at s + 1 - onset (the
  instant it certainly existed; s - onset is kept as the interval's lower end), and it counts only if s + 1 <= hold end
  (else it straddles the hold end: listed per episode as `logStraddlesHoldEnd`, not a catch). A record stamped in the
  onset's second is in-window (sensor_rep/vectors.py floors the log window the same way): on this evidence 0 catches.
  Span observation time is the span END; Hotel's Jaeger reporter flushes every 1 s, so span-vs-ledger differences under
  1 s are not resolvable (detection counts are unaffected).
G3 per (population, posture, sensor, rule): the same rules on every no-fault window of hold length at offsets onset_med +
  i·hold (i >= 0, ending <= duration + 1 s) in every valid no-fault cell of the posture, each with its own pre-window
  [t0, window start). Admissible iff k <= TAU·n_eff (TAU = 0.05). n_eff = 0 -> not admissible (never reported as a catch).
  Family false-alarm rate: leave-one-no-fault-cell-out (admissibility from the other cells' windows), the class's filters
  applied (outside the class target, spikes on its path, BC as in the column), k/n windows and time to the first false alarm.
G2: a sensor of the target service is `own` and reported apart. On OTel the target is the entry (frontend), so the
  ledger is the target's own sensor there.
BY CONSTRUCTION (per episode and sensor-rule; MAP/isolability taxonomy plus round 4's BC-caller-log):
  BC-ledger-stopped-on-path  ledger, stopping fault (pause/stop), target on the driven route;
  BC-caller-span   span of another service whose op is one of the target's own span ops, stopping fault;
  BC-idle-cpu      `cpu` / `sys_cpu` firing downwards, stopping fault;
  BC-downstream-absent  `absent` on a span or log token, stopping fault;
  BC-caller-log    a warn/error/other-level log template of a DIRECT caller of the target (call-graph edge caller->target)
                   firing by `appear`, any fault kind (round 4, decision 2: "the caller is the service that logs").
                   Structural, not by message text; the templates it flags are listed in the report for checking.
IMPACT before detection: ledger requests STARTED in [onset, onset + time to detection] that failed or whose latency crossed
  the per-request threshold of their route (full-rate baseline). Undetected episodes: the hold's total, reported apart.
TRAFFIC (ledger side only): units (Hotel and OTel requests, TeaStore journeys) are kept with probability p (Bernoulli,
  primary; Poisson-like arrivals) or every round(1/p)-th from a random phase (periodic: what a slower open-loop schedule
  does), SEEDS seeds per (cell, p), seeded by (population, cell, p, seed). The ledger's baseline thins with it; a route
  whose baseline falls below 3 requests has no latency verdict (`?` share). The ledger rules admissible at full rate are
  kept; the thinned no-fault false-alarm rate is reported beside them. This is a bound on the ledger side only: thinning
  does not reproduce what the SUT would do at lower load (its state, queueing and every sensor's noise change with load,
  and sensors whose signal is load-driven, e.g. BC-idle-cpu, would weaken). Admissible ledger rules are re-derived by G3 at
  each thinning rate (per posture, route and rule, over the thinned no-fault trials). Analytic: with in-window bad-request
  share q, effect delay d (first bad request's start after the bound) and observation lag l, a Poisson stream of rate r
  needing m bad requests (1 for the failure rule, 3 for run3/median) misses within hold H with probability
  P(Poisson(r·q·(H - d - l)) < m) and its median time to detection is d + l + λ_m / (r·q), λ_1 = ln 2. A sensor with time
  t beats the ledger in median for r < λ_m / (q·(t - d - l)) (every rate if t <= d + l). It uses p·rate, not the
  periodic/discrete arrivals, so it is biased slightly late; not applied to TeaStore (journeys) or OTel (concurrency cap).
"""
import argparse
import bisect
import datetime as dt
import hashlib
import importlib.util
import json
import math
import platform
import random
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
REPO = RESEARCH.parent
OUT_JSON = HERE / "out" / "detection_time.json"
OUT_MD = HERE / "DETECTION_TIME.md"
sys.path.insert(0, str(RESEARCH / "protocol"))

K = 4.0
SCALE = 1.4826
TAU = 0.05
MIN_BASELINE = 3
RUN_N = 3
ABSENT_MIN = 5
ABSENT_GAP_MULT = 2.0
LEDGER_FLOOR_MS = 1.0
WINDOW_OVERRUN_S = 1.0
STOPPING = ("pause", "stop")
CPU_TOKENS = ("cpu", "sys_cpu")
CALLER_LOG_LEVELS = ("warn", "error", "other")
E_RULES = ("failed", "spike", "run3", "median")
LEDGER_RULES = E_RULES + ("watchdog",)
THIN_P = (1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001)
SEEDS = 200
HOTEL_POPS = ("hotel-lmt2", "hotel-sel1", "hotel-int1")
POPS = HOTEL_POPS + ("teastore-T16", "otel-v3")
ENTRY = {"hotel": "frontend", "teastore": "webui", "otel": "frontend"}
FAMILY_ORDER = ("E", "L", "M", "S", "Tsel", "T")
SAMPLED = ("M", "S")                     # families whose sampling cadence does not depend on requests
INCLUSIVE = True                         # comparator `>=` (symptoms.py); flipped only by a self-check mutant
PATH_FILTER = True                       # round 4: spikes count only on the affected call path; mutant flips it
G3_TAU = TAU                             # mutant sets it to 1.0 (k <= n)
LOG_UPPER = True                         # whole-second log stamp timed at s + 1; mutant times it at s
LOG_HOLD_CAP = True                      # a whole-second record counts only if s + 1 <= hold end; mutant drops the cap


# =========================================================================== pure logic (exercised by --self-check)

def robust(values):
    m = statistics.median(values)
    return m, statistics.median(abs(v - m) for v in values)


def threshold(values, floor, k=K):
    m, mad = robust(values)
    return m, max(k * SCALE * mad, floor)


def beyond(v, m, thr, d):
    x = (v - m) if d == "up" else (m - v)
    return x >= thr if INCLUSIVE else x > thr


def level_rules(obs, vals, m, thr, dirs):
    """obs/vals: the in-window samples sorted by observation time. {rule: (t, dir)} for spike, run3, median."""
    out, run, prefix = {}, {d: 0 for d in dirs}, []
    for t, v in zip(obs, vals):
        for d in dirs:
            if beyond(v, m, thr, d):
                out.setdefault("spike", (t, d))
                run[d] += 1
                if run[d] >= RUN_N:
                    out.setdefault("run3", (t, d))
            else:
                run[d] = 0
        bisect.insort(prefix, v)
        if "median" not in out and len(prefix) >= MIN_BASELINE:
            pm = statistics.median(prefix)
            for d in dirs:
                if beyond(pm, m, thr, d):
                    out["median"] = (t, d)
                    break
        if len(out) == 3:
            break
    return out


def count_rules(pre, win, a, b, error_token=False):
    """pre: observation times in [t0, a); win: in [a, b] (sorted). {rule: (t, None)} for appear, absent."""
    out = {}
    if not pre and win:
        out["appear"] = (win[0], None)
    if not error_token and len(pre) >= ABSENT_MIN:
        g = ABSENT_GAP_MULT * max(y - x for x, y in zip(pre, pre[1:]))
        last = pre[-1]
        if g > 0 and last + g >= a:
            for t in win + [math.inf]:
                if t - last > g:
                    if last + g <= b:
                        out["absent"] = (last + g, None)
                    break
                last = t
    return out


def route_baselines(reqs, a, k=K):
    """reqs: (start, end, ok, route, unit). Per route (median, thr) from ok requests that ended before a (>= 3)."""
    base = defaultdict(list)
    for r in reqs:
        if r[1] < a and r[2]:
            base[r[3]].append((r[1] - r[0]) * 1000.0)
    return {route: threshold(v, LEDGER_FLOOR_MS, k) for route, v in base.items() if len(v) >= MIN_BASELINE}


def ledger_rules(reqs, a, b, k=K, rules=LEDGER_RULES, base=None):
    """First observation per (route, rule) inside [a, b]. reqs sorted by end. Returns ({(route, rule): t}, thresholds,
    routes with in-window requests but no latency baseline)."""
    if base is None:
        base = route_baselines(reqs, a, k)
    out, run, prefix, unknown = {}, Counter(), defaultdict(list), set()
    ends = [r[1] for r in reqs]
    for r in reqs[bisect.bisect_left(ends, a):bisect.bisect_right(ends, b)]:
        s, e, ok, route = r[0], r[1], r[2], r[3]
        if not ok:
            if "failed" in rules:
                out.setdefault((route, "failed"), e)
            continue
        if route not in base:
            unknown.add(route)
            continue
        m, thr = base[route]
        lat = (e - s) * 1000.0
        if beyond(lat, m, thr, "up"):
            if "spike" in rules:
                out.setdefault((route, "spike"), e)
            run[route] += 1
            if run[route] >= RUN_N and "run3" in rules:
                out.setdefault((route, "run3"), e)
        else:
            run[route] = 0
        if "median" in rules and (route, "median") not in out:
            bisect.insort(prefix[route], lat)
            if len(prefix[route]) >= MIN_BASELINE and beyond(statistics.median(prefix[route]), m, thr, "up"):
                out[(route, "median")] = e
    if "watchdog" in rules:
        for r in reqs:
            s, e, ok, route = r[0], r[1], r[2], r[3]
            if s > b:
                continue
            c = []
            if not ok and a <= e <= b:
                c.append(e)
            if route in base:
                m, thr = base[route]
                if (e - s) * 1000.0 >= m + thr:
                    x = s + (m + thr) / 1000.0
                    if a <= x <= b:
                        c.append(x)
            if c:
                key = (route, "watchdog")
                out[key] = min(out.get(key, math.inf), min(c))
    return out, base, unknown


def log_ttd(t, a, whole_second, b=None):
    """(lower, conservative) time to detection of a log record stamped t for onset a, or None when the record is not
    certainly inside the hold [a, b]. A whole-second stamp bounds the record to [t, t + 1): it is timed at t + 1 (the
    instant it certainly existed; the lower end is kept for the interval), and it counts only if t + 1 <= b (a record
    stamped in the hold's last second straddles the hold end: `?`, not a catch)."""
    if whole_second:
        hi = t + 1.0 - a if LOG_UPPER else max(0.0, t - a)
        if LOG_HOLD_CAP and b is not None and t + 1.0 > b:
            return None
        return max(0.0, t - a), hi
    return max(0.0, t - a), max(0.0, t - a)


def bad_request(r, base):
    if not r[2]:
        return True
    if r[3] not in base:
        return False
    m, thr = base[r[3]]
    return beyond((r[1] - r[0]) * 1000.0, m, thr, "up")


def impact(reqs, base, a, t_detect):
    """Requests started in [a, t_detect] that failed or crossed their route's per-request threshold."""
    return sum(1 for r in reqs if a <= r[0] <= t_detect and bad_request(r, base))


def admissible(k, n, tau=None):
    tau = G3_TAU if tau is None else tau
    return bool(n) and k <= tau * n


def affected_path(target, edges):
    """target + its transitive callers + its transitive callees (call-graph edges caller -> callee)."""
    up, down = defaultdict(set), defaultdict(set)
    for x, y in edges:
        down[x].add(y)
        up[y].add(x)
    out = {target}
    for g in (up, down):
        stack = [target]
        while stack:
            for n in g[stack.pop()]:
                if n not in out:
                    out.add(n)
                    stack.append(n)
    return out


def bc_flags(f, target, kind, ctx):
    """f: a fire dict (ch, svc, tok, rule, dir, level). ctx: onRoute, ops {service: span op tokens}, edges."""
    flags = []
    stop = kind in STOPPING
    ch, svc, tok, rule = f["ch"], f["svc"], f["tok"], f["rule"]
    if ch == "ledger" and stop and target in ctx["onRoute"]:
        flags.append("BC-ledger-stopped-on-path")
    if ch == "span" and stop and svc != target and tok.split(":error")[0] in ctx["ops"].get(target, ()):
        flags.append("BC-caller-span")
    if ch == "metric" and stop and tok in CPU_TOKENS and f.get("dir") == "down":
        flags.append("BC-idle-cpu")
    if ch in ("span", "log") and stop and rule == "absent":
        flags.append("BC-downstream-absent")
    if ch == "log" and rule == "appear" and f.get("level") in CALLER_LOG_LEVELS and (svc, target) in ctx["edges"]:
        flags.append("BC-caller-log")
    return flags


def scored(f, target, path, entry):
    """(counts?, own?) under G2 and the spike path rule."""
    own = (entry if f["ch"] == "ledger" else f["svc"]) == target
    if f["rule"] == "spike" and PATH_FILTER and f["ch"] != "ledger" and f["svc"] not in path:
        return False, own
    return True, own


def thin_units(n_units, p, seed, mode):
    """Kept unit indices (sorted)."""
    if p >= 1.0:
        return list(range(n_units))
    rng = random.Random(seed)
    if mode == "periodic":
        m = max(1, int(round(1.0 / p)))
        return list(range(rng.randrange(m), n_units, m))
    out, i, lq = [], -1, math.log(1.0 - p)
    while True:
        i += int(math.log(1.0 - rng.random()) / lq) + 1
        if i >= n_units:
            return out
        out.append(i)


def poisson_ge(lam, m):
    """P(Poisson(lam) >= m)."""
    if lam <= 0:
        return 0.0 if m > 0 else 1.0
    term, cdf = math.exp(-lam), 0.0
    for i in range(m):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def lam_median(m):
    """lam with P(Poisson(lam) >= m) = 0.5 (ln 2 for m = 1)."""
    lo, hi = 0.0, 10.0 + 2 * m
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if poisson_ge(mid, m) < 0.5 else (lo, mid)
    return (lo + hi) / 2


def analytic(q, lag, hold, rate, m=1, delay=0.0):
    """Poisson ledger needing m bad requests (failure or spike: 1; run3 / median: 3), bad share q after an effect delay,
    observation lag: (P(miss within hold), median time to detection or None if beyond the hold)."""
    if q <= 0 or rate <= 0:
        return 1.0, None
    eff = max(hold - delay - lag, 0.0)
    miss = 1.0 - poisson_ge(rate * q * eff, m)
    med = delay + lag + lam_median(m) / (rate * q)
    return miss, (med if med <= hold else None)


def crossover_rate(q, lag, t_sensor, m=1, delay=0.0):
    """Ledger rate below which a sensor with time to detection t_sensor beats the ledger's median (analytic)."""
    if t_sensor is None or q <= 0:
        return None
    if t_sensor <= delay + lag:
        return math.inf
    return lam_median(m) / (q * (t_sensor - delay - lag))


def dist(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"n": len(xs), "min": xs[0], "q25": q[0], "median": statistics.median(xs), "q75": q[2], "max": xs[-1]}


# =========================================================================== evidence loading

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_V = None


def visibility():
    global _V
    if _V is None:
        _V = _load("dt_visibility", RESEARCH / "visibility-map" / "visibility.py")
    return _V


def epoch(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def call_graph(sut):
    pm = json.loads((RESEARCH / "project-map" / "project_map.json").read_text())["suts"][sut]["callGraph"]
    edges = {tuple(e.split("->")) for e in pm["edges"]}
    return edges, set(pm["onRoute"])


def hotel_ledger(attempt, route):
    rows = visibility().hotel_ledger_rows(Path(attempt))
    reqs = [(s, s + ms / 1000.0, ok, route, i) for i, (s, ms, ok) in enumerate(sorted(rows))]
    return sorted(reqs, key=lambda r: r[1]), len(reqs)


def teastore_ledger(d):
    """visibility.teastore_ledger_rows with the journey index kept (the thinning unit); checked equal to it."""
    reqs = []
    lines = [json.loads(x) for x in (Path(d) / "journey-ledger.jsonl").open()]
    for j, r in enumerate(lines):
        for q in r.get("requests") or []:
            s = q["actualStartMonotonic"]
            reqs.append((s, q["actualEndMonotonic"], q["outcome"] == "succeeded" and q["statusCode"] == 200,
                         q.get("routeId", "?"), j))
    theirs = visibility().teastore_ledger_rows(Path(d))[0]
    mine = sorted((s, (e - s) * 1000.0, ok) for s, e, ok, _, _ in reqs)
    assert mine == sorted(theirs), "TeaStore ledger reader differs from visibility.teastore_ledger_rows: %s" % d
    return sorted(reqs, key=lambda r: r[1]), len(lines)


def prep_streams(cell):
    P = {}
    for (ch, svc, tok), s in cell["streams"].items():
        if ch == "ledger":
            continue
        pairs = sorted(zip((t + v for t, v in zip(s.t, s.v)), s.v)) if ch == "span" else list(zip(s.t, s.v))
        pairs = [p for p in pairs if p[1] is not None]
        P[(ch, svc, tok)] = ([p[0] for p in pairs], [p[1] for p in pairs], s.meta)
    return P


def load_sensor_population(name):
    from sensor_rep import population, run as srun
    population.register_late()
    cfg = population.POPULATIONS[name]
    P = population.parser(cfg["sut"])
    cells = [c for c in population.load(name) if c["valid"]]
    out = []
    for c in cells:
        d = REPO / c["cell"]
        c["chans"] = srun.collected_channels(cfg, c)
        c["prep"] = prep_streams(c)
        c.pop("streams")
        bw, bm = c["base"]["wall"], c["base"]["mono"]
        if cfg["sut"] == "hotel":
            plan = json.loads((d / "opportunity-plan.json").read_text())
            c["ledger"], c["units"] = hotel_ledger(d, plan.get("workloadId", "?"))
            c["t0"] = {"wall": bw, "mono": None}
            if c["target"]:
                r = json.loads((d / "fault-receipt.json").read_text())
                a, b = float(r["startedMonotonic"]), float(r["revertingMonotonic"])
                c["cmd"] = {"A": {"mono": a, "wall": bw + a - bm}, "B": {"mono": b, "wall": bw + b - bm},
                            "commandSeconds": float(r["appliedMonotonic"]) - a, "onsetSource": "fault-receipt startedMonotonic"}
        else:
            c["ledger"], c["units"] = teastore_ledger(d)
            c["t0"] = {"wall": c["t0"]["wall"], "mono": None}
            if c["target"]:
                iv = json.loads((d / "intervention.json").read_text())
                mb = iv["measurementBarrier"]
                a_m, a_w = float(mb["scheduledOnsetSeconds"]), epoch(mb["scheduledOnsetWall"])
                c["cmd"] = {"A": {"mono": a_m, "wall": a_w},
                            "B": {"mono": float(iv["actualOffsetMonotonicOffsetSeconds"]), "wall": epoch(iv["actualOffsetWall"])},
                            "commandSeconds": float(iv["actualOnsetMonotonicOffsetSeconds"]) - a_m,
                            "onsetSource": "intervention measurementBarrier.scheduledOnset*"}
        c["family"] = lambda ch, coll, posture, _P=P: _P.family(ch, coll, posture)
        c["channelsPresent"] = {k: bool(v.get("present")) for k, v in c["channels"].items()}
        out.append(c)
    return cfg["sut"], cfg["x"], out, cfg["collects"]


def load_otel():
    V = visibility()
    root = REPO / "tmp" / "otel-v3-evidence"
    out = []
    for d in sorted(root.glob("runs/*/*")):
        if not (d / "receipt.json").exists():
            continue
        rc = json.loads((d / "receipt.json").read_text())
        if rc.get("state") != "valid":
            continue
        rk = rc["runKey"]
        base, rows = V.otel_ledger_rows(d)
        led = json.loads((d / "request-ledger.json").read_text())
        reqs = sorted(((s, s + ms / 1000.0, ok, "recommendations", i) for i, (s, ms, ok) in enumerate(rows)),
                      key=lambda r: r[1])
        ivp = d / "intervention.json"
        iv = json.loads(ivp.read_text()) if ivp.exists() else None
        c = {"sut": "otel", "population": "otel-v3", "cell": d.relative_to(REPO).as_posix(), "posture": rk["posture"],
             "regime": rk["regime"], "block": rk["block"], "valid": True, "target": iv["service"] if iv else None,
             "faultKind": "pause" if iv else None, "base": {"mono": 0.0, "wall": base}, "t0": {"mono": None, "wall": base},
             "duration": led["endedAtEpoch"] - base, "chans": {"ledger"}, "prep": {}, "ledger": reqs, "units": len(reqs),
             "family": lambda *a: None, "channelsPresent": {"ledger": True}}
        if iv:
            a, b = float(iv["actualOnsetMonotonicOffsetSeconds"]), float(iv["actualOffsetMonotonicOffsetSeconds"])
            c["cmd"] = {"A": {"mono": a, "wall": base + a}, "B": {"mono": b, "wall": base + b}, "commandSeconds": None,
                        "onsetSource": "intervention actualOnsetMonotonicOffsetSeconds (pre-command stamp)"}
        out.append(c)
    return "otel", "tmp/otel-v3-evidence/runs", out, {}


# =========================================================================== evaluation of one window

def whole_second_logs(cells):
    n = tot = 0
    for c in cells:
        for (ch, _, _), (obs, _, _) in c["prep"].items():
            if ch == "log":
                tot += len(obs)
                n += sum(1 for t in obs if t == int(t))
    return tot > 0 and n == tot, (n, tot)


def eval_window(c, A, B, ws_logs):
    """Every sensor-rule's first observation in [A, B] (per clock). Returns list of fire dicts (ttd = t - A >= 0)."""
    from sensor_rep import catch
    fires, straddle = [], []
    t0 = c["t0"]
    for (ch, svc, tok), (obs, vals, meta) in c["prep"].items():
        if ch not in c["chans"]:
            continue
        clk = meta["clock"]
        a, b = A[clk], B[clk]
        a_in = math.floor(a) if (ch == "log" and ws_logs) else a
        lo = 0 if t0.get(clk) is None else bisect.bisect_left(obs, t0[clk])
        ia, ib = bisect.bisect_left(obs, a_in), bisect.bisect_right(obs, b)
        got = {}
        if ch in ("log", "span"):
            got.update(count_rules(obs[lo:ia], obs[ia:ib], a_in, b, tok.endswith(":error")))
        if ch == "metric" or (ch == "span" and not tok.endswith(":error")):
            pre = vals[lo:ia]
            if len(pre) >= MIN_BASELINE and ib > ia:
                m, thr = threshold(pre, catch.level_floor(ch, tok, statistics.median(pre)))
                got.update(level_rules(obs[ia:ib], vals[ia:ib], m, thr, ("up", "down") if ch == "metric" else ("up",)))
        for rule, (t, d) in got.items():
            if ch == "log":
                lt = log_ttd(t, a, ws_logs, b)
                if lt is None:
                    straddle.append((ch, svc, tok, rule))
                    continue
                lo, ttd = lt
            else:
                lo, ttd = max(0.0, t - a), max(0.0, t - a)
            fires.append({"ch": ch, "svc": svc, "tok": tok, "rule": rule, "ttd": ttd, "ttdLo": lo, "dir": d,
                          "level": meta.get("level"), "family": c["family"](ch, meta.get("collector"), c["posture"])})
    entry = ENTRY[c["sut"]]
    led, base, unknown = ledger_rules(c["ledger"], A["mono"], B["mono"])
    for (route, rule), t in led.items():
        fires.append({"ch": "ledger", "svc": entry, "tok": route, "rule": rule, "ttd": max(0.0, t - A["mono"]),
                      "dir": "up", "level": None, "family": "E"})
    c["_straddle"] = straddle
    return fires, base, sorted(unknown)


def fkey(f):
    return (f["ch"], f["svc"], f["tok"], f["rule"])


def nofault_windows(cells, onset_off, hold):
    out = []
    for c in cells:
        if c["target"] is not None:
            continue
        i = 0
        while onset_off + (i + 1) * hold <= c["duration"] + WINDOW_OVERRUN_S:
            lo, hi = onset_off + i * hold, onset_off + (i + 1) * hold
            out.append((c, i, {k: c["base"][k] + lo for k in c["base"]}, {k: c["base"][k] + hi for k in c["base"]}))
            i += 1
    return out


# =========================================================================== one population

def run_population(name):
    if name == "otel-v3":
        sut, x, cells, table = load_otel()
    else:
        sut, x, cells, table = load_sensor_population(name)
    entry = ENTRY[sut]
    edges, on_route = call_graph(sut)
    ops = defaultdict(set)
    for c in cells:
        for (ch, svc, tok) in c["prep"]:
            if ch == "span":
                ops[svc].add(tok.split(":error")[0])
    ctx = {"edges": edges, "onRoute": on_route, "ops": ops}
    ws_logs, ws_counts = whole_second_logs(cells)
    faults = [c for c in cells if c["target"]]
    onset_off = statistics.median(c["cmd"]["A"]["mono"] - c["base"]["mono"] for c in faults)
    hold = statistics.median(c["cmd"]["B"]["mono"] - c["cmd"]["A"]["mono"] for c in faults)
    classes = {}
    for c in faults:
        classes.setdefault(c["regime"], {"target": c["target"], "faultKind": c["faultKind"]})
    # ---- timed records per (posture, channel) in the no-fault cells' windows: 0 means G3 cannot test that channel
    nf_records = defaultdict(Counter)
    # ---- no-fault windows and G3
    nfw = nofault_windows(cells, onset_off, hold)
    for c, i, A, B in nfw:
        for (ch, _, _), (obs, _, meta) in c["prep"].items():
            if ch in c["chans"]:
                lo_, hi_ = A[meta["clock"]], B[meta["clock"]]
                nf_records[c["posture"]][ch] += sum(1 for t in obs if lo_ <= t <= hi_)
    nf_fires = []
    for c, i, A, B in nfw:
        fires, _, _ = eval_window(c, A, B, ws_logs)
        nf_fires.append({"cell": c["cell"], "posture": c["posture"], "index": i, "fires": fires,
                         "A": A, "B": B, "c": c})
    g3 = defaultdict(Counter)              # posture -> key -> k
    g3_cell = defaultdict(Counter)         # (posture, cell) -> key -> k
    n_win, n_win_cell = Counter(), Counter()
    for w in nf_fires:
        n_win[w["posture"]] += 1
        n_win_cell[(w["posture"], w["cell"])] += 1
        for f in w["fires"]:
            g3[w["posture"]][fkey(f)] += 1
            g3_cell[(w["posture"], w["cell"])][fkey(f)] += 1
    # ---- fault episodes
    episodes = []
    for c in faults:
        A, B = c["cmd"]["A"], c["cmd"]["B"]
        fires, base, unknown = eval_window(c, A, B, ws_logs)
        straddle = ["%s:%s:%s/%s" % x for x in c.pop("_straddle", [])]
        cls = classes[c["regime"]]
        path = affected_path(c["target"], edges) if c["target"] in on_route else {c["target"]}
        n = n_win[c["posture"]]
        kept = []
        for f in fires:
            k = g3[c["posture"]][fkey(f)]
            counts, own = scored(f, c["target"], path, entry)
            f.update({"g3k": k, "g3n": n, "admissible": admissible(k, n), "own": own, "onPath": f["svc"] in path,
                      "counts": counts, "bc": bc_flags(f, c["target"], c["faultKind"], ctx)})
            kept.append(f)
        hold_c = B["mono"] - A["mono"]
        reqs_in = [r for r in c["ledger"] if A["mono"] <= r[0] <= B["mono"]]
        bad = [r for r in reqs_in if bad_request(r, base)]
        lags = [r[1] - r[0] for r in bad]
        episodes.append({"cell": c["cell"], "regime": c["regime"], "target": c["target"], "faultKind": c["faultKind"],
                         "posture": c["posture"], "block": c["block"], "onset": A, "end": B, "holdSeconds": hold_c,
                         "commandSeconds": c["cmd"]["commandSeconds"], "onsetSource": c["cmd"]["onsetSource"],
                         "affectedPath": sorted(path), "fires": kept, "logStraddlesHoldEnd": straddle, "ledgerBaseline": {k: list(v) for k, v in base.items()},
                         "ledgerRoutesWithoutBaseline": unknown, "requestsStartedInHold": len(reqs_in),
                         "badRequestsInHold": len(bad), "q": (len(bad) / len(reqs_in)) if reqs_in else None,
                         "qFailed": (sum(1 for r in reqs_in if not r[2]) / len(reqs_in)) if reqs_in else None,
                         "effectDelaySeconds": (min(r[0] for r in bad) - A["mono"]) if bad else None,
                         "lagSeconds": statistics.median(lags) if lags else None, "_c": c})
    return {"name": name, "sut": sut, "evidence": x, "entry": entry, "edges": sorted("%s->%s" % e for e in edges),
            "onRoute": sorted(on_route), "wholeSecondLogs": ws_logs, "logStampsIntegral": ws_counts,
            "onsetOffsetSeconds": onset_off, "holdSeconds": hold, "classes": classes, "episodes": episodes,
            "nofault": nf_fires, "nWin": dict(n_win), "collectsTable": table, "nfRecords": nf_records, "nWinCell": n_win_cell, "g3": g3, "g3Cell": g3_cell,
            "cells": cells, "ctx": ctx}


# =========================================================================== aggregation

def family_ttd(ep, fam, own=False, bc=True, rules=None):
    best = None
    for f in ep["fires"]:
        if f["family"] != fam or not f["admissible"] or not f["counts"] or f["own"] != own:
            continue
        if fam == "E" and f["rule"] not in (rules or E_RULES):
            continue
        if not bc and f["bc"]:
            continue
        if best is None or f["ttd"] < best["ttd"]:
            best = f
    return best


FAMILY_CHANNEL = {"L": ("log", None), "M": ("metric", "metric:docker-stats"), "S": ("metric", "metric:cgroup-sampler"),
                  "T": ("span", None), "Tsel": ("span", None)}


def collects(ep, fam, P):
    """The posture collects the family (population posture table) and the cell retained its channel file."""
    c = ep["_c"]
    if fam == "E":
        return True
    table = P.get("collectsTable") or {}
    if c["posture"] not in table.get(fam, ()):
        return False
    ch, chkey = FAMILY_CHANNEL[fam]
    return ch in c["chans"] and (chkey is None or c["channelsPresent"].get(chkey, False))


def false_alarms(P, cls, posture, fam, own=False, bc=True):
    """Leave-one-no-fault-cell-out family false-alarm rate with the class's filters."""
    target, kind = cls["target"], cls["faultKind"]
    path = affected_path(target, P["ctx"]["edges"]) if target in P["ctx"]["onRoute"] else {target}
    n_tot = P["nWin"].get(posture, 0)
    fired, times, n = 0, [], 0
    for w in P["nofault"]:
        if w["posture"] != posture:
            continue
        n += 1
        n_other = n_tot - P["nWinCell"][(posture, w["cell"])]
        mine = P["g3Cell"][(posture, w["cell"])]
        first = None
        for f in w["fires"]:
            if f["family"] != fam or (fam == "E" and f["rule"] not in E_RULES):
                continue
            k_other = P["g3"][posture][fkey(f)] - mine[fkey(f)]
            if not admissible(k_other, n_other):
                continue
            counts, is_own = scored(f, target, path, P["entry"])
            if not counts or is_own != own:
                continue
            if not bc and bc_flags(f, target, kind, P["ctx"]):
                continue
            first = f["ttd"] if first is None else min(first, f["ttd"])
        if first is not None:
            fired += 1
            times.append(first)
    return {"k": fired, "n": n, "timeToFirstFalseAlarm": dist(times)}


def postures_of(P):
    order = ("none", "logs", "metrics", "selected", "async", "full")
    ps = sorted({e["posture"] for e in P["episodes"]}, key=lambda p: order.index(p) if p in order else 99)
    return ps


def ttd_table(P, bc=True):
    rows = []
    for regime, cls in sorted(P["classes"].items()):
        for posture in postures_of(P):
            eps = [e for e in P["episodes"] if e["regime"] == regime and e["posture"] == posture]
            row = {"regime": regime, "target": cls["target"], "faultKind": cls["faultKind"], "posture": posture,
                   "n": len(eps), "families": {}}
            for fam in FAMILY_ORDER:
                ev = [e for e in eps if collects(e, fam, P)]
                if not ev:
                    continue
                for own in (False, True):
                    hits = [family_ttd(e, fam, own=own, bc=bc) for e in ev]
                    t = [h["ttd"] for h in hits if h]
                    key = fam + (":own" if own else "")
                    pen = statistics.mean(h["ttd"] if h else e["holdSeconds"] for h, e in zip(hits, ev))
                    ch = FAMILY_CHANNEL.get(fam, ("ledger", None))[0]
                    testable = fam == "E" or P["nfRecords"][posture][ch] > 0
                    row["families"][key] = {"k": len(t), "n": len(ev), "ttd": dist(t), "penalisedMeanTtd": pen,
                                            "g3Testable": testable,
                                            "falseAlarms": (false_alarms(P, cls, posture, fam, own=own, bc=bc) if testable
                                                            else {"k": None, "n": 0, "timeToFirstFalseAlarm": None,
                                                                  "untestable": "no timed %s record in any no-fault window" % ch}),
                                            "rules": dict(Counter(h["rule"] for h in hits if h)),
                                            "bcFlags": dict(Counter(fl for h in hits if h for fl in h["bc"]))}
            rows.append(row)
    return rows


def ledger_rule_table(P):
    """Per (class, posture, rule): detections over episodes using the rule on any ADMISSIBLE route, and G3 per route."""
    rows = []
    for regime in sorted(P["classes"]):
        for posture in postures_of(P):
            eps = [e for e in P["episodes"] if e["regime"] == regime and e["posture"] == posture]
            r = {"regime": regime, "posture": posture, "n": len(eps), "rules": {}}
            n = P["nWin"].get(posture, 0)
            routes = sorted({x[3] for e in eps for x in e["_c"]["ledger"]})
            for rule in LEDGER_RULES:
                t_any, t_adm = [], []
                for e in eps:
                    h = [f for f in e["fires"] if f["ch"] == "ledger" and f["rule"] == rule]
                    if h:
                        t_any.append(min(x["ttd"] for x in h))
                    ha = [f for f in h if f["admissible"]]
                    if ha:
                        t_adm.append(min(x["ttd"] for x in ha))
                g3 = {route: [P["g3"][posture][("ledger", P["entry"], route, rule)], n] for route in routes}
                r["rules"][rule] = {"kAny": len(t_any), "ttdAny": dist(t_any), "k": len(t_adm), "ttd": dist(t_adm),
                                    "g3PerRoute": g3,
                                    "admissibleRoutes": [x for x, (k, nn) in g3.items() if admissible(k, nn)]}
            r["routes"] = routes
            rows.append(r)
    return rows


def impact_table(P):
    rows = []
    for regime in sorted(P["classes"]):
        eps = [e for e in P["episodes"] if e["regime"] == regime]
        row = {"regime": regime, "n": len(eps),
               "holdBad": dist([e["badRequestsInHold"] for e in eps]),
               "holdRequests": dist([e["requestsStartedInHold"] for e in eps]), "families": {}}
        for fam in FAMILY_ORDER:
            for own in (False, True):
                for bc in (True, False):
                    ev = [e for e in eps if collects(e, fam, P)]
                    if not ev:
                        continue
                    det, und = [], []
                    for e in ev:
                        h = family_ttd(e, fam, own=own, bc=bc)
                        c = e["_c"]
                        base = {k: tuple(v) for k, v in e["ledgerBaseline"].items()}
                        if h:
                            det.append(impact(c["ledger"], base, e["onset"]["mono"],
                                              min(e["onset"]["mono"] + h["ttd"], e["end"]["mono"])))
                        else:
                            und.append(e["badRequestsInHold"])
                    key = fam + (":own" if own else "") + ("" if bc else ":noBC")
                    row["families"][key] = {"n": len(ev), "detected": len(det), "impactBeforeDetection": dist(det),
                                            "undetectedHoldBad": dist(und)}
        rows.append(row)
    return rows


def base_rate(P):
    """(units per second, requests per second, unit name) over the valid cells' measurement."""
    cells = P["cells"]
    dur = sum(c["duration"] for c in cells)
    units = sum(c["units"] for c in cells)
    reqs = sum(len(c["ledger"]) for c in cells)
    return units / dur, reqs / dur, ("journey" if P["sut"] == "teastore" else "request")


def thinned_fires(c, A, B, p, seed, mode, unit_of=4):
    kept_units = set(thin_units(c["units"], p, seed, mode))
    reqs = [r for r in c["ledger"] if r[unit_of] in kept_units]
    out, _, unknown = ledger_rules(reqs, A, B, rules=E_RULES)
    return {k: t - A for k, t in out.items()}, bool(unknown)


def first_of(fires, keys, failed_only=False):
    ts = [t for k, t in fires.items() if k in keys and (not failed_only or k[1] == "failed")]
    return min(ts) if ts else None


def seed_of(*parts):
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def ledger_adm_keys(P, c, posture):
    """(route, rule) of the E rules admissible at full rate in this posture."""
    n = P["nWin"].get(posture, 0)
    return {(route, rule) for route in {r[3] for r in c["ledger"]} for rule in E_RULES
            if admissible(P["g3"][posture][("ledger", P["entry"], route, rule)], n)}


def traffic(P):
    """Ledger thinning per class, plus crossover against the sampled families (and logs)."""
    unit_rate, req_rate, unit = base_rate(P)
    out = {"baseUnitRate": unit_rate, "baseRequestRate": req_rate, "unit": unit, "seeds": SEEDS, "p": list(THIN_P),
           "noFaultFalseAlarms": {}, "classes": {}}
    # thinned no-fault windows, once per (mode, p): G3 is re-derived at each rate per (posture, route, rule) over the
    # (window x seed) trials, and the rules admissible AT THAT RATE are used for the fault episodes; the family
    # false-alarm count printed beside them is in-sample (the same trials decided admissibility), so it is a lower value
    nf_cache, adm_at = {}, {}
    for mode in ("bernoulli", "periodic"):
        out["noFaultFalseAlarms"][mode] = []
        for p in THIN_P:
            seeds = 1 if p >= 1.0 else SEEDS
            kk, nn = defaultdict(Counter), Counter()
            trials = []
            for w in P["nofault"]:
                c = w["c"]
                for sd in range(seeds):
                    f, _ = thinned_fires(c, w["A"]["mono"], w["B"]["mono"], p, seed_of(P["name"], c["cell"], p, sd, mode), mode)
                    nn[w["posture"]] += 1
                    for key in f:
                        kk[w["posture"]][key] += 1
                    trials.append((w["posture"], f))
            adm = {}
            for posture in nn:
                routes = {r[3] for c in P["cells"] if c["posture"] == posture for r in c["ledger"]}
                adm[posture] = {(rt, ru) for rt in routes for ru in E_RULES if admissible(kk[posture][(rt, ru)], nn[posture])}
            adm_at[(mode, p)] = adm
            k = sum(1 for posture, f in trials if first_of(f, adm[posture]) is not None)
            kf = sum(1 for posture, f in trials if first_of(f, adm[posture], True) is not None)
            out["noFaultFalseAlarms"][mode].append({"p": p, "k": k, "kFailedOnly": kf, "n": len(trials),
                                                    "admissible": {po: sorted("%s/%s" % x for x in v) for po, v in adm.items()}})
    for regime, cls in sorted(P["classes"].items()):
        eps = [e for e in P["episodes"] if e["regime"] == regime]
        res = {}
        for mode in ("bernoulli", "periodic"):
            res[mode] = []
            for pi, p in enumerate(THIN_P):
                seeds = 1 if p >= 1.0 else SEEDS
                det = miss = unk = 0
                ttds, per_ep, per_ep_f = [], [], []
                for e in eps:
                    c = e["_c"]
                    adm = adm_at[(mode, p)].get(e["posture"], set())
                    ep_t, ep_f = [], []
                    for sd in range(seeds):
                        f, u = thinned_fires(c, e["onset"]["mono"], e["end"]["mono"], p,
                                             seed_of(P["name"], c["cell"], p, sd, mode), mode)
                        t, tf = first_of(f, adm), first_of(f, adm, True)
                        ep_t.append(t)
                        ep_f.append(tf)
                        if t is not None:
                            det += 1
                            ttds.append(t)
                        elif u:
                            unk += 1
                        else:
                            miss += 1
                    per_ep.append(ep_t)
                    per_ep_f.append(ep_f)
                tot = det + miss + unk
                f_all = [t for ep_f in per_ep_f for t in ep_f]
                f_det = [t for t in f_all if t is not None]
                f_pen = statistics.mean(t if t is not None else e["holdSeconds"] for e, ep_f in zip(eps, per_ep_f) for t in ep_f)
                f_med = statistics.median([t for t in f_det] + [math.inf] * (len(f_all) - len(f_det))) if f_all else None
                pen = statistics.mean(t if t is not None else e["holdSeconds"] for e, ep_t in zip(eps, per_ep) for t in ep_t)
                all_t = sorted([t for t in ttds] + [math.inf] * (tot - det))
                med_all = statistics.median(all_t) if all_t else None
                fa = out["noFaultFalseAlarms"][mode][pi]
                res[mode].append({"p": p, "unitRate": p * unit_rate, "requestRate": p * req_rate, "trials": tot,
                                  "detected": det, "missed": miss, "unknown": unk,
                                  "missShare": (miss / tot) if tot else None, "unknownShare": (unk / tot) if tot else None,
                                  "ttdDetected": dist(ttds), "penalisedMeanTtd": pen,
                                  "medianTtdAllTrials": None if med_all is None or math.isinf(med_all) else med_all,
                                  "noFaultFalseAlarms": [fa["k"], fa["n"]], "_perEpisode": per_ep,
                                  "failedOnly": {"missShare": (len(f_all) - len(f_det)) / len(f_all) if f_all else None,
                                                 "penalisedMeanTtd": f_pen,
                                                 "medianTtdAllTrials": None if f_med is None or math.isinf(f_med) else f_med,
                                                 "noFaultFalseAlarms": [fa["kFailedOnly"], fa["n"]]}})
        # analytic (per request; TeaStore requests arrive in journeys, so the Poisson-per-request model is rough there)
        qf = statistics.median(e["qFailed"] for e in eps if e["qFailed"] is not None)
        qall = statistics.median(e["q"] for e in eps if e["q"] is not None)
        # model: failures need 1 request (the failed rule); latency-only classes need RUN_N (run3 / median), because
        # the single-request spike rule is G3-inadmissible wherever it was tested (ledger rule table)
        model_m, q = (1, qf) if qf > 0 else (RUN_N, qall)
        # the Poisson model treats bad requests as independent arrivals: valid for the failure rule (m = 1) and for a
        # shift that makes nearly every request bad (run3 then needs any 3 kept requests); not for scattered crossings,
        # and not for TeaStore, whose requests arrive in journeys (the thinning unit)
        applicable = unit == "request" and (model_m == 1 or q >= 0.9) and P["sut"] != "otel"
        # OTel: the generator caps concurrency at 8 with a 15 s timeout, so starts stall during the pause (85 of ~155
        # scheduled start in the hold); thinning that record is not a lower offered rate, and the model does not apply
        lags = [e["lagSeconds"] for e in eps if e["lagSeconds"] is not None]
        lag = statistics.median(lags) if lags else 0.0
        dl = [e["effectDelaySeconds"] for e in eps if e["effectDelaySeconds"] is not None]
        delay = statistics.median(dl) if dl else 0.0
        H = statistics.median(e["holdSeconds"] for e in eps)
        ana = []
        for p in THIN_P:
            miss, med = analytic(q, lag, H, p * req_rate, model_m, delay) if applicable else (None, None)
            ana.append({"p": p, "requestRate": p * req_rate, "predictedMiss": miss, "predictedMedianTtd": med})
        cross = {}
        for fam in ("M", "S", "L", "M:own", "S:own", "L:own"):
            base_fam, own = fam.split(":")[0], fam.endswith(":own")
            ev = [(i, e) for i, e in enumerate(eps) if collects(e, base_fam, P)]
            if not ev:
                continue
            for bc in (True, False):
                key = fam + ("" if bc else ":noBC")
                st = {i: family_ttd(e, base_fam, own=own, bc=bc) for i, e in ev}
                hit = [v["ttd"] for v in st.values() if v]
                if not hit:
                    cross[key] = {"n": len(ev), "sensorDetected": 0}
                    continue
                s_pen = statistics.mean(st[i]["ttd"] if st[i] else e["holdSeconds"] for i, e in ev)
                means = []
                for row in res["bernoulli"]:
                    l_pen = statistics.mean(lt if lt is not None else e["holdSeconds"]
                                            for i, e in ev for lt in row["_perEpisode"][i])
                    means.append({"p": row["p"], "requestRate": row["requestRate"], "ledgerPenalisedMean": l_pen})
                first_mean = next((x for x in means if s_pen < x["ledgerPenalisedMean"]), None)
                shares = []
                for row in res["bernoulli"]:
                    wins = trials = 0
                    for i, _ in ev:
                        ts = st[i]["ttd"] if st[i] else math.inf
                        for lt in row["_perEpisode"][i]:
                            trials += 1
                            wins += ts < (math.inf if lt is None else lt)
                    shares.append({"p": row["p"], "requestRate": row["requestRate"], "share": wins / trials})
                first = next((x for x in shares if x["share"] > 0.5), None)
                med_all = statistics.median(hit + [math.inf] * (len(ev) - len(hit)))
                cross[key] = {"n": len(ev), "sensorDetected": len(hit), "sensorTtd": dist(hit), "beatShare": shares,
                              "sensorPenalisedMean": s_pen, "ledgerPenalisedMeans": means,
                              "firstRateMeanBeaten": first_mean["requestRate"] if first_mean else None,
                              "firstRateBeaten": first["requestRate"] if first else None,
                              "analyticCrossover": (crossover_rate(q, lag, med_all, model_m, delay)
                                                    if applicable and not math.isinf(med_all) else None)}
        out["classes"][regime] = {"n": len(eps), "q": q, "qFailed": qf, "qBad": qall, "modelRequired": model_m,
                                  "analyticApplicable": applicable,
                                  "effectDelaySeconds": delay, "lagSeconds": lag, "holdSeconds": H, "thinning": res,
                                  "analytic": ana, "crossover": cross}
    return out


def resolution(P):
    """Measured cadence per channel: metric sample gaps (median, per collector), records per second in pre-windows."""
    gaps, rec = defaultdict(list), defaultdict(list)
    for c in P["cells"]:
        if c["target"] is None:
            continue
        a = c["cmd"]["A"]
        for (ch, svc, tok), (obs, _, meta) in c["prep"].items():
            if ch == "metric" and len(obs) > 1 and svc == P["entry"]:
                gaps[meta.get("collector")].append(statistics.median(y - x for x, y in zip(obs, obs[1:])))
            if ch in ("log", "span"):
                t0 = c["t0"]["wall"]
                n = sum(1 for t in obs if t0 <= t < a["wall"])
                rec[(ch, c["posture"])].append(n / (a["wall"] - t0))
        pre = [r for r in c["ledger"] if r[1] < a["mono"]]
        span = a["mono"] - (min(r[0] for r in c["ledger"]) if c["ledger"] else a["mono"])
        rec[("ledger", c["posture"])].append(len(pre) / span if span > 0 else 0.0)
    tot = defaultdict(float)
    for (ch, posture), xs in rec.items():
        tot[(ch, posture)] = statistics.median(xs) * 1.0 if xs else 0.0
    return {"metricGapMedianSeconds": {k: statistics.median(v) for k, v in gaps.items()},
            "recordsPerSecondPreWindowSumOverServices": {"%s/%s" % k: round(v, 3) for k, v in sorted(tot.items())},
            "logStampWholeSeconds": P["wholeSecondLogs"], "logStampsIntegral": P["logStampsIntegral"]}


def template_text(cell, svc, tok):
    """The masked message of the first record of template `tok` of `svc` in this cell (for checking BC-caller-log)."""
    from sensor_rep.parsers import common
    S = common.symptoms()
    d = REPO / cell["cell"]
    if cell["sut"] == "hotel":
        lines = [ln.split(" | ", 1)[1] for ln in (d / "application.log").read_text(errors="replace").splitlines()
                 if " | " in ln and ln.split(" | ", 1)[0].strip().rsplit("-", 1)[0] == svc]
        layouts = S.HOTEL_LAYOUTS
    else:
        lines, layouts = (d / ("%s.log" % svc)).read_text(errors="replace").splitlines(), S.JVM_LAYOUTS
    records, _ = S.parse_stream(lines, layouts)
    for r in records:
        if r["framework"] != "jvm-throwable" and S.template_id(r["framework"], r["level"], r["key"], r["msg"]) == tok:
            return "%s %s" % (r["level"], S.mask(r["msg"])[:140])
    return "?"


def caller_log_templates(P):
    out, text = Counter(), {}
    for e in P["episodes"]:
        for f in e["fires"]:
            if "BC-caller-log" in f["bc"] and f["admissible"]:
                k = "%s %s:%s:%s (target %s)" % (e["regime"], f["ch"], f["svc"], f["tok"], e["target"])
                out[k] += 1
                if k not in text:
                    text[k] = template_text(e["_c"], f["svc"], f["tok"])
    return {k: {"episodes": n, "message": text[k]} for k, n in out.items()}


def onset_check(P):
    """F-ADH-085: the onset used is a pre-command bound, at or before the post-command stamp, in every episode."""
    cmd = [e["commandSeconds"] for e in P["episodes"]]
    known = [x for x in cmd if x is not None]
    return {"episodes": len(cmd), "postCommandStampKnown": len(known), "boundAtOrBeforeStamp": sum(1 for x in known if x >= 0)}


def offpath_spikes(P):
    n = Counter()
    for e in P["episodes"]:
        for f in e["fires"]:
            if f["rule"] == "spike" and f["admissible"] and not f["counts"]:
                n[f["family"]] += 1
    return dict(n)


# =========================================================================== rendering

def fmt_t(d):
    if not d:
        return "—"
    if d["n"] == 1:
        return "%.2f" % d["median"]
    return "%.2f [%.2f–%.2f]" % (d["median"], d["min"], d["max"])


def fmt_cell(v):
    if v is None:
        return "—"
    s = "%d/%d" % (v["k"], v["n"])
    if v["k"]:
        s += " · " + fmt_t(v["ttd"])
    if v.get("penalisedMeanTtd") is not None:
        s += " · **%.2f**" % v["penalisedMeanTtd"]
    if v.get("g3Testable") is False and v["k"]:
        s += " †"
    return s


def fmt_fa(v):
    fa = v["falseAlarms"]
    if fa.get("untestable"):
        return "? (no records)"
    if not fa["n"]:
        return "?"
    s = "%d/%d" % (fa["k"], fa["n"])
    if fa["k"]:
        s += " (%.1f s)" % fa["timeToFirstFalseAlarm"]["median"]
    return s


def render(out):
    L = []
    w = L.append
    w("# Time to detection: ledger vs every sensor, on retained evidence")
    w("")
    w("Protocol draft 3, decisions 14 and 15 (spatio-temporal objective: per fault, detected or not, time to detection, "
      "impact before detection; traffic per route as a parameter; primary outcome = time to detection with misses charged at "
      "the window end, averaged over episodes), with decisions 9-11 and OFFLINE_RESULTS round 4 (ledger spread per request; "
      "a single-sample spike counts only on the affected call path inside the fault window, here approximated at service "
      "level; BC-caller-log).")
    w("")
    w("**Scope: instance.** Retained evidence, one host and one campaign per population, populations never pooled. "
      "The online rules below are engineering defaults chosen for this analysis, not a preregistered rule: K, the floors, "
      "the run length, the silence multiplier and the no-fault window placement are recorded in the script's docstring. "
      "Unknown is `?` or `—`; a share with denominator 0 is never printed. Status: built %s by a subagent; one independent "
      "adversarial review (Opus; Fable was rate-limited) applied, see the end." % out["generatedAt"][:10])
    w("")
    w("## Commands")
    w("")
    w("    rm -rf ~/Library/Caches/com.apple.python/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement/research")
    w("    /usr/bin/python3 -B research/detection-time/detection_time.py --self-check")
    w("    /usr/bin/python3 -B research/detection-time/detection_time.py      # ~%d s; writes out/detection_time.json and this file" % out["runtimeSeconds"])
    w("")
    w("Run: framework commit `%s` (HEAD at run time; this script uncommitted, sha256 `%s`), Python %s, %s seeds per "
      "(cell, thinning fraction)." % (out["frameworkCommit"][:12], out["scriptSha256"][:16], out["python"], SEEDS))
    w("")
    w("## What was measured, per population")
    w("")
    w("| population | evidence | valid fault episodes | no-fault windows per posture (cells) | onset bound | onset offset / hold (s) | command duration (s) | ledger rate | metric cadence, measured | log stamps |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for name in POPS:
        p = out["populations"][name]
        r = p["resolution"]
        cad = ", ".join("%s %.2f s" % (k, v) for k, v in sorted(r["metricGapMedianSeconds"].items())) or "—"
        cmd = p["commandSeconds"]
        w("| %s | `%s` | %d | %s | %s | %.2f / %.2f | %s | %.3g %s/s (%.3g req/s) | %s | %s |" % (
            name, p["evidence"], p["episodes"], ", ".join("%s %d (%d)" % (k, v, p["nofaultCells"][k]) for k, v in sorted(p["nWin"].items())),
            p["onsetSource"], p["onsetOffsetSeconds"], p["holdSeconds"],
            "—" if not cmd else "%.2f–%.2f" % (cmd["min"], cmd["max"]),
            p["traffic"]["baseUnitRate"], p["traffic"]["unit"], p["traffic"]["baseRequestRate"], cad,
            "whole seconds" if r["logStampWholeSeconds"] else ("sub-second" if r["logStampsIntegral"][1] else "—")))
    w("")
    w("Onset check (F-ADH-085): " + "; ".join(
        ("%s %d/%d episodes with the bound at or before the post-command stamp" % (
            n, out["populations"][n]["onsetCheck"]["boundAtOrBeforeStamp"], out["populations"][n]["onsetCheck"]["postCommandStampKnown"]))
        if out["populations"][n]["onsetCheck"]["postCommandStampKnown"] else
        ("%s — (no post-command stamp retained; the bound is the pre-command stamp by the code order)" % n)
        for n in POPS) + ". Hotel's bound is pre-command by statement order (lmt_faults.py / compose_pause.py), so its check "
      "only confirms the order was kept; TeaStore's scheduled onset is computed (barrier + 180 s), not stamped.")
    w("")
    w("Resolution per channel: spans and ledger requests are per record (observation = end of the span / request); logs are "
      "per record at the stamp resolution above; docker stats (M) and the cgroup sampler (S) at the measured cadence (Hotel "
      "only; TeaStore T16 retained no metric channel, OTel v3 is read for its ledger only). docker stats' declared "
      "`intervalSeconds` is 1.0 but the measured gap is the one printed (`docker stats --no-stream` takes ~3 s per round). "
      "A time to detection below a channel's cadence is not resolvable on that channel.")
    w("")
    w("## 0. Primary outcome (decision 15): time to detection, misses charged at the hold end, averaged over episodes")
    w("")
    w("Seconds from the command bound; a family that misses an episode is charged that episode's hold. Each cell: with BC / "
      "without BC catches. Outside the target (G2), except `E:own` (OTel: the target is the entry). n per cell as in table 1. "
      "These means inherit every limit of the rules and of n (4 per Hotel cell, 3 per TeaStore and OTel cell); read them with "
      "the false-alarm columns of table 1, which this mean does not charge.")
    w("")
    for name in POPS:
        p = out["populations"][name]
        rows, rows_nb = p["ttd"], p["ttdNoBC"]
        fams = [f for f in FAMILY_ORDER if any(f in r["families"] for r in rows)]
        if any(r["target"] == p["entry"] for r in rows):
            fams = ["E:own"] + fams
        w("**%s** (hold %.1f s)" % (name, p["holdSeconds"]))
        w("")
        w("| class | posture | n | " + " | ".join(fams) + " |")
        w("|---|---|---|" + "---|" * len(fams))
        for r, rn in zip(rows, rows_nb):
            cells = []
            for f in fams:
                v, vn = r["families"].get(f), rn["families"].get(f)
                cells.append("—" if not v else "%.2f / %.2f" % (v["penalisedMeanTtd"], vn["penalisedMeanTtd"]))
            w("| %s | %s | %d | %s |" % (r["regime"].replace("-effect", ""), r["posture"], r["n"], " | ".join(cells)))
        w("")
    w("## 1. Time to detection per (fault class, posture, family), by-construction catches included")
    w("")
    w("Each cell: detected k/n episodes · time to detection in seconds from the command bound, median [min–max] over the "
      "detected ones · **mean over all n episodes with misses charged at the hold end** (decision 15's primary outcome, "
      "bold; the same number as table 0). Hotel log stamps are whole seconds, so a log record stamped s is timed at s + 1 "
      "(the instant it certainly existed); the lower end s is in the JSON (`fires[i][4]`). Family false-alarm rate in no-fault windows of the same posture, leave-one-cell-out, same filters: "
      "k/n windows (median time to the first false alarm). Outside the target only (G2); the ledger family E counts its "
      "rules failed / spike / run3 / median. `—`: the posture does not collect the family.")
    w("")
    for bc in (True, False):
        if not bc:
            w("## 2. The same without by-construction catches")
            w("")
            w("Every sensor-rule carrying a BC flag (BC-ledger-stopped-on-path, BC-caller-span, BC-idle-cpu, "
              "BC-downstream-absent, BC-caller-log) is dropped, in the fault windows and in the false-alarm count.")
            w("")
        for name in POPS:
            p = out["populations"][name]
            rows = p["ttd" if bc else "ttdNoBC"]
            fams = [f for f in FAMILY_ORDER if any(f in r["families"] for r in rows)]
            if any(r["target"] == p["entry"] for r in rows):
                fams = ["E:own"] + fams
            w("**%s**" % name)
            w("")
            w("| class (target, kind) | posture | n | " + " | ".join("%s | FA %s" % (f, f) for f in fams) + " |")
            w("|---|---|---|" + "---|---|" * len(fams))
            for r in rows:
                cells = []
                for f in fams:
                    v = r["families"].get(f)
                    cells += [fmt_cell(v), fmt_fa(v) if v else "—"]
                w("| %s (%s, %s) | %s | %d | %s |" % (r["regime"].replace("-effect", ""), r["target"], r["faultKind"],
                                                      r["posture"], r["n"], " | ".join(cells)))
            w("")
            own = [(r, f, r["families"][f]) for r in rows for f in r["families"] if f.endswith(":own") and r["families"][f]["k"]]
            if own:
                w("Own sensors of the target (G2, reported apart): " + "; ".join(
                    "%s %s %s %s" % (r["regime"].replace("-effect", ""), r["posture"], f, fmt_cell(v)) for r, f, v in own) + ".")
                w("")
    w("Admissible single-sample spikes excluded because their service is off the affected call path (round 4): " + "; ".join(
        "%s %s" % (n, ", ".join("%s %d" % kv for kv in sorted(out["populations"][n]["offPathSpikesExcluded"].items())) or "0")
        for n in POPS) + " (fires, summed over episodes).")
    w("")
    w("## 3. The ledger's rules one by one")
    w("")
    w("Ledger sensor = one per route at the entry. Per rule: detected k/n by the rule on an admissible route · time to "
      "detection; then `adm a/b routes` and the G3 k/n_eff of the inadmissible routes (τ = 0.05); `any route: k` = the rule "
      "on any route, admissible or not. `watchdog` is not part of E.")
    w("")
    for name in POPS:
        p = out["populations"][name]
        w("**%s**" % name)
        w("")
        w("| class | posture | n | " + " | ".join(LEDGER_RULES) + " |")
        w("|---|---|---|" + "---|" * len(LEDGER_RULES))
        for r in p["ledgerRules"]:
            cells = []
            for rule in LEDGER_RULES:
                v = r["rules"][rule]
                inad = ["%s %d/%d" % (rt, k, nn) for rt, (k, nn) in sorted(v["g3PerRoute"].items()) if rt not in v["admissibleRoutes"]]
                g = "adm %d/%d routes%s" % (len(v["admissibleRoutes"]), len(v["g3PerRoute"]),
                                             ("; G3 " + ", ".join(inad)) if inad else "")
                head = ("%d/%d · %s" % (v["k"], r["n"], fmt_t(v["ttd"]))) if v["k"] else "0/%d" % r["n"]
                extra = "" if v["kAny"] == v["k"] else " · any route: %d" % v["kAny"]
                cells.append("%s · %s%s" % (head, g, extra))
            w("| %s | %s | %d | %s |" % (r["regime"].replace("-effect", ""), r["posture"], r["n"], " | ".join(cells)))
        w("")
    w("## 4. Impact before detection")
    w("")
    w("Ledger requests started between the command bound and the family's first catch that failed or crossed their route's "
      "per-request threshold: median [min–max] over the detected episodes (all postures that collect the family pooled), "
      "with detected/collected episodes. `hold` = the same count over the whole hold, for scale.")
    w("")
    for name in POPS:
        p = out["populations"][name]
        fams = []
        for r in p["impact"]:
            for f in r["families"]:
                if f not in fams:
                    fams.append(f)
        fams = [f for f in fams if not f.endswith(":own:noBC")]
        w("**%s**" % name)
        w("")
        w("| class | hold: bad / started | " + " | ".join(fams) + " |")
        w("|---|---|" + "---|" * len(fams))
        for r in p["impact"]:
            cells = []
            for f in fams:
                v = r["families"].get(f)
                if not v:
                    cells.append("—")
                elif not v["detected"]:
                    cells.append("0/%d" % v["n"])
                else:
                    cells.append("%s (%d/%d)" % (fmt_t(v["impactBeforeDetection"]).replace(".00", ""), v["detected"], v["n"]))
            w("| %s | %s / %s | %s |" % (r["regime"].replace("-effect", ""), fmt_t(r["holdBad"]).replace(".00", ""),
                                        fmt_t(r["holdRequests"]).replace(".00", ""), " | ".join(cells)))
        w("")
    w("## 5. Traffic dependence: the ledger thinned")
    w("")
    w("**Thinning the ledger does not reproduce what the SUT would do at lower load.** The SUT's state, its queueing, and "
      "every sensor's noise change with load, and sensors whose signal is load-driven (e.g. BC-idle-cpu: callers idle "
      "because requests stopped) would weaken. The numbers below bound the **ledger side only**: what the same fault, seen "
      "through fewer requests, would leave the ledger to see. The sensors' times are the ones measured at the campaign's load.")
    w("")
    w("Per class: share of (episode × seed) trials with no ledger catch inside the hold (miss), with no catch and a route "
      "without a latency baseline (`?`), median time to detection over the detected trials, and the no-fault false-alarm "
      "share of the thinned ledger. Bernoulli thinning (Poisson-like arrivals); periodic thinning in the JSON. Analytic "
      "Poisson prediction from the full-rate bad-request share q and observation lag l in the last column.")
    w("")
    for name in POPS:
        p = out["populations"][name]
        T = p["traffic"]
        w("**%s** (base %.3g %s/s, %.3g requests/s; %d seeds)" % (name, T["baseUnitRate"], T["unit"], T["baseRequestRate"], SEEDS))
        w("")
        w("| class | model: m · q · delay · lag · hold (s) | p | requests/s | miss | ? | miss periodic | median TTD all trials · detected (s) | mean TTD, miss = hold (s) | FA no-fault | failed rule only: miss · mean · FA | analytic miss · median |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for regime, cl in T["classes"].items():
            for row, per, an in zip(cl["thinning"]["bernoulli"], cl["thinning"]["periodic"], cl["analytic"]):
                if row["p"] not in (1.0, 0.1, 0.01, 0.001, 0.2, 0.02):
                    continue
                if an["predictedMiss"] is None:
                    ana_s = "n/a"
                else:
                    ana_s = "%.2f · %s" % (an["predictedMiss"], "%.2f" % an["predictedMedianTtd"]
                                           if an["predictedMedianTtd"] is not None else "> hold")
                fo = row["failedOnly"]
                w("| %s | %d · %.2f · %.2f · %.2f · %.1f | %g | %.3g | %s | %s | %s | %s · %s | %.2f | %s | %s · %.2f · %s | %s |" % (
                    regime.replace("-effect", ""), cl["modelRequired"], cl["q"], cl["effectDelaySeconds"], cl["lagSeconds"],
                    cl["holdSeconds"], row["p"], row["requestRate"],
                    "%.2f" % row["missShare"] if row["missShare"] is not None else "?",
                    "%.2f" % row["unknownShare"] if row["unknownShare"] is not None else "?",
                    "%.2f" % per["missShare"] if per["missShare"] is not None else "?",
                    "> hold" if row["medianTtdAllTrials"] is None else "%.2f" % row["medianTtdAllTrials"], fmt_t(row["ttdDetected"]),
                    row["penalisedMeanTtd"], "%d/%d" % tuple(row["noFaultFalseAlarms"]) if row["noFaultFalseAlarms"][1] else "?",
                    "?" if fo["missShare"] is None else "%.2f" % fo["missShare"], fo["penalisedMeanTtd"],
                    "%d/%d" % tuple(fo["noFaultFalseAlarms"]) if fo["noFaultFalseAlarms"][1] else "?", ana_s))
        w("")
    w("### Where a sampled or per-record sensor first beats the thinned ledger (its signal's own load dependence not measured)")
    w("")
    w("For each class and family: the sensor's measured time to detection (full load; a miss counts as never) against the "
      "thinned ledger's, per (episode × seed); `first rate` = the highest request rate on the grid at which the sensor is "
      "faster in more than half the trials (`—`: at no rate down to p = 0.001). Analytic = λ_m / (q·(t − d − l)) with t the "
      "sensor's median over all its episodes (`—` if it misses in half or more), d the effect delay, l the ledger's "
      "observation lag, λ_1 = ln 2; ∞ = the sensor is faster than d + l, so faster at any rate; n/a = the Poisson model does "
      "not apply (scattered crossings, or TeaStore's journey-clustered requests). M and S "
      "sample at a fixed cadence whatever the traffic; L is per record and its coupling to requests is unknown here (`?`), "
      "so its row is not a request-independent comparison. Spans thin with requests and are not compared.")
    w("")
    w("M and S sample at a fixed cadence, so their times are set by where the first sample after the effect falls "
      "(docker stats every 3.07 s, cgroup every 5 s): M catches fall only at 1.45-1.51, 4.55-4.58 and 7.57-7.65 s, S at "
      "4.8, 9.8 and 14.8 s. With a random sampling phase the same sensor would take [effect, effect + cadence]; the rates "
      "below hold for this campaign's phase only. Hotel log rows (whole-second stamps) are timed at the stamp's end and "
      "coincide with the ledger failure they report (same request), so their crossover is a stamp artefact; they are kept "
      "only for completeness.")
    w("")
    w("| population | class | family | detected | sensor TTD (s) | faster at full rate | first rate faster (req/s) | first rate, mean TTD miss = hold (req/s) | analytic (req/s) | without BC: detected · first rate |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    never = defaultdict(list)
    for name in POPS:
        T = out["populations"][name]["traffic"]
        for regime, cl in T["classes"].items():
            for fam in ("M", "S", "L", "M:own", "S:own", "L:own"):
                v, vn = cl["crossover"].get(fam), cl["crossover"].get(fam + ":noBC")
                if v is None:
                    continue
                if not v["sensorDetected"] and not (vn and vn["sensorDetected"]):
                    never[(name, fam)].append(regime.replace("-effect", ""))
                    continue
                ac = v.get("analyticCrossover")
                nb = "—" if not vn else ("0/%d" % vn["n"] if not vn["sensorDetected"] else "%d/%d · %s" % (
                    vn["sensorDetected"], vn["n"], "%.3g" % vn["firstRateBeaten"] if vn["firstRateBeaten"] is not None else "—"))
                w("| %s | %s | %s | %d/%d | %s | %s | %s | %s | %s | %s |" % (
                    name, regime.replace("-effect", ""), fam, v["sensorDetected"], v["n"], fmt_t(v.get("sensorTtd")),
                    "%.2f" % v["beatShare"][0]["share"] if v.get("beatShare") else "—",
                    "%.3g" % v["firstRateBeaten"] if v.get("firstRateBeaten") is not None else "—",
                    "%.3g" % v["firstRateMeanBeaten"] if v.get("firstRateMeanBeaten") is not None else "—",
                    "n/a" if not cl["analyticApplicable"] else ("—" if ac is None else ("∞" if ac in (math.inf, "inf") else "%.3g" % ac)),
                    nb))
    w("")
    w("Never detecting (with or without BC), so no crossover: " + "; ".join(
        "%s %s: %s" % (n, f, ", ".join(rs)) for (n, f), rs in sorted(never.items())) + ".")
    w("")
    w("## BC-caller-log: the templates it flags")
    w("")
    w("Structural rule (warn/error/other-level template of a direct caller of the target, firing by appear). Listed so a "
      "reader can check each one is a caller's log about its failed call; admissible fires per episode count:")
    w("")
    for name in POPS:
        for k, v in sorted(out["populations"][name]["callerLogTemplates"].items()):
            w("- %s: %s × %d episodes: `%s`" % (name, k, v["episodes"], v["message"].replace("|", "/")))
    w("")
    w("## Findings (instance scope; contrasts, not mechanisms)")
    w("")
    for line in out.get("findings", []):
        w("- " + line)
    w("")
    w("## Engineering defaults and limits")
    w("")
    for line in out["defaults"]:
        w("- " + line)
    w("")
    w("## Review")
    w("")
    for line in out.get("review", ["not yet reviewed"]):
        w("- " + line)
    w("")
    return "\n".join(L)


# =========================================================================== main

def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if not str(k).startswith("_") and k not in ("c",)}
    if isinstance(o, (list, tuple)):
        return [strip(v) for v in o]
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return None if math.isnan(o) else "inf"
    return o


DEFAULTS = [
    "Baselines are each cell's own pre-window, per sample / per request (decision round 4: ledger spread per request); the "
    "sensor_rep window rule (no-fault tiles, window medians) is not used for timing because a window median has no time.",
    "K = 4, scale 1.4826, floors from sensor_rep/catch.py (span latency 1 ms, ledger 1 ms, metric floors from symptoms.py / "
    "lmt_detect.py, else 2 % of the median); comparator `>=`; >= 3 pre-window samples for a level threshold.",
    "run3 = 3 consecutive samples; median = online median of >= 3 in-window samples; absent = silence > 2 x the longest "
    "pre-window gap after >= 5 pre-window records. One rule pool for every channel; no detector selection (§2b not run).",
    "No-fault windows: hold-length windows at onset_med + i·hold inside every valid no-fault cell of the posture, each with "
    "its own pre-window; windows of one cell are not independent (n_eff is stated with its cells). Later windows have "
    "longer pre-windows than the fault cells.",
    "G3 per (posture, sensor, rule) at τ = 0.05. Hotel n_eff = 20 per posture (k <= 1 admissible); TeaStore and OTel 6 "
    "(k = 0). TeaStore no-fault cells hold no application log records, so log rules there cannot be removed by G3.",
    "The affected call path for spikes is service-level (target, transitive callers, transitive callees in the project "
    "map's call graph); per-request trace attribution was not done.",
    "Observation time = when a record becomes available (span end, request end, log stamp, metric stamp). docker stats "
    "and cgroup rates are stamped at the end of their interval.",
    "Detection is counted only inside the hold [command bound, hold end]; a catch after the revert is not a detection.",
    "Ledger readers: visibility.hotel_ledger_rows / teastore_ledger_rows (checked equal, journey index kept) / "
    "otel_ledger_rows. Ledger latency baselines are per route; TeaStore has four routes.",
    "OTel: barrier-relative fault offsets against the ledger's own start stamp (taken after the barrier), skew not measured.",
    "Thinning keeps the full-rate admissible ledger rules; E only (failed, spike, run3, median).",
]


def main():
    import time
    t_start = time.time()
    out = {"generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "script": "research/detection-time/detection_time.py",
           "scriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "frameworkCommit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                                             text=True).stdout.strip(),
           "python": platform.python_version(),
           "constants": {"K": K, "scale": SCALE, "tau": TAU, "minBaseline": MIN_BASELINE, "runN": RUN_N,
                         "absentMin": ABSENT_MIN, "absentGapMult": ABSENT_GAP_MULT, "ledgerFloorMs": LEDGER_FLOOR_MS,
                         "thinP": THIN_P, "seeds": SEEDS},
           "defaults": DEFAULTS, "populations": {}}
    for name in POPS:
        print("…", name, flush=True)
        P = run_population(name)
        rows = ttd_table(P, bc=True)
        rows_nobc = ttd_table(P, bc=False)
        T = traffic(P)
        cmd = [e["commandSeconds"] for e in P["episodes"] if e["commandSeconds"] is not None]
        nf_cells = Counter()
        for c in P["cells"]:
            if c["target"] is None:
                nf_cells[c["posture"]] += 1
        eps = []
        for e in P["episodes"]:
            ee = {k: v for k, v in e.items() if k not in ("fires", "_c")}
            ee["fires"] = [[f["family"], "%s:%s:%s" % (f["ch"], f["svc"], f["tok"]), f["rule"], round(f["ttd"], 4),
                            round(f.get("ttdLo", f["ttd"]), 4),
                            f["dir"], "%d/%d" % (f["g3k"], f["g3n"]), f["admissible"], f["own"], f["onPath"],
                            f["counts"], f["bc"]] for f in sorted(e["fires"], key=lambda f: f["ttd"])
                           if f["admissible"] or f["ch"] == "ledger"]
            ee["firesInadmissible"] = sum(1 for f in e["fires"] if not f["admissible"])
            for fam in FAMILY_ORDER:
                for own in (False, True):
                    for bc in (True, False):
                        h = family_ttd(e, fam, own=own, bc=bc)
                        ee.setdefault("familyTtd", {})["%s%s%s" % (fam, ":own" if own else "", "" if bc else ":noBC")] = \
                            (None if not collects(e, fam, P) else (round(h["ttd"], 4) if h else "miss"))
            eps.append(ee)
        out["populations"][name] = {
            "sut": P["sut"], "evidence": P["evidence"], "entry": P["entry"], "edges": P["edges"], "onRoute": P["onRoute"],
            "episodes": len(P["episodes"]), "onsetSource": P["episodes"][0]["onsetSource"],
            "onsetOffsetSeconds": P["onsetOffsetSeconds"], "holdSeconds": P["holdSeconds"],
            "commandSeconds": dist(cmd), "nWin": P["nWin"], "nofaultCells": dict(nf_cells),
            "resolution": resolution(P), "ttd": rows, "ttdNoBC": rows_nobc, "ledgerRules": ledger_rule_table(P),
            "impact": impact_table(P), "traffic": T, "callerLogTemplates": caller_log_templates(P),
            "onsetCheck": onset_check(P), "offPathSpikesExcluded": offpath_spikes(P),
            "episodeDetail": eps}
    out["runtimeSeconds"] = int(time.time() - t_start)
    out = strip(out)
    if (HERE / "findings.json").exists():
        f = json.loads((HERE / "findings.json").read_text())
        out["findings"], out["review"] = f.get("findings", []), f.get("review", [])
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, sort_keys=True))
    OUT_MD.write_text(render(out))
    print("wrote", OUT_JSON.relative_to(REPO), OUT_MD.relative_to(REPO), "in", out["runtimeSeconds"], "s")


def render_only():
    out = json.loads(OUT_JSON.read_text())
    if (HERE / "findings.json").exists():
        f = json.loads((HERE / "findings.json").read_text())
        out["findings"], out["review"] = f.get("findings", []), f.get("review", [])
    OUT_MD.write_text(render(out))
    print("rendered", OUT_MD.relative_to(REPO))


# =========================================================================== self-check on planted timelines

def _checks():
    """Planted timelines with known answers. Returns a list of (name, ok)."""
    R = []
    # 1. ledger: 10/s, latency 10 ms (+-0.5), onset at 45.0; from 45.2 every request times out at 1 s
    reqs = []
    for i in range(600):
        s = i * 0.1
        if s < 45.15:
            lat = 0.010 + (0.0005 if i % 2 else -0.0005)
            reqs.append((s, s + lat, True, "r", i))
        else:
            reqs.append((s, s + 1.0, False, "r", i))
    reqs.sort(key=lambda r: r[1])
    out, base, _ = ledger_rules(reqs, 45.0, 60.0)
    m, thr = base["r"]
    R.append(("ledger failed at first timeout end (46.2)", abs(out[("r", "failed")] - 46.2) < 1e-6))
    R.append(("ledger watchdog at start + threshold", abs(out[("r", "watchdog")] - (45.2 + (m + thr) / 1000.0)) < 1e-6))
    R.append(("ledger threshold = max(K*1.4826*MAD, 1 ms) per request", abs(thr - max(K * SCALE * 0.5, 1.0)) < 1e-9))
    R.append(("impact before detection counts started-in-window bad requests",
              impact(reqs, base, 45.0, 46.2) == sum(1 for r in reqs if 45.0 <= r[0] <= 46.2 and not r[2])))
    # 2. ledger: +20 ms on every request from 45.0: spike at first, run3 at third, median at third
    reqs2 = []
    for i in range(600):
        s = i * 0.1 + 0.05
        lat = 0.010 + (0.0005 if i % 2 else -0.0005) + (0.020 if s >= 45.0 else 0.0)
        reqs2.append((s, s + lat, True, "r", i))
    reqs2.sort(key=lambda r: r[1])
    o2, _, _ = ledger_rules(reqs2, 45.0, 60.0)
    first = min(r[1] for r in reqs2 if r[0] >= 45.0)
    third = sorted(r[1] for r in reqs2 if r[0] >= 45.0)[2]
    R.append(("ledger spike at first slowed request", abs(o2[("r", "spike")] - first) < 1e-9))
    R.append(("ledger run3 and median at the third", abs(o2[("r", "run3")] - third) < 1e-9 and abs(o2[("r", "median")] - third) < 1e-9))
    R.append(("ledger: no failure rule on an all-ok stream", ("r", "failed") not in o2))
    # 3. metric every 3 s from 0, value 10 +- 0.1, step to 50 at t = 48
    obs = [3.0 * i for i in range(40)]
    vals = [(50.0 if t >= 48 else (10.5 if i % 2 else 10.0)) for i, t in enumerate(obs)]
    pre = [v for t, v in zip(obs, vals) if t < 45.0]
    mm, tt = threshold(pre, 2.0)
    win = [(t, v) for t, v in zip(obs, vals) if 45.0 <= t <= 60.0]
    g = level_rules([t for t, _ in win], [v for _, v in win], mm, tt, ("up", "down"))
    R.append(("metric spike at the first stepped sample (+3 s)", g.get("spike") == (48.0, "up")))
    R.append(("metric run3 at the third stepped sample (+9 s)", g.get("run3") == (54.0, "up")))
    R.append(("metric median once 2 of 3 in-window samples are up (+6 s)", g.get("median") == (51.0, "up")))
    # inclusive comparator: a sample exactly at the threshold fires
    g_eq = level_rules([46.0], [mm + tt], mm, tt, ("up",))
    R.append(("comparator inclusive (sample at m + thr fires)", g_eq.get("spike") == (46.0, "up")))
    # 4. counts: appear at 47; absent: one record per second until 45, G = 2 s -> fires at 44 + 2 = 46
    c1 = count_rules([], [47.0, 48.0], 45.0, 60.0)
    R.append(("appear at the first in-window record", c1.get("appear") == (47.0, None)))
    pre_t = [float(t) for t in range(0, 45)]
    c2 = count_rules(pre_t, [], 45.0, 60.0)
    R.append(("absent at last + 2 x max gap", c2.get("absent") == (46.0, None)))
    c3 = count_rules(pre_t, [float(t) for t in range(45, 61)], 45.0, 60.0)
    R.append(("absent: steady stream does not fire", "absent" not in c3))
    R.append(("whole-second log stamped in the hold's last second straddles the hold end (no catch)",
              log_ttd(59.0, 45.0, True, 59.8) is None and log_ttd(58.0, 45.0, True, 59.8) == (13.0, 14.0)))
    # eval_window on a planted two-clock cell: wall = mono + 1000; onset mono 45.15 / wall 1045.15, hold to 60.15
    def fam(ch, coll, posture):
        return {"log": "L", "metric": "M"}.get(ch)
    lg = [1000.0 + t for t in range(0, 45)] + [1047.0]
    mt_t = [1000.0 + 3 * i for i in range(30)]
    mt_v = [10.0 if t < 1048 else 50.0 for t in mt_t]
    pc = {"sut": "hotel", "posture": "full", "chans": {"log", "metric", "ledger"}, "t0": {"wall": 1000.0, "mono": None},
          "family": fam,
          "prep": {("log", "frontend", "tplA"): ([1047.0], [1.0], {"clock": "wall", "level": "error", "collector": "x"}),
                   ("log", "geo", "steady"): (lg, [1.0] * len(lg), {"clock": "wall", "level": "info", "collector": "x"}),
                   ("metric", "geo", "cpu"): (mt_t, mt_v, {"clock": "wall", "collector": "docker-stats"})},
          "ledger": sorted([(i * 0.1, i * 0.1 + (0.01 if i * 0.1 < 45.3 else 1.0), i * 0.1 < 45.3, "r", i) for i in range(600)],
                           key=lambda r: r[1])}
    fw, _, _ = eval_window(pc, {"mono": 45.15, "wall": 1045.15}, {"mono": 60.15, "wall": 1060.15}, True)
    got = {(f["svc"], f["tok"], f["rule"]): round(f["ttd"], 6) for f in fw}
    lo_a = {(f["svc"], f["tok"], f["rule"]): round(f.get("ttdLo", f["ttd"]), 6) for f in fw}
    R.append(("eval_window: log appear timed at stamp + 1 on the wall clock (2.85 s; lower end 1.85 s)",
              got.get(("frontend", "tplA", "appear")) == 2.85 and lo_a.get(("frontend", "tplA", "appear")) == 1.85))
    R.append(("eval_window: metric spike on the wall clock (+2.85 s)", got.get(("geo", "cpu", "spike")) == 2.85))
    R.append(("eval_window: ledger failure on the monotonic clock (first fail starts 45.3, ends 46.3: 1.15 s)",
              got.get(("frontend", "r", "failed")) == 1.15))
    R.append(("eval_window: steady log stream silent after 1045 -> absent at 1044 + 2 + 1 s stamp", got.get(("geo", "steady", "absent")) == round(1044 + 2 + 1 - 1045.15, 6)))
    R.append(("whole-second log stamp: TTD = stamp + 1 - onset, interval kept",
              log_ttd(46.0, 45.15, True) == (46.0 - 45.15, 47.0 - 45.15) and log_ttd(45.0, 45.15, True)[0] == 0.0
              and abs(log_ttd(45.0, 45.15, True)[1] - 0.85) < 1e-9 and log_ttd(46.3, 45.15, False)[1] == 46.3 - 45.15))
    c4 = count_rules(pre_t, [], 45.0, 45.5)
    R.append(("absent: silence ending after the hold is no catch", "absent" not in c4))
    # 5. G3 arithmetic
    R.append(("G3: 1 of 20 admissible, 2 of 20 not, n = 0 not", admissible(1, 20) and not admissible(2, 20) and not admissible(0, 0)))
    # 6. affected path and spike filter
    edges = {("frontend", "search"), ("search", "geo"), ("search", "rate"), ("frontend", "profile")}
    path = affected_path("search", edges)
    R.append(("affected path = target + callers + callees", path == {"frontend", "search", "geo", "rate"}))
    f_off = {"ch": "metric", "svc": "profile", "tok": "cpu", "rule": "spike"}
    f_on = {"ch": "metric", "svc": "geo", "tok": "cpu", "rule": "spike"}
    f_run = {"ch": "metric", "svc": "profile", "tok": "cpu", "rule": "run3"}
    R.append(("off-path spike not scored, on-path spike and off-path run3 scored",
              not scored(f_off, "search", path, "frontend")[0] and scored(f_on, "search", path, "frontend")[0]
              and scored(f_run, "search", path, "frontend")[0]))
    R.append(("ledger own iff target is the entry", scored({"ch": "ledger", "svc": "frontend", "tok": "r", "rule": "failed"},
                                                          "frontend", path, "frontend")[1]))
    # 7. BC flags
    ctx = {"onRoute": {"frontend", "search", "geo", "rate", "profile"}, "ops": {"search": {"/search.Search/Nearby"}},
           "edges": edges}
    R.append(("BC-caller-log on a caller's error log", bc_flags({"ch": "log", "svc": "frontend", "tok": "x", "rule": "appear",
                                                                 "level": "error"}, "search", "pause", ctx) == ["BC-caller-log"]))
    R.append(("no BC-caller-log on a non-caller or info log",
              bc_flags({"ch": "log", "svc": "geo", "tok": "x", "rule": "appear", "level": "error"}, "search", "pause", ctx) == []
              and bc_flags({"ch": "log", "svc": "frontend", "tok": "x", "rule": "appear", "level": "info"}, "search", "pause", ctx) == []))
    R.append(("BC-idle-cpu on a downward cpu fire under pause only",
              bc_flags({"ch": "metric", "svc": "frontend", "tok": "cpu", "rule": "spike", "dir": "down"}, "search", "pause", ctx) == ["BC-idle-cpu"]
              and bc_flags({"ch": "metric", "svc": "frontend", "tok": "cpu", "rule": "spike", "dir": "down"}, "search", "degradation", ctx) == []))
    R.append(("BC-caller-span and BC-ledger-stopped-on-path",
              bc_flags({"ch": "span", "svc": "frontend", "tok": "/search.Search/Nearby:error", "rule": "appear"}, "search", "pause", ctx) == ["BC-caller-span"]
              and bc_flags({"ch": "ledger", "svc": "frontend", "tok": "r", "rule": "failed"}, "search", "pause", ctx) == ["BC-ledger-stopped-on-path"]))
    # 8. thinning: p = 1 keeps everything; Bernoulli share ~ p; periodic spacing; miss rate vs the analytic Poisson value
    R.append(("p = 1 keeps every unit", thin_units(50, 1.0, 1, "bernoulli") == list(range(50))))
    kept = sum(len(thin_units(1000, 0.1, s, "bernoulli")) for s in range(200)) / 200.0
    R.append(("Bernoulli keeps ~p", abs(kept - 100) < 3))
    per = thin_units(1000, 0.01, 7, "periodic")
    R.append(("periodic keeps every 100th", all(b - a == 100 for a, b in zip(per, per[1:])) and len(per) == 10))
    misses = 0
    trials = 400
    for s in range(trials):
        k = set(thin_units(600, 0.01, s, "bernoulli"))
        sub = [r for r in reqs if r[4] in k]
        o, _, _ = ledger_rules(sub, 45.0, 60.0, rules=E_RULES)
        misses += not o
    # q = 1 from 45.2 (all fail), lag 1 s, rate 0.1/s, effective hold 15 - 0.2 - 1
    pred = math.exp(-0.1 * 1.0 * (15.0 - 0.2 - 1.0))
    R.append(("thinned miss rate ~ analytic Poisson exp(-r q (H - l))", abs(misses / trials - pred) < 0.07))
    R.append(("analytic crossover: sensor faster than the lag beats at every rate", crossover_rate(1.0, 1.0, 0.5) == math.inf))
    R.append(("analytic crossover value", abs(crossover_rate(1.0, 1.0, 3.0) - math.log(2) / 2.0) < 1e-9))
    R.append(("lam_median(1) = ln 2, P(Poisson >= 3) at its median = 0.5",
              abs(lam_median(1) - math.log(2)) < 1e-9 and abs(poisson_ge(lam_median(3), 3) - 0.5) < 1e-9))
    return R


def self_check():
    global INCLUSIVE, PATH_FILTER, G3_TAU
    R = _checks()
    bad = [n for n, ok in R if not ok]
    for n, ok in R:
        print("%-4s %s" % ("ok" if ok else "FAIL", n))
    if bad:
        raise SystemExit("self-check FAILED: %d of %d" % (len(bad), len(R)))
    mutants = {"comparator strict (>)": ("INCLUSIVE", False), "no spike path filter": ("PATH_FILTER", False),
               "G3 k <= n": ("G3_TAU", 1.0), "log timed at its stamp": ("LOG_UPPER", False),
               "no hold-end cap for logs": ("LOG_HOLD_CAP", False)}
    caught = 0
    for label, (var, val) in mutants.items():
        old = globals()[var]
        globals()[var] = val
        try:
            fails = [n for n, ok in _checks() if not ok]
        finally:
            globals()[var] = old
        print("mutant %-24s %s (%d checks fail)" % (label, "caught" if fails else "NOT CAUGHT", len(fails)))
        caught += bool(fails)
    if caught != len(mutants):
        raise SystemExit("self-check FAILED: mutants caught %d of %d" % (caught, len(mutants)))
    print("self-check pass: %d checks, %d/%d mutants caught" % (len(R), caught, len(mutants)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--render", action="store_true", help="re-render the markdown from out/detection_time.json")
    a = ap.parse_args()
    if a.self_check:
        self_check()
    elif a.render:
        render_only()
    else:
        main()
