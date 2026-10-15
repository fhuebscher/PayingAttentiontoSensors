#!/usr/bin/env python3
"""Traffic-sweep analysis v3.3: v3.2's reader and rules (sweep_analysis_v3_2.py, frozen 05f70d4, imported and never
edited) extended for OTel campaign F and the TeaStore off-path epoch (research/traffic-sweep/BUDGET_F.md step 4,
BUDGET_TEASTORE_OFFPATH.md step 4, research/PLAN_LANES_20261014.md). Admission and reporting only.

    uv run python research/detection-time/sweep_analysis_v3_3.py <campaign dir> [<campaign dir> ...] --system otel|teastore \
        --out <new dir> [--blocks 1 2 3] [--split <split.json>] [--test-blocks 4 5] [--validation <no-fault campaign dir> ...]

STATUS: FROZEN by digest (research/protocol/FREEZE_V33_20261014.md) before any cell of campaign F or of teastore-offpath-v1 was
read (both launched 2026-10-14, none fetched; the only cells read while it was written are E's, as a regression, and synthetic
fixtures). The registry's epoch, regime and target entries are re-pinned at the harness commits 715d57b (OTel F) and f74b29b
(teastore-offpath-v1) and active; celf_v3_3.py and score_test_v3_3.py pin this file's and the registry's digests. Every claim
below is scope **method**; no number is produced by this file.

ENGINEERING CHOICE (recorded): like v3.2 over v3.1, v3.3 is a module of its own. It imports v3.2 (`import
sweep_analysis_v3_2 as v32`) and rebinds, for the duration of one run, a few of v3.2's module-level names (a context
manager restores every one) and swaps v3.2's `v32_context` for its own wrapper, so that v3.2's `run32`, `build_json32` and
`render32` run unchanged inside the v3.3 context. A v3.3 readout carries scriptSha256 of THIS file, v32ScriptSha256 of v3.2
and v31ScriptSha256 of v3.1, and keeps v3.2's `v32` block (its registry digest included) beside a `v33` block.

DEVIATIONS FROM v3.2. A group not listed did not change (calibration, level rules, `absent`/`appear`, pass rule, cost model,
placement and scorer logic are v3.2's). Each row names its switch (flipped only by tests/test_sweep_analysis_v3_3.py, a
planted defect each) and its registry entry (parameters_v3_3.json).
  Group 8 epoch admission (V33_EPOCH_PROFILES; switches ADMIT_NEW_EPOCHS, TEASTORE_SHAPE_CHECK, TEASTORE_TARGET_CHECK):
     8.3 OTel `otel-offpath-f-v1` is admitted as a campaign-E-role epoch with E's regimes (no-fault-calibration, fraud, accounting
         and frontend pause): v3.2's block selection, registry split, held-out rule and two-epochs refusal apply to it
         unchanged. It is a registry entry, not code.
     8.4 TeaStore `teastore-offpath-v1` is admitted as a campaign-B-shaped epoch with regimes no-fault-cost, recommender-pause-effect
         (target recommender) and auth-freeze-effect (target auth). v3.2 rebinds regimes per epoch for OTel only; v3.3 does it for
         TeaStore: a regime outside its epoch's declared regimes stops the run (UnknownSchema; v2.4 dropped an unknown regime
         silently as `not scored`, sweep_analysis_v2.py:1204), a legacy TeaStore epoch's cell named for an off-path regime
         stops the run, and a pause cell whose intervention names another service than its regime's declared target stops the
         run (v2.4 recorded that as a `parse error` not-scored cell). The regimes and targets are extended only when a cell of
         the off-path epoch is in the campaigns read (a receipts-only pre-scan), so a readout of legacy TeaStore epochs is v3.2's.
  Group 4 P1 and P2 (V33_ROUTE_MODEL_TEASTORE; switch TEASTORE_TWO_PAUSE): v2.4's pause_regime() asserts exactly one stopping
     regime per system (sweep_analysis_v2.py:2836-2839). With the TeaStore off-path epoch there are two; the reader accepts
     exactly the declared pair with the declared targets, declares P1 and P2 for the request-path pause (auth-freeze-effect), and
     refuses any other set or target loudly.
  Group 9 bookkeeping and display (V33_LANE_RULES, V33_LANES_REPORT_RULE; switches LANES_COUNTED_ONLY, LANES_OWN_SEPARATE): the
     readout carries a `v33.lanes` block, per regime and rate, with for each episode the earliest COUNTED fire of (a) the
     target's own sensors (excluded from the placement by decisions 84/111, kept excluded: this is a separate report row),
     (b) the coordinator-side sensors (OTel: log ids of service kafka; TeaStore: log ids of service registry) and (c) the
     consumer-group lag metrics (OTel: metric ids of service kafka named kafka.consumer_group.lag*; TeaStore: none, `—`). The id
     sets are defined by rule (service, channel, metric-name prefix), not by hash. A lane reads `—` when no sensor of it was
     collected in the cell; the summary's denominator is episodes with collected sensors. Counted = celf_v3's rule for a
     sensor fire under decision 72 (`counts` and no BC flag): a BC-flagged fire is a miss in the objective. Beside it, per lane,
     `earliestByConstruction` is the earliest fire that was dropped ONLY because it carries a BC flag (counts True, flags
     non-empty), with its flag list, labelled "by construction, not counted" (switch LANES_BC_SEPARATE). Reporting only: counting,
     placement and pass rule are unchanged.
  Kafka metric admission: no code. The kafkametrics receiver's resources carry service.name=kafka, `kafka` is in
     research/otel-offpath/adapter.py APP_SERVICES, so v2.4's reader (otel_metrics -> adapter.parse_otelcol) admits them under
     service `kafka`; MIN_BASELINE_POOLED stays 20. A resource without service.name is dropped by the adapter (tested).
"""
import argparse
import contextlib
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sweep_analysis_v3_2 as v32  # noqa: E402  v3.2 (frozen), never edited

