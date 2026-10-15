#!/usr/bin/env python3
"""Traffic-sweep analysis v3.2: v3.1's reader and rules (sweep_analysis_v3.py, frozen 7ec9f28 + decision 92, imported and
never edited) extended for campaign E (research/traffic-sweep/BUDGET_E.md, ec4b9fa, step 3): a multi-route request
ledger, the new off-path epochs, off-path fault classes and a block split inside one campaign.

    uv run python research/detection-time/sweep_analysis_v3_2.py <campaign dir> [<campaign dir> ...] --system otel \
        --out <new dir> [--blocks 1 2 3] [--split <split.json>] [--validation <no-fault campaign dir> ...]

STATUS: FROZEN by digest (research/protocol/FREEZE_V32_20261013.md) before any campaign-E cell was read, after two
same-provider adversarial reviews; the epoch, ledger and route entries of research/protocol/parameters_v3_2.json are
re-pinned at harness 6a5c2a9 (V32_EPOCH_PROFILES, V32_LEDGER_SCHEMAS, V32_ROUTE_MODEL_OTEL, all active). The only
off-path cells read while it was written are the off-path pilot v2's (a shakedown). Every claim below is scope
**method**; no number is produced by this file.

ENGINEERING CHOICE (recorded): like v3.1 over v2.4, v3.2 is a module of its own that imports v3.1 (`import
sweep_analysis_v3 as v31`) and v2.4 and rebinds a few of their module-level names for the duration of one run (a context
manager restores every one), because the frozen files must stay byte-identical (v3.1 pins its scriptSha256 in celf_v3.py
and score_test_v3.py). A v3.2 readout therefore carries scriptSha256 of THIS file and v31ScriptSha256 of v3.1.

DEVIATIONS FROM v3.1, grouped as in research/protocol/DEVIATIONS_V2_TO_V3.md. A group not listed did not change. Each row
names its switch (flipped only by tests/test_sweep_analysis_v3_2.py, a planted defect each) and its registry entry.
  Group 1 calibration unit, criterion, honest counts: unchanged (per (sensor, rule), zero held-out alarms, nested counts).
  Group 2 level-rule thresholds: unchanged.
  Group 3 `absent` and `appear`: unchanged.
  Group 4 ledger, status taxonomy, P4 (V32_LEDGER_ANY_ROUTE_RULE, switch LEDGER_ANY_ROUTE; V32_ROUTE_MODEL_OTEL,
     switches OFFPATH_PATHS, ROUTE_EDGES, P1_P2_ONE_REGIME):
     4.1 the ledger E fires on any route (already so in v2.4/v3.1, which key the ledger by route; stated and tested here
         with a route other than the first). OTel's route is now each row's `route`, not the URL of the one request.
     4.2 off-path pause classes (fraud-pause-effect, accounting-pause-effect) are classes like the others: P4 and the
         placement score them; the ledger is expected not to detect them and is not assumed not to (a catch counts).
     4.3 own-sensor exclusion per class (decision 84), unchanged logic, tested on the two new targets.
     4.4 the affected path of an off-path target is declared (consumer + Kafka), not the call-graph closure (an async
         consumer has no synchronous caller); the declared SYNCHRONOUS call graph of the upstream mix is added to the
         project map's 5-service graph, only when a v3.2-epoch cell is read (the async Kafka edges are not walked); the ledger's by-construction flag keeps v2.4's rule (target on the
         synchronous route, so an off-path pause is never flagged).
     4.5 P1 and P2 stay declared for ONE regime, the request-path pause (V32_ROUTE_MODEL_OTEL.p1p2Regime): v2.4's
         pause_regime() asserts one stopping regime per system and would stop on three.
  Group 5 false-alarm reporting and the fresh check: unchanged.
  Group 6 pooling, campaign keys, quiet time (V32_BLOCK_SELECT_RULE, switch BLOCK_SELECT; ONE_NEW_EPOCH):
     6.1 cells of a campaign-E epoch can be selected by block number (`--blocks`), outcome-blind (only the receipt's
         runKey is read of an excluded cell); the readout records the selection, the excluded cells and the split file's
         sha256. This is what makes a training readout and a full readout of ONE campaign (decision 95).
     6.2 two different new epochs in one run are refused (their block numbers would collide in the (harness, block)
         fold key of celf_v3); legacy-epoch FAULT cells beside a new epoch are refused too (NEW_EPOCH_ALONE: their
         episodes would enter the placement's training); legacy no-fault cells may be pooled.
     6.3 the selection also applies to --validation campaigns (VALIDATION_SELECTED), `--blocks` with no campaign-E cell
         read is refused (REQUIRE_E_FOR_BLOCKS), and every readout episode carries its `studyEpoch` so that the
         placement and the scorer can check that the recorded blocks describe the episodes (independent review, F1/F5/F6).
  Group 7 onset (H4) timing and carrier: unchanged (the off-path epochs are read as campaign-B-shaped: harness tag `B`,
     decision 69's H4 record, V3_B_RECORD_KEYS unchanged, so a record of another key set stops the run).
  Group 8 schema and epoch admission (V32_EPOCH_PROFILES, V32_LEDGER_SCHEMAS; switches ADMIT_OFFPATH_EPOCHS,
     EPOCH_SHAPE_CHECK, MULTI_ROUTE_LEDGER):
     8.1 the epochs `otel-offpath-pilot-v1` and the campaign-E epoch (a registry parameter) are admitted explicitly, as
         campaign-B-shaped, with their regimes; any other epoch name stops the run (UnknownSchema), as before.
     8.2 the multi-route ledger kind is read only in the epochs that declare it and the legacy single-route kind only in
         the legacy epochs; a ledger of another kind or key set, or a row whose route is not a key of the ledger's `routeCounts`,
         stops the run. A regime outside its epoch's declared regimes stops the run (a legacy epoch's cell named
         `fraud-pause-effect` is a shape mismatch, not an unknown class to be silently scored).
  Group 9 bookkeeping and display: the readout carries a `v32` block (epochs admitted, routes, per-route exposure, declared
     edges not observed, split); the markdown gets a v3.2 section.
  Group 10 placement and test scoring: celf_v3_2.py (tiered budgets) and score_test_v3_2.py (block-split scorer).
  Decision 102 (V32_TRAIN_ONLY_CALIBRATION_RULE; TRAIN_ONLY_CALIBRATION, HELD_OUT_REQUIRED), groups 1 and 6: with
     `--test-blocks` (= V32_E_SPLIT.test) the cells of those blocks are held out of every fit and calibration (pooled
     fits, per-(sensor, rule) calibration, leave-one-cell-out folds, route-graph context, validation fit) and scored as
     episodes with the training-calibrated detectors, applied unchanged. The readout tags each episode `heldOut`.
     The v2.4 reference row (`reference=True`, the default) is routed through the same train-only filter: its
     leave-one-out fits (v24.loco_fits) and its operating point (v24.operating_point) see the training cells only
     (review finding F2; the readout records it in v32.referenceFit).
  Decisions 99-101 (placement and scorer): see celf_v3_2.py (cumulative runtime tier) and score_test_v3_2.py (pass rule).
  P1/P2 and `dependsOn` rows (V32_P1P2_DEPENDS_RULE, switch P1P2_EXCLUDE_DEPENDS), group 4: rows that wait on a
     predecessor are excluded from P1 and P2 only and listed per cell (v32.dependsOnRows); kept for detection.
  Exposure (V32_EXPOSURE_RULE, switch PER_ROUTE_EXPOSURE): counted per route (requests started in the hold per route; a
     route's services from the no-fault traces of that route's requests); the pooled path of v2.4 is kept beside it.
"""
import argparse
import contextlib
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sweep_analysis_v3 as v31  # noqa: E402  v3.1 (frozen), never edited
import sweep_analysis_v2 as v24  # noqa: E402  v2.4 (frozen), never edited

