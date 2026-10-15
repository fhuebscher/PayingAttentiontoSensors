#!/usr/bin/env python3
"""POST HOC, EXPLORATORY pooled lane evidence over every committed fault-episode readout, all three SUTs.

    uv run python research/lanes/pooled_lanes.py --out research/lanes/out-pooled-20261014

NOTHING HERE IS PREREGISTERED. Scope of every row: **instance** (one SUT, one host, one campaign family per row; a pooled row
pools campaigns of ONE SUT on ONE host, never across SUTs). It reads only committed readout JSON (no raw cell, nothing under
tmp/), calls no frozen reader, edits no existing file, and refuses to write into an existing output directory.

An episode is a readout `episodes[]` entry; its fires are [family, sensor, rule, ttd, dir, own, onPath, counts, bc, movedBy]
(research/detection-time/sweep_analysis_v2.py:3611-3612, celf_v3.FIRE). Per lane and episode, three times (seconds after the
pre-command onset stamp, `None` = a miss, never 0):
  * ttdCounted         earliest fire with `counts` true and NO BC flag (the field the scorer counts);
  * ttdByConstruction  earliest fire with `counts` true and a BC flag (BC-caller-log, BC-downstream-absent ...);
  * ttdAny             the earlier of the two (a fire with `counts` false is never used in any of them).
Lanes: own (own flag true, family != E); coordinator (log ids of service `registry` in TeaStore / `kafka` in OTel; Hotel: `—`,
consul collects nothing); coordinatorStrict (the heartbeat-removal / group-member-failed ids of research/lanes/out-20261013,
the lane that LANES.md reports); lag (OTel kafka consumer-lag metric ids armed at the rate, else `—`); ledger (family E, a rule
of celf_v3.E_RULES, own fires dropped as celf_v3.counted does).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO / "research" / "placement", REPO / "research"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import celf_v3 as cv  # noqa: E402  frozen; imported, never edited

POST_HOC = "POST HOC, EXPLORATORY (not preregistered; computed after the readouts were seen)"
SCOPE = "instance"
DASH = "—"
SWEEP = REPO / "research" / "traffic-sweep"
LANES_JSON = REPO / "research" / "lanes" / "out-20261013" / "lanes.json"
FIRE = cv.FIRE

# ---------------------------------------------------------------------------- switch (tests/test_pooled_lanes.py flips it)
COUNTED_ONLY = True          # a fire with counts False is never used (False: planted defect)

# ---------------------------------------------------------------------------- the chosen readout per campaign
# One readout per campaign: the latest frozen/committed one that contains the campaign's fault episodes. Readouts that pool
# the same cells are listed in NOT_USED with the reason (no double counting).
USED = [
    {"system": "teastore", "dir": "readout-teastore-c-v3.1", "file": "sweep_analysis_v3.json", "reader": "v3.1",
     "covers": "TeaStore sweep r2 + campaign B + campaign C (auth-freeze, persistence-cpu-throttle; 4 + 12 + 12 each)"},
    {"system": "otel", "dir": "readout-otel-c-v3.1", "file": "sweep_analysis_v3.json", "reader": "v3.1",
     "covers": "OTel sweep r1 + campaign B + campaign C (frontend-pause, productcatalog-cpu-throttle; 4 + 12 + 12 each)"},
    {"system": "otel", "dir": "readout-otel-e-score-v3.2", "file": "sweep_analysis_v3_2.json", "reader": "v3.2",
     "covers": "OTel campaign E (accounting-pause, fraud-pause, frontend-pause, 5 each, rate 25; blocks 1-3 train, 4-5 test)"},
    {"system": "hotel", "dir": "readout-hotel-primary-v3.1", "file": "sweep_analysis_v3.json", "reader": "v3.1",
     "covers": "Hotel sweep relaunch 3 (search-pause, cpu-throttle on profile, net-delay on rate; 16 each)"},
]
NOT_USED_REASON = [
    (r"^readout-teastore-(primary|quietcurve-.*)-v3\.1$", "pools sweep r2 + B (+ quiet cells) only: a subset of the C readout's fault cells"),
    (r"^readout-otel-(primary|quietcurve-.*)-v3\.1$", "pools sweep r1 + B (+ quiet cells) only: a subset of the C readout's fault cells"),
    (r"^readout-hotel-quietcurve-.*-v3\.1$", "same sweep r3 fault cells as the primary readout, quiet-time ablation"),
    (r"^readout-teastore-r2-v(2\.4|3.*)$", "earlier reader version of sweep r2 (superseded by the C v3.1 readout, which also pools B and C)"),
    (r"^readout-otel-r1-v(2\.4|3.*)$", "earlier reader version of sweep r1 (superseded by the C v3.1 readout, which also pools B and C)"),
    (r"^readout-hotel-r3-v2\.4$", "v2.4: no calibration (no prices); the same Hotel sweep r3 cells as the used v3.1 readout, read by an earlier detector"),
    (r"^readout-hotel-r3(-.*)?$", "earlier reader version of Hotel sweep r3 (superseded by the v3.1 primary readout)"),
    (r"^readout-otel-e-train-v3\.2$", "blocks 1-3 of E only; the score readout carries all 15 episodes with identical fires on blocks 1-3 (decision 102)"),
]
CAMPAIGN_LABEL = [("teastoresweep2", "sweep r2"), ("teastoreb1", "B"), ("c-fault-copy", "C"), ("otel-sweep-evidence", "sweep r1"),
                  ("otel-b-evidence", "B"), ("hotelsweep3", "sweep r3"), ("otel-e-evidence", "E")]

# ---------------------------------------------------------------------------- coordinator membership (a constant, with its source)
# TeaStore: every service registers with the registry (registry log: "Registered ...auth|webui|persistence|recommender|image").
# OTel: the only Kafka consumer groups seen by the broker's GroupCoordinator log are accountingservice and frauddetectionservice
# (research/lanes/out-20261013/lanes.json O2, 20 E cells); frontend and productcatalogservice are not group members.
MEMBERS = {"teastore": {"auth", "persistence", "webui", "recommender", "image"},
           "otel": {"accountingservice", "frauddetectionservice"}, "hotel": set()}
COORD_PREFIX = {"teastore": "log:registry:", "otel": "log:kafka:"}
LAG_RX = re.compile(r"^metric:(kafka|frauddetectionservice):.*(records_lag|kafka\.lag\.max|last_poll_seconds_ago|time_between_poll|records_lead)")

CLASS_LABEL = {
    "hit-counted": "hit, counted field",
    "d": "(d) by-construction hit only (counted field miss)",
    "a": "(a) structural: no coordinator collected",
    "b": "(b) fault keeps heartbeats alive (throttle/delay: no failure record)",
    "c": "(c) fault target not registered with the coordinator",
    "e": "(e) unexplained miss (target is a member, fault is a pause)",
}


# ============================================================================ pure helpers

def fmt(x, nd=2):
    if x is None:
        return DASH
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return ("%." + str(nd) + "f") % x
    return str(x)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(fmt(c) for c in r) + " |")
    return "\n".join(out)


def tstats(ts):
    ts = [t for t in ts if t is not None]
    if not ts:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {"n": len(ts), "min": min(ts), "median": statistics.median(ts), "max": max(ts)}


def usable(f):
    """A fire is usable only with `counts` true (switch COUNTED_ONLY lets a test plant the defect of ignoring it)."""
    return bool(f[FIRE["counts"]]) if COUNTED_ONLY else True


def lane_times(fires):
    """-> {ttdCounted, ttdByConstruction, ttdAny, rules, ids} of an episode's lane fires (already filtered to the lane)."""
    counted = [f[FIRE["ttd"]] for f in fires if usable(f) and not f[FIRE["bc"]]]
    bcs = [f[FIRE["ttd"]] for f in fires if usable(f) and f[FIRE["bc"]]]
    c, b = (min(counted) if counted else None), (min(bcs) if bcs else None)
    anyt = min([t for t in (c, b) if t is not None], default=None)
    used = [f for f in fires if usable(f)]
    return {"ttdCounted": c, "ttdByConstruction": b, "ttdAny": anyt,
            "ids": sorted({f[FIRE["sensorId"]] for f in used}), "rules": sorted({f[FIRE["rule"]] for f in used})}


