#!/usr/bin/env python3
"""Traffic-sweep analysis v3.4: v3.3's reader and rules (sweep_analysis_v3_3.py, frozen, imported and never edited) extended
for the Hotel off-path epoch `hotel-offpath-v1` (research/traffic-sweep/DECLARATION_HOTEL_OFFPATH.md, 4945293; budget
research/traffic-sweep/BUDGET_OVERNIGHT_20261014.md item 4). Admission and reporting only.

    uv run python research/detection-time/sweep_analysis_v3_4.py <campaign dir> [<campaign dir> ...] --system hotel|otel|teastore \
        --out <new dir> [--blocks 1 2 3] [--split <split.json>] [--test-blocks 4 5] [--validation <no-fault campaign dir> ...]

STATUS: FROZEN by digest (research/protocol/FREEZE_V34_20261015.md) before any cell of hotel-offpath-v1 was read (the run was
launched 2026-10-14 on fb14srv4, nothing fetched; the only real cells read while it was written are the committed Hotel
primary readout's inputs, as a regression, and synthetic fixtures). The registry's epoch, route-model and lane entries are
pinned at the Hotel harness commit 9ad0b98 and active. Every claim below is scope **method**; no number is produced by this file.

ENGINEERING CHOICE (recorded): like v3.3 over v3.2, v3.4 is a module of its own. It imports v3.3 (`import sweep_analysis_v3_3 as
v33`) and, for the duration of one run, replaces v3.3's `v33_context` by a wrapper (a context manager restores everything), adds
Hotel's lane rules to v3.3's `LANE_RULES`, and, only when the campaigns contain the off-path epoch (a pre-scan of
`cell-contract.json`, no cell is read) or a Hotel regime v2.4 does not know, rebinds v2.4's Hotel regime and target tables, its
cell loader, its pause-regime function and v3.1's cell finder. A v3.4 readout carries scriptSha256 of THIS file, v33ScriptSha256
of v3.3, v32ScriptSha256 of v3.2 and v31ScriptSha256 of v3.1, keeps v3.3's `v32` and `v33` blocks, and adds a `v34` block. A
readout of campaigns without the off-path epoch (every legacy Hotel readout, every OTel and TeaStore readout) is v3.3's, key by
key, except identity keys and the new block (and, for Hotel, v3.3 itself stops: it has no Hotel lane rules; v3.4 adds them).

DEVIATIONS FROM v3.3. A group not listed did not change (calibration, level rules, `absent`/`appear`, pass rule, cost model,
placement and scorer logic are v3.1's and v3.2's; the OTel and TeaStore rules are v3.3's). Each row names its switch (flipped only
by tests/test_sweep_analysis_v3_4.py, a planted defect each) and its registry entry (parameters_v3_4.json).
  Group 8 epoch admission (V34_EPOCH_PROFILES; switches ADMIT_HOTEL_OFFPATH, HOTEL_SHAPE_CHECK, HOTEL_TARGET_CHECK,
     HOTEL_DESIGN_CHECK, HOTEL_EPOCH_CHECK, HOTEL_EXTRA_ALONE, HOTEL_UNIQUE_CELLS):
     8.5 Hotel `hotel-offpath-v1` is admitted as the Hotel sweep layout (v2.4's loader reads it unchanged) with regimes
         no-fault-calibration, consul-pause-effect (target consul) and search-pause-effect (target search), rates 10 and 1, posture
         full, blocks 1..5. v2.4's Hotel loader gates nothing by epoch and drops a regime it does not know silently as a `not
         scored` cell (sweep_analysis_v2.py:921-922); v3.4 stops the run (UnknownSchema) on: a regime outside its epoch's declared
         set (and a legacy epoch's cell named for an off-path regime), a fault receipt that names another target (v2.4 listed that
         as `not scored`) or another fault kind than its regime declares (v2.4 checks only the target: a wrong kind with the
         right target was read as valid), a rate, block or posture outside the declared design,
         and a study epoch the registry does not know in a run that contains the off-path epoch. All of this is active only when
         the campaigns contain the off-path epoch or a Hotel regime outside the legacy set (so that a typo cannot be dropped
         silently); a readout of legacy Hotel campaigns is v3.3's engine untouched.
     8.6 legacy Hotel cells of ANY kind beside the off-path epoch are refused (HOTEL_EXTRA_ALONE; v3.2's NEW_EPOCH_ALONE for
         Hotel, whose epoch v3.2 reads from receipt.json and Hotel has none: the epoch here comes from cell-contract.json, and
         stricter than v3.2: no-fault cells too). A legacy no-fault cell never collected consul, and v3.1's calibration reads a
         fold without data as zero false alarms (sweep_analysis_v3.py:640-648), so pooling one would calibrate consul's sensors
         on absence (independent review, B1); the epoch is calibrated on its own no-fault cells. A (regime, rate, block) of the off-path epoch given twice (an attempt and its
         relaunch repeat the run IDs under different campaign directories, and the pooling guard keys on (campaign, run path))
         is refused (HOTEL_UNIQUE_CELLS): read ONE fetch of the epoch.
  Group 4 P1 and P2 (V34_ROUTE_MODEL_HOTEL; switch HOTEL_TWO_PAUSE, HOTEL_PATH_CHECK): v2.4's pause_regime() asserts exactly one
     stopping regime per system. With the off-path epoch Hotel has two; the reader accepts exactly the declared pair with the
     declared targets, declares P1 and P2 for the on-path control (search-pause-effect) and refuses any other set or target.
     The affected path of consul is {consul} (consul is not a node of the project map's Hotel graph); the reader checks that the
     path every consul episode actually used equals the declaration (HOTEL_PATH_CHECK) instead of assuming it. P2 and P4 'k of 4'
     verdicts read `—` at 5 episodes per (regime, rate) (v2.4's EPISODES_HOTEL = 4 is not rebound, as for OTel E/F and the
     TeaStore off-path epoch).
  Group 9 bookkeeping and display (V34_LANE_RULES, V34_REPORT_RULE; switch HOTEL_LANE_RULES): v3.3's lanes block gets Hotel's
     rules: own = the episode's target's sensors (for consul-pause: consul's), coordinator `—` and lag `—` (no service observes its
     peers' liveness, no queue; the negative control of DECLARATION_HOTEL_OFFPATH.md), by v3.3's own lane engine, unchanged. The
     v34 block adds, per consul-pause episode, the off-path manifestation record (receipt manifested, duringState.paused,
     outageObserved, docker pause and unpause events of service consul; the route outage is recorded, not required) and, per
     channel, how many valid cells of the epoch collected the extra service consul (`—` when none; absence is not zero).
     Reporting only: counting, placement and pass rule are unchanged.
  Extra collected service: no code. consul's docker-stats cpu and cgroup rows are read by the existing Hotel parser, which admits
     a service by its compose log prefix, its cpu.json `service` and its system-samples.json `services` (the compose prefix rule of
     sweep_analysis.py read_logs and sweep_analysis_v2.py read_logs, which v2.4 uses; parse_cell's log events are discarded), so consul has metric sensors without any change. consul has no spans (not one of the ten Jaeger-traced
     services). consul's LOG lines are another matter: the parser keeps only records of the three Hotel layouts (zerolog JSON,
     zerolog console, Go log `YYYY/MM/DD HH:MM:SS`; symptoms.HOTEL_LAYOUTS), and consul 1.13's native lines (`<ISO 8601> [INFO]
     agent: ...`, `==> ...`) match none of them (checked on synthetic lines written in the documented go-hclog format, test_consul_native_lines_match_no_hotel_layout: 0
     records, all `unparsed`; not on real consul output, the image is hashicorp/consul:1.13), so unless consul is run
     with a layout the reader knows it has NO log sensor. Adding a layout would change what may be measured (a preregistration
     decision, not an engineering default), so v3.4 does not; the v34 block reports the number of consul log lines in the cells
     and the number of log sensors, and says loudly when lines exist and no sensor does.
"""
import argparse
import contextlib
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sweep_analysis_v3_3 as v33  # noqa: E402  v3.3 (frozen), never edited

