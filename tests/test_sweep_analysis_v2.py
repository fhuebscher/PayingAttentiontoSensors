"""Traffic-sweep analysis v2.4 (research/detection-time/sweep_analysis_v2.py): the methodology-hardening rules,
protocol round 11 (decisions 51-55), round 12 (decision 57), round 13 (decisions 58, 59) with the v2.2 review's fixes and
round 14 (decision 60).

Layer: unit + synthetic end-to-end. Synthetic fixtures only; no sweep evidence is read. Every new rule has a check that
passes on v2.1, and where v1 behaved differently the same check is shown to fail on v1's behaviour (v1's own function, or
the switch that restores it). Every round-11 rule has a check that is shown to fail on v2's behaviour: v2 itself, loaded
from git (32e3178 = 87b04ef plus the reason-text fix), and v2's registry (ac313f1); decision 57's checks are shown to
fail on v2.1 itself, loaded from git (22e0d12), decision 58's on v2.2 (421a6d2) and decision 60's on v2.3 (af6f223).
Every new rule has at least one
planted defect (MUTANTS, or an explicit planted variant) that must make one of its checks fail. Also: the parameter
registry (no tunable numeric literal in v2.1 outside the allow-list, also inside float("...")/int("...") or literal
arithmetic; every tunable imported from v1/detection_time equal to its registry entry; no `unknown` origin among the
entries v2.1 reads), v1 and detection_time unchanged, the readout text, the CLI never overwriting.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import math
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))

import sweep_analysis as sa1  # noqa: E402
import sweep_analysis_v2 as v2  # noqa: E402
import detection_time as dtm  # noqa: E402

T0 = 1_790_000_000.0          # barrier, wall clock
B0 = 5000.0                   # barrier, monotonic clock
OFF = T0 - B0                 # true wall - monotonic offset
NF, SP, CT, ND = sa1.NOFAULT, "search-pause-effect", "cpu-throttle-effect", "net-delay-effect"
OFFSETS = (0.1, 0.35, 0.6, 0.85)
HOLD, MEAS = 60.0, 180.0
READ_GAP = (2e-6, 3e-6)       # startedAt read before the monotonic start, endedAt after the monotonic end
RECEIPT = 0.0003              # Docker receive delay of every log line


# ----------------------------------------------------------------------------- synthetic campaign

def _iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _app(t):
    return dt.datetime.fromtimestamp(math.floor(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dock(t):
    whole = math.floor(t)
    return dt.datetime.fromtimestamp(whole, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + \
        ".%09dZ" % int(round((t - whole) * 1e9))


def _w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))


def _span(trace, sid, parent, svc, op, t, d, tags):
    return {"traceId": trace, "spanId": sid, "parentSpanId": parent, "service": svc, "parentService": None,
            "operation": op, "startTimeUs": int(round(t * 1e6)), "durationUs": int(round(d * 1e6)), "tags": tags,
            "signatureSha256": "x"}


def off(rate, block):
    return round(((block - 1) + 0.4) / 4.0 / rate, 6)


COMPOSE = {"services": {
    "frontend": {"depends_on": {"consul": {}}}, "search": {"depends_on": {"consul": {}}},
    "rate": {"depends_on": {"consul": {}, "memcached-rate": {}, "mongodb-rate": {}}},
    "profile": {"depends_on": {"consul": {}, "memcached-profile": {}}}, "user": {"depends_on": {"mongodb-user": {}}},
    "consul": {}, "memcached-rate": {}, "mongodb-rate": {}, "memcached-profile": {}, "mongodb-user": {}}}
METRIC_SVCS = ("frontend", "search", "profile", "rate", "memcached-rate", "user")


def make_cell(root, regime, rate, block, offset, docker_event=True, extra_log=None, outlier=None, user_spread=None,
              lose_first_delayed_search=False):
    """One sweep cell. search-pause freezes search 0.25 s after the command (startedMonotonic = A): every request
    started from then on times out after 1.001 s. cpu-throttle raises profile's PSI. net-delay adds 0.2 s to every
    request from A + 0.05 s and 0.1 s to rate's memcached span (which ends ~0.107 s before the client's reply).
    extra_log: a frontend info template written once at barrier + 30 s. outlier: (request index, memcached duration
    in microseconds). user_spread: (spread, outlier) for user's 9 background spans: durations 1000 + spread x (k % 3)
    microseconds (MAD > 0), span 4 lasting `outlier` microseconds if given (user is on no affected path).
    lose_first_delayed_search: the first delayed request's search span never reaches the collector, so search's silence
    is ended by the second delayed request while the ledger's is ended by the first (decision 58's fixture)."""
    fault = {NF: None, SP: "search-pause", CT: "profile-cpu-throttle", ND: "rate-net-delay"}[regime]
    rt = ("%g" % rate).replace(".", "p")
    klass = {None: "calibration", "search-pause": "effect/search-pause", "profile-cpu-throttle": "effect/cpu-throttle",
             "rate-net-delay": "effect/net-delay"}
    d = root / "runs" / klass[fault] / ("r" + rt) / ("b%02d" % block) / ("p%02d-full" % block) / "attempt-01"
    onset = 60.0 + offset
    timing = {"requestsPerSecond": rate, "interArrivalSeconds": 1.0 / rate, "requestTimeoutSeconds": 1.0,
              "measurementSeconds": MEAS, "faultOnsetBaseSeconds": 60, "faultOnsetPhaseOffsetSeconds": offset,
              "faultOnsetSeconds": onset, "faultHoldSeconds": 60, "scoredWindowSeconds": [onset, onset + HOLD]}
    _w(d / "cell-contract.json", {"runId": "%s-r%s-b%02d" % (regime, rt, block), "fault": fault, "timing": timing,
                                  "compiledPlanCanonicalSha256": "7" * 64, "admissionCanonicalSha256": "a" * 64,
                                  "runKey": {"regime": regime, "requestsPerSecond": rate, "block": block,
                                             "posture": "full", "attempt": 1}})
    _w(d / "cell-terminal.json", {"candidateCellValid": True})
    _w(d / "opportunity-plan.json", {"barrierAt": _iso(T0), "barrierMonotonic": B0, "durationSeconds": MEAS,
                                     "workloadId": "hotel-search-v1", "rate": rate})
    A = B0 + onset + 0.1
    applied = A + (0.25 if fault == "search-pause" else 0.05)
    rev = A + HOLD
    code = (FAULT_CODE[regime] * 100 + int(rate * 100)) * 100 + block
    rows, spans, logs = [], [], []
    lost = [False]

    def log(t, level, msg, svc="frontend"):
        return "%s-1  | %s {\"level\":\"%s\",\"time\":\"%s\",\"message\":\"%s\"}" % (
            svc, _dock(t + RECEIPT), level, _app(t), msg)
    for i in range(int(round(rate * MEAS))):
        so = i / rate
        s = B0 + so + 0.002
        tok = "hr-%032x" % (code * 10_000_000 + i)
        paused = fault == "search-pause" and applied - 0.005 <= s <= rev
        delayed = fault == "rate-net-delay" and applied <= s <= rev
        lat = 1.001 if paused else 0.010 + (0.0005 if i % 2 else 0.0) + 1e-6 * (i % 5) + (0.2 if delayed else 0.0)
        e = s + lat
        rows.append({"sequence": i, "scheduledMonotonicOffsetSeconds": so, "actualStartMonotonic": s,
                     "actualEndMonotonic": e, "outcome": "transport-error" if paused else "completed",
                     "statusCode": None if paused else 200, "error": "timed out" if paused else None,
                     "opaqueToken": tok, "startedAt": _iso(s + OFF - READ_GAP[0]), "endedAt": _iso(e + OFF + READ_GAP[1])})
        ws, we, tr = s + OFF, e + OFF, "t%s%06d" % (code, i)
        tags = {sa1.TOKEN_TAG: tok}
        if paused:
            tags["error"] = True
            logs.append(log(we + 0.0005 - OFF + OFF, "error", "request failed token=%s" % tok))
        spans.append(_span(tr, "r%d" % i, None, "frontend", "HTTP GET /hotels", ws, we - ws, tags))
        if not paused:
            mc = (540 if i % 2 else 500) + (i % 5) + (100_000 if delayed else 0)
            if outlier and outlier[0] == i:
                mc = outlier[1]
            if delayed and lose_first_delayed_search and not lost[0]:
                lost[0] = True
            else:
                spans.append(_span(tr, "s%d" % i, "r%d" % i, "search", "/search.Search/Nearby", ws + 0.001,
                                   we - ws - 0.002, {}))
            spans.append(_span(tr, "g%d" % i, "s%d" % i, "rate", "/rate.Rate/GetRates", ws + 0.002,
                               0.004 + (0.1 if delayed else 0.0), {}))
            spans.append(_span(tr, "m%d" % i, "g%d" % i, "rate", "memcached_get", ws + 0.003, mc / 1e6, {}))
    _w(d / "opportunity-ledger.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    logs.append(log(T0 + 1.2345, "info", "TLS disabled."))
    logs += [log(T0 + 0.5 + 7 * k, "info", "cache refreshed") for k in range(26)]
    logs.append('time="2026-10-03T05:10:00Z" level=warning msg="compose cli line"')
    if extra_log:
        logs.append(log(T0 + 30.0, "info", extra_log))
    if fault is not None:
        pre = (B0 + onset + 0.01, B0 + onset + 0.04)
        during = (A + 0.06, A + (5.06 if fault == "search-pause" else 0.07))
        rc = {"schemaVersion": 1, "faultKind": "pause" if fault == "search-pause" else "degradation",
              "scenario": fault, "targetService": FAULT_TARGET[fault], "startedMonotonic": A,
              "appliedMonotonic": applied, "revertingMonotonic": rev, "readyAtMonotonic": rev + 0.5,
              "endedMonotonic": rev + 0.6, "error": None,
              "probes": [{"phase": "pre", "startMonotonic": pre[0], "endMonotonic": pre[1], "available": True},
                         {"phase": "during", "startMonotonic": during[0], "endMonotonic": during[1],
                          "available": fault != "search-pause"}]}
        _w(d / "fault-receipt.json", rc)
        ev = []
        if fault == "search-pause" and docker_event:
            for act, t in (("pause", applied), ("unpause", rev + 0.05)):
                ev.append({"Type": "container", "Action": act, "Actor": {"ID": "c", "Attributes": {
                    "com.docker.compose.service": "search", "name": "search-1"}}, "scope": "local",
                    "time": int(t + OFF), "timeNano": int(round((t + OFF) * 1e9))})
        _w(d / "docker-events.jsonl", "".join(json.dumps(x) + "\n" for x in ev))
        for k, (lo, hi) in enumerate((pre, during)):
            spans.append(_span("probe%d%s" % (k, code), "p%d" % k, None, "frontend", "HTTP GET /hotels", lo + OFF,
                               hi - lo, {}))
    _w(d / "application.log", "\n".join(logs) + "\n")
    _w(d / "traces-normalized.json", {"events": spans})
    _w(d / "jaeger-raw-remainder.json", {"queries": [{"service": "user", "traceCount": 9, "traces": [
        {"traceID": "bg%s%d" % (code, k), "processes": {"p1": {"serviceName": "user"}},
         "spans": [{"spanID": "u%d" % k, "processID": "p1", "operationName": "/user.User/CheckUser",
                    "startTime": int((T0 + 10 + 20 * k) * 1e6),
                    "duration": (1000 + (20 if k % 2 else 0)) if user_spread is None else (
                        user_spread[1] if (user_spread[1] and k == 4) else 1000 + user_spread[0] * (k % 3)),
                    "references": [], "tags": []}]} for k in range(9)]}]})
    _w(d / "compose-rendered.yml", COMPOSE)
    cpu = []
    for t in range(0, 181, 3):
        paused = fault == "search-pause" and applied - B0 <= t <= rev - B0
        cpu.append({"capturedAtEpoch": T0 + t + 0.25, "capturedAtMonotonic": B0 + t + 0.25, "containers": [
            {"service": s, "containerId": s, "cpuPercent": (0.0 if (paused and s == "search") else
                                                            5.0 + (0.1 if t % 2 else 0.0))} for s in METRIC_SVCS]})
    _w(d / "cpu.json", {"intervalSeconds": 3.0, "samples": cpu})
    smp = []
    for t in range(0, 185, 5):
        thr = fault == "profile-cpu-throttle" and t >= A - B0
        smp.append({"at": _iso(T0 + t), "monotonic": B0 + t, "services": {
            s: {"cpuUsageUsec": int(1e6 * 0.05 * t) + (1000 if (t // 5) % 2 else 0),
                "memoryCurrent": 10_000_000 + (4096 if (t // 5) % 2 else 0),
                "psiCpuSomeTotalUsec": 500 * (t // 5) + (300 if (t // 5) % 2 else 0) + (
                    int(1e5 * (t - (A - B0))) if (thr and s == "profile") else 0),
                "psiIoSomeTotalUsec": 0, "psiMemorySomeTotalUsec": 0, "rbytes": 0, "wbytes": 4096 * (t // 5)}
            for s in METRIC_SVCS}})
    _w(d / "system-samples.json", {"intervalSeconds": 5.0, "kind": "hotel-lmt-system-samples-v1", "samples": smp})
    return d


FAULT_CODE = {NF: 1, SP: 2, CT: 3, ND: 4}
FAULT_TARGET = {"search-pause": "search", "profile-cpu-throttle": "profile", "rate-net-delay": "rate"}


def make_main(root, docker_event=True):
    for b in (1, 2, 3, 4):
        for regime in (NF, SP, CT, ND):
            make_cell(root, regime, 1.0, b, OFFSETS[b - 1], docker_event=docker_event)
    return root


@pytest.fixture(scope="module")
def paths(tmp_path_factory):
    base = tmp_path_factory.mktemp("sweep_v2")
    main = make_main(base / "main")
    slow = base / "slow"                                  # 0.05/s: own pre-windows hold ~3 requests
    for b in (1, 2, 3, 4):
        make_cell(slow, NF, 0.05, b, off(0.05, b))
        make_cell(slow, ND, 0.05, b, off(0.05, b))
    fast = base / "fast"                                  # 10/s pause: the ledger's `absent` (reference setting)
    for b in (1, 2):
        make_cell(fast, NF, 10.0, b, off(10.0, b))
        make_cell(fast, SP, 10.0, b, off(10.0, b))
    quiet = base / "quiet"                                # 4 no-fault cells: K fit (outlier) and LOCO (rare template)
    for b in (1, 2, 3, 4):
        make_cell(quiet, NF, 1.0, b, OFFSETS[b - 1], outlier=(100, 734) if b == 1 else None,
                  extra_log="rare template" if b == 2 else None)
    noevent = base / "noevent"
    for b in (1, 2, 3, 4):
        make_cell(noevent, NF, 1.0, b, OFFSETS[b - 1])
        make_cell(noevent, SP, 1.0, b, OFFSETS[b - 1], docker_event=False)
    fastnd = base / "fastnd"                              # 10/s net delay: the ledger's `absent` (M1)
    for b in (1, 2):
        make_cell(fastnd, NF, 10.0, b, off(10.0, b))
        make_cell(fastnd, ND, 10.0, b, off(10.0, b))
    straddle = base / "straddle"                          # 1/s pause: b2 has a request that passed search (M5)
    for b in (1, 2):
        make_cell(straddle, NF, 1.0, b, OFFSETS[b - 1])
        make_cell(straddle, SP, 1.0, b, STRADDLE_OFFSET if b == 2 else OFFSETS[b - 1])
    offpath = base / "offpath"                            # 4 no-fault cells, one off-path outlier beyond every K (M3)
    for b in (1, 2, 3, 4):
        make_cell(offpath, NF, 1.0, b, OFFSETS[b - 1], user_spread=(7, 1_000_000 if b == 3 else None))
    fastnd4 = base / "fastnd4"                            # 4 blocks of 10/s net delay: a P4 verdict decision 57 moves
    for b in (1, 2, 3, 4):
        make_cell(fastnd4, NF, 10.0, b, off(10.0, b))
        make_cell(fastnd4, ND, 10.0, b, off(10.0, b))
    lostnd, lostnd4 = base / "lostnd", base / "lostnd4"   # 10/s net delay, first delayed search span lost (58)
    for b in (1, 2, 3, 4):
        for d in ((lostnd, lostnd4) if b <= 2 else (lostnd4,)):
            make_cell(d, NF, 10.0, b, off(10.0, b))
            make_cell(d, ND, 10.0, b, off(10.0, b), lose_first_delayed_search=True)
    return {"main": main, "slow": slow, "fast": fast, "quiet": quiet, "noevent": noevent, "fastnd": fastnd,
            "straddle": straddle, "offpath": offpath, "fastnd4": fastnd4, "lostnd": lostnd, "lostnd4": lostnd4}


# b2 of the straddle fixture: request 61 starts 10 ms before the pause, its search span ends 0.5 ms before it and the
# request completes 0.5 ms after it (latency 10.5 ms, search span ends 1 ms before the reply, so delta = 1 ms);
# request 62 is the first to time out. A = B0 + 60.1 + offset, pause = A + 0.25; request i starts at B0 + i + 0.002.
STRADDLE_OFFSET = 61 + 0.002 + 0.010 - 60.35


# ----------------------------------------------------------------------------- run cache (keyed by the switch state)

SWITCHES = ("POOLED", "MIN_POOLED_CHECK", "RELATIVE_FLOOR", "RESOLUTION_FLOOR", "LOCO", "SAME_REQUEST", "MARGIN_CHECK",
            "ACTUATOR_FLAG", "LEDGER_MISSED_APART", "P1_INTERVAL", "P3_RESTRICT", "EXPOSURE_TRACES", "FAR_MEETS",
            "LEDGER_ABSENT", "ABSENT_REARM", "P4_MUTED_DASH", "SAME_SILENCE", "MAD_ZERO_DASH",
            "SCORED_SET_CALIBRATION", "P1_AMBIGUITY", "SECONDARY_H4_SPLIT", "K_FIT_UNIT")
_CACHE = {}


def _state():
    return tuple(repr(getattr(v2, s)) for s in SWITCHES)


def R(path, compare=False):
    key = (str(path), compare, _state())
    if key not in _CACHE:
        _CACHE[key] = v2.run(path, compare=compare)
    return _CACHE[key]


def cells_of(path):
    key = ("cells", str(path), _state())
    if key not in _CACHE:
        _CACHE[key] = [v2.load_or_invalid(d) for d in v2.v1.find_cells(path)[1]]
    return _CACHE[key]


# ----------------------------------------------------------------------------- hand-built cells for unit checks

def _fam(ch, coll, posture):
    return {"log": "L", "span": "T", "metric": "M" if coll == "docker-stats" else "S"}.get(ch)


def hand_cell(prep, A=1060.0, B=1120.0, target="search", ledger=()):
    """Wall clock = monotonic + 1000; barrier at wall 1000."""
    return {"sut": "hotel", "posture": "full", "chans": {"log", "span", "metric", "ledger"}, "family": _fam,
            "t0": {"wall": 1000.0, "mono": 0.0}, "probes": {"wall": [], "mono": []},
            "cmd": {"A": {"wall": A, "mono": A - 1000.0}, "B": {"wall": B, "mono": B - 1000.0}},
            "target": target, "ledger": list(ledger), "prep": prep}


def hand_fit(level=None, count=None, res=None, rate=1.0):
    fake = {"rate": rate, "segLevel": level or {}, "segCount": count or {}, "segRes": res or {}}
    return v2.Fit([fake], rate, res_cells=[fake])


SPAN_META = {"clock": "wall", "collector": "jaeger", "level": None}
KEY_U = ("span", "user", "/user.User/CheckUser")


def check_h1_tiny_baseline():
    """v1: three identical pre-onset durations (MAD 0) and the 1 ms floor make an ordinary +1.2 ms value a spike.
    v2: the pooled fault-free baseline (60 values, MAD 0.5 ms) does not."""
    obs = [1010.0, 1030.0, 1050.0, 1070.0]
    vals = [0.005, 0.005, 0.005, 0.0062]
    c = hand_cell({KEY_U: (obs, vals, SPAN_META)})
    pooled = [0.004 + 0.002 * (i % 21) / 20 for i in range(60)] + vals[:3]
    fires, _, _, _ = v2.eval_episode(c, hand_fit({KEY_U: pooled}, res={("span",): 1e-6}), {"T": v2.K_REF},
                                     v2.ARMS["primary"], False)
    v2_ok = not any(f["rule"] == "spike" for f in fires)
    old, _, _ = sa1.eval_window(c, c["cmd"]["A"], c["cmd"]["B"], False, 4.0, 1.0)
    return v2_ok, any(f["rule"] == "spike" and f["tok"] == KEY_U[2] for f in old)


def check_h1_min20():
    """n = 19 pooled points: no level verdict (—), even for a large shift; 20 points: a verdict (MAD > 0)."""
    obs = [1050.0 + i for i in range(20)]
    vals = [0.001] * 10 + [0.1] * 10
    c = hand_cell({KEY_U: (obs, vals, SPAN_META)})
    base = [0.001 + 1e-5 * (i % 3) for i in range(19)]
    f19 = v2.eval_episode(c, hand_fit({KEY_U: base}), {"T": v2.K_REF}, v2.ARMS["primary"], False)[0]
    f20 = v2.eval_episode(c, hand_fit({KEY_U: base + [0.001]}), {"T": v2.K_REF}, v2.ARMS["primary"], False)[0]
    return not any(f["rule"] == "spike" for f in f19) and any(f["rule"] == "spike" for f in f20)


KEY_F = ("span", "frontend", "HTTP_GET_/hotels")


def check_floor_relative():
    """Median 100 ms, MAD 0.05 ms, +3 ms in the window: v2's 10 % floor (10 ms) holds it; v1's 1 ms floor fires."""
    base = [0.1 + (0.00005 if i % 2 else -0.00005) for i in range(40)]
    c = hand_cell({KEY_F: ([1061.0, 1062.0], [0.103, 0.103], SPAN_META)})
    fires = v2.eval_episode(c, hand_fit({KEY_F: base}, res={("span",): 1e-6}), {"T": v2.K_REF},
                            v2.ARMS["primary"], False)[0]
    c1 = hand_cell({KEY_F: ([1000.0 + i for i in range(40)] + [1061.0, 1062.0], base + [0.103, 0.103], SPAN_META)})
    old = sa1.eval_window(c1, c1["cmd"]["A"], c1["cmd"]["B"], False, 4.0, 1.0)[0]
    return not any(f["rule"] == "spike" for f in fires), any(f["rule"] == "spike" for f in old)


KEY_P = ("metric", "rate", "sys_psi_io")
PSI_META = {"clock": "wall", "collector": "cgroup-sampler", "level": None}


def check_floor_resolution():
    """Median 0, MAD 1 (K x 1.4826 x MAD = 5.9 at K = 4), a resolution of 50 between distinct fault-free values (from
    another segment of the fit): 25 is below the resolution, 50 is a catch. Without the resolution term 25 fires."""
    base = [0.0] * 20 + [1.0] * 10 + [-1.0] * 10
    seg = {"rate": 1.0, "segLevel": {KEY_P: base}, "segCount": {}, "segRes": {("metric", "cgroup-sampler", "sys_psi_io"): 50.0}}
    fit = v2.Fit([seg], 1.0, res_cells=[seg])
    lo = v2.eval_episode(hand_cell({KEY_P: ([1065.0], [25.0], PSI_META)}), fit, {"S": v2.K_REF}, v2.ARMS["primary"], False)[0]
    hi = v2.eval_episode(hand_cell({KEY_P: ([1065.0], [50.0], PSI_META)}), fit, {"S": v2.K_REF}, v2.ARMS["primary"], False)[0]
    return not lo and any(f["rule"] == "spike" for f in hi) and v2.min_positive_gap([0.0, 0.0, 50.0, 125.0]) == 50.0


def check_absent_rearm():
    """A stream silent at onset that resumes and goes silent again: v2 catches the second silence; dbebcbb gave no
    verdict for a stream silent at the window start."""
    rec = [1000.0 + i for i in range(50)] + [1070.0 + i for i in range(10)]   # silent 1049-1070, then until 1079
    g = 2.0
    return v2.first_silence(rec, 1000.0, 1060.0, 1120.0, g) == 1081.0 and \
        v2.silences(rec, 1000.0, 1000.0, 1120.0, g) == [1051.0, 1081.0]


def _cdf_logsum(k, lam):
    logs = [i * math.log(lam) - lam - math.lgamma(i + 1) for i in range(k + 1)]
    top = max(logs)
    return math.exp(top) * math.fsum(math.exp(x - top) for x in logs)


def check_poisson():
    """Exact bounds (Hanley's rule of three at k = 0); the incomplete-gamma CDF equals a log-space sum, and large
    counts stay correct where exp(-lam) underflows (dbebcbb's poisson_ge)."""
    if any(abs(v2.poisson_cdf(k, lam) - _cdf_logsum(k, lam)) > 1e-10
           for k in (0, 1, 3, 10, 200, 2000) for lam in (0.5, 2.0, k + 0.5, 2.0 * k + 5)):
        return False
    big = v2.poisson_upper(2000)
    return abs(v2.poisson_upper(0) / 0.2 - 14.9787) < 1e-3 and abs(v2.poisson_upper(3) / 0.2 - 38.768) < 1e-2 and \
        abs(v2.poisson_upper(1) - 4.7439) < 1e-3 and 2070.0 < big < 2080.0 and \
        abs(v2.poisson_cdf(3, 2.0) - 0.857123) < 1e-6 and abs(v2.poisson_cdf(2000, big) - 0.05) < 1e-9


def check_far_restart_equivalence():
    """The distinct-instant count equals an explicit restart-after-alarm loop over the episode rules (spike, run3,
    median from dt.level_rules; appear with the cell's own history; re-armed absent)."""
    lv = [1000.0 + 0.5 * i for i in range(360)]
    vals = [0.01 + (0.0001 if i % 2 else 0.0) for i in range(360)]
    for j in (37, 38, 39, 120, 121, 300):
        vals[j] = 0.02
    cnt = [1000.0 + 3 * i for i in range(30)] + [1100.0 + 3 * i for i in range(20)] + [1170.0]
    X = hand_cell({KEY_F: (lv, vals, SPAN_META), ("log", "frontend", "rare"): ([1033.3, 1044.4], [1.0, 1.0],
                                                                                {"clock": "wall", "level": "info"}),
                   ("log", "frontend", "beat"): (cnt, [1.0] * len(cnt), {"clock": "wall", "level": "info"})})
    X.update({"end": {"wall": 1180.0, "mono": 180.0}, "wsLogs": False})
    fit = hand_fit({KEY_F: [0.01 + (0.0001 if i % 2 else 0.0) for i in range(40)]},
                   {("log", "frontend", "beat"): (40, 3.0, 40), KEY_F: (40, 0.5, 40)}, {("span",): 1e-6})
    fixed, level = v2.quiet_events(X, fit, v2.ARMS["primary"])
    k = v2.K_GRID.index(v2.K_REF)
    fast = v2.alarm_counts(*v2.merge_events([(fixed.get(f, {}), level.get(f, [])) for f in ("T", "L")]))[k]
    m, thr = v2.threshold(fit.level[KEY_F], v2.K_REF, v2.ARMS["primary"], 1e-6)
    t, n = None, 0
    while True:                                   # the OR of every rule, restarted after each alarm
        cands = []
        ia = 0 if t is None else next((i for i, x in enumerate(lv) if x > t), len(lv))
        got = dtm.level_rules(lv[ia:], vals[ia:], m, thr, ("up",))
        cands += [x for x, _ in got.values()]
        own = [x for x in (1033.3, 1044.4) if t is not None and x <= t]
        first = [x for x in (1033.3, 1044.4) if t is None or x > t]
        if not own and first:
            cands.append(first[0])
        for rec, g in ((cnt, 2 * 3.0), (lv, 2 * 0.5)):
            cands += [x for x in v2.silences(rec, 1000.0, 1000.0, 1180.0, g) if t is None or x > t]
        if not cands:
            break
        t, n = min(cands), n + 1
    return fast == n == 10                         # 6 spikes, 1 appear, 3 silences


def check_alignment(paths):
    c = cells_of(paths["main"])[0]
    return abs(c["align"]["offset"] - OFF) < 2e-6 and c["align"]["residual"] < 6e-6 and c["align"]["pairs"] == 360


def check_receipt_bound(paths):
    """Per cell max(Docker stamp - app second): the fixture's lines give fractional part + 0.0003."""
    c = next(x for x in cells_of(paths["main"]) if x["regime"] == SP)
    worst = 0.0
    for line in (ROOT / c["cell"] if not Path(c["cell"]).is_absolute() else Path(c["cell"])).joinpath(
            "application.log").read_text().splitlines():
        if " | " in line and "{" in line:
            o = json.loads(line.split(" ", 4)[-1])
            d = sa1.docker_stamp(line.split(" | ", 1)[1])[0]
            worst = max(worst, d - dtm.epoch(o["time"]))
    b = c["logReceipt"]["bound"]
    return b is not None and abs(b - worst) < 1e-6 and RECEIPT <= b and c["logReceipt"]["dockerDigits"] == 9


# ----------------------------------------------------------------------------- operating point

def check_loco(paths):
    """A template present in one no-fault cell only: held out, that cell raises an `appear` alarm (L, 1/s), in every
    class's scored set and in the all-sensors count. Fitted with the cell itself (no LOCO) the alarm disappears."""
    op = v2.operating_point(cells_of(paths["quiet"]), v2.ARMS["primary"])
    ts = [op["table"]["L"][g][1.0] for g in (SP, CT, ND)] + [op["allSensors"]["table"]["L"][1.0]]
    return all(t["perK"][0]["alarms"] == 1 and any("appear" in s for s in t["atLargestK"]) for t in ts)


def check_k_fit(paths):
    """One memcached duration (rate's span) 7.2 x 1.4826 x MAD above the median in 0.2 h of quiet time: certified
    (bound <= 15/h) first at K = 8 (0 alarms) where rate is on the affected path (pause of search, delay of rate); the
    point estimate (1 alarm = 5/h) would already meet at 2.5. One K per family (decision 53): T = 8."""
    op = v2.operating_point(cells_of(paths["quiet"]), v2.ARMS["primary"])
    t = op["table"]["T"][SP][1.0]
    return (t["minKCertified"] == 8.0 and t["minKPoint"] == 2.5 and op["table"]["T"][ND][1.0]["minK"] == 8.0
            and op["fitted"]["T"]["K"] == 8.0 and op["fitted"]["E"]["K"] == 2.5 and op["fitted"]["system"]["K"] is None
            and abs(t["quietHours"] - 0.2) < 1e-9 and op["allSensors"]["table"]["T"][1.0]["minK"] == 8.0)


# ----------------------------------------------------------------------------- end to end on the main fixture

def _eps(Rr, regime, setting="primary"):
    return [e for e in Rr["results"][setting]["eps"] if e["regime"] == regime]


def check_kmaps(paths):
    Rr = R(paths["main"])
    return all(Rr["kmaps"]["primary"][g][1.0] == {f: 2.5 for f in v2.FAMILIES} for g in (SP, CT, ND))


def check_ledger_absent(paths):
    """10/s pause: the ledger's silence (`absent` on completions, H3 e) fires ~0.4 s after onset, before any timeout
    (> 1 s); dbebcbb's ledger rules have no `absent`."""
    Rr = R(paths["fast"])
    ok = True
    for e in _eps(Rr, SP, "reference"):
        f = v2.col_fire(e, "E", True)
        ok &= f is not None and f["rule"] == "absent" and f["ttd"] < 0.6
        old, _, _ = dtm.ledger_rules(e["_c"]["ledger"], e["onset"]["mono"], e["end"]["mono"], rules=dtm.E_RULES)
        ok &= min(t for t in old.values()) - e["onset"]["mono"] > 1.0
    return ok


def check_pooled_end_to_end(paths):
    """0.05/s net delay: the ledger's own pre-window holds ~3 requests (< 20, no level verdict), the pooled baseline
    holds ~48, so E catches the delayed request by `spike`."""
    Rr = R(paths["slow"])
    eps = _eps(Rr, ND)
    return len(eps) == 4 and all((v2.col_fire(e, "E", True) or {}).get("rule") == "spike" for e in eps)


def check_actuator(paths):
    """cpu-throttle: the throttled target's PSI is flagged BC-actuator-readback (decision 26); v1 does not flag it."""
    Rr = R(paths["main"])
    fl = [f for e in _eps(Rr, CT) for f in e["fires"] if f["svc"] == "profile" and f["tok"] == "sys_psi_cpu"]
    v1flags = [sa1.bc_flags(f, "profile", "degradation", Rr["ctx"], {}, "content") for f in fl]
    return bool(fl) and all("BC-actuator-readback" in f["bc"] for f in fl) and not any(
        "BC-actuator-readback" in x for x in v1flags)


def check_same_request_e2e(paths):
    """net delay at 1/s: search's span (P4a) and rate's memcached span (P4b) end before the client sees the reply of
    the SAME request; both are leads, neither is a win. v1's rule (strictly lower) counts them."""
    Rr = R(paths["main"])
    ok = True
    for scope in ("P4a", "P4b"):
        v = Rr["predictions"]["P4"][scope][ND]["perRate"]["1"]
        ok &= v["wins"] == 0 and all(fo["sameRequest"] for fo in v["folds"] if fo["category"] == "same request")
        ok &= sum(fo["category"] == "same request" for fo in v["folds"]) >= 3
        ok &= sum(fo["v1StyleWin"] for fo in v["folds"]) >= 3
    return ok


def check_p1(paths):
    """Block 4's first request after the command completes inside [command, pause event] (ambiguous); the next one
    times out. v2's interval holds in 4/4; v1's point expectation fails block 4 by ~1 s."""
    Rr = R(paths["main"])
    p = Rr["predictions"]["P1"]
    b4 = next(x for x in p["perEpisode"] if x["block"] == 4)
    on = next(e for e in _eps(Rr, SP) if e["block"] == 4)["_c"]["onset"]
    return (p["k"] == 4 and p["n"] == 4 and p["holds"] is True and b4["requestClasses"].get("straddling", 0) >= 1
            and abs(on["hi"] - (on["lo"] + 0.25)) < 1e-5)


def check_p1_v1_fails(paths):
    old = v2.v1.run(paths["main"], grid=[v2.v1.REF], variants=False)["reference"]["predictions"]["P1"]
    return [x["ok"] for x in sorted(old["perEpisode"], key=lambda x: x["block"])] == [True, True, True, False]


def check_p1_no_event(paths):
    p = R(paths["noevent"])["predictions"]["P1"]
    return p["n"] == 0 and p["notEvaluable"] == 4 and p["holds"] is None


def check_exposure(paths):
    ex = R(paths["main"])["exposure"]
    return ("memcached-rate" in ex["routePath"] and "mongodb-rate" in ex["routePath"] and "user" not in ex["routePath"]
            and "profile" not in ex["routePath"] and "consul" not in ex["routePath"]
            and "user" in ex["neverExposedServices"] and "span:user:/user.User/CheckUser" in ex["neverExposedSensors"]
            and all(v["requestsStartedInWindow"] >= 1 for v in ex["episodes"].values()))


def check_p3(paths):
    p = R(paths["main"])["predictions"]["P3"]
    return [x["state"] for x in p] == [v2.DASH] * 3 and all("traffic-independent" in x["reason"] for x in p)


def check_p2(paths):
    p = R(paths["main"])["predictions"]["P2"]["1"]
    return p["holds"] is True and p["perEpisode"] == [2, 2, 2, 2]


# ----------------------------------------------------------------------------- H3 unit checks (judge_fold)

def judge_cell(**kw):
    c = {"ledgerStamps": {"monoGranularity": 1e-9}, "align": {"residual": 2e-6},
         "logReceipt": {"bound": 0.9, "servicesWithoutAppStamp": [], "dockerDigits": 9}, "wsLogs": False, "prep": {},
         "spanTok": {}, "logTok": {}, "ledgerTok": {}}
    c.update(kw)
    return c


def _fire(ch, svc, tok, rule, ttd, t, family):
    return {"ch": ch, "svc": svc, "tok": tok, "rule": rule, "ttd": ttd, "tObs": t, "family": family, "movedBy": 0.0}


LEDGER_FIRE = _fire("ledger", "frontend", "r", "failed", 1.0, 200.0, "E")


def check_margin():
    """A log 0.2 s ahead of the ledger, receipt-delay bound 0.9 s: inside the margin, no win (v1: a win)."""
    j = v2.judge_fold(_fire("log", "frontend", "tplA", "appear", 0.8, 100.0, "L"), LEDGER_FIRE, 60.0, judge_cell())
    return j["category"] == "lead within the margin" and not j["win"] and j["v1StyleWin"] and \
        abs(j["margin"] - (0.9 + 2e-6 + 2e-9)) < 1e-9 and abs(j["marginAvailability"] - (2e-6 + 2e-9)) < 1e-12 \
        and j["winAvailability"] is True


def check_same_request_unit():
    c = judge_cell(spanTok={("search", "op"): {100.0: {"hr-a"}}}, ledgerTok={200.0: {"hr-a"}})
    j = v2.judge_fold(_fire("span", "search", "op", "spike", 0.9, 100.0, "T"), LEDGER_FIRE, 60.0, c)
    k = v2.judge_fold(_fire("span", "search", "op", "spike", 0.9, 100.0, "T"), LEDGER_FIRE, 60.0,
                      judge_cell(spanTok={("search", "op"): {100.0: {"hr-b"}}}, ledgerTok={200.0: {"hr-a"}}))
    return j["category"] == "same request" and not j["win"] and k["win"] and k["winAvailability"] is None


def check_ledger_missed():
    j = v2.judge_fold(_fire("metric", "profile", "cpu", "spike", 3.0, 100.0, "M"), None, 60.0, judge_cell())
    return j["category"].startswith("ledger missed") and not j["win"] and j["ledgerMissed"] and j["v1StyleWin"]


def check_no_app_stamp():
    c = judge_cell(logReceipt={"bound": 0.9, "servicesWithoutAppStamp": ["consul"], "dockerDigits": 9})
    j = v2.judge_fold(_fire("log", "consul", "tpl", "appear", 0.1, 100.0, "L"), LEDGER_FIRE, 60.0, c)
    return j["category"] == "log lead not counted (no app stamp)" and not j["win"]


def _ep(block, fires, kmap=None):
    c = judge_cell(chans={"ledger", "span"}, channelsPresent={"span": True})
    for f in fires:
        f.setdefault("admissible", True)
        f.setdefault("counts", True)
        f.setdefault("own", False)
        f.setdefault("bc", [])
    return {"cell": "c%d" % block, "regime": SP, "rate": 1.0, "block": block, "holdSeconds": 60.0, "fires": fires,
            "kmap": kmap or {f: 2.5 for f in v2.FAMILIES}, "_c": c}


def check_tied():
    """Two sensors with equal training means: the name-order choice is recorded with the win share of the tie."""
    eps = []
    for b in (1, 2, 3, 4):
        eps.append(_ep(b, [dict(LEDGER_FIRE),
                           _fire("span", "geo", "a", "spike", 0.5, 100.0 + b, "T"),
                           _fire("span", "geo", "b", "spike", 0.5 if b < 4 else 2.0, 100.0 + b, "T")]))
    row = v2.p4(eps, False, False)[SP]["perRate"]["1"]
    f4 = row["folds"][3]
    f1 = row["folds"][0]
    return f1["tied"] == ["span:geo:a"] and f1["tiedWinShare"] == [1, 1] and \
        f4["tied"] == ["span:geo:a", "span:geo:b"] and f4["tiedWinShare"] == [1, 2] and row["wins"] == 4


# ----------------------------------------------------------------------------- v2 itself, for the round-11 contrasts

V2_REV, V2_REGISTRY_REV, V2_TESTS_REV = "32e3178", "ac313f1", "c770a6d"
_OLD = {}


def git_show(rev, rel):
    got = subprocess.run(["git", "-C", str(ROOT), "show", "%s:%s" % (rev, rel)], capture_output=True)
    if got.returncode != 0:
        pytest.skip("git history not available")
    return got.stdout.decode()


def old_v2():
    """sweep_analysis_v2.py as it was at 32e3178 (v2 = 87b04ef + the reason-text fix), executed as its own module on
    the current registry (every entry it reads is unchanged in name and value)."""
    if "mod" not in _OLD:
        mod = types.ModuleType("sweep_analysis_v2_at_" + V2_REV)
        mod.__file__ = str(ROOT / "research" / "detection-time" / "sweep_analysis_v2.py")
        exec(compile(git_show(V2_REV, "research/detection-time/sweep_analysis_v2.py"), "v2@" + V2_REV, "exec"),
             mod.__dict__)
        _OLD["mod"] = mod
    return _OLD["mod"]


def old_registry():
    return {p["name"]: p for p in json.loads(git_show(V2_REGISTRY_REV, "research/protocol/parameters.json"))["parameters"]}


def R_old(path):
    key = ("old", str(path))
    if key not in _CACHE:
        _CACHE[key] = old_v2().run(path, compare=False)
    return _CACHE[key]


def safely(fn, *a):
    """A round-11 check run on v2: a structure v2 does not have counts as the check failing."""
    try:
        return bool(fn(*a))
    except (KeyError, AttributeError, TypeError):
        return False


# ----------------------------------------------------------------------------- B1 (decision 55)

def b1_eps():
    """Four pause episodes at 1/s, T collected but not at the operating point (kmap T None): the ledger catches, no
    sensor family at the operating point has a candidate."""
    return [_ep(b, [dict(LEDGER_FIRE)], kmap=dict({f: 2.5 for f in v2.FAMILIES}, T=None)) for b in (1, 2, 3, 4)]


def check_b1(m):
    row = m.p4(b1_eps(), False, False)[SP]["perRate"]["1"]
    hr = m.highest_rate({10.0: {"holds": None}, 1.0: {"holds": True}, 0.2: {"holds": False}, 0.05: {"holds": False}})
    none = m.highest_rate({10.0: {"holds": None}, 1.0: {"holds": False}, 0.2: {"holds": False}, 0.05: None})
    alld = m.highest_rate({r: {"holds": None} for r in v2.RATES})
    return (row["holds"] is None and row["wins"] is None and "T" in row["note"]
            and not any(fo.get("category") == "sensor missed" for fo in row["folds"])
            and hr == "1; — at {10}" and none == "none in {1, 0.2}; — at {10, 0.05}"
            and alld == "— at {10, 1, 0.2, 0.05}")


# ----------------------------------------------------------------------------- M1 (decision 51)

def check_same_silence_unit(m):
    """The ledger's `absent` names the request that ends its silence; a span catch on that request is same-request."""
    fE = dict(_fire("ledger", "frontend", "r", "absent", 1.0, 200.0, "E"), silenceTokens=["hr-a"], silenceEndedBy=200.5)
    c = judge_cell(spanTok={("rate", "memcached_get"): {100.0: {"hr-a"}}})
    j = m.judge_fold(_fire("span", "rate", "memcached_get", "spike", 0.9, 100.0, "T"), fE, 60.0, c)
    k = m.judge_fold(_fire("span", "rate", "memcached_get", "spike", 0.9, 100.0, "T"), fE, 60.0,
                     judge_cell(spanTok={("rate", "memcached_get"): {100.0: {"hr-b"}}}))
    return j["category"] == "same request" and not j["win"] and k["win"]


def check_same_silence_e2e(paths, old=False):
    """10/s net delay (reference K, the only setting where every family has a K on this 0.1 h fixture): the ledger's
    first catch is `absent`, ~5-8 ms after rate's memcached span of the first delayed request ends; that request is
    the completion that ends the silence, so both folds are same-request (v2: wins)."""
    Rr = R_old(paths["fastnd"]) if old else R(paths["fastnd"])
    v = Rr["results"]["reference"]["P4"]["P4b"][ND]["perRate"]["10"]
    ok = len(v["folds"]) == 2 and all(
        fo["ledgerRule"] == "absent" and fo["category"] == "same request" and fo["lead"] > fo["margin"]
        and fo.get("sameSilence") for fo in v["folds"])
    for e in [x for x in Rr["results"]["reference"]["eps"] if x["regime"] == ND]:
        fE = v2.col_fire(e, "E", True)
        c = e["_c"]
        row = next((r for r in c["ledger"] if r.end == fE.get("silenceEndedBy")), None)
        first_delayed = min((r for r in c["ledger"] if r.end - r.start > 0.2), key=lambda r: r.start)
        ok &= row is not None and fE["rule"] == "absent" and fE.get("silenceTokens") == [row.token] \
            and row == first_delayed
    return ok


# ----------------------------------------------------------------------------- M2 (decision 52)

def check_mad_zero(m):
    """MAD = 0 (39 zeros and one 50): v2 scored 50 against the resolution floor (a spike); v2.1 lists the sensor and
    gives its level rules —, in an episode and on held-out quiet time. A span with MAD = 0 keeps `absent`."""
    seg = {"rate": 1.0, "segLevel": {KEY_P: [0.0] * 39 + [50.0], KEY_U: [0.005] * 40},
           "segCount": {KEY_U: (40, 1.0, 40)}, "segRes": {("metric", "cgroup-sampler", "sys_psi_io"): 50.0}}
    fit = m.Fit([seg], 1.0, res_cells=[seg])
    c = hand_cell({KEY_P: ([1065.0], [50.0], PSI_META),
                   KEY_U: ([1000.0 + i for i in range(63)], [0.005] * 60 + [0.009] * 3, SPAN_META)})
    fires = m.eval_episode(c, fit, {"S": m.K_REF, "T": m.K_REF}, m.ARMS["primary"], False)[0]
    X = hand_cell({KEY_P: ([1010.0, 1020.0], [0.0, 50.0], PSI_META)})
    X.update({"end": {"wall": 1180.0, "mono": 180.0}, "wsLogs": False})
    _, level = m.quiet_events(X, fit, m.ARMS["primary"])
    return (not any(f["rule"] in ("spike", "run3", "median") for f in fires)
            and any(f["rule"] == "absent" and f["tok"] == KEY_U[2] for f in fires)
            and KEY_P in getattr(fit, "madZero", ()) and KEY_U in fit.madZero and not level.get("S"))


# ----------------------------------------------------------------------------- M3 (decision 55)

KEY_UC = ("metric", "user", "cpu")                 # on no affected path
KEY_SC = ("metric", "search", "cpu")               # on the pause's path; a CPU drop under a pause is BC-idle-cpu
KEY_FS = ("span", "frontend", "HTTP_GET_/hotels")  # on every path
M_META = {"clock": "wall", "collector": "docker-stats", "level": None}


def hand_ctx():
    edges, on_route = dtm.call_graph("hotel")
    return {"edges": edges, "onRoute": on_route, "ops": {}}


def m3_cell():
    """Held-out quiet cell, 3 s cadence on [1000, 1180]: user CPU (off-path): an isolated spike, then a run of three,
    then a dip; search CPU: a dip, an up-spike, a run of three up; frontend span: two spikes."""
    t = [1000.0 + 3 * i for i in range(61)]
    uc = [5.0] * 61
    for j in (5,):
        uc[j] = 7.0
    for j in (20, 21, 22):
        uc[j] = 7.0
    uc[40] = 3.0
    sc = [5.0] * 61
    sc[10] = 3.0
    sc[15] = 7.0
    for j in (30, 31, 32, 50):
        sc[j] = 7.0
    ft = [1000.5 + 0.5 * i for i in range(360)]
    fv = [0.01] * 360
    fv[50] = fv[300] = 0.02
    X = hand_cell({KEY_UC: (t, uc, M_META), KEY_SC: (t, sc, M_META), KEY_FS: (ft, fv, SPAN_META)})
    X.update({"end": {"wall": 1180.0, "mono": 180.0}, "wsLogs": False, "logText": {}})
    base = [4.9, 5.0, 5.1] * 14
    fit = hand_fit({KEY_UC: base, KEY_SC: base, KEY_FS: [0.0099, 0.01, 0.0101] * 14}, res={("span",): 1e-6})
    return X, fit


def brute_force_alarms(X, fit, share, regime, ctx, i, fams):
    """Independent restart loop for the scored detector of `regime`: per sensor-rule, the episode detector's first
    fire after the last alarm (dt.level_rules on the samples after it; appear = first record of a token the fit never
    saw; absent = the next silence), kept if dt.scored and bc_of admit it as in an episode of that class."""
    target, kind = v2.FAULT_TARGETS[regime]
    path = v2.v1.path_of(target, ctx)
    pseudo = {"target": target, "faultKind": kind, "logText": X.get("logText", {})}

    def admitted(f):
        return dtm.scored(f, target, path, v2.ENTRY)[0] and not v2.bc_of(f, pseudo, ctx, regime)
    t, n = None, 0
    while True:
        cands = []
        for key, (obs, vals, meta) in X["prep"].items():
            ch, svc, tok = key
            if v2.family_of(X, ch, meta) not in fams:
                continue
            t0, end = X["t0"][meta["clock"]], X["end"][meta["clock"]]
            base = {"ch": ch, "svc": svc, "tok": tok, "level": meta.get("level")}
            inside = [j for j, x in enumerate(obs) if t0 <= x <= end]
            later = [j for j in inside if t is None or obs[j] > t]
            if ch in ("log", "span"):
                if fit.novel(key) and inside and (t is None or obs[inside[0]] > t) and admitted(
                        dict(base, rule="appear", dir=None)):
                    cands.append(obs[inside[0]])
                g = fit.gap(key) if not tok.endswith(":error") else None
                if g is not None:
                    xs = [x for x in v2.silences(obs, t0, t0, end, g) if t is None or x > t]
                    if xs and admitted(dict(base, rule="absent", dir=None)):
                        cands.append(xs[0])
            if ch == "metric" or (ch == "span" and not tok.endswith(":error")):
                lv = fit.lvl(key)
                if lv is None:
                    continue
                m, thr = v2.threshold(lv, v2.K_GRID[i], share, fit.res.get(v2.instrument(ch, meta, tok)))
                if thr <= 0:
                    continue
                got = dtm.level_rules([obs[j] for j in later], [vals[j] for j in later], m, thr,
                                      ("up", "down") if ch == "metric" else ("up",))
                cands += [x for rule, (x, d) in got.items() if admitted(dict(base, rule=rule, dir=d))]
        if not cands:
            return n
        t, n = min(cands), n + 1


def check_restart_simulation():
    """restart_count (the M3 detector, with admission) equals the brute-force restart loop for every class, for M, T
    and the system group, at every grid K; with everything admitted it equals the distinct-instant count."""
    X, fit = m3_cell()
    ctx, share = hand_ctx(), v2.ARMS["primary"]
    fixed, level = v2.quiet_material(X, fit, share)
    ev = v2.event_lists(fixed, level)
    ok = True
    for regime in (SP, CT, ND):
        fok, lok = v2.admission(fixed, level, regime, ctx, X)
        for g, fams in (("M", ("M",)), ("T", ("T",)), ("system", v2.SENSOR_FAMILIES)):
            for i in range(len(v2.K_GRID)):
                ok &= v2.restart_count(ev[g], fixed, level, fok, lok, i) == brute_force_alarms(
                    X, fit, share, regime, ctx, i, fams)
    fa, la = v2.admit_all(fixed, level)
    fx, lv = v2.quiet_events(X, fit, share)
    for g, fams in (("M", ("M",)), ("T", ("T",)), ("system", v2.SENSOR_FAMILIES)):
        dist = v2.alarm_counts(*v2.merge_events([(fx.get(f, {}), lv.get(f, [])) for f in fams]))
        ok &= [v2.restart_count(ev[g], fixed, level, fa, la, i) for i in range(len(v2.K_GRID))] == dist
    # the classes differ where they should: user's CPU spikes never count (off-path), its run of three does
    k = v2.K_GRID.index(v2.K_REF)
    fok, lok = v2.admission(fixed, level, CT, ctx, X)
    fa_m = v2.restart_count(ev["M"], fixed, level, fa, la, k)
    return ok and v2.restart_count(ev["M"], fixed, level, fok, lok, k) < fa_m


def check_calibration_is_scored(paths, m):
    """The calibrated count of class cpu-throttle (target profile) for T at K = 2.5 equals the brute-force count of
    that class's scored detector on the four held-out quiet cells: the memcached outlier is on rate, off profile's
    path, so its spike never counts. v2 counted it (one count for every class)."""
    cells = cells_of(paths["quiet"]) if m is v2 else [m.load_or_invalid(d) for d in m.v1.find_cells(paths["quiet"])[1]]
    op = m.operating_point(cells, m.ARMS["primary"])
    mine = cells_of(paths["quiet"])
    fits, ctx = v2.loco_fits(mine), v2.v1.make_ctx([c for c in mine if c["valid"]])
    bf = sum(brute_force_alarms(X, fits[id(X)], v2.ARMS["primary"], CT, ctx, 0, ("T",)) for X in mine
             if X["valid"] and X["target"] is None)
    t = op["table"]["T"]
    got = t[CT][1.0] if CT in t else t[1.0]
    return got["perK"][0]["alarms"] == bf == 0


def check_k_per_class(paths, m=None):
    """One user span (on no affected path) lasts 1 s in one quiet cell: beyond every grid K on all sensors (v2: T never
    at the operating point), never a counted alarm on any class's scored set (v2.1: T at the operating point)."""
    m = m or v2
    cells = cells_of(paths["offpath"]) if m is v2 else [m.load_or_invalid(d) for d in m.v1.find_cells(paths["offpath"])[1]]
    op = m.operating_point(cells, m.ARMS["primary"])
    km = m.kmaps_from(op, [1.0])
    ts = [km[g][1.0]["T"] for g in (SP, CT, ND)] if SP in km else [km[1.0]["T"]]
    return all(k is not None for k in ts)


# ----------------------------------------------------------------------------- M4 (decision 53)

def check_k_unit_family(paths):
    op = v2.operating_point(cells_of(paths["quiet"]), v2.ARMS["primary"])
    return all(v2.kmaps_from(op, [1.0])[g][1.0]["T"] == 8.0 for g in (SP, CT, ND))


def check_k_unit_decided(reg):
    e = reg["K_FIT_UNIT"]
    return e["value"] == "family" and e["origin_type"] == "decision" and "decision 53" in e["origin_ref"]


# ----------------------------------------------------------------------------- M5 (decision 54)

def check_p1_ambiguity(Rr):
    """b2: request 61 passed search 0.5 ms before the pause and completed 0.5 ms after it; delta = 1 ms puts it in the
    ambiguity window, so the latest expected timeout is request 62's. v2 expected request 61's and failed b2."""
    p = Rr["predictions"]["P1"]
    b2 = next(x for x in p["perEpisode"] if x["block"] == 2)
    return (p["holds"] is True and p["k"] == p["n"] == 2 and abs(b2["delta"] - 0.001) < 2e-5
            and b2["ambiguous"] >= 1 and b2["deltaRequests"] >= 50)


def check_p1_decided(reg):
    t, a = reg.get("P1_TOLERANCE_RULE"), reg.get("P1_AMBIGUITY_WINDOW_RULE")
    return bool(t and a) and all(x["origin_type"] == "decision" and "decision 54" in x["origin_ref"]
                                 and "BEFORE ANY TeaStore OR OTel CELL IS READ" in x["origin_ref"] for x in (t, a))


# ----------------------------------------------------------------------------- minors

def absent_gap_ok(Rr, J):
    """Every rate's statement agrees with the gap and timeout recomputed from the fits and the cells."""
    ok = bool(J["absentGap"])
    for r, x in J["absentGap"].items():
        f = Rr["fits"][float(r)]
        T = {c["timing"]["requestTimeoutSeconds"] for c in Rr["cells"] if c["valid"] and c["rate"] == float(r)}
        for route, g in x["gapSeconds"].items():
            g2 = f.gap(("ledger", v2.ENTRY, route + v2.COMPLETIONS))
            ok &= g == g2 and x["gapBelowTimeout"][route] == (g2 < min(T))
    return ok


def check_absent_gap(paths):
    """At 10/s the gap (~0.2 s) is below the 1 s timeout; at 1/s (2 s) it is not. The readout says so per rate and
    makes no blanket 'before any timeout' claim (v2's DEFAULTS did)."""
    out = []
    for name in ("fast", "main"):
        Rr = R(paths[name], compare=True)
        J = v2.build_json(Rr)
        md = v2.render(Rr, J)
        out.append((absent_gap_ok(Rr, J), md, J))
    (ok10, md10, J10), (ok1, md1, J1) = out
    return (ok10 and ok1 and "before any timeout" not in md10 + md1
            and "(can fire before a timeout)" in md10 and "(cannot fire before a timeout)" in md1
            and list(J10["absentGap"]["10"]["gapBelowTimeout"].values()) == [True]
            and list(J1["absentGap"]["1"]["gapBelowTimeout"].values()) == [False])


def check_secondary_h4(paths, m=None):
    """Pause at 1/s: every failed request counted before the first catch is classed against the onset interval, the
    classes sum to the count, and none is `before` (they are scheduled after the onset)."""
    Rr = R_old(paths["main"]) if m is not None else R(paths["main"])
    ok, seen = True, 0
    for row in Rr["secondary"]:
        if row["regime"] != SP or row["rate"] != 1.0:
            continue
        for col, v in row["columns"].items():
            if v is None:
                continue
            for pe in v["perEpisode"]:
                h = pe["byH4Class"]
                ok &= h is not None and sum(h.values()) == pe["failedBefore"] and h["before"] == 0
                seen += 1
            ok &= v["byH4Class"] is not None and v["byH4ClassEpisodes"] == v["n"]
    return ok and seen > 0


def check_binding(m):
    b = " ".join(m.BINDING)
    return ("rounds 7-14" in b and "readout-hotel-r3/REVIEW.md" in b and "readout-hotel-r3-v2-fix1/REVIEW.md" in b
            and "decisions 26-60" in b and "d126589" in b and "6162c37" in b and "c17f6a6" in b)


def check_doses(reg):
    return all(reg[n]["origin_type"] == "decision" and "decision 50" in reg[n]["origin_ref"]
               for n in ("FAULT_DOSE_CPU_THROTTLE", "FAULT_DOSE_NET_DELAY"))


def check_resolution_label(reg):
    return "float-difference granularity" in reg["RESOLUTION_RULE"]["value"]


# ----------------------------------------------------------------------------- decision 57 (v2.2)

V21_REV = "22e0d12"


def old_v21():
    """sweep_analysis_v2.py as it was at 22e0d12 (v2.1, the record of the Hotel re-analysis), executed as its own
    module on the current registry (every entry it reads is unchanged in name and value)."""
    if "mod21" not in _OLD:
        mod = types.ModuleType("sweep_analysis_v2_at_" + V21_REV)
        mod.__file__ = str(ROOT / "research" / "detection-time" / "sweep_analysis_v2.py")
        exec(compile(git_show(V21_REV, "research/detection-time/sweep_analysis_v2.py"), "v2.1@" + V21_REV, "exec"),
             mod.__dict__)
        _OLD["mod21"] = mod
    return _OLD["mod21"]


def R_v21(path):
    key = ("v21", str(path))
    if key not in _CACHE:
        _CACHE[key] = old_v21().run(path, compare=False)
    return _CACHE[key]


def _absent_fire(tokens, source):
    return dict(_fire("span", "search", "/search.Search/Nearby", "absent", 0.5, 100.0, "T"), silenceEndedBy=100.4,
                silenceTokens=list(tokens), silenceTokenSource=source)


def check_sensor_silence_unit(m):
    """A span's `absent` whose silence is ended by the ledger's catching request is same-request; one whose
    silence-ending observation names no request is unclassifiable (no win); one ended by another request wins."""
    c = judge_cell(ledgerTok={200.0: {"hr-a"}})
    j = m.judge_fold(_absent_fire(["hr-a"], "trace"), LEDGER_FIRE, 60.0, c)
    w = m.judge_fold(_absent_fire(["hr-b"], "trace"), LEDGER_FIRE, 60.0, c)
    k = m.judge_fold(_absent_fire([], "the ending span carries no token and belongs to no tokened trace"),
                     LEDGER_FIRE, 60.0, c)
    return (j["category"] == "same request" and not j["win"] and j.get("sensorSilence") is True
            and w["category"] == "win" and w["win"] and not w.get("unclassifiable")
            and k["category"] == m.UNCLASSIFIABLE and not k["win"] and k.get("unclassifiable") is True)


def check_silence_tokens_unit():
    """The silence-ending observation's own token first (a tokened root span, a log line naming a token), else the
    token of its trace; none -> no token, with the reason."""
    c = {"spanOwnTok": {("frontend", "op"): {10.0: {"hr-r"}}},
         "spanTok": {("frontend", "op"): {10.0: {"hr-r"}}, ("search", "op"): {11.0: {"hr-s"}}},
         "logTok": {("frontend", "tpl"): {12.0: {"hr-l"}}}, "logTraceTok": {("frontend", "tpl"): {13.0: {"hr-t"}}}}
    return (v2.silence_tokens(c, "span", "frontend", "op", 10.0) == (["hr-r"], "observation")
            and v2.silence_tokens(c, "span", "search", "op", 11.0) == (["hr-s"], "trace")
            and v2.silence_tokens(c, "log", "frontend", "tpl", 12.0) == (["hr-l"], "observation")
            and v2.silence_tokens(c, "log", "frontend", "tpl", 13.0) == (["hr-t"], "trace")
            and v2.silence_tokens(c, "log", "frontend", "tpl", 14.0)[0] == []
            and "no observation" in v2.silence_tokens(c, "span", "search", "op", None)[1])


def check_sensor_silence_e2e(paths, which="v22"):
    """10/s net delay (reference K): search's span stream goes silent ~1 ms before the ledger's completions do; the
    first delayed request ends both silences (its search span carries the token through its trace, the frontend root
    span its own), so the P4a folds are same-request (v2.1: wins, the lead being above the margin)."""
    Rr = R_v21(paths["fastnd"]) if which == "v21" else R(paths["fastnd"])
    v = Rr["results"]["reference"]["P4"]["P4a"][ND]["perRate"]["10"]
    ok = len(v["folds"]) == 2 and all(
        fo["sensorRule"] == "absent" and fo["ledgerRule"] == "absent" and fo["lead"] > fo["margin"]
        and fo["category"] == "same request" and fo.get("sensorSilence") is True
        and fo.get("sensorSilenceSource") == "trace" and fo["sensorSilenceTokens"] == fo["ledgerSilenceTokens"]
        for fo in v["folds"])
    for e in [x for x in Rr["results"]["reference"]["eps"] if x["regime"] == ND]:
        c = e["_c"]
        first_delayed = min((r for r in c["ledger"] if r.end - r.start > 0.2), key=lambda r: r.start)
        se = [f for f in e["fires"] if f["svc"] == "search" and f["rule"] == "absent"]
        fr = [f for f in e["fires"] if f["ch"] == "span" and f["svc"] == "frontend" and f["rule"] == "absent"]
        ok &= bool(se) and se[0].get("silenceTokens") == [first_delayed.token]
        ok &= bool(fr) and all(f.get("silenceTokenSource") == "observation" and f["silenceTokens"] == [
            first_delayed.token] for f in fr)
    return ok


def check_unclassifiable_reported(m):
    """Four held-out folds whose only candidate is a span `absent` without a silence-ending token: no win, each counted
    as unclassifiable in the rate's row and in the decision-57 summary."""
    eps = [_ep(b, [dict(LEDGER_FIRE), _absent_fire([], "no observation ends the silence")]) for b in (1, 2, 3, 4)]
    row = m.p4(eps, False, False)[SP]["perRate"]["1"]
    summ = m.decision57_summary({"P4": {"P4a": m.p4(eps, False, False)}})
    return (row["wins"] == 0 and row["unclassifiable"] == 4 and row["sensorAbsentWithoutToken"] == 4
            and row["holds"] is False and summ["totals"]["withoutToken"] == 4
            and all(fo["category"] == m.UNCLASSIFIABLE for fo in row["folds"]))


def check_d57_decided(reg):
    e = reg.get("SENSOR_ABSENT_TOKEN_RULE")
    return bool(e) and e["origin_type"] == "decision" and "decision 57" in e["origin_ref"] and \
        "BEFORE ANY TeaStore OR OTel CELL IS READ" in e["origin_ref"] and "unclassifiable" in e["value"]


def _no_trace_fallback(c, ch, svc, tok, ender):
    """Planted defect: the silence-ending observation's own token only (no trace fallback)."""
    return _REAL_SILENCE_TOKENS(dict(c, spanTok={}, logTraceTok={}), ch, svc, tok, ender)


_REAL_SILENCE_TOKENS = v2.silence_tokens


# ----------------------------------------------------------------------------- decision 58 (v2.3)

V22_REV = "421a6d2"


def old_v22():
    """sweep_analysis_v2.py at 421a6d2 (v2.2, frozen 5c98726), executed as its own module on its own registry."""
    if "mod22" not in _OLD:
        mod = types.ModuleType("sweep_analysis_v2_at_" + V22_REV)
        mod.__file__ = str(ROOT / "research" / "detection-time" / "sweep_analysis_v2.py")
        src = git_show(V22_REV, "research/detection-time/sweep_analysis_v2.py")
        reg = json.loads(git_show(V22_REV, "research/protocol/parameters.json"))
        mod.__dict__["__v22_registry__"] = reg
        src = src.replace("REGISTRY = load_registry()", "REGISTRY = {p['name']: p for p in __v22_registry__['parameters']}")
        exec(compile(src, "v2.2@" + V22_REV, "exec"), mod.__dict__)
        _OLD["mod22"] = mod
    return _OLD["mod22"]


def R_v22(path):
    key = ("v22", str(path))
    if key not in _CACHE:
        _CACHE[key] = old_v22().run(path, compare=False)
    return _CACHE[key]


def _absent_ledger(end_tokens, start_tokens, t=200.0, ttd=1.0):
    return dict(_fire("ledger", "frontend", "r", "absent", ttd, t, "E"), silenceEndedBy=t + 0.2,
                silenceTokens=list(end_tokens), silenceStartedBy=t - 0.25, silenceStartTokens=list(start_tokens),
                silenceGap=0.25)


def _absent_sensor(end_tokens, start_tokens):
    return dict(_absent_fire(end_tokens, "trace"), silenceStartedBy=100.0 - 0.23, silenceStartTokens=list(start_tokens),
                silenceStartTokenSource="trace" if start_tokens else "no token", silenceGap=0.23)


def check_start_token_unit(m):
    """Absent vs absent: ends differ, starts are one request -> same request (58); starts and ends differ -> win;
    the sensor's start names no request -> unclassifiable; a mixed pair (the ledger caught by `failed`) keeps 57."""
    c = judge_cell(cmd={"A": {"mono": 199.0, "wall": 99.5}})          # start term 0.48 s: above any margin
    j = m.judge_fold(_absent_sensor(["hr-x"], ["hr-a"]), _absent_ledger(["hr-y"], ["hr-a"]), 60.0, c)
    w = m.judge_fold(_absent_sensor(["hr-x"], ["hr-b"]), _absent_ledger(["hr-y"], ["hr-a"]), 60.0, c)
    u = m.judge_fold(_absent_sensor(["hr-x"], []), _absent_ledger(["hr-y"], ["hr-a"]), 60.0, c)
    mixed = m.judge_fold(_absent_sensor(["hr-x"], ["hr-a"]), dict(LEDGER_FIRE), 60.0,
                         judge_cell(ledgerTok={200.0: {"hr-a"}}))
    return (j["category"] == "same request" and j.get("silenceStartSame") is True and j["sensorSilence"] is False
            and w["category"] == "win" and u["category"] == m.UNCLASSIFIABLE
            and any("decision 58" in x for x in u.get("unclassifiableBy") or [])
            and mixed["category"] == "win" and not mixed.get("silenceStartSame"))


def check_start_token_e2e(paths, which="v23"):
    """10/s net delay, the first delayed request's search span lost: search's silence is ended by the second delayed
    request, the ledger's by the first (decision 57: no match), but both silences start with the last undelayed request
    (decision 58: same request). The lead is decomposed exactly: (last completion - last search span end) + (g_E - g_T)."""
    Rr = R_v22(paths["lostnd"]) if which == "v22" else R(paths["lostnd"])
    v = Rr["results"]["reference"]["P4"]["P4a"][ND]["perRate"]["10"]
    ok = len(v["folds"]) == 2
    for fo, e in zip(v["folds"], sorted([x for x in Rr["results"]["reference"]["eps"] if x["regime"] == ND],
                                        key=lambda x: x["block"])):
        c = e["_c"]
        last_undelayed = max((r for r in c["ledger"] if r.end - r.start < 0.2 and r.end < e["onset"]["mono"] + 1.0),
                             key=lambda r: r.end)
        d = fo.get("decomposition") or {}
        ok &= (fo["sensor"] == "span:search:/search.Search/Nearby" and fo["sensorRule"] == "absent"
               and fo["ledgerRule"] == "absent" and fo["lead"] > fo["margin"] and fo["sensorSilence"] is False
               and fo.get("silenceStartSame") is True and fo["category"] == "same request"
               and fo["sensorSilenceStartTokens"] == fo["ledgerSilenceStartTokens"] == [last_undelayed.token]
               and abs(d["startDifference"] + d["gapDifference"] - fo["lead"]) < 1e-9 and abs(d["residual"]) < 1e-9)
    return ok


def check_d58_decided(reg):
    e, p2 = reg.get("SILENCE_START_TOKEN_RULE"), reg.get("P2_DOBS_S_TEASTORE")
    return (bool(e) and e["origin_type"] == "decision" and "decision 58" in e["origin_ref"]
            and "BEFORE ANY TeaStore OR OTel CELL IS READ" in e["origin_ref"] and "STARTING" in e["value"]
            and bool(p2) and p2["value"] == 15.0 and "decision 59" in p2["origin_ref"])


# ----------------------------------------------------------------------------- decision 60 (v2.4)

V23_REV = "af6f223"


def old_v23():
    """sweep_analysis_v2.py at af6f223 (v2.3, frozen 830f309), executed as its own module on its own registry."""
    if "mod23" not in _OLD:
        mod = types.ModuleType("sweep_analysis_v2_at_" + V23_REV)
        mod.__file__ = str(ROOT / "research" / "detection-time" / "sweep_analysis_v2.py")
        src = git_show(V23_REV, "research/detection-time/sweep_analysis_v2.py")
        mod.__dict__["__v23_registry__"] = json.loads(git_show(V23_REV, "research/protocol/parameters.json"))
        src = src.replace("REGISTRY = load_registry()", "REGISTRY = {p['name']: p for p in __v23_registry__['parameters']}")
        exec(compile(src, "v2.3@" + V23_REV, "exec"), mod.__dict__)
        _OLD["mod23"] = mod
    return _OLD["mod23"]


A60 = {"mono": 199.0, "wall": 99.5}       # onset on both clocks of the hand-built decision-60 episodes


def _d60_pair(start_term, gap_term, block=1, ttd_sensor=0.4):
    """A sensor's `absent` (span) and the ledger's `absent` whose silences start and end with four different requests:
    the sensor's last observation before its silence is A + x_S, the ledger's last completion A + x_S + start_term; the
    sensor's gap 0.2 s, the ledger's 0.2 s + gap_term. Their times to detection follow (x + g), so lead = start + gap."""
    xs, gs, ge = ttd_sensor - 0.2, 0.2, 0.2 + gap_term
    xe = xs + start_term
    f = dict(_fire("span", "search", "/search.Search/Nearby", "absent", xs + gs, A60["wall"] + xs + gs, "T"),
             clock="wall", silenceEndedBy=A60["wall"] + xs + gs + 0.05, silenceTokens=["hr-s-end-%d" % block],
             silenceTokenSource="trace", silenceStartedBy=A60["wall"] + xs, silenceStartTokens=["hr-s-start-%d" % block],
             silenceStartTokenSource="trace", silenceGap=gs)
    fE = dict(_fire("ledger", "frontend", "r", "absent", xe + ge, A60["mono"] + xe + ge, "E"), clock="mono",
              silenceEndedBy=A60["mono"] + xe + ge + 0.05, silenceTokens=["hr-e-end-%d" % block],
              silenceStartedBy=A60["mono"] + xe, silenceStartTokens=["hr-e-start-%d" % block], silenceGap=ge)
    return f, fE


def d60_eps(start_term, gap_term):
    """Four pause episodes at 1/s (hand-built), each with only the decision-60 pair."""
    eps = []
    for b in (1, 2, 3, 4):
        f, fE = _d60_pair(start_term, gap_term, b)
        e = _ep(b, [fE, f])
        e["_c"]["cmd"] = {"A": dict(A60), "B": {"mono": A60["mono"] + 60.0, "wall": A60["wall"] + 60.0}}
        eps.append(e)
    return eps


def check_start_term(m):
    """Start term 1 µs < tie margin (~3 µs: ledger 1e-9 + span 1e-6 + alignment 2e-6) < start + gap (~1 ms): no win,
    category `start term within the margin` (v2.3: win, the gap term made the lead). Start term 5 ms: a win in both.
    The decomposition is printed either way. P4 over four such episodes: 0 wins (v2.3: 4, holds)."""
    c = judge_cell(cmd={"A": dict(A60)})
    f, fE = _d60_pair(1e-6, 1e-3)
    tie = m.judge_fold(f, fE, 60.0, c)
    f2_, fE2 = _d60_pair(5e-3, 1e-3)
    win = m.judge_fold(f2_, fE2, 60.0, c)
    d = tie.get("decomposition") or {}
    row = m.p4(d60_eps(1e-6, 1e-3), False, False)[SP]["perRate"]["1"]
    return (tie["margin"] < tie["lead"] and abs(d["startDifference"] - 1e-6) < 1e-9 and abs(d["gapDifference"] - 1e-3)
            < 1e-9 and d["startDifference"] < tie["margin"] and tie["category"] == m.START_TERM_TIE and not tie["win"]
            and win["category"] == "win" and win["win"] and row["wins"] == 0 and row["holds"] is False
            and all(fo["category"] == m.START_TERM_TIE for fo in row["folds"]) and row.get("startTermTies") == 4)


def check_d60_mixed_unchanged(m):
    """A mixed pair (the ledger caught by `failed`) with the same stamps keeps the lead rule: a win."""
    c = judge_cell(cmd={"A": dict(A60)})
    f, _ = _d60_pair(1e-6, 1e-3)
    led = dict(LEDGER_FIRE, ttd=f["ttd"] + 1e-3)
    j = m.judge_fold(f, led, 60.0, c)
    return j["category"] == "win" and not j.get("startTermRule")


def check_d60_decided(reg):
    e = reg.get("START_TERM_RULE")
    return (bool(e) and e["origin_type"] == "decision" and "decision 60" in e["origin_ref"]
            and "c17f6a6" in e["origin_ref"] and "BEFORE ANY TeaStore OR OTel CELL IS READ" in e["origin_ref"]
            and "gap term" in e["value"] and "never counts" in e["value"])


def check_g3_label(m):
    """G3: the unclassifiable label names both ends; a v2.2/v2.3 readout's label compares equal to it."""
    old_fold = {"sensor": "s", "category": "unclassifiable (no silence-ending token)"}
    return ("silence-starting" in m.UNCLASSIFIABLE and "silence-ending" in m.UNCLASSIFIABLE
            and m._old_cat(old_fold) == m.UNCLASSIFIABLE)


# ----------------------------------------------------------------------------- the checks and the planted defects

CHECKS = {
    "h1-tiny-baseline": lambda p: check_h1_tiny_baseline()[0],
    "h1-min20": lambda p: check_h1_min20(),
    "floor-relative": lambda p: check_floor_relative()[0],
    "floor-resolution": lambda p: check_floor_resolution(),
    "absent-rearm": lambda p: check_absent_rearm(),
    "poisson": lambda p: check_poisson(),
    "far-restart-equivalence": lambda p: check_far_restart_equivalence(),
    "alignment": check_alignment,
    "receipt-bound": check_receipt_bound,
    "loco": check_loco,
    "k-fit": check_k_fit,
    "kmaps": check_kmaps,
    "ledger-absent": check_ledger_absent,
    "pooled-e2e": check_pooled_end_to_end,
    "actuator": check_actuator,
    "same-request-e2e": check_same_request_e2e,
    "p1": check_p1,
    "p1-no-event": check_p1_no_event,
    "exposure": check_exposure,
    "p3": check_p3,
    "p2": check_p2,
    "margin": lambda p: check_margin(),
    "same-request-unit": lambda p: check_same_request_unit(),
    "ledger-missed": lambda p: check_ledger_missed(),
    "no-app-stamp": lambda p: check_no_app_stamp(),
    "tied": lambda p: check_tied(),
    # round 11
    "b1": lambda p: check_b1(v2),
    "same-silence-unit": lambda p: check_same_silence_unit(v2),
    "same-silence-e2e": check_same_silence_e2e,
    "mad-zero": lambda p: check_mad_zero(v2),
    "restart-simulation": lambda p: check_restart_simulation(),
    "calibration-is-scored": lambda p: check_calibration_is_scored(p, v2),
    "k-per-class": check_k_per_class,
    "k-unit-family": check_k_unit_family,
    "p1-ambiguity": lambda p: check_p1_ambiguity(R(p["straddle"])),
    "absent-gap": check_absent_gap,
    "secondary-h4": check_secondary_h4,
    "binding": lambda p: check_binding(v2),
    # round 12 (decision 57)
    "sensor-silence-unit": lambda p: check_sensor_silence_unit(v2),
    "silence-tokens-unit": lambda p: check_silence_tokens_unit(),
    "sensor-silence-e2e": check_sensor_silence_e2e,
    "unclassifiable-reported": lambda p: check_unclassifiable_reported(v2),
    # round 13 (decision 58)
    "start-token-unit": lambda p: check_start_token_unit(v2),
    "start-token-e2e": check_start_token_e2e,
    # round 14 (decision 60) and the v2.3 review
    "start-term": lambda p: check_start_term(v2),
    "d60-mixed-unchanged": lambda p: check_d60_mixed_unchanged(v2),
    "g3-label": lambda p: check_g3_label(v2),
}

MUTANTS = {   # label: (attribute, planted value, checks of which at least one must fail)
    "own pre-window baseline (H1)": ("POOLED", False, ["pooled-e2e"]),
    "no n >= 20 minimum (H1)": ("MIN_POOLED_CHECK", False, ["h1-min20"]),
    "no relative floor (decision 27/32)": ("RELATIVE_FLOOR", False, ["floor-relative"]),
    "no resolution floor (decision 27/32)": ("RESOLUTION_FLOOR", False, ["floor-resolution"]),
    "held-out cell fitted on itself (H2)": ("LOCO", False, ["loco"]),
    "K met on the point estimate (decision 33)": ("FAR_MEETS", "point", ["k-fit"]),
    "absent not re-armed": ("ABSENT_REARM", False, ["absent-rearm"]),
    "ledger without absent (H3 e)": ("LEDGER_ABSENT", False, ["ledger-absent"]),
    "same request counted (H3 c)": ("SAME_REQUEST", False, ["same-request-unit", "same-request-e2e"]),
    "no timing margin (H3 b)": ("MARGIN_CHECK", False, ["margin"]),
    "actuator readback not flagged (decision 26)": ("ACTUATOR_FLAG", False, ["actuator"]),
    "ledger miss counted as a win (H3 d)": ("LEDGER_MISSED_APART", False, ["ledger-missed"]),
    "P1 point expectation (H4)": ("P1_INTERVAL", False, ["p1"]),
    "P3 unrestricted (H11)": ("P3_RESTRICT", False, ["p3"]),
    "every service exposed (H5)": ("EXPOSURE_TRACES", False, ["exposure"]),
    # round 11
    "'sensor missed' where a family is not at the operating point (B1)": ("P4_MUTED_DASH", False, ["b1"]),
    "ledger `absent` without the silence's token (M1)": ("SAME_SILENCE", False,
                                                         ["same-silence-unit", "same-silence-e2e"]),
    "MAD = 0 scored against the floor (M2)": ("MAD_ZERO_DASH", False, ["mad-zero"]),
    "K from the all-sensors count (M3)": ("SCORED_SET_CALIBRATION", False, ["k-per-class"]),
    "one K per system (M4)": ("K_FIT_UNIT", "system", ["k-unit-family"]),
    "P1 window without delta (M5)": ("P1_AMBIGUITY", False, ["p1-ambiguity"]),
    "secondary without the H4 split (minor)": ("SECONDARY_H4_SPLIT", False, ["secondary-h4"]),
    "binding line of rounds 7-9 (minor)": ("BINDING", ("research/PROTOCOL_DRAFT_20261002.md rounds 7-9 (decisions 26-47)",),
                                           ["binding"]),
    # round 12
    "sensor `absent` without the silence's token (decision 57)": (
        "SENSOR_SILENCE_TOKEN", False, ["sensor-silence-unit", "sensor-silence-e2e", "unclassifiable-reported"]),
    "no trace fallback for the silence-ending observation (decision 57)": (
        "silence_tokens", _no_trace_fallback, ["silence-tokens-unit", "sensor-silence-e2e"]),
    # round 13
    "absent/absent pair tested on the ending records only (decision 58)": (
        "SILENCE_START_TOKEN", False, ["start-token-unit", "start-token-e2e"]),
    # round 14
    "gap term counted toward an absent/absent lead (decision 60)": ("START_TERM_ONLY", False, ["start-term"]),
}


def test_checks_pass(paths):
    res = {name: bool(fn(paths)) for name, fn in CHECKS.items()}
    assert all(res.values()), [k for k, v in res.items() if not v]


@pytest.mark.parametrize("label", sorted(MUTANTS))
def test_planted_defect_is_caught(label, paths, monkeypatch):
    attr, val, names = MUTANTS[label]
    monkeypatch.setattr(v2, attr, val)
    assert any(not CHECKS[n](paths) for n in names), "planted defect not caught: %s" % label


def test_k_fit_unit_system(paths, monkeypatch):
    """K_FIT_UNIT `system`: L, M, S, T take the per-system K (here none: the rare template keeps L above the target)
    while the ledger keeps its own; the `unit` argument gives the same (the systemK setting beside the primary)."""
    op = v2.operating_point(cells_of(paths["quiet"]), v2.ARMS["primary"])
    assert all(v2.kmaps_from(op, [1.0])[g][1.0]["T"] == 8.0 for g in (SP, CT, ND))
    sysk = {"E": 2.5, "L": None, "M": None, "S": None, "T": None}
    assert all(v2.kmaps_from(op, [1.0], unit="system")[g][1.0] == sysk for g in (SP, CT, ND))
    monkeypatch.setattr(v2, "K_FIT_UNIT", "system")
    assert all(v2.kmaps_from(op, [1.0])[g][1.0] == sysk for g in (SP, CT, ND))


def test_new_rules_fail_on_v1_behaviour(paths):
    """Where v1 behaved differently, v1's own function gives the other answer."""
    assert check_h1_tiny_baseline() == (True, True)          # v1 fires on the 3-point baseline
    assert check_floor_relative() == (True, True)            # v1's 1 ms floor fires
    assert check_p1_v1_fails(paths)                          # v1's point P1 fails block 4
    j = v2.judge_fold(_fire("log", "frontend", "t", "appear", 0.8, 100.0, "L"), LEDGER_FIRE, 60.0, judge_cell())
    assert j["v1StyleWin"] and not j["win"]                  # v1's strictly-lower rule wins inside the margin
    folds, wins = sa1.loeo({"span:search:op": [0.9] * 4}, [1.0] * 4, [60.0] * 4)
    assert wins == 4                                         # v1 counts same-request / in-margin leads as wins
    j = v2.judge_fold(_fire("metric", "profile", "cpu", "spike", 3.0, 100.0, "M"), None, 60.0, judge_cell())
    assert j["v1StyleWin"] and not j["win"]                  # v1 counts a ledger miss as a win
    assert sa1.P3_TESTABLE and not any(v["trafficIndependent"] for v in v2.P3_TI.values())


def test_moved_verdicts_and_readout(paths, tmp_path):
    """v1 in process on the main fixture: every moved verdict carries a reason; P3 moves for H11; the readout names
    every binding document, carries the label, has no stale 'primary until' text and prints the rule on P4 lines."""
    Rr = R(paths["main"], compare=True)
    moved = {m["verdict"]: m for m in Rr["moved"]}
    assert moved and all(m["reason"] and m["reason"] != v2.DASH for m in moved.values())
    p3 = [m for k, m in moved.items() if k.startswith("P3")]
    assert p3 and all("H11" in m["reason"] for m in p3)
    nd = [m for k, m in moved.items() if k.startswith("P4") and ND in k]
    assert nd and all("same request (H3 c, row 15)" in m["reason"] for m in nd)
    ct = moved["P4b %s r1" % CT]                            # v1 won with the throttled target's PSI
    assert ct["v1"] is True and ct["v2"] is False and "BC-actuator-readback, decision 26" in ct["reason"]
    J = v2.build_json(Rr)
    md = v2.render(Rr, J)
    for doc in ("DECLARATION.md", "AMENDMENT_1.md", "AMENDMENT_2.md", "AMENDMENT_3.md", "METHODOLOGY_HARDENING.md",
                "rounds 7-14", "parameters.json", "readout-hotel-r3/REVIEW.md", "readout-hotel-r3-v2-fix1/REVIEW.md"):
        assert doc in md, doc
    assert v2.LABEL in md and "primary until" not in md and "vs E `" in md
    assert "## Moved verdicts (v1" in md and "P1 under v1's definition" in md and "P1 under v2.4's definition" in md
    assert "holds by branch: timeout interval 4" in md and J["predictions"]["P1"]["holdsByBranch"] == {
        "timeout interval": 4}                                   # F2
    assert "frozen for TeaStore and OTel" in md and "per-system K" in md and "Scale not estimable" in md
    assert "## Decision 57" in md and J["decision57"]["totals"] is not None
    assert J["label"] == v2.LABEL and J["version"] == "2.4" and J["movedVerdicts"] and json.dumps(J, default=sorted)


def test_cli_writes_new_directory_only(paths, tmp_path):
    out = tmp_path / "readout"
    assert v2.main([str(paths["main"]), "--out", str(out)]) == 0
    assert (out / "SWEEP_ANALYSIS_V2_4.md").read_text().startswith("# Traffic sweep, Hotel: analysis v2.4")
    J = json.loads((out / "sweep_analysis_v2_4.json").read_text())
    assert J["predictions"]["P1"]["holds"] is True and J["parameters"]["FAR_TARGET_PER_HOUR"] == 15.0
    with pytest.raises(SystemExit):
        v2.main([str(paths["main"]), "--out", str(out)])


def test_round11_registry_entries():
    """Decisions 50, 53 and 54 recorded as decided; the ledger-latency resolution labelled; the new rule texts read."""
    reg = v2.REGISTRY
    assert check_k_unit_decided(reg) and check_p1_decided(reg) and check_doses(reg) and check_resolution_label(reg)
    for n, d in (("LEDGER_ABSENT_TOKEN_RULE", "decision 51"), ("SCALE_NOT_ESTIMABLE_RULE", "decision 52"),
                 ("CALIBRATION_SET_RULE", "decision 55"), ("P4_NOT_EVALUABLE_RULE", "decision 55"),
                 ("P1_AMBIGUITY_WINDOW_RULE", "decision 54")):
        assert reg[n]["origin_type"] == "decision" and d in reg[n]["origin_ref"] and n in v2.PARAMS_USED, n


@pytest.mark.parametrize("name,field,value,check", [
    ("K_FIT_UNIT", "origin_type", "engineering default", "check_k_unit_decided"),
    ("P1_TOLERANCE_RULE", "origin_type", "engineering default", "check_p1_decided"),
    ("P1_AMBIGUITY_WINDOW_RULE", "origin_ref", "proposed", "check_p1_decided"),
    ("FAULT_DOSE_NET_DELAY", "origin_type", "unknown", "check_doses"),
    ("RESOLUTION_RULE", "value", "min positive difference between two distinct values", "check_resolution_label")])
def test_planted_registry_defect_is_caught(name, field, value, check):
    reg = json.loads(json.dumps(v2.REGISTRY))
    reg[name][field] = value
    assert not globals()[check](reg)


def test_round11_rules_fail_on_v2(paths):
    """Each round-11 check, run on v2 itself (32e3178) or on v2's registry (ac313f1), fails; on v2.1 each passes
    (test_checks_pass, test_round11_registry_entries)."""
    old, reg_old = old_v2(), old_registry()
    assert not safely(check_b1, old)                                   # B1: "sensor missed" -> "none", no "— at"
    assert not safely(check_same_silence_unit, old)                    # M1: the same-silence lead was a win
    assert not safely(check_same_silence_e2e, paths, True)
    assert not safely(check_mad_zero, old)                             # M2: MAD = 0 scored against the floor
    assert not safely(check_calibration_is_scored, paths, old)         # M3: calibrated on all sensors
    assert not safely(check_k_per_class, paths, old)
    assert not check_k_unit_decided(reg_old)                           # M4: an engineering default in v2
    assert not safely(check_p1_ambiguity, R_old(paths["straddle"]))    # M5: b2 failed
    assert not check_p1_decided(reg_old)
    assert not safely(check_secondary_h4, paths, old)                  # minors
    assert not check_binding(old)
    assert not check_doses(reg_old) and not check_resolution_label(reg_old)
    assert "fires before any timeout" in " ".join(old.DEFAULTS)


def test_decision57_fails_on_v21(paths):
    """Each decision-57 check, run on v2.1 itself (22e0d12), fails; on v2.2 each passes (test_checks_pass). v2.1 gave
    a sensor's `absent` no token, so the same-request and the unclassifiable pairs were wins."""
    old = old_v21()
    assert not hasattr(old, "SENSOR_SILENCE_TOKEN") and not hasattr(old, "silence_tokens")
    assert not safely(check_sensor_silence_unit, old)
    assert not safely(check_sensor_silence_e2e, paths, "v21")
    assert not safely(check_unclassifiable_reported, old)
    v = R_v21(paths["fastnd"])["results"]["reference"]["P4"]["P4a"][ND]["perRate"]["10"]
    assert [fo["category"] for fo in v["folds"]] == ["win", "win"]          # the contrast, stated


def test_round12_registry_entry():
    assert check_d57_decided(v2.REGISTRY) and "SENSOR_ABSENT_TOKEN_RULE" in v2.PARAMS_USED
    reg = json.loads(json.dumps(v2.REGISTRY))
    reg["SENSOR_ABSENT_TOKEN_RULE"]["origin_type"] = "engineering default"
    assert not check_d57_decided(reg)
    assert not check_d57_decided(old_registry())


def test_moved_vs_v21(paths, tmp_path):
    """v2.1 (22e0d12) writes its readout of 4 blocks of 10/s net delay; v2.2 reads it: P4a net-delay r10 moves from
    holds (4 wins: search's span `absent` ~1 ms ahead of the ledger's) to fails (4 same-request folds), and the
    reason names decision 57. A v2.1 readout of other evidence is refused."""
    out = tmp_path / "v21"
    assert old_v21().main([str(paths["fastnd4"]), "--out", str(out)]) == 0
    J21 = json.loads((out / "sweep_analysis_v2_1.json").read_text())
    assert J21["version"] == "2.1"
    Rr = v2.run(paths["fastnd4"], v21_readout=out / "sweep_analysis_v2_1.json")
    cmp_ = Rr["vs"]["v2.1"]
    rows = {m["verdict"]: m for m in cmp_["moved"]}
    m = rows["P4a %s r10" % ND]
    assert m["old"] is True and m["new"] is False and "decision 57" in m["reason"]
    assert all("decision 57" in x["reason"] and "unexpected" not in x["reason"] for x in rows.values())
    fc = [x for x in cmp_["folds"] if x["setting"] == "primary" and x["view"] in ("P4a", "P4b")]
    assert len(fc) == 4 and all(x["rules"][0].startswith("decision 57") and x["old"][2] == "win"
                                and x["new"][2] == "same request" for x in fc)
    assert len(cmp_["folds"]) >= len(fc) and cmp_["unexplained"] == 0               # F12: every setting and view
    md = v2.render(Rr, v2.build_json(Rr))
    assert "## Moved verdicts (v2.1 -> v2.4 primary)" in md and "| P4a %s r10 | holds | fails |" % ND in md
    assert "across all settings and BC views" in md
    assert "unclassifiable pairs: 0" in md
    with pytest.raises(SystemExit):
        v2.v2_reference(*v2.v1.find_cells(paths["fastnd"]), out / "sweep_analysis_v2_1.json")


def test_decision58_fails_on_v22(paths):
    """Each decision-58 check, run on v2.2 itself (421a6d2, its own registry), fails; on v2.3 each passes. v2.2 tested
    an absent/absent pair on the silence-ending observations only, so the lost-span folds were wins."""
    old = old_v22()
    assert not hasattr(old, "SILENCE_START_TOKEN") and old.VERSION == "2.2"
    assert not safely(check_start_token_unit, old)
    assert not safely(check_start_token_e2e, paths, "v22")
    v = R_v22(paths["lostnd"])["results"]["reference"]["P4"]["P4a"][ND]["perRate"]["10"]
    assert [fo["category"] for fo in v["folds"]] == ["win", "win"]           # the contrast, stated


def test_round13_registry_entries():
    reg = v2.REGISTRY
    assert check_d58_decided(reg) and "SILENCE_START_TOKEN_RULE" in v2.PARAMS_USED
    for name in ("SILENCE_START_TOKEN_RULE", "P2_DOBS_S_TEASTORE"):
        planted = json.loads(json.dumps(reg))
        planted[name]["origin_ref"] = planted[name]["origin_ref"].replace("decision 5", "round ")
        assert not check_d58_decided(planted), name
    assert not check_d58_decided({p["name"]: p for p in json.loads(git_show(V22_REV, "research/protocol/parameters.json"))
                                  ["parameters"]})
    for n in ("JSON_LOG_STAMP_RULE", "HARNESS_PROVENANCE", "KNOWN_LIMITATIONS", "V23_FIXES"):
        assert reg[n]["origin_type"] != "unknown" and "v2.2 review" in reg[n]["origin_ref"] and n in v2.PARAMS_USED
    assert set(reg["KNOWN_LIMITATIONS"]["value"]) == {"F7", "F9", "F10", "F11", "G4"}


def test_moved_vs_v22(paths, tmp_path):
    """v2.2 (421a6d2) writes its readout of 4 blocks of 10/s net delay with the first delayed search span lost; v2.3
    reads it: P4a net-delay r10 moves from holds (4 wins) to fails, every changed fold in every setting and view is
    decision 58's, none unexplained (F12)."""
    out = tmp_path / "v22"
    assert old_v22().main([str(paths["lostnd4"]), "--out", str(out)]) == 0
    J22 = json.loads((out / "sweep_analysis_v2_2.json").read_text())
    assert J22["version"] == "2.2"
    Rr = v2.run(paths["lostnd4"], compare=False, v22_readout=out / "sweep_analysis_v2_2.json")
    cmp_ = Rr["vs"]["v2.2"]
    rows = {m["verdict"]: m for m in cmp_["moved"]}
    m = rows["P4a %s r10" % ND]
    assert m["old"] is True and m["new"] is False and "decision 58" in m["reason"] and "unexpected" not in m["reason"]
    prim = [x for x in cmp_["folds"] if x["setting"] == "primary" and x["view"] == "P4a"]
    assert len(prim) == 4 and all(x["old"][2] == "win" and x["new"][2] == "same request" for x in prim)
    assert cmp_["unexplained"] == 0 and all(x["rules"][0].startswith("decision 58") for x in cmp_["folds"])
    assert len(cmp_["folds"]) > len(prim)                       # other settings / views move too, and are counted
    Rr["v1"], Rr["moved"] = {"source": "-", "predictions": {"P1": {"k": 0, "n": 0, "holds": None}},
                             "verdicts": {}, "p4PerRate": {}}, []
    md = v2.render(Rr, v2.build_json(Rr))
    assert "## Moved verdicts (v2.2 -> v2.4 primary)" in md and "| P4a %s r10 | holds | fails |" % ND in md
    assert "**%d across all settings and BC views**" % len(cmp_["folds"]) in md
    assert "lead = " in md and "start +" in md and "decision 58" in md


def test_decision60_fails_on_v23():
    """The decision-60 check, run on v2.3 itself (af6f223, its own registry), fails: v2.3 counted the gap term, so the
    pair whose start term is inside the margin was a win and P4 held 4/4."""
    old = old_v23()
    assert not hasattr(old, "START_TERM_ONLY") and old.VERSION == "2.3"
    assert not safely(check_start_term, old)
    c = judge_cell(cmd={"A": dict(A60)})
    f, fE = _d60_pair(1e-6, 1e-3)
    assert old.judge_fold(f, fE, 60.0, c)["category"] == "win"                 # the contrast, stated
    row = old.p4(d60_eps(1e-6, 1e-3), False, False)[SP]["perRate"]["1"]
    assert row["wins"] == 4 and row["holds"] is True
    assert check_d60_mixed_unchanged(old)                                     # mixed pairs: same in both versions
    assert not safely(check_g3_label, old)


def test_round14_registry_entries():
    reg = v2.REGISTRY
    assert check_d60_decided(reg) and "START_TERM_RULE" in v2.PARAMS_USED and "V24_FIXES" in v2.PARAMS_USED
    planted = json.loads(json.dumps(reg))
    planted["START_TERM_RULE"]["origin_type"] = "engineering default"
    assert not check_d60_decided(planted)
    assert not check_d60_decided({p["name"]: p for p in json.loads(git_show(V23_REV, "research/protocol/parameters.json"))
                                  ["parameters"]})
    g4 = reg["KNOWN_LIMITATIONS"]["value"]["G4"]
    assert "productcatalogservice" in g4 and "main.go:57" in g4 and "frontend" in g4
    np_ = reg["JSON_LOG_STAMP_RULE"]["value"]["notParsed"]
    assert "productcatalogservice" in np_ and "frontend" in np_ and "recommendationservice" in np_


def test_planted_absent_gap_claim_is_caught(paths, monkeypatch):
    """A readout that claims `absent` precedes a timeout at every rate (v2's blanket sentence, per rate) is caught."""
    real = v2.absent_gap_report

    def blanket(Rr):
        out = real(Rr)
        for x in out.values():
            x["gapBelowTimeout"] = dict.fromkeys(x["gapBelowTimeout"], True)
        return out
    monkeypatch.setattr(v2, "absent_gap_report", blanket)
    assert not check_absent_gap(paths)


def test_moved_vs_v2(paths, tmp_path):
    """v2 (32e3178) writes its readout of the straddle fixture; v2.1 reads it and lists every verdict that moved with
    the round-11 rule: P1 (M5) and the P4 highest-rate texts (B1's '— at'). A v2 readout of other evidence is refused."""
    out = tmp_path / "v2"
    assert old_v2().main([str(paths["straddle"]), "--out", str(out)]) == 0
    Rr = v2.run(paths["straddle"], v2_readout=out / "sweep_analysis_v2.json")
    rows = {m["verdict"]: m for m in Rr["movedVsV2"]}
    assert rows["P1"]["v2fix1"] is False and rows["P1"]["v22"] is True
    assert "M5 (decision 54)" in rows["P1"]["reason"] and "r1 b2 fails -> holds" in rows["P1"]["reason"]
    hr = rows["P4a %s" % SP]
    assert hr["v2fix1"] == v2.DASH and hr["v22"] == "— at {10, 1, 0.2, 0.05}" and "ledger family E" in hr["reason"]
    assert all(m["reason"] and m["reason"] != v2.DASH for m in rows.values())
    md = v2.render(Rr, v2.build_json(Rr))
    assert "## Moved verdicts (v2-fix1 -> v2.4 primary)" in md and "| P1 | fails | holds | M5 (decision 54)" in md
    with pytest.raises(SystemExit):
        v2.v2_reference(*v2.v1.find_cells(paths["main"]), out / "sweep_analysis_v2.json")


def test_v1_readout_must_match_evidence(paths, tmp_path):
    out = tmp_path / "v1"
    sa1.main([str(paths["noevent"]), "--out", str(out), "--reference-only"])
    with pytest.raises(SystemExit):
        v2.v1_reference(paths["main"], *v2.v1.find_cells(paths["main"]), out / "sweep_analysis.json")
    old = v2.v1_reference(paths["noevent"], *v2.v1.find_cells(paths["noevent"]), out / "sweep_analysis.json")
    assert "input digest matches" in old["source"] and "P1" in old["verdicts"]


# ----------------------------------------------------------------------------- the parameter registry

V2_SRC = ROOT / "research" / "detection-time" / "sweep_analysis_v2.py"
ALLOWED_LITERALS = {        # value: reason (structural or a unit conversion, never a tunable)
    0: "zero, first index, empty start", 1: "unit step, next index, the leading 1 of P2's model",
    2: "halving (bisection midpoint)", 1e6: "microseconds per second (unit)", 1e9: "nanoseconds per second (unit)",
    1000: "milliseconds per second (unit)", 3600: "seconds per hour (unit)", 10: "decimal base of a representation",
}


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _const_expr(node):
    """A numeric literal, a signed one, or arithmetic of such (no name involved)."""
    if isinstance(node, ast.Constant):
        return _is_number(node.value)
    if isinstance(node, ast.UnaryOp):
        return _const_expr(node.operand)
    if isinstance(node, ast.BinOp):
        return _const_expr(node.left) and _const_expr(node.right)
    return False


def _numeric_string(node):
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return False
    try:
        float(node.value.strip())
    except ValueError:
        return False
    return True


def numeric_literals(src):
    """Tunable-looking literals: a numeric constant outside the allow-list; float("...") / int("...") on a numeric
    string (any value: a number hidden in a string); arithmetic of literals only (e.g. 2 * 2, 0.5 + 0.5)."""
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant) and _is_number(node.value):
            if node.value not in ALLOWED_LITERALS:
                out.append((node.lineno, node.value))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("float", "int") \
                and node.args and _numeric_string(node.args[0]):
            out.append((node.lineno, "%s(%r)" % (node.func.id, node.args[0].value)))
        elif isinstance(node, ast.BinOp) and _const_expr(node):
            out.append((node.lineno, ast.unparse(node)))
    return out


SWITCH_IMPORTS = {   # boolean v1 / dbebcbb switches v2.1 reads: their planted-defect default, never flipped by v2.1
    "dt.INCLUSIVE": "dbebcbb's comparator `>=` (asserted True; the operating-point count assumes it)",
    "v1.DOCKER_STAMP": "v1's Docker receive stamp rule for logs (DECLARATION Analysis definitions, Stamps)",
    "v1.TOKEN_FILTER": "v1's token rule for spans (DECLARATION Analysis definitions, probe windows)",
}
MODULE_OF = {"v1": sa1, "dt": dtm, "sweep_analysis": sa1, "detection_time": dtm}


def imported_constants(src):
    """Every v1 / dbebcbb module constant v2.1 reads: `v1.NAME` / `dt.NAME` attributes and from-imports."""
    out = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ("v1", "dt") \
                and node.attr.isupper():
            out.add("%s.%s" % (node.value.id, node.attr))
        if isinstance(node, ast.ImportFrom) and node.module in ("sweep_analysis", "detection_time"):
            out.update("%s.%s" % ({"sweep_analysis": "v1", "detection_time": "dt"}[node.module], a.name)
                       for a in node.names)
    return sorted(out)


def _has_number(v):
    if _is_number(v):
        return True
    if isinstance(v, dict):
        return any(_has_number(x) for x in v.values())
    if isinstance(v, (list, tuple, set, frozenset)):
        return any(_has_number(x) for x in v)
    return False


def import_violations(src, registry, mapping):
    """Imported constants that are tunables (numeric, or boolean) without an equal registry entry: a numeric one must
    map (IMPORTED_TUNABLES) to a registry entry of equal value; a boolean one too, or be a declared reader switch at
    its default True."""
    bad = []
    for name in imported_constants(src):
        mod, attr = name.split(".")
        val = getattr(MODULE_OF[mod], attr)
        if isinstance(val, bool):
            if name in mapping:
                if registry[mapping[name]]["value"] != val:
                    bad.append(name)
            elif not (name in SWITCH_IMPORTS and val is True):
                bad.append(name)
        elif _has_number(val):
            norm = list(val) if isinstance(val, tuple) else val
            if name not in mapping or registry[mapping[name]]["value"] != norm:
                bad.append(name)
    return bad


def unknown_used(registry, used):
    return sorted(n for n in used if registry[n]["origin_type"] == "unknown" or registry[n].get("status") != "active")


def test_no_tunable_literal_in_v2():
    assert numeric_literals(V2_SRC.read_text()) == []


def test_planted_literal_is_caught():
    src = V2_SRC.read_text().replace("K_REF = param(\"K_REFERENCE\")", "K_REF = 4.0")
    assert (src != V2_SRC.read_text()) and numeric_literals(src) == [(next(
        i + 1 for i, ln in enumerate(src.splitlines()) if ln.startswith("K_REF = 4.0")), 4.0)]


def _old_scanner():
    """v2's scanner (tests at c770a6d): numeric constants only."""
    tree = ast.parse(git_show(V2_TESTS_REV, "tests/test_sweep_analysis_v2.py"))
    keep = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "numeric_literals") or (
        isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "ALLOWED_LITERALS" for t in n.targets))]
    ns = {"ast": ast}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "scanner@" + V2_TESTS_REV, "exec"), ns)
    return ns["numeric_literals"]


