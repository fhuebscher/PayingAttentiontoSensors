"""Traffic-sweep extension of the detection-time analysis (research/detection-time/sweep_analysis.py).

Layer: unit + synthetic end-to-end. Synthetic fixtures only: no sweep evidence is read (the analysis is blind until the
main session runs it). Covers: detection_time.py unchanged at dbebcbb and equal to the extension at the reference point;
probe-window exclusion and the move of a catch to the window end; probe spans dropped by token; Docker receive stamps;
a miss charged at the hold end; P1 pass and fail; the P2 boundary; the P4 3-of-4 boundary and leave-one-episode-out;
impact counted by scheduled time; an absent channel rendered `—`, not 0; the output path never overwritten. Planted
defects: every switch in sweep_analysis flipped, and every patched function in MUTANTS, must make a check fail.
Review fixes (Fable, on da6c002): partial and invalid cells listed, never fatal (B1, M3); two rates with P3 holds / fails
and a per-rate G3 difference (M2); whole-second rule per cell (m1); a late actual start that flips P1 and the impact
count, and the failed_before boundary (m2); provenance (m4); a span stream in the reference equivalence (m5); probe and
caller-span variants side by side and "decided by the probe rule" (M1).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "detection-time"))

import sweep_analysis as sa  # noqa: E402
import detection_time as dtm  # noqa: E402

T0 = 1_790_000_000.0          # barrier, wall clock
B0 = 5000.0                   # barrier, monotonic clock
NOFAULT = sa.NOFAULT
SP = "search-pause-effect"
CT = "cpu-throttle-effect"


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
    """Stratified onset offset: block b takes quarter b of one inter-arrival (0.4 of the way in)."""
    return round(((block - 1) + 0.4) / 4.0 / rate, 6)


def make_cell(root, regime, rate, block, offset, late=0.0, samples=True, spans=True, docker=True, mem_jump=None,
              nf_log=None, fault_log=None, early_log=None, late_rows=None):
    """One sweep cell. search-pause: from A + 0.05 every request times out at its 1 s client timeout; the receipt's
    startedMonotonic is A + `late` (late > 0 plants an onset-stamp defect). mem_jump: frontend memory +2 MB from
    A + mem_jump s (fault cells). nf_log / fault_log: a frontend warn template at onset + 20 s in no-fault / fault cells.
    early_log: a frontend warn template at A + 0.5 s, inside the during-probe window. late_rows {sequence: delay}: the
    request starts that much after its scheduled time. docker=False: log lines without the Docker receive stamp."""
    fault = {NOFAULT: None, SP: "search-pause", CT: "profile-cpu-throttle"}[regime]
    rt = ("%g" % rate).replace(".", "p")
    klass = {None: "calibration", "search-pause": "effect/search-pause", "profile-cpu-throttle": "effect/cpu-throttle"}
    d = (root / "runs" / klass[fault] / ("r" + rt) / ("b%02d" % block)
         / ("p%02d-full" % block) / "attempt-01")
    onset, hold, M = 60.0 + offset, 60.0, 180.0
    timing = {"requestsPerSecond": rate, "interArrivalSeconds": 1.0 / rate, "requestTimeoutSeconds": 1.0,
              "measurementSeconds": 180, "faultOnsetBaseSeconds": 60, "faultOnsetPhaseOffsetSeconds": offset,
              "faultOnsetSeconds": onset, "faultHoldSeconds": 60, "scoredWindowSeconds": [onset, onset + hold],
              "applicationLogTimestamps": True, "probeStamps": True, "faultApplied": fault is not None}
    run_id = "%s-r%s-b%02d-full-a01" % (regime, rt, block)
    _w(d / "cell-contract.json", {"runId": run_id, "fault": fault, "timing": timing,
                                  "compiledPlanCanonicalSha256": "7" * 64, "admissionCanonicalSha256": "a" * 64, "runKey": {
        "studyEpoch": "hotel-traffic-sweep-v1", "regime": regime, "requestsPerSecond": rate, "block": block,
        "posture": "full", "attempt": 1}})
    _w(d / "cell-terminal.json", {"candidateCellValid": True})
    _w(d / "opportunity-plan.json", {"barrierAt": _iso(T0), "barrierMonotonic": B0, "durationSeconds": M,
                                     "workloadId": "hotel-search-v1", "rate": rate})
    a_true = B0 + onset + 0.1
    eff = (a_true + 0.05, a_true + hold) if fault == "search-pause" else None
    rows, spans, first_fail = [], [], None
    for i in range(int(round(rate * M))):
        so = i / rate
        s = B0 + so + 0.002 + (late_rows or {}).get(i, 0.0)
        failed = eff is not None and eff[0] <= s <= eff[1]
        e = s + (1.0 if failed else 0.010 + (0.0005 if i % 2 else 0.0))
        tok = "hr-%032x" % (block * 1_000_000 + i)
        rows.append({"sequence": i, "scheduledMonotonicOffsetSeconds": so, "actualStartMonotonic": s,
                     "actualEndMonotonic": e, "outcome": "transport-error" if failed else "completed",
                     "statusCode": None if failed else 200, "error": "timed out" if failed else None,
                     "opaqueToken": tok})
        if failed and first_fail is None:
            first_fail = e
        ws, we = T0 + (s - B0), T0 + (e - B0)
        tags = {sa.TOKEN_TAG: tok}
        if failed:
            tags["error"] = True
        spans.append(_span("t%06d" % i, "r%06d" % i, None, "frontend", "HTTP GET /hotels", ws, we - ws, tags))
        if not failed:
            spans.append(_span("t%06d" % i, "c%06d" % i, "r%06d" % i, "search", "/search.Search/Nearby",
                               ws + 0.001, we - ws - 0.002, {}))
    _w(d / "opportunity-ledger.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")

    def log(t, level, msg):
        stamp = (_dock(t) + " ") if docker else ""
        return "frontend-1  | %s{\"level\":\"%s\",\"time\":\"%s\",\"message\":\"%s\"}" % (stamp, level, _app(t), msg)
    logs = [log(T0 + 1.2345, "info", "TLS disabled.")]
    logs += ["frontend-1  | %sOBSPLACEMENT_WITNESS {\"opaqueToken\":\"x\"}" % ((_dock(T0 + t) + " ") if docker else "")
             for t in range(5, 180, 20)]
    logs.append('time="2026-10-03T05:10:00Z" level=warning msg="compose cli line"')
    if fault is None and nf_log:
        logs.append(log(T0 + onset + 20.0, "warn", nf_log))
    if fault is not None and fault_log:
        logs.append(log(T0 + (a_true + 20.0 - B0), "warn", fault_log))
    if fault is not None and early_log:
        logs.append(log(T0 + (a_true + 0.5 - B0), "warn", early_log))
    if fault == "profile-cpu-throttle":       # lmt_faults.inject receipt shape (degradation)
        _w(d / "fault-receipt.json", {
            "schemaVersion": 1, "faultKind": "degradation", "scenario": fault, "targetService": "profile",
            "startedMonotonic": a_true, "appliedMonotonic": a_true + 0.05, "revertingMonotonic": a_true + hold,
            "revertedAtMonotonic": a_true + hold + 0.05, "readyAtMonotonic": a_true + hold + 0.1,
            "endedMonotonic": a_true + hold + 0.2, "error": None, "requestedHoldSeconds": hold,
            "probes": [{"phase": "pre", "startMonotonic": a_true - 0.05, "endMonotonic": a_true - 0.04, "available": True},
                       {"phase": "during", "startMonotonic": a_true + 0.06, "endMonotonic": a_true + 0.07,
                        "available": True}]})
    if fault == "search-pause":
        pre = (B0 + onset + 0.01, B0 + onset + 0.04)
        during = (a_true + 0.06, a_true + 5.06)
        _w(d / "fault-receipt.json", {
            "schemaVersion": 1, "faultKind": "pause", "scenario": "search-pause", "targetService": "search",
            "startedMonotonic": a_true + late, "appliedMonotonic": a_true + late + 0.05,
            "revertingMonotonic": a_true + hold, "unpausedAtMonotonic": a_true + hold + 0.05,
            "readyAtMonotonic": a_true + hold + 0.5, "endedMonotonic": a_true + hold + 0.6, "error": None,
            "probes": [{"phase": "pre", "startMonotonic": pre[0], "endMonotonic": pre[1], "available": True},
                       {"phase": "during", "startMonotonic": during[0], "endMonotonic": during[1], "available": False}]})
        for k, (lo, hi) in enumerate((pre, during, (a_true + hold + 0.2, a_true + hold + 0.21))):
            spans.append(_span("probe%d" % k, "p%d" % k, None, "frontend", "HTTP GET /hotels", T0 + lo - B0, hi - lo, {}))
        logs.append(log(T0 + (during[0] + 2.5 - B0), "error", "probe only failure"))
        logs.append(log(T0 + (a_true + 10.003 - B0), "error", "SearchHandler Nearby failed"))
    _w(d / "application.log", "\n".join(logs) + "\n")
    if spans:
        _w(d / "traces-normalized.json", {"events": spans})
        _w(d / "jaeger-raw-remainder.json", {"queries": [{"service": "user", "traceCount": 1, "traces": [
            {"traceID": "bg1", "processes": {"p1": {"serviceName": "user"}},
             "spans": [{"spanID": "s1", "processID": "p1", "operationName": "/user.User/CheckUser",
                        "startTime": int((T0 + 10) * 1e6), "duration": 1000, "references": [], "tags": []}]}]}]})
    cpu = []
    for t in range(0, 180, 3):
        paused = fault is not None and a_true - B0 <= t <= a_true + hold - B0
        cpu.append({"capturedAtEpoch": T0 + t, "capturedAtMonotonic": B0 + t, "containers": [
            {"service": "frontend", "containerId": "f", "cpuPercent": 5.0 + (0.1 if t % 2 else 0.0)},
            {"service": "search", "containerId": "s", "cpuPercent": 0.0 if paused else 3.0 + (0.1 if t % 2 else 0.0)}]})
    _w(d / "cpu.json", {"intervalSeconds": 1.0, "samples": cpu})
    if samples:
        smp = []
        for t in range(0, 185, 5):
            smp.append({"at": _iso(T0 + t), "monotonic": B0 + t, "services": {
                svc: {"cpuUsageUsec": int(1e6 * 0.05 * t),
                      "memoryCurrent": 10_000_000 + (1000 if t % 2 else 0) + (
                          2_000_000 if (svc == "frontend" and fault is not None and mem_jump is not None
                                        and t >= a_true - B0 + mem_jump) else 0),
                      "psiCpuSomeTotalUsec": (int(1e5 * max(0.0, t - (a_true - B0))) if svc == "profile" and
                                              fault == "profile-cpu-throttle" else 0),
                      "psiIoSomeTotalUsec": 0, "psiMemorySomeTotalUsec": 0,
                      "rbytes": 0, "wbytes": 0} for svc in ("frontend", "search", "profile")}})
        _w(d / "system-samples.json", {"intervalSeconds": 5.0, "kind": "hotel-lmt-system-samples-v1", "samples": smp})
    return d


OFFSETS = (0.1, 0.35, 0.6, 0.85)       # stratified quarters of one 1 s inter-arrival


def make_campaign(root, late_block=None, samples=True, blocks=(1, 2, 3, 4), **kw):
    for b in blocks:
        make_cell(root, NOFAULT, 1.0, b, OFFSETS[b - 1], samples=samples)
        make_cell(root, SP, 1.0, b, OFFSETS[b - 1], late=0.9 if b == late_block else 0.0, samples=samples, **kw)
    return root


SLOW = "cache refill slow"          # a frontend warn template, not naming the target


def make_two_rate(root, jump_rates):
    """Rates 10 and 0.05, 4 blocks each. S: frontend memory jumps 6 s after the pause at `jump_rates` (P3 for
    search-pause S outside). L: SLOW appears in every no-fault window at 10/s only and in every hold at both rates,
    so G3 admits it at 0.05/s and rejects it at 10/s (a per-rate G3 difference)."""
    for rate in (10.0, 0.05):
        for b in (1, 2, 3, 4):
            make_cell(root, NOFAULT, rate, b, off(rate, b), spans=False, nf_log=SLOW if rate == 10.0 else None)
            make_cell(root, SP, rate, b, off(rate, b), spans=False, fault_log=SLOW,
                      mem_jump=6.0 if rate in jump_rates else None)
    return root


@pytest.fixture(scope="module")
def campaigns(tmp_path_factory):
    base = tmp_path_factory.mktemp("sweep")
    mixed = base / "mixedws"
    make_cell(mixed, NOFAULT, 1.0, 1, OFFSETS[0])
    make_cell(mixed, SP, 1.0, 1, OFFSETS[0], docker=False)
    late_start = base / "latestart"
    make_cell(late_start, NOFAULT, 1.0, 1, OFFSETS[0])
    make_cell(late_start, SP, 1.0, 1, OFFSETS[0], late_rows={61: 0.8, 62: 1.0})
    return {"ok": make_campaign(base / "ok"), "late": make_campaign(base / "late", late_block=4),
            "absent": make_campaign(base / "absent", samples=False, blocks=(1,)),
            "p3hold": make_two_rate(base / "p3hold", (10.0, 0.05)), "p3fail": make_two_rate(base / "p3fail", (10.0,)),
            "mixedws": mixed, "latestart": late_start,
            "decided": make_campaign(base / "decided", early_log="upstream slow")}


def _run(path, variants=False):
    return sa.run(path, grid=[sa.REF], variants=variants)


# ----------------------------------------------------------------------------- hand-built cell for the window rules

def _hand_cell():
    """Wall clock = monotonic + 1000. A span stream every 0.5 s until A + 1.85 (silent after), a log stream with one
    record inside the probe window only."""
    def fam(ch, coll, posture):
        return {"log": "L", "span": "T", "metric": "M"}.get(ch)
    span_t = [1000.0 + 0.5 * i for i in range(0, 95)]        # last record 1047.0
    return {"sut": "hotel", "posture": "full", "chans": {"log", "span", "ledger"}, "t0": {"wall": 1000.0, "mono": None},
            "family": fam, "ledger": [],
            "prep": {("span", "geo", "/geo.Geo/Nearby"): (span_t, [0.005] * len(span_t),
                                                          {"clock": "wall", "collector": "jaeger", "level": None}),
                     ("log", "frontend", "tplP"): ([1048.5], [1.0], {"clock": "wall", "collector": "x", "level": "error"})}}


A_H, B_H = {"mono": 45.15, "wall": 1045.15}, {"mono": 105.15, "wall": 1105.15}
PROBE_H = {"wall": [(1047.5, 1050.0)], "mono": [(47.5, 50.0)]}


# ----------------------------------------------------------------------------- checks (each returns True when right)

def check_probe_excluded():
    fires, _, _ = sa.eval_window(_hand_cell(), A_H, B_H, False, probes=PROBE_H)
    return not any(f["tok"] == "tplP" for f in fires)


def check_probe_moved():
    fires, _, _ = sa.eval_window(_hand_cell(), A_H, B_H, False, probes=PROBE_H)
    ab = [f for f in fires if f["tok"] == "/geo.Geo/Nearby" and f["rule"] == "absent"]
    # silence after 1047.0, gap 2 x 0.5 s -> absent at 1048.0, inside [1047.5, 1050.0] -> moved to 1050.0
    return len(ab) == 1 and ab[0]["moved"] and abs(ab[0]["ttd"] - (1050.0 - 1045.15)) < 1e-9


def check_no_fabricated_silence():
    # the stream keeps its 0.5 s cadence through the probe window: dropping those records must not make it `absent`
    c = _hand_cell()
    t = [1000.0 + 0.5 * i for i in range(0, 230)]            # until 1114.5, past the hold end 1105.15
    c["prep"][("span", "geo", "/geo.Geo/Nearby")] = (t, [0.005] * len(t), {"clock": "wall", "collector": "jaeger",
                                                                          "level": None})
    fires, _, _ = sa.eval_window(c, A_H, B_H, False, probes=PROBE_H)
    return not any(f["tok"] == "/geo.Geo/Nearby" and f["rule"] == "absent" for f in fires)


def check_miss_at_hold():
    s = sa.summarise([2.0, None, None, None], [60.0, 60.0, 60.0, 60.0])
    return s["k"] == 1 and s["n"] == 4 and abs(s["penalisedMeanTtd"] - (2.0 + 180.0) / 4) < 1e-9


def check_scheduled_count():
    # a request scheduled at a + 0.5 that started late (a + 1.5) and failed is impact before a catch at a + 1.0
    # and one scheduled exactly at the catch is counted (inclusive upper bound)
    reqs = [(101.5, 102.5, False, "r", 0, 100.5), (100.2, 100.3, True, "r", 1, 100.2),
            (101.0, 102.0, False, "r", 2, 101.0)]
    return sa.failed_before(reqs, 100.0, 101.0) == 2


def check_p2_boundary():
    lo = sa.p2_verdict([3, 3, 3, 4], 0.05)          # threshold 3.05: three of four within -> holds
    hi = sa.p2_verdict([3, 3, 4, 4], 0.05)
    edge = sa.p2_verdict([13, 13, 13, 14], 10.0)    # threshold 13 exactly: `<=`
    short = sa.p2_verdict([1, 1, 1], 1.0)            # n = 3: not evaluable
    return lo["holds"] is True and hi["holds"] is False and edge["holds"] is True and edge["k"] == 3 \
        and short["holds"] is None


def check_p4_boundary():
    holds = [60.0] * 4
    _, w3 = sa.loeo({"span:geo:x": [0.4, 0.4, 0.4, None]}, [1.0] * 4, holds)
    _, w2 = sa.loeo({"span:geo:x": [0.4, 0.4, None, None]}, [1.0] * 4, holds)
    per = {r: {"holds": False} for r in sa.RATES}
    return (w3 == 3 and sa.p4_holds(w3, 4) is True and w2 == 2 and sa.p4_holds(w2, 4) is False
            and sa.p4_holds(3, 3) is None and sa.highest_rate(per) == "none in {10, 1, 0.2, 0.05}"
            and sa.highest_rate({**per, 0.2: {"holds": True}}) == "0.2")


def check_loeo():
    # in-sample selection (all four episodes) picks B in every fold and wins 3 of 4; leave-one-out wins 2 of 4
    cands = {"A": [0.5, 0.5, 0.5, None], "B": [None, 0.4, 0.4, 0.4]}
    folds, wins = sa.loeo(cands, [1.0] * 4, [60.0] * 4)
    return wins == 2 and [f["sensor"] for f in folds] == ["B", "B", "B", "A"]


def check_p1(R_ok, R_late):
    ok = R_ok["reference"]["predictions"]["P1"]
    late = R_late["reference"]["predictions"]["P1"]
    return (ok["k"] == 4 and ok["n"] == 4 and ok["holds"] is True
            and [x["ok"] for x in late["perEpisode"]] == [True, True, True, False] and late["holds"] is False
            and abs(late["perEpisode"][3]["deviation"] + 1.0) < 0.01)


def _cell(R, regime, block):
    return next(c for c in R["cells"] if c["regime"] == regime and c["block"] == block)


def check_token(R_ok):
    c = _cell(R_ok, SP, 1)
    obs = c["prep"][("span", "frontend", "HTTP_GET_/hotels")][0]
    return len(obs) == 180 and ("span", "user", "/user.User/CheckUser") in c["prep"] \
        and c["readStats"]["tracesExcludedNoToken"] == 3


def check_stamp(R_ok):
    c = _cell(R_ok, NOFAULT, 1)
    tls = [k for k, (lv, msg) in c["logText"].items() if msg == "TLS disabled."]
    obs = c["prep"][("log",) + tls[0]][0] if tls else []
    return len(obs) == 1 and abs(obs[0] - (T0 + 1.2345)) < 1e-4 and c["wsLogs"] is False


def check_probe_log_e2e(R_ok):
    eps = R_ok["reference"]["G"]["episodes"]
    probe_tpl = [k[1] for k, (lv, msg) in eps[0]["_c"]["logText"].items() if msg == "probe only failure"]
    return len(eps) == 4 and probe_tpl and not any(f["tok"] == probe_tpl[0] for e in eps for f in e["fires"])


def check_absent_dash(R_abs):
    J = sa.build_json(R_abs)
    md = sa.render(R_abs, J)
    row = next(r for r in R_abs["reference"]["primary"] if r["regime"] == SP and r["rate"] == 1.0)
    line = next(ln for ln in md.splitlines() if ln.startswith("| search-pause | 1 | 1 |"))
    cols = [x.strip() for x in line.strip("|").split("|")]
    # columns: class, rate, n, then (col, col no BC, FA col) for E L M S T; S is the 4th triple
    s_cells = cols[3 + 3 * 3: 3 + 3 * 4]
    return row["columns"]["S"] is None and row["columns"]["M"] is not None and s_cells == [sa.DASH] * 3 \
        and J["reference"]["predictions"]["P2"]["1"]["holds"] is None and "0/0" not in md


def _p3(R):
    return next(x for x in R["reference"]["predictions"]["P3"] if x["regime"] == SP)


def check_two_rate_p3(R_hold, R_fail):
    """P3 search-pause S outside: memory at 10/s caught at ~9.8 s, at 0.05/s at ~7.9 s (holds); without the jump at
    0.05/s the mean is the hold (fails). Both sides need exactly the 4 episodes of their own rate."""
    h, f = _p3(R_hold), _p3(R_fail)
    return (h["state"] == "holds" and f["state"] == "fails" and h["sides"]["10"]["n"] == 4
            and h["sides"]["0.05"]["n"] == 4 and h["sides"]["10"]["k"] == 4 and f["sides"]["0.05"]["k"] == 0
            and abs(f["sides"]["0.05"]["penalisedMeanTtd"] - 60.0) < 1e-6)


def check_per_rate_g3(R_hold):
    G = R_hold["reference"]["G"]
    tid = next(k[1] for e in G["episodes"] for k, (lv, msg) in e["_c"]["logText"].items() if msg == SLOW)
    key = ("log", "frontend", tid, "appear")
    adm = {r: [f["admissible"] for e in sa.eps_of(G, SP, r) for f in e["fires"] if sa.dt.fkey(f) == key]
           for r in (10.0, 0.05)}
    return (G["g3"][10.0][key] == 4 and G["g3"][0.05][key] == 0 and adm[10.0] == [False] * 4
            and adm[0.05] == [True] * 4)


def check_ws_per_cell(R_mixed):
    (e,) = R_mixed["reference"]["G"]["episodes"]
    tid = next(k[1] for k, (lv, msg) in e["_c"]["logText"].items() if msg == "SearchHandler Nearby failed")
    (f,) = [f for f in e["fires"] if f["tok"] == tid]
    s = math.floor(T0 + (e["_c"]["cmd"]["A"]["mono"] + 10.003 - B0))   # the app's whole-second stamp
    return e["_c"]["wsLogs"] is True and abs(f["ttd"] - (s + 1.0 - e["onset"]["wall"])) < 1e-6


def check_late_start(R_ls):
    """Request 61 is scheduled at 61 s but starts at 61.8 s: the ledger's catch is late against the schedule, which P1
    must flag; request 62 is scheduled before the catch but starts after it, so impact by scheduled time is 2."""
    (x,) = R_ls["reference"]["predictions"]["P1"]["perEpisode"]
    row = next(r for r in R_ls["reference"]["secondary"] if r["regime"] == SP and r["rate"] == 1.0)
    return (x["ok"] is False and abs(x["deviation"] - 0.802) < 1e-3
            and row["columns"]["E"]["perEpisode"][0]["failedBefore"] == 2)


def checks(paths):
    """(name, thunk) in cost order; campaigns are run once per evaluation."""
    cache = {}

    def R(name):
        if name not in cache:
            cache[name] = _run(paths[name])
        return cache[name]
    return [("probe-excluded", check_probe_excluded), ("probe-moved", check_probe_moved),
            ("no-fabricated-silence", check_no_fabricated_silence), ("miss-at-hold", check_miss_at_hold),
            ("scheduled-count", check_scheduled_count), ("p2-boundary", check_p2_boundary),
            ("p4-boundary", check_p4_boundary), ("loeo", check_loeo),
            ("p1", lambda: check_p1(R("ok"), R("late"))), ("token", lambda: check_token(R("ok"))),
            ("stamp", lambda: check_stamp(R("ok"))), ("probe-log-e2e", lambda: check_probe_log_e2e(R("ok"))),
            ("absent-dash", lambda: check_absent_dash(R("absent"))),
            ("ws-per-cell", lambda: check_ws_per_cell(R("mixedws"))),
            ("late-start", lambda: check_late_start(R("latestart"))),
            ("two-rate-p3", lambda: check_two_rate_p3(R("p3hold"), R("p3fail"))),
            ("per-rate-g3", lambda: check_per_rate_g3(R("p3hold")))]


def evaluate(paths):
    return {name: bool(fn()) for name, fn in checks(paths)}


# ----------------------------------------------------------------------------- tests

def test_checks_pass(campaigns):
    res = evaluate(campaigns)
    assert all(res.values()), [k for k, v in res.items() if not v]


_READ_LEDGER, _EPS_OF = sa.read_ledger, sa.eps_of


def _ledger_sched_is_actual(attempt, plan):
    return [r[:5] + (r[0],) for r in _READ_LEDGER(attempt, plan)]


def _p1_on_actual(reqs, a, timeout):
    st = sorted(r[0] for r in reqs if r[0] >= a)
    return st[0] - a + timeout if st else None


def _failed_before_exclusive(reqs, a, t_end):
    return sum(1 for r in reqs if not r[2] and a <= r[5] < t_end)


MUTANTS = {
    # review fixes: each was a planted defect the da6c002 tests did not catch
    "eps_of ignores rate": ("eps_of", lambda G, regime, rate: [e for e in G["episodes"] if e["regime"] == regime]),
    "read_ledger scheduled := actual": ("read_ledger", _ledger_sched_is_actual),
    "p1_expected on actual start": ("p1_expected", _p1_on_actual),
    "failed_before exclusive upper bound": ("failed_before", _failed_before_exclusive),
    "whole-second rule campaign-wide": ("WS_PER_CELL", False),
    "G3 pooled across rates": ("G3_PER_RATE", False),
    # da6c002
    "probe samples scored": ("PROBE_EXCLUDE", False),
    "catch inside a probe window not moved": ("PROBE_MOVE", False),
    "dropped probe records read as silence": ("PROBE_LIVENESS", False),
    "probe spans kept (no token filter)": ("TOKEN_FILTER", False),
    "app stamp instead of Docker receive time": ("DOCKER_STAMP", False),
    "mean over detected episodes only": ("MISS_AT_HOLD", False),
    "impact counted by actual start": ("COUNT_BY_SCHEDULED", False),
    "P2 comparator strict": ("P2_INCLUSIVE", False),
    "P4 criterion 2 of 4": ("P4_MIN", 2),
    "selection in-sample, not leave-one-out": ("LOEO", False),
    "absent column rendered 0": ("ABSENT_DASH", False),
}


@pytest.mark.parametrize("label", sorted(MUTANTS))
def test_planted_defect_is_caught(label, campaigns, monkeypatch):
    var, val = MUTANTS[label]
    monkeypatch.setattr(sa, var, val)
    assert any(not fn() for _, fn in checks(campaigns)), "planted defect not caught: %s" % label


def test_detection_time_unchanged_at_dbebcbb():
    src = ROOT / "research" / "detection-time" / "detection_time.py"
    got = subprocess.run(["git", "-C", str(ROOT), "show", "dbebcbb:research/detection-time/detection_time.py"],
                         capture_output=True)
    if got.returncode != 0:
        pytest.skip("git history for dbebcbb not available")
    assert src.read_bytes() == got.stdout
    # its own planted timelines still pass after the extension was imported, and its switches are untouched
    assert all(ok for _, ok in dtm._checks())
    assert (dtm.K, dtm.INCLUSIVE, dtm.PATH_FILTER, dtm.G3_TAU, dtm.LOG_UPPER, dtm.LOG_HOLD_CAP) == \
        (4.0, True, True, 0.05, True, True)
    assert sa.dt is dtm


def test_reference_point_equals_dbebcbb_eval_window():
    """dbebcbb's planted two-clock cell (detection_time._checks): the extension at K = 4, floor 1 ms, no probes gives
    exactly dt.eval_window's fires; the grid changes the ledger threshold as declared."""
    def fam(ch, coll, posture):
        return {"log": "L", "metric": "M", "span": "T"}.get(ch)
    lg = [1000.0 + t for t in range(0, 45)] + [1047.0]
    mt_t = [1000.0 + 3 * i for i in range(30)]
    mt_v = [10.0 if t < 1048 else 50.0 for t in mt_t]
    sp_t = [1000.0 + 0.5 * i for i in range(120)]                    # span ends; +15 ms from 1047 (review m5)
    sp_v = [(0.0050 if i % 2 else 0.0052) + (0.015 if t >= 1047.0 else 0.0) for i, t in enumerate(sp_t)]
    pc = {"sut": "hotel", "posture": "full", "chans": {"log", "metric", "ledger", "span"},
          "t0": {"wall": 1000.0, "mono": None}, "family": fam,
          "prep": {("log", "frontend", "tplA"): ([1047.0], [1.0], {"clock": "wall", "level": "error", "collector": "x"}),
                   ("log", "geo", "steady"): (lg, [1.0] * len(lg), {"clock": "wall", "level": "info", "collector": "x"}),
                   ("metric", "geo", "cpu"): (mt_t, mt_v, {"clock": "wall", "collector": "docker-stats"}),
                   ("span", "search", "/geo.Geo/Nearby"): (sp_t, sp_v, {"clock": "wall", "collector": "jaeger",
                                                                       "level": None})},
          "ledger": sorted([(i * 0.1, i * 0.1 + (0.01 if i * 0.1 < 45.3 else 1.0), i * 0.1 < 45.3, "r", i)
                            for i in range(600)], key=lambda r: r[1])}
    A, B = {"mono": 45.15, "wall": 1045.15}, {"mono": 60.15, "wall": 1060.15}
    theirs, tb, tu = dtm.eval_window(pc, A, B, True)
    mine, mb, mu = sa.eval_window(pc, A, B, True, 4.0, 1.0)
    keys = ("ch", "svc", "tok", "rule", "ttd", "dir", "level", "family")
    assert sorted(tuple(f[k] for k in keys) for f in mine) == sorted(tuple(f[k] for k in keys) for f in theirs)
    assert mb == tb and mu == tu and len(theirs) >= 4
    span = sorted((f["rule"], round(f["ttd"], 6)) for f in mine if f["ch"] == "span")
    assert ("spike", round(1047.0 - 1045.15, 6)) in span and ("run3", round(1048.0 - 1045.15, 6)) in span
    _, b2, _ = sa.eval_window(pc, A, B, True, 4.0, 2.0)
    assert b2["r"][1] == 2.0                          # MAD 0 -> the floor is the threshold
    # the span floor follows the grid: a +1.5 ms shift is caught at floor 1 ms, not at 2 ms (MAD 0.1 ms, K = 4)
    pc["prep"][("span", "search", "/geo.Geo/Nearby")] = (sp_t, [(0.0050 if i % 2 else 0.0052) + (
        0.0015 if t >= 1047.0 else 0.0) for i, t in enumerate(sp_t)], {"clock": "wall", "collector": "jaeger",
                                                                      "level": None})
    at1 = [f for f in sa.eval_window(pc, A, B, True, 4.0, 1.0)[0] if f["ch"] == "span"]
    at2 = [f for f in sa.eval_window(pc, A, B, True, 4.0, 2.0)[0] if f["ch"] == "span"]
    assert at1 and not at2