v32, v31, v24 = v33.v32, v33.v31, v33.v24
v1 = v24.v1

PARAMETERS_V34 = REPO / "research" / "protocol" / "parameters_v3_4.json"
VERSION = "3.4"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V3_4.md", "sweep_analysis_v3_4.json"
LABEL = "frozen v3.4 for the Hotel off-path epoch hotel-offpath-v1 (FREEZE_V34_20261015.md)"
DASH = v24.DASH


# =========================================================================== the v3.4 registry (decision 37)

def load_registry(path=PARAMETERS_V34):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY34 = load_registry()
PARAMS_USED34 = set()


def param34(name):
    PARAMS_USED34.add(name)
    return REGISTRY34[name]["value"]


HOTEL_PROFILES = param34("V34_EPOCH_PROFILES")
HOTEL_MODEL = param34("V34_ROUTE_MODEL_HOTEL")
LANE_RULES34 = param34("V34_LANE_RULES")
REPORT_RULE = param34("V34_REPORT_RULE")
assert not set(LANE_RULES34) & set(v33.LANE_RULES), "v3.4 adds lane rules; it does not redefine v3.3's"
assert all(p["system"] == "hotel" for p in HOTEL_PROFILES.values())
assert not set(HOTEL_PROFILES) & (set(v33.ADDED_PROFILES) | set(v33.V32_PROFILES)), "v3.4 adds epochs; it does not redefine"