@pytest.mark.parametrize("planted", ['K_REF = float("4.0")', 'K_REF = int("4")', "K_REF = 2 * 2",
                                     "K_REF = 0.5 + 0.5", 'RUN = float(" 3 ")', "K_REF = -(2 ** 2)"])
def test_planted_hidden_literal_is_caught(planted):
    """A number hidden in a string conversion or in literal arithmetic is caught (v2's scanner missed each, built only
    from the allow-listed constants 0, 1, 2, 10 or a string)."""
    src = V2_SRC.read_text().replace("K_REF = param(\"K_REFERENCE\")", planted)
    line = next(i + 1 for i, ln in enumerate(src.splitlines()) if ln == planted)
    assert src != V2_SRC.read_text() and any(ln == line for ln, _ in numeric_literals(src))
    if planted != "K_REF = 0.5 + 0.5":                  # 0.5 itself is a literal v2's scanner did catch
        assert not any(ln == line for ln, _ in _old_scanner()(src))


def test_imported_tunables_equal_the_registry():
    """Every numeric or boolean constant v2.1 takes from v1 / detection_time equals its registry entry (or is a
    declared reader switch at its default); the module's own assert checks the same mapping at import."""
    src = V2_SRC.read_text()
    names = imported_constants(src)
    assert {"dt.RUN_N", "dt.MIN_BASELINE", "dt.PATH_FILTER", "v1.REF"} <= set(names)
    assert import_violations(src, v2.REGISTRY, v2.IMPORTED_TUNABLES) == []
    assert all(v2.REGISTRY[r]["status"] == "active" and v2.REGISTRY[r]["origin_type"] != "unknown"
               for r in v2.IMPORTED_TUNABLES.values())