dt, v1 = v24.dt, v24.v1

PARAMETERS_V32 = REPO / "research" / "protocol" / "parameters_v3_2.json"
VERSION = "3.2"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V3_2.md", "sweep_analysis_v3_2.json"
LABEL = "frozen v3.2 for campaign E (FREEZE_V32_20261013.md; harness names pinned at 6a5c2a9)"
LEGACY_LEDGER_KIND = "otel-demo-route-ledger-v1"


# =========================================================================== the v3.2 registry (decision 37)

def load_registry(path=PARAMETERS_V32):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY32 = load_registry()
PARAMS_USED32 = set()


def param32(name):
    PARAMS_USED32.add(name)
    return REGISTRY32[name]["value"]


EPOCH_PROFILES = param32("V32_EPOCH_PROFILES")
LEDGER_SCHEMAS = param32("V32_LEDGER_SCHEMAS")
ROUTE_MODEL = param32("V32_ROUTE_MODEL_OTEL")
SYNC_EDGES = {tuple(e.split("->")) for e in ROUTE_MODEL["edges"]}
ASYNC_EDGES = {tuple(e.split("->")) for e in ROUTE_MODEL["asyncEdges"]}
RULES_TEXT32 = {n: param32(n) for n in ("V32_LEDGER_ANY_ROUTE_RULE", "V32_EXPOSURE_RULE", "V32_OWN_PER_CLASS_RULE",
                                        "V32_BLOCK_SELECT_RULE", "V32_TRAIN_ONLY_CALIBRATION_RULE",
                                        "V32_P1P2_DEPENDS_RULE")}
E_SPLIT = param32("V32_E_SPLIT")