# Switches flipped only by tests/test_sweep_analysis_v3_4.py (planted defects); the analysis never changes them.
ADMIT_HOTEL_OFFPATH = True    # 8.5: the off-path epoch is admitted (False: it is an unknown epoch, the run stops)
HOTEL_SHAPE_CHECK = True      # 8.5: a regime outside its epoch's declared regimes stops the run (False: v2.4's silent drop)
HOTEL_TARGET_CHECK = True     # 8.5: a fault receipt's target and kind must be its regime's declared ones (False: v2.4's not-scored)
HOTEL_DESIGN_CHECK = True     # 8.5: rate, block and posture must be the declared design's (False: read)
HOTEL_EPOCH_CHECK = True      # 8.5: an epoch the registry does not know, beside the off-path epoch, stops the run (False: read)
HOTEL_EXTRA_ALONE = True      # 8.6: legacy Hotel cells of any kind beside the off-path epoch are refused (False: pooled)
HOTEL_UNIQUE_CELLS = True     # 8.6: one (regime, rate, block) of the off-path epoch is read once (False: a relaunch pools silently)
HOTEL_TWO_PAUSE = True        # P1/P2: the declared pair of pause regimes is accepted (False: v2.4's one-regime assertion)
HOTEL_PATH_CHECK = True       # the declared affected path of consul equals the one the episodes used (False: not checked)
HOTEL_LANE_RULES = True       # lanes: Hotel's rules are registered (False: v3.3's KeyError, the run stops)
SWITCHES = ("ADMIT_HOTEL_OFFPATH", "HOTEL_SHAPE_CHECK", "HOTEL_TARGET_CHECK", "HOTEL_DESIGN_CHECK", "HOTEL_EPOCH_CHECK",
            "HOTEL_EXTRA_ALONE", "HOTEL_UNIQUE_CELLS", "HOTEL_TWO_PAUSE", "HOTEL_PATH_CHECK", "HOTEL_LANE_RULES")


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def legacy_regimes():
    return set(HOTEL_MODEL["legacyRegimes"])


def legacy_epochs():
    return sorted({e for p in HOTEL_PROFILES.values() for e in p["legacyHotelEpochs"]})


def profile_regimes(profile):
    return {profile["noFaultRegime"], *profile["faultRegimes"]}


def lane_rules():
    """v3.3's lane rules plus Hotel's (a copy; v3.3's table is never edited)."""
    merged = dict(v33.LANE_RULES)
    if HOTEL_LANE_RULES:
        merged.update(LANE_RULES34)
    return merged


# =========================================================================== Hotel: epoch shape, the pause pair, extra epochs

_ORIG_V33_CTX = v33.v33_context
_ORIG_HOTEL_LOAD = v24.load_or_invalid
_ORIG_PAUSE = v33._ORIG_PAUSE
_ACTIVE = {"hotel": False}      # the off-path epoch (or a Hotel regime outside the legacy set) is in the campaigns of this run


