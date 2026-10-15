#!/usr/bin/env python3
"""Generic campaign gates P0, R1, R2, F1, G1, G2, G3, G4 over one normalised cell (protocol draft 3, section 4).

Spec: research/PROTOCOL_DRAFT_20261002.md section 4; keep/fold/drop of every per-SUT gate: research/protocol/GATES.md.
Lifted from research/visibility-map/traffic_gate.py:56-169 (need / g1 / g2 / entry_rule_can_fire / evaluate), with
G1 moved from completed starts to SCHEDULED opportunities and the per-cell gates P0, R1, R2, F1 added.

VENDORING. This file is copied byte-identically into each runtime module's `validation/` directory, where it runs as
`python3 -I` on CPython 3.9: standard library only, no package-relative import, no PEP 604 annotation, no f-string, no
dataclass. tests/test_protocol_gates.py enforces the 3.9 syntax floor and compares any vendored copy by sha256.

Every gate is a pure function of its arguments and returns a verdict record

    {"gate": str, "verdict": "pass" | "fail" | "—", "value": ..., "threshold": ..., "reason": str[, "detail": {...}]}

"—" means the gate could not be evaluated because an input is absent (unknown is not zero). A cell is valid only when
every BLOCKING gate that applies to it is "pass", so "—" blocks exactly like "fail". P0 and G4 are presence gates:
for them a missing record IS the failure, so they never return "—".

Normalised cell (all times in seconds on the cell's own clock; the measurement barrier is 0 where one exists):

    cell = {
      "cellId":   str,
      "kind":     "fault" | "nofault",
      "posture":  str,                                  # key into profile["channels"] and profile["emitters"]
      "valid":    True | False | None,                  # the harness's own cell verdict (None: not recorded)
      "plan": {
        "offered":         int,                         # opportunities the plan schedules
        "rate":            float,                       # declared opportunities per second
        "durationSeconds": float,                       # scheduled measurement length
        "window":          [a, b] | None,               # scheduled fault window; for a no-fault cell its pseudo
      },                                                #   window (same offsets), None for a cost-only cell
      "measurement": [m0, m1] | None,                   # default [0, plan.durationSeconds]
      "ledgerKind":  "ledger" | "proxy" | None,         # "proxy": rows inferred (trace starts), not a ledger
      "ledger": [                                       # one row per scheduled opportunity, or None
        {"scheduled": float, "started": float | None, "ended": float | None,
         "status": "ok" | "failed" | "timeout" | "dropped" | "unknown"},
      ] | None,                                         #   dropped = scheduled but never dispatched
      "fault": {                                        # fault cells; None or absent for no-fault cells
        "scheduledOnset": float, "scheduledHold": float,
        "onsetCommandIssued": float, "onsetCommandReturned": float,      # stamps taken around the onset command
        "revertCommandIssued": float, "revertCommandReturned": float,
        "onsetSource": "pre-command" | "scheduled" | "probe" | "post-command",   # only pre-command passes F1
        "manifested": bool, "reverted": bool,
      },
      "channels": {channel: {"recordsAfterWarmup": int, "recordsInCell": int, "recordsTotal": int}},
      "readiness": {"servicesRunning": {service: bool}, "routeStatus": {route: int}, "ledgerRows": int,
                    "attempt": int},
      "baseState":  {"freshProject": bool, "volumesRemoved": bool},
      "provenance": {"namespaceEmpty": bool, "imageDigests": {service: str},
                     "postureProof": {"method": "connection-count" | "emitted-bytes",
                                      "observed": {service: number}}},
    }

Profile parameters (the generated system profile, research/system-profiles/; only these keys are read):

    profile = {"sut": str, "routes": [route], "rate": float, "services": [measured service],
               "channels": {posture: [channel collected]}, "emitters": {posture: [service expected to emit]}}

Gates (blocking unless marked):
  P0 provenance   namespace empty; every measured service's image pinned by sha256 digest; posture proved by observed
                  behaviour (connection count or emitted bytes, never by reading config): an observation for every
                  expected emitter, at least one of them nonzero when the posture expects any, and no emitter outside
                  the posture's expected set (the currencyservice leak class). A single silent expected emitter is
                  reported, not blocking (an off-path service can be idle under the workload).
  R1 ready        every measured service running; HTTP 200 on every declared route; ledger receiving rows; every
                  channel the posture collects delivered >= 1 record after warm-up. readiness_action(): restart once,
                  then stop and ask.
  R2 base state   fresh project and `down -v` before the cell.
  R2.recovery     NOT blocking, a carry-over record: last RECOVERY_WINDOW_S of a fault cell meets G2's bound and its
                  p50 is within RECOVERY_P50_RATIO of the pre-onset p50.
  F1 fault truth  manifested and reverted; onset stamp taken immediately before the command ("pre-command"); a
                  post-command probe (F-ADH-085) and a copied scheduled onset (which would make the schedule check
                  trivially true) both fail; onset within ONSET_TOLERANCE_S of schedule; hold bounded by the two
                  commands; revert inside the measurement. Fault cells only.
  G1 traffic      SCHEDULED opportunities in the scored window >= need(rate, seconds), AND >= G1_MIN_DISPATCHED of
                  them actually started inside the window. Not completed starts against the rate floor: a
                  concurrency-capped open-loop generator stalls its starts while the target is paused, which is the
                  fault's effect, not missing traffic. The dispatch condition is an addition to draft 3's wording
                  (review 2026-10-02): every harness ledger pre-allocates one row per plan slot (scheduled = start +
                  i / rate), so given G4 the scheduled count alone cannot fail and "no traffic in the window" (draft
                  3 section 5 challenge set) would pass. G1_MIN_DISPATCHED = 0 restores the literal wording; the
                  choice is the user's. Scored window: fault cell [onsetCommandIssued, revertCommandIssued]; no-fault
                  cell plan.window, else the whole measurement.
  G2 healthy      rows scheduled in [m0, onset): successes >= need(rate, onset - m0) and failure share (failed +
                  timeout + dropped over known outcomes) <= PRE_FAIL_MAX. Rows are attributed by schedule even when
                  they end after onset, so a pre-onset timeout cannot hide behind the onset (conservative: the few
                  requests in flight at onset count against G2). A cost-only cell is checked over its whole
                  measurement. Onset = onsetCommandIssued (a lower bound, F-ADH-085).
  G3 FA rate      population level, analysis side, NOT part of cell validity: k/n_eff per sensor family over no-fault
                  windows that pass G1 and G2 and in which a planted failure makes the entry rule fire; n_eff = 0 fails
                  (a rate that cannot fail is not a rate).
  G4 provenance   ledger present (not a proxy); fault timing present on fault cells; harness validity recorded;
                  offered == plan.offered (no literal); plan.offered == plan.rate x plan.durationSeconds (+-1); plan
                  rate == profile rate (a profile without a rate fails); >= SCOPE_MIN of ledger rows and of the records
                  of every channel the posture collects inside the cell (a collected channel without in-cell / total
                  counts fails: the ledger share alone is ~1.0 by construction).
Campaign stop (stop_decision / evaluate_campaign): stop and ask the user on the first invalid cell. A cell whose kind
is neither "fault" nor "nofault" is invalid ("kind"), so a typo cannot skip F1.

Engineering defaults (recorded here, not preregistered; changing FLOOR, PRE_FAIL_MAX or TAU is preregistration-class):
  FLOOR 0.5 and PRE_FAIL_MAX 0.05 and SCOPE_MIN 0.95   protocol draft 3 section 4 (traffic_gate.py's values)
  SCOPE_SLACK_S 5.0          records within +-5 s of the measurement count as inside (traffic_gate.py:157-159)
  TAU 0.05                   provisional (PLAN_FABLE part 2); draft 3 decision 5 sets it after the scope mapping
  ONSET_TOLERANCE_S 1.0      TeaStore's controller refuses an onset > 1 s late (performance_campaign.py:1938-1940)
  HOLD_TOLERANCE_S 1.0       hold may exceed schedule by the onset command's own duration plus this
  RECOVERY_WINDOW_S 60, RECOVERY_P50_RATIO 1.5   R2.recovery, non-blocking, so not preregistration-class
  G1_MIN_DISPATCHED 1        see G1; deviation from draft 3's wording, flagged for the user
  need() is max(1, ceil(FLOOR x rate x seconds)); rows are attributed to windows by their SCHEDULED stamp; a dropped
  row before onset is a failure; "unknown" outcomes are excluded from both counts and G2 is "—" when none are known.
  G3's n_eff counts only no-fault cells that are valid (every blocking gate and the harness verdict) and can fire.
  Not handled: a zero-rate (idle) rung fails G1, G2 and G4 by construction; such a rung needs its own gate set.

    /usr/bin/python3 -I -B protocol_gates.py --self-check             # one planted defect per gate; exit 1 on a miss
    /usr/bin/python3 -I -B protocol_gates.py --self-check --break G1  # shows the self-check catching a dead gate
"""
import copy
import math
import re
import statistics
import sys

