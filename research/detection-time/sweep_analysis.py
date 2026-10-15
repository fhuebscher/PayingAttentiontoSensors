#!/usr/bin/env python3
"""Traffic-sweep extension of the detection-time analysis: Hotel pilot, epoch hotel-traffic-sweep-v1.

BINDING [D] = research/traffic-sweep/DECLARATION.md (frozen a795fc9) + AMENDMENT_1.md. Its "analysis" row: detection_time.py
as committed in dbebcbb plus a sweep extension committed before any result is looked at. This file is that extension.
detection_time.py is imported and never edited: its sensor definitions (log template / span op / metric / ledger route),
online rules (appear, absent, spike, run3, median, failed, watchdog), observation times, stamp rule, miss rule, G3
arithmetic, G2 own/outside split, spike path filter and BC taxonomy are reused as they are. Written blind: one archived
attempt-2 cell was opened for file names, key names and types only (no values); nothing here was run on sweep evidence.
Tested on synthetic fixtures only (tests/test_sweep_analysis.py).

    uv run python research/detection-time/sweep_analysis.py <fetched campaign dir> --out <new dir>

The campaign dir holds `runs/<class>/r<rate>/b<NN>/p<NN>-full/attempt-01/` (or one child that does). Writes
<out>/sweep_analysis.json and <out>/SWEEP_ANALYSIS.md; <out> must not exist (new evidence never overwrites old).

WHAT IS READ PER CELL (item 1; [D] Design):
  cell-contract.json `timing`: rate, scheduled onset = barrier + faultOnsetSeconds (60 s + the stratified offset), hold,
  request timeout; cell-terminal.json `candidateCellValid` (valid cells only); opportunity-plan.json barrier (both clocks);
  opportunity-ledger.jsonl (actual start/end, outcome, statusCode, scheduledMonotonicOffsetSeconds, sequence);
  fault-receipt.json (startedMonotonic, appliedMonotonic, revertingMonotonic, readyAtMonotonic, probes); application.log
  (`docker compose logs --timestamps`); cpu.json (M); system-samples.json (S); traces-normalized.json plus
  jaeger-raw-remainder.json (T, all services). Metrics and ledger go through sensor_rep/parsers/hotel.parse_cell unchanged;
  logs and spans are re-read here because of the Docker stamp and the token rule below.
  A cell is NOT SCORED, listed with its reason, when: cell-terminal.json is missing (a cell that stopped the campaign
  leaves a contract-only directory) or its candidateCellValid is not true (such cells are never parsed); its regime is
  unknown; a fault regime has no fault-receipt.json or the no-fault regime has one; the receipt's target is not the
  regime's; or parsing raises (the error is recorded, the run continues).
PROVENANCE: the JSON records the harness commit (campaign runtime-admission.json bindings.frameworkCommit, else `—`), the
  plan and admission digests named by the cell contracts, and sha256 over the sorted (relative path, size) of every file
  read.
ONSET AND WINDOW: as dbebcbb, the fault window is [receipt startedMonotonic (pre-command bound, F-ADH-085),
  revertingMonotonic]; a miss is charged at that hold end. No-fault cells: the contract's pseudo window
  (`scoredWindowSeconds`, the same seeded onset phase) on the barrier. The scheduled onset and its lag to the command
  bound are reported per episode.
PROBE WINDOWS (item 2; [D] Analysis definitions, first bullet): receipt `probes` [startMonotonic, endMonotonic] (pre and
  during) and [revertingMonotonic, readyAtMonotonic] (recovery polling), mapped to the wall clock through the barrier.
  Every sensor sample or record observed inside one is dropped (from the pre-window baseline too), so it can be no
  catch; for the `absent` rule only, in-window records still count as the stream being alive (dropping them must not
  fabricate silence). A catch whose time falls inside a window moves to that window's end (past the hold end it is no
  catch). The ledger is not touched.
  Spans: a trace with a frontend root span that carries no `obsplacement.opaque_token` tag is dropped whole (probe,
  warm-up and readiness requests carry no token); traces with no frontend root (all-services remainder) are kept.
  VARIANTS (review M1; the primary is PRIMARY_PROBE, a user decision, "declared" until changed): "declared" = the rule
  above; "scope" = window exclusion and the move only for logs and metrics of the services the hung probe touches
  (frontend and the fault target), every other record kept, spans by token only; "none" = no window exclusion and no
  move (the token rule stays), sensitivity only. All three are computed at the reference point side by side; the grid
  runs on the primary. A P3/P4 verdict that differs between the primary and "none" is rendered "decided by the probe
  rule". The chosen sensor's move (s) is reported per P4 fold and per P3 episode, and the during-probe window length per
  episode (under a pause it is ~[applied + 0.25, applied + 5.3] s at every rate: compose_pause.py:54-62, 173-187).
STAMPS ([D] Analysis definitions, Stamps): a log record's time is the Docker receive stamp of its first line when the
  line has one; otherwise the app stamp, timed by dbebcbb's whole-second rule (s + 1 s, cap at the hold end). Decided
  per cell (a cell whose log records all have integral stamps), never campaign-wide.
GRID ([D] "Ledger rule ... scored on the same K x floor grid as the sensors"; protocol §3): K in {3, 4, 5} x latency floor
  in {0.5, 1, 2} ms, applied to the span-latency and ledger-latency floors; metric floors stay sensor_rep's per-resource
  floors (K applies). Reference point K = 4, floor 1 ms (= dbebcbb, checked equal by a test); every prediction is also
  reported as the number of grid points (of 9) that give the reference verdict.
G3 per rate (dbebcbb's arithmetic, tau = 0.05): no-fault windows of the same rate, one per valid no-fault cell (n = 4 per
  rate, so k = 0 is required; uncertified). False alarms ([D] False alarms): per rate on the same windows, leave-one-cell-
  out admissibility, the class's filters (outside/own, spike path, BC), k/n windows, reported beside the score.
PRIMARY (item 3; [D] Outcomes 1): per (class, rate, family column), mean time to detection over ALL episodes with a miss
  charged the episode's hold; with and without BC catches for sensors; the ledger E keeps its catches in both views
  ([D] "BC filters candidate sensors, never the ledger baseline"). Own sensors of the target are separate columns.
SECONDARY ([D] Outcomes 2): failed requests (outcome not completed-200) whose SCHEDULED time lies in [onset, onset + time to
  detection]; a miss counts the whole hold. Requests scheduled before the onset and failing after it are not counted.
P1 ([D] Predictions): search-pause, per episode, |E - (wait to the first scheduled request >= onset + client timeout)|
  <= 0.5 s. E at the reference point, BC included.
P2: search-pause, per rate, failed requests scheduled before the ledger's first `failed`-rule catch <= 1 + rate x 1 s + 2,
  in >= 3 of 4 episodes. Per-episode counts are reported.
P3: declared testable set only: (search-pause, S outside the target), (cpu-throttle, S of the target). Family time without
  BC, mean over the 4 episodes: at 0.05/s <= at 10/s + 5 s (S cadence). A cell whose family detects in 0 of 4 episodes at
  10/s is "untestable", not a failure.
P4 (item 4; [D] P4 and Selection vs evaluation): per (class, rate), leave-one-episode-out: the candidate sensor with the
  lowest mean time on three episodes (misses at hold) is scored on the fourth against the ledger in the same episode
  (strictly lower = a win). Holds iff wins >= 3 of 4. P4a: sensors outside the target, without BC; P4b: the target's own
  sensors, without BC (with BC beside). Reported: the highest rate where it holds, or "none in {10, 1, 0.2, 0.05}".
  Fewer than 4 evaluable episodes at a (class, rate): `—` (not evaluable), never "none"; the highest-rate text then
  names the rates that were `—`.
BY CONSTRUCTION (item 5; [D] By-construction "flagged by content (the record names the callee), incl. BC-caller-log"):
  dbebcbb's flags, except BC-caller-log, which here fires on a warn/error/other log template of any non-target service,
  by `appear`, whose masked message names the target (its service name or one of its gRPC method names, as whole words).
  BC-caller-span, two variants side by side (review, open point 2; the primary is PRIMARY_CALLER_SPAN, a user decision,
  "kind" until changed): "kind" = dbebcbb (detection_time.py:309, stopping faults only); "content" = the same test with
  the stopping-fault condition dropped (a non-target span whose op is one of the target's ops, every fault class), in a
  local override; detection_time.py is not edited.
Absent is never zero: a family whose channel file is missing in every episode prints `—`; a denominator of 0 prints `—`.
"""
import argparse
import bisect
import datetime as _dt
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import detection_time as dt  # noqa: E402  dbebcbb, unchanged; it puts research/protocol on sys.path
from sensor_rep import catch  # noqa: E402
from sensor_rep.events import Event, group, level_class, stream_meta  # noqa: E402
from sensor_rep.parsers import common, hotel  # noqa: E402

DECLARATION = "research/traffic-sweep/DECLARATION.md (frozen a795fc9) + research/traffic-sweep/AMENDMENT_1.md"
BASE_COMMIT = "dbebcbb"
SUT, ENTRY = "hotel", dt.ENTRY["hotel"]
RATES = (10.0, 1.0, 0.2, 0.05)                    # [D] Design: rates, highest first
NOFAULT = "no-fault-calibration"
FAULT_REGIMES = ("search-pause-effect", "cpu-throttle-effect", "net-delay-effect")
FAULT_TARGETS = {"search-pause-effect": ("search", "pause"), "cpu-throttle-effect": ("profile", "degradation"),
                 "net-delay-effect": ("rate", "degradation")}   # candidate_sweep.FAULTS + lmt_faults / compose_pause
EPISODES = 4                                      # [D] Episodes: 4 per (regime, rate)
GRID_K = (3.0, 4.0, 5.0)                          # protocol §3 robustness grid
GRID_FLOOR_MS = (0.5, 1.0, 2.0)
REF = (4.0, 1.0)                                  # dbebcbb's setting
FAMILIES = ("E", "L", "M", "S", "T")              # posture `full` only: spans are T, never Tsel
COLUMNS = ("E", "L", "M", "S", "T", "L:own", "M:own", "S:own", "T:own")
FAMILY_FILE = {"L": ("log", "log"), "M": ("metric", "metric:docker-stats"), "S": ("metric", "metric:cgroup-sampler"),
               "T": ("span", "span")}