def _contract_run(d):
    """(studyEpoch, regime, rate, block, posture, timing rate) of a Hotel cell's contract, or Nones (unreadable contracts are
    v2.4's `not scored` cells, not ours to judge)."""
    try:
        ct = json.loads((Path(d) / "cell-contract.json").read_text())
    except (OSError, ValueError):
        return None, None, None, None, None, None
    if not isinstance(ct, dict):
        return None, None, None, None, None, None
    rk = ct.get("runKey") or {}
    timing = ct.get("timing") or {}
    return (rk.get("studyEpoch") or ct.get("studyEpoch"), rk.get("regime"), rk.get("requestsPerSecond"), rk.get("block"),
            rk.get("posture"), timing.get("requestsPerSecond"))


def hotel_scan(campaigns):
    """(epochs, regimes) as the cell contracts of the campaigns name them (Counters; contracts only, no cell is read)."""
    epochs, regimes = Counter(), Counter()
    for camp in campaigns:
        try:
            _root, dirs = v1.find_cells(camp)
        except SystemExit:
            continue                # the reader itself refuses a directory without runs/; not ours to repeat
        for d in dirs:
            epoch, regime = _contract_run(d)[:2]
            epochs[epoch] += 1
            regimes[regime] += 1
    return epochs, regimes


def offpath_epochs_in(epochs):
    names = set(HOTEL_PROFILES) if ADMIT_HOTEL_OFFPATH else set()
    return sorted(e for e in epochs if e in names)


def hotel_is_active(epochs, regimes):
    """The v3.4 Hotel rules apply when the off-path epoch is in the campaigns, or any contract names a regime outside the legacy
    Hotel set (v2.4 would drop it silently; here it reaches the loader, which refuses it)."""
    unknown = {r for r in regimes if isinstance(r, str)} - legacy_regimes()
    return bool(offpath_epochs_in(epochs)) or bool(unknown)


def load_hotel34(d):
    """v2.4's Hotel cell loader behind the v3.4 epoch-shape, target and design checks (8.5); the cell's studyEpoch is the
    contract's (Hotel has no receipt.json, so v3.1's load3 would leave it None)."""
    d = Path(d)
    epoch, regime, rate, block, posture, trate = _contract_run(d)
    if isinstance(regime, str):
        prof = HOTEL_PROFILES.get(epoch) if ADMIT_HOTEL_OFFPATH else None
        if prof is None and HOTEL_EPOCH_CHECK and epoch not in legacy_epochs():
            raise v24.UnknownSchema("%s: study epoch %r is not a Hotel epoch this reader knows (%s)" % (
                d, epoch, ", ".join(legacy_epochs() + sorted(HOTEL_PROFILES) if ADMIT_HOTEL_OFFPATH else legacy_epochs())))
        allowed = profile_regimes(prof) if prof else legacy_regimes()
        if HOTEL_SHAPE_CHECK and regime not in allowed:
            raise v24.UnknownSchema("%s: regime %r is not a regime of Hotel epoch %r (%s)" % (
                d, regime, epoch, sorted(allowed)))
        if prof is not None and HOTEL_DESIGN_CHECK:
            rates = {float(x) for x in prof["rates"]}
            for r in (rate, trate):
                if r is not None and float(r) not in rates:
                    raise v24.UnknownSchema("%s: rate %r is not a declared rate of Hotel epoch %r (%s)" % (
                        d, r, epoch, sorted(rates)))
            if not (isinstance(block, int) and 1 <= block <= prof["design"]["blocks"]):
                raise v24.UnknownSchema("%s: block %r is outside 1..%d of Hotel epoch %r" % (
                    d, block, prof["design"]["blocks"], epoch))
            if posture not in prof["postures"]:
                raise v24.UnknownSchema("%s: posture %r is not a declared posture of Hotel epoch %r (%s)" % (
                    d, posture, epoch, prof["postures"]))
        if prof is not None and HOTEL_TARGET_CHECK and regime in prof["faultRegimes"] and (d / "fault-receipt.json").exists():
            want, kind = prof["faultRegimes"][regime]
            try:
                fr = json.loads((d / "fault-receipt.json").read_text())
            except (OSError, ValueError):
                fr = None
            if isinstance(fr, dict) and (fr.get("targetService"), fr.get("faultKind")) != (want, kind):
                raise v24.UnknownSchema("%s: fault receipt names target %r, kind %r; regime %r of epoch %r declares %r, %r" % (
                    d, fr.get("targetService"), fr.get("faultKind"), regime, epoch, want, kind))
    c = _ORIG_HOTEL_LOAD(d)
    if c.get("valid"):
        c["studyEpoch"] = epoch
    return c