def episode_lanes(e, system, coord_strict, lag_armed):
    """Lane record of one episode. lag_armed: set of armed lag ids at the episode's rate (empty -> lane is `—`)."""
    fires = e["fires"]
    non_e = [f for f in fires if f[FIRE["family"]] != cv.LEDGER_FAMILY]
    out = {"own": lane_times([f for f in non_e if f[FIRE["own"]]])}
    if system in COORD_PREFIX:
        pre = COORD_PREFIX[system]
        out["coordinator"] = lane_times([f for f in non_e if f[FIRE["sensorId"]].startswith(pre)])
        out["coordinatorStrict"] = lane_times([f for f in non_e if f[FIRE["sensorId"]] in coord_strict])
    else:
        out["coordinator"] = out["coordinatorStrict"] = None          # Hotel: consul collects nothing: structural absence
    if system == "otel" and lag_armed:
        out["lag"] = lane_times([f for f in non_e if f[FIRE["sensorId"]] in lag_armed])
    else:
        out["lag"] = None                                             # no armed lag id (or TeaStore/Hotel: n/a)
    out["ledger"] = lane_times([f for f in fires if f[FIRE["family"]] == cv.LEDGER_FAMILY
                                and f[FIRE["rule"]] in cv.E_RULES and not f[FIRE["own"]]])
    return out