P1_TOL_S = 0.5                                    # [D] P1 within ±0.5 s
P2_DOBS_S = 1.0                                   # [D] P2 1 + rate x 1 s + 2
P2_EPS = 2.0
P3_CADENCE_S = {"M": 3.0, "S": 5.0}               # [D] P3 one sampling cadence (M ~3 s, S 5 s)
P3_TESTABLE = (("search-pause-effect", "S", False), ("cpu-throttle-effect", "S", True))
P3_RATES = (10.0, 0.05)
P4_MIN = 3                                        # [D] P4 >= 3 of 4 paired episodes
TOKEN_TAG = "obsplacement.opaque_token"
TOKEN = re.compile(r"^hr-[0-9a-f]{32}$")          # workload/candidate_search.py TOKEN
DOCKER_TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z(?: |$)")
DASH = "—"
READ_FILES = ("cell-contract.json", "cell-terminal.json", "opportunity-plan.json", "opportunity-ledger.jsonl",
              "fault-receipt.json", "application.log", "cpu.json", "system-samples.json", "traces-normalized.json",
              "jaeger-raw-remainder.json")

# User decisions (review M1 and open point 2). Every variant is computed and reported; these name the primary.
PROBE_VARIANTS = ("declared", "scope", "none")
PRIMARY_PROBE = "scope"
CALLER_SPAN_VARIANTS = ("kind", "content")
PRIMARY_CALLER_SPAN = "content"

# Switches flipped only by tests/test_sweep_analysis.py (planted defects); the analysis never changes them.
PROBE_EXCLUDE = True          # drop samples inside probe windows
PROBE_MOVE = True             # move a catch inside a probe window to the window end
PROBE_LIVENESS = True         # records inside a probe window still count as liveness for `absent`
TOKEN_FILTER = True           # drop traces of untokenised frontend requests
DOCKER_STAMP = True           # time log records at the Docker receive stamp
MISS_AT_HOLD = True           # average over all episodes, a miss charged at the hold end
COUNT_BY_SCHEDULED = True     # impact counted by scheduled time
P2_INCLUSIVE = True           # P2 comparator `<=`
LOEO = True                   # select on the three other episodes
ABSENT_DASH = True            # render an absent column as `—`
WS_PER_CELL = True            # whole-second log rule decided per cell, not campaign-wide
G3_PER_RATE = True            # G3 and false alarms keyed by rate, never pooled across rates


def g3key(rate):
    return rate if G3_PER_RATE else "pooled"


# =========================================================================== pure helpers

def docker_stamp(text):
    """`2026-10-03T05:10:00.123456789Z <line>` -> (epoch seconds, <line>); (None, text) without a stamp."""
    m = DOCKER_TS.match(text)
    if not m:
        return None, text
    base = _dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt.timezone.utc).timestamp()
    frac = m.group(2) or ""
    return base + (int(frac) / 10.0 ** len(frac) if frac else 0.0), text[m.end():]


def in_any(t, wins):
    return any(lo <= t <= hi for lo, hi in wins)


def exclude(obs, vals, wins):
    """Samples observed inside a probe window are not scored ([D] probe windows). Returns (obs, vals, dropped)."""
    if not wins or not PROBE_EXCLUDE:
        return obs, vals, 0
    keep = [i for i, t in enumerate(obs) if not in_any(t, wins)]
    if len(keep) == len(obs):
        return obs, vals, 0
    return [obs[i] for i in keep], [vals[i] for i in keep], len(obs) - len(keep)


def move_out(t, wins):
    """A catch at t inside a probe window moves to that window's end ([D]); chained windows are followed."""
    moved = False
    if PROBE_MOVE:
        for lo, hi in sorted(wins):
            if lo <= t < hi:
                t, moved = hi, True
    return t, moved


def summarise(hits, holds):
    """hits: time to detection per episode (None = miss); holds: the episode's hold. Primary outcome ([D] Outcomes 1)."""
    t = [h for h in hits if h is not None]
    if MISS_AT_HOLD:
        pen = statistics.mean(h if h is not None else H for h, H in zip(hits, holds)) if hits else None
    else:
        pen = statistics.mean(t) if t else None
    return {"k": len(t), "n": len(hits), "ttd": dt.dist(t), "penalisedMeanTtd": pen, "perEpisode": list(hits)}


def failed_before(reqs, a, t_end):
    """[D] Outcomes 2: failed requests started before the first catch, counted by SCHEDULED time in [a, t_end].
    reqs: (start, end, ok, route, sequence, scheduled) on the monotonic clock."""
    i = 5 if COUNT_BY_SCHEDULED else 0
    return sum(1 for r in reqs if not r[2] and a <= r[i] <= t_end)


def p1_expected(reqs, a, timeout):
    """[D] P1: the wait to the first scheduled request at or after onset plus the client timeout."""
    sched = sorted(r[5] for r in reqs)
    i = bisect.bisect_left(sched, a)
    return None if i == len(sched) else sched[i] - a + timeout


def p1_ok(observed, expected, tol=P1_TOL_S):
    return observed is not None and expected is not None and abs(observed - expected) <= tol + 1e-12


def p2_threshold(rate):
    return 1.0 + rate * P2_DOBS_S + P2_EPS


def p2_ok(count, rate):
    thr = p2_threshold(rate)
    return count <= thr + 1e-9 if P2_INCLUSIVE else count < thr - 1e-9


def p2_verdict(counts, rate):
    """[D] P2: in >= 3 of 4 episodes per rate. Fewer than 4 episodes: not evaluable (None)."""
    ok = [p2_ok(c, rate) for c in counts]
    return {"k": sum(ok), "n": len(ok), "threshold": p2_threshold(rate), "perEpisode": list(counts),
            "holds": (sum(ok) >= 3) if len(ok) == EPISODES else None}


def loeo(cands, ledger, holds):
    """[D] P4 + Selection vs evaluation. cands {sensor: [ttd|None per episode]}, ledger [ttd|None], holds [s].
    Per held-out episode: the sensor with the lowest mean over the other episodes (miss = hold; a sensor that misses
    every training episode is not selectable; ties by sensor id) is compared with the ledger in that episode; a win is
    a strictly lower time (a miss counts as the hold). Returns (folds, wins)."""
    n = len(holds)
    folds, wins = [], 0
    for i in range(n):
        train = [j for j in range(n) if j != i] if LOEO else list(range(n))
        best = None
        for s in sorted(cands):
            ts = cands[s]
            if all(ts[j] is None for j in train):
                continue
            score = statistics.mean(ts[j] if ts[j] is not None else holds[j] for j in train)
            if best is None or score < best[0]:
                best = (score, s)
        s = best[1] if best else None
        st = cands[s][i] if s else None
        sv = st if st is not None else holds[i]
        lv = ledger[i] if ledger[i] is not None else holds[i]
        win = s is not None and sv < lv
        wins += win
        folds.append({"heldOut": i, "sensor": s, "trainMean": best[0] if best else None, "sensorTtd": st,
                      "ledgerTtd": ledger[i], "win": win})
    return folds, wins


def p4_holds(wins, n):
    return (wins >= P4_MIN) if n == EPISODES else None


def highest_rate(per_rate):
    """[D] P4 reported: the highest rate where the criterion holds, or "none in {10, 1, 0.2, 0.05}"."""
    ev = [r for r in RATES if per_rate.get(r) is not None and per_rate[r].get("holds") is not None]
    hit = [r for r in ev if per_rate[r]["holds"]]
    if hit:
        return "%g" % hit[0]
    s = "none in {%s}" % ", ".join("%g" % r for r in ev) if ev else DASH
    missing = [r for r in RATES if r not in ev]
    if ev and missing:
        s += "; — at {%s}" % ", ".join("%g" % r for r in missing)
    return s


def callee_names(target, ops):
    names = {target.lower()}
    for tok in ops.get(target, ()):
        if tok.startswith("/"):
            m = tok.split(":error")[0].rsplit("/", 1)[-1]
            if len(m) >= 4:
                names.add(m.lower())
    return names


def names_callee(msg, target, ops):
    low = (msg or "").lower()
    return any(re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(nm), low) for nm in callee_names(target, ops))


def bc_flags(f, target, kind, ctx, text, caller_span="kind"):
    """dbebcbb's taxonomy (dt.bc_flags) with BC-caller-log decided by content ([D] By-construction). caller_span "kind":
    BC-caller-span as dbebcbb (stopping faults only); "content": the same test without the stopping condition."""
    flags = [x for x in dt.bc_flags(f, target, kind, ctx) if x != "BC-caller-log"]
    if caller_span == "content" and "BC-caller-span" not in flags and f["ch"] == "span" and f["svc"] != target \
            and f["tok"].split(":error")[0] in ctx["ops"].get(target, ()):
        flags.append("BC-caller-span")
    if f["ch"] == "log" and f["rule"] == "appear" and f.get("level") in dt.CALLER_LOG_LEVELS and f["svc"] != target:
        lm = text.get((f["svc"], f["tok"]))
        if lm and names_callee(lm[1], target, ctx["ops"]):
            flags.append("BC-caller-log")
    return flags


# =========================================================================== reading one cell

def read_logs(attempt, posture, stats):
    """application.log -> (events or None if the file is absent, {(svc, template): (level, masked message)})."""
    S = common.symptoms()
    p = attempt / "application.log"
    if not p.exists():
        return None, {}
    lines, stamps = defaultdict(list), defaultdict(list)
    for raw in p.read_text(errors="replace").splitlines():
        if " | " not in raw:
            stats["composeCliLines"] += 1
            continue
        prefix, payload = raw.split(" | ", 1)
        svc = prefix.strip().rsplit("-", 1)[0]
        t, rest = docker_stamp(payload)
        if t is None:
            stats["logLinesWithoutDockerStamp"] += 1
        else:
            stats["logLinesWithDockerStamp"] += 1
        lines[svc].append(rest)
        stamps[svc].append(t)
    evs, text = [], {}
    for svc in sorted(lines):
        st = stamps[svc]
        stamped = DOCKER_STAMP and any(x is not None for x in st)
        records, _ = S.parse_stream(lines[svc], S.HOTEL_LAYOUTS, stamp=(lambda i, _s=st: _s[i]) if stamped else None)
        for r in records:
            if r["framework"] == "jvm-throwable":
                continue
            tid = S.template_id(r["framework"], r["level"], r["key"], r["msg"])
            lv = level_class(r["framework"], r["level"])
            if r["t"] is None:
                stats["logRecordsUntimed"] += 1
            stats["logRecords"] += 1
            m = stream_meta(SUT, posture, "log", svc, "application", "compose-logs", "wall", "per-record", lv)
            evs.append(Event("log", svc, tid, r["t"], 1.0, m))
            text.setdefault((svc, tid), (lv, S.mask(r["msg"])[:200]))
    return evs, text