# Switches flipped only by tests/test_sweep_analysis_v3_2.py (planted defects); the analysis never changes them.
ADMIT_OFFPATH_EPOCHS = True   # 8.1: the profile epochs are admitted (False: they are unknown epochs and stop the run)
EPOCH_SHAPE_CHECK = True      # 8.2: ledger kind and regime must match the cell's epoch (False: any mix is read)
MULTI_ROUTE_LEDGER = True     # 8.2/4.1: a row's own route (False: every row gets the first declared route)
LEDGER_ANY_ROUTE = True       # 4.1: E fires on any route (False: only the first route's ledger streams count)
OFFPATH_PATHS = True          # 4.4: declared affected path of an off-path target (False: {target} only)
ROUTE_EDGES = True            # 4.4: the declared call graph is added to the project map's (False: the map only)
P1_P2_ONE_REGIME = True       # 4.5: P1 and P2 are declared for the request-path pause (False: v2.4's assertion)
BLOCK_SELECT = True           # 6.1: `--blocks` selects E cells by block number (False: every cell is read)
ONE_NEW_EPOCH = True          # 6.2: two new epochs in one run are refused (False: pooled)
NEW_EPOCH_ALONE = True        # 6.2: legacy-epoch FAULT cells beside a new epoch are refused (False: pooled)
VALIDATION_SELECTED = True    # 6.1: the block selection applies to --validation campaigns too (False: only the first read)
REQUIRE_E_FOR_BLOCKS = True   # 6.1: --blocks with no campaign-E cell read is refused (False: a label the filter never used)
PER_ROUTE_EXPOSURE = True     # exposure per route (False: v2.4's pooled path only)
TRAIN_ONLY_CALIBRATION = True # decision 102: held-out (test-block) cells never enter a fit or a calibration (False: they do)
HELD_OUT_REQUIRED = True      # decision 102: a registry test block read without the heldOut flag is refused (False: read)
P1P2_EXCLUDE_DEPENDS = True   # dependsOn rows are left out of P1 and P2 only, kept for detection (False: used by P1/P2)


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def new_epochs():
    return sorted(EPOCH_PROFILES)


def e_epochs():
    return sorted(e for e, p in EPOCH_PROFILES.items() if p.get("role") == "campaign-E")


def legacy_regimes():
    """The regimes of the legacy OTel epochs (v2.4's registry entry, before any v3.2 rebinding)."""
    prof = v24.REGISTRY["SYSTEM_OTEL"]["value"]
    return {prof["noFaultRegime"], *prof["faultRegimes"]}


def profile_regimes(profile):
    return {profile["noFaultRegime"], *profile["faultRegimes"]}


# =========================================================================== multi-route ledger (group 8, row 4.1)

class MultiLedger(dict):
    """A multi-route request ledger rewritten in v1's shape (so v2.4's reader and its checks run on it unchanged), with
    each row's route and task kept aside by row index."""

    routes_by_seq = ()
    tasks_by_seq = ()
    declared_routes = ()
    depends = frozenset()


def _receipt_epoch(path):
    try:
        rc = _ORIG["read_json"](Path(path).parent / "receipt.json")
    except (OSError, ValueError):
        return None, None
    rk = rc.get("runKey") or {}
    return rk.get("studyEpoch"), rk.get("regime")


def _strict(obj, keys, where):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise v24.UnknownSchema("%s: keys %s, the pinned v3.2 schema is %s" % (
            where, sorted(obj) if isinstance(obj, dict) else type(obj).__name__, sorted(keys)))


def check_multi_ledger(doc, where):
    """V32_LEDGER_SCHEMAS: the key sets and the route declaration (the keys of `routeCounts`); a violation stops the run."""
    sch = LEDGER_SCHEMAS.get(doc.get("kind"))
    if sch is None:
        raise v24.UnknownSchema("%s: ledger kind %r is not a pinned v3.2 kind (%s)" % (
            where, doc.get("kind"), sorted(LEDGER_SCHEMAS)))
    _strict(doc, sch["keys"], where + " request-ledger.json")
    if doc.get("schemaVersion") != sch["schemaVersion"]:
        raise v24.UnknownSchema("%s: schemaVersion %r, pinned %r" % (where, doc.get("schemaVersion"),
                                                                       sch["schemaVersion"]))
    counts = doc[sch["routesFromKey"]]
    if not (isinstance(counts, dict) and counts and all(isinstance(r, str) and r for r in counts)):
        raise v24.UnknownSchema("%s: `%s` must be a non-empty object keyed by route id" % (where, sch["routesFromKey"]))
    routes = sorted(counts)
    for i, q in enumerate(doc["requests"]):
        _strict(q, sch["rowKeys"], "%s request-ledger.json row %d" % (where, i))
        if q[sch["routeKey"]] not in counts:
            raise v24.UnknownSchema("%s: row %d route %r is not in the ledger's declared routes %s" % (
                where, i, q[sch["routeKey"]], routes))
    return sch


def to_legacy(doc, sch):
    """The v1-shaped ledger v2.4's reader checks and reads (the mix keys dropped; url is the base, never read as a route)."""
    out = MultiLedger({k: v for k, v in doc.items() if k not in sch["extraTopKeys"]})
    out["kind"] = LEGACY_LEDGER_KIND
    out["requests"] = [{k: v for k, v in q.items() if k not in sch["extraRowKeys"]} for q in doc["requests"]]
    routes = sorted(doc[sch["routesFromKey"]])
    first = routes[0]
    out.routes_by_seq = [q[sch["routeKey"]] if MULTI_ROUTE_LEDGER else first for q in doc["requests"]]
    out.tasks_by_seq = [q[sch["taskKey"]] for q in doc["requests"]]
    out.declared_routes = routes
    out.depends = frozenset(i for i, q in enumerate(doc["requests"]) if q.get("dependsOn") is not None)
    return out