v31, v24 = v32.v31, v32.v24
dt = v24.dt

PARAMETERS_V33 = REPO / "research" / "protocol" / "parameters_v3_3.json"
VERSION = "3.3"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V3_3.md", "sweep_analysis_v3_3.json"
LABEL = "frozen v3.3 for campaigns F and teastore-offpath-v1 (FREEZE_V33_20261014.md)"


# =========================================================================== the v3.3 registry (decision 37)

def load_registry(path=PARAMETERS_V33):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY33 = load_registry()
PARAMS_USED33 = set()


def param33(name):
    PARAMS_USED33.add(name)
    return REGISTRY33[name]["value"]


V32_PROFILES = dict(v32.EPOCH_PROFILES)            # v3.2's registry entry as frozen, captured before any rebinding
ADDED_PROFILES = param33("V33_EPOCH_PROFILES")
TS_MODEL = param33("V33_ROUTE_MODEL_TEASTORE")
LANE_RULES = param33("V33_LANE_RULES")
LANES_RULE_TEXT = param33("V33_LANES_REPORT_RULE")
assert not set(V32_PROFILES) & set(ADDED_PROFILES), "v3.3 adds epochs; it does not redefine v3.2's"

# Switches flipped only by tests/test_sweep_analysis_v3_3.py (planted defects); the analysis never changes them.
ADMIT_NEW_EPOCHS = True       # 8.3/8.4: F and the TeaStore off-path epoch are admitted (False: unknown epochs, the run stops)
TEASTORE_SHAPE_CHECK = True   # 8.4: a regime outside its epoch's declared regimes stops the run (False: v2.4's silent drop)
TEASTORE_TARGET_CHECK = True  # 8.4: a pause cell's intervention service must be its regime's declared target (False: read)
TEASTORE_TWO_PAUSE = True     # P1/P2: the declared pair of pause regimes is accepted (False: v2.4's one-regime assertion)
LANES_COUNTED_ONLY = True     # lanes: only counted fires (False: a fire the spike path filter dropped is a lane fire too)
LANES_OWN_SEPARATE = True     # lanes: an own fire is in `own` only (False: also in coordinator/lag when the service matches)
LANES_BC_SEPARATE = True      # lanes: a by-construction (BC-flagged) fire is not a counted fire, it is reported beside it (False: counted)
SWITCHES = ("ADMIT_NEW_EPOCHS", "TEASTORE_SHAPE_CHECK", "TEASTORE_TARGET_CHECK", "TEASTORE_TWO_PAUSE",
            "LANES_COUNTED_ONLY", "LANES_OWN_SEPARATE", "LANES_BC_SEPARATE")