def test_bc_caller_log_by_content(campaigns):
    R = _run(campaigns["ok"])
    flagged = [f for e in R["reference"]["G"]["episodes"] for f in e["fires"] if "BC-caller-log" in f["bc"]]
    texts = {e["_c"]["logText"].get((f["svc"], f["tok"]), (None, None))[1]
             for e in R["reference"]["G"]["episodes"] for f in e["fires"] if "BC-caller-log" in f["bc"]}
    assert flagged and texts == {"SearchHandler Nearby failed"}
    ops = {"search": {"/search.Search/Nearby"}, "profile": {"/profile.Profile/GetProfiles"}}
    assert sa.names_callee("SearchHandler Nearby failed", "search", ops)
    assert not sa.names_callee("SearchHandler GetProfiles failed", "search", ops)
    assert not sa.names_callee("SearchHandler CheckAvailability failed", "search", ops)   # "searchhandler" is one word


def test_full_grid_and_cli_never_overwrites(campaigns, tmp_path):
    out = tmp_path / "readout"
    assert sa.main([str(campaigns["absent"]), "--out", str(out)]) == 0
    J = json.loads((out / "sweep_analysis.json").read_text())
    assert len(J["grid"]) == 9 and all(v["agree"][1] == 9 for v in J["gridAgreement"].values())
    assert (out / "SWEEP_ANALYSIS.md").read_text().startswith("# Traffic sweep, Hotel")
    with pytest.raises(SystemExit):
        sa.main([str(campaigns["absent"]), "--out", str(out)])