def pause_regime34():
    """The one regime P1 and P2 are declared for, with the Hotel pause pair accepted: the stopping regimes in force must be
    EXACTLY V34_ROUTE_MODEL_HOTEL.pauseRegimes with those targets (anything else stops the run)."""
    if not HOTEL_TWO_PAUSE:
        return _ORIG_PAUSE()
    got = {r: v24.FAULT_TARGETS[r][0] for r in v24.FAULT_REGIMES if v24.FAULT_TARGETS[r][1] in v24.dt.STOPPING}
    if got != HOTEL_MODEL["pauseRegimes"]:
        raise v24.UnknownSchema("Hotel stopping regimes %s are not the declared pair %s (V34_ROUTE_MODEL_HOTEL): P1 and P2 "
                                "are declared for the declared pair only" % (got, HOTEL_MODEL["pauseRegimes"]))
    return HOTEL_MODEL["p1p2Regime"]


def _wrap_find_and_load(prev):
    def find_and_load34(campaigns):
        found, cells = prev(campaigns)
        if HOTEL_UNIQUE_CELLS:
            seen = {}
            for i, (root, dirs) in enumerate(found):
                for d in dirs:
                    epoch, regime, rate, block = _contract_run(d)[:4]
                    if epoch in HOTEL_PROFILES:
                        key = (regime, float(rate) if rate is not None else None, block)
                        if key in seen:
                            raise SystemExit("refusing: cell %s of epoch %s is in campaigns %d and %d: a relaunch repeats the run "
                                             "IDs, the reader's pooling guard keys on (campaign, run path) and would pool both "
                                             "silently; read ONE fetch of the epoch" % (key, epoch, seen[key], i))
                        seen[key] = i
        if HOTEL_EXTRA_ALONE:
            legacy = [c for c in cells if c["valid"] and c.get("studyEpoch") not in HOTEL_PROFILES]
            if legacy:
                raise SystemExit("refusing: %d valid cell(s) of a legacy Hotel epoch (%s) beside the off-path epoch: a legacy "
                                 "cell never collected the extra service (consul), and v3.1's calibration reads a fold without "
                                 "data as zero false alarms (sweep_analysis_v3.py:640-648), so pooling it would calibrate "
                                 "consul's sensors on absence; legacy fault cells would also enter the pooled calibration "
                                 "under another design. Read the off-path epoch alone" % (
                                     len(legacy), ", ".join(sorted({str(c.get("studyEpoch")) for c in legacy}))))
        return found, cells
    return find_and_load34


@contextlib.contextmanager
def v34_context(system, rates=None, blocks=None, test_blocks=None):
    """v3.3's context and, for Hotel with the off-path epoch (or an unknown regime) in the campaigns, the epoch admission, the
    regime and target tables, the pause pair and the legacy-fault-cell refusal."""
    saved = []

    def put(mod, name, val):
        saved.append((mod, name, getattr(mod, name)))
        setattr(mod, name, val)

    with _ORIG_V33_CTX(system, rates, blocks, test_blocks) as st:
        try:                        # restored INSIDE v3.3's context: its own exit then restores what it rebound, in order
            if system == "hotel" and _ACTIVE["hotel"]:
                regimes, targets = list(v24.FAULT_REGIMES), dict(v24.FAULT_TARGETS)
                if ADMIT_HOTEL_OFFPATH:
                    for prof in HOTEL_PROFILES.values():
                        for r, (svc, kind) in prof["faultRegimes"].items():
                            if r not in regimes:
                                regimes.append(r)
                            targets[r] = (svc, kind)
                put(v24, "FAULT_REGIMES", tuple(regimes))
                put(v24, "FAULT_TARGETS", targets)
                put(v24, "load_or_invalid", load_hotel34)
                put(v24, "pause_regime", pause_regime34)
                put(v31, "find_and_load3", _wrap_find_and_load(v31.find_and_load3))
            yield st
        finally:
            for mod, name, val in reversed(saved):
                setattr(mod, name, val)