BC_LABEL = "by construction, not counted"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def profiles_for(system):
    """v3.2's profiles plus v3.3's, those of one system (v3.2's loops over its profile dict add every profile's regimes to
    the system being read, so a profile of another system must never be in it)."""
    merged = dict(V32_PROFILES)
    if ADMIT_NEW_EPOCHS:
        merged.update(ADDED_PROFILES)
    return {e: p for e, p in merged.items() if p["system"] == system}


def teastore_epochs():
    return sorted(profiles_for("teastore"))


def teastore_legacy_regimes():
    prof = v24.REGISTRY["SYSTEM_TEASTORE"]["value"]
    return {prof["noFaultRegime"], *prof["faultRegimes"]}


# =========================================================================== TeaStore: epoch shape and the pause pair

_ORIG_TS_LOAD = v24.teastore_load_or_invalid
_ORIG_PAUSE = v24.pause_regime
_ORIG_CTX = v32.v32_context
_ACTIVE = {"teastore": False}      # a cell of the TeaStore off-path epoch is in the campaigns of this run (set by run33)


def _receipt_run(d):
    """(studyEpoch, regime) of a TeaStore cell's receipt, or (None, None) (blocked-evidence directories have none)."""
    try:
        rc = v24._read_json(Path(d) / "receipt.json")
    except (OSError, ValueError):
        return None, None
    if not isinstance(rc, dict):
        return None, None
    return rc.get("studyEpoch"), (rc.get("run") or {}).get("regime")


def load_teastore33(d):
    """v2.4's TeaStore cell loader behind the v3.3 epoch-shape check (8.4) and the target check."""
    d = Path(d)
    epoch, regime = _receipt_run(d)
    if isinstance(regime, str):
        prof = v32.EPOCH_PROFILES.get(epoch)
        if TEASTORE_SHAPE_CHECK:
            allowed = v32.profile_regimes(prof) if prof else teastore_legacy_regimes()
            if regime not in allowed:
                raise v24.UnknownSchema("%s: regime %r is not a regime of TeaStore epoch %r (%s)" % (
                    d, regime, epoch, sorted(allowed)))
        if prof and TEASTORE_TARGET_CHECK and regime in prof["faultRegimes"] and (d / "intervention.json").exists():
            want = prof["faultRegimes"][regime][0]
            got = (v24._read_json(d / "intervention.json") or {}).get("service")
            if got != want:
                raise v24.UnknownSchema("%s: intervention service %r, regime %r of epoch %r declares target %r" % (
                    d, got, regime, epoch, want))
    return _ORIG_TS_LOAD(d)