def test_rate_without_nofault_window_is_dash_not_miss(tmp_path):
    """A campaign that stopped before any no-fault cell of a rate: G3 has n = 0 there, so nothing is admissible; the
    episodes must read `—` (not evaluable), never 0/n detections charged at the hold."""
    make_cell(tmp_path, SP, 1.0, 1, OFFSETS[0])
    R = _run(tmp_path)
    row = next(r for r in R["reference"]["primary"] if r["regime"] == SP and r["rate"] == 1.0)
    assert row["n"] == 1 and all(v is None for v in row["columns"].values())
    p1 = R["reference"]["predictions"]["P1"]
    assert p1["n"] == 0 and p1["notEvaluable"] == 1 and p1["holds"] is None
    assert R["reference"]["predictions"]["P2"]["1"] is None
    md = sa.render(R, sa.build_json(R))
    line = next(ln for ln in md.splitlines() if ln.startswith("| search-pause | 1 | 1 |"))
    assert "/" not in line.split("|", 4)[4] and "No-fault windows per rate" in md


def test_degradation_receipt_path(tmp_path):
    """cpu-throttle of profile (lmt_faults receipt): loads, its short probes are windows, the throttled service's PSI
    is an own-sensor catch (S:own), never an outside one, and the ledger misses (no failure, no latency shift)."""
    make_cell(tmp_path, NOFAULT, 1.0, 1, OFFSETS[0])
    make_cell(tmp_path, CT, 1.0, 1, OFFSETS[0])
    R = _run(tmp_path)
    (ep,) = R["reference"]["G"]["episodes"]
    assert ep["target"] == "profile" and ep["faultKind"] == "degradation" and ep["g3n"] == 1
    assert [p["kind"] for p in ep["_c"]["probeWindows"]] == ["probe-pre", "probe-during", "recovery"]
    row = next(r for r in R["reference"]["primary"] if r["regime"] == CT and r["rate"] == 1.0)
    own, out = row["columns"]["S:own"]["noBC"], row["columns"]["S"]["noBC"]
    assert own["k"] == 1 and 0 < own["penalisedMeanTtd"] < 10 and out["k"] == 0
    assert row["columns"]["E"]["bc"]["k"] == 0 and row["columns"]["E"]["bc"]["penalisedMeanTtd"] == ep["holdSeconds"]