_ORIG = {"read_json": v24._read_json, "otel_ledger": v24.otel_ledger,    # the frozen functions, captured at import,
         "load_or_invalid": v24.otel_load_or_invalid, "make_ctx": v24.make_ctx,   # before any rebinding of them
         "path_of": v1.path_of, "pause_regime": v24.pause_regime, "eval_episode3": v31.eval_episode3,
         "exposure": v24.exposure, "fits_for3": v31.fits_for3, "loco_fits3": v31.loco_fits3,
         "pair_fits": v31.pair_fits, "calibrate": v31.calibrate, "validation": v31.validation,
         "predictions_p1": v24.predictions_p1, "predictions_p2": v24.predictions_p2,
         "loco_fits": v24.loco_fits, "operating_point": v24.operating_point}
_LEDGERS = {}         # str(request-ledger.json path) -> MultiLedger, for the cell loader to pick up


def read_json32(path):
    doc = _ORIG["read_json"](path)
    p = Path(path)
    if p.name != "request-ledger.json" or not isinstance(doc, dict):
        return doc
    epoch, _ = _receipt_epoch(p)
    prof = EPOCH_PROFILES.get(epoch)
    want = prof["ledgerKind"] if prof else LEGACY_LEDGER_KIND
    if EPOCH_SHAPE_CHECK and doc.get("kind") != want:
        raise v24.UnknownSchema("%s: ledger kind %r in epoch %r, which declares %r" % (p, doc.get("kind"), epoch, want))
    if doc.get("kind") == LEGACY_LEDGER_KIND:
        return doc
    sch = check_multi_ledger(doc, str(p))
    ml = to_legacy(doc, sch)
    _LEDGERS[str(p)] = ml
    return ml


def otel_ledger32(led, stats):
    out = _ORIG["otel_ledger"](led, stats)
    if isinstance(led, MultiLedger):
        reqs = [r._replace(route=led.routes_by_seq[r.seq]) for r in out[0]]
        return (reqs,) + tuple(out[1:])
    return out


def load_or_invalid32(d):
    """v2.4's OTel cell loader behind the epoch-shape check (8.2) and with the multi-route extras attached."""
    epoch, regime = _receipt_epoch(Path(d) / "request-ledger.json")
    if EPOCH_SHAPE_CHECK and regime is not None:
        prof = EPOCH_PROFILES.get(epoch)
        allowed = profile_regimes(prof) if prof else legacy_regimes()
        if regime not in allowed:
            raise v24.UnknownSchema("%s: regime %r is not a regime of epoch %r (%s)" % (d, regime, epoch,
                                                                                         sorted(allowed)))
    c = _ORIG["load_or_invalid"](d)
    ml = _LEDGERS.pop(str(Path(d) / "request-ledger.json"), None)
    if ml is not None and c.get("valid"):
        c["ledgerRoutes"] = list(ml.declared_routes)
        c["ledgerTasks"] = {i: t for i, t in enumerate(ml.tasks_by_seq)}
        c["ledgerRouteBySeq"] = {i: r for i, r in enumerate(ml.routes_by_seq)}
        c["ledgerDepends"] = set(ml.depends)
        if c.get("timing") is not None:
            c["timing"]["route"] = ",".join(ml.declared_routes)
            c["timing"]["routes"] = list(ml.declared_routes)
    return c


# =========================================================================== paths and graph (group 4, rows 4.4-4.5)

def _train(cells):
    """Decision 102: the cells that may inform a fit, a calibration or the route context (held-out cells never)."""
    return [c for c in cells if not c.get("heldOut")] if TRAIN_ONLY_CALIBRATION else list(cells)


def fits_for3_32(cells):
    return _ORIG["fits_for3"](_train(cells))


def loco_fits3_32(cells):
    return _ORIG["loco_fits3"](_train(cells))


def loco_fits_reference_32(cells):
    """The v2.4 reference row's leave-one-quiet-cell-out fits (v3's `_run` calls v24.loco_fits on every cell): train-only."""
    return _ORIG["loco_fits"](_train(cells))


def operating_point_32(cells, share, fits=None, ctx=None):
    """The v2.4 reference row's family operating point (v3's `_run`, `reference=True`): its fits, its quiet cells and its
    hours come from the training cells only, so a held-out (test-block) cell never informs the reference (review finding
    F2). The cell objects are the same ones, so the fits keyed by id(cell) still match."""
    return _ORIG["operating_point"](_train(cells), share, fits, ctx)


def pair_fits_32(cells, rate):
    return _ORIG["pair_fits"](_train(cells), rate)


def calibrate32(cells, *a, **k):
    return _ORIG["calibrate"](_train(cells), *a, **k)