def pause_regime33():
    """The one regime P1 and P2 are declared for, with the TeaStore pause pair accepted: the stopping regimes in force must be
    EXACTLY V33_ROUTE_MODEL_TEASTORE.pauseRegimes with those targets (anything else stops the run)."""
    if not TEASTORE_TWO_PAUSE:
        return _ORIG_PAUSE()
    got = {r: v24.FAULT_TARGETS[r][0] for r in v24.FAULT_REGIMES if v24.FAULT_TARGETS[r][1] in dt.STOPPING}
    if got != TS_MODEL["pauseRegimes"]:
        raise v24.UnknownSchema("TeaStore stopping regimes %s are not the declared pair %s (V33_ROUTE_MODEL_TEASTORE): P1 and "
                                "P2 are declared for the declared pair only" % (got, TS_MODEL["pauseRegimes"]))
    return TS_MODEL["p1p2Regime"]


def epochs_present(campaigns, system):
    """The off-path epochs of `system` named by the receipts of the campaigns (receipts only; no cell is read)."""
    names = set(ADDED_PROFILES) if ADMIT_NEW_EPOCHS else set()
    out = set()
    for camp in campaigns:
        for rp in Path(camp).glob("**/receipt.json"):
            try:
                rc = json.loads(rp.read_text())
            except (OSError, ValueError):
                continue
            ep = (rc.get("studyEpoch") or (rc.get("runKey") or {}).get("studyEpoch")) if isinstance(rc, dict) else None
            if ep in names and ADDED_PROFILES[ep]["system"] == system:
                out.add(ep)
    return sorted(out)


@contextlib.contextmanager
def v33_context(system, rates=None, blocks=None, test_blocks=None):
    """v3.2's context with v3.2's epoch registry replaced by the v3.3 union of the system, and, for TeaStore with an
    off-path cell in the campaigns, the epoch admission, the regime and target bindings and the pause pair."""
    saved = []

    def put(mod, name, val):
        saved.append((mod, name, getattr(mod, name)))
        setattr(mod, name, val)

    try:
        put(v32, "EPOCH_PROFILES", profiles_for(system))
        if system == "teastore":
            put(v32, "ROUTE_MODEL", TS_MODEL)
            put(v32, "SYNC_EDGES", set())
            put(v32, "ASYNC_EDGES", set())
        with _ORIG_CTX(system, rates, blocks, test_blocks) as st:
            if system == "teastore" and _ACTIVE["teastore"] and v32.EPOCH_PROFILES:
                b = {k: list(v) for k, v in v31.STUDY_EPOCHS_B.items()}
                b["teastore"] = list(b.get("teastore", [])) + [e for e in v32.EPOCH_PROFILES
                                                               if e not in b.get("teastore", [])]
                put(v31, "STUDY_EPOCHS_B", b)
                put(v24, "teastore_load_or_invalid", load_teastore33)
                regimes, targets = list(v24.FAULT_REGIMES), dict(v24.FAULT_TARGETS)
                for prof in v32.EPOCH_PROFILES.values():
                    for r, (svc, kind) in prof["faultRegimes"].items():
                        if r not in regimes:
                            regimes.append(r)
                        targets[r] = (svc, kind)
                put(v24, "FAULT_REGIMES", tuple(regimes))
                put(v24, "FAULT_TARGETS", targets)
                put(v24, "pause_regime", pause_regime33)
            yield st
    finally:
        for mod, name, val in reversed(saved):
            setattr(mod, name, val)


@contextlib.contextmanager
def _v33_wrapped(active_teastore):
    """v3.2's run32 / build_json32 / render32 call `v32_context` by module name: swap it for the v3.3 wrapper."""
    prev = _ACTIVE["teastore"]
    _ACTIVE["teastore"] = bool(active_teastore)
    v32.v32_context = v33_context
    try:
        yield
    finally:
        v32.v32_context = _ORIG_CTX
        _ACTIVE["teastore"] = prev


# =========================================================================== lanes (group 9, reporting only)

LANES = ("own", "coordinator", "lag")