FLOOR = 0.5
PRE_FAIL_MAX = 0.05
SCOPE_MIN = 0.95
SCOPE_SLACK_S = 5.0
TAU = 0.05
ONSET_TOLERANCE_S = 1.0
HOLD_TOLERANCE_S = 1.0
RECOVERY_WINDOW_S = 60.0
RECOVERY_P50_RATIO = 1.5
G1_MIN_DISPATCHED = 1

UNKNOWN = "—"
FAILURE_STATUSES = ("failed", "timeout", "dropped")
OBSERVED_PROOF_METHODS = ("connection-count", "emitted-bytes")
COMMAND_BOUNDED_ONSET = ("pre-command",)
FAULT_STAMPS = ("onsetCommandIssued", "onsetCommandReturned", "revertCommandIssued", "revertCommandReturned")
BLOCKING = ("P0", "R1", "R2", "F1", "G1", "G2", "G4")
KINDS = ("fault", "nofault")
DIGEST = re.compile(r"(^|@)sha256:[0-9a-f]{64}$")


# --------------------------------------------------------------------------- helpers

def verdict(gate, ok, value, threshold, reason, detail=None):
    """ok True/False/None -> pass/fail/—."""
    record = {"gate": gate, "verdict": UNKNOWN if ok is None else ("pass" if ok else "fail"),
              "value": value, "threshold": threshold, "reason": reason}
    if detail is not None:
        record["detail"] = detail
    return record