# ----------------------------------------------------------------------------- review fixes: direct tests

def test_partial_and_invalid_cells_are_listed_not_fatal(tmp_path):
    """B1 + M3: a contract-only cell (the one that stopped the campaign), an invalid cell with a malformed file, a
    fault cell without its receipt, a no-fault cell with one, and a valid cell that fails to parse are all listed
    with a reason; the run completes and scores only the two good cells."""
    make_cell(tmp_path, NOFAULT, 1.0, 1, OFFSETS[0])
    make_cell(tmp_path, SP, 1.0, 1, OFFSETS[0])
    d = make_cell(tmp_path, SP, 1.0, 2, OFFSETS[1])                       # stopped: contract only
    for p in d.iterdir():
        if p.name != "cell-contract.json":
            p.unlink()
    d = make_cell(tmp_path, NOFAULT, 1.0, 2, OFFSETS[1])                  # invalid, empty samples (hotel.py:125)
    _w(d / "cell-terminal.json", {"candidateCellValid": False})
    _w(d / "system-samples.json", {"intervalSeconds": 5.0, "samples": []})
    d = make_cell(tmp_path, SP, 1.0, 3, OFFSETS[2])                       # fault cell, no receipt
    (d / "fault-receipt.json").unlink()
    d = make_cell(tmp_path, NOFAULT, 1.0, 3, OFFSETS[2])                  # no-fault cell with a receipt
    _w(d / "fault-receipt.json", {"targetService": "search", "faultKind": "pause", "appliedMonotonic": 1.0,
                                  "revertingMonotonic": 2.0, "startedMonotonic": 1.0})
    d = make_cell(tmp_path, SP, 1.0, 4, OFFSETS[3])                       # valid, but a malformed file
    _w(d / "system-samples.json", {"intervalSeconds": 5.0, "samples": []})
    R = _run(tmp_path)
    J = sa.build_json(R)
    reasons = {(x["regime"], int(x["rate"]), x["cell"].split("/b0")[1][0]): x["reason"] for x in J["cells"]["notScored"]}
    assert reasons[(SP, 1, "2")].startswith("no cell-terminal.json")
    assert reasons[(NOFAULT, 1, "2")] == "candidateCellValid is False"
    assert reasons[(SP, 1, "3")] == "no fault-receipt.json for regime search-pause-effect"
    assert reasons[(NOFAULT, 1, "3")] == "a fault-receipt.json for regime no-fault-calibration"
    assert reasons[(SP, 1, "4")].startswith("parse error: IndexError")
    assert len(R["reference"]["G"]["episodes"]) == 1 and len(R["reference"]["G"]["nofault"][1.0]) == 1
    md = sa.render(R, J)
    assert "candidateCellValid is False" in md and J["cells"]["found"]["%s r1" % SP] == 4