def classify_coordinator(system, target, fault_kind, lane):
    """Class of one episode's coordinator outcome: 'hit-counted', or d / a / b / c / e (see CLASS_LABEL)."""
    if system == "hotel" or lane is None:
        return "a"
    if lane["ttdCounted"] is not None:
        return "hit-counted"
    if lane["ttdByConstruction"] is not None:
        return "d"
    if target not in MEMBERS[system]:
        return "c"
    if fault_kind != "pause":
        return "b"
    return "e"


def spearman(xs, ys):
    """Spearman rank correlation with average ranks; None if fewer than 4 pairs or a constant variable."""
    if len(xs) < 4:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0 + 1
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy)


def campaign_label(J, e):
    path = J["campaigns"][e["campaignIndex"]]
    path = path if isinstance(path, str) else json.dumps(path)
    for key, lab in CAMPAIGN_LABEL:
        if key in path:
            return lab
    return "campaign %d" % e["campaignIndex"]


def lag_armed_at(J, rate):
    s = J["calibration"]["primary"]["perRate"][cv.rate_key(rate)]["sensors"]
    return sorted(k for k, v in s.items() if LAG_RX.search(k) and v.get("placeable"))


def lag_universe_at(J, rate):
    s = J["calibration"]["primary"]["perRate"][cv.rate_key(rate)]["sensors"]
    return sorted(k for k in s if LAG_RX.search(k))


# ============================================================================ build

def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def strict_ids():
    L = json.loads(LANES_JSON.read_text())
    return {"otel": {c["id"] for c in L["O2"]["candidatesOtel"] if c["lane2"]},
            "teastore": {c["id"] for c in L["O2"]["candidatesTeaStore"] if c["lane2"]}}, L