def lane_of(f, target, rules):
    """The lane of one fire under `rules` (a V33_LANE_RULES system entry), or None. The ledger is never a lane sensor; an own
    fire (decision 84's flag) is `own` and only `own` (LANES_OWN_SEPARATE); then coordinator, then lag, by rule: service, channel,
    metric-name or log-id prefix."""
    if f["ch"] == "ledger":
        return None
    if LANES_OWN_SEPARATE and (f["own"] or f["svc"] == target):
        return "own"
    for lane in ("coordinator", "lag"):
        r = rules.get(lane)
        if r and f["svc"] == r["service"] and f["ch"] in r["channels"] and any(
                f["tok"].startswith(p) for p in r["tokenPrefixes"]):
            return lane
    if not LANES_OWN_SEPARATE and (f["own"] or f["svc"] == target):
        return "own"
    return None


def sensors_in_lane(keys, lane, target, rules):
    """How many collected sensor keys (ch, svc, tok) of a cell belong to the lane (collected, not necessarily calibrated)."""
    n = 0
    for ch, svc, tok in keys:
        f = {"ch": ch, "svc": svc, "tok": tok, "own": svc == target}
        n += lane_of(f, target, rules) == lane
    return n


def _earliest(fs, with_flags=False):
    fs = sorted(fs, key=lambda f: (f["ttd"], "%s:%s:%s" % (f["ch"], f["svc"], f["tok"]), f["rule"]))
    if not fs:
        return None
    first = fs[0]
    out = {"ttd": first["ttd"], "ttdLo": first.get("ttdLo"), "sensor": "%s:%s:%s" % (first["ch"], first["svc"], first["tok"]),
           "rule": first["rule"]}
    if with_flags:
        out["bcFlags"] = list(first.get("bc") or [])
        out["label"] = BC_LABEL
    return out


def lanes_episode(e, rules):
    """Per lane: collected sensors, counted fires, distinct sensors, the earliest counted fire (None: no fire) and, beside it, the
    earliest fire dropped only by a BC flag (`earliestByConstruction`, with its flags; "by construction, not counted")."""
    c = e["_c"]
    keys = list(c.get("prep", {}))
    by = {lane: [] for lane in LANES}
    bc = {lane: [] for lane in LANES}
    for f in e["fires"]:
        if LANES_COUNTED_ONLY and not f.get("counts"):
            continue
        lane = lane_of(f, e["target"], rules)
        if lane is not None and (lane == "own" or rules.get(lane) is not None):
            (bc if (LANES_BC_SEPARATE and f.get("bc")) else by)[lane].append(f)
    out = {}
    for lane in LANES:
        collected = sensors_in_lane(keys, lane, e["target"], rules)
        if lane != "own" and rules.get(lane) is None:
            out[lane] = {"collectedSensors": None, "countedFires": None, "distinctSensors": None, "earliest": None,
                         "byConstructionFires": None, "earliestByConstruction": None,
                         "note": "no %s lane is declared for this system" % lane}
            continue
        fs = by[lane]
        out[lane] = {"collectedSensors": collected, "countedFires": len(fs),
                     "distinctSensors": len({(f["ch"], f["svc"], f["tok"]) for f in fs}),
                     "earliest": _earliest(fs),
                     "byConstructionFires": len(bc[lane]), "earliestByConstruction": _earliest(bc[lane], True)}
    return out


def _summ(rows, lane):
    got = [r["lanes"][lane] for r in rows]
    if got and got[0].get("note"):
        return {"episodes": len(rows), "withCollectedSensors": None, "withFire": None, "ttdMedian": None, "ttdMin": None,
                "ttdMax": None, "withByConstructionFire": None, "byConstructionTtdMedian": None,
                "byConstructionTtdMin": None, "byConstructionTtdMax": None, "note": got[0]["note"]}
    coll = [g for g in got if g["collectedSensors"]]
    ttds = sorted(g["earliest"]["ttd"] for g in coll if g["earliest"])
    bts = sorted(g["earliestByConstruction"]["ttd"] for g in coll if g["earliestByConstruction"])
    return {"episodes": len(rows), "withCollectedSensors": len(coll), "withFire": len(ttds),
            "ttdMedian": statistics.median(ttds) if ttds else None,
            "ttdMin": ttds[0] if ttds else None, "ttdMax": ttds[-1] if ttds else None,
            "withByConstructionFire": len(bts), "byConstructionTtdMedian": statistics.median(bts) if bts else None,
            "byConstructionTtdMin": bts[0] if bts else None, "byConstructionTtdMax": bts[-1] if bts else None,
            "byConstructionLabel": BC_LABEL}