def test_receipt_target_must_match_regime(tmp_path):
    make_cell(tmp_path, NOFAULT, 1.0, 1, OFFSETS[0])
    d = make_cell(tmp_path, SP, 1.0, 1, OFFSETS[0])
    r = json.loads((d / "fault-receipt.json").read_text())
    _w(d / "fault-receipt.json", dict(r, targetService="geo"))
    R = _run(tmp_path)
    (x,) = sa.build_json(R)["cells"]["notScored"]
    assert x["reason"] == "receipt target 'geo', regime search-pause-effect expects 'search'"
    assert R["reference"]["G"]["episodes"] == []


def test_provenance(tmp_path):
    """m4: harness commit from the campaign's runtime-admission.json, plan and admission digests from the contracts,
    and a digest over (relative path, size) of every file read, which moves when a read file changes."""
    root = make_campaign(tmp_path / "c", blocks=(1,))
    _w(root / "runtime-admission.json", {"bindings": {"frameworkCommit": "7a1d97b" + "0" * 33}})
    J = sa.build_json(_run(root))
    pv = J["provenance"]
    assert pv["harnessCommit"] == "7a1d97b" + "0" * 33 and pv["planSha256"] == ["7" * 64]
    assert pv["admissionSha256"] == ["a" * 64] and pv["input"]["files"] == 1 + 9 + 10   # admission + no-fault cell (no receipt) + fault cell
    led = next(root.glob("runs/calibration/**/opportunity-ledger.jsonl"))
    led.write_text(led.read_text() + "\n")
    assert sa.build_json(_run(root))["provenance"]["input"]["sha256"] != pv["input"]["sha256"]
    assert sa.build_json(_run(make_campaign(tmp_path / "d", blocks=(1,))))["provenance"]["harnessCommit"] is None