def combine(checks):
    """False if any check is False, else None if any is None, else True."""
    values = list(checks.values())
    if any(v is False for v in values):
        return False
    if any(v is None for v in values):
        return None
    return True


def need(rate, seconds, floor=FLOOR):
    """Minimum count for a window: max(1, ceil(floor x rate x seconds)); None when the rate is unknown."""
    if rate is None or seconds is None:
        return None
    return max(1, int(math.ceil(floor * float(rate) * max(float(seconds), 0.0) - 1e-9)))


def measurement(cell):
    m = cell.get("measurement")
    if m is not None:
        return float(m[0]), float(m[1])
    duration = (cell.get("plan") or {}).get("durationSeconds")
    return (0.0, float(duration)) if duration is not None else None


def fault_timing(cell):
    """The four command stamps, or None when any is missing."""
    fault = cell.get("fault") or {}
    if any(fault.get(k) is None for k in FAULT_STAMPS):
        return None
    return {k: float(fault[k]) for k in FAULT_STAMPS}


def scored_window(cell):
    """G1's window: the command-bounded hold for a fault cell, plan.window or the whole measurement otherwise."""
    if cell.get("kind") == "fault":
        t = fault_timing(cell)
        return None if t is None else (t["onsetCommandIssued"], t["revertCommandIssued"])
    w = (cell.get("plan") or {}).get("window")
    return (float(w[0]), float(w[1])) if w else measurement(cell)


def onset_of(cell):
    """G2's onset: the pre-command stamp for a fault cell, the pseudo onset for a no-fault cell, None for cost cells."""
    if cell.get("kind") == "fault":
        t = fault_timing(cell)
        return None if t is None else t["onsetCommandIssued"]
    w = (cell.get("plan") or {}).get("window")
    return float(w[0]) if w else None


def outcome_counts(rows):
    good = sum(1 for r in rows if r.get("status") == "ok")
    bad = sum(1 for r in rows if r.get("status") in FAILURE_STATUSES)
    return good, bad


def latencies(rows):
    return [r["ended"] - r["started"] for r in rows
            if r.get("status") == "ok" and r.get("started") is not None and r.get("ended") is not None]


def _scheduled_complete(rows):
    return all(r.get("scheduled") is not None for r in rows)


# --------------------------------------------------------------------------- per-cell gates

def p0(cell, profile):
    prov = cell.get("provenance") or {}
    services = list(profile.get("services") or [])
    digests = prov.get("imageDigests") or {}
    unpinned = sorted(s for s in services if not DIGEST.search(str(digests.get(s) or "")))
    proof = prov.get("postureProof") or {}
    expected = set((profile.get("emitters") or {}).get(cell.get("posture"), []) or [])
    observed = proof.get("observed")
    leaked = sorted(s for s, n in (observed or {}).items() if n and s not in expected)
    silent = sorted(s for s in expected if not (observed or {}).get(s))
    unobserved = sorted(s for s in expected if s not in (observed or {}))
    checks = {
        "namespaceEmpty": prov.get("namespaceEmpty") is True,
        "imagesByDigest": bool(services) and not unpinned,
        "postureProofObserved": proof.get("method") in OBSERVED_PROOF_METHODS and isinstance(observed, dict)
        and not unobserved and (not expected or any((observed or {}).get(s) for s in expected)),
        "noEmitterOutsidePosture": isinstance(observed, dict) and not leaked,
    }
    failed = sorted(k for k, v in checks.items() if not v)
    return verdict("P0", not failed, failed, "all of %s" % sorted(checks),
                   "provenance complete" if not failed else "provenance fails: %s" % ", ".join(failed),
                   {"unpinned": unpinned, "leakedEmitters": leaked, "silentExpectedEmitters": silent,
                    "unobservedExpectedEmitters": unobserved,
                    "proofMethod": proof.get("method")})