@contextlib.contextmanager
def _v34_wrapped(active_hotel):
    """v3.3's run33 / build_json33 / render33 call `v33_context` by module name (to put it in v3.2's slot): swap it for the v3.4
    wrapper, and give v3.3's lanes block Hotel's rules."""
    prev, prev_rules, prev_ctx = _ACTIVE["hotel"], v33.LANE_RULES, v33.v33_context
    _ACTIVE["hotel"] = bool(active_hotel)
    v33.v33_context = v34_context
    v33.LANE_RULES = lane_rules()
    try:
        yield
    finally:
        v33.v33_context = prev_ctx
        v33.LANE_RULES = prev_rules
        _ACTIVE["hotel"] = prev


# =========================================================================== whole run

def _check_paths(R):
    """HOTEL_PATH_CHECK: every episode of a declared off-path target used the declared affected path."""
    if not HOTEL_PATH_CHECK:
        return
    for e in R["results"]["primary"]["eps"]:
        want = HOTEL_MODEL["affectedPath"].get(e["target"])
        if want is not None and sorted(e["affectedPath"]) != sorted(want):
            raise v24.UnknownSchema("%s: the affected path used for target %r is %s; V34_ROUTE_MODEL_HOTEL declares %s" % (
                e["cell"], e["target"], sorted(e["affectedPath"]), sorted(want)))


def run34(campaign, system="hotel", validation_dirs=(), reference=True, blocks=None, split=None, test_blocks=None):
    """v3.3's run33 inside the v3.4 context. Returns v3.3's result dict plus R["_v34ctx"]."""
    campaigns = [campaign] if isinstance(campaign, (str, Path)) else list(campaign)
    if system == "hotel" and (split is not None or test_blocks is not None):
        raise SystemExit("refusing: --split and --test-blocks are not applied to Hotel (held-out status keys on receipt.json, "
                         "which Hotel cells do not have) and no registry split is declared for the off-path epoch")
    scan = campaigns + ([validation_dirs] if isinstance(validation_dirs, (str, Path)) else list(validation_dirs))
    epochs, regimes = hotel_scan(scan) if system == "hotel" else (Counter(), Counter())
    active = system == "hotel" and hotel_is_active(epochs, regimes)
    with _v34_wrapped(active):
        R = v33.run33(campaign, system=system, validation_dirs=validation_dirs, reference=reference, blocks=blocks,
                      split=split, test_blocks=test_blocks)
        if active:
            _check_paths(R)
    R["_v34ctx"] = {"system": system, "hotelActive": active,
                    "hotelOffPath": offpath_epochs_in(epochs) if active else []}
    return R


def _cell_path(c):
    p = Path(c["cell"])
    return p if p.is_absolute() else REPO / p


def manifestation(e):
    """The off-path manifestation record of one pause episode (V34_ROUTE_MODEL_HOTEL.manifestation); fields the cell does not
    carry are None (`—`), never False. Reporting only."""
    c = e["_c"]
    try:
        fr = json.loads((_cell_path(c) / "fault-receipt.json").read_text())
    except (OSError, ValueError):
        fr = {}
    ev = c.get("dockerEvents")
    acts = Counter(x.get("action") for x in (ev or ()) if x.get("service") == e["target"])
    row = {"cell": e["cell"], "rate": e["rate"], "block": e["block"], "target": e["target"],
           "manifested": fr.get("manifested"),
           "duringStatePaused": (fr.get("duringState") or {}).get("paused") if isinstance(fr.get("duringState"), dict) else None,
           "outageObserved": fr.get("outageObserved"),
           "dockerEventsRead": ev is not None,
           "dockerPauseEvents": acts.get("pause", 0) if ev is not None else None,
           "dockerUnpauseEvents": acts.get("unpause", 0) if ev is not None else None}
    known = [row["manifested"], row["duringStatePaused"], row["dockerPauseEvents"], row["dockerUnpauseEvents"]]
    row["offPathManifested"] = (None if any(x is None for x in known) else
                                bool(row["manifested"] is True and row["duringStatePaused"] is True
                                     and row["dockerPauseEvents"] >= 1 and row["dockerUnpauseEvents"] >= 1))
    return row