def validation32(val_cells, cal, cells, fits_sc, share, sets):
    return _ORIG["validation"](val_cells, cal, _train(cells), fits_sc, share, sets)


def _without_depends(eps):
    out = []
    for e in eps:
        dep = e["_c"].get("ledgerDepends")
        if P1P2_EXCLUDE_DEPENDS and dep:
            e = dict(e, _c=dict(e["_c"], ledger=[r for r in e["_c"]["ledger"] if r.seq not in dep]))
        out.append(e)
    return out


def predictions_p1_32(eps):
    return _ORIG["predictions_p1"](_without_depends(eps))


def predictions_p2_32(eps):
    return _ORIG["predictions_p2"](_without_depends(eps))


def make_ctx32(cells):
    ctx = _ORIG["make_ctx"](_train(cells))
    if (ROUTE_EDGES and v24.SYSTEM == "otel" and any(c.get("studyEpoch") in EPOCH_PROFILES for c in cells)):
        ctx["edges"] = set(ctx["edges"]) | SYNC_EDGES        # the asynchronous Kafka edges stay out (no synchronous caller)
        ctx["onRoute"] = set(ctx["onRoute"]) | set(ROUTE_MODEL["syncServices"])
    return ctx


def path_of32(target, ctx):
    ap = ROUTE_MODEL["affectedPath"]
    if v24.SYSTEM == "otel" and target in ap:
        return set(ap[target]) if OFFPATH_PATHS else {target}
    return _ORIG["path_of"](target, ctx)


def pause_regime32():
    if P1_P2_ONE_REGIME and v24.SYSTEM == "otel" and EPOCH_PROFILES:
        return ROUTE_MODEL["p1p2Regime"]
    return _ORIG["pause_regime"]()


def eval_episode3_32(c, fit, calr, share, ws_logs):
    fires, unknown, straddle, moved_out = _ORIG["eval_episode3"](c, fit, calr, share, ws_logs)
    if not LEDGER_ANY_ROUTE:                    # planted defect: only the first route's ledger streams
        first = (c.get("ledgerRoutes") or sorted({r.route for r in c["ledger"]}))[0]
        fires = [f for f in fires if f["family"] != "E" or f["tok"] == first]
    return fires, unknown, straddle, moved_out


# =========================================================================== exposure per route

def exposure32(cells, eps):
    out = _ORIG["exposure"](cells, eps)
    if not PER_ROUTE_EXPOSURE:
        return out
    valid = [c for c in cells if c["valid"]]
    svc_of_route = defaultdict(set)
    for c in valid:
        if c["target"] is not None:
            continue
        route_of_tok = {r.token: r.route for r in c["ledger"] if r.token}
        for tok, services in (c.get("spanEnds") or {}).items():
            if tok in route_of_tok:
                svc_of_route[route_of_tok[tok]] |= set(services)
    routes = sorted({r.route for c in valid for r in c["ledger"]})
    stores = set(out["projection"].get("dataStoresByDependsOn") or [])
    per_ep, exposed_any = {}, set()
    for e in eps:
        c = e["_c"]
        n = Counter(r.route for r in c["ledger"] if e["onset"]["mono"] <= r.start <= e["end"]["mono"])
        exposed = set()
        for route, k in n.items():
            if k >= 1:
                exposed |= svc_of_route.get(route, set())
        if exposed:
            exposed |= stores
        per_ep[e["cell"]] = {"requestsStartedInWindowPerRoute": {r: n.get(r, 0) for r in routes},
                             "exposedServices": sorted(exposed)}
        exposed_any |= exposed
        out["episodes"][e["cell"]]["exposedServicesPooled"] = out["episodes"][e["cell"]]["exposedServices"]
        out["episodes"][e["cell"]]["exposedServices"] = sorted(exposed)
        out["episodes"][e["cell"]]["requestsStartedInWindowPerRoute"] = per_ep[e["cell"]][
            "requestsStartedInWindowPerRoute"]
    sensors = set()
    for c in valid:
        sensors |= {"%s:%s:%s" % k for k in c["prep"]}
    never = sorted(s for s in sensors if s.split(":")[1] not in exposed_any)
    out["neverExposedSensorsPooled"] = out.get("neverExposedSensors")
    out["neverExposedSensors"] = never
    out["neverExposedServices"] = sorted({s.split(":")[1] for s in never})
    out["perRoute"] = {"routes": routes, "servicesByRoute": {r: sorted(svc_of_route.get(r, ())) for r in routes},
                       "rule": RULES_TEXT32["V32_EXPOSURE_RULE"]}
    return out


# =========================================================================== reading: epochs, blocks

def _read_block(d):
    try:
        rc = _ORIG["read_json"](Path(d) / "receipt.json")
    except (OSError, ValueError):
        return None, None
    rk = rc.get("runKey") or {}
    return rk.get("studyEpoch"), rk.get("block")


class _Read:
    """State of one run: which call of find_and_load3 is the primary read (block selection applies there only)."""

    def __init__(self, blocks, test_blocks=None):
        self.blocks, self.calls, self.excluded = blocks, 0, []
        self.test_blocks = set(test_blocks) if test_blocks is not None else None