def r1(cell, profile):
    ready = cell.get("readiness")
    if not ready:
        return verdict("R1", None, None, None, "no readiness record")
    if not profile.get("services") or not profile.get("routes"):
        return verdict("R1", None, None, None, "profile declares no measured services or no routes")
    running = ready.get("servicesRunning") or {}
    status = ready.get("routeStatus") or {}
    chans = cell.get("channels") or {}
    collected = list((profile.get("channels") or {}).get(cell.get("posture"), []) or [])
    checks = {}
    for s in profile.get("services") or []:
        checks["running:" + s] = None if s not in running else running[s] is True
    for route in profile.get("routes") or []:
        checks["route200:" + route] = None if route not in status else status[route] == 200
    rows = ready.get("ledgerRows")
    checks["ledgerReceiving"] = None if rows is None else rows >= 1
    for ch in collected:
        n = (chans.get(ch) or {}).get("recordsAfterWarmup")
        checks["channel:" + ch] = None if n is None else n >= 1
    ok = combine(checks)
    bad = sorted(k for k, v in checks.items() if v is False)
    unknown = sorted(k for k, v in checks.items() if v is None)
    reason = ("ready" if ok else "not ready: %s" % ", ".join(bad) if ok is False
              else "readiness unknown: %s" % ", ".join(unknown))
    return verdict("R1", ok, bad or unknown, "every service running, 200 per route, ledger rows >= 1, "
                   "every collected channel >= 1 record after warm-up", reason,
                   {"attempt": ready.get("attempt"), "checks": checks})


def readiness_action(r1_record, attempt):
    """Restart once, then stop and ask (draft 3 section 4, R1)."""
    if r1_record["verdict"] == "pass":
        return "proceed"
    return "restart" if attempt <= 1 else "stop-and-ask"


def r2(cell):
    base = cell.get("baseState")
    if not base:
        return verdict("R2", None, None, None, "no base-state record")
    checks = {"freshProject": base.get("freshProject"), "volumesRemoved": base.get("volumesRemoved")}
    checks = {k: (None if v is None else v is True) for k, v in checks.items()}
    ok = combine(checks)
    return verdict("R2", ok, checks, "fresh project and down -v before the cell",
                   "fresh base state" if ok else "base state not fresh or unknown: %s" % checks)


def r2_recovery(cell):
    """Non-blocking carry-over record: the last RECOVERY_WINDOW_S of a fault cell against G2's bound and p50."""
    if cell.get("kind") != "fault":
        return verdict("R2.recovery", None, None, None, "not a fault cell")
    m, t, rows = measurement(cell), fault_timing(cell), cell.get("ledger")
    if m is None or t is None or rows is None or not _scheduled_complete(rows):
        return verdict("R2.recovery", None, None, None, "measurement, fault timing or scheduled ledger missing")
    a, b = m[1] - RECOVERY_WINDOW_S, m[1]
    if a < t["revertCommandReturned"]:
        return verdict("R2.recovery", None, None, None, "last %.0f s overlap the fault (revert returned at %.2f s)"
                       % (RECOVERY_WINDOW_S, t["revertCommandReturned"]))
    tail = [r for r in rows if a <= r["scheduled"] <= b]
    good, bad = outcome_counts(tail)
    onset = t["onsetCommandIssued"]
    pre = [r for r in rows if m[0] <= r["scheduled"] < onset and not (r.get("ended") is not None and r["ended"] > onset)]
    p_tail, p_pre = latencies(tail), latencies(pre)
    p50_tail = statistics.median(p_tail) if p_tail else None
    p50_pre = statistics.median(p_pre) if p_pre else None
    fl = need((cell.get("plan") or {}).get("rate"), RECOVERY_WINDOW_S)
    share = bad / float(good + bad) if good + bad else None
    checks = {"successes": None if fl is None else good >= fl,
              "failureShare": None if share is None else share <= PRE_FAIL_MAX,
              "p50": None if p50_tail is None or p50_pre is None else p50_tail <= RECOVERY_P50_RATIO * p50_pre}
    ok = combine(checks)
    return verdict("R2.recovery", ok, {"successes": good, "failureShare": share, "p50": p50_tail},
                   {"successes": fl, "failureShareMax": PRE_FAIL_MAX,
                    "p50Max": None if p50_pre is None else RECOVERY_P50_RATIO * p50_pre},
                   "recovered" if ok else "recovery %s: %s" % ("unknown" if ok is None else "fails", checks),
                   {"window": [a, b], "blocking": False})