def collected_service(R, epoch, svc):
    """How many valid cells of `epoch` collected sensors of `svc`, per channel (the keys of the cell's `prep`)."""
    cells = [c for c in R["cells"] if c["valid"] and c.get("studyEpoch") == epoch]
    by_ch, any_cells, keys = Counter(), 0, set()
    log_lines, log_cells, log_missing = 0, 0, 0
    for c in cells:
        mine = [k for k in c["prep"] if k[1] == svc]
        any_cells += bool(mine)
        keys |= set(mine)
        for ch in {k[0] for k in mine}:
            by_ch[ch] += 1
        n = _log_lines_of(c, svc)
        if n is None:
            log_missing += 1
            continue
        log_lines += n
        log_cells += n > 0
    log_sensors = len({k for k in keys if k[0] == "log"})
    out = {"validCellsOfEpoch": len(cells), "cellsWithAnySensor": any_cells, "cellsByChannel": dict(sorted(by_ch.items())),
           "distinctSensors": len(keys), "collected": any_cells > 0,
           "logLinesInApplicationLog": log_lines, "cellsWithLogLines": log_cells, "cellsWithoutApplicationLog": log_missing,
           "logSensors": log_sensors}
    if log_lines and not log_sensors:
        out["logNote"] = ("%d log line(s) of `%s` are in application.log but no Hotel log layout (zerolog JSON, zerolog console, "
                          "Go log: sensor_rep/parsers/hotel.py, symptoms.HOTEL_LAYOUTS) parsed one: the service has no log "
                          "sensor, its log channel is a dead channel for this reader" % (log_lines, svc))
    return out


def _log_lines_of(c, svc):
    """Lines of the cell's application.log that carry the compose prefix `<svc>-<n> | ` (hotel.parse_cell's own prefix rule)."""
    try:
        text = (_cell_path(c) / "application.log").read_text(errors="replace")
    except OSError:
        return None
    n = 0
    for raw in text.splitlines():
        if " | " in raw and raw.split(" | ", 1)[0].strip().rsplit("-", 1)[0] == svc:
            n += 1
    return n


def _v34_block(R):
    ctx = R["_v34ctx"]
    system, active = ctx["system"], ctx["hotelActive"]
    present = ctx["hotelOffPath"]
    eps = R["results"]["primary"]["eps"]
    off = HOTEL_MODEL["offPathRegime"]
    blk = {"version": VERSION, "label": LABEL, "system": system, "hotelRulesActive": active,
           "epochsAddedByV34": sorted(HOTEL_PROFILES) if ADMIT_HOTEL_OFFPATH else [],
           "hotelOffPathEpochsRead": present,
           "hotelPauseRegimes": HOTEL_MODEL["pauseRegimes"] if active else None,
           "hotelP1P2Regime": HOTEL_MODEL["p1p2Regime"] if active else None,
           "affectedPathDeclared": HOTEL_MODEL["affectedPath"] if active else None,
           "extraCollectedServices": {}, "designCounts": {}, "manifestation": {"rule": None, "episodes": []},
           "switches": {k: globals()[k] for k in SWITCHES},
           "parametersV34Sha256": _sha(PARAMETERS_V34),
           "parametersV34": {n: REGISTRY34[n]["value"] for n in sorted(PARAMS_USED34)}}
    if active and present:
        for epoch in present:
            for svc in HOTEL_PROFILES[epoch]["extraCollectedServices"]:
                x = collected_service(R, epoch, svc)
                never = (R.get("exposure") or {}).get("neverExposedServices") or []
                x["listedAsNeverExposed"] = svc in never
                if x["listedAsNeverExposed"]:
                    x["exposureNote"] = ("v2.4's exposure rule (route services from the no-fault traces) lists `%s` among the "
                                         "never-exposed services although it is the fault target of its own regime: consul has no "
                                         "spans and is on no route, so that listing is the rule's, not a finding" % svc)
                blk["extraCollectedServices"]["%s:%s" % (epoch, svc)] = x
            prof = HOTEL_PROFILES[epoch]
            for regime in sorted(profile_regimes(prof)):
                for rate in prof["rates"]:
                    k = (regime, float(rate))
                    blk["designCounts"]["%s r%g" % (regime, rate)] = {
                        "declaredPerRegimeAndRate": prof["design"]["episodesPerRegimeAndRate"], "found": R["found"].get(k, 0),
                        "valid": R["valid"].get(k, 0)}
        blk["manifestation"] = {
            "rule": HOTEL_MODEL["manifestation"][off]["rule"],
            "episodes": [manifestation(e) for e in sorted(
                (x for x in eps if x["regime"] == off), key=lambda x: (-x["rate"],) + v24.episode_order(x))]}
    return blk