def collect(used=None, strict=None):
    """Per-episode records over every used readout."""
    used = USED if used is None else used
    if strict is None:
        strict, _ = strict_ids()
    recs, inputs = [], []
    for u in used:
        p = SWEEP / u["dir"] / u["file"]
        J = json.loads(p.read_text())
        inputs.append(dict(u, path=str(p.relative_to(REPO)), sha256=sha256(p), episodes=len(J["episodes"])))
        system = u["system"]
        armed = {}
        for e in J["episodes"]:
            rk = cv.rate_key(e["rate"])
            if rk not in armed:
                armed[rk] = (lag_armed_at(J, e["rate"]), lag_universe_at(J, e["rate"]))
            lanes = episode_lanes(e, system, strict.get(system, set()), set(armed[rk][0]))
            kind = e["regime"].replace("-effect", "")
            recs.append({"system": system, "readout": u["dir"], "campaign": campaign_label(J, e), "regime": kind,
                         "faultKind": e["faultKind"], "target": e["target"], "rate": e["rate"], "block": e["block"],
                         "cell": e["cell"].split(" :: ")[-1], "lanes": lanes,
                         "lagArmedIds": armed[rk][0], "lagIdsInUniverse": len(armed[rk][1]),
                         "coordClass": classify_coordinator(system, e["target"], e["faultKind"], lanes["coordinator"])})
    return recs, inputs


LANE_ORDER = ("own", "coordinator", "coordinatorStrict", "lag", "ledger")