def f1(cell):
    if cell.get("kind") != "fault":
        return verdict("F1", None, None, None, "not a fault cell (F1 does not apply)")
    fault, t, m = cell.get("fault") or {}, fault_timing(cell), measurement(cell)
    if t is None or m is None:
        return verdict("F1", False, None, None, "fault timing incomplete: needs %s" % ", ".join(FAULT_STAMPS))
    sched_on, sched_hold = fault.get("scheduledOnset"), fault.get("scheduledHold")
    hold = t["revertCommandIssued"] - t["onsetCommandIssued"]
    onset_cmd = t["onsetCommandReturned"] - t["onsetCommandIssued"]
    checks = {
        "manifested": fault.get("manifested") is True,
        "reverted": fault.get("reverted") is True,
        "onsetCommandBounded": fault.get("onsetSource") in COMMAND_BOUNDED_ONSET,
        "commandsOrdered": (t["onsetCommandIssued"] <= t["onsetCommandReturned"] <= t["revertCommandIssued"]
                            <= t["revertCommandReturned"]),
        "onsetOnSchedule": sched_on is not None and abs(t["onsetCommandIssued"] - float(sched_on)) <= ONSET_TOLERANCE_S,
        "holdBounded": sched_hold is not None and (float(sched_hold) - HOLD_TOLERANCE_S <= hold
                                                   <= float(sched_hold) + onset_cmd + HOLD_TOLERANCE_S),
        "insideMeasurement": m[0] <= t["onsetCommandIssued"] and t["revertCommandReturned"] <= m[1],
    }
    failed = sorted(k for k, v in checks.items() if not v)
    return verdict("F1", not failed, failed, "all of %s" % sorted(checks),
                   "fault truth holds" if not failed else "fault truth fails: %s" % ", ".join(failed),
                   {"holdSeconds": hold, "onsetCommandSeconds": onset_cmd, "onsetSource": fault.get("onsetSource")})


def g1(cell):
    rows, w = cell.get("ledger"), scored_window(cell)
    rate = (cell.get("plan") or {}).get("rate")
    if rows is None:
        return verdict("G1", None, None, None, "no ledger")
    if w is None:
        return verdict("G1", None, None, None, "no scored window (fault timing missing)")
    if not _scheduled_complete(rows):
        return verdict("G1", None, None, None, "ledger rows lack scheduled stamps")
    a, b = w
    n = sum(1 for r in rows if a <= r["scheduled"] <= b)
    started = sum(1 for r in rows if r.get("started") is not None and a <= r["started"] <= b)
    fl = need(rate, b - a)
    if fl is None:
        return verdict("G1", None, n, None, "plan rate unknown")
    ok = n >= fl and started >= G1_MIN_DISPATCHED
    return verdict("G1", ok, n, fl, "%d scheduled opportunities in [%.2f, %.2f] vs floor %d; %d dispatched (min %d)"
                   % (n, a, b, fl, started, G1_MIN_DISPATCHED),
                   {"window": [a, b], "rate": rate, "startedInWindow": started, "minDispatched": G1_MIN_DISPATCHED})


def g2(cell):
    rows, m = cell.get("ledger"), measurement(cell)
    rate = (cell.get("plan") or {}).get("rate")
    if rows is None or m is None:
        return verdict("G2", None, None, None, "no ledger or measurement")
    if not _scheduled_complete(rows):
        return verdict("G2", None, None, None, "ledger rows lack scheduled stamps")
    onset = onset_of(cell)
    if onset is None and cell.get("kind") == "fault":
        return verdict("G2", None, None, None, "fault timing missing")
    if onset is None:                                   # cost-only cell: the whole measurement
        lo, hi, cost = m[0], m[1], True
        pre = [r for r in rows if lo <= r["scheduled"] <= hi]
    else:
        lo, hi, cost = m[0], onset, False
        pre = [r for r in rows if lo <= r["scheduled"] < hi]
    good, bad = outcome_counts(pre)
    fl = need(rate, hi - lo)
    if good + bad == 0:
        return verdict("G2", None, {"successes": 0, "failureShare": None}, None, "no known outcome before onset")
    share = bad / float(good + bad)
    ok = None if fl is None else (good >= fl and share <= PRE_FAIL_MAX)
    return verdict("G2", ok, {"successes": good, "failureShare": share},
                   {"successes": fl, "failureShareMax": PRE_FAIL_MAX},
                   "%s: %d successes, failure share %.3f over [%.2f, %.2f)" % (
                       "healthy" if ok else "not healthy" if ok is False else "unknown", good, share, lo, hi),
                   {"window": [lo, hi], "costCell": cost, "failures": bad})


def entry_rule_can_fire(cell):
    """Would one planted failed request in the no-fault window make the entry-point rule fire? Needs >= 1 dispatched
    request in the window and >= 1 successful pre-window request (traffic_gate.py:92-110). None: not a FA window."""
    w = (cell.get("plan") or {}).get("window")
    if cell.get("kind") != "nofault" or not w:
        return None
    rows, m = cell.get("ledger"), measurement(cell)
    if rows is None or m is None or not _scheduled_complete(rows):
        return False
    a, b = float(w[0]), float(w[1])
    inside = [r for r in rows if r.get("started") is not None and a <= r["started"] <= b]
    pre_ok = [r for r in rows if m[0] <= r["scheduled"] < a and r.get("status") == "ok"]
    return bool(inside) and bool(pre_ok)