def test_scope_variant_keeps_other_services():
    """M1 (iii) "scope": only logs and metrics of frontend and the target are window-excluded and moved; a geo log
    inside the window is kept and a span catch inside it is not moved (spans are handled by token)."""
    c = _hand_cell()
    c["prep"][("log", "geo", "tplG")] = ([1048.5], [1.0], {"clock": "wall", "collector": "x", "level": "error"})
    fires, _, _ = sa.eval_window(c, A_H, B_H, False, probes=PROBE_H, scope={"frontend", "search"})
    got = {(f["tok"], f["rule"]): (f["ttd"], f["moved"]) for f in fires}
    assert ("tplG", "appear") in got and ("tplP", "appear") not in got
    assert got[("/geo.Geo/Nearby", "absent")] == (pytest.approx(1048.0 - 1045.15), False)
    declared = {(f["tok"], f["rule"]) for f in sa.eval_window(c, A_H, B_H, False, probes=PROBE_H)[0]}
    assert ("tplG", "appear") not in declared


def test_caller_span_variants():
    """Open point 2: "kind" = dbebcbb (stopping faults only); "content" drops the stopping condition. A caller's span
    of the delayed target's RPC is flagged under "content" only; under a pause both flag it."""
    ctx = {"onRoute": {"frontend", "search", "rate"}, "ops": {"rate": {"/rate.Rate/GetRates"}},
           "edges": {("frontend", "search"), ("search", "rate")}}
    f = {"ch": "span", "svc": "search", "tok": "/rate.Rate/GetRates", "rule": "spike", "dir": "up"}
    assert sa.bc_flags(f, "rate", "degradation", ctx, {}, "kind") == []
    assert sa.bc_flags(f, "rate", "degradation", ctx, {}, "content") == ["BC-caller-span"]
    assert sa.bc_flags(f, "rate", "pause", ctx, {}, "kind") == sa.bc_flags(f, "rate", "pause", ctx, {}, "content") \
        == ["BC-caller-span"]