@pytest.mark.parametrize("planted", ["X = dt.K", "X = dt.TAU", "X = v1.P1_TOL_S", "from detection_time import ABSENT_MIN",
                                     "X = dt.LOG_UPPER"])
def test_planted_imported_tunable_is_caught(planted):
    src = V2_SRC.read_text() + "\n" + planted + "\n"
    assert import_violations(src, v2.REGISTRY, v2.IMPORTED_TUNABLES) == [
        planted.replace("X = ", "").replace("from detection_time import ", "dt.")]


def test_planted_registry_mismatch_of_an_import_is_caught():
    reg = json.loads(json.dumps(v2.REGISTRY))
    reg["RUN_N"]["value"] = 4
    assert import_violations(V2_SRC.read_text(), reg, v2.IMPORTED_TUNABLES) == ["dt.RUN_N"]


def test_registry_entries_used_have_an_origin():
    assert v2.PARAMS_USED and unknown_used(v2.REGISTRY, v2.PARAMS_USED) == []
    doc = json.loads(v2.PARAMETERS.read_text())
    types = set(doc["originTypes"])
    assert all(p["origin_type"] in types and p["origin_ref"] for p in doc["parameters"])
    names = {p["name"] for p in doc["parameters"]}
    # the four rows PARAMETER_REGISTRY.md left `unknown`, each with its resolution, none used by v2
    for n in ("TAU", "SYS_FLOORS", "FAULT_DOSE_CPU_THROTTLE", "FAULT_DOSE_NET_DELAY"):
        assert n in names and n not in v2.PARAMS_USED and "RESOLUTION" in v2.REGISTRY[n]["origin_ref"]
    assert v2.REGISTRY["MAD_SCALE"]["origin_type"] == "literature" and "D1" in v2.REGISTRY["MAD_SCALE"]["origin_ref"]
    assert v2.REGISTRY["RESOLUTION_RULE"]["origin_type"] == "measured"


def test_planted_unknown_origin_is_caught():
    reg = json.loads(json.dumps(v2.REGISTRY))
    reg["K_GRID"]["origin_type"] = "unknown"
    assert unknown_used(reg, v2.PARAMS_USED) == ["K_GRID"]
    reg = json.loads(json.dumps(v2.REGISTRY))
    assert unknown_used(reg, set(v2.PARAMS_USED) | {"TAU"}) == ["TAU"]


def test_v1_and_detection_time_unchanged():
    """v1 produced the committed readout e31e316 at 21bda46; detection_time.py is dbebcbb's."""
    for rel, rev in (("research/detection-time/sweep_analysis.py", "21bda46"),
                     ("research/detection-time/detection_time.py", "dbebcbb")):
        got = subprocess.run(["git", "-C", str(ROOT), "show", "%s:%s" % (rev, rel)], capture_output=True)
        if got.returncode != 0:
            pytest.skip("git history not available")
        assert (ROOT / rel).read_bytes() == got.stdout, rel
    assert v2.v1 is sa1 and v2.dt is dtm