def _remainder_spans(doc):
    """jaeger-raw-remainder.json (raw Jaeger v1 traces) -> normalized-like span dicts (normalizers/jaeger.py fields)."""
    out = []
    for q in doc.get("queries") or []:
        for trace in q.get("traces") or []:
            procs = {k: (v or {}).get("serviceName") for k, v in (trace.get("processes") or {}).items()}
            for sp in trace.get("spans") or []:
                refs = [r for r in sp.get("references") or [] if r.get("refType") == "CHILD_OF"]
                out.append({"traceId": trace.get("traceID"), "spanId": sp.get("spanID"),
                            "parentSpanId": refs[0].get("spanID") if refs else None,
                            "service": procs.get(sp.get("processID")), "operation": sp.get("operationName"),
                            "startTimeUs": sp.get("startTime"), "durationUs": sp.get("duration"),
                            "tags": {str(t.get("key")): t.get("value") for t in sp.get("tags") or [] if t.get("key")}})
    return out


def read_spans(attempt, posture, stats):
    """traces-normalized.json + jaeger-raw-remainder.json -> span events (None if neither file exists)."""
    S = common.symptoms()
    p, rp = attempt / "traces-normalized.json", attempt / "jaeger-raw-remainder.json"
    if not p.exists() and not rp.exists():
        return None
    spans = json.loads(p.read_text())["events"] if p.exists() else []
    if rp.exists():
        rem = _remainder_spans(json.loads(rp.read_text()))
        stats["remainderSpans"] += len(rem)
        spans = spans + rem
    seen, uniq = set(), []
    for e in spans:
        key = (e.get("traceId"), e.get("spanId"))
        if key in seen:
            stats["duplicateSpans"] += 1
            continue
        seen.add(key)
        uniq.append(e)
    by_trace = defaultdict(list)
    for e in uniq:
        by_trace[e.get("traceId")].append(e)
    keep = set()
    for tid, es in by_trace.items():
        entry_root = any(e.get("parentSpanId") is None and e.get("service") == ENTRY for e in es)
        tokened = any(TOKEN.match(str((e.get("tags") or {}).get(TOKEN_TAG, ""))) for e in es)
        if TOKEN_FILTER and entry_root and not tokened:
            stats["tracesExcludedNoToken"] += 1
            stats["spansExcludedNoToken"] += len(es)
            continue
        keep.add(tid)
    out = []
    for e in uniq:
        if e.get("traceId") not in keep:
            continue
        if e.get("startTimeUs") is None or e.get("durationUs") is None or not e.get("service") or not e.get("operation"):
            stats["spansUnusable"] += 1
            continue
        tok = S.op_token(e["operation"])
        m = stream_meta(SUT, posture, "span", e["service"], "application", "jaeger", "wall", "per-record")
        t, d = e["startTimeUs"] / 1e6, e["durationUs"] / 1e6
        out.append(Event("span", e["service"], tok, t, d, m))
        if S.span_error(e):
            out.append(Event("span", e["service"], tok + ":error", t, d, m))
    stats["spansKept"] += len(out)
    return out


def read_ledger(attempt, plan):
    """(start, end, ok, route, sequence, scheduled) per offered request, monotonic clock, sorted by end.
    ok = outcome completed and status 200 (visibility.hotel_ledger_rows); scheduled = barrier + scheduled offset."""
    bm, route = float(plan["barrierMonotonic"]), plan.get("workloadId", "?")
    reqs = []
    for line in (attempt / "opportunity-ledger.jsonl").open():
        row = json.loads(line)
        s, e = float(row["actualStartMonotonic"]), float(row["actualEndMonotonic"])
        reqs.append((s, e, row["outcome"] == "completed" and row.get("statusCode") == 200, route,
                     int(row.get("sequence", len(reqs))), bm + float(row["scheduledMonotonicOffsetSeconds"])))
    return sorted(reqs, key=lambda r: r[1])


def probe_windows(receipt):
    """[D] probe windows: receipt `probes` (pre, during) and [revertingMonotonic, readyAtMonotonic]. Monotonic."""
    out = []
    for p in receipt.get("probes") or []:
        if p.get("startMonotonic") is not None and p.get("endMonotonic") is not None:
            out.append((float(p["startMonotonic"]), float(p["endMonotonic"]), "probe-%s" % p.get("phase")))
    rev = receipt.get("revertingMonotonic")
    end = receipt.get("readyAtMonotonic")
    if end is None:
        end = receipt.get("endedMonotonic")
    if rev is not None and end is not None:
        out.append((float(rev), float(end), "recovery"))
    return sorted(out)


def load_cell(attempt):
    attempt = Path(attempt)
    c = hotel.parse_cell(attempt, "sweep")          # metrics, ledger events, barrier, validity, target (unchanged)
    contract = json.loads((attempt / "cell-contract.json").read_text())
    timing = contract.get("timing") or {}
    plan = json.loads((attempt / "opportunity-plan.json").read_text())
    stats = Counter()
    log_ev, text = read_logs(attempt, c["posture"], stats)
    span_ev = read_spans(attempt, c["posture"], stats)
    ev = [e for e in c.pop("events") if e.channel not in ("log", "span")] + (log_ev or []) + (span_ev or [])
    c["channels"]["log"]["present"] = log_ev is not None
    c["channels"]["span"]["present"] = span_ev is not None
    c["streams"] = group(ev)
    c["chans"] = {"ledger"} | {k.split(":")[0] for k, v in c["channels"].items() if v.get("present")}
    c["prep"] = dt.prep_streams(c)
    c.pop("streams")
    bw, bm = c["base"]["wall"], c["base"]["mono"]
    c["rate"] = float(timing.get("requestsPerSecond", contract.get("runKey", {}).get("requestsPerSecond")))
    c["timing"] = timing
    win = timing.get("scoredWindowSeconds") or [timing["faultOnsetSeconds"],
                                                 float(timing["faultOnsetSeconds"]) + float(timing["faultHoldSeconds"])]
    c["scheduledOnset"] = {"mono": bm + float(win[0]), "wall": bw + float(win[0])}
    c["ledger"] = read_ledger(attempt, plan)
    c["units"] = len(c["ledger"])
    c["t0"] = {"wall": bw, "mono": None}
    c["probes"] = {"mono": [], "wall": []}
    c["probeWindows"] = []
    if c["target"]:
        r = json.loads((attempt / "fault-receipt.json").read_text())
        a, b = float(r["startedMonotonic"]), float(r["revertingMonotonic"])
        c["cmd"] = {"A": {"mono": a, "wall": bw + a - bm}, "B": {"mono": b, "wall": bw + b - bm},
                    "commandSeconds": float(r["appliedMonotonic"]) - a if r.get("appliedMonotonic") is not None else None,
                    "onsetSource": "fault-receipt startedMonotonic"}
        if "probes" not in r:
            stats["receiptWithoutProbes"] += 1
        wins = probe_windows(r)
        c["probeWindows"] = [{"kind": k, "startMono": lo, "endMono": hi, "seconds": hi - lo} for lo, hi, k in wins]
        c["probes"] = {"mono": [(lo, hi) for lo, hi, _ in wins],
                       "wall": [(bw + lo - bm, bw + hi - bm) for lo, hi, _ in wins]}
    else:
        a, b = bm + float(win[0]), bm + float(win[1])
        c["cmd"] = {"A": {"mono": a, "wall": bw + a - bm}, "B": {"mono": b, "wall": bw + b - bm},
                    "commandSeconds": None, "onsetSource": "cell-contract timing scoredWindowSeconds (pseudo window)"}
    c["family"] = lambda ch, coll, posture: hotel.family(ch, coll, posture)
    c["channelsPresent"] = {k: bool(v.get("present")) for k, v in c["channels"].items()}
    c["logText"] = text
    c["readStats"] = dict(stats)
    # [D] Stamps: the whole-second rule only for a cell whose own log stamps are all integral (review m1)
    c["wsLogs"] = dt.whole_second_logs([c])[0]
    c["planSha256"] = contract.get("compiledPlanCanonicalSha256")
    c["admissionSha256"] = contract.get("admissionCanonicalSha256")
    dur = [p["seconds"] for p in c["probeWindows"] if p["kind"] == "probe-during"]
    c["duringWindowSeconds"] = sum(dur) if dur else None
    c["reason"] = None
    return c


def invalid_cell(d, contract, reason):
    """A cell that is listed, never scored (review B1, M3)."""
    contract = contract if isinstance(contract, dict) else {}
    rk, timing = contract.get("runKey") or {}, contract.get("timing") or {}
    rate = timing.get("requestsPerSecond", rk.get("requestsPerSecond"))
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = None
    return {"cell": common.rel(d), "regime": rk.get("regime") or "?", "rate": rate, "block": rk.get("block"),
            "valid": False, "target": None, "reason": reason, "readStats": {},
            "planSha256": contract.get("compiledPlanCanonicalSha256"),
            "admissionSha256": contract.get("admissionCanonicalSha256")}


def load_or_invalid(d):
    """Gatekeeping before parsing: only a finished, valid cell whose regime agrees with its receipt is parsed; any
    parse error makes the cell not scored (recorded) instead of killing the run."""
    d = Path(d)
    try:
        contract = json.loads((d / "cell-contract.json").read_text())
    except (OSError, ValueError) as exc:
        return invalid_cell(d, None, "cell-contract.json unreadable: %s" % exc)
    term = d / "cell-terminal.json"
    if not term.exists():
        return invalid_cell(d, contract, "no cell-terminal.json (the cell did not finish)")
    try:
        verdict = json.loads(term.read_text()).get("candidateCellValid")
    except (OSError, ValueError, AttributeError) as exc:
        return invalid_cell(d, contract, "cell-terminal.json unreadable: %s" % exc)
    if verdict is not True:
        return invalid_cell(d, contract, "candidateCellValid is %r" % (verdict,))
    regime = (contract.get("runKey") or {}).get("regime")
    if regime not in (NOFAULT,) + FAULT_REGIMES:
        return invalid_cell(d, contract, "unknown regime %r" % (regime,))
    has_receipt = (d / "fault-receipt.json").exists()
    if has_receipt != (regime != NOFAULT):
        return invalid_cell(d, contract, "%s fault-receipt.json for regime %s" % ("a" if has_receipt else "no", regime))
    try:
        c = load_cell(d)
    except Exception as exc:  # noqa: BLE001 - recorded per cell; the campaign readout must still be written
        return invalid_cell(d, contract, "parse error: %s: %s" % (type(exc).__name__, exc))
    if (c["target"] is None) != (regime == NOFAULT):
        return invalid_cell(d, contract, "target %r for regime %s" % (c["target"], regime))
    if regime != NOFAULT and c["target"] != FAULT_TARGETS[regime][0]:
        return invalid_cell(d, contract, "receipt target %r, regime %s expects %r" % (
            c["target"], regime, FAULT_TARGETS[regime][0]))
    return c