def find_and_load32(campaigns):
    st = _STATE["read"]
    st.calls += 1
    find, load = v24.system_io()
    found, cells, seen = [], [], {}
    new_seen, e_seen = set(), False
    with v31.admit_b_epochs():
        for i, campaign in enumerate(campaigns):
            root, dirs = find(campaign)
            keep = []
            for d in dirs:
                epoch, block = _read_block(d)
                if epoch in EPOCH_PROFILES:
                    new_seen.add(epoch)
                e_seen = e_seen or epoch in e_epochs()
                if (BLOCK_SELECT and (st.calls == 1 or VALIDATION_SELECTED) and st.blocks is not None
                        and epoch in e_epochs() and block not in st.blocks):
                    st.excluded.append({"cell": v24.common.rel(d), "epoch": epoch, "block": block,
                                        "call": st.calls})
                    continue
                keep.append(d)
            found.append((root, keep))
            for d in keep:
                k = v31.pool_key(root, d)
                if k in seen:
                    raise SystemExit("cell %s given twice (campaigns %d and %d): pooling keys on (campaign, run path)"
                                     % (k, seen[k], i))
                seen[k] = i
                c = v31.load3(load, d)
                _epoch, _block = _read_block(d)
                c["heldOut"] = bool(_epoch in e_epochs() and st.test_blocks is not None and _block in st.test_blocks)
                if (HELD_OUT_REQUIRED and E_SPLIT["test"] is not None and _epoch in e_epochs()
                        and _block in E_SPLIT["test"] and not c["heldOut"]):
                    raise SystemExit("refusing: a cell of registry test block %s (V32_E_SPLIT) was read without "
                                     "--test-blocks: its data would calibrate the detectors that score it (decision "
                                     "102)" % _block)
                c["campaignIndex"] = i
                c["poolKey"] = k
                c["cellKey"] = ("%s :: %s" % k) if (v31.CELL_KEY_POOL and isinstance(k, tuple)) else c["cell"]
                cells.append(c)
    if ONE_NEW_EPOCH and len(new_seen) > 1:
        raise SystemExit("refusing: cells of %d different v3.2 epochs in one run (%s): their block numbers would "
                         "collide in the (harness, block) fold key; read each epoch on its own" % (
                             len(new_seen), ", ".join(sorted(new_seen))))
    if NEW_EPOCH_ALONE and new_seen:
        legacy = [c for c in cells if c["valid"] and c.get("target") is not None
                  and c.get("studyEpoch") not in EPOCH_PROFILES]
        if legacy:
            raise SystemExit("refusing: %d fault cell(s) of a legacy epoch (%s) beside the v3.2 epoch(s) %s: their "
                             "episodes would enter the placement's training and share block numbers with it; legacy "
                             "no-fault cells may be pooled, legacy fault cells may not" % (
                                 len(legacy), ", ".join(sorted({str(c.get("studyEpoch")) for c in legacy})),
                                 ", ".join(sorted(new_seen))))
    if REQUIRE_E_FOR_BLOCKS and st.blocks is not None and st.calls == 1 and not e_seen:
        raise SystemExit("refusing: --blocks given but no cell of a campaign-E epoch (%s) was found: the selection "
                         "would be a label the filter never applied" % ", ".join(e_epochs()))
    return found, cells


_STATE = {}


def check_split_args(blocks, test_blocks):
    """The registry split (decision 100) binds `--blocks` and `--test-blocks`; a test-block set must be a subset of the
    blocks read."""
    if test_blocks is not None and blocks is not None and not set(test_blocks) <= set(blocks):
        raise SystemExit("refusing: --test-blocks %s are not among the blocks read %s" % (sorted(test_blocks),
                                                                                         sorted(blocks)))
    if E_SPLIT["train"] is None:
        return
    allowed = set(E_SPLIT["train"]) | set(E_SPLIT["test"])
    if blocks is not None and not set(blocks) <= allowed:
        raise SystemExit("refusing: --blocks %s outside the registry split %s (V32_E_SPLIT)" % (sorted(blocks),
                                                                                              sorted(allowed)))
    if test_blocks is not None and sorted(test_blocks) != sorted(E_SPLIT["test"]):
        raise SystemExit("refusing: --test-blocks %s are not the registry test blocks %s (decision 100)" % (
            sorted(test_blocks), sorted(E_SPLIT["test"])))