def g4(cell, profile):
    rows, plan, m = cell.get("ledger"), cell.get("plan") or {}, measurement(cell)
    offered, rate, duration = plan.get("offered"), plan.get("rate"), plan.get("durationSeconds")
    shares = {}
    if rows and m is not None and _scheduled_complete(rows):
        shares["ledger"] = sum(1 for r in rows if m[0] - SCOPE_SLACK_S <= r["scheduled"] <= m[1] + SCOPE_SLACK_S) \
            / float(len(rows))
    collected = list((profile.get("channels") or {}).get(cell.get("posture"), []) or [])
    chans = cell.get("channels") or {}
    missing_scope = []
    for ch in sorted(set(collected) | set(chans)):
        c = chans.get(ch) or {}
        if c.get("recordsTotal") and c.get("recordsInCell") is not None:
            shares["channel:" + ch] = c["recordsInCell"] / float(c["recordsTotal"])
        elif ch in collected:
            missing_scope.append(ch)
    profile_rate = profile.get("rate")
    checks = {
        "ledger": cell.get("ledgerKind") == "ledger" and isinstance(rows, list),
        "faultTiming": fault_timing(cell) is not None if cell.get("kind") == "fault" else True,
        "validityRecorded": cell.get("valid") is not None,
        "offeredEqualsPlan": isinstance(rows, list) and offered is not None and len(rows) == int(offered),
        "planConsistent": None not in (offered, rate, duration)
        and abs(float(offered) - float(rate) * float(duration)) <= 1.0,
        "rateEqualsProfile": None not in (rate, profile_rate) and math.isclose(float(rate), float(profile_rate)),
        "scope": "ledger" in shares and not missing_scope and min(shares.values()) >= SCOPE_MIN,
    }
    failed = sorted(k for k, v in checks.items() if not v)
    return verdict("G4", not failed, failed, "all of %s; scope >= %.2f" % (sorted(checks), SCOPE_MIN),
                   "provenance complete" if not failed else "provenance fails: %s" % ", ".join(failed),
                   {"offered": len(rows) if isinstance(rows, list) else None, "planOffered": offered,
                    "scopeShares": shares, "channelsWithoutScopeCounts": missing_scope})


# --------------------------------------------------------------------------- cell, campaign, G3

def evaluate_cell(cell, profile):
    records = [p0(cell, profile), r1(cell, profile), r2(cell), r2_recovery(cell), f1(cell), g1(cell), g2(cell),
               g4(cell, profile)]
    required = [g for g in BLOCKING if g != "F1" or cell.get("kind") == "fault"]
    by_gate = dict((r["gate"], r) for r in records)
    failed = [g for g in required if by_gate[g]["verdict"] != "pass"]
    if cell.get("kind") not in KINDS:
        failed.append("kind")
    if cell.get("valid") is False:
        failed.append("harness")
    return {"cellId": cell.get("cellId"), "kind": cell.get("kind"), "posture": cell.get("posture"),
            "verdicts": records, "valid": not failed, "failedGates": failed, "canFire": entry_rule_can_fire(cell)}


def stop_decision(cell_result):
    """Campaign stop rule: stop and ask the user on the first invalid cell."""
    if cell_result["valid"]:
        return None
    return {"action": "stop-and-ask", "cellId": cell_result["cellId"], "failedGates": cell_result["failedGates"]}


def g3(cell_results, firings=None, tau=TAU):
    """False-alarm rate per sensor family over valid no-fault windows that can fire (valid implies G1 and G2 pass).
    cell_results: evaluate_cell outputs; firings: {family: [cellId fired]}.
    Returns one 'G3' window record plus one 'G3:<family>' record per family."""
    fa = [r for r in cell_results if r["kind"] == "nofault" and r["canFire"] is not None]

    eligible = set(r["cellId"] for r in fa if r["canFire"] and r["valid"])
    n, n_eff = len(fa), len(eligible)
    ok = None if n == 0 else n_eff > 0
    out = [verdict("G3", ok, n_eff, n, "no no-fault window" if n == 0 else
                   "%d of %d no-fault windows can carry a false alarm%s" % (
                       n_eff, n, "" if n_eff == n else " (partial)") if n_eff else
                   "no eligible no-fault window: the rate cannot fail", {"eligible": sorted(eligible)})]
    for family, fired in sorted((firings or {}).items()):
        k = len(set(fired) & eligible)
        if n == 0:
            out.append(verdict("G3:" + family, None, None, tau, "no no-fault window"))
        elif n_eff == 0:
            out.append(verdict("G3:" + family, False, None, tau, "n_eff = 0: the rate cannot fail"))
        else:
            rate = k / float(n_eff)
            out.append(verdict("G3:" + family, rate <= tau, rate, tau, "%d/%d eligible no-fault windows fired"
                               % (k, n_eff), {"k": k, "nEff": n_eff, "n": n, "partial": n_eff < n}))
    return out


def evaluate_campaign(cells, profile, firings=None, tau=TAU):
    """Every cell in campaign order, the stop decision (first invalid cell) and G3."""
    results = [evaluate_cell(c, profile) for c in cells]
    stop = None
    for r in results:
        stop = stop_decision(r)
        if stop is not None:
            break
    return {"cells": results, "stop": stop, "g3": g3(results, firings, tau)}