def test_probe_rule_decides_and_variants_side_by_side(campaigns):
    """M1: an outside warn log 0.5 s after the pause beats the ledger in every episode, but it lies in the 5 s
    during-probe window, so the declared rule drops it. P4a at 1/s therefore holds only without the probe rule, and the
    readout says "decided by the probe rule" rather than "none". Variants, moves and window lengths are reported."""
    R = _run(campaigns["decided"], variants=True)
    assert set(R["variants"]) == {(p, c) for p in sa.PROBE_VARIANTS for c in sa.CALLER_SPAN_VARIANTS}
    none = R["variants"][("none", sa.PRIMARY_CALLER_SPAN)]["predictions"]["P4"]["P4a"][SP]
    scope = R["variants"][("scope", sa.PRIMARY_CALLER_SPAN)]["predictions"]["P4"]["P4a"][SP]
    prim = R["reference"]["predictions"]["P4"]["P4a"][SP]
    assert none["perRate"]["1"]["holds"] is True and prim["perRate"]["1"]["holds"] is False
    assert scope["perRate"]["1"]["holds"] is False                      # frontend is in the hung probe's scope
    dec = R["decidedByProbeRule"]
    assert dec["P4a %s r1" % SP] == {"primary": False, "withoutProbeRule": True}
    assert dec["P4a %s" % SP]["withoutProbeRule"] == "1"
    folds = prim["perRate"]["1"]["folds"]
    assert all(abs(f["duringWindowSeconds"] - 5.0) < 1e-6 for f in folds) and all("movedBy" in f for f in folds)
    J = sa.build_json(R)
    md = sa.render(R, J)
    assert "**decided by the probe rule**" in md and "decided by the probe rule (primary: none in {1}" in md
    assert "Variants side by side" in md and J["primaryProbeVariant"] == sa.PRIMARY_PROBE == "scope"
    assert J["primaryCallerSpanVariant"] == sa.PRIMARY_CALLER_SPAN == "content" and len(J["variants"]) == 6
    p3 = J["reference"]["predictions"]["P3"][0]
    assert p3["sides"]["10"] is None                                    # single-rate campaign: P3 not evaluable