@contextlib.contextmanager
def v32_context(system, rates=None, blocks=None, test_blocks=None):
    """Rebind the v3.1 / v2.4 names listed in the module docstring for one run; restore them all on exit."""
    saved = []

    def put(mod, name, val):
        saved.append((mod, name, getattr(mod, name)))
        setattr(mod, name, val)

    check_split_args(blocks, test_blocks)
    st = _Read(blocks, test_blocks)
    prev = _STATE.get("read")
    _STATE["read"] = st
    try:
        if system == "otel" and EPOCH_PROFILES:
            if ADMIT_OFFPATH_EPOCHS:
                b = {k: list(v) for k, v in v31.STUDY_EPOCHS_B.items()}
                b["otel"] = list(b.get("otel", [])) + [e for e in EPOCH_PROFILES if e not in b.get("otel", [])]
                put(v31, "STUDY_EPOCHS_B", b)
            put(v24, "_read_json", read_json32)
            put(v24, "otel_ledger", otel_ledger32)
            put(v24, "otel_load_or_invalid", load_or_invalid32)
            put(v24, "make_ctx", make_ctx32)
            put(v1, "path_of", path_of32)
            put(v24, "pause_regime", pause_regime32)
            put(v31, "eval_episode3", eval_episode3_32)
            put(v24, "exposure", exposure32)
            put(v24, "predictions_p1", predictions_p1_32)
            put(v24, "predictions_p2", predictions_p2_32)
            put(v31, "fits_for3", fits_for3_32)
            put(v31, "loco_fits3", loco_fits3_32)
            put(v24, "loco_fits", loco_fits_reference_32)             # F2: the v2.4 reference fit is train-only too
            put(v24, "operating_point", operating_point_32)
            put(v31, "pair_fits", pair_fits_32)
            put(v31, "calibrate", calibrate32)
            put(v31, "validation", validation32)
            regimes, targets = list(v24.FAULT_REGIMES), dict(v24.FAULT_TARGETS)
            for prof in EPOCH_PROFILES.values():
                for r, (svc, kind) in prof["faultRegimes"].items():
                    if r not in regimes:
                        regimes.append(r)
                    targets[r] = (svc, kind)
            put(v24, "FAULT_REGIMES", tuple(regimes))
            put(v24, "FAULT_TARGETS", targets)
        if rates:
            put(v24, "RATES", tuple(sorted(set(v24.RATES) | set(rates), reverse=True)))
        put(v31, "find_and_load3", find_and_load32)
        yield st
    finally:
        for mod, name, val in reversed(saved):
            setattr(mod, name, val)
        _STATE["read"] = prev


# =========================================================================== whole run

def run32(campaign, system="otel", validation_dirs=(), reference=True, blocks=None, split=None, test_blocks=None):
    """v3.1's run with the v3.2 context. blocks: block numbers of the E epochs to read (None: all). split: the split
    file's path (sha256 recorded). Returns v3.1's result dict plus R["v32"]."""
    campaigns = [campaign] if isinstance(campaign, (str, Path)) else list(campaign)
    with v24.use_system(system):
        rates = _rates_of(campaigns, system)
        with v32_context(system, rates, blocks, test_blocks) as st:
            R = v31._run(campaign, list(validation_dirs), reference)
            R["v32"] = _v32_block(R, st, blocks, split, rates)
    R["_v32ctx"] = {"system": system, "rates": rates, "blocks": blocks, "testBlocks": test_blocks}
    return R


def _rates_of(campaigns, system):
    """The rates in the campaigns' receipts (so that P4 and the tables cover a rate outside v2.4's grid)."""
    out = set()
    if system != "otel":
        return out
    for camp in campaigns:
        for rp in Path(camp).glob("**/receipt.json"):
            try:
                rk = json.loads(rp.read_text()).get("runKey") or {}
            except (OSError, ValueError):
                continue
            if rk.get("studyEpoch") in EPOCH_PROFILES and rk.get("requestsPerSecond") is not None:
                out.add(float(rk["requestsPerSecond"]))
    return out


def _v32_block(R, st, blocks, split, rates):
    cells = [c for c in R["cells"] if c["valid"]]
    declared = SYNC_EDGES | ASYNC_EDGES
    ctx_edges = set(R["ctx"]["edges"])
    observed = set()
    for c in cells:
        if c["target"] is None:
            observed |= set(c.get("spanEdges") or ())
    epochs = Counter(c.get("studyEpoch") for c in R["cells"])
    routes = sorted({r.route for c in R["cells"] if c["valid"] for r in c["ledger"]})
    return {
        "version": VERSION, "label": LABEL,
        "epochsRead": dict(sorted((str(k), v) for k, v in epochs.items())),
        "epochsAdmittedExplicitly": new_epochs() if ADMIT_OFFPATH_EPOCHS else [],
        "ledgerRoutes": routes,
        "heldOutCells": sorted(c.get("cellKey", c["cell"]) for c in R["cells"] if c.get("heldOut")),
        "dependsOnRows": {c.get("cellKey", c["cell"]): len(c["ledgerDepends"]) for c in R["cells"]
                          if c.get("valid") and c.get("ledgerDepends")},
        "blockSelection": {"blocks": sorted(blocks) if blocks is not None else None,
                           "testBlocks": sorted(st.test_blocks) if st.test_blocks is not None else None,
                           "applies": e_epochs(), "excludedCells": list(st.excluded),
                           "excludedCount": len(st.excluded),
                           "splitSha256": _sha(split) if split else None},
        "ratesAddedToGrid": sorted(rates), "asyncEdgesDeclared": sorted("%s->%s" % e for e in ASYNC_EDGES),
        "edgesObservedNotDeclared": sorted("%s->%s" % e for e in observed - declared - ctx_edges),
        "edgesDeclaredNotObserved": sorted("%s->%s" % e for e in declared - observed) if observed else None,
        "rules": RULES_TEXT32,
        "offPathClasses": {r: svc for p in EPOCH_PROFILES.values() for r, (svc, k) in p["faultRegimes"].items()
                           if svc in ROUTE_MODEL["affectedPath"]},
        "referenceFit": ("train-only: v2.4's reference operating point and its leave-one-out fits are computed on the "
                         "training cells (held-out test-block cells excluded; review finding F2)") if TRAIN_ONLY_CALIBRATION
                        else "ALL cells, held-out ones included (TRAIN_ONLY_CALIBRATION off: planted)",
        "parametersV32Sha256": _sha(PARAMETERS_V32),
        "parametersV32": {n: REGISTRY32[n]["value"] for n in sorted(PARAMS_USED32)},
    }