# --------------------------------------------------------------------------- self-check (in memory, writes nothing)

SYNTH_PROFILE = {"sut": "synthetic", "routes": ["/a", "/b"], "rate": 4.0, "services": ["frontend", "search", "geo"],
                 "channels": {"full": ["traces", "logs"]}, "emitters": {"full": ["frontend", "search", "geo"]}}


def synthetic_cell(cell_id, kind):
    """Open loop at 4/s over 300 s (1200 opportunities), 20 ms latency; fault window [100, 130] with every third
    in-window request failing at a 1 s timeout; no-fault cells carry the same pseudo window."""
    rows = []
    for k in range(1200):
        s = k * 0.25
        st = s + 0.001
        failing = kind == "fault" and 100.0 <= s <= 130.0 and k % 3 == 0
        rows.append({"scheduled": s, "started": st, "ended": st + (1.0 if failing else 0.02),
                     "status": "timeout" if failing else "ok"})
    cell = {"cellId": cell_id, "kind": kind, "posture": "full", "valid": True,
            "plan": {"offered": 1200, "rate": 4.0, "durationSeconds": 300.0, "window": [100.0, 130.0]},
            "measurement": [0.0, 300.0], "ledgerKind": "ledger", "ledger": rows,
            "channels": {"traces": {"recordsAfterWarmup": 500, "recordsInCell": 990, "recordsTotal": 1000},
                         "logs": {"recordsAfterWarmup": 80, "recordsInCell": 200, "recordsTotal": 200}},
            "readiness": {"servicesRunning": {"frontend": True, "search": True, "geo": True},
                          "routeStatus": {"/a": 200, "/b": 200}, "ledgerRows": 4, "attempt": 1},
            "baseState": {"freshProject": True, "volumesRemoved": True},
            "provenance": {"namespaceEmpty": True,
                           "imageDigests": dict((s, "registry/%s@sha256:%s" % (s, "ab" * 32))
                                                for s in ("frontend", "search", "geo")),
                           "postureProof": {"method": "connection-count",
                                            "observed": {"frontend": 3, "search": 2, "geo": 1}}}}
    if kind == "fault":
        cell["fault"] = {"scheduledOnset": 100.0, "scheduledHold": 30.0, "onsetCommandIssued": 100.01,
                         "onsetCommandReturned": 100.3, "revertCommandIssued": 130.32,
                         "revertCommandReturned": 130.6, "onsetSource": "pre-command",
                         "manifested": True, "reverted": True}
    return cell


def _plant_g1(c):
    # the schedule ran at double rate over [0, 150) and then stopped: offered == plan, nothing scheduled after 150 s
    for k, r in enumerate(c["ledger"]):
        r["scheduled"] = k * 0.125
        r["started"] = r["scheduled"] + 0.001
        r["ended"] = r["started"] + 0.02
        r["status"] = "ok"
    c["fault"]["onsetCommandIssued"], c["fault"]["scheduledOnset"] = 160.01, 160.0
    c["fault"]["onsetCommandReturned"], c["fault"]["revertCommandIssued"] = 160.3, 190.32
    c["fault"]["revertCommandReturned"] = 190.6


def _plant_g2(c):
    for r in c["ledger"]:
        if r["scheduled"] < 100.0:
            r["status"] = "failed"


def _plant_g4(c):
    c["ledger"] = c["ledger"][1:]          # one opportunity lost: offered != plan


def _plant_stall(c, cap=2, timeout=10.0):
    """Concurrency-capped generator during the pause: `cap` requests hang until `timeout`, so starts trickle at
    cap / timeout per second while every opportunity stays scheduled (OTel: 85 of 155 started in a ~155 s window)."""
    a, b = c["fault"]["onsetCommandIssued"], c["fault"]["revertCommandIssued"]
    free = [a] * cap                                    # times at which each worker slot frees up
    for r in c["ledger"]:
        if not a <= r["scheduled"] <= b:
            continue
        slot = min(range(cap), key=lambda i: free[i])
        start = max(r["scheduled"], free[slot])
        if start > b:
            r["started"], r["ended"], r["status"] = None, None, "dropped"
            continue
        r["started"], r["ended"], r["status"] = start, start + timeout, "timeout"
        free[slot] = start + timeout


PLANTED = {
    # defect: (gate it must flip, index of the cell it is planted in, mutation)
    "posture-leak": ("P0", 0, lambda c: c["provenance"]["postureProof"]["observed"].update({"currency": 7})),
    "route-404": ("R1", 0, lambda c: c["readiness"]["routeStatus"].update({"/b": 404})),
    "volumes-kept": ("R2", 0, lambda c: c["baseState"].update({"volumesRemoved": False})),
    "probe-stamped-onset": ("F1", 0, lambda c: c["fault"].update({"onsetSource": "probe"})),
    "schedule-misses-window": ("G1", 0, _plant_g1),
    "failing-before-fault": ("G2", 0, _plant_g2),
    "family-fires-in-no-fault": ("G3:log", None, None),
    "offered-not-plan": ("G4", 0, _plant_g4),
}