def lanes_block(R, system):
    """V33_LANES_REPORT_RULE over the primary arm's episodes, per regime and rate."""
    rules = LANE_RULES[system]
    eps = R["results"]["primary"]["eps"]
    out = {"rule": LANES_RULE_TEXT, "system": system,
           "rules": {k: v for k, v in rules.items()}, "regimes": {}}
    for regime in sorted({e["regime"] for e in eps}):
        rows = []
        for e in sorted((x for x in eps if x["regime"] == regime), key=lambda x: (-x["rate"],) + v24.episode_order(x)):
            rows.append({"cell": e["cell"], "rate": e["rate"], "block": e["block"],
                         "heldOut": bool(e["_c"].get("heldOut")), "target": e["target"], "lanes": lanes_episode(e, rules)})
        by_rate = {}
        for rate in sorted({r["rate"] for r in rows}, reverse=True):
            sub = [r for r in rows if r["rate"] == rate]
            by_rate["%g" % rate] = {lane: _summ(sub, lane) for lane in LANES}
        out["regimes"][regime] = {"target": rows[0]["target"], "episodes": rows, "byRate": by_rate}
    return out


# =========================================================================== whole run

def run33(campaign, system="otel", validation_dirs=(), reference=True, blocks=None, split=None, test_blocks=None):
    """v3.2's run32 inside the v3.3 context. Returns v3.2's result dict plus R["v33ctx"]."""
    campaigns = [campaign] if isinstance(campaign, (str, Path)) else list(campaign)
    present = epochs_present(campaigns, system) if system == "teastore" else []
    with _v33_wrapped(bool(present)):
        R = v32.run32(campaign, system=system, validation_dirs=validation_dirs, reference=reference, blocks=blocks,
                      split=split, test_blocks=test_blocks)
    R["_v33ctx"] = {"system": system, "teastoreOffPath": present}
    return R


def _v33_block(R):
    ctx = R["_v33ctx"]
    system = ctx["system"]
    with _v33_wrapped(bool(ctx["teastoreOffPath"])):
        lanes = lanes_block(R, system)
    admitted = sorted(e for e, p in ADDED_PROFILES.items() if p["system"] == system) if ADMIT_NEW_EPOCHS else []
    return {"version": VERSION, "label": LABEL, "system": system,
            "epochsAddedByV33": admitted,
            "epochsRead": R["v32"]["epochsRead"],
            "teastorePauseRegimes": TS_MODEL["pauseRegimes"] if ctx["teastoreOffPath"] else None,
            "teastoreP1P2Regime": TS_MODEL["p1p2Regime"] if ctx["teastoreOffPath"] else None,
            "lanes": lanes,
            "switches": {k: globals()[k] for k in SWITCHES},
            "parametersV33Sha256": _sha(PARAMETERS_V33),
            "parametersV33": {n: REGISTRY33[n]["value"] for n in sorted(PARAMS_USED33)}}


def build_json33(R):
    with _v33_wrapped(bool(R["_v33ctx"]["teastoreOffPath"])):
        J = v32.build_json32(R)
    J["v32ScriptSha256"] = J["scriptSha256"]
    J["version"], J["label"] = VERSION, LABEL
    J["script"] = "research/detection-time/sweep_analysis_v3_3.py"
    J["scriptSha256"] = _sha(__file__)
    J["v33"] = _v33_block(R)
    return J


def _fmt_t(x):
    return v24.DASH if x is None else "%.1f s" % x