def build_json32(R):
    ctx = R["_v32ctx"]
    with v24.use_system(ctx["system"]), v32_context(ctx["system"], ctx["rates"], ctx["blocks"], ctx["testBlocks"]):
        J = v31._build_json(R)         # not build_json: that re-enters use_system and drops the extra regimes
    epoch_of = {c.get("cellKey", c["cell"]): c.get("studyEpoch") for c in R["cells"]}
    held = {c.get("cellKey", c["cell"]): bool(c.get("heldOut")) for c in R["cells"]}
    for e in J["episodes"]:
        e["studyEpoch"] = epoch_of.get(e["cell"])
        e["heldOut"] = held.get(e["cell"], False)
    J["version"], J["label"] = VERSION, LABEL
    J["script"] = "research/detection-time/sweep_analysis_v3_2.py"
    J["v31ScriptSha256"] = J["scriptSha256"]
    J["scriptSha256"] = _sha(__file__)
    J["v32"] = R["v32"]
    return J


def render32(R, J):
    ctx = R["_v32ctx"]
    with v24.use_system(ctx["system"]), v32_context(ctx["system"], ctx["rates"], ctx["blocks"], ctx["testBlocks"]):
        md = v31._render(R, J)
    v = R["v32"]
    w = ["", "## v3.2 additions (campaign E)", "",
         "Frozen v3.2 (FREEZE_V32_20261013.md); harness names pinned at 6a5c2a9 (V32_EPOCH_PROFILES, V32_LEDGER_SCHEMAS).", "",
         "- Epochs read: %s. Admitted explicitly: %s." % (
             ", ".join("`%s` %d" % kv for kv in v["epochsRead"].items()) or v24.DASH,
             ", ".join("`%s`" % e for e in v["epochsAdmittedExplicitly"]) or v24.DASH),
         "- Ledger routes: %s." % (", ".join("`%s`" % r for r in v["ledgerRoutes"]) or v24.DASH),
         "- Ledger rule: " + RULES_TEXT32["V32_LEDGER_ANY_ROUTE_RULE"],
         "- Block selection: %s; excluded by the split: %d cell(s); split file sha256 %s." % (
             v["blockSelection"]["blocks"] if v["blockSelection"]["blocks"] is not None else "all",
             v["blockSelection"]["excludedCount"], v["blockSelection"]["splitSha256"] or v24.DASH),
         "- Off-path classes scored like the others: %s." % (
             ", ".join("`%s` (%s)" % kv for kv in sorted(v["offPathClasses"].items())) or v24.DASH),
         "- Declared call-graph edges not observed in the no-fault traces: %s; observed edges not declared: %s." % (
             v["edgesDeclaredNotObserved"] if v["edgesDeclaredNotObserved"] is not None else v24.DASH,
             v["edgesObservedNotDeclared"]), ""]
    return md + "\n".join(w) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory/ies of one system (pooled, H1)")
    ap.add_argument("--system", default="otel", choices=v24.SYSTEMS)
    ap.add_argument("--out", required=True, help="NEW output directory; refused if it exists")
    ap.add_argument("--validation", nargs="+", default=[], help="no-fault campaign directory/ies, never pooled")
    ap.add_argument("--blocks", nargs="+", type=int, default=None,
                    help="block numbers of the campaign-E epoch to read (V32_BLOCK_SELECT_RULE); default all")
    ap.add_argument("--test-blocks", nargs="+", type=int, default=None,
                    help="blocks held out of every fit and calibration (decision 102); the registry's test blocks")
    ap.add_argument("--split", default=None, help="the declared split file (its sha256 is recorded)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    camp = [Path(x) for x in a.campaign]
    R = run32(camp[0] if len(camp) == 1 else camp, system=a.system, validation_dirs=[Path(x) for x in a.validation],
              blocks=set(a.blocks) if a.blocks is not None else None, split=a.split,
              test_blocks=set(a.test_blocks) if a.test_blocks is not None else None)
    with v24.use_system(a.system):
        v31.finish(R)
    J = build_json32(R)
    out.mkdir(parents=True)
    v31.write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    v31.write_new(out / OUT_MD, render32(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