def input_digest(root, dirs):
    """sha256 over the sorted (relative path, size) of every file the analysis reads (review m4)."""
    rows = []
    for p in [root / "runtime-admission.json"] + [d / f for d in dirs for f in READ_FILES]:
        if p.is_file():
            rows.append("%s\t%d" % (p.relative_to(root).as_posix(), p.stat().st_size))
    rows.sort()
    return {"files": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}


def harness_commit(root):
    try:
        return json.loads((root / "runtime-admission.json").read_text())["bindings"]["frameworkCommit"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def find_cells(campaign):
    campaign = Path(campaign)
    if not (campaign / "runs").is_dir():
        kids = [d for d in campaign.iterdir() if (d / "runs").is_dir()] if campaign.is_dir() else []
        if len(kids) != 1:
            raise SystemExit("no runs/ under %s (and not exactly one child holding one)" % campaign)
        campaign = kids[0]
    return campaign, sorted(d for d in (campaign / "runs").glob("**/attempt-01")
                            if d.is_dir() and (d / "cell-contract.json").exists())


# =========================================================================== one window (dt.eval_window + grid + probes)

def route_baselines(reqs, a, k, floor_ms):
    """dt.route_baselines with the latency floor as a grid parameter."""
    base = defaultdict(list)
    for r in reqs:
        if r[1] < a and r[2]:
            base[r[3]].append((r[1] - r[0]) * 1000.0)
    return {route: dt.threshold(v, floor_ms, k) for route, v in base.items() if len(v) >= dt.MIN_BASELINE}


def eval_window(c, A, B, ws_logs, k=REF[0], floor_ms=REF[1], probes=None, dropped=None, scope=None):
    """dt.eval_window (dbebcbb) line for line, with K and the latency floor as parameters and the probe rule.
    At the reference point without probes it returns what dt.eval_window returns (tested). scope: None = the probe
    windows apply to every sensor ("declared"); a set of services = only to logs and metrics of those ("scope")."""
    probes = probes or {}
    fires, straddle, moved_out = [], [], []
    t0 = c["t0"]
    for (ch, svc, tok), (obs, vals, meta) in c["prep"].items():
        if ch not in c["chans"]:
            continue
        clk = meta["clock"]
        wins = probes.get(clk, ()) if (scope is None or (svc in scope and ch in ("log", "metric"))) else ()
        obs_all = obs
        obs, vals, nd = exclude(obs, vals, wins)
        if nd and dropped is not None:
            dropped[ch] += nd
        a, b = A[clk], B[clk]
        a_in = math.floor(a) if (ch == "log" and ws_logs) else a
        lo = 0 if t0.get(clk) is None else bisect.bisect_left(obs, t0[clk])
        ia, ib = bisect.bisect_left(obs, a_in), bisect.bisect_right(obs, b)
        got = {}
        if ch in ("log", "span"):
            got.update(dt.count_rules(obs[lo:ia], obs[ia:ib], a_in, b, tok.endswith(":error")))
            if nd and PROBE_LIVENESS:
                # absent: a record inside a probe window is not scored, but it still shows the stream is alive, so
                # dropping it must not fabricate silence (the catch would be true by construction)
                alive = dt.count_rules(obs[lo:ia], obs_all[bisect.bisect_left(obs_all, a_in):bisect.bisect_right(obs_all, b)],
                                       a_in, b, tok.endswith(":error"))
                got.pop("absent", None)
                if "absent" in alive:
                    got["absent"] = alive["absent"]
        if ch == "metric" or (ch == "span" and not tok.endswith(":error")):
            pre = vals[lo:ia]
            if len(pre) >= dt.MIN_BASELINE and ib > ia:
                fl = floor_ms / 1000.0 if ch == "span" else catch.level_floor(ch, tok, statistics.median(pre))
                m, thr = dt.threshold(pre, fl, k)
                got.update(dt.level_rules(obs[ia:ib], vals[ia:ib], m, thr, ("up", "down") if ch == "metric" else ("up",)))
        for rule, (t, d) in got.items():
            t_orig = t
            t, moved = move_out(t, wins)
            if moved and t > b:
                moved_out.append((ch, svc, tok, rule))
                continue
            if ch == "log":
                lt = dt.log_ttd(t, a, ws_logs, b)
                if lt is None:
                    straddle.append((ch, svc, tok, rule))
                    continue
                tlo, ttd = lt
            else:
                tlo, ttd = max(0.0, t - a), max(0.0, t - a)
            fires.append({"ch": ch, "svc": svc, "tok": tok, "rule": rule, "ttd": ttd, "ttdLo": tlo, "dir": d,
                          "level": meta.get("level"), "family": c["family"](ch, meta.get("collector"), c["posture"]),
                          "moved": moved, "movedBy": t - t_orig})
    base = route_baselines(c["ledger"], A["mono"], k, floor_ms)
    led, base, unknown = dt.ledger_rules(c["ledger"], A["mono"], B["mono"], k=k, base=base)
    for (route, rule), t in led.items():
        fires.append({"ch": "ledger", "svc": ENTRY, "tok": route, "rule": rule, "ttd": max(0.0, t - A["mono"]),
                      "dir": "up", "level": None, "family": "E", "moved": False, "movedBy": 0.0})
    c["_straddle"], c["_movedPastHoldEnd"] = straddle, moved_out
    return fires, base, sorted(unknown)


# =========================================================================== one grid point

def collects(c, fam):
    if fam == "E":
        return True
    ch, key = FAMILY_FILE[fam]
    return ch in c["chans"] and c["channelsPresent"].get(key, False)


def make_ctx(cells):
    edges, on_route = dt.call_graph(SUT)
    ops = defaultdict(set)
    for c in cells:
        for (ch, svc, tok) in c["prep"]:
            if ch == "span":
                ops[svc].add(tok.split(":error")[0])
    ws_logs, ws_counts = dt.whole_second_logs(cells)
    return {"edges": edges, "onRoute": on_route, "ops": ops, "wsLogs": ws_logs, "wsCounts": ws_counts}


def path_of(target, ctx):
    return dt.affected_path(target, ctx["edges"]) if target in ctx["onRoute"] else {target}


def ws_of(c, ctx):
    return c["wsLogs"] if WS_PER_CELL else ctx["wsLogs"]


def analyse(cells, ctx, k, floor_ms, probe_variant=None):
    probe_variant = probe_variant or PRIMARY_PROBE
    valid = [c for c in cells if c["valid"]]
    G = {"k": k, "floorMs": floor_ms, "probeVariant": probe_variant, "callerSpan": PRIMARY_CALLER_SPAN,
         "nofault": defaultdict(list), "g3": defaultdict(Counter), "episodes": []}
    for c in valid:
        if c["target"] is not None:
            continue
        fires, _, _ = eval_window(c, c["cmd"]["A"], c["cmd"]["B"], ws_of(c, ctx), k, floor_ms)
        G["nofault"][g3key(c["rate"])].append({"cell": c["cell"], "fires": fires,
                                               "g3": Counter(dt.fkey(f) for f in fires), "logText": c["logText"],
                                               "collects": {f: collects(c, f) for f in FAMILIES}})
        for f in fires:
            G["g3"][g3key(c["rate"])][dt.fkey(f)] += 1
    for c in valid:
        if c["target"] is None:
            continue
        A, B = c["cmd"]["A"], c["cmd"]["B"]
        dropped = Counter()
        probes = None if probe_variant == "none" else c["probes"]
        scope = {ENTRY, c["target"]} if probe_variant == "scope" else None
        fires, base, unknown = eval_window(c, A, B, ws_of(c, ctx), k, floor_ms, probes, dropped, scope)
        path = path_of(c["target"], ctx)
        n = len(G["nofault"][g3key(c["rate"])])
        for f in fires:
            kk = G["g3"][g3key(c["rate"])][dt.fkey(f)]
            counts, own = dt.scored(f, c["target"], path, ENTRY)
            f.update({"g3k": kk, "g3n": n, "admissible": dt.admissible(kk, n), "own": own, "onPath": f["svc"] in path,
                      "counts": counts})
            for cs in CALLER_SPAN_VARIANTS:
                f["bc:" + cs] = bc_flags(f, c["target"], c["faultKind"], ctx, c["logText"], cs)
            f["bc"] = f["bc:" + G["callerSpan"]]
        G["episodes"].append({
            "cell": c["cell"], "regime": c["regime"], "rate": c["rate"], "block": c["block"], "target": c["target"],
            "faultKind": c["faultKind"], "onset": A, "end": B, "holdSeconds": B["mono"] - A["mono"], "g3n": n,
            "scheduledOnsetMono": c["scheduledOnset"]["mono"], "onsetLagSeconds": A["mono"] - c["scheduledOnset"]["mono"],
            "commandSeconds": c["cmd"]["commandSeconds"], "duringWindowSeconds": c["duringWindowSeconds"],
            "affectedPath": sorted(path), "fires": fires,
            "droppedInProbeWindows": dict(dropped), "movedPastHoldEnd": ["%s:%s:%s/%s" % x for x in c.pop("_movedPastHoldEnd", [])],
            "logStraddlesHoldEnd": ["%s:%s:%s/%s" % x for x in c.pop("_straddle", [])],
            "ledgerRoutesWithoutBaseline": unknown, "ledgerBaseline": {r: list(v) for r, v in base.items()}, "_c": c})
    G["episodes"].sort(key=lambda e: (e["regime"], -e["rate"], e["block"]))
    return G


def set_caller_span(G, variant):
    """Point every fire's `bc` at one caller-span variant (both are stored on the fire)."""
    G["callerSpan"] = variant
    for e in G["episodes"]:
        for f in e["fires"]:
            f["bc"] = f["bc:" + variant]


def col_fire(ep, col, bc):
    """The column's first catch in one episode (a fire dict), None = miss, "absent" = not evaluable: the channel file
    is missing, or the rate has no valid no-fault window (G3 n = 0 admits nothing, so a miss would be fabricated)."""
    fam, own = col.split(":")[0], col.endswith(":own")
    if not collects(ep["_c"], fam) or not ep["g3n"]:
        return "absent"
    return dt.family_ttd(ep, fam, own=own, bc=bc or fam == "E")   # the ledger keeps its BC catches in both views


def col_hit(ep, col, bc):
    h = col_fire(ep, col, bc)
    return h if h in ("absent", None) else h["ttd"]


def eps_of(G, regime, rate):
    return [e for e in G["episodes"] if e["regime"] == regime and e["rate"] == rate]


def false_alarms(G, ctx, regime, rate, fam, own, bc):
    """[D] False alarms: per rate, no-fault windows at the same onset phase, leave-one-cell-out admissibility, the
    class's filters. fam None = any sensor family (the candidate pool of P4). {k, n} with n = windows that collect it."""
    target, kind = FAULT_TARGETS[regime]
    path = path_of(target, ctx)
    wins = G["nofault"].get(g3key(rate), [])
    n_tot = len(wins)
    fired, n, times = 0, 0, []
    for w in wins:
        if fam is not None and not w["collects"].get(fam, False):
            continue
        n += 1
        first = None
        for f in w["fires"]:
            if fam is None and f["family"] == "E":
                continue
            if fam is not None and f["family"] != fam:
                continue
            if f["family"] == "E" and f["rule"] not in dt.E_RULES:
                continue
            if not dt.admissible(G["g3"][g3key(rate)][dt.fkey(f)] - w["g3"][dt.fkey(f)], n_tot - 1):
                continue
            counts, is_own = dt.scored(f, target, path, ENTRY)
            if not counts or is_own != own:
                continue
            if not bc and f["family"] != "E" and bc_flags(f, target, kind, ctx, w["logText"], G["callerSpan"]):
                continue
            first = f["ttd"] if first is None else min(first, f["ttd"])
        if first is not None:
            fired += 1
            times.append(first)
    return {"k": fired, "n": n, "timeToFirstFalseAlarm": dt.dist(times)}


def primary(G, ctx):
    rows = []
    for regime in FAULT_REGIMES:
        for rate in RATES:
            eps = eps_of(G, regime, rate)
            row = {"regime": regime, "rate": rate, "n": len(eps), "columns": {}}
            for col in COLUMNS:
                fam, own = col.split(":")[0], col.endswith(":own")
                if fam == "E" and own:
                    continue
                v = {}
                for bc in (True, False):
                    pairs = [(col_hit(e, col, bc), e) for e in eps]
                    pairs = [(h, e) for h, e in pairs if h != "absent"]
                    if not pairs:
                        v = None
                        break
                    s = summarise([h for h, _ in pairs], [e["holdSeconds"] for _, e in pairs])
                    s["falseAlarms"] = false_alarms(G, ctx, regime, rate, fam, own, bc)
                    v["bc" if bc else "noBC"] = s
                row["columns"][col] = v
            rows.append(row)
    return rows


def secondary(G):
    """[D] Outcomes 2 per (class, rate, column): failed requests scheduled in [onset, onset + time to detection]."""
    rows = []
    for regime in FAULT_REGIMES:
        for rate in RATES:
            eps = eps_of(G, regime, rate)
            row = {"regime": regime, "rate": rate, "n": len(eps), "columns": {}}
            for col in COLUMNS:
                if col == "E:own":
                    continue
                per = []
                for e in eps:
                    h = col_hit(e, col, col.startswith("E"))     # sensors without BC; the ledger with its catches
                    if h == "absent":
                        continue
                    a = e["onset"]["mono"]
                    t_end = a + (h if h is not None else e["holdSeconds"])
                    per.append({"block": e["block"], "detected": h is not None, "failedBefore": failed_before(e["_c"]["ledger"], a, t_end)})
                row["columns"][col] = ({"n": len(per), "detected": sum(p["detected"] for p in per),
                                        "failedBefore": dt.dist([p["failedBefore"] for p in per]), "perEpisode": per}
                                       if per else None)
            rows.append(row)
    return rows


def per_sensor(G):
    """[D] Outcomes 1 "per sensor": every sensor (channel:service:token) with an admissible, path-scored catch in a
    (class, rate), its time per episode (min over its rules; None = miss) and the mean with misses at the hold, with and
    without BC. Descriptive and in-sample (no selection); P4 is where a sensor is chosen, leave-one-episode-out."""
    out = []
    for regime in FAULT_REGIMES:
        for rate in RATES:
            eps = sorted((e for e in eps_of(G, regime, rate) if e["g3n"]), key=lambda e: e["block"])
            per = {}
            for i, e in enumerate(eps):
                for f in e["fires"]:
                    if f["family"] == "E" or not f["admissible"] or not f["counts"]:
                        continue
                    sid = "%s:%s:%s" % (f["ch"], f["svc"], f["tok"])
                    row = per.setdefault(sid, {"family": f["family"], "own": f["own"], "bc": [None] * len(eps),
                                               "noBC": [None] * len(eps)})
                    for key in ("bc", "noBC"):
                        if key == "noBC" and f["bc"]:
                            continue
                        if row[key][i] is None or f["ttd"] < row[key][i]:
                            row[key][i] = f["ttd"]
            holds = [e["holdSeconds"] for e in eps]
            for sid, row in sorted(per.items()):
                out.append({"regime": regime, "rate": rate, "sensor": sid, "family": row["family"], "own": row["own"],
                            "bc": summarise(row["bc"], holds), "noBC": summarise(row["noBC"], holds)})
    return out


def ledger_failed_ttd(ep):
    ts = [f["ttd"] for f in ep["fires"] if f["ch"] == "ledger" and f["rule"] == "failed" and f["admissible"]]
    return min(ts) if ts else None


def predictions(G, ctx):
    out = {}
    # ---- P1: search-pause, per episode, E vs schedule wait + client timeout
    p1 = []
    for e in [x for x in G["episodes"] if x["regime"] == "search-pause-effect"]:
        c = e["_c"]
        timeout = float(c["timing"].get("requestTimeoutSeconds", P2_DOBS_S))
        exp = p1_expected(c["ledger"], e["onset"]["mono"], timeout)
        obs = col_hit(e, "E", True)
        if obs == "absent":
            p1.append({"rate": e["rate"], "block": e["block"], "cell": e["cell"], "expected": exp, "observed": None,
                       "deviation": None, "ok": None})
            continue
        p1.append({"rate": e["rate"], "block": e["block"], "cell": e["cell"], "expected": exp, "observed": obs,
                   "deviation": (obs - exp) if (obs is not None and exp is not None) else None, "ok": p1_ok(obs, exp)})
    ev = [x for x in p1 if x["ok"] is not None]
    out["P1"] = {"perEpisode": p1, "k": sum(1 for x in ev if x["ok"]), "n": len(ev), "notEvaluable": len(p1) - len(ev),
                 "perRate": {"%g" % r: [sum(1 for x in ev if x["rate"] == r and x["ok"]), sum(1 for x in ev if x["rate"] == r)]
                             for r in RATES},
                 "holds": (all(x["ok"] for x in ev) if ev and len(ev) == len(p1) else None)}
    # ---- P2: search-pause, per rate, failed requests before the ledger's first `failed` catch
    p2 = {}
    for rate in RATES:
        eps = [e for e in eps_of(G, "search-pause-effect", rate) if e["g3n"]]
        counts, det = [], []
        for e in eps:
            t = ledger_failed_ttd(e)
            a = e["onset"]["mono"]
            counts.append(failed_before(e["_c"]["ledger"], a, a + (t if t is not None else e["holdSeconds"])))
            det.append(t is not None)
        v = p2_verdict(counts, rate)
        v["failedRuleDetected"] = det
        p2["%g" % rate] = v if eps else None
    out["P2"] = p2
    # ---- P3: declared testable set
    p3 = []
    for regime, fam, own in P3_TESTABLE:
        col = fam + (":own" if own else "")
        cad = P3_CADENCE_S[fam]
        sides = {}
        for rate in P3_RATES:
            eps = sorted(eps_of(G, regime, rate), key=lambda e: e["block"])
            for key, bc in (("%g" % rate, False), ("%g:withBC" % rate, True)):
                hits = [(col_fire(e, col, bc), e) for e in eps]
                hits = [(h, e) for h, e in hits if h != "absent"]
                if not hits:
                    sides[key] = None
                    continue
                sides[key] = summarise([h["ttd"] if h else None for h, _ in hits], [e["holdSeconds"] for _, e in hits])
                # review M1 (i): how far the probe rule moved each episode's first catch (s; None = miss)
                sides[key]["movedBy"] = [h["movedBy"] if h else None for h, _ in hits]
                sides[key]["duringWindowSeconds"] = [e["duringWindowSeconds"] for _, e in hits]
        hi, lo = sides["10"], sides["0.05"]
        if hi is None or lo is None or hi["n"] != EPISODES or lo["n"] != EPISODES:
            state, holds = "not evaluable (n %s at 10/s, %s at 0.05/s)" % (hi["n"] if hi else 0, lo["n"] if lo else 0), None
        elif hi["k"] == 0:
            state, holds = "untestable (no catch at 10/s)", None
        elif hi["penalisedMeanTtd"] is None or lo["penalisedMeanTtd"] is None:
            state, holds = "not evaluable (no mean)", None
        else:
            holds = lo["penalisedMeanTtd"] <= hi["penalisedMeanTtd"] + cad + 1e-12
            state = "holds" if holds else "fails"
        p3.append({"regime": regime, "column": col, "cadence": cad, "sides": sides, "state": state, "holds": holds})
    out["P3"] = p3
    # ---- P4a / P4b
    out["P4"] = {}
    for scope, own in (("P4a", False), ("P4b", True)):
        rows = {}
        for regime in FAULT_REGIMES:
            per = {}
            for rate in RATES:
                eps = sorted((e for e in eps_of(G, regime, rate) if e["g3n"]), key=lambda e: e["block"])
                if not eps:
                    per[rate] = None
                    continue
                views = {}
                for bc in (False, True):
                    cands = defaultdict(lambda n=len(eps): [None] * n)
                    moved = defaultdict(lambda n=len(eps): [None] * n)
                    for i, e in enumerate(eps):
                        for f in e["fires"]:
                            if f["family"] == "E" or not f["admissible"] or not f["counts"] or f["own"] != own:
                                continue
                            if not bc and f["bc"]:
                                continue
                            s = "%s:%s:%s" % (f["ch"], f["svc"], f["tok"])
                            if cands[s][i] is None or f["ttd"] < cands[s][i]:
                                cands[s][i], moved[s][i] = f["ttd"], f["movedBy"]
                    folds, wins = loeo(dict(cands), [col_hit(e, "E", True) for e in eps], [e["holdSeconds"] for e in eps])
                    for fo in folds:     # review M1 (i): the chosen sensor's move in the held-out episode
                        fo["movedBy"] = moved[fo["sensor"]][fo["heldOut"]] if fo["sensor"] else None
                        fo["duringWindowSeconds"] = eps[fo["heldOut"]]["duringWindowSeconds"]
                    views["noBC" if not bc else "withBC"] = {
                        "n": len(eps), "wins": wins, "holds": p4_holds(wins, len(eps)), "folds": folds,
                        "candidates": len(cands),
                        "candidatePoolFalseAlarms": false_alarms(G, ctx, regime, rate, None, own, bc)}
                per[rate] = dict(views["noBC"], withBC=views["withBC"])
            rows[regime] = {"perRate": {"%g" % r: v for r, v in per.items()}, "highestRate": highest_rate(per),
                            "highestRateWithBC": highest_rate({r: (v["withBC"] if v else None) for r, v in per.items()})}
        out["P4"][scope] = rows
    return out


def verdict_key(pred):
    """The values compared across the grid (reference verdict vs each grid point)."""
    v = {"P1": pred["P1"]["holds"]}
    for r, x in pred["P2"].items():
        v["P2@%s" % r] = None if x is None else x["holds"]
    for x in pred["P3"]:
        v["P3 %s %s" % (x["regime"], x["column"])] = x["state"]
    for scope, rows in pred["P4"].items():
        for regime, x in rows.items():
            v["%s %s" % (scope, regime)] = x["highestRate"]
    return v


# =========================================================================== whole campaign

def summaries(G, ctx, caller_span):
    set_caller_span(G, caller_span)
    return {"primary": primary(G, ctx), "secondary": secondary(G), "predictions": predictions(G, ctx)}


def p4_rate_holds(pred):
    """(scope, regime, rate) -> holds, for the probe-rule comparison."""
    return {(scope, regime, r): (v["holds"] if v else None)
            for scope, rows in pred["P4"].items() for regime, x in rows.items() for r, v in x["perRate"].items()}


def decided_by_probe_rule(prim, none):
    """Review M1 (iv): a verdict that differs between the primary probe variant and "none" is decided by the probe
    rule. Keys as verdict_key, plus P4 per (scope, regime, rate)."""
    a, b = verdict_key(prim), verdict_key(none)
    out = {k: {"primary": a[k], "withoutProbeRule": b.get(k)} for k in a if a[k] != b.get(k)}
    ra, rb = p4_rate_holds(prim), p4_rate_holds(none)
    for key in ra:
        if ra[key] != rb.get(key):
            out["%s %s r%s" % key] = {"primary": ra[key], "withoutProbeRule": rb.get(key)}
    return out


def run(campaign, grid=None, variants=True):
    root, dirs = find_cells(campaign)
    cells = [load_or_invalid(d) for d in dirs]
    ctx = make_ctx([c for c in cells if c["valid"]])
    grid = grid or [(k, f) for k in GRID_K for f in GRID_FLOOR_MS]
    if REF not in grid:
        grid = [REF] + list(grid)
    res = {}
    for k, f in grid:          # the grid runs on the primary probe and caller-span variants
        G = analyse(cells, ctx, k, f, PRIMARY_PROBE)
        res[(k, f)] = dict(summaries(G, ctx, PRIMARY_CALLER_SPAN), G=G)
    ref = res[REF]
    var = {}
    if variants:               # every variant side by side at the reference point
        for pv in PROBE_VARIANTS:
            G = ref["G"] if pv == PRIMARY_PROBE else analyse(cells, ctx, REF[0], REF[1], pv)
            for cs in CALLER_SPAN_VARIANTS:
                var[(pv, cs)] = summaries(G, ctx, cs)
        set_caller_span(ref["G"], PRIMARY_CALLER_SPAN)
    ref["perSensor"] = per_sensor(ref["G"])
    ref_v = verdict_key(ref["predictions"])
    agree = {key: [sum(1 for g in res.values() if verdict_key(g["predictions"]).get(key) == val), len(res)]
             for key, val in ref_v.items()}
    decided = (decided_by_probe_rule(ref["predictions"], var[("none", PRIMARY_CALLER_SPAN)]["predictions"])
               if variants and PRIMARY_PROBE != "none" else None)
    found = Counter((c["regime"], c["rate"]) for c in cells)
    valid = Counter((c["regime"], c["rate"]) for c in cells if c["valid"])
    prov = {"harnessCommit": harness_commit(root),
            "planSha256": sorted({c["planSha256"] for c in cells if c.get("planSha256")}),
            "admissionSha256": sorted({c["admissionSha256"] for c in cells if c.get("admissionSha256")}),
            "input": input_digest(root, dirs)}
    return {"campaign": root, "cells": cells, "ctx": ctx, "grid": res, "reference": ref, "agreement": agree,
            "referenceVerdicts": ref_v, "found": found, "valid": valid, "variants": var, "decidedByProbeRule": decided,
            "provenance": prov}


def _git(*args):
    try:
        return subprocess.run(["git", "-C", str(REPO)] + list(args), capture_output=True, text=True).stdout.strip()
    except OSError:
        return "?"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def episode_detail(G):
    out = []
    for e in G["episodes"]:
        c = e["_c"]
        d = {k: v for k, v in e.items() if k not in ("fires", "_c")}
        d["probeWindows"] = c["probeWindows"]
        d["readStats"] = c["readStats"]
        d["fires"] = [[f["family"], "%s:%s:%s" % (f["ch"], f["svc"], f["tok"]), f["rule"], round(f["ttd"], 4),
                       round(f["ttdLo"], 4) if "ttdLo" in f else None, f["dir"], "%d/%d" % (f["g3k"], f["g3n"]),
                       f["admissible"], f["own"], f["onPath"], f["counts"], f["bc:kind"], f["bc:content"],
                       round(f["movedBy"], 4)]
                      for f in sorted(e["fires"], key=lambda f: f["ttd"]) if f["admissible"] or f["ch"] == "ledger"]
        d["firesInadmissible"] = sum(1 for f in e["fires"] if not f["admissible"])
        d["columns"] = {col + ("" if bc else ":noBC"): (lambda h: h if h != "absent" else None)(col_hit(e, col, bc))
                        for col in COLUMNS for bc in (True, False)}
        out.append(d)
    return out


def caller_log_templates(G):
    out = Counter()
    text = {}
    for e in G["episodes"]:
        for f in e["fires"]:
            if "BC-caller-log" in f["bc"] and f["admissible"]:
                key = "%s r%g log:%s:%s (target %s)" % (e["regime"], e["rate"], f["svc"], f["tok"], e["target"])
                out[key] += 1
                text[key] = e["_c"]["logText"].get((f["svc"], f["tok"]), ("?", "?"))
    return {k: {"episodes": n, "level": text[k][0], "message": text[k][1]} for k, n in sorted(out.items())}


def resolution(R):
    out = {}
    for rate in RATES:
        cells = [c for c in R["cells"] if c["valid"] and c["target"] and c["rate"] == rate]
        if cells:
            ws, counts = dt.whole_second_logs(cells)
            r = dt.resolution({"cells": cells, "entry": ENTRY, "wholeSecondLogs": ws, "logStampsIntegral": counts})
            out["%g" % rate] = r
    return out


DEFAULTS = [
    "Onset = fault-receipt startedMonotonic (dbebcbb, pre-command bound); the scheduled onset (barrier + timing."
    "faultOnsetSeconds) is reported with its lag. P1's wait and P2's count use the same onset. No-fault pseudo window: "
    "the contract's scoredWindowSeconds on the barrier.",
    "K x floor grid: the floor applies to span and ledger latency only; metric floors stay per resource. Reference "
    "K = 4, floor 1 ms; predictions report the reference verdict and k/9 grid points agreeing.",
    "G3 per rate on one pseudo window per no-fault cell (n = 4: only k = 0 is admissible; uncertified). False alarms "
    "per rate, leave-one-cell-out, k/n beside every score; P4 rows carry the candidate pool's false alarms.",
    "Probe windows: samples observed inside are dropped from the pre-window too; for `absent` they still count as "
    "liveness (else the drop itself fabricates silence); a catch inside moves to the window end, and past the hold end "
    "it is no catch. A metric sample stamped after a window whose interval overlaps it is kept. Under a pause the "
    "during-probe can hang up to its 5 s timeout (compose_pause.route_available), so every sensor catch is pushed to "
    "at least its end while the ledger is untouched: a structural handicap of sensors, not a finding. "
    "Spans: whole traces with an untokenised frontend root are dropped; traces without a frontend root are kept.",
    "Log time = Docker receive stamp of the record's first line (with --timestamps); app whole-second stamp at s + 1 "
    "only for a cell whose log stamps are all integral, decided per cell (review m1).",
    "Probe variants (review M1): declared (primary until PRIMARY_PROBE changes) / scope (window rule only for logs and "
    "metrics of frontend and the target; spans by token only) / none (no window rule, token rule kept), all at the "
    "reference point; the grid runs on the primary. A P3/P4 verdict that differs from `none` is 'decided by the probe "
    "rule'. Caller-span variants: kind (dbebcbb, stopping faults; primary until PRIMARY_CALLER_SPAN changes) / content "
    "(every fault class).",
    "Cells not scored, listed with the reason: no cell-terminal.json, candidateCellValid not true, unknown regime, "
    "receipt presence not matching the regime, receipt target not the regime's, or a parse error (review B1, M3).",
    "Ledger baselines: each cell's own pre-window per request (dbebcbb); at 0.05/s a route has ~3 pre-onset requests, "
    "so latency rules often have no baseline (`failed` needs none). The pooled no-fault baseline of brief A B9 was not "
    "adopted (not in the declaration).",
    "P1 uses E (min over admissible failed/spike/run3/median) at the reference point; a ledger miss fails the episode. "
    "P1 holds iff every search-pause episode is within ±0.5 s.",
    "P2 uses the ledger's first admissible `failed` catch; a miss counts failed requests over the whole hold; inclusive "
    "`<=`. Fewer than 4 episodes at a rate: `—`.",
    "P3: family-level (first admissible catch of the family), without BC, mean over 4 episodes with misses at the hold; "
    "only the declared testable set; the probe move of each episode's first catch and the during-window length are "
    "reported beside both sides.",
    "P4: sensor = channel:service:token, its time = min over its admissible, path-scored rules; selection by the "
    "lowest mean over the 3 training episodes (miss = hold), ties by name; a sensor missing every training episode is "
    "not selectable; win = strictly lower than the ledger (E with BC) in the held-out episode. P4b's primary is also "
    "without BC (BC-idle-cpu of the paused target is the fault itself); with BC is beside. Fewer than 4 evaluable "
    "episodes at a (class, rate): `—`, never 'none' (review m3).",
    "BC-caller-log by content: warn/error/other template, rule appear, any non-target service, message naming the "
    "target's service name or a gRPC method of its spans (whole words, >= 4 letters). Other flags as dbebcbb; the "
    "caller-span flag in two variants (see above).",
    "Secondary: counted by scheduled time in [onset, onset + time to detection]; sensors without BC, the ledger with "
    "its catches; a miss counts the hold.",
    "Resolution: observation time = span end, request end, log Docker receive stamp, metric sample stamp (dbebcbb). "
    "Hotel's Jaeger reporter flushes every 1 s, so span-vs-ledger differences under 1 s are not resolvable; docker "
    "stats and the cgroup sampler resolve no better than their measured cadence (printed above).",
    "Not computed: CELF / enumerated placements, D3 probabilistic detection, D4 max-min, D5 labels (exploratory in [D]); "
    "the 15 s re-censored horizon; slowed-request impact; maximum in flight per cell.",
]

HARNESS_GAPS = [
    "Token on non-root spans: only the frontend root span carries `obsplacement.opaque_token` (witness patch), so "
    "probe exclusion is per trace and needs the root retained; a trace without a frontend root cannot be attributed "
    "(`—`, kept). Source: traces-normalized.json / jaeger-raw-remainder.json.",
    "Recovery polls are not stamped one by one (compose_pause.wait_recovered uses route_available, not timed_probe), "
    "so the whole [revertingMonotonic, readyAtMonotonic] is excluded. Source: fault-receipt.json.",
    "No per-sample interval start for docker stats / cgroup rates: probe exclusion is by stamp only. Source: cpu.json, "
    "system-samples.json.",
]


def rr_key(regime, rate):
    return "%s r%s" % (regime, "?" if rate is None else "%g" % rate)


def build_json(R):
    ref = R["reference"]
    G = ref["G"]
    grid = {}
    for (k, f), g in R["grid"].items():
        grid["K%g_floor%gms" % (k, f)] = {"predictions": g["predictions"],
                                         "primaryMeans": [{"regime": r["regime"], "rate": r["rate"], "n": r["n"],
                                                           "means": {col: (None if v is None else
                                                                           [v["bc"]["penalisedMeanTtd"], v["noBC"]["penalisedMeanTtd"]])
                                                                     for col, v in r["columns"].items()}}
                                                          for r in g["primary"]]}
    out = {
        "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(), "declaration": DECLARATION,
        "scope": "instance (one SUT, one host, one campaign)",
        "script": "research/detection-time/sweep_analysis.py", "scriptSha256": _sha(__file__),
        "detectionTimeSha256": _sha(HERE / "detection_time.py"), "detectionTimeBaseCommit": BASE_COMMIT,
        "frameworkCommit": _git("rev-parse", "HEAD"), "python": platform.python_version(),
        "campaign": str(R["campaign"]),
        "constants": {"rates": RATES, "gridK": GRID_K, "gridFloorMs": GRID_FLOOR_MS, "reference": REF, "tau": dt.TAU,
                      "episodes": EPISODES, "p1TolS": P1_TOL_S, "p2": "1 + rate x %g s + %g" % (P2_DOBS_S, P2_EPS),
                      "p3CadenceS": P3_CADENCE_S, "p4Min": P4_MIN},
        "cells": {"found": {rr_key(*k): v for k, v in sorted(R["found"].items(), key=lambda kv: rr_key(*kv[0]))},
                  "valid": {rr_key(*k): v for k, v in sorted(R["valid"].items(), key=lambda kv: rr_key(*kv[0]))},
                  "notScored": [{"cell": c["cell"], "regime": c["regime"], "rate": c["rate"], "reason": c["reason"]}
                                for c in R["cells"] if not c["valid"]]},
        "provenance": R["provenance"],
        "primaryProbeVariant": PRIMARY_PROBE, "primaryCallerSpanVariant": PRIMARY_CALLER_SPAN,
        "variants": {"probe=%s callerSpan=%s" % k: {"predictions": v["predictions"]} for k, v in R["variants"].items()},
        "decidedByProbeRule": R["decidedByProbeRule"],
        "wholeSecondLogCells": [sum(1 for c in R["cells"] if c["valid"] and c["wsLogs"]),
                                sum(1 for c in R["cells"] if c["valid"])],
        "resolution": resolution(R),
        "reference": {"primary": ref["primary"], "secondary": ref["secondary"], "predictions": ref["predictions"],
                      "perSensor": ref["perSensor"],
                      "episodes": episode_detail(G), "callerLogTemplates": caller_log_templates(G)},
        "gridAgreement": {k: {"reference": R["referenceVerdicts"][k], "agree": v} for k, v in R["agreement"].items()},
        "grid": grid, "defaults": DEFAULTS, "harnessGaps": HARNESS_GAPS,
    }
    return dt.strip(out)


# =========================================================================== rendering

def f2(x):
    return DASH if x is None else "%.2f" % x


def fcol(v, key="bc"):
    if v is None:
        return DASH if ABSENT_DASH else "0"
    s = v[key]
    out = "%d/%d" % (s["k"], s["n"])
    if s["k"]:
        out += " · " + dt.fmt_t(s["ttd"])
    return out + " · **%s**" % f2(s["penalisedMeanTtd"])


def ffa(v, key="bc"):
    if v is None:
        return DASH if ABSENT_DASH else "0"
    fa = v[key]["falseAlarms"]
    if not fa["n"]:
        return DASH
    s = "%d/%d" % (fa["k"], fa["n"])
    if fa["k"]:
        s += " (%.1f s)" % fa["timeToFirstFalseAlarm"]["median"]
    return s


def short(regime):
    return regime.replace("-effect", "")


def probe_decided(dec, key, text):
    """Review M1 (iv): a verdict that the probe rule decides is labelled as such, with both values."""
    if key not in dec:
        return text
    return "decided by the probe rule (primary: %s; without it: %s)" % (dec[key]["primary"], dec[key]["withoutProbeRule"])


def render(R, J):
    ref = R["reference"]
    pred = ref["predictions"]
    agr = R["agreement"]
    L = []
    w = L.append
    w("# Traffic sweep, Hotel: time to detection per rate (%s)" % Path(str(R["campaign"])).name)
    w("")
    w("**Scope: instance** (one SUT, one host, one campaign). Analysis: `%s` (sha256 `%s`) on `detection_time.py` "
      "(sha256 `%s`, base commit %s), HEAD `%s`, Python %s. Binding: %s. Every count carries its denominator; `—` = "
      "absent or not evaluable, never 0." % (J["script"], J["scriptSha256"][:16], J["detectionTimeSha256"][:16],
                                             BASE_COMMIT, J["frameworkCommit"][:12], J["python"], DECLARATION))
    w("")
    w("## What was read")
    w("")
    w("| class | " + " | ".join("r%g valid/found" % r for r in RATES) + " |")
    w("|---|" + "---|" * len(RATES))
    for regime in (NOFAULT,) + FAULT_REGIMES:
        w("| %s | %s |" % (short(regime), " | ".join(
            ("%d/%d" % (R["valid"][(regime, r)], R["found"][(regime, r)])) if R["found"][(regime, r)] else DASH
            for r in RATES)))
    w("")
    inv = J["cells"]["notScored"]
    w("Cells not scored: %s." % ("; ".join("`%s` (%s)" % (x["cell"], x["reason"]) for x in inv) if inv else "none"))
    pv = R["provenance"]
    w("")
    w("Provenance: harness commit %s; plan sha256 %s; admission sha256 %s; input digest %s over %d files (sorted "
      "relative path and size of every file read)." % (
          "`%s`" % pv["harnessCommit"] if pv["harnessCommit"] else DASH,
          ", ".join("`%s`" % x[:16] for x in pv["planSha256"]) or DASH,
          ", ".join("`%s`" % x[:16] for x in pv["admissionSha256"]) or DASH,
          "`%s`" % pv["input"]["sha256"][:16], pv["input"]["files"]))
    eps = ref["G"]["episodes"]
    lag = [e["onsetLagSeconds"] for e in eps]
    hold = [e["holdSeconds"] for e in eps]
    pw = [p for e in eps for p in e["_c"]["probeWindows"]]
    drop = Counter()
    for e in eps:
        drop.update(e["droppedInProbeWindows"])
    st = Counter()
    for c in R["cells"]:
        st.update(c["readStats"])
    w("")
    w("Fault episodes: %d. Onset = receipt startedMonotonic; its lag after the scheduled onset: %s s; hold %s s. Probe "
      "windows: %d (%s), total %s s; sensor samples dropped inside them (reference point): %s. Moved catches past the "
      "hold end: %d. Spans: %d traces / %d spans dropped for no token, %d kept. Log lines with / without a Docker "
      "stamp: %d / %d; cells timed by the whole-second rule: %d/%d." % (
          len(eps), dt.fmt_t(dt.dist(lag)), dt.fmt_t(dt.dist(hold)), len(pw),
          ", ".join("%s %d" % kv for kv in sorted(Counter(p["kind"] for p in pw).items())) or DASH,
          f2(sum(p["seconds"] for p in pw)) if pw else DASH,
          ", ".join("%s %d" % kv for kv in sorted(drop.items())) or "0",
          sum(len(e["movedPastHoldEnd"]) for e in eps), st["tracesExcludedNoToken"], st["spansExcludedNoToken"],
          st["spansKept"], st["logLinesWithDockerStamp"], st["logLinesWithoutDockerStamp"],
          J["wholeSecondLogCells"][0], J["wholeSecondLogCells"][1]))
    w("")
    w("No-fault windows per rate (G3 and false-alarm denominator; 0 = every fault episode at that rate is `—`): " +
      ", ".join("r%g %d" % (r, len(ref["G"]["nofault"].get(g3key(r), []))) for r in RATES) + ".")
    w("")
    w("Metric cadence measured (median gap, entry service): " + "; ".join(
        "r%s %s" % (r, ", ".join("%s %.2f s" % kv for kv in sorted(v["metricGapMedianSeconds"].items())) or DASH)
        for r, v in J["resolution"].items()) + ".")
    w("")
    dec = R["decidedByProbeRule"] or {}
    w("## Predictions (reference K = 4, floor 1 ms; `grid` = grid points of 9 giving the same verdict)")
    w("")
    w("Probe variant **%s**, caller-span variant **%s** (the primaries; every variant is in the table below). A verdict "
      "that differs when the probe-window rule is switched off is printed **decided by the probe rule**. P4 needs 4 "
      "evaluable episodes per (class, rate); fewer is `—`, never 'none'." % (PRIMARY_PROBE, PRIMARY_CALLER_SPAN))
    w("")
    p1 = pred["P1"]
    w("- **P1** (search-pause, |E − (schedule wait + timeout)| ≤ 0.5 s per episode): %d/%d episodes; per rate %s. "
      "Not evaluable: %d. Verdict: %s (grid %s)." % (p1["k"], p1["n"], ", ".join(("r%s %d/%d" % (r, a, b)) if b else ("r%s %s" % (r, DASH))
                                                                for r, (a, b) in p1["perRate"].items()),
                                  p1["notEvaluable"],
                                  {True: "holds", False: "fails: harness or onset defect to explain", None: DASH}[p1["holds"]],
                                  "%d/%d" % tuple(agr["P1"])))
    for r, v in pred["P2"].items():
        if v is None:
            w("- **P2** r%s: %s (no episodes)." % (r, DASH))
            continue
        w("- **P2** r%s (failed before the ledger's first `failed` catch ≤ %.2f): %d/%d episodes, counts %s; verdict %s "
          "(grid %d/%d)." % (r, v["threshold"], v["k"], v["n"], v["perEpisode"],
                             {True: "holds", False: "fails", None: DASH + " (n < 4)"}[v["holds"]],
                             agr["P2@%s" % r][0], agr["P2@%s" % r][1]))
    for x in pred["P3"]:
        s10, s005 = x["sides"]["10"], x["sides"]["0.05"]
        w("- **P3** %s %s (without BC; 0.05/s ≤ 10/s + %.0f s): 10/s %s, 0.05/s %s: **%s** (grid %d/%d)." % (
            short(x["regime"]), x["column"], x["cadence"],
            DASH if not s10 else "%d/%d · mean %s" % (s10["k"], s10["n"], f2(s10["penalisedMeanTtd"])),
            DASH if not s005 else "%d/%d · mean %s" % (s005["k"], s005["n"], f2(s005["penalisedMeanTtd"])),
            probe_decided(dec, "P3 %s %s" % (x["regime"], x["column"]), x["state"]),
            agr["P3 %s %s" % (x["regime"], x["column"])][0], agr["P3 %s %s" % (x["regime"], x["column"])][1]))
        for side in ("10", "0.05"):
            sd = x["sides"][side]
            if sd:
                w("  - P3 %s r%s moves of the first catch (s; `—` = miss): %s; during-probe windows (s): %s." % (
                    short(x["regime"]), side, ", ".join(f2(m) for m in sd["movedBy"]),
                    ", ".join(f2(m) for m in sd["duringWindowSeconds"])))
    for scope, rows in pred["P4"].items():
        label = "outside the target, without BC" if scope == "P4a" else "the target's own sensors, without BC"
        for regime, x in rows.items():
            cells = []
            for r in RATES:
                v = x["perRate"]["%g" % r]
                txt = DASH if v is None else "%d/%d (BC incl. %d/%d)" % (v["wins"], v["n"], v["withBC"]["wins"],
                                                                          v["withBC"]["n"])
                key = "%s %s r%g" % (scope, regime, r)
                if key in dec:
                    txt += " **decided by the probe rule** (without it: %s)" % {
                        True: "holds", False: "does not hold", None: DASH}[dec[key]["withoutProbeRule"]]
                cells.append("r%g %s" % (r, txt))
            w("- **%s** %s (%s; LOEO wins over paired episodes): %s; highest rate: **%s** (with BC: %s; grid %d/%d)." % (
                scope, short(regime), label, ", ".join(cells),
                probe_decided(dec, "%s %s" % (scope, regime), x["highestRate"]), x["highestRateWithBC"],
                agr["%s %s" % (scope, regime)][0], agr["%s %s" % (scope, regime)][1]))
    w("")
    if R["variants"]:
        keys = list(verdict_key(pred))
        cols = [(pv, cs) for pv in PROBE_VARIANTS for cs in CALLER_SPAN_VARIANTS]
        w("**Variants side by side** (reference point; primary = probe %s, caller-span %s):" % (
            PRIMARY_PROBE, PRIMARY_CALLER_SPAN))
        w("")
        w("| verdict | " + " | ".join("probe %s / span %s%s" % (pv, cs, " (primary)" if (pv, cs) == (
            PRIMARY_PROBE, PRIMARY_CALLER_SPAN) else "") for pv, cs in cols) + " |")
        w("|---|" + "---|" * len(cols))
        for key in keys:
            vals = [verdict_key(R["variants"][c]["predictions"]).get(key) for c in cols]
            w("| %s | %s |" % (key, " | ".join(DASH if v is None else str(v) for v in vals)))
    w("")
    w("## 0. Primary outcome: time to detection, misses charged at the hold end, mean over all episodes")
    w("")
    w("Seconds from the onset. Cell: detected k/n · median [min–max] over detected · **mean over all n** (with BC catches); "
      "then the same without BC; FA = false alarms k/n no-fault windows of the same rate (leave-one-cell-out, the "
      "class's filters), median time to the first. The ledger E keeps its catches in both views.")
    w("")
    for own in (False, True):
        cols = [c for c in COLUMNS if c.endswith(":own") == own and c != "E:own"]
        if own:
            w("**Own sensors of the target (G2, never in a P4a set)**")
            w("")
        w("| class | rate | n | " + " | ".join("%s | %s no BC | FA %s" % (c, c, c) for c in cols) + " |")
        w("|---|---|---|" + "---|---|---|" * len(cols))
        for row in ref["primary"]:
            cells = []
            for c in cols:
                v = row["columns"].get(c)
                cells += [fcol(v, "bc"), fcol(v, "noBC") if c != "E" else "(= E)", ffa(v, "bc")]
            w("| %s | %g | %d | %s |" % (short(row["regime"]), row["rate"], row["n"], " | ".join(cells)))
        w("")
    w("## 1. Secondary: failed requests scheduled before the first catch")
    w("")
    w("Per episode, failed requests whose scheduled time lies in [onset, onset + time to detection] (a miss counts the "
      "whole hold): median [min–max] over n, (detected/n). Sensors without BC; the ledger with its catches.")
    w("")
    cols = [c for c in COLUMNS if c != "E:own"]
    w("| class | rate | n | " + " | ".join(cols) + " |")
    w("|---|---|---|" + "---|" * len(cols))
    for row in ref["secondary"]:
        cells = []
        for c in cols:
            v = row["columns"].get(c)
            cells.append(DASH if v is None else "%s (%d/%d)" % (dt.fmt_t(v["failedBefore"]).replace(".00", ""),
                                                                v["detected"], v["n"]))
        w("| %s | %g | %d | %s |" % (short(row["regime"]), row["rate"], row["n"], " | ".join(cells)))
    w("")
    w("## 2. Prediction detail")
    w("")
    w("P1 per episode (rate, block: expected · observed · deviation, s): " + "; ".join(
        "r%g b%s %s · %s · %s%s" % (x["rate"], x["block"], f2(x["expected"]), f2(x["observed"]), f2(x["deviation"]),
                                    "" if x["ok"] else " ✗") for x in p1["perEpisode"]) + "." if p1["perEpisode"] else
      "P1: no search-pause episode (`—`).")
    w("")
    for scope, rows in pred["P4"].items():
        for regime, x in rows.items():
            for r in RATES:
                v = x["perRate"]["%g" % r]
                if v is None:
                    continue
                fa = v["candidatePoolFalseAlarms"]
                w("- %s %s r%g: candidates %d; folds %s; candidate pool false alarms %s." % (
                    scope, short(regime), r, v["candidates"], "; ".join(
                        "ep%d %s %s (moved %s, during window %s) vs E %s%s" % (
                            f["heldOut"] + 1, f["sensor"] or DASH, f2(f["sensorTtd"]), f2(f["movedBy"]),
                            f2(f["duringWindowSeconds"]), f2(f["ledgerTtd"]), " win" if f["win"] else "")
                        for f in v["folds"]),
                    ("%d/%d" % (fa["k"], fa["n"])) if fa["n"] else DASH))
    w("")
    w("During-probe window per episode (s), the span in which every sensor catch is held back under the declared "
      "rule:")
    w("")
    for regime in FAULT_REGIMES:
        for r in RATES:
            es = sorted(eps_of(ref["G"], regime, r), key=lambda e: e["block"])
            if es:
                w("- %s r%g: %s" % (short(regime), r, ", ".join("b%s %s" % (e["block"], f2(e["duringWindowSeconds"]))
                                                               for e in es)))
    w("")
    w("## 3. BC-caller-log by content: the templates it flags")
    w("")
    tpl = J["reference"]["callerLogTemplates"]
    for k, v in tpl.items():
        w("- %s × %d episodes: %s `%s`" % (k, v["episodes"], v["level"], str(v["message"]).replace("|", "/")))
    if not tpl:
        w("- none flagged.")
    w("")
    w("## Engineering defaults (recorded) and declared limits")
    w("")
    for line in DEFAULTS:
        w("- " + line)
    w("")
    w("## Not emitted by the harness")
    w("")
    for line in HARNESS_GAPS:
        w("- " + line)
    w("")
    return "\n".join(L)


def write_new(path, text):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", help="fetched campaign directory (holds runs/, or one child that does)")
    ap.add_argument("--out", required=True, help="NEW output directory; refused if it exists")
    ap.add_argument("--reference-only", action="store_true",
                    help="only K = 4, floor 1 ms (a smoke run; the declared analysis is the full grid)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    R = run(Path(a.campaign), grid=[REF] if a.reference_only else None)
    J = build_json(R)
    out.mkdir(parents=True)
    write_new(out / "sweep_analysis.json", json.dumps(J, indent=1, sort_keys=True))
    write_new(out / "SWEEP_ANALYSIS.md", render(R, J))
    print("wrote", out / "sweep_analysis.json", out / "SWEEP_ANALYSIS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