def summarise(recs, key):
    """Group episode records by `key(rec)`; per lane: episodes, counted, by-construction-only, any, time stats of ttdAny."""
    g = defaultdict(list)
    for r in recs:
        g[key(r)].append(r)
    rows = []
    for k, rs in sorted(g.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        row = {"key": list(k), "episodes": len(rs), "lanes": {}}
        for lane in LANE_ORDER:
            ls = [r["lanes"][lane] for r in rs]
            if all(x is None for x in ls):
                row["lanes"][lane] = None            # not collected / none armed: `—`, never 0
                continue
            ls = [x for x in ls if x is not None]
            anyt = [x["ttdAny"] for x in ls]
            cnt = [x["ttdCounted"] for x in ls]
            bc = [x["ttdByConstruction"] for x in ls]
            row["lanes"][lane] = {"episodes": len(ls), "counted": sum(t is not None for t in cnt),
                                  "byConstruction": sum(t is not None for t in bc),
                                  "byConstructionOnly": sum(1 for c, b in zip(cnt, bc) if c is None and b is not None),
                                  "any": sum(t is not None for t in anyt), "ttdAny": tstats(anyt),
                                  "ttdCounted": tstats(cnt), "ttdByConstruction": tstats(bc)}
        rows.append(row)
    return rows


def failure_table(recs):
    g = defaultdict(list)
    for r in recs:
        g[(r["system"], r["regime"], r["faultKind"], r["target"])].append(r)
    rows = []
    for k, rs in sorted(g.items()):
        counts = defaultdict(int)
        for r in rs:
            counts[r["coordClass"]] += 1
        rows.append({"system": k[0], "regime": k[1], "faultKind": k[2], "target": k[3], "episodes": len(rs),
                     "classes": dict(counts),
                     "hitsAny": sum(1 for r in rs if r["lanes"]["coordinator"] and r["lanes"]["coordinator"]["ttdAny"] is not None),
                     "hitsCounted": counts.get("hit-counted", 0)})
    return rows


def rate_dependence(recs):
    """Per (system, regime, lane): median ttdAny per rate and Spearman rho(log10 rate, ttdAny) over detected episodes."""
    g = defaultdict(list)
    for r in recs:
        g[(r["system"], r["regime"])].append(r)
    out = []
    for (system, regime), rs in sorted(g.items()):
        for lane in ("own", "coordinator", "ledger"):
            ls = [(r["rate"], r["lanes"][lane]) for r in rs if r["lanes"][lane] is not None]
            if not ls:
                continue
            rates = sorted({x[0] for x in ls})
            per = {}
            for rt in rates:
                ts = [x["ttdAny"] for ra, x in ls if ra == rt]
                st = tstats(ts)
                per["%g" % rt] = {"episodes": len(ts), "detected": st["n"], "median": st["median"]}
            det = [(math.log10(ra), x["ttdAny"]) for ra, x in ls if x["ttdAny"] is not None]
            rho = spearman([a for a, _ in det], [b for _, b in det]) if len({a for a, _ in det}) > 1 else None
            out.append({"system": system, "regime": regime, "lane": lane, "perRate": per, "nDetected": len(det),
                        "spearmanRho": rho})
    return out


def cross_checks(recs, L):
    """Two numbers against research/lanes/out-20261013/LANES.md, plus every own any-rule row against lanes.json O1."""
    checks = []

    def sel(**kw):
        return [r for r in recs if all(r[k] == v for k, v in kw.items())]
    e_eps = [r for r in sel(system="otel", readout="readout-otel-e-score-v3.2") if r["regime"] in ("accounting-pause", "fraud-pause")]
    ts = [r["lanes"]["own"]["ttdAny"] for r in e_eps]
    st = tstats(ts)
    checks.append({"check": "LANES.md: E own 10/10, 0.88-1.55 s (accounting + fraud pause, own lane, any rule)",
                   "computed": "%d/%d, %.2f-%.2f s" % (st["n"], len(e_eps), st["min"] or float("nan"), st["max"] or float("nan")),
                   "ok": st["n"] == 10 and len(e_eps) == 10 and round(st["min"], 2) == 0.88 and round(st["max"], 2) == 1.55})
    c_eps = [r for r in sel(system="teastore", regime="auth-freeze")]
    ts = [r["lanes"]["coordinator"]["ttdAny"] for r in c_eps]
    st = tstats(ts)
    checks.append({"check": "LANES.md: TeaStore C readout registry 28/28, 9.07-11.75 s (auth-freeze, all campaigns of the readout)",
                   "computed": "%d/%d, %.2f-%.2f s" % (st["n"], len(c_eps), st["min"] or float("nan"), st["max"] or float("nan")),
                   "ok": st["n"] == 28 and len(c_eps) == 28 and round(st["min"], 2) == 9.07 and round(st["max"], 2) == 11.75})
    # every own any-rule row of LANES.md O1 (E, TeaStore C, Hotel v3.1) against this script's own lane
    bad, n = [], 0
    for row in L["O1"]:
        if row["system"] not in ("otel", "teastore", "hotel"):
            continue
        rs = [r for r in recs if r["system"] == row["system"] and r["regime"] + "-effect" == row["regime"]
              and r["rate"] == row["rate"] and (row["system"] != "otel" or r["readout"] == "readout-otel-e-score-v3.2")]
        det = [r["lanes"]["own"]["ttdAny"] for r in rs if r["lanes"]["own"]["ttdAny"] is not None]
        med = statistics.median(det) if det else None
        n += 1
        if len(det) != row["anyOwnRuleDetected"] or (med is None) != (row["anyOwnRuleMedian"] is None) or \
                (med is not None and abs(med - row["anyOwnRuleMedian"]) > 1e-9):
            bad.append((row["system"], row["regime"], row["rate"], len(det), row["anyOwnRuleDetected"]))
    checks.append({"check": "own lane (any rule) equals LANES.md O1 'any own rule' detected and median, every row",
                   "computed": "%d rows compared, %d differ" % (n, len(bad)), "ok": not bad, "differ": bad})
    return checks


def build(out_dir):
    out_dir = Path(out_dir)
    if out_dir.exists() or out_dir.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s (new evidence never overwrites old)" % out_dir)
    strict, L = strict_ids()
    recs, inputs = collect(USED, strict)
    all_dirs = sorted(p.name for p in SWEEP.glob("readout-*") if p.is_dir())
    used_dirs = {u["dir"] for u in USED}
    not_used = []
    for d in all_dirs:
        if d in used_dirs:
            continue
        why = next((w for rx, w in NOT_USED_REASON if re.match(rx, d)), "no rule: unclassified, not used")
        not_used.append({"dir": d, "reason": why})
    R = {"label": POST_HOC, "scope": SCOPE, "inputs": inputs, "notUsed": not_used,
         "strictIds": {k: sorted(v) for k, v in strict.items()},
         "members": {k: sorted(v) for k, v in MEMBERS.items()},
         "episodes": recs,
         "perCampaign": summarise(recs, lambda r: (r["system"], r["campaign"], r["regime"], r["faultKind"], "%g" % r["rate"])),
         "pooled": summarise(recs, lambda r: (r["system"], r["regime"], r["faultKind"], "%g" % r["rate"])),
         "coordinatorFailure": failure_table(recs), "rateDependence": rate_dependence(recs),
         "offPathPilotV2": DASH + " (no sweep readout: research/placement/pilot-offpath/manifestation-v2.json holds manifestation verdicts, no fires)",
         "crossChecks": cross_checks(recs, L)}
    out_dir.mkdir(parents=True)
    (out_dir / "pooled.json").write_text(json.dumps(R, indent=1, default=str))
    (out_dir / "POOLED.md").write_text(render_md(R))
    return R


# ============================================================================ rendering

def cell(lane, which="any"):
    if lane is None:
        return DASH
    if which == "counted":
        return "%d/%d" % (lane["counted"], lane["episodes"])
    st = lane["ttdAny"]
    base = "%d/%d" % (lane["any"], lane["episodes"])
    if st["n"]:
        base += " %.2f (%.2f-%.2f)" % (st["median"], st["min"], st["max"])
    return base


def lane_rows(rows, keyw):
    out = []
    for r in rows:
        L = r["lanes"]
        out.append(list(r["key"]) + [r["episodes"], cell(L["own"]), cell(L["own"], "counted"), cell(L["coordinator"]),
                                     cell(L["coordinator"], "counted"), cell(L["coordinatorStrict"]), cell(L["coordinatorStrict"], "counted"), cell(L["lag"]),
                                     cell(L["ledger"]), cell(L["ledger"], "counted")])
    return out


def render_md(R):
    o = ["# Pooled lane evidence, all three SUTs, 2026-10-14", "",
         "**%s.** Scope of every table: **%s** (one SUT, one host; pooled rows pool campaigns of one SUT, never SUTs). Produced by "
         "`research/lanes/pooled_lanes.py` from the committed readout JSON listed below; nothing under `tmp/` was read, no frozen file edited. "
         "Plan: user request 2026-10-14 (expand E's 10 off-path episodes to every relevant episode, show where the coordinator lane fails)." % (POST_HOC, SCOPE), "",
         "Cell format: `detected/episodes median (min-max)` in seconds after the pre-command onset stamp; `—` = not collected, none armed or "
         "no episode (never 0). A lane's *any* column uses fires with `counts` true; *counted* is the subset with no BC flag (the field the "
         "scorer counts); the difference is the by-construction-only hits (`byConstructionOnly` in pooled.json). Lanes: **own** = sensors of the "
         "fault's target service; **coord** = every log id of service `registry` (TeaStore) / `kafka` (OTel), Hotel `—` (consul writes no log, "
         "structural absence); **coord strict** = only the heartbeat-removal / group-member-failed ids reported in LANES.md; **lag** = OTel kafka "
         "consumer-lag metric ids armed at the rate (armed = placeable at the rate in the readout's calibration); **ledger** = family E. "
         "**These are detection times only: no lane here is priced or charged for false alarms** (a lane's time is the earliest fire of any of its sensors, so a lane with several sensors is not a single-sensor claim). "
         "Rate 25 exists only in campaign E (reader v3.2), rates 0.05-10 in the v3.1 readouts: Table 3 mixes the two readers for OTel frontend-pause.", "",
         "## Readouts used (one per campaign) and not used", ""]
    o.append(md_table(["system", "readout", "reader", "episodes", "covers", "sha256 (first 12)"],
                      [[u["system"], u["path"], u["reader"], u["episodes"], u["covers"], u["sha256"][:12]] for u in R["inputs"]]))
    o += ["", "Not used (every other `readout-*` directory under research/traffic-sweep):", ""]
    o.append(md_table(["readout", "reason"], [[n["dir"], n["reason"]] for n in R["notUsed"]]))
    o += ["", "OTel off-path pilot v2: %s. Placement scorer outputs (`research/placement/test-c`, `test-e`) are derived from the used readouts and add no episodes." % R["offPathPilotV2"], "",
          "## Cross-checks against research/lanes/out-20261013/LANES.md", ""]
    o.append(md_table(["check", "computed", "ok"], [[c["check"], c["computed"], c["ok"]] for c in R["crossChecks"]]))
    hdr = ["episodes", "own any", "own counted", "coord any", "coord counted", "coord strict any", "coord strict counted", "lag", "ledger any", "ledger counted"]
    o += ["", "## Table 1: SUT x fault kind x rate (pooled over the SUT's campaigns)", ""]
    o.append(md_table(["system", "fault", "kind", "rate"] + hdr, lane_rows(R["pooled"], 4)))
    o += ["", "## Table 1b: SUT x campaign x fault kind x rate", ""]
    o.append(md_table(["system", "campaign", "fault", "kind", "rate"] + hdr, lane_rows(R["perCampaign"], 5)))
    o += ["", "## Table 2: coordinator failure, SUT x fault kind", "",
          "Classes (first match): hit counted; (d) counted field miss but a by-construction hit; (a) no coordinator collected (Hotel); (c) fault target "
          "is not a member of the coordinator (OTel: not an accounting/frauddetection Kafka group member); (b) member, fault is a throttle/delay "
          "(no failure record in the window, hence heartbeats/session survived); (e) member, pause, no hit (unexplained). (a), (b), (c) are assigned "
          "from fault kind and membership (`MEMBERS` in the script), not measured heartbeat liveness; the *absence* of a failure record is the measurement.", ""]
    rows = []
    for r in R["coordinatorFailure"]:
        c = r["classes"]
        rows.append([r["system"], r["regime"], r["faultKind"], r["target"], r["episodes"], c.get("hit-counted", 0), c.get("d", 0),
                     c.get("a", 0), c.get("b", 0), c.get("c", 0), c.get("e", 0)])
    o.append(md_table(["system", "fault", "kind", "target", "episodes", "hit counted", "(d) by-constr. only", "(a) structural",
                       "(b) heartbeat alive", "(c) not registered", "(e) unexplained"], rows))
    o += ["", "## Table 3: traffic dependence (median ttdAny per rate; Spearman rho of log10 rate vs ttdAny over detected episodes)", ""]
    rates = sorted({k for r in R["rateDependence"] for k in r["perRate"]}, key=float)
    rows = []
    for r in R["rateDependence"]:
        cells = []
        for rt in rates:
            p = r["perRate"].get(rt)
            cells.append(DASH if p is None else ("%d/%d %s" % (p["detected"], p["episodes"], "%.2f" % p["median"] if p["median"] is not None else DASH)))
        rows.append([r["system"], r["regime"], r["lane"]] + cells + [r["nDetected"], r["spearmanRho"]])
    o.append(md_table(["system", "fault", "lane"] + ["rate %s" % x for x in rates] + ["n detected", "rho"], rows))
    o += ["", "rho is `—` below 4 detected episodes or with one rate only. It is a descriptive rank correlation on one SUT's instance, not a test.", ""]
    return "\n".join(o)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    R = build(a.out)
    for c in R["crossChecks"]:
        print("%s: %s -> %s" % ("PASS" if c["ok"] else "FAIL", c["check"], c["computed"]))
    print("wrote", a.out)
    return 0 if all(c["ok"] for c in R["crossChecks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