def build_json34(R):
    ctx = R["_v34ctx"]
    with _v34_wrapped(ctx["hotelActive"]):
        J = v33.build_json33(R)
        blk = _v34_block(R)
    J["v33ScriptSha256"] = J["scriptSha256"]
    J["version"], J["label"] = VERSION, LABEL
    J["script"] = "research/detection-time/sweep_analysis_v3_4.py"
    J["scriptSha256"] = _sha(__file__)
    J["v34"] = blk
    return J


def render34(R, J):
    ctx = R["_v34ctx"]
    with _v34_wrapped(ctx["hotelActive"]):
        md = v33.render33(R, J)
    v = J["v34"]
    w = ["", "## v3.4 additions (Hotel off-path epoch; admission and lanes)", "",
         "Frozen v3.4 (FREEZE_V34_20261015.md); harness names pinned at Hotel 9ad0b98. Scope: instance; a report, no mechanism claim.",
         "",
         "- Epochs added by v3.4: %s." % (", ".join("`%s`" % e for e in v["epochsAddedByV34"]) or DASH),
         "- Hotel off-path epoch read: %s; Hotel rules active: %s." % (
             ", ".join("`%s`" % e for e in v["hotelOffPathEpochsRead"]) or DASH, v["hotelRulesActive"]),
         "- Hotel pause regimes (explicit targets): %s; P1 and P2 declared for `%s`." % (
             v["hotelPauseRegimes"] or DASH, v["hotelP1P2Regime"] or DASH),
         "- Rule: " + REPORT_RULE, ""]
    for key, x in v["extraCollectedServices"].items():
        w += ["### Extra collected service `%s`" % key, "",
              "- valid cells of the epoch: %d; with any sensor of the service: %d (%s); distinct sensors: %d." % (
                  x["validCellsOfEpoch"], x["cellsWithAnySensor"],
                  ", ".join("%s %d" % kv for kv in x["cellsByChannel"].items()) or DASH, x["distinctSensors"]),
              "- application.log lines of the service: %d in %d cell(s); log sensors: %d." % (
                  x["logLinesInApplicationLog"], x["cellsWithLogLines"], x["logSensors"])]
        if x.get("logNote"):
            w.append("- **" + x["logNote"] + "**")
        if x.get("exposureNote"):
            w.append("- " + x["exposureNote"] + ".")
        w.append("")
    if v["designCounts"]:
        w += ["### Declared design against cells found", "", "| regime, rate | declared | found | valid |", "|---|---|---|---|"]
        for k, x in v["designCounts"].items():
            w.append("| %s | %d | %d | %d |" % (k, x["declaredPerRegimeAndRate"], x["found"], x["valid"]))
        w.append("")
    eps = v["manifestation"]["episodes"]
    if eps:
        w += ["### Off-path manifestation record", "", "Rule: " + v["manifestation"]["rule"], "",
              "| cell | rate | block | manifested | during paused | outage observed (recorded, not required) | docker pause / unpause events "
              "| manifested by rule |", "|---|---|---|---|---|---|---|---|"]

        def f(x):
            return DASH if x is None else str(x)
        for r in eps:
            w.append("| %s | %g | %s | %s | %s | %s | %s / %s | %s |" % (
                r["cell"], r["rate"], r["block"], f(r["manifested"]), f(r["duringStatePaused"]), f(r["outageObserved"]),
                f(r["dockerPauseEvents"]), f(r["dockerUnpauseEvents"]), f(r["offPathManifested"])))
        w.append("")
    return md + "\n".join(w) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory/ies of one system (pooled, H1)")
    ap.add_argument("--system", default="hotel", choices=v24.SYSTEMS)
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
    R = run34(camp[0] if len(camp) == 1 else camp, system=a.system, validation_dirs=[Path(x) for x in a.validation],
              blocks=set(a.blocks) if a.blocks is not None else None, split=a.split,
              test_blocks=set(a.test_blocks) if a.test_blocks is not None else None)
    with v24.use_system(a.system):
        v31.finish(R)
    J = build_json34(R)
    out.mkdir(parents=True)
    v31.write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    v31.write_new(out / OUT_MD, render34(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