def render33(R, J):
    with _v33_wrapped(bool(R["_v33ctx"]["teastoreOffPath"])):
        md = v32.render32(R, J)
    v = J["v33"]
    w = ["", "## v3.3 additions (campaign F, TeaStore off-path epoch; admission and lanes)", "",
         "Frozen v3.3 (FREEZE_V33_20261014.md); harness names pinned at 715d57b (OTel F) and f74b29b (teastore-offpath-v1). Scope: instance; a report, no mechanism claim.", "",
         "- Epochs added by v3.3: %s." % (", ".join("`%s`" % e for e in v["epochsAddedByV33"]) or v24.DASH),
         "- TeaStore pause regimes (explicit targets): %s; P1 and P2 declared for `%s`." % (
             v["teastorePauseRegimes"] or v24.DASH, v["teastoreP1P2Regime"] or v24.DASH),
         "- Lane rule: " + v["lanes"]["rule"], ""]
    for regime, x in v["lanes"]["regimes"].items():
        w += ["### Lanes, `%s` (target `%s`)" % (regime, x["target"]), "",
              "| rate | lane | episodes with collected sensors | with a counted fire | earliest counted fire, median [min, max] "
              "| with a by-construction fire (%s) | earliest by-construction fire, median [min, max] |" % BC_LABEL,
              "|---|---|---|---|---|---|---|"]
        for rate, per in x["byRate"].items():
            for lane in LANES:
                s = per[lane]
                if s.get("note"):
                    w.append("| %s | %s | %s | %s | %s (%s) | %s | %s |" % (rate, lane, v24.DASH, v24.DASH, v24.DASH,
                                                                          s["note"], v24.DASH, v24.DASH))
                    continue
                w.append("| %s | %s | %d of %d | %s | %s [%s, %s] | %s | %s [%s, %s] |" % (
                    rate, lane, s["withCollectedSensors"], s["episodes"],
                    v24.DASH if not s["withCollectedSensors"] else "%d of %d" % (s["withFire"], s["withCollectedSensors"]),
                    _fmt_t(s["ttdMedian"]), _fmt_t(s["ttdMin"]), _fmt_t(s["ttdMax"]),
                    v24.DASH if not s["withCollectedSensors"] else "%d of %d" % (s["withByConstructionFire"],
                                                                                 s["withCollectedSensors"]),
                    _fmt_t(s["byConstructionTtdMedian"]), _fmt_t(s["byConstructionTtdMin"]),
                    _fmt_t(s["byConstructionTtdMax"])))
        w.append("")
    return md + "\n".join(w) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory/ies of one system (pooled, H1)")
    ap.add_argument("--system", default="otel", choices=v24.SYSTEMS)
    ap.add_argument("--out", required=True, help="NEW output directory; refused if it exists")
    ap.add_argument("--validation", nargs="+", default=[], help="no-fault campaign directory/ies, never pooled")
    ap.add_argument("--blocks", nargs="+", type=int, default=None,
                    help="block numbers of a campaign-E-role epoch to read (V32_BLOCK_SELECT_RULE); default all")
    ap.add_argument("--test-blocks", nargs="+", type=int, default=None,
                    help="blocks held out of every fit and calibration (decision 102); the registry's test blocks")
    ap.add_argument("--split", default=None, help="the declared split file (its sha256 is recorded)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    camp = [Path(x) for x in a.campaign]
    R = run33(camp[0] if len(camp) == 1 else camp, system=a.system, validation_dirs=[Path(x) for x in a.validation],
              blocks=set(a.blocks) if a.blocks is not None else None, split=a.split,
              test_blocks=set(a.test_blocks) if a.test_blocks is not None else None)
    with v24.use_system(a.system):
        v31.finish(R)
    J = build_json33(R)
    out.mkdir(parents=True)
    v31.write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    v31.write_new(out / OUT_MD, render33(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