def synthetic_campaign(defect=None):
    """Two fault and two no-fault cells (fault, fault, nofault, nofault); `defect` from PLANTED. Returns
    (cells, profile, firings)."""
    cells = [synthetic_cell("fault-0", "fault"), synthetic_cell("fault-1", "fault"),
             synthetic_cell("nofault-0", "nofault"), synthetic_cell("nofault-1", "nofault")]
    # healthy: the log family fires in no no-fault window; planted: in both (2/2 > TAU)
    firings = {"log": ["nofault-0", "nofault-1"] if defect == "family-fires-in-no-fault" else []}
    if defect is not None and PLANTED[defect][2] is not None:
        PLANTED[defect][2](cells[PLANTED[defect][1]])
    return cells, copy.deepcopy(SYNTH_PROFILE), firings


def _gate_verdicts(E):
    """{gate: 'pass'|'fail'|'—'}, a gate failing in any cell is 'fail'; G3 records from the population."""
    out = {}
    for r in E["cells"]:
        for v in r["verdicts"]:
            if v["gate"] == "R2.recovery":
                continue
            if v["gate"] == "F1" and r["kind"] != "fault":
                continue
            prev = out.get(v["gate"], "pass")
            out[v["gate"]] = "fail" if "fail" in (prev, v["verdict"]) else (
                UNKNOWN if UNKNOWN in (prev, v["verdict"]) else "pass")
    for v in E["g3"]:
        out[v["gate"]] = v["verdict"]
    return out


def self_check(broken=(), out=None):
    """Healthy campaign: every gate passes and nothing stops. Each planted defect must flip exactly its gate (every
    other gate stays as in the healthy run) and, for a blocking gate, stop the campaign at the planted cell.
    `broken`: gates forced to 'pass', simulating a gate that never fires; the self-check must then report a miss.
    Returns True when no mismatch."""
    broken = set(broken)
    lines = []

    def run(defect):
        cells, profile, firings = synthetic_campaign(defect)
        E = evaluate_campaign(cells, profile, firings)
        for r in E["cells"]:
            for v in r["verdicts"]:
                if v["gate"] in broken:
                    v["verdict"] = "pass"
            required = [g for g in BLOCKING if g != "F1" or r["kind"] == "fault"]
            extra = [g for g in r["failedGates"] if g in ("kind", "harness")]      # not gates: never broken
            r["failedGates"] = [v["gate"] for v in r["verdicts"] if v["gate"] in required and v["verdict"] != "pass"]
            r["failedGates"] += extra
            r["valid"] = not r["failedGates"]
        for v in E["g3"]:
            if v["gate"].split(":")[0] in broken:
                v["verdict"] = "pass"
        E["stop"] = next((stop_decision(r) for r in E["cells"] if not r["valid"]), None)
        return E

    healthy = run(None)
    base = _gate_verdicts(healthy)
    bad = 0
    ok_healthy = all(v == "pass" for v in base.values()) and healthy["stop"] is None
    bad += not ok_healthy
    lines.append("%-26s %s %s" % ("healthy", "all pass, no stop" if ok_healthy else "FAILED %s stop=%s" % (
        base, healthy["stop"]), "ok" if ok_healthy else "MISSED"))
    for defect, (gate, index, _) in sorted(PLANTED.items()):
        E = run(defect)
        got = _gate_verdicts(E)
        flipped = got.get(gate) == "fail"
        others = dict((g, v) for g, v in got.items() if g != gate and v != base.get(g))
        stop_ok = True
        if gate in BLOCKING:
            stop_ok = E["stop"] is not None and E["stop"]["cellId"] == E["cells"][index]["cellId"]
        ok = flipped and not others and stop_ok
        bad += not ok
        lines.append("%-26s %-7s expected fail got %-5s others changed %s stop %s %s" % (
            defect, gate, got.get(gate), others or "none", E["stop"]["cellId"] if E["stop"] else None,
            "ok" if ok else "MISSED"))
    lines.append("self-check: %s (%d mismatches)%s" % ("PASS" if not bad else "FAIL", bad,
                                                      "; broken gates: %s" % sorted(broken) if broken else ""))
    if out is not None:
        out.extend(lines)
    return bad == 0


def main(argv):
    if "--self-check" not in argv:
        sys.stdout.write(__doc__)
        return 0
    broken = argv[argv.index("--break") + 1].split(",") if "--break" in argv else ()
    lines = []
    ok = self_check(broken, lines)
    sys.stdout.write("protocol_gates self-check, python %s\n%s\n" % (sys.version.split()[0], "\n".join(lines)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
