#!/usr/bin/env python3
"""Traffic-sweep analysis v2.4: the methodology-hardening decisions (H1-H5, H7, H8, H11, rows 15 and 19) on the Hotel
sweep, revised by protocol round 11 (decisions 51-55), the independent v2 review, protocol round 12 (decision 57),
protocol round 13 (decisions 58, 59), the independent v2.2 review and protocol round 14 (decision 60); with readers for
TeaStore and OTel.

BINDING. Hotel: research/traffic-sweep/DECLARATION.md (a795fc9) + AMENDMENT_1.md (6aca1ff) + AMENDMENT_2.md (ddf03df) +
AMENDMENT_3.md (a7d509d). Methodology: research/protocol/METHODOLOGY_HARDENING.md (H1-H11) as decided in
research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60). Binding inputs: the v1 review
(research/traffic-sweep/readout-hotel-r3/REVIEW.md, a61801c) and the v2 review
(research/traffic-sweep/readout-hotel-r3-v2-fix1/REVIEW.md, cb795c5). Every tunable value is read from
research/protocol/parameters.json (decision 37, provenance rule); tests/test_sweep_analysis_v2.py fails on a numeric
literal here that is not a unit conversion or a structural 0/1/2 (also inside float("...")/int("...") or literal
arithmetic), on a tunable imported from v1/detection_time that does not equal its registry entry, and on any registry
entry used here whose origin is `unknown`. v1 (sweep_analysis.py, readout e31e316) is imported and never edited;
detection_time.py (dbebcbb) likewise. v2 is this file at 87b04ef / 32e3178, v2.1 at 22e0d12 (the record of the Hotel
re-analysis, readout ee983bb), v2.2 at 421a6d2 (freeze 5c98726, Hotel readout bc8e738), v2.3 at af6f223 (freeze 830f309,
Hotel readout 037e84e); the tests load them from git to show each later rule failing on the earlier behaviour.

    uv run python research/detection-time/sweep_analysis_v2.py <campaign dir> --out <new dir> \
        [--v1-readout research/traffic-sweep/readout-hotel-r3/sweep_analysis.json] \
        [--v2-readout research/traffic-sweep/readout-hotel-r3-v2-fix1/sweep_analysis_v2.json] \
        [--v21-readout research/traffic-sweep/readout-hotel-r3-v2.1/sweep_analysis_v2_1.json] \
        [--v22-readout research/traffic-sweep/readout-hotel-r3-v2.2/sweep_analysis_v2_2.json] \
        [--v23-readout research/traffic-sweep/readout-hotel-r3-v2.3/sweep_analysis_v2_3.json]
    uv run python research/detection-time/sweep_analysis_v2.py <campaign dir> [<campaign dir> ...] \
        --system teastore|otel --out <new dir>

On Hotel this is an EXPLORATORY RE-ANALYSIS: v1's to v2.3's results were seen before v2.4 was written. Its rules come
from the decisions, not from which verdicts they move. Written and tested on synthetic fixtures only. v2.4 is the
version frozen for TeaStore and OTel (decision 60): no rule changes before those cells are read.

WHAT v2.4 CHANGES AGAINST v2.3 (round 14 and the v2.3 review; a switch below, flipped only by planted-defect tests):
  Decision 60 (START_TERM_ONLY, START_TERM_RULE). An `absent`-vs-`absent` pair that decisions 57 and 58 leave neither
     same-request nor unclassifiable (different requests start and end the two silences) is a win only if its START
     term (ledger's last completion before its silence - sensor's last observation before its silence, each from the
     onset in its own clock) exceeds the tie margin; the gap term (g_ledger - g_sensor) never counts toward a lead and
     stays printed in the decomposition. Category: "start term within the margin (decision 60)". Mixed pairs unchanged.
  G3: the unclassifiable label names both ends ("no silence-ending or silence-starting token"); earlier readouts' label
     is mapped onto it when comparing. G4: OTel's productcatalogservice and frontend logs carry no parseable app stamp
     (KNOWN_LIMITATIONS, JSON_LOG_STAMP_RULE notParsed). A v2.3 comparison (`--v23-readout`) is added.

WHAT v2.3 CHANGES AGAINST v2.2 (round 13 and the v2.2 review; switches below, flipped only by planted-defect tests):
  Decision 58 (SILENCE_START_TOKEN, SILENCE_START_TOKEN_RULE). For an `absent`-vs-`absent` pair the records that START
     the two silences set the lead: lead = (ledger's last completion - sensor's last observation) + (g_ledger -
     g_sensor). Such a pair is same-request (no win) if the starting records share a request token or the ending ones
     do (decision 57, unchanged); the sensor's starting token is its own, else its trace's entry-root token; a missing
     start token makes the pair unclassifiable (no win, counted). Mixed pairs keep decision 57. Every absent/absent
     lead is printed with its decomposition.
  Decision 59: P2 on TeaStore uses TeaStore's 15 s client timeout (registry origin only; the value was already 15).
  F2: P1's branch is printed (summary and detail) and holds are counted by branch.
  F3 (JSON_LINE_STAMP, JSON_LOG_STAMP_RULE): a json-line record keeps its own stamp (Envoy's start + duration; a zoned
     `timestamp` / `time` / `ts` string; pino's numeric `time` in ms); others stay without one ("not counted").
  F5: the TeaStore / OTel readouts state the harness provenance (HARNESS_PROVENANCE); a TeaStore cell from a harness
     commit the registry does not list is flagged. F11: the readers' drop counts are printed. F12: changed P4 folds are
     counted in every setting and BC view against v2.1 and v2.2 (`--v22-readout`), each with its rule.
  F7, F9, F10, F11: known limitations (KNOWN_LIMITATIONS), printed in every readout.

WHAT v2.2 CHANGES AGAINST v2.1 (round 12; a switch below, flipped only by the planted-defect tests):
  Decision 57 (SENSOR_SILENCE_TOKEN), the mirror of decision 51. A sensor's `absent` catch carries the token(s) of the
     observation that ends its silence (the first record of the stream after the gap; SENSOR_ABSENT_TOKEN_RULE): the
     observation's own token where it carries one (a tokened root span, a log line naming a token), else the token of
     the trace it belongs to (the entry-root token, as the harness correlates it). If that request is the ledger's
     catching request, H3 (c) classes the pair same-request (no win). If neither token exists (no observation ends the
     silence, or the ending one carries no token and belongs to no tokened trace), the pair is "unclassifiable": no
     win, counted and reported per rate.
  Readers for TeaStore and OTel (`--system teastore|otel`; several campaign directories of one system are pooled,
     H1). Written from the harness code that writes the cells (TeaStore 91c4967, OTel 6e37ec2) and tested on cells the
     harnesses' own writers produced (tests/fixtures/sweep_v22, tests/test_sweep_analysis_v22_systems.py); no TeaStore
     or OTel evidence was read. Each maps its cell onto the model the Hotel loader produces (ledger rows, the fault
     receipt and onset interval, spans with request tokens, logs with Docker receive stamps, metric samples, probe
     windows, the route's call path). System values (regimes, targets, actuators, timeouts, route services, readback
     map, episodes, P2's timeout, P3/availability maps, schemas) are registry entries declared before any of their
     cells was read. Where a system lacks a field, the dependent output is `—` with the reason (dash_outputs), never a
     default value; a file outside the pinned schema stops the run (UnknownSchema). Rule-level changes for every
     system, none of which moves a Hotel verdict: P1/P2 key on the system's pause regime; P4 with one episode is `—`
     plus the single-episode comparison (descriptive); a family no cell collects has no operating point (`—`); the
     onset interval's upper bound is the command's return where the cells keep no Docker events (P1's Docker-event
     tolerance terms then do not apply; TeaStore adds its receipt-alignment residual); span stamps are nanoseconds.

WHAT v2.1 CHANGES AGAINST v2 (round 11; each a switch below, flipped only by the planted-defect tests):
  B1 (decision 55, P4_MUTED_DASH). P4 at a (class, rate) is `—` (not evaluable) when a collected sensor family is not
     at the operating point there; never "sensor missed" or "none". highest_rate prints "— at {rates}" for them.
  M1 (decision 51, SAME_SILENCE). The ledger's `absent` catch carries the token of the first completion that ends the
     silence; a sensor catch on that request is same-request (H3 c), so no win.
  M2 (decision 52, MAD_ZERO_DASH). A sensor whose fault-free MAD is 0 at its baseline is "scale not estimable": its
     level rules (spike, run3, median) give `—`, no catch and no false alarm, and it is listed. `appear` and `absent`
     do not need the scale and are kept. No quantile threshold (a later sensitivity row, W2).
  M3 (decision 55, SCORED_SET_CALIBRATION). Held-out false alarms are counted on the scored sensor set of each fault
     class: the spike path filter (dt.scored) and the by-construction flags (bc_of, no-BC view, as P4) applied exactly
     as in scoring, the detector restarted after each counted alarm (exact simulation, below). The operating point is
     therefore per (family, class, rate). v2's all-sensors count is kept beside it, labelled.
  M4 (decision 53). K per channel family within the system is the primary, decided; one K per family over every
     (class, rate) where some grid K meets the target; the system-wide K (L, M, S, T together) beside it.
  M5 (decision 54, P1_AMBIGUITY). P1's ambiguity window is [startedMonotonic, Docker `pause` event + delta], delta = the
     cell's pre-onset median over fault-free requests of (request end - end of the paused service's spans in that
     request's trace); the tolerance is the measured timing terms (P1_TOLERANCE_RULE). Both decided before any TeaStore
     or OTel cell is read.
  Minors: the ledger's `absent` gap is stated per rate against the client timeout (it fires before a timeout only where
     the gap is shorter); the secondary table carries the H4 class split (SECONDARY_H4_SPLIT); the ledger-latency
     resolution is labelled a float-difference granularity; the fault doses are decision 50's.

WHAT CHANGES AGAINST v1 (each a switch below, flipped only by the planted-defect tests):
  H1 baseline (POOLED). Per (rate, sensor) the fault-free data are pooled: the no-fault cells from the barrier to the
     measurement end, plus the pre-onset time [barrier, receipt startedMonotonic) of every fault cell, unscreened.
     Excluded: the warm-up (it precedes the barrier) and the probe windows (scope rule, AMENDMENT_3). A scored episode's
     baseline is therefore the other cells' fault-free data plus its own pre-onset, never its post-onset. A sensor
     needs MIN_BASELINE_POOLED points for a level threshold and for the largest-gap scale of `absent`, else `—`.
     `appear` fires on a token with no record in the pooled fault-free data (the vocabulary).
  Floor (RELATIVE_FLOOR, RESOLUTION_FLOOR; decisions 27, 32). threshold = max(K * MAD_SCALE * MAD, share * |median|,
     resolution), share = FLOOR_REL_PRIMARY (arm FLOOR_REL_ARM beside); resolution per RESOLUTION_RULE. A zero
     threshold gives no level verdict.
  H2/H7 operating point (LOCO, FAR_MEETS_CRITERION). False alarms are counted per hour of the OR of all rules, over
     each held-out no-fault cell, scored with values fitted without that cell; the detector restarts after each alarm.
     Because run3 and median can never fire before spike (each needs a sample beyond the threshold), and appear,
     absent (re-armed), failed and spike are each a set of instants, the restart count equals the number of distinct
     alarm instants in the cell (tested against a brute-force restart loop); this is v2's all-sensors count, kept
     beside the v2.1 count. On the scored set (M3) an off-path sensor's spike does not count while its run3 and median
     do, so v2.1 simulates the restarted detector exactly (restart_count, tested against the same brute-force loop and
     against the distinct-instant count when nothing is filtered). Exact one-sided Poisson upper bound at
     FAR_CONFIDENCE. K per (system, family) = the smallest K_GRID value whose bound meets FAR_TARGET_PER_HOUR at
     every (class, rate) where some grid K meets it; where none does, the family is not at the operating point
     (`—`). K = K_REFERENCE is a reference row. The per-system K (one K for L, M, S, T together) is reported beside.
  H3 P4 (Hotel only). A held-out win needs (a) the sensor faster than the ledger at the operating point, (b) a lead
     above the timing-uncertainty margin (MARGIN_RULE: both stamps' granularity + the per-cell clock-alignment
     residual + for logs the per-cell receipt-delay bound; a service writing no app stamp gets no log lead), (c) the
     catch neither same-request (SAME_REQUEST: the catching observation carries the token of the ledger's catching
     row) nor by construction (existing BC flags + BC-actuator-readback, ACTUATOR_READBACK, decision 26); (d) "the
     ledger missed it" is counted apart from "faster" (LEDGER_MISSED_APART); (e) the ledger has `absent` on request
     completions (LEDGER_ABSENT). Selection leave-one-episode-out on the other three episodes, ties reported with the
     win share across the tied sensors; paired differences per episode, descriptive (n = 4); every fold line prints
     the sensor's and the ledger's catching rule. The P4_MIN count is kept as the declared, descriptive criterion.
  H4 onset interval (P1_INTERVAL). search-pause: [receipt startedMonotonic, Docker `pause` event of the target]
     (docker-events.jsonl timeNano, mapped wall -> monotonic by the per-cell fit); degradation faults:
     [startedMonotonic, appliedMonotonic]. Ledger requests are classed before / straddling / after. P1's expected catch
     is the interval [min{start + T : end > lo}, min{start + T : end > hi}] (T the client timeout; a request that
     completes inside [lo, hi] is ambiguous and sets only the earliest end); v2.1 widens the ambiguity window to
     [lo, hi + delta] (M5, P1_AMBIGUITY_WINDOW_RULE, decision 54). P1 holds per episode if the ledger's first `failed`
     catch lies inside it +- P1_TOLERANCE_RULE (decision 54). P1 under v1's definition is printed from v1's readout.
  H5 exposure (recorded only). A sensor is exposed in an episode if >= 1 ledger request started in the fault window
     and its service is on the route's call path projected from the no-fault cells' traces (EXPOSURE_RULE). Misses
     are still charged in every episode; exposure changes wording only ("not exposed in this run").
  H8 clocks. Event time is primary (decision 43). Availability is taken only from measured collector receive stamps
     (AVAILABILITY_SOURCES); spans have none on Hotel, so their availability is `—`. The P4 availability verdict is a
     sensitivity row beside the event-time verdict.
  H11 P3 (P3_RESTRICT). Only families traffic-independent by mechanism (P3_TRAFFIC_INDEPENDENT); empty -> `—`.
  TAU (k/n admissibility) is gone: noise is handled by the operating point.
UNCHANGED (v1 / dbebcbb functions reused): readers' file rules and the not-scored cell gate, token rule for spans,
Docker receive stamp for logs and the per-cell whole-second rule, probe windows (scope) and the move of a catch to a
window end, spike path filter, BC taxonomy with BC-caller-log and caller-span by content, miss charged at the hold,
impact by scheduled time, onset bound = startedMonotonic for every time to detection.
"""
import argparse
import bisect
import contextlib
import datetime as _dt
import hashlib
import json
import math
import platform
import re
import statistics
import sys
from collections import Counter, defaultdict, namedtuple
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import detection_time as dt  # noqa: E402  dbebcbb, unchanged
import sweep_analysis as v1  # noqa: E402  v1, unchanged (readout e31e316)
from sensor_rep.events import Event, group, level_class, project_map, stream_meta  # noqa: E402
from sensor_rep.parsers import common, hotel  # noqa: E402
from sensor_rep.parsers import otel as sr_otel  # noqa: E402  (RUNTIME_NS only)

PARAMETERS = REPO / "research" / "protocol" / "parameters.json"
HOTEL_BINDING = BINDING = ("research/traffic-sweep/DECLARATION.md (a795fc9)", "research/traffic-sweep/AMENDMENT_1.md (6aca1ff)",
           "research/traffic-sweep/AMENDMENT_2.md (ddf03df)", "research/traffic-sweep/AMENDMENT_3.md (a7d509d)",
           "research/protocol/METHODOLOGY_HARDENING.md (H1-H11)",
           "research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; round 11 = aae8898, decision 57 = "
           "d126589, round 13 = 6162c37, round 14 = c17f6a6)",
           "research/traffic-sweep/readout-hotel-r3/REVIEW.md (a61801c, the v1 review)",
           "research/traffic-sweep/readout-hotel-r3-v2-fix1/REVIEW.md (cb795c5, the v2 review)",
           "research/protocol/parameters.json (decision 37)")
VERSION = "2.4"
HOTEL_LABEL = LABEL = "exploratory re-analysis (v1, v2, v2.1, v2.2 and v2.3 results seen)"
OUT_MD, OUT_JSON = "SWEEP_ANALYSIS_V2_4.md", "sweep_analysis_v2_4.json"


# =========================================================================== the registry (decision 37)

def load_registry(path=PARAMETERS):
    doc = json.loads(Path(path).read_text())
    return {p["name"]: p for p in doc["parameters"]}


REGISTRY = load_registry()
PARAMS_USED = set()


def param(name):
    """Every tunable value of v2 comes through here; the names used are checked against their origin by the tests."""
    PARAMS_USED.add(name)
    return REGISTRY[name]["value"]


RATES = tuple(param("RATES"))
EPISODES = param("EPISODES_HOTEL")
K_REF = param("K_REFERENCE")
K_GRID = tuple(param("K_GRID"))
SCALE = param("MAD_SCALE")
ARMS = {"primary": param("FLOOR_REL_PRIMARY"), "arm": param("FLOOR_REL_ARM")}
MIN_POOLED = param("MIN_BASELINE_POOLED")
FAR_TARGET = param("FAR_TARGET_PER_HOUR")
FAR_CONF = param("FAR_CONFIDENCE")
FAR_MEETS = param("FAR_MEETS_CRITERION")
K_FIT_UNIT = param("K_FIT_UNIT")
RUN_N = param("RUN_N")
MEDIAN_MIN = param("MEDIAN_MIN_SAMPLES")
ABSENT_GAP_MULT = param("ABSENT_GAP_MULT")
ABSENT_REARM = param("ABSENT_REARM")
PATH_FILTER = param("PATH_FILTER")
PRIMARY_PROBE = param("PRIMARY_PROBE_VARIANT")
PRIMARY_CALLER_SPAN = param("PRIMARY_CALLER_SPAN_VARIANT")
P2_DOBS_S = param("P2_DOBS_S")
P2_EPS = param("P2_EPS")
P2_MIN = param("P2_MIN_EPISODES")
P4_MIN = param("P4_MIN")
P3_CADENCE_S = param("P3_CADENCE_S")
P3_TI = param("P3_TRAFFIC_INDEPENDENT")
ACTUATOR = param("ACTUATOR_READBACK")
LEDGER_ABSENT = param("LEDGER_ABSENT")
AVAIL_SOURCES = param("AVAILABILITY_SOURCES")
REPORT_TOP = param("REPORT_TOP_SOURCES")
RULES_TEXT = {n: param(n) for n in ("RESOLUTION_RULE", "MARGIN_RULE", "LOG_RECEIPT_RULE", "P1_TOLERANCE_RULE",
                                    "P1_AMBIGUITY_WINDOW_RULE", "SCALE_NOT_ESTIMABLE_RULE", "CALIBRATION_SET_RULE",
                                    "LEDGER_ABSENT_TOKEN_RULE", "SENSOR_ABSENT_TOKEN_RULE", "P4_NOT_EVALUABLE_RULE",
                                    "EXPOSURE_RULE")}

# the registry is the source of truth for values that reused dbebcbb / v1 functions read internally
# Tunables v2.1 takes from v1 / dbebcbb by attribute (module.NAME -> registry entry); the tests scan the source for
# every numeric or boolean v1./dt. constant and require it here (or among the reader switches), equal to the registry.
IMPORTED_TUNABLES = {"dt.RUN_N": "RUN_N", "dt.MIN_BASELINE": "MEDIAN_MIN_SAMPLES", "dt.PATH_FILTER": "PATH_FILTER",
                     "v1.REF": "V1_REFERENCE_POINT"}
for _name, _reg in IMPORTED_TUNABLES.items():
    _mod, _attr = _name.split(".")
    _val = getattr({"dt": dt, "v1": v1}[_mod], _attr)
    assert (list(_val) if isinstance(_val, tuple) else _val) == param(_reg), "registry vs %s" % _name
assert RUN_N == dt.RUN_N and MEDIAN_MIN == dt.MIN_BASELINE and PATH_FILTER == dt.PATH_FILTER, "registry vs dbebcbb"
assert dt.INCLUSIVE is True, "the operating-point count assumes dbebcbb's inclusive comparator"
assert PRIMARY_PROBE == "scope", "v2 implements the scope probe rule only (AMENDMENT_3 primary)"
assert K_REF in K_GRID, "the reference K must be a grid point"
assert list(K_GRID) == sorted(K_GRID)

# unit conversions and structure (not tunable)
US_PER_S = 1e6
NS_PER_S = 1e9
MS_PER_S = 1000.0
S_PER_HOUR = 3600.0
DECIMAL_BASE = 10.0

# structure reused from v1 (names, files, mappings; no tunable value)
SUT, ENTRY = v1.SUT, v1.ENTRY
NOFAULT, FAULT_REGIMES, FAULT_TARGETS = v1.NOFAULT, v1.FAULT_REGIMES, v1.FAULT_TARGETS
FAMILIES = ("E", "L", "M", "S", "T")
SENSOR_FAMILIES = ("L", "M", "S", "T")
COLUMNS = v1.COLUMNS
DASH = v1.DASH
TOKEN_SEARCH = re.compile(v1.TOKEN.pattern.lstrip("^").rstrip("$"))
COMPLETIONS = "#completions"
E_RULES = tuple(dt.E_RULES) + ("absent",)
READ_FILES = v1.READ_FILES + ("docker-events.jsonl", "compose-rendered.yml")
SETTINGS = ("primary", "arm", "reference", "systemK")
TITLE = "Hotel"
SYSTEM = "hotel"

# =========================================================================== systems (v2.2): one model, three readers
# Hotel's values above are the defaults; use_system() rebinds the module-level names below for TeaStore or OTel and
# restores them on exit. Every value comes from the registry (SYSTEM_<SUT>, CLIENT_TIMEOUT_S_<SUT>, ...), declared
# before any TeaStore or OTel cell was read.
SYSTEMS = ("hotel", "teastore", "otel")
SYSTEM_GLOBALS = ("SYSTEM", "TITLE", "SUT", "ENTRY", "NOFAULT", "FAULT_REGIMES", "FAULT_TARGETS", "EPISODES",
                  "ACTUATOR", "P3_TI", "AVAIL_SOURCES", "READ_FILES", "BINDING", "LABEL", "P2_DOBS_S")
FAMILY_CHANNELS = param("FAMILY_CHANNELS")
LOG_LAYOUT_NAMES = param("LOG_LAYOUTS")
TOKEN_SOURCES = param("TOKEN_SOURCES")
SCHEMAS = param("SCHEMAS")
P1_ERROR_ANSWER = param("P1_ERROR_ANSWER_RULE")
LOG_TEXT_CHARS = param("LOG_TEXT_CHARS")
JSON_STAMP_RULE = param("JSON_LOG_STAMP_RULE")
RULES_TEXT.update({n: param(n) for n in ("ROUTE_GRAPH_RULE", "PROBE_TRACE_RULE", "CLOCK_RULE_TEASTORE",
                                          "SILENCE_START_TOKEN_RULE", "START_TERM_RULE")})
HARNESS_PROVENANCE = param("HARNESS_PROVENANCE")
KNOWN_LIMITATIONS = param("KNOWN_LIMITATIONS")
V23_FIXES = param("V23_FIXES")
V24_FIXES = param("V24_FIXES")


def _system_values(name):
    """The registry's profile of one system as the module-level names it rebinds (data only)."""
    if name == "hotel":
        return {"SYSTEM": "hotel", "TITLE": "Hotel", "SUT": v1.SUT, "ENTRY": v1.ENTRY, "NOFAULT": v1.NOFAULT,
                "FAULT_REGIMES": v1.FAULT_REGIMES, "FAULT_TARGETS": v1.FAULT_TARGETS,
                "EPISODES": param("EPISODES_HOTEL"), "ACTUATOR": param("ACTUATOR_READBACK"),
                "P3_TI": param("P3_TRAFFIC_INDEPENDENT"), "AVAIL_SOURCES": param("AVAILABILITY_SOURCES"),
                "READ_FILES": v1.READ_FILES + ("docker-events.jsonl", "compose-rendered.yml"),
                "BINDING": HOTEL_BINDING, "LABEL": HOTEL_LABEL, "P2_DOBS_S": param("P2_DOBS_S")}
    up = name.upper()
    prof = param("SYSTEM_" + up)
    return {"SYSTEM": name, "TITLE": prof["title"], "SUT": prof["sut"], "ENTRY": prof["entry"],
            "NOFAULT": prof["noFaultRegime"], "FAULT_REGIMES": tuple(prof["faultRegimes"]),
            "FAULT_TARGETS": {r: tuple(v) for r, v in prof["faultTargets"].items()},
            "EPISODES": param("EPISODES_" + up), "ACTUATOR": param("ACTUATOR_READBACK_" + up),
            "P3_TI": param("P3_TRAFFIC_INDEPENDENT_" + up), "AVAIL_SOURCES": param("AVAILABILITY_SOURCES_" + up),
            "READ_FILES": SYSTEM_READ_FILES[name], "BINDING": SYSTEM_BINDING[name],
            "LABEL": "analysis frozen before any %s cell was read" % prof["title"],
            "P2_DOBS_S": param("P2_DOBS_S_" + up)}


SYSTEM_READ_FILES = {
    "teastore": ("receipt.json", "candidate-validation.json", "journey-ledger.plan.json", "journey-ledger.jsonl",
                 "intervention.json", "auth.log", "application.log", "traces.json", "system-samples.json"),
    "otel": ("receipt.json", "request-ledger.json", "intervention.json", "otelcol.log", "application.log")}
SYSTEM_BINDING = {
    "teastore": ("research/traffic-sweep/DECLARATION_TEASTORE.md (c9f072b)",
                 "research/traffic-sweep/AMENDMENT_TEASTORE_1.md (bbbd80b)",
                 "research/traffic-sweep/AMENDMENT_TEASTORE_2.md (b840353)",
                 "research/traffic-sweep/DECLARATION_QUIET_TEASTORE.md (fc64a6d)",
                 "research/protocol/METHODOLOGY_HARDENING.md (H1-H11)",
                 "research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = "
                 "6162c37, round 14 = c17f6a6)",
                 "harness observability-placement-runtime-teastore-protocol 91c4967 (the cell writer and validator)",
                 "research/protocol/parameters.json (decision 37)"),
    "otel": ("research/traffic-sweep/DECLARATION_OTEL.md (da95915)", "research/traffic-sweep/AMENDMENT_OTEL_1.md (16ae373)",
             "research/traffic-sweep/DECLARATION_QUIET_OTEL.md (593d4ee)",
             "research/protocol/METHODOLOGY_HARDENING.md (H1-H11)",
             "research/PROTOCOL_DRAFT_20261002.md rounds 7-14 (decisions 26-60; decision 57 = d126589, round 13 = "
                 "6162c37, round 14 = c17f6a6)",
             "harness observability-placement-runtime-otel-protocol 6e37ec2 (the cell writer and terminal)",
             "research/protocol/parameters.json (decision 37)")}


@contextlib.contextmanager
def use_system(name):
    """Rebind the system's module-level names (registry values) for the duration; restore them on exit."""
    if name not in SYSTEMS:
        raise SystemExit("unknown system %r (one of %s)" % (name, ", ".join(SYSTEMS)))
    if name == "hotel" and SYSTEM == "hotel":         # Hotel's values are the module defaults (and test switches)
        yield
        return
    g = globals()
    saved = {k: g[k] for k in SYSTEM_GLOBALS}
    g.update(_system_values(name))
    try:
        yield
    finally:
        g.update(saved)


class UnknownSchema(RuntimeError):
    """A cell file whose schema (version, kind, key set) is not what the pinned harness writes, or a declared design
    value the cell contradicts: the run stops (never a guess, never a cell quietly not scored)."""


def check_schema(doc, where, expect):
    """expect: {key: value} (dotted keys reach one level down; a list value = one of)."""
    if not isinstance(doc, dict):
        raise UnknownSchema("%s is not a JSON object" % where)
    for key, want in expect.items():
        got = doc
        for part in key.split("."):
            got = got.get(part) if isinstance(got, dict) else None
        ok = got in want if isinstance(want, list) else got == want
        if not ok:
            raise UnknownSchema("%s: %s = %r, the pinned harness writes %r" % (where, key, got, want))

# Switches flipped only by tests/test_sweep_analysis_v2.py (planted defects); the analysis never changes them.
POOLED = True                 # H1: pooled cross-fitted fault-free baseline (False = the cell's own pre-window)
MIN_POOLED_CHECK = True       # H1: n >= MIN_BASELINE_POOLED, else no level / absent verdict
RELATIVE_FLOOR = True         # decisions 27/32: share x |median| in the floor
RESOLUTION_FLOOR = True       # decisions 27/32: instrument resolution in the floor
LOCO = True                   # H2: a held-out quiet cell is scored with values fitted without it
SAME_REQUEST = True           # row 15 / H3 (c)
MARGIN_CHECK = True           # H3 (b)
ACTUATOR_FLAG = True          # decision 26
LEDGER_MISSED_APART = True    # H3 (d)
P1_INTERVAL = True            # H4: P1 against the interval expectation
P3_RESTRICT = True            # H11
EXPOSURE_TRACES = True        # H5: route path from the no-fault traces (False = every service exposed)
# v2.1 (round 11)
P4_MUTED_DASH = True          # B1: P4 = — where a collected sensor family is not at the operating point
SAME_SILENCE = True           # M1: the ledger's `absent` carries the token of the completion that ends the silence
MAD_ZERO_DASH = True          # M2: MAD = 0 -> scale not estimable, level rules —
SCORED_SET_CALIBRATION = True # M3: false alarms on the scored set per class (False = v2's all-sensors count)
P1_AMBIGUITY = True           # M5: P1 ambiguity window [lo, hi + delta]
SECONDARY_H4_SPLIT = True     # minor: secondary table split by H4 class
# v2.2 (round 12)
SENSOR_SILENCE_TOKEN = True   # decision 57: a sensor's `absent` carries the token of the observation ending its silence
# v2.3 (round 13 and the v2.2 review)
SILENCE_START_TOKEN = True    # decision 58: absent/absent pairs also same-request when the silence-starting records are
JSON_LINE_STAMP = True        # F3: a json-line record's own stamp (Envoy start_time + duration_ms; time / timestamp)
# v2.4 (round 14)
START_TERM_ONLY = True        # decision 60: absent/absent pairs of different requests win only on the start term
PROBE_TRACE_FILTER = True     # PROBE_TRACE_RULE: untokened entry-rooted probe traces are not read (TeaStore, OTel)
RECEIPT_CLOCK_MAP = True      # CLOCK_RULE_TEASTORE: the producer's offsets mapped onto the ledger's clock
ROUTE_GRAPH = True            # ROUTE_GRAPH_RULE: the project map's call graph restricted to the system's route


# =========================================================================== small pure helpers

def decimals(x):
    """Fractional digits of a float's shortest repr (= the JSON text it was read from)."""
    s = repr(float(x)).lower()
    if "e" in s:
        mant, ex = s.split("e")
        d = len(mant.split(".")[1]) if "." in mant else 0
        return max(0, d - int(ex))
    return len(s.split(".")[1]) if "." in s else 0


def granularity(values):
    """10^-d for the most fractional digits among the values' representations (None for no value)."""
    d = [decimals(v) for v in values if v is not None]
    return DECIMAL_BASE ** -max(d) if d else None


def iso_digits(s):
    m = re.search(r"\.(\d+)", s or "")
    return len(m.group(1)) if m else 0


def gamma_q(a, x):
    """Regularized upper incomplete gamma Q(a, x) (Numerical Recipes §6.2: series for x < a + 1, else the modified
    Lentz continued fraction), iterated to machine precision."""
    if x <= 0:
        return 1.0
    eps, tiny = sys.float_info.epsilon, sys.float_info.min
    front = math.exp(a * math.log(x) - x - math.lgamma(a))
    if x < a + 1:
        ap, term = a, 1.0 / a
        total = term
        while abs(term) >= abs(total) * eps:
            ap += 1
            term *= x / ap
            total += term
        return max(0.0, 1.0 - total * front)
    b = x + 1 - a
    c, d = 1.0 / tiny, 1.0 / b
    h, i = d, 1
    while True:
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1) < eps:
            return min(1.0, front * h)
        i += 1


def poisson_cdf(k, lam):
    """P(X <= k) for X ~ Poisson(lam) = Q(k + 1, lam) (stable where dt.poisson_ge's exp(-lam) underflows)."""
    return 1.0 if lam <= 0 else gamma_q(k + 1, lam)


def poisson_upper(k, conf=None):
    """Exact one-sided upper confidence limit of a Poisson mean after observing k events (bisection to float
    convergence on P(X <= k; lam) = 1 - conf)."""
    alpha = 1.0 - (FAR_CONF if conf is None else conf)

    def cdf(lam):
        return poisson_cdf(k, lam)
    lo, hi = 0.0, 1.0
    while cdf(hi) > alpha:
        lo, hi = hi, hi + hi
    while True:
        mid = (lo + hi) / 2
        if mid in (lo, hi):
            return hi
        lo, hi = (mid, hi) if cdf(mid) > alpha else (lo, mid)


def min_positive_gap(vals):
    u = sorted(set(v for v in vals if v is not None))
    g = [y - x for x, y in zip(u, u[1:]) if y > x]
    return min(g) if g else None


def max_gap(times):
    g = [y - x for x, y in zip(times, times[1:])]
    return max(g) if g else None


def silence_bounds(records, t0, a, b, g):
    """(instant r + g, the record that ends the silence or None, the record r that starts it) for every record r >= t0
    followed by a silence longer than g, with r + g in [a, b] (re-armed: the stream may resume and go silent again).
    records: sorted (liveness)."""
    out = []
    i = bisect.bisect_left(records, max(t0, a - g))
    n = len(records)
    while i < n and records[i] + g <= b:
        nxt = records[i + 1] if i + 1 < n else math.inf
        x = records[i] + g
        if nxt - records[i] > g and x >= a:
            out.append((x, None if nxt == math.inf else nxt, records[i]))
        i += 1
    return out


def silence_enders(records, t0, a, b, g):
    """(instant r + g, the record that ends the silence or None) per silence (silence_bounds without the start)."""
    return [(x, e) for x, e, _ in silence_bounds(records, t0, a, b, g)]


def silences(records, t0, a, b, g):
    """`absent` alarm instants (silence_enders without the ender)."""
    return [x for x, _, _ in silence_bounds(records, t0, a, b, g)]


def first_silence_bounds(records, t0, a, b, g):
    """The episode's `absent` catch, the record that ends its silence (M1, decision 51; decision 57) and the record
    that starts it (the last observation before the silence, decision 58). ABSENT_REARM False = dbebcbb: only the first
    silence after the last pre-window record, and no verdict for a stream already silent at a."""
    if ABSENT_REARM:
        s = silence_bounds(records, t0, a, b, g)
        return s[0] if s else (None, None, None)
    pre = records[bisect.bisect_left(records, t0):bisect.bisect_left(records, a)]
    if not pre or pre[-1] + g < a:
        return None, None, None
    last = pre[-1]
    for t in records[bisect.bisect_left(records, a):] + [math.inf]:
        if t - last > g:
            return (last + g, None if t == math.inf else t, last) if last + g <= b else (None, None, None)
        last = t
    return None, None, None


def first_silence_ender(records, t0, a, b, g):
    """first_silence_bounds without the start (v2.1 / v2.2's interface)."""
    return first_silence_bounds(records, t0, a, b, g)[:2]


def first_silence(records, t0, a, b, g):
    return first_silence_ender(records, t0, a, b, g)[0]


def floor_of(m, share, res):
    f = []
    if RELATIVE_FLOOR:
        f.append(share * abs(m))
    if RESOLUTION_FLOOR and res is not None:
        f.append(res)
    return max(f) if f else 0.0


def threshold(lv, k, share, res):
    """(median, thr) of a pooled level baseline (m, mad, n); thr = max(K * SCALE * MAD, floor)."""
    m, mad, _ = lv
    return m, max(k * SCALE * mad, floor_of(m, share, res))


def deviation(v, m, dirs):
    return max((v - m) if d == "up" else (m - v) for d in dirs)


def instrument(ch, meta, tok):
    if ch == "metric":
        return ("metric", meta.get("collector"), tok)
    return (ch,)


def family_of(c, ch, meta):
    if ch == "ledger":
        return "E"
    return c["family"](ch, meta.get("collector"), c["posture"])


def log_time(t, ws):
    """Observation time of a log record (whole-second stamp s timed at s + 1, as dt.log_ttd)."""
    return t + 1.0 if ws else t


# =========================================================================== reading one cell (v1 readers, extended)

def read_logs(attempt, posture, stats):
    """application.log -> (events | None, {(svc, tpl): (level, masked msg)}, {(svc, tpl): {t: tokens}}, receipt info).
    Events and texts are v1.read_logs' own (Docker receive stamp when the line has one). Added: each record's app
    stamp (one more parse without the Docker stamp; records correspond one to one), the per-cell receipt-delay bound
    max(Docker stamp - app stamp) (LOG_RECEIPT_RULE), and any request token in the message."""
    S = common.symptoms()
    info = {"bound": None, "servicesWithoutAppStamp": [], "dockerDigits": None, "linesWithBoth": 0}
    evs, text = v1.read_logs(attempt, posture, stats)
    if evs is None:
        return None, {}, {}, info
    lines, stamps, digits = defaultdict(list), defaultdict(list), []
    for raw in (attempt / "application.log").read_text(errors="replace").splitlines():
        if " | " not in raw:
            continue
        prefix, payload = raw.split(" | ", 1)
        svc = prefix.strip().rsplit("-", 1)[0]
        m = v1.DOCKER_TS.match(payload)
        t, rest = v1.docker_stamp(payload)
        if t is not None:
            digits.append(len(m.group(2) or ""))
        lines[svc].append(rest)
        stamps[svc].append(t)
    by_svc = defaultdict(list)
    for e in evs:
        by_svc[e.service].append(e)
    toks, delays = defaultdict(lambda: defaultdict(set)), []
    for svc in sorted(lines):
        stamped = v1.DOCKER_STAMP and any(x is not None for x in stamps[svc])
        apps = [r for r in S.parse_stream(lines[svc], S.HOTEL_LAYOUTS)[0] if r["framework"] != "jvm-throwable"]
        mine = by_svc.get(svc, [])
        if len(apps) != len(mine):
            raise ValueError("log records of %s do not correspond between the two parses" % svc)
        app_seen = False
        for e, ra in zip(mine, apps):
            if ra["t"] is not None:
                app_seen = True
                if stamped and e.t is not None:
                    delays.append(e.t - ra["t"])
            found = set(TOKEN_SEARCH.findall(ra["msg"] or ""))
            if found and e.t is not None:
                toks[(svc, e.token)][e.t] |= found
        if stamped and not app_seen:
            info["servicesWithoutAppStamp"].append(svc)
    info["bound"] = max(delays) if delays else None
    info["linesWithBoth"] = len(delays)
    info["dockerDigits"] = max(digits) if digits else None
    return evs, text, {k: dict(v) for k, v in toks.items()}, info


def read_spans(attempt, posture, stats):
    """As v1.read_spans (token rule unchanged), plus: per (service, op token) the request tokens of the trace each
    observation (span end) belongs to; parent -> child service edges of tokened entry-rooted traces; span key names;
    per request token, per service, the latest span end (wall s) in that token's traces (M5's delta); per (service, op
    token) the span's OWN token (the tag on the span itself, i.e. the tokened entry root; decision 57)."""
    S = common.symptoms()
    p, rp = attempt / "traces-normalized.json", attempt / "jaeger-raw-remainder.json"
    if not p.exists() and not rp.exists():
        return None, {}, set(), set(), {}, {}
    spans = json.loads(p.read_text())["events"] if p.exists() else []
    keys = set()
    for e in spans:
        keys.update(e.keys())
    if rp.exists():
        rem = v1._remainder_spans(json.loads(rp.read_text()))
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
    keep, edges = {}, set()
    for tid, es in by_trace.items():
        entry_root = any(e.get("parentSpanId") is None and e.get("service") == ENTRY for e in es)
        tk = {str((e.get("tags") or {}).get(v1.TOKEN_TAG, "")) for e in es}
        tk = {x for x in tk if v1.TOKEN.match(x)}
        if v1.TOKEN_FILTER and entry_root and not tk:
            stats["tracesExcludedNoToken"] += 1
            stats["spansExcludedNoToken"] += len(es)
            continue
        keep[tid] = tk
        if entry_root and tk:
            svc_of = {e.get("spanId"): e.get("service") for e in es}
            for e in es:
                ps = svc_of.get(e.get("parentSpanId"))
                if ps and e.get("service") and ps != e.get("service"):
                    edges.add((ps, e.get("service")))
    out, toks, ends = [], defaultdict(lambda: defaultdict(set)), defaultdict(dict)
    own = defaultdict(lambda: defaultdict(set))
    for e in uniq:
        if e.get("traceId") not in keep:
            continue
        if e.get("startTimeUs") is None or e.get("durationUs") is None or not e.get("service") or not e.get("operation"):
            stats["spansUnusable"] += 1
            continue
        tok = S.op_token(e["operation"])
        m = stream_meta(SUT, posture, "span", e["service"], "application", "jaeger", "wall", "per-record")
        t, d = e["startTimeUs"] / US_PER_S, e["durationUs"] / US_PER_S
        out.append(Event("span", e["service"], tok, t, d, m))
        names = [tok]
        if S.span_error(e):
            out.append(Event("span", e["service"], tok + ":error", t, d, m))
            names.append(tok + ":error")
        mine = str((e.get("tags") or {}).get(v1.TOKEN_TAG, ""))
        if v1.TOKEN.match(mine):                       # decision 57: the span's own token (the tokened root)
            for nm in names:
                own[(e["service"], nm)][t + d].add(mine)
        if keep[e["traceId"]]:
            for nm in names:
                toks[(e["service"], nm)][t + d] |= keep[e["traceId"]]
            for tk in keep[e["traceId"]]:
                ends[tk][e["service"]] = max(ends[tk].get(e["service"], t + d), t + d)
    stats["spansKept"] += len(out)
    stats["spansWithOwnToken"] += sum(len(v) for x in own.values() for v in x.values())
    return out, {k: dict(v) for k, v in toks.items()}, edges, keys, dict(ends), {k: dict(v) for k, v in own.items()}


Req = namedtuple("Req", "start end ok route seq sched token wallStart wallEnd")


def read_ledger(attempt, plan):
    """v1.read_ledger's rows (start, end, ok, route, sequence, scheduled; its ok rule) + (token, startedAt, endedAt as
    epoch s) as `Req`, sorted by end; and the stamps' representation granularity. dt.ledger_rules and v1's helpers
    index the first six fields, which keep v1's order."""
    extra, mono, iso = {}, [], []
    for i, line in enumerate((attempt / "opportunity-ledger.jsonl").open()):
        row = json.loads(line)
        ws = dt.epoch(row["startedAt"]) if row.get("startedAt") else None
        we = dt.epoch(row["endedAt"]) if row.get("endedAt") else None
        mono += [float(row["actualStartMonotonic"]), float(row["actualEndMonotonic"])]
        iso += [iso_digits(row.get("startedAt")), iso_digits(row.get("endedAt"))]
        extra[int(row.get("sequence", i))] = (row.get("opaqueToken"), ws, we)
    reqs = [Req(s, e, ok, route, seq, sched, *extra[seq]) for s, e, ok, route, seq, sched in v1.read_ledger(attempt, plan)]
    info = {"monoGranularity": granularity(mono), "wallGranularity": (DECIMAL_BASE ** -max(iso)) if iso else None}
    return reqs, info


def fit_alignment(reqs):
    """Per-cell wall = monotonic + offset over the ledger's own paired stamps (H3 b): offset = median of the
    differences, residual = the largest absolute deviation from it."""
    d = [w - m for r in reqs for w, m in ((r.wallStart, r.start), (r.wallEnd, r.end)) if w is not None]
    if not d:
        return None
    off = statistics.median(d)
    return {"offset": off, "residual": max(abs(x - off) for x in d), "pairs": len(d)}


def read_docker_events(attempt):
    p = attempt / "docker-events.jsonl"
    if not p.exists():
        return None
    out = []
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            attrs = (r.get("Actor") or {}).get("Attributes") or {}
            out.append({"action": r.get("Action") or r.get("status"), "service": attrs.get("com.docker.compose.service"),
                        "timeNano": r.get("timeNano")})
    return out


def read_depends(attempt):
    p = attempt / "compose-rendered.yml"
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text())
    except ValueError:
        return None
    out = {}
    for s, d in (doc.get("services") or {}).items():
        dep = d.get("depends_on") or {}
        out[s] = sorted(dep) if isinstance(dep, (dict, list)) else []
    return out


def load_cell(attempt):
    attempt = Path(attempt)
    c = hotel.parse_cell(attempt, "sweep")       # metrics, validity, target (unchanged)
    contract = json.loads((attempt / "cell-contract.json").read_text())
    timing = contract.get("timing") or {}
    plan = json.loads((attempt / "opportunity-plan.json").read_text())
    stats = Counter()
    log_ev, text, log_tok, receipt = read_logs(attempt, c["posture"], stats)
    span_ev, span_tok, edges, span_keys, span_ends, span_own = read_spans(attempt, c["posture"], stats)
    ev = [e for e in c.pop("events") if e.channel not in ("log", "span", "ledger")] + (log_ev or []) + (span_ev or [])
    c["channels"]["log"]["present"] = log_ev is not None
    c["channels"]["span"]["present"] = span_ev is not None
    c["streams"] = group(ev)
    c["chans"] = {"ledger"} | {k.split(":")[0] for k, v in c["channels"].items() if v.get("present")}
    c["prep"] = dt.prep_streams(c)
    c.pop("streams")
    bw, bm = c["base"]["wall"], c["base"]["mono"]
    c["rate"] = float(timing.get("requestsPerSecond", contract.get("runKey", {}).get("requestsPerSecond")))
    c["timing"] = timing
    c["ledger"], c["ledgerStamps"] = read_ledger(attempt, plan)
    al = fit_alignment(c["ledger"])
    if al is None:
        raise ValueError("no ledger wall/monotonic stamp pairs for the clock-alignment fit")
    c["align"] = al
    off = al["offset"]
    dur = float(plan["durationSeconds"])
    c["t0"] = {"wall": bw, "mono": bm}
    c["end"] = {"mono": bm + dur, "wall": bm + dur + off}
    c["probes"] = {"mono": [], "wall": []}
    c["probeWindows"] = []
    c["dockerEvents"] = read_docker_events(attempt)
    c["depends"] = read_depends(attempt)
    c["logText"], c["logTok"], c["logReceipt"], c["spanTok"], c["spanEdges"] = text, log_tok, receipt, span_tok, edges
    c["spanKeys"] = sorted(span_keys)
    c["spanEnds"] = span_ends
    c["spanOwnTok"] = span_own
    c["family"] = lambda ch, coll, posture: hotel.family(ch, coll, posture)
    c["channelsPresent"] = {k: bool(v.get("present")) for k, v in c["channels"].items()}
    c["wsLogs"] = dt.whole_second_logs([c])[0]
    c["planSha256"] = contract.get("compiledPlanCanonicalSha256")
    c["admissionSha256"] = contract.get("admissionCanonicalSha256")
    c["ledgerTok"] = defaultdict(set)
    for r in c["ledger"]:
        if r.token:
            c["ledgerTok"][r.end].add(r.token)
    if c["target"]:
        r = json.loads((attempt / "fault-receipt.json").read_text())
        a, b = float(r["startedMonotonic"]), float(r["revertingMonotonic"])
        c["cmd"] = {"A": {"mono": a, "wall": a + off}, "B": {"mono": b, "wall": b + off},
                    "commandSeconds": float(r["appliedMonotonic"]) - a if r.get("appliedMonotonic") is not None else None,
                    "onsetSource": "fault-receipt startedMonotonic"}
        wins = v1.probe_windows(r)
        c["probeWindows"] = [{"kind": k, "startMono": lo, "endMono": hi, "seconds": hi - lo} for lo, hi, k in wins]
        c["probes"] = {"mono": [(lo, hi) for lo, hi, _ in wins], "wall": [(lo + off, hi + off) for lo, hi, _ in wins]}
        c["receiptGranularity"] = granularity([r.get(k) for k in ("startedMonotonic", "appliedMonotonic",
                                                                  "revertingMonotonic", "readyAtMonotonic")])
        c["onset"] = onset_interval(c, r)
        c["seg"] = {"mono": (bm, a), "wall": (bw, a + off), "closed": False}
    else:
        c["cmd"] = None
        c["seg"] = {"mono": (bm, bm + dur), "wall": (bw, bm + dur + off), "closed": True}
    c["readStats"] = dict(stats)
    c["reason"] = None
    segment_stats(c)
    return c


def onset_interval(c, receipt):
    """H4: [startedMonotonic, effect bound] on the monotonic clock."""
    lo = float(receipt["startedMonotonic"])
    out = {"lo": lo, "loSource": "fault-receipt startedMonotonic", "hi": None, "hiSource": None}
    if c["faultKind"] in dt.STOPPING:
        ev = [e for e in (c["dockerEvents"] or []) if e["action"] == c["faultKind"] and e["service"] == c["target"]
              and e["timeNano"] is not None]
        if ev:
            t = min(e["timeNano"] for e in ev) / NS_PER_S - c["align"]["offset"]
            out.update(hi=t, hiSource="docker-events.jsonl `%s` of %s (timeNano, wall -> monotonic by the cell's fit)"
                       % (c["faultKind"], c["target"]))
        else:
            out["hiSource"] = "no docker `%s` event of %s: —" % (c["faultKind"], c["target"])
    elif receipt.get("appliedMonotonic") is not None:
        out.update(hi=float(receipt["appliedMonotonic"]), hiSource="fault-receipt appliedMonotonic")
    return out


def segment_stats(c):
    """The cell's fault-free segment per stream: level values (probe-excluded, scope rule), record counts and largest
    gap (liveness: every record), the instrument resolution (smallest positive step between distinct values)."""
    scope = {ENTRY, c["target"]} if c["target"] else set()
    closed = c["seg"]["closed"]
    level, count, res = {}, {}, {}

    def cut(times, lo, hi):
        return bisect.bisect_left(times, lo), (bisect.bisect_right(times, hi) if closed else bisect.bisect_left(times, hi))

    def note_res(inst, vals):
        g = min_positive_gap(vals)
        if g is not None and (res.get(inst) is None or g < res[inst]):
            res[inst] = g
    for key, (obs, vals, meta) in c["prep"].items():
        ch, svc, tok = key
        if ch not in c["chans"]:
            continue
        clk = meta["clock"]
        lo, hi = c["seg"][clk]
        if ch == "log" and c["wsLogs"] and not closed:
            hi = math.floor(hi)
        i0, i1 = cut(obs, lo, hi)
        wins = c["probes"][clk] if (svc in scope and ch in ("log", "metric")) else ()
        kept = [i for i in range(i0, i1) if not v1.in_any(obs[i], wins)] if wins else list(range(i0, i1))
        if ch in ("log", "span"):
            count[key] = (i1 - i0, max_gap(obs[i0:i1]), len(kept))
        if ch == "metric" or (ch == "span" and not tok.endswith(":error")):
            vs = [vals[i] for i in kept]
            level[key] = vs
            note_res(instrument(ch, meta, tok), vs)
    routes = sorted({r.route for r in c["ledger"]})
    lo, hi = c["seg"]["mono"]
    for route in routes:
        rr = [r for r in c["ledger"] if r.route == route]
        ends = [r.end for r in rr]
        i0, i1 = cut(ends, lo, hi)
        seg = rr[i0:i1]
        lat = [(r.end - r.start) * MS_PER_S for r in seg if r.ok]
        level[("ledger", ENTRY, route)] = lat
        note_res(("ledger",), lat)
        count[("ledger", ENTRY, route + COMPLETIONS)] = (len(seg), max_gap([r.end for r in seg]), len(seg))
    c["segLevel"], c["segCount"], c["segRes"] = level, count, res


# =========================================================================== gatekeeping (v1's rules, v2's loader)

def load_or_invalid(d):
    d = Path(d)
    try:
        contract = json.loads((d / "cell-contract.json").read_text())
    except (OSError, ValueError) as exc:
        return v1.invalid_cell(d, None, "cell-contract.json unreadable: %s" % exc)
    term = d / "cell-terminal.json"
    if not term.exists():
        return v1.invalid_cell(d, contract, "no cell-terminal.json (the cell did not finish)")
    try:
        verdict = json.loads(term.read_text()).get("candidateCellValid")
    except (OSError, ValueError, AttributeError) as exc:
        return v1.invalid_cell(d, contract, "cell-terminal.json unreadable: %s" % exc)
    if verdict is not True:
        return v1.invalid_cell(d, contract, "candidateCellValid is %r" % (verdict,))
    regime = (contract.get("runKey") or {}).get("regime")
    if regime not in (NOFAULT,) + FAULT_REGIMES:
        return v1.invalid_cell(d, contract, "unknown regime %r" % (regime,))
    has_receipt = (d / "fault-receipt.json").exists()
    if has_receipt != (regime != NOFAULT):
        return v1.invalid_cell(d, contract, "%s fault-receipt.json for regime %s" % ("a" if has_receipt else "no", regime))
    try:
        c = load_cell(d)
    except Exception as exc:  # noqa: BLE001 - recorded per cell; the readout must still be written
        return v1.invalid_cell(d, contract, "parse error: %s: %s" % (type(exc).__name__, exc))
    if (c["target"] is None) != (regime == NOFAULT):
        return v1.invalid_cell(d, contract, "target %r for regime %s" % (c["target"], regime))
    if regime != NOFAULT and c["target"] != FAULT_TARGETS[regime][0]:
        return v1.invalid_cell(d, contract, "receipt target %r, regime %s expects %r" % (
            c["target"], regime, FAULT_TARGETS[regime][0]))
    return c


# =========================================================================== v2.2 readers: TeaStore and OTel
# Written from the harness code that writes the cells (TeaStore 91c4967: modules/teastore/execution/performance_campaign.py, modules/teastore/workload/fixed_load.py,
# modules/teastore/collectors/kieker_native.py, modules/teastore/collectors/system_probe.py, modules/teastore/witness/extract_native_token_correlation.py; OTel 6e37ec2: modules/otel-demo/execution/candidate_remote.py
# run_sweep_cell, validation/candidate_terminal.py) and tested on cells the harnesses' own fixtures write
# (tests/fixtures/sweep_v22); no TeaStore or OTel evidence was read. Each maps its cell onto the model Hotel's
# load_cell produces: ledger rows (Req), the fault receipt and onset interval, spans with request tokens, logs with
# Docker receive stamps, metric samples, probe windows. A file the pinned harness does not write that way stops the
# run (UnknownSchema); a cell the harness itself did not validate is listed, never scored.

BLOCKED_SUFFIX = ".blocked-evidence"                  # TeaStore performance_campaign.BLOCKED_EVIDENCE_SUFFIX
TS_BRIDGE_KEYS = ("nativeTraceId", "service", "token")  # extract_native_token_correlation.BRIDGE_KEYS
TRACEPARENT_RX = re.compile(r"\b00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}\b")   # W3C Trace Context, version 00
GENERIC_LAYOUTS = ("json-line", "plain-line")


def _campaign_root(campaign):
    campaign = Path(campaign)
    if not (campaign / "runs").is_dir():
        kids = [d for d in campaign.iterdir() if (d / "runs").is_dir()] if campaign.is_dir() else []
        if len(kids) != 1:
            raise SystemExit("no runs/ under %s (and not exactly one child holding one)" % campaign)
        campaign = kids[0]
    return campaign


def _not_scored(d, regime, rate, block, reason):
    """A cell that is listed, never scored (v1.invalid_cell's record)."""
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = None
    return {"cell": common.rel(d), "regime": regime or "?", "rate": rate, "block": block, "valid": False,
            "target": None, "reason": reason, "readStats": {}, "planSha256": None, "admissionSha256": None}


def _read_json(path):
    return json.loads(Path(path).read_text())


def otel_adapter():
    """research/otel-offpath/adapter.py, loaded by path and never edited (as sensor_rep/parsers/otel.py)."""
    return common.load("sensor_rep_otel_adapter", common.RESEARCH / "otel-offpath" / "adapter.py")


def parse_json_line(line):
    """LOG_LAYOUTS `json-line`: a JSON object; key = its sorted top-level keys, message = key=value pairs (masked by
    the template), level from a `level` / `severity` string by the OTel adapter's severity names."""
    s = line.strip()
    if not s.startswith("{"):
        return None
    try:
        o = json.loads(s)
    except ValueError:
        return None
    if not isinstance(o, dict) or not o:
        return None
    word = next((o[k] for k in ("level", "severity") if isinstance(o.get(k), str)), None)
    keys = sorted(o)
    msg = " ".join("%s=%s" % (k, json.dumps(o[k], sort_keys=True) if isinstance(o[k], (dict, list)) else o[k])
                   for k in keys)
    return common.symptoms().rec("json-line", otel_adapter()._severity("", word) if word else None,
                                 json_stamp(o) if JSON_LINE_STAMP else None, ",".join(keys), msg)


def _unit_seconds(value, unit):
    """A number in the registry's unit (`s` or `ms`) as seconds; None for anything else."""
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or unit not in ("s", "ms"):
        return None
    return x / MS_PER_S if unit == "ms" else x


def _iso_seconds(value):
    """A zoned ISO-8601 / RFC 3339 string as epoch seconds; None without a zone (local time is not recorded)."""
    if not isinstance(value, str):
        return None
    try:
        d = _dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.timestamp() if d.tzinfo is not None else None


def json_stamp(o):
    """F3 (JSON_LOG_STAMP_RULE): a json-line record's own stamp, only in the forms the harness source writes: Envoy's
    access log start + duration (written at completion), else `timestamp` / `time` / `ts` as a zoned ISO string, or as
    a number where the source fixes its unit (pino's `time`, epoch ms). None: no stamp (the line's lead is not counted,
    LOG_RECEIPT_RULE)."""
    rule = JSON_STAMP_RULE
    for pr in rule["pairs"]:
        if pr["start"] in o and pr["duration"] in o:
            a, d = _unit_seconds(o[pr["start"]], pr["startUnit"]), _unit_seconds(o[pr["duration"]], pr["durationUnit"])
            return None if a is None or d is None else a + d
    for fld in rule["fields"]:
        v = o.get(fld["key"])
        if v is None:
            continue
        t = _iso_seconds(v) if isinstance(v, str) else (
            _unit_seconds(v, fld["number"]) if fld.get("number") else None)
        if t is not None:
            return t
    return None


def parse_plain_line(line):
    """LOG_LAYOUTS `plain-line`: any non-indented line starts a record (an indented one continues the previous)."""
    if not line.strip() or line[:1].isspace():
        return None
    return common.symptoms().rec("plain-line", None, None, None, line.strip())


def log_layouts(system):
    S = common.symptoms()
    by = {"zerolog-json": S.parse_zerolog_json, "zerolog-console": S.parse_zerolog_console, "go-log": S.parse_go_log,
          "log4j": S.parse_log4j, "jul": S.parse_jul, "mariadb": S.parse_mariadb, "jvm-throwable": S.parse_throwable,
          "json-line": parse_json_line, "plain-line": parse_plain_line}
    return tuple(by[n] for n in LOG_LAYOUT_NAMES[system])


def token_regex(system):
    return re.compile(TOKEN_SOURCES[system]["pattern"].lstrip("^").rstrip("$"))


def read_compose_log(path, posture, stats, layouts, token_rx, trace_rx=None):
    """`docker compose logs --timestamps` (application.log) -> (events | None, {(svc, template): (level, masked msg)},
    {(svc, template): {t: tokens named}}, {(svc, template): {t: trace ids named}}, receipt info). v1.read_logs and
    Hotel's read_logs with the system's layouts: a record is timed at its first line's Docker receive stamp; its own
    stamp, where the layout parses one, gives the per-cell receipt-delay bound (LOG_RECEIPT_RULE)."""
    S = common.symptoms()
    info = {"bound": None, "servicesWithoutAppStamp": [], "dockerDigits": None, "linesWithBoth": 0}
    if not path.exists():
        return None, {}, {}, {}, info
    lines, stamps, digits = defaultdict(list), defaultdict(list), []
    for raw in path.read_text(errors="replace").splitlines():
        if " | " not in raw:
            stats["composeCliLines"] += 1
            continue
        prefix, payload = raw.split(" | ", 1)
        svc = prefix.strip().rsplit("-", 1)[0]
        m = v1.DOCKER_TS.match(payload)
        t, rest = v1.docker_stamp(payload)
        if t is None:
            stats["logLinesWithoutDockerStamp"] += 1
        else:
            stats["logLinesWithDockerStamp"] += 1
            digits.append(len(m.group(2) or ""))
        lines[svc].append(rest)
        stamps[svc].append(t)
    evs, text, delays = [], {}, []
    toks, traces = defaultdict(lambda: defaultdict(set)), defaultdict(lambda: defaultdict(set))
    for svc in sorted(lines):
        st = stamps[svc]
        stamped = any(x is not None for x in st)
        at = S.parse_stream(lines[svc], layouts, stamp=lambda i: i)[0]     # each record's first line
        own, pst = S.parse_stream(lines[svc], layouts)
        for k, v in pst.items():
            stats["log:" + k] += v
        if len(at) != len(own):
            raise ValueError("log records of %s do not correspond between the two parses" % svc)
        app_seen = False
        for ri, r in zip(at, own):
            if r["framework"] == "jvm-throwable":
                continue                                     # no template (symptoms.log_symbols)
            t = st[ri["t"]] if stamped else r["t"]
            tid = S.template_id(r["framework"], r["level"], r["key"], r["msg"])
            lv = "undefined" if (r["framework"] in GENERIC_LAYOUTS and r["level"] is None) else \
                level_class(r["framework"], r["level"])
            stats["logRecords"] += 1
            if t is None:
                stats["logRecordsUntimed"] += 1
            meta_ = stream_meta(SUT, posture, "log", svc, "application", "compose-logs", "wall", "per-record", lv)
            evs.append(Event("log", svc, tid, t, 1.0, meta_))
            text.setdefault((svc, tid), (lv, S.mask(r["msg"])[:LOG_TEXT_CHARS]))
            if r["t"] is not None:
                app_seen = True
                if stamped and t is not None:
                    delays.append(t - r["t"])
            if t is not None:
                found = set(token_rx.findall(r["msg"] or ""))
                if found:
                    toks[(svc, tid)][t] |= found
                if trace_rx is not None:
                    tr = set(trace_rx.findall(r["msg"] or ""))
                    if tr:
                        traces[(svc, tid)][t] |= tr
        if stamped and not app_seen:
            info["servicesWithoutAppStamp"].append(svc)
    info.update(bound=max(delays) if delays else None, linesWithBoth=len(delays),
                dockerDigits=max(digits) if digits else None)
    return evs, text, {k: dict(v) for k, v in toks.items()}, {k: dict(v) for k, v in traces.items()}, info


def finish_cell(c, ev, logs, spans, stats):
    """The model's remaining fields (as Hotel's load_cell): streams, channels, tokens, whole-second flag, segments.
    logs = (text, tokens, trace tokens, receipt info); spans = (tokens, own tokens, edges, keys, ends)."""
    c["streams"] = group(ev)
    c["chans"] = {"ledger"} | {k.split(":")[0] for k, v in c["channels"].items() if v.get("present")}
    c["prep"] = dt.prep_streams(c)
    c.pop("streams")
    c["logText"], c["logTok"], c["logTraceTok"], c["logReceipt"] = logs
    c["spanTok"], c["spanOwnTok"], c["spanEdges"], keys, c["spanEnds"] = spans
    c["spanKeys"] = sorted(keys)
    c["channelsPresent"] = {k: bool(v.get("present")) for k, v in c["channels"].items()}
    c["wsLogs"] = dt.whole_second_logs([c])[0]
    c["ledgerTok"] = defaultdict(set)
    for r in c["ledger"]:
        if r.token:
            c["ledgerTok"][r.end].add(r.token)
    c["readStats"] = dict(stats)
    c["reason"] = None
    segment_stats(c)
    return c


def _fault_windows(c, a, b, wins):
    off = c["align"]["offset"]
    c["probeWindows"] = [{"kind": k, "startMono": lo, "endMono": hi, "seconds": hi - lo} for lo, hi, k in wins]
    c["probes"] = {"mono": [(lo, hi) for lo, hi, _ in wins], "wall": [(lo + off, hi + off) for lo, hi, _ in wins]}
    c["seg"] = {"mono": (c["base"]["mono"], a), "wall": (c["base"]["wall"], a + off), "closed": False}


def _nofault_windows(c):
    bm, bw, dur, off = c["base"]["mono"], c["base"]["wall"], c["duration"], c["align"]["offset"]
    c["cmd"] = None
    c["probes"], c["probeWindows"] = {"mono": [], "wall": []}, []
    c["seg"] = {"mono": (bm, bm + dur), "wall": (bw, bm + dur + off), "closed": True}


# --------------------------------------------------------------------------- TeaStore (harness 91c4967)

def teastore_find_cells(campaign):
    """runs/<regime>/b<BB>-<OO>-<posture> with receipt.json (modules/teastore/execution/performance_campaign.py, modules/teastore/execution/candidate_cell_executor.py);
    `.blocked-evidence` directories are listed as not scored."""
    root = _campaign_root(campaign)
    return root, sorted(d for d in (root / "runs").glob("*/*") if d.is_dir() and (
        (d / "receipt.json").exists() or d.name.endswith(BLOCKED_SUFFIX)))


def teastore_load_or_invalid(d):
    d = Path(d)
    if d.name.endswith(BLOCKED_SUFFIX):
        return _not_scored(d, d.parent.name, None, None, "blocked evidence (the producer refused the cell)")
    try:
        rc = _read_json(d / "receipt.json")
    except (OSError, ValueError) as exc:
        return _not_scored(d, d.parent.name, None, None, "receipt.json unreadable: %s" % exc)
    check_schema(rc, "%s receipt.json" % d.name, dict(SCHEMAS["teastore"]["receipt.json"],
                                                      studyEpoch=param("SYSTEM_TEASTORE")["studyEpochs"]))
    run_, timing = rc.get("run") or {}, rc.get("timing") or {}
    regime, rate, block = run_.get("regime"), timing.get("journeysPerSecond"), run_.get("block")
    vp = d / "candidate-validation.json"
    if not vp.exists():
        return _not_scored(d, regime, rate, block, "no candidate-validation.json (the cell did not finish)")
    try:
        val = _read_json(vp)
    except (OSError, ValueError) as exc:
        return _not_scored(d, regime, rate, block, "candidate-validation.json unreadable: %s" % exc)
    check_schema(val, "%s candidate-validation.json" % d.name, SCHEMAS["teastore"]["candidate-validation.json"])
    if val.get("verdict") != "pass" or val.get("cellStatus") != "valid":
        return _not_scored(d, regime, rate, block, "candidate-validation verdict %r, cellStatus %r" % (
            val.get("verdict"), val.get("cellStatus")))
    if regime not in (NOFAULT,) + FAULT_REGIMES:
        return _not_scored(d, regime, rate, block, "unknown regime %r" % (regime,))
    has = (d / "intervention.json").exists()
    if has != (regime != NOFAULT):
        return _not_scored(d, regime, rate, block, "%s intervention.json for regime %s" % ("an" if has else "no", regime))
    try:
        return teastore_load_cell(d, rc)
    except UnknownSchema:
        raise
    except Exception as exc:  # noqa: BLE001 - recorded per cell; the readout must still be written
        return _not_scored(d, regime, rate, block, "parse error: %s: %s" % (type(exc).__name__, exc))


def teastore_ledger(path, stats):
    """journey-ledger.jsonl -> (Req rows sorted by end, stamp granularities, {sequence: outcome detail}). One row per
    login journey (the unit, DECLARATION_TEASTORE.md); start/end = actualStart/EndMonotonic (seconds from fixed_load's
    barrier), ok = outcome `succeeded` and every request 200 (dt.teastore_ledger's rule), route = workloadId,
    scheduled = scheduledMonotonicOffsetSeconds, token = opaqueToken. A journey that never started is counted."""
    sch = SCHEMAS["teastore"]["journey-ledger.jsonl"]
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    for r in rows:
        check_schema(r, path.name, sch)
    reqs, detail, mono, iso = [], {}, [], []
    for r in sorted((r for r in rows if r["recordType"] == "journey-terminal"), key=lambda r: int(r["sequence"])):
        s, e = r.get("actualStartMonotonic"), r.get("actualEndMonotonic")
        if s is None or e is None:
            stats["journeysWithoutStart"] += 1
            continue
        q = r.get("requests") or []
        ok = r.get("outcome") == "succeeded" and bool(q) and all(x.get("statusCode") == HTTPStatus.OK for x in q)
        status = q[-1].get("statusCode") if q else None
        detail[int(r["sequence"])] = {"outcome": r.get("outcome"), "status": status,
                                      "errors": [x.get("type") for x in r.get("errors") or []],
                                      "errorAnswer": (not ok) and r.get("outcome") != "timeout" and status is not None}
        reqs.append(Req(float(s), float(e), ok, r["workloadId"], int(r["sequence"]),
                        float(r["scheduledMonotonicOffsetSeconds"]), r.get("opaqueToken"),
                        dt.epoch(r["startedAt"]) if r.get("startedAt") else None,
                        dt.epoch(r["endedAt"]) if r.get("endedAt") else None))
        mono += [float(s), float(e)]
        iso += [iso_digits(r.get("startedAt")), iso_digits(r.get("endedAt"))]
    reqs.sort(key=lambda r: r.end)
    return reqs, {"monoGranularity": granularity(mono),
                  "wallGranularity": (DECIMAL_BASE ** -max(iso)) if iso else None}, detail


def teastore_bridge(path, stats):
    """auth.log bridge lines -> {Kieker trace_id: token} (TOKEN_SOURCES; the harness's reconcile rules: one trace per
    token, one token per trace; a pair outside them gives no token and is counted). A bridge line outside the fixed
    schema stops the run (the harness's validator refuses such a cell)."""
    src = TOKEN_SOURCES["teastore"]
    marker, tok_rx = src["bridgeMarker"], re.compile(src["pattern"])
    if not path.exists():
        stats["bridgeLogMissing"] += 1
        return {}
    pairs = set()
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if marker not in line:
            continue
        try:
            row = json.loads(line.split(marker, 1)[1]) if line.count(marker) == 1 else None
        except ValueError:
            row = None
        if (not isinstance(row, dict) or set(row) != set(TS_BRIDGE_KEYS) or row.get("service") != "auth"
                or not isinstance(row.get("token"), str) or not tok_rx.match(row["token"])
                or not re.fullmatch(r"-?(0|[1-9][0-9]*)", str(row.get("nativeTraceId"))) or
                str(row.get("nativeTraceId")) == "-1"):
            raise UnknownSchema("auth.log line %d: bridge row outside the fixed schema (harness 91c4967)" % n)
        pairs.add((row["token"], str(row["nativeTraceId"])))
    by_tok, by_trace = defaultdict(set), defaultdict(set)
    for tk, tid in pairs:
        by_tok[tk].add(tid)
        by_trace[tid].add(tk)
    bad_tok = {tk for tk, tids in by_tok.items() if len(tids) > 1}
    bad_tr = {tid for tid, tks in by_trace.items() if len(tks) > 1}
    out = {tid: next(iter(tks)) for tid, tks in by_trace.items() if tid not in bad_tr and next(iter(tks)) not in bad_tok}
    stats["bridgeTokensWithSeveralTraces"] += len(bad_tok)          # F11: counted per token / per trace
    stats["bridgeTracesWithSeveralTokens"] += len(bad_tr)
    stats["bridgeRowsDropped"] += sum(1 for tk, tid in pairs if tid not in out)
    stats["bridgeMappings"] += len(out)
    return out


def teastore_spans(d, posture, stats, probes_wall):
    """traces.json (Kieker events, modules/teastore/collectors/kieker_native.py) -> span events (start tin, value tout - tin; error token as
    sensor_rep's TeaStore parser) and, per (service, op), the token of the trace each span end belongs to (the auth
    bridge); untokened webui-rooted traces starting in a probe window are not read (PROBE_TRACE_RULE)."""
    S = common.symptoms()
    p = d / "traces.json"
    if not p.exists():
        return None, ({}, {}, set(), set(), {})
    evs = _read_json(p)
    if not isinstance(evs, list):
        raise UnknownSchema("%s traces.json is not an array" % d.name)
    bridge = teastore_bridge(d / "auth.log", stats)
    need = ("trace_id", "span_id", "parent_span_id", "service", "operation", "tin", "tout")
    keys, seen, uniq = set(), set(), []
    for e in evs:
        check_schema(e, "%s traces.json event" % d.name, SCHEMAS["teastore"]["traces.json"])
        if any(k not in e for k in need):
            raise UnknownSchema("%s traces.json: an event lacks %s" % (d.name, [k for k in need if k not in e]))
        keys.update(e)
        key = (str(e["trace_id"]), e["span_id"])
        if key in seen:
            stats["duplicateSpans"] += 1
            continue
        seen.add(key)
        uniq.append(e)
    by_trace = defaultdict(list)
    for e in uniq:
        by_trace[str(e["trace_id"])].append(e)
    keep, edges = {}, set()
    for tid, es in by_trace.items():
        tk = {bridge[tid]} if tid in bridge else set()
        roots = [e for e in es if e.get("parent_span_id") == "" and e.get("service") == ENTRY]
        if PROBE_TRACE_FILTER and roots and not tk and v1.in_any(min(e["tin"] for e in roots) / NS_PER_S, probes_wall):
            stats["probeTracesExcluded"] += 1
            stats["probeSpansExcluded"] += len(es)
            continue
        keep[tid] = tk
        if not tk:
            stats["tracesWithoutToken"] += 1
        if roots and tk:
            svc_of = {e["span_id"]: e["service"] for e in es}
            for e in es:
                ps = svc_of.get(e.get("parent_span_id"))
                if ps and ps != e["service"] and "unknown" not in (ps, e["service"]):
                    edges.add((ps, e["service"]))
    out, toks, ends = [], defaultdict(lambda: defaultdict(set)), defaultdict(dict)
    for e in uniq:
        tid = str(e["trace_id"])
        if tid not in keep:
            continue
        if e["service"] in (None, "", "unknown") or e["tin"] is None or e["tout"] is None or not e["operation"]:
            stats["spansUnusable"] += 1
            continue
        tok = S.op_token(e["operation"])
        m = stream_meta(SUT, posture, "span", e["service"], "application", "kieker", "wall", "per-record")
        t, du = e["tin"] / NS_PER_S, (e["tout"] - e["tin"]) / NS_PER_S
        out.append(Event("span", e["service"], tok, t, du, m))
        names = [tok]
        if e.get("status_code") not in (None, HTTPStatus.OK, 0):
            out.append(Event("span", e["service"], tok + ":error", t, du, m))
            names.append(tok + ":error")
        for nm in names if keep[tid] else ():
            toks[(e["service"], nm)][t + du] |= keep[tid]
        for tk_ in keep[tid]:
            ends[tk_][e["service"]] = max(ends[tk_].get(e["service"], t + du), t + du)
    stats["spansKept"] += len(out)
    return out, ({k: dict(v) for k, v in toks.items()}, {}, edges, keys, dict(ends))


def teastore_samples(path, posture, wall_of, stats):
    """system-samples.json (modules/teastore/collectors/system_probe.py, cgroup v2 every 5 s) -> Hotel's sampler tokens: sys_cpu (cores),
    sys_memory (bytes), sys_io (bytes/s), sys_psi_{cpu,memory,io} (stall usec/s), each rate over consecutive samples
    by their `monotonic` stamps and timed at the later one (CLOCK_RULE_TEASTORE); a null service row (scope gone) is
    skipped and counted."""
    if not path.exists():
        return None, None
    doc = _read_json(path)
    check_schema(doc, "system-samples.json", SCHEMAS["teastore"]["system-samples.json"])
    rows, res = doc["samples"], doc.get("intervalSeconds")
    svcs = sorted({s for r in rows for s, v in (r.get("services") or {}).items() if v is not None})
    out = []
    for s in svcs:
        m = stream_meta(SUT, posture, "metric", s, "runtime", "cgroup-sampler", "wall", res)
        for r in rows:
            v = (r.get("services") or {}).get(s)
            if v is not None and v.get("memoryCurrent") is not None:
                out.append(Event("metric", s, "sys_memory", wall_of(r["monotonic"]), float(v["memoryCurrent"]), m))
        for a, b in zip(rows, rows[1:]):
            va, vb = (a.get("services") or {}).get(s), (b.get("services") or {}).get(s)
            span = float(b["monotonic"]) - float(a["monotonic"])
            if va is None or vb is None or span <= 0:
                stats["samplePairsSkipped"] += 1
                continue
            t = wall_of(b["monotonic"])
            for tok, key, scale in (("sys_cpu", "cpuUsageUsec", 1.0 / US_PER_S), ("sys_psi_cpu", "psiCpuSomeTotalUsec", 1.0),
                                    ("sys_psi_memory", "psiMemorySomeTotalUsec", 1.0),
                                    ("sys_psi_io", "psiIoSomeTotalUsec", 1.0)):
                if va.get(key) is not None and vb.get(key) is not None:
                    out.append(Event("metric", s, tok, t, (vb[key] - va[key]) / span * scale, m))
            if all(x.get(k) is not None for x in (va, vb) for k in ("rbytes", "wbytes")):
                out.append(Event("metric", s, "sys_io", t,
                                 ((vb["rbytes"] + vb["wbytes"]) - (va["rbytes"] + va["wbytes"])) / span, m))
    return out, res


def teastore_family(ch, coll, posture):
    return {"log": "L", "span": "T"}.get(ch) or ("S" if coll == "cgroup-sampler" else "M")


def teastore_load_cell(d, rc):
    sch = SCHEMAS["teastore"]
    timing, run_ = dict(rc["timing"]), rc["run"]
    if float(timing["requestTimeoutSeconds"]) != param("CLIENT_TIMEOUT_S_TEASTORE"):
        raise UnknownSchema("%s: requestTimeoutSeconds %r, declared %r (CLIENT_TIMEOUT_S_TEASTORE)" % (
            d.name, timing["requestTimeoutSeconds"], param("CLIENT_TIMEOUT_S_TEASTORE")))
    regime, posture = run_["regime"], run_["posture"]
    plan = _read_json(d / "journey-ledger.plan.json")
    check_schema(plan, "journey-ledger.plan.json", sch["journey-ledger.plan.json"])
    stats = Counter()
    reqs, lstamps, detail = teastore_ledger(d / "journey-ledger.jsonl", stats)
    al = fit_alignment(reqs)
    if al is None:
        raise ValueError("no ledger wall/monotonic stamp pairs for the clock-alignment fit")
    off = al["offset"]
    win = rc["window"]
    e_p, m_p = dt.epoch(win["measurementStartedAt"]), float(win["measurementStartMonotonic"])

    shift = (e_p - off) if RECEIPT_CLOCK_MAP else 0.0

    def from_producer(x):                               # CLOCK_RULE_TEASTORE: producer offset -> ledger clock
        return shift + float(x)
    target, kind = FAULT_TARGETS[regime] if regime != NOFAULT else (None, None)
    c = {"sut": SUT, "population": "sweep", "cell": common.rel(d), "posture": posture, "regime": regime,
         "block": run_["block"], "valid": True, "target": target, "faultKind": kind, "noFault": target is None,
         "base": {"wall": dt.epoch(plan["barrierAt"]), "mono": 0.0}, "duration": float(timing["measurementSeconds"]),
         "rate": float(timing["journeysPerSecond"]), "ledger": reqs, "ledgerStamps": lstamps, "ledgerDetail": detail,
         "align": al, "dockerEvents": None, "depends": None, "planSha256": None, "admissionSha256": None,
         "harnessCommit": (rc.get("source") or {}).get("frameworkCommit"), "studyEpoch": rc.get("studyEpoch")}
    c["timing"] = dict(timing, requestsPerSecond=c["rate"])
    c["t0"] = dict(c["base"])
    c["end"] = {"mono": c["base"]["mono"] + c["duration"], "wall": c["base"]["mono"] + c["duration"] + off}
    if target is not None:
        iv = _read_json(d / "intervention.json")
        check_schema(iv, "%s intervention.json" % d.name, sch["intervention.json"])
        if iv.get("service") != target:
            raise ValueError("intervention service %r, regime %s expects %r" % (iv.get("service"), regime, target))
        sw, ready = iv["sweep"], iv["readiness"]
        cs = sw["commandStamps"]
        a = from_producer(cs["onsetCommandIssuedMonotonicOffsetSeconds"])
        ret = from_producer(cs["onsetCommandReturnedMonotonicOffsetSeconds"])
        b = from_producer(cs["revertCommandIssuedMonotonicOffsetSeconds"])
        c["cmd"] = {"A": {"mono": a, "wall": a + off}, "B": {"mono": b, "wall": b + off}, "commandSeconds": ret - a,
                    "onsetSource": "intervention sweep.commandStamps onsetCommandIssuedMonotonicOffsetSeconds "
                                   "(pre-command), producer clock mapped to the ledger's"}
        wins = sorted([(from_producer(p["startMonotonicOffsetSeconds"]), from_producer(p["endMonotonicOffsetSeconds"]),
                        "probe-%s" % p.get("phase")) for p in sw.get("probes") or []]
                      + [(b, from_producer(ready["observedAtMonotonicOffsetSeconds"]), "recovery")])
        _fault_windows(c, a, b, wins)
        c["receiptGranularity"] = granularity(
            [v for k, v in cs.items() if k.endswith("Seconds")] + [ready["observedAtMonotonicOffsetSeconds"]]
            + [p[k] for p in sw.get("probes") or [] for k in ("startMonotonicOffsetSeconds", "endMonotonicOffsetSeconds")])
        pairs = [(cs.get("onsetCommandIssuedWall"), cs.get("onsetCommandIssuedMonotonicOffsetSeconds")),
                 (cs.get("revertCommandIssuedWall"), cs.get("revertCommandIssuedMonotonicOffsetSeconds")),
                 (ready.get("observedAtWall"), ready.get("observedAtMonotonicOffsetSeconds"))] + [
            (x.get("observedAtWall"), x.get("observedAtMonotonicOffsetSeconds")) for x in iv.get("duringStateSamples") or []]
        pairs = [(dt.epoch(w_), float(x)) for w_, x in pairs if w_ and x is not None]
        c["receiptAlign"] = {"offset": e_p - off, "pairs": len(pairs),
                             "residual": max(abs(w_ - (e_p + x)) for w_, x in pairs) if pairs else None,
                             "source": "intervention wall/offset pairs against receipt.window measurementStartedAt"}
        c["onset"] = {"lo": a, "loSource": c["cmd"]["onsetSource"], "hi": ret, "hiKind": "command-returned",
                      "hiSource": "intervention sweep.commandStamps onsetCommandReturnedMonotonicOffsetSeconds (the "
                                  "cell keeps no Docker events: [command issued, command returned])"}
    else:
        _nofault_windows(c)
    span_ev, spans = teastore_spans(d, posture, stats, c["probes"]["wall"])
    log_ev, text, log_tok, log_tr, receipt = read_compose_log(d / "application.log", posture, stats,
                                                               log_layouts("teastore"), token_regex("teastore"))
    met_ev, res_s = teastore_samples(d / "system-samples.json", posture, lambda mono: e_p + float(mono) - m_p, stats)
    c["channels"] = {"log": {"present": log_ev is not None, "file": "application.log"},
                     "span": {"present": span_ev is not None, "file": "traces.json"},
                     "metric:cgroup-sampler": {"present": met_ev is not None, "file": "system-samples.json",
                                               "resolution": res_s},
                     "metric:docker-stats": {"present": False, "file": None}}
    c["familyAbsent"] = {"M": "docker-stats samples (resources.json) are written in no-fault cells only (the frozen "
                              "no-fault-cost path, DECLARATION_TEASTORE.md Regimes): no fault episode has M, so it is "
                              "not read (FAMILY_CHANNELS)"}
    c["family"] = teastore_family
    return finish_cell(c, (log_ev or []) + (span_ev or []) + (met_ev or []), (text, log_tok, log_tr, receipt),
                       spans, stats)


# --------------------------------------------------------------------------- OTel Demo (harness 6e37ec2)

def otel_find_cells(campaign):
    """runs/<artifactRootClass>/r<rate>-b<NN>-<PP>-full with receipt.json (modules/otel-demo/execution/candidate_sweep.py:727-728)."""
    root = _campaign_root(campaign)
    return root, sorted(p.parent for p in (root / "runs").glob("**/receipt.json"))


def otel_load_or_invalid(d):
    d = Path(d)
    try:
        rc = _read_json(d / "receipt.json")
    except (OSError, ValueError) as exc:
        return _not_scored(d, None, None, None, "receipt.json unreadable: %s" % exc)
    check_schema(rc, "%s receipt.json" % d.name, dict(SCHEMAS["otel"]["receipt.json"],
                                                      **{"runKey.studyEpoch": param("SYSTEM_OTEL")["studyEpochs"]}))
    rk = rc.get("runKey") or {}
    regime, rate, block = rk.get("regime"), rk.get("requestsPerSecond"), rk.get("block")
    if rc.get("state") != "valid":
        return _not_scored(d, regime, rate, block, "receipt state %r: %s" % (rc.get("state"), rc.get("error")))
    if regime not in (NOFAULT,) + FAULT_REGIMES:
        return _not_scored(d, regime, rate, block, "unknown regime %r" % (regime,))
    has = (d / "intervention.json").exists()
    if has != (regime != NOFAULT):
        return _not_scored(d, regime, rate, block, "%s intervention.json for regime %s" % ("an" if has else "no", regime))
    try:
        return otel_load_cell(d, rc)
    except UnknownSchema:
        raise
    except Exception as exc:  # noqa: BLE001 - recorded per cell; the readout must still be written
        return _not_scored(d, regime, rate, block, "parse error: %s: %s" % (type(exc).__name__, exc))


def otel_ledger(led, stats):
    """request-ledger.json -> (Req rows sorted by end, granularities, {sequence: outcome detail}, {originalTraceId:
    token}). start/end = started/endedMonotonic (the fault receipt's clock), ok = outcome `ok` (status 200, no
    error), route = the URL path, scheduled = barrierMonotonic + scheduledOffsetSeconds, sequence = row index."""
    sch = SCHEMAS["otel"]["request-ledger.json"]
    if set(led) != set(sch["keys"]):
        raise UnknownSchema("request-ledger.json keys %s, the pinned harness writes %s" % (sorted(led), sch["keys"]))
    bm, route = float(led["barrierMonotonic"]), urlparse(led["url"]).path
    reqs, detail, tt, mono, walls = [], {}, {}, [], []
    for i, q in enumerate(led["requests"]):
        if set(q) != set(sch["rowKeys"]):
            raise UnknownSchema("request-ledger.json row %d keys %s, the pinned harness writes %s" % (
                i, sorted(q), sch["rowKeys"]))
        ok = q["outcome"] == "ok"
        detail[i] = {"outcome": q["outcome"], "status": q["status"], "errors": [q["error"]] if q["error"] else [],
                     "errorAnswer": (not ok) and q["outcome"] != "timeout" and q["status"] is not None}
        reqs.append(Req(float(q["startedMonotonic"]), float(q["endedMonotonic"]), ok, route, i,
                        bm + float(q["scheduledOffsetSeconds"]), q["requestToken"], float(q["startedAtEpoch"]),
                        float(q["endedAtEpoch"])))
        tt[q["originalTraceId"]] = q["requestToken"]
        mono += [q["startedMonotonic"], q["endedMonotonic"]]
        walls += [q["startedAtEpoch"], q["endedAtEpoch"]]
    reqs.sort(key=lambda r: r.end)
    return reqs, {"monoGranularity": granularity(mono), "wallGranularity": granularity(walls)}, detail, tt


def otel_span_records(lines, stats):
    """otelcol.log (debug exporter, detailed, collector 0.108.0) -> span dicts {service, trace, id, parent, name,
    start, end (epoch ns), status}: the adapter's layout rules (adapter.parse_otelcol, which drops the ids), keeping
    the ids; services by adapter.catalog_service (frontend-proxy -> frontendproxy; the collector's own and unknown
    resources are not read and are counted)."""
    A = otel_adapter()
    out, kind, res, in_res, svc, cur = [], None, {}, False, None, None

    def flush():
        nonlocal cur
        if cur is not None and svc is not None:
            if all(cur.get(k) is not None for k in ("trace", "id", "name", "start", "end")):
                out.append(dict(cur, service=svc))
            else:
                stats["spansIncomplete"] += 1
        cur = None
    for raw in lines:
        s = A._payload(raw.rstrip("\r\n")).strip()
        if not s:
            continue
        last = s.rsplit("\t", 1)[-1]
        if last.startswith(("ResourceSpans #", "ResourceMetrics #", "ResourceLog #")):
            flush()
            kind = "spans" if last.startswith("ResourceSpans") else "other"
            res, in_res, svc = {}, False, None
            continue
        if "\tinfo\t" in s or "\twarn\t" in s or "\terror\t" in s:
            flush()
            continue
        if kind != "spans":
            continue
        if s == "Resource attributes:":
            in_res = True
            continue
        if s.startswith("ScopeSpans #"):
            flush()
            if in_res:
                in_res = False
                name = res.get("service.name")
                svc, why = A.catalog_service(name) if name is not None else (None, "noServiceName")
                if why:
                    stats["spanResourcesNotRead:%s" % why] += 1
            continue
        if in_res:
            if s.startswith("-> "):
                k, _, v = s[len("-> "):].partition(": ")
                res[k] = A._attr_value(v)
            continue
        if s.startswith("Span #"):
            flush()
            cur = {}
            continue
        if cur is None or s.startswith("->") or ":" not in s:
            continue
        k, _, v = s.partition(":")
        k, v = k.strip(), v.strip()
        if k == "Trace ID":
            cur["trace"] = v
        elif k == "Parent ID":
            cur["parent"] = v or None
        elif k == "ID":
            cur["id"] = v
        elif k == "Name":
            cur["name"] = v
        elif k == "Start time":
            cur["start"] = A._nanos(v)
        elif k == "End time":
            cur["end"] = A._nanos(v)
        elif k == "Status code":
            cur["status"] = v
    flush()
    return out


def otel_spans(lines, posture, stats, trace_token, probes_wall):
    """Spans -> events and, per (service, op), the token of the request each span end belongs to: its Trace ID equal
    to a ledger row's originalTraceId (TOKEN_SOURCES; the harness's join, candidate_remote.parse_trace_correlation).
    A trace is entry-rooted when a frontendproxy span's parent is not in the trace (the client's injected parent is
    never exported); untokened entry-rooted traces starting in a probe window are not read (PROBE_TRACE_RULE)."""
    S = common.symptoms()
    recs = otel_span_records(lines, stats)
    if not recs and not any("ResourceSpans #" in x for x in lines):
        return None, ({}, {}, set(), set(), {})
    seen, uniq = set(), []
    for e in recs:
        key = (e["trace"], e["id"])
        if key in seen:
            stats["duplicateSpans"] += 1
            continue
        seen.add(key)
        uniq.append(e)
    by_trace = defaultdict(list)
    for e in uniq:
        by_trace[e["trace"]].append(e)
    keep, edges = {}, set()
    for tid, es in by_trace.items():
        tk = {trace_token[tid]} if tid in trace_token else set()
        ids = {e["id"] for e in es}
        roots = [e for e in es if e["service"] == ENTRY and (e.get("parent") is None or e["parent"] not in ids)]
        if PROBE_TRACE_FILTER and roots and not tk and v1.in_any(min(e["start"] for e in roots) / NS_PER_S,
                                                                  probes_wall):
            stats["probeTracesExcluded"] += 1
            stats["probeSpansExcluded"] += len(es)
            continue
        keep[tid] = tk
        if not tk:
            stats["tracesWithoutToken"] += 1
        if roots and tk:
            svc_of = {e["id"]: e["service"] for e in es}
            for e in es:
                ps = svc_of.get(e.get("parent"))
                if ps and ps != e["service"]:
                    edges.add((ps, e["service"]))
    out, toks, ends = [], defaultdict(lambda: defaultdict(set)), defaultdict(dict)
    for e in uniq:
        if e["trace"] not in keep:
            continue
        tok = S.op_token(e["name"])
        m = stream_meta(SUT, posture, "span", e["service"], "application", "otelcol-debug-exporter", "wall",
                        "per-record")
        t, du = e["start"] / NS_PER_S, (e["end"] - e["start"]) / NS_PER_S
        out.append(Event("span", e["service"], tok, t, du, m))
        names = [tok]
        if e.get("status") == "Error":                 # adapter.parse_otelcol's error rule
            out.append(Event("span", e["service"], tok + ":error", t, du, m))
            names.append(tok + ":error")
        tk = keep[e["trace"]]
        for nm in names if tk else ():
            toks[(e["service"], nm)][t + du] |= tk
        for x in tk:
            ends[x][e["service"]] = max(ends[x].get(e["service"], t + du), t + du)
    stats["spansKept"] += len(out)
    keys = {"Trace ID", "Parent ID", "ID", "Name", "Start time", "End time", "Status code"}
    return out, ({k: dict(v) for k, v in toks.items()}, {}, edges, keys, dict(ends))


def otel_metrics(lines, posture, stats):
    """OTLP metric data points in otelcol.log -> metric events by the adapter's own series rules (parse_otelcol /
    metric_series, never edited); resolution = the median export gap (as sensor_rep's OTel parser)."""
    A = otel_adapter()
    parsed = A.parse_otelcol(lines)
    if not parsed["metrics"]:
        return None, None
    gaps = [b - a for ex in parsed.get("exports", {}).values() for ts in ex.values() for a, b in zip(ts, ts[1:])]
    res = statistics.median(gaps) if gaps else None
    out = []
    for svc, series in parsed["metrics"].items():
        for tok, xs in series.items():
            src = "runtime" if tok.startswith(sr_otel.RUNTIME_NS) else "application"   # sensor_rep's OTel rule
            m = stream_meta(SUT, posture, "metric", svc, src, "otlp-debug-exporter", "wall", res)
            for t, x in xs:
                out.append(Event("metric", svc, tok, t, x, m))
    stats["metricPoints"] += sum(len(xs) for sr in parsed["metrics"].values() for xs in sr.values())
    return out, res


def otel_family(ch, coll, posture):
    return {"log": "L", "span": "T", "metric": "M"}.get(ch)


def otel_load_cell(d, rc):
    sch = SCHEMAS["otel"]
    led = _read_json(d / "request-ledger.json")
    check_schema(led, "%s request-ledger.json" % d.name, {k: v for k, v in sch["request-ledger.json"].items()
                                                          if k in ("schemaVersion", "kind")})
    if float(led["requestTimeoutSeconds"]) != param("CLIENT_TIMEOUT_S_OTEL"):
        raise UnknownSchema("%s: requestTimeoutSeconds %r, declared %r (CLIENT_TIMEOUT_S_OTEL)" % (
            d.name, led["requestTimeoutSeconds"], param("CLIENT_TIMEOUT_S_OTEL")))
    rk = rc["runKey"]
    regime, posture = rk["regime"], rk["posture"]
    stats = Counter()
    reqs, lstamps, detail, trace_token = otel_ledger(led, stats)
    al = fit_alignment(reqs)
    if al is None:
        raise ValueError("no ledger wall/monotonic stamp pairs for the clock-alignment fit")
    off = al["offset"]
    target, kind = FAULT_TARGETS[regime] if regime != NOFAULT else (None, None)
    c = {"sut": SUT, "population": "sweep", "cell": common.rel(d), "posture": posture, "regime": regime,
         "block": rk["block"], "valid": True, "target": target, "faultKind": kind, "noFault": target is None,
         "base": {"wall": float(led["barrierEpoch"]), "mono": float(led["barrierMonotonic"])},
         "duration": float(led["durationSeconds"]), "rate": float(led["ratePerSecond"]), "ledger": reqs,
         "ledgerStamps": lstamps, "ledgerDetail": detail, "align": al, "dockerEvents": None, "depends": None,
         "planSha256": None, "admissionSha256": None, "harnessCommit": None, "studyEpoch": rk.get("studyEpoch")}
    if c["rate"] != float(rk["requestsPerSecond"]):
        raise ValueError("ledger rate %r, run key %r" % (c["rate"], rk["requestsPerSecond"]))
    c["timing"] = {"requestsPerSecond": c["rate"], "requestTimeoutSeconds": float(led["requestTimeoutSeconds"]),
                   "measurementSeconds": c["duration"], "route": urlparse(led["url"]).path}
    c["t0"] = dict(c["base"])
    c["end"] = {"mono": c["base"]["mono"] + c["duration"], "wall": c["base"]["mono"] + c["duration"] + off}
    if target is not None:
        iv = _read_json(d / "intervention.json")
        if set(iv) != set(sch["intervention.json"]["keys"]):
            raise UnknownSchema("%s intervention.json keys %s, the pinned harness writes %s" % (
                d.name, sorted(iv), sch["intervention.json"]["keys"]))
        check_schema(iv, "%s intervention.json" % d.name, {"onsetSource": sch["intervention.json"]["onsetSource"]})
        if iv["service"] != target:
            raise ValueError("intervention service %r, regime %s expects %r" % (iv["service"], regime, target))
        if float(iv["barrierMonotonic"]) != c["base"]["mono"]:
            raise ValueError("intervention and ledger barriers differ")
        a, applied, b = float(iv["startedMonotonic"]), float(iv["appliedMonotonic"]), float(iv["revertingMonotonic"])
        c["cmd"] = {"A": {"mono": a, "wall": a + off}, "B": {"mono": b, "wall": b + off}, "commandSeconds": applied - a,
                    "onsetSource": "intervention startedMonotonic (pre-command)"}
        wins = sorted([(float(p["startMonotonic"]), float(p["endMonotonic"]), "probe-%s" % p.get("phase"))
                       for p in iv.get("probes") or []] + [(b, float(iv["readyAtMonotonic"]), "recovery")])
        _fault_windows(c, a, b, wins)
        c["receiptGranularity"] = granularity([iv[k] for k in ("startedMonotonic", "appliedMonotonic",
                                                               "revertingMonotonic", "revertedMonotonic",
                                                               "readyAtMonotonic")])
        c["onset"] = {"lo": a, "loSource": c["cmd"]["onsetSource"], "hi": applied, "hiKind": "command-returned",
                      "hiSource": "intervention appliedMonotonic (after the command returned and docker inspect saw "
                                  "the state; the cell keeps no Docker events)"}
    else:
        _nofault_windows(c)
    op = d / "otelcol.log"
    lines = op.read_text(errors="replace").splitlines() if op.exists() else None
    span_ev, spans = otel_spans(lines, posture, stats, trace_token, c["probes"]["wall"]) if lines is not None else (
        None, ({}, {}, set(), set(), {}))
    met_ev, res_m = otel_metrics(lines, posture, stats) if lines is not None else (None, None)
    log_ev, text, log_tok, log_tr, receipt = read_compose_log(d / "application.log", posture, stats,
                                                               log_layouts("otel"), token_regex("otel"), TRACEPARENT_RX)
    log_trace_tok = {}
    for k, per in log_tr.items():
        mapped = {t: {trace_token[x] for x in tids if x in trace_token} for t, tids in per.items()}
        mapped = {t: v for t, v in mapped.items() if v}
        if mapped:
            log_trace_tok[k] = mapped
    c["channels"] = {"log": {"present": log_ev is not None, "file": "application.log"},
                     "span": {"present": span_ev is not None, "file": "otelcol.log"},
                     "metric:otlp": {"present": met_ev is not None, "file": "otelcol.log", "resolution": res_m},
                     "metric:cgroup-sampler": {"present": False, "file": None}}
    c["familyAbsent"] = {"S": "OTel sweep cells keep no cgroup or docker-stats sampler (resources.json holds two "
                              "docker-engine CPU counters, before and after the window; FAMILY_CHANNELS)"}
    c["family"] = otel_family
    return finish_cell(c, (log_ev or []) + (span_ev or []) + (met_ev or []), (text, log_tok, log_trace_tok, receipt),
                       spans, stats)


# =========================================================================== H1: pooled fault-free baselines

class Fit:
    """Pooled fault-free statistics at one rate over `cells` (excluding `exclude`): level (median, MAD, n), count
    (records, largest gap, scored records), instrument resolution over `res_cells` (every rate)."""

    def __init__(self, cells, rate, exclude=None, res_cells=None):
        use = [c for c in cells if c["rate"] == rate and c is not exclude]
        vals, cnt = defaultdict(list), {}
        for c in use:
            for k, v in c["segLevel"].items():
                vals[k].extend(v)
            for k, (n, g, ns) in c["segCount"].items():
                n0, g0, s0 = cnt.get(k, (0, None, 0))
                gg = [x for x in (g0, g) if x is not None]
                cnt[k] = (n0 + n, max(gg) if gg else None, s0 + ns)
        self.level = {k: dt.robust(v) + (len(v),) for k, v in vals.items() if v}
        # M2 (decision 52): enough points but MAD = 0 -> the scale is not estimable; listed, level rules —
        self.madZero = sorted(k for k, (_, mad, n) in self.level.items()
                              if mad == 0 and not (MIN_POOLED_CHECK and n < MIN_POOLED))
        self.count = cnt
        self.res = {}
        for c in (res_cells if res_cells is not None else use):
            if c is exclude:
                continue
            for inst, g in c["segRes"].items():
                if self.res.get(inst) is None or g < self.res[inst]:
                    self.res[inst] = g
        self.cells = len(use)

    def lvl(self, key):
        lv = self.level.get(key)
        if lv is None or (MIN_POOLED_CHECK and lv[2] < MIN_POOLED):
            return None
        if MAD_ZERO_DASH and lv[1] == 0:
            return None
        return lv

    def gap(self, key):
        n, g, _ = self.count.get(key, (0, None, 0))
        if g is None or g <= 0 or (MIN_POOLED_CHECK and n < MIN_POOLED):
            return None
        return ABSENT_GAP_MULT * g

    def novel(self, key):
        return self.count.get(key, (0, None, 0))[2] == 0


def fits_for(cells):
    """Episode baselines: per rate, every valid cell's fault-free data (= the other cells + the episode's own
    pre-onset). POOLED False (planted defect): each fault cell gets its own pre-window only."""
    valid = [c for c in cells if c["valid"]]
    if POOLED:
        return {r: Fit(valid, r, res_cells=valid) for r in sorted({c["rate"] for c in valid})}
    return {id(c): Fit([c], c["rate"], res_cells=[c]) for c in valid}


def fit_of(fits, c):
    return fits[c["rate"]] if POOLED else fits[id(c)]


# =========================================================================== system-generic context (v2.2)

def collects(c, fam):
    """The cell retained the family's channel (FAMILY_CHANNELS of its system); E always."""
    if fam == "E":
        return True
    ch, key = FAMILY_CHANNELS[SYSTEM][fam]
    return ch in c["chans"] and c["channelsPresent"].get(key, False)


def route_services():
    return None if (SYSTEM == "hotel" or not ROUTE_GRAPH) else set(param("ROUTE_SERVICES_" + SYSTEM.upper()))


def make_ctx(cells):
    """v1.make_ctx for the current system: the project map's call graph (dt.call_graph), restricted to the system's
    route services where its base run drove another route (ROUTE_GRAPH_RULE); span op tokens per service; the
    whole-second log flag."""
    edges, on_route = dt.call_graph(SUT)
    keep = route_services()
    if keep is not None:
        edges = {(x, y) for x, y in edges if x in keep and y in keep}
        on_route = set(on_route) & keep
    ops = defaultdict(set)
    for c in cells:
        for (ch, svc, tok) in c["prep"]:
            if ch == "span":
                ops[svc].add(tok.split(":error")[0])
    ws_logs, ws_counts = dt.whole_second_logs(cells)
    return {"edges": edges, "onRoute": on_route, "ops": ops, "wsLogs": ws_logs, "wsCounts": ws_counts}


def episode_order(e):
    return (e.get("campaignIndex", 0), e["block"])


# =========================================================================== one episode at one operating point

def eval_episode(c, fit, kmap, share, ws_logs):
    """Every sensor-rule's first observation in [A, B] (as v1.eval_window, scope probe rule) with the pooled
    baseline, the relative floor and each family's K (kmap; None = family not at the operating point: no fires)."""
    A, B = c["cmd"]["A"], c["cmd"]["B"]
    scope = {ENTRY, c["target"]}
    fires, straddle, moved_out = [], [], []
    for key, (obs, vals, meta) in c["prep"].items():
        ch, svc, tok = key
        if ch not in c["chans"]:
            continue
        fam = family_of(c, ch, meta)
        k = kmap.get(fam)
        if k is None:
            continue
        clk = meta["clock"]
        wins = c["probes"][clk] if (svc in scope and ch in ("log", "metric")) else ()
        obs_all = obs
        obs, vals, _ = v1.exclude(obs, vals, wins)
        a, b = A[clk], B[clk]
        a_in = math.floor(a) if (ch == "log" and ws_logs) else a
        ia, ib = bisect.bisect_left(obs, a_in), bisect.bisect_right(obs, b)
        got, ender, starter, g = {}, None, None, None
        if ch in ("log", "span"):
            if fit.novel(key) and ib > ia:
                got["appear"] = (obs[ia], None)
            g = fit.gap(key) if not tok.endswith(":error") else None
            if g is not None:
                t, ender, starter = first_silence_bounds(obs_all, c["t0"][clk], a_in, b, g)
                if t is not None:
                    got["absent"] = (t, None)
        if ch == "metric" or (ch == "span" and not tok.endswith(":error")):
            lv = fit.lvl(key)
            if lv is not None and ib > ia:
                m, thr = threshold(lv, k, share, fit.res.get(instrument(ch, meta, tok)))
                if thr > 0:
                    got.update(dt.level_rules(obs[ia:ib], vals[ia:ib], m, thr,
                                              ("up", "down") if ch == "metric" else ("up",)))
        for rule, (t, d) in got.items():
            t_orig = t
            t, moved = v1.move_out(t, wins)
            if moved and t > b:
                moved_out.append("%s:%s:%s/%s" % (ch, svc, tok, rule))
                continue
            if ch == "log":
                lt = dt.log_ttd(t, a, ws_logs, b)
                if lt is None:
                    straddle.append("%s:%s:%s/%s" % (ch, svc, tok, rule))
                    continue
                tlo, ttd = lt
            else:
                tlo = ttd = max(0.0, t - a)
            fires.append({"ch": ch, "svc": svc, "tok": tok, "rule": rule, "ttd": ttd, "ttdLo": tlo, "dir": d,
                          "level": meta.get("level"), "family": fam, "moved": moved, "movedBy": t - t_orig,
                          "tObs": t_orig, "clock": clk, "collector": meta.get("collector")})
            if rule == "absent":                        # decision 57: the observation that ends the silence
                toks, src = silence_tokens(c, ch, svc, tok, ender)
                stoks, ssrc = silence_tokens(c, ch, svc, tok, starter)       # decision 58: the one that starts it
                fires[-1].update(silenceEndedBy=ender, silenceTokens=toks, silenceTokenSource=src,
                                 silenceStartedBy=starter, silenceStartTokens=stoks, silenceStartTokenSource=ssrc,
                                 silenceGap=g)
    kE = kmap.get("E")
    unknown = []
    if kE is not None:
        base = {}
        for route in sorted({r.route for r in c["ledger"]}):
            lv = fit.lvl(("ledger", ENTRY, route))
            if lv is not None:
                m, thr = threshold(lv, kE, share, fit.res.get(("ledger",)))
                if thr > 0:
                    base[route] = (m, thr)
        led, _, unknown = dt.ledger_rules(c["ledger"], A["mono"], B["mono"], rules=dt.E_RULES, base=base)
        led = dict(led)
        silence = {}
        if LEDGER_ABSENT:
            for route in sorted({r.route for r in c["ledger"]}):
                g = fit.gap(("ledger", ENTRY, route + COMPLETIONS))
                if g is not None:
                    rr = [r for r in c["ledger"] if r.route == route]
                    t, ender, starter = first_silence_bounds(sorted(r.end for r in rr), c["t0"]["mono"], A["mono"],
                                                             B["mono"], g)
                    if t is not None:
                        led[(route, "absent")] = t
                        # M1 (decision 51): the completion that ends the silence names the request; decision 58: the
                        # last completion before the silence names the request that starts it
                        silence[route] = (ender, sorted({r.token for r in rr if r.end == ender and r.token})
                                          if ender is not None else [], starter,
                                          sorted({r.token for r in rr if r.end == starter and r.token}), g)
        for (route, rule), t in led.items():
            f = {"ch": "ledger", "svc": ENTRY, "tok": route, "rule": rule, "ttd": max(0.0, t - A["mono"]),
                 "ttdLo": max(0.0, t - A["mono"]), "dir": "up", "level": None, "family": "E",
                 "moved": False, "movedBy": 0.0, "tObs": t, "clock": "mono", "collector": "workload-ledger"}
            if rule == "absent":
                (f["silenceEndedBy"], f["silenceTokens"], f["silenceStartedBy"], f["silenceStartTokens"],
                 f["silenceGap"]) = silence[route]
            fires.append(f)
    return fires, sorted(unknown), straddle, moved_out


def bc_of(f, c, ctx, regime):
    flags = v1.bc_flags(f, c["target"], c["faultKind"], ctx, c["logText"], PRIMARY_CALLER_SPAN)
    act = (ACTUATOR.get(regime) or {}).get(f["ch"], [])
    if ACTUATOR_FLAG and f["svc"] == c["target"] and f["tok"] in act:
        flags.append("BC-actuator-readback")
    return flags


def analyse(cells, ctx, fits, kmaps, share):
    """kmaps: regime -> rate -> {family: K or None}. Fault episodes with scored fires."""
    eps = []
    for c in cells:
        if not c["valid"] or c["target"] is None:
            continue
        kmap = kmaps.get(c["regime"], {}).get(c["rate"], {})
        fires, unknown, straddle, moved_out = eval_episode(c, fit_of(fits, c), kmap, share, v1.ws_of(c, ctx))
        path = v1.path_of(c["target"], ctx)
        for f in fires:
            counts, own = dt.scored(f, c["target"], path, ENTRY)
            f.update({"own": own, "onPath": f["svc"] in path, "counts": counts, "admissible": True,
                      "bc": bc_of(f, c, ctx, c["regime"])})
        eps.append({"cell": c["cell"], "regime": c["regime"], "rate": c["rate"], "block": c["block"],
                    "campaignIndex": c.get("campaignIndex", 0),
                    "target": c["target"], "faultKind": c["faultKind"], "onset": c["cmd"]["A"], "end": c["cmd"]["B"],
                    "holdSeconds": c["cmd"]["B"]["mono"] - c["cmd"]["A"]["mono"], "g3n": 1, "kmap": dict(kmap),
                    "affectedPath": sorted(path), "fires": fires, "ledgerRoutesWithoutBaseline": unknown,
                    "logStraddlesHoldEnd": straddle, "movedPastHoldEnd": moved_out, "_c": c})
    eps.sort(key=lambda e: (e["regime"], -e["rate"]) + episode_order(e))
    return eps


# =========================================================================== H2 / H7: false alarms and the operating point

def sid_of(src):
    return "%s:%s:%s" % (src["ch"], src["svc"], src["tok"])


def quiet_material(X, fit, share):
    """One held-out no-fault cell scored with `fit`: the K-independent alarm material of every sensor-rule.
    fixed: [(t, src)] for appear, absent and the ledger's failed and absent (src: fam, ch, svc, tok, level, rule).
    level: per level sensor (with a pooled baseline and a positive threshold at some grid K) its in-cell samples, each
    with the highest grid index at which it is beyond the threshold (-1: never) and its direction (a positive
    threshold is crossed in at most one direction); sensors that are beyond at no grid K are dropped (no level rule
    can fire without a beyond sample)."""
    fixed, level = [], []

    def add_level(src, dirs, m, mad, fl, obs, vals):
        thr = [max(k * SCALE * mad, fl) for k in K_GRID]
        if thr[-1] <= 0:
            return
        ts, vs, ks, ds = [], [], [], []
        for t, v in zip(obs, vals):
            dev = deviation(v, m, dirs)
            i = bisect.bisect_right(thr, dev) - 1
            ts.append(t)
            vs.append(v)
            ks.append(i if (i >= 0 and thr[i] > 0) else -1)
            ds.append("up" if v - m >= m - v else "down")
        if ks and max(ks) >= 0:
            level.append({"src": src, "dirs": dirs, "m": m, "thr": thr, "t": ts, "v": vs, "k": ks, "d": ds,
                          "maxk": max(ks)})
    for key, (obs, vals, meta) in X["prep"].items():
        ch, svc, tok = key
        if ch not in X["chans"]:
            continue
        fam = family_of(X, ch, meta)
        clk = meta["clock"]
        t0, end = X["t0"][clk], X["end"][clk]
        i0, i1 = bisect.bisect_left(obs, t0), bisect.bisect_right(obs, end)
        ws = ch == "log" and X["wsLogs"]
        src = {"fam": fam, "ch": ch, "svc": svc, "tok": tok, "level": meta.get("level")}
        if ch in ("log", "span"):
            if fit.novel(key) and i1 > i0:
                fixed.append((log_time(obs[i0], ws), dict(src, rule="appear")))
            g = fit.gap(key) if not tok.endswith(":error") else None
            if g is not None:
                for t in silences(obs, t0, t0, end, g):
                    fixed.append((t, dict(src, rule="absent")))
        if ch == "metric" or (ch == "span" and not tok.endswith(":error")):
            lv = fit.lvl(key)
            if lv is None:
                continue
            m, mad, _ = lv
            add_level(src, ("up", "down") if ch == "metric" else ("up",), m, mad,
                      floor_of(m, share, fit.res.get(instrument(ch, meta, tok))), obs[i0:i1], vals[i0:i1])
    # ledger: failed, spike on ok latency, absent on completions (H3 e)
    t0, end = X["t0"]["mono"], X["end"]["mono"]
    for route in sorted({r.route for r in X["ledger"]}):
        rr = [r for r in X["ledger"] if r.route == route and t0 <= r.end <= end]
        src = {"fam": "E", "ch": "ledger", "svc": ENTRY, "tok": route, "level": None}
        for r in rr:
            if not r.ok:
                fixed.append((r.end, dict(src, rule="failed")))
        lv = fit.lvl(("ledger", ENTRY, route))
        if lv is not None:
            m, mad, _ = lv
            ok = [r for r in rr if r.ok]
            add_level(src, ("up",), m, mad, floor_of(m, share, fit.res.get(("ledger",))),
                      [r.end for r in ok], [(r.end - r.start) * MS_PER_S for r in ok])
        g = fit.gap(("ledger", ENTRY, route + COMPLETIONS)) if LEDGER_ABSENT else None
        if g is not None:
            for t in silences(sorted(r.end for r in X["ledger"] if r.route == route), t0, t0, end, g):
                fixed.append((t, dict(src, rule="absent")))
    return fixed, level


def quiet_events(X, fit, share, material=None):
    """v2's form of the material: per family, the alarm instants that do not depend on K (appear, absent, failed) and
    the level samples with the highest grid index at which each is beyond the threshold. Sources kept for the report."""
    fixed_l, level_l = material if material is not None else quiet_material(X, fit, share)
    fixed, level = defaultdict(dict), defaultdict(list)
    for t, src in fixed_l:
        fixed[src["fam"]].setdefault(t, []).append(sid_of(src) + "/" + src["rule"])
    for L in level_l:
        for t, k in zip(L["t"], L["k"]):
            if k >= 0:
                level[L["src"]["fam"]].append((t, k, sid_of(L["src"]) + "/spike"))
    return fixed, level


def alarm_counts(fixed, level):
    """Distinct alarm instants at every grid index (the detector restarts after each alarm). Exact when every
    sensor-rule counts (v2's all-sensors detector): run3 and median never fire before a spike of the same sensor."""
    times = set(fixed)
    by = defaultdict(list)
    for t, i, _ in level:
        by[i].append(t)
    out = [0] * len(K_GRID)
    for i in range(len(K_GRID) - 1, -1, -1):
        times.update(by.get(i, ()))
        out[i] = len(times)
    return out


def merge_events(parts):
    fixed, level = {}, []
    for fx, lv in parts:
        for t, src in fx.items():
            fixed.setdefault(t, []).extend(src)
        level.extend(lv)
    return fixed, level


FIXED_EV, LEVEL_EV = 0, 1
LEVEL_RULES = ("spike", "run3", "median")


def event_lists(fixed, level):
    """Per family and for `system` (L, M, S, T), the time-ordered events (t, kind, index, sample)."""
    by = defaultdict(list)
    for a, (t, src) in enumerate(fixed):
        by[src["fam"]].append((t, FIXED_EV, a, 0))
    for a, L in enumerate(level):
        by[L["src"]["fam"]].extend((t, LEVEL_EV, a, j) for j, t in enumerate(L["t"]))
    out = {g: sorted(by.get(g, ())) for g in FAMILIES}
    out["system"] = sorted(e for f in SENSOR_FAMILIES for e in out[f])
    return out


def admission(fixed, level, regime, ctx, X):
    """M3: which sensor-rules of one held-out cell belong to the scored set of a fault class, decided exactly as an
    episode of that class decides them: dt.scored's spike path filter and bc_of's by-construction flags (the no-BC
    view, as P4), per rule and per direction. The ledger keeps its BC catches in every view (as col_fire)."""
    target, kind = FAULT_TARGETS[regime]
    path = v1.path_of(target, ctx)
    pseudo = {"target": target, "faultKind": kind, "logText": X["logText"]}

    def ok(src, rule, d):
        if src["ch"] == "ledger":
            return True
        f = dict(src, rule=rule, dir=d)
        return dt.scored(f, target, path, ENTRY)[0] and not bc_of(f, pseudo, ctx, regime)
    fixed_ok = [ok(src, src["rule"], None) for _, src in fixed]
    level_ok = []
    for L in level:
        o = {r: {d: ok(L["src"], r, d) for d in L["dirs"]} for r in LEVEL_RULES}
        o["any"] = any(v for r in LEVEL_RULES for v in o[r].values())
        o["slow"] = not all(o["spike"].values())       # run3 / median can lead only where a spike is muted
        level_ok.append(o)
    return fixed_ok, level_ok


def admit_all(fixed, level):
    o = {"any": True, "slow": False}
    return [True] * len(fixed), [dict(o, **{r: dict.fromkeys(L["dirs"], True) for r in LEVEL_RULES}) for L in level]


class _RuleState:
    """One level sensor's rule state since the last restart: run lengths per direction, whether spike / run3 / median
    have fired (a fire mutes its rule until the next restart), the sorted samples since the restart (median)."""
    __slots__ = ("epoch", "run", "spike", "run3", "median", "prefix")

    def __init__(self, epoch, dirs):
        self.epoch, self.run, self.prefix = epoch, dict.fromkeys(dirs, 0), []
        self.spike = self.run3 = self.median = False


def restart_count(events, fixed, level, fixed_ok, level_ok, i, sources=None):
    """The scored detector at grid index i on one held-out cell, restarted after each counted alarm: per sensor-rule
    its first fire since the last restart (dt.level_rules' semantics: spike = first beyond sample, run3 = RUN_N
    consecutive beyond samples in one direction, median = the running median of the samples since the restart beyond
    the threshold after MEDIAN_MIN samples; appear / absent / failed at their instants) counts if admitted; a fire
    that is not admitted (off-path spike, BC flag) mutes that sensor-rule until the next restart, as in an episode.
    Returns the number of alarms (distinct instants); `sources` (Counter) collects the alarming sensor-rules."""
    n, t_r, epoch, state = 0, -math.inf, 0, {}
    for t, kind, a, j in events:
        if t <= t_r:
            continue
        if kind == FIXED_EV:
            if fixed_ok[a]:
                n, t_r, epoch = n + 1, t, epoch + 1
                if sources is not None:
                    sources[sid_of(fixed[a][1]) + "/" + fixed[a][1]["rule"]] += 1
            continue
        L, ok = level[a], level_ok[a]
        if not ok["any"] or L["maxk"] < i or L["thr"][i] <= 0:
            continue
        d = L["d"][j] if L["k"][j] >= i else None
        if not ok["slow"]:
            if d is None:
                continue
            fire = "spike"
        else:
            st = state.get(a)
            if st is None or st.epoch != epoch:
                st = state[a] = _RuleState(epoch, L["dirs"])
            fire = None
            if d is not None and not st.spike:
                st.spike = True
                if ok["spike"][d]:
                    fire = "spike"
            run = st.run
            for dd in L["dirs"]:
                run[dd] = run[dd] + 1 if dd == d else 0
            if d is not None and not st.run3 and run[d] >= RUN_N:
                st.run3 = True
                if ok["run3"][d] and fire is None:
                    fire = "run3"
            if not st.median:
                pre = st.prefix
                bisect.insort(pre, L["v"][j])
                if len(pre) >= MEDIAN_MIN:
                    h = len(pre) // 2
                    pm = pre[h] if len(pre) % 2 else (pre[h - 1] + pre[h]) / 2
                    for dd in L["dirs"]:
                        if dt.beyond(pm, L["m"], L["thr"][i], dd):
                            st.median = True
                            if ok["median"][dd] and fire is None:
                                fire = "median"
                            break
            if fire is None:
                continue
        n, t_r, epoch = n + 1, t, epoch + 1
        if sources is not None:
            sources[sid_of(L["src"]) + "/" + fire] += 1
    return n


def loco_fits(cells):
    """H2: per held-out no-fault cell, the fit without it (LOCO False, planted defect: with it)."""
    valid = [c for c in cells if c["valid"]]
    return {id(X): Fit(valid, X["rate"], exclude=X if LOCO else None, res_cells=valid)
            for X in valid if X["target"] is None}


def far_row(counts, hours, cells, sources):
    per = []
    for i, k in enumerate(K_GRID):
        n = counts[i]
        ub = poisson_upper(n) / hours
        per.append({"K": k, "alarms": n, "perHour": n / hours, "upperPerHour": ub,
                    "certified": ub <= FAR_TARGET, "pointMeets": n / hours <= FAR_TARGET})
    crit = "certified" if FAR_MEETS == "upper" else "pointMeets"
    return {"quietCells": cells, "quietHours": hours, "perK": per,
            "minK": next((x["K"] for x in per if x[crit]), None),
            "minKCertified": next((x["K"] for x in per if x["certified"]), None),
            "minKPoint": next((x["K"] for x in per if x["pointMeets"]), None),
            "atLargestK": dict(sources.most_common())}


def fit_k(rows):
    """K_FIT_UNIT's definition: the smallest grid K whose count meets the target at every row (class, rate) where some
    grid K meets it; None when no row meets it (or, non-monotone counts only, no K meets them all)."""
    crit = "certified" if FAR_MEETS == "upper" else "pointMeets"
    S = [x for x in rows if x["minK"] is not None]
    if not S:
        return None
    return next((k for i, k in enumerate(K_GRID) if all(x["perK"][i][crit] for x in S)), None)


def meets_at(row, k):
    crit = "certified" if FAR_MEETS == "upper" else "pointMeets"
    return k is not None and row is not None and row["perK"][K_GRID.index(k)][crit]


def operating_point(cells, share, fits=None, ctx=None):
    """Per (family, class, rate) on the scored set (M3): held-out false alarms per hour at every grid K, the exact upper
    bound, the smallest K that meets the target; per family one K (K_FIT_UNIT `family`, decision 53) and the
    per-system K beside. v2's all-sensors count (no class filter) is kept beside it in `allSensors`, labelled."""
    valid = [c for c in cells if c["valid"]]
    quiet = [c for c in valid if c["target"] is None]
    fits = fits if fits is not None else loco_fits(cells)
    ctx = ctx if ctx is not None else make_ctx(valid)
    groups = list(FAMILIES) + ["system"]
    nk, top = len(K_GRID), len(K_GRID) - 1
    table = {g: {regime: {} for regime in FAULT_REGIMES} for g in groups}
    table_all = {g: {} for g in groups}
    held_out_mad0 = {}
    for rate in sorted({c["rate"] for c in valid}, reverse=True):
        xs = [c for c in quiet if c["rate"] == rate]
        if not xs:
            continue
        c_all = {g: [0] * nk for g in groups}
        s_all = {g: Counter() for g in groups}
        c_cls = {g: {regime: [0] * nk for regime in FAULT_REGIMES} for g in groups}
        s_cls = {g: {regime: Counter() for regime in FAULT_REGIMES} for g in groups}
        hours, mad0 = 0.0, set()
        for X in xs:
            fit = fits[id(X)]
            mad0.update(fit.madZero)
            fixed, level = quiet_material(X, fit, share)
            hours += (X["end"]["mono"] - X["t0"]["mono"]) / S_PER_HOUR
            fx, lv = quiet_events(X, fit, share, (fixed, level))
            for g in groups:                                  # v2's all-sensors count, labelled
                fams = SENSOR_FAMILIES if g == "system" else (g,)
                f2_, l2_ = merge_events([(fx.get(f, {}), lv.get(f, [])) for f in fams])
                for i, n in enumerate(alarm_counts(f2_, l2_)):
                    c_all[g][i] += n
                for t, src in f2_.items():
                    s_all[g].update(src)
                s_all[g].update(s for _, i, s in l2_ if i == top)
            ev = event_lists(fixed, level)
            fok_e, lok_e = admit_all(fixed, level)            # E: class-independent, every rule counts
            for i in range(nk):
                c_cls["E"][FAULT_REGIMES[0]][i] += restart_count(ev["E"], fixed, level, fok_e, lok_e, i,
                                                                  s_cls["E"][FAULT_REGIMES[0]] if i == top else None)
            for regime in FAULT_REGIMES:
                fok, lok = admission(fixed, level, regime, ctx, X)
                for g in groups:
                    if g == "E":
                        continue
                    for i in range(nk):
                        c_cls[g][regime][i] += restart_count(ev[g], fixed, level, fok, lok, i,
                                                              s_cls[g][regime] if i == top else None)
        for regime in FAULT_REGIMES[1:]:
            c_cls["E"][regime], s_cls["E"][regime] = c_cls["E"][FAULT_REGIMES[0]], s_cls["E"][FAULT_REGIMES[0]]
        for g in groups:
            table_all[g][rate] = far_row(c_all[g], hours, len(xs), s_all[g])
            for regime in FAULT_REGIMES:
                table[g][regime][rate] = far_row(c_cls[g][regime], hours, len(xs), s_cls[g][regime])
        held_out_mad0[rate] = sorted("%s:%s:%s" % k for k in mad0)
    fitted, fitted_all = {}, {}
    for g in groups:
        k = fit_k([row for regime in FAULT_REGIMES for row in table[g][regime].values()])
        fitted[g] = {"K": k, "atOperatingPoint": {regime: {r: meets_at(row, k) for r, row in table[g][regime].items()}
                                                  for regime in FAULT_REGIMES}}
        ka = fit_k(list(table_all[g].values()))
        fitted_all[g] = {"K": ka, "atOperatingPoint": {r: meets_at(row, ka) for r, row in table_all[g].items()}}
    for g in SENSOR_FAMILIES:                         # v2.2: a family no cell collects has no operating point (—)
        if not any(collects(c, g) for c in valid):
            fitted[g] = {"K": None, "notCollected": True,
                         "atOperatingPoint": {regime: {r: False for r in table[g][regime]} for regime in FAULT_REGIMES}}
            fitted_all[g] = {"K": None, "notCollected": True, "atOperatingPoint": {r: False for r in table_all[g]}}
    return {"share": share, "table": table, "fitted": fitted,
            "allSensors": {"table": table_all, "fitted": fitted_all,
                           "label": "all sensors of the family, no class filter (v2's calibration set; not used for "
                                    "K in v2.1)"},
            "heldOutScaleNotEstimable": held_out_mad0}


def kmaps_from(op, rates, unit=None):
    """regime -> rate -> {family: K or None}. Unit `family` (decision 53): each family's own K; `system`: the
    per-system K for L, M, S, T (the ledger E keeps its own). SCORED_SET_CALIBRATION False (planted defect): v2's
    all-sensors fit, the same for every class."""
    unit = unit or K_FIT_UNIT
    out = {}
    for regime in FAULT_REGIMES:
        out[regime] = {}
        for r in rates:
            m = {}
            for f in FAMILIES:
                g = f if (unit == "family" or f == "E") else "system"
                if SCORED_SET_CALIBRATION:
                    fit = op["fitted"][g]
                    at = fit["atOperatingPoint"].get(regime, {}).get(r)
                else:
                    fit = op["allSensors"]["fitted"][g]
                    at = fit["atOperatingPoint"].get(r)
                m[f] = fit["K"] if at else None
            out[regime][r] = m
    return out


# =========================================================================== aggregation

def col_fire(ep, col, bc):
    """The column's first catch (fire dict), None = miss, "absent" = not evaluable (channel file missing, or the
    family is not at the operating point at this rate)."""
    fam, own = col.split(":")[0], col.endswith(":own")
    if not collects(ep["_c"], fam) or ep["kmap"].get(fam) is None:
        return "absent"
    return dt.family_ttd(ep, fam, own=own, bc=bc or fam == "E", rules=E_RULES)


def col_hit(ep, col, bc):
    h = col_fire(ep, col, bc)
    return h if h in ("absent", None) else h["ttd"]


def eps_of(eps, regime, rate):
    return [e for e in eps if e["regime"] == regime and e["rate"] == rate]


def primary_table(eps, op):
    rows = []
    for regime in FAULT_REGIMES:
        for rate in RATES:
            es = eps_of(eps, regime, rate)
            row = {"regime": regime, "rate": rate, "n": len(es), "columns": {}}
            for col in COLUMNS:
                fam, own = col.split(":")[0], col.endswith(":own")
                if fam == "E" and own:
                    continue
                v = {}
                for bc in (True, False):
                    pairs = [(col_hit(e, col, bc), e) for e in es]
                    pairs = [(h, e) for h, e in pairs if h != "absent"]
                    if not pairs:
                        v = None
                        break
                    s = v1.summarise([h for h, _ in pairs], [e["holdSeconds"] for _, e in pairs])
                    v["bc" if bc else "noBC"] = s
                if v is not None and op is not None:
                    t = op["table"][fam].get(regime, {}).get(rate)
                    k = es[0]["kmap"].get(fam) if es else None
                    x = next((y for y in (t or {}).get("perK", []) if y["K"] == k), None)
                    v["falseAlarms"] = None if x is None else {"K": k, "alarms": x["alarms"], "perHour": x["perHour"],
                                                               "upperPerHour": x["upperPerHour"]}
                row["columns"][col] = v
            rows.append(row)
    return rows


def h4_split(e, a, t_end):
    """The failed requests v1.failed_before counts (scheduled in [a, t_end]), by H4 class against the episode's onset
    interval [lo, hi] (classify_requests); None where the interval has no upper bound or the lists disagree."""
    c = e["_c"]
    on = c.get("onset") or {}
    fl = [r for r in c["ledger"] if not r.ok and a <= r.sched <= t_end]
    if not SECONDARY_H4_SPLIT or on.get("hi") is None or len(fl) != v1.failed_before(c["ledger"], a, t_end):
        return None
    return dict(dict.fromkeys(("before", "straddling", "after"), 0), **classify_requests(fl, on["lo"], on["hi"]))


def secondary_table(eps):
    """Failed requests scheduled in [onset, onset + time to detection] (v1's rule), plus their split by H4 class
    (before / straddling / after the onset interval)."""
    rows = []
    for regime in FAULT_REGIMES:
        for rate in RATES:
            es = eps_of(eps, regime, rate)
            row = {"regime": regime, "rate": rate, "n": len(es), "columns": {}}
            for col in COLUMNS:
                if col == "E:own":
                    continue
                per = []
                for e in es:
                    h = col_hit(e, col, col.startswith("E"))
                    if h == "absent":
                        continue
                    a = e["onset"]["mono"]
                    t_end = a + (h if h is not None else e["holdSeconds"])
                    per.append({"block": e["block"], "detected": h is not None,
                                "failedBefore": v1.failed_before(e["_c"]["ledger"], a, t_end),
                                "byH4Class": h4_split(e, a, t_end)})
                split = [p["byH4Class"] for p in per if p["byH4Class"] is not None]
                row["columns"][col] = ({"n": len(per), "detected": sum(p["detected"] for p in per),
                                        "failedBefore": dt.dist([p["failedBefore"] for p in per]), "perEpisode": per,
                                        "byH4Class": ({k: sum(x[k] for x in split) for k in split[0]} if split else None),
                                        "byH4ClassEpisodes": len(split)}
                                       if per else None)
            rows.append(row)
    return rows


def per_sensor(eps, exposure):
    out = []
    for regime in FAULT_REGIMES:
        for rate in RATES:
            es = sorted(eps_of(eps, regime, rate), key=episode_order)
            per = {}
            for i, e in enumerate(es):
                for f in e["fires"]:
                    if f["family"] == "E" or not f["counts"]:
                        continue
                    sid = "%s:%s:%s" % (f["ch"], f["svc"], f["tok"])
                    row = per.setdefault(sid, {"family": f["family"], "own": f["own"], "svc": f["svc"],
                                               "bc": [None] * len(es), "noBC": [None] * len(es)})
                    for key in ("bc", "noBC"):
                        if key == "noBC" and f["bc"]:
                            continue
                        if row[key][i] is None or f["ttd"] < row[key][i]:
                            row[key][i] = f["ttd"]
            holds = [e["holdSeconds"] for e in es]
            for sid, row in sorted(per.items()):
                exp = [row["svc"] in exposure["episodes"].get(e["cell"], {}).get("exposedServices", ()) for e in es]
                out.append({"regime": regime, "rate": rate, "sensor": sid, "family": row["family"], "own": row["own"],
                            "exposed": exp, "bc": v1.summarise(row["bc"], holds),
                            "noBC": v1.summarise(row["noBC"], holds)})
    return out


# =========================================================================== H3: P4

def silence_tokens(c, ch, svc, tok, ender):
    """Decision 57 (SENSOR_ABSENT_TOKEN_RULE): (tokens, source) of the observation that ends a sensor's silence (the
    stream's first record after the gap, at `ender`): its own token(s) (span: the token on the span itself; log: the
    tokens named in the line), else the token(s) of the trace it belongs to (span: the trace's entry-root token, as
    the harness correlates it; log: the trace the line names, where the cell format carries one). Neither ->
    ([], reason): the pair is unclassifiable."""
    if ender is None:
        return [], "no observation ends the silence"
    own_map = {"span": c.get("spanOwnTok"), "log": c.get("logTok")}.get(ch) or {}
    trace_map = {"span": c.get("spanTok"), "log": c.get("logTraceTok")}.get(ch) or {}
    own = own_map.get((svc, tok), {}).get(ender)
    if own:
        return sorted(own), "observation"
    tr = trace_map.get((svc, tok), {}).get(ender)
    if tr:
        return sorted(tr), "trace"
    return [], "the ending %s carries no token and belongs to no tokened trace" % ch


def obs_tokens(f, c):
    """Request tokens of a fire's catching observation (spans: the trace's token; logs: tokens in the message). The
    ledger's `absent` carries the token of the completion that ends its silence (M1, decision 51); a sensor's `absent`
    the token of the observation that ends its silence (decision 57, silence_tokens)."""
    if f["rule"] == "absent":
        if f["ch"] == "ledger" and SAME_SILENCE:
            return set(f.get("silenceTokens") or ())
        if f["ch"] != "ledger" and SENSOR_SILENCE_TOKEN:
            return set(f.get("silenceTokens") or ())
        return set()
    if f["ch"] == "span":
        return set(c["spanTok"].get((f["svc"], f["tok"]), {}).get(f["tObs"], ()))
    if f["ch"] == "log":
        return set(c["logTok"].get((f["svc"], f["tok"]), {}).get(f["tObs"], ()))
    if f["ch"] == "ledger":
        return set(c["ledgerTok"].get(f["tObs"], ()))
    return set()


def stamp_granularity(f, c):
    if f["ch"] == "ledger":
        return c["ledgerStamps"]["monoGranularity"]
    if f["ch"] == "span":                           # Jaeger microseconds (Hotel); Kieker / OTLP nanoseconds
        return 1.0 / US_PER_S if SYSTEM == "hotel" else 1.0 / NS_PER_S
    if f["ch"] == "log":
        if c["wsLogs"] or c["logReceipt"]["dockerDigits"] is None:
            return 1.0
        return DECIMAL_BASE ** -c["logReceipt"]["dockerDigits"]
    obs = c["prep"].get((f["ch"], f["svc"], f["tok"]), ([], [], {}))[0]
    return granularity(obs)


def margin(f, fE, c):
    """H3 (b): timing uncertainty between the sensor's and the ledger's stamps, in both clocks. Event time: both
    granularities + alignment residual + (logs) the receipt-delay bound; None when a log lead cannot be counted.
    Availability: the receive stamp's own granularity + alignment; None where no receive stamp is recorded."""
    gl, gs = stamp_granularity(fE, c), stamp_granularity(f, c)
    base = (gl or 0.0) + (gs or 0.0) + c["align"]["residual"]
    ev, av = base, base
    if f["ch"] == "log":
        rc = c["logReceipt"]
        if c["wsLogs"]:
            av = None                                       # timed by the app stamp: no receive stamp
        elif rc["bound"] is None or f["svc"] in rc["servicesWithoutAppStamp"]:
            ev = None                                       # no app stamp: log leads are not counted
        else:
            ev = base + max(0.0, rc["bound"])
    if AVAIL_SOURCES.get(f["family"]) is None:
        av = None
    return ev, av


def judge_fold(f, fE, hold, c):
    """H3 (a)-(d) for one held-out episode. f: the sensor's catch (fire or None), fE: the ledger's (E) catch."""
    st = f["ttd"] if f else None
    lt = fE["ttd"] if fE else None
    out = {"sensorTtd": st, "sensorRule": f["rule"] if f else None, "ledgerTtd": lt,
           "ledgerRule": fE["rule"] if fE else None, "lead": None, "margin": None, "marginAvailability": None,
           "sameRequest": None, "sameSilence": None, "sensorSilence": None, "unclassifiable": None,
           "category": None, "win": False, "winAvailability": None,
           "ledgerMissed": False, "v1StyleWin": (st if st is not None else hold) < (lt if lt is not None else hold)}
    if f is None:
        out["category"] = "sensor missed"
        return out
    sensor_absent = f["rule"] == "absent" and f["ch"] != "ledger"
    if sensor_absent:                               # decision 57: the request that ends the sensor's silence
        out.update(sensorSilenceTokens=list(f.get("silenceTokens") or []),
                   sensorSilenceSource=f.get("silenceTokenSource"))
    if fE is None:
        out["ledgerMissed"] = True
        if LEDGER_MISSED_APART:
            out["category"] = "ledger missed (counted apart)"
            return out
        lt = hold
    lead = lt - st
    ev, av = margin(f, fE, c) if fE else (0.0, 0.0)
    toks = obs_tokens(f, c)
    end_same = bool(fE) and bool(toks & obs_tokens(fE, c))
    same = end_same
    unclass_by = ["decision 57: the silence-ending observation names no request"] if (
        SENSOR_SILENCE_TOKEN and sensor_absent and not toks) else []
    both = bool(fE) and sensor_absent and fE["ch"] == "ledger" and fE["rule"] == "absent"
    if both:                                        # decision 58: the records that start the two silences
        out["decomposition"] = lead_decomposition(f, fE, c, lead)
        if SILENCE_START_TOKEN:
            ss, se = set(f.get("silenceStartTokens") or ()), set(fE.get("silenceStartTokens") or ())
            out.update(silenceStartSame=bool(ss & se), sensorSilenceStartTokens=sorted(ss),
                       ledgerSilenceStartTokens=sorted(se), sensorSilenceStartSource=f.get("silenceStartTokenSource"))
            same = same or bool(ss & se)
            if not ss or not se:
                unclass_by.append("decision 58: the silence-starting %s names no request" % (
                    "observation" if not ss else "completion"))
    unclass = bool(unclass_by) and not same
    d60 = bool(both and START_TERM_ONLY)
    out["startTermRule"] = d60
    out.update(lead=lead, margin=ev, marginAvailability=av, sameRequest=same,
               sameSilence=bool(end_same and fE["ch"] == "ledger" and fE["rule"] == "absent"),
               sensorSilence=bool(end_same and sensor_absent), unclassifiable=unclass,
               unclassifiableBy=unclass_by if unclass else [])
    if fE is not None and fE["rule"] == "absent" and fE["ch"] == "ledger":
        out["ledgerSilenceTokens"] = list(fE.get("silenceTokens") or [])
    if lead <= 0:
        out["category"] = "not faster"
    elif MARGIN_CHECK and (ev is None or lead <= ev):
        out["category"] = "log lead not counted (no app stamp)" if ev is None else "lead within the margin"
    elif SAME_REQUEST and same:
        out["category"] = "same request"
    elif unclass:
        out["category"] = UNCLASSIFIABLE
    elif d60 and not start_wins(out.get("decomposition"), ev):
        out["category"] = START_TERM_TIE                # decision 60: the gap term never counts toward a lead
    else:
        out["category"] = "win"
        out["win"] = True
    if fE is not None and av is not None:           # availability clock: measured receive stamps only (H8)
        out["winAvailability"] = (lead > 0 and (not MARGIN_CHECK or lead > av) and not (SAME_REQUEST and same)
                                  and not unclass and not (d60 and not start_wins(out.get("decomposition"), av)))
    return out


# G3 (v2.3 review): a missing start token (decision 58) also makes a pair unclassifiable
UNCLASSIFIABLE = "unclassifiable (no silence-ending or silence-starting token)"
CATEGORY_ALIASES = {"unclassifiable (no silence-ending token)": UNCLASSIFIABLE}   # v2.2 / v2.3 readouts' label
START_TERM_TIE = "start term within the margin (decision 60)"


def start_wins(dec, tie):
    """Decision 60 (START_TERM_RULE): an absent-vs-absent pair of different requests is a win only if its start term
    exceeds the tie margin; no start term (missing stamps or onset), or no margin, is no win."""
    if dec is None or tie is None:
        return False
    return dec["startDifference"] > (tie if MARGIN_CHECK else 0.0)


def lead_decomposition(f, fE, c, lead):
    """Decision 58: an absent-vs-absent lead = (the ledger's last completion before its silence - the sensor's last
    observation before its silence) + (g_ledger - g_sensor), each start taken relative to the onset in its own clock.
    `residual` = lead - the two terms (non-zero only where a time to detection is clipped at the onset, a log stamp is
    timed at its second's end, or a catch was moved out of a probe window)."""
    cmd = c.get("cmd") or {}
    se, ss, ge, gs = fE.get("silenceStartedBy"), f.get("silenceStartedBy"), fE.get("silenceGap"), f.get("silenceGap")
    if None in (se, ss, ge, gs) or not cmd:
        return None
    start = (se - cmd["A"]["mono"]) - (ss - cmd["A"][f.get("clock", "wall")])
    return {"startDifference": start, "gapDifference": ge - gs, "residual": lead - start - (ge - gs),
            "ledgerGap": ge, "sensorGap": gs}


def p4(eps, scope_own, bc_view):
    """Per (regime, rate): leave-one-episode-out selection on the other episodes (lowest mean, miss = hold; ties by
    name, the win share across tied sensors reported), H3 judgement on the held-out one."""
    rows = {}
    for regime in FAULT_REGIMES:
        per = {}
        for rate in RATES:
            es = sorted(eps_of(eps, regime, rate), key=episode_order)
            if not es:
                per[rate] = None
                continue
            if es[0]["kmap"].get("E") is None:
                per[rate] = {"n": len(es), "wins": None, "holds": None, "folds": [], "notEvaluable": True,
                             "note": "— (not evaluable): ledger family E not at the operating point at this rate "
                                     "(H2/H7)"}
                continue
            muted = [f for f in SENSOR_FAMILIES if any(collects(e["_c"], f) for e in es)
                     and es[0]["kmap"].get(f) is None]
            if P4_MUTED_DASH and muted:                  # B1 (decision 55): no "sensor missed", no "none"
                per[rate] = {"n": len(es), "wins": None, "holds": None, "folds": [], "notEvaluable": True,
                             "familiesNotAtOperatingPoint": muted,
                             "note": "— (not evaluable): family %s not at the operating point for this class at this "
                                     "rate (B1, decision 55)" % ", ".join(muted)}
                continue
            if len(es) < 2:                              # v2.2: leave-one-episode-out needs a training episode
                per[rate] = {"n": len(es), "wins": None, "holds": None, "folds": [], "notEvaluable": True,
                             "familiesNotAtOperatingPoint": [],
                             "note": "— (not evaluable): n = %d, leave-one-episode-out selection needs >= 2 "
                                     "episodes; the single-episode comparison is descriptive" % len(es),
                             "singleEpisode": single_episode(es[0], scope_own, bc_view)}
                continue
            cands = defaultdict(lambda n=len(es): [None] * n)
            for i, e in enumerate(es):
                for f in e["fires"]:
                    if f["family"] == "E" or not f["counts"] or f["own"] != scope_own:
                        continue
                    if not bc_view and f["bc"]:
                        continue
                    s = "%s:%s:%s" % (f["ch"], f["svc"], f["tok"])
                    if cands[s][i] is None or f["ttd"] < cands[s][i]["ttd"]:
                        cands[s][i] = f
            holds = [e["holdSeconds"] for e in es]
            ledger = [col_fire(e, "E", True) for e in es]
            ledger = [None if x == "absent" else x for x in ledger]
            folds, wins, missed = [], 0, 0
            for i, e in enumerate(es):
                train = [j for j in range(len(es)) if j != i]
                scored = []
                for s in sorted(cands):
                    ts = cands[s]
                    if all(ts[j] is None for j in train):
                        continue
                    scored.append((statistics.mean(ts[j]["ttd"] if ts[j] else holds[j] for j in train), s))
                if not scored:
                    fo = {"heldOut": i, "block": e["block"], "sensor": None, "tied": [], "trainMean": None}
                    fo.update(judge_fold(None, ledger[i], holds[i], e["_c"]))
                    folds.append(fo)
                    continue
                best = min(x for x, _ in scored)
                tied = [s for x, s in scored if x == best]
                s = tied[0]
                fo = {"heldOut": i, "block": e["block"], "sensor": s, "tied": tied, "trainMean": best}
                fo.update(judge_fold(cands[s][i], ledger[i], holds[i], e["_c"]))
                tj = [judge_fold(cands[t][i], ledger[i], holds[i], e["_c"])["win"] for t in tied]
                fo["tiedWinShare"] = [sum(tj), len(tj)]
                st = fo["sensorTtd"] if fo["sensorTtd"] is not None else holds[i]
                lt = fo["ledgerTtd"] if fo["ledgerTtd"] is not None else holds[i]
                fo["pairedDifference"] = lt - st
                fo["movedBy"] = cands[s][i]["movedBy"] if cands[s][i] else None
                wins += fo["win"]
                missed += fo["ledgerMissed"] and fo["sensorTtd"] is not None
                folds.append(fo)
            diffs = [fo.get("pairedDifference") for fo in folds if fo.get("pairedDifference") is not None]
            per[rate] = {"n": len(es), "wins": wins, "ledgerMissedSensorCaught": missed,
                         "familiesNotAtOperatingPoint": [f for f in SENSOR_FAMILIES if es[0]["kmap"].get(f) is None],
                         "holds": (wins >= P4_MIN) if len(es) == EPISODES else None, "folds": folds,
                         "candidates": len(cands),
                         "unclassifiable": sum(1 for fo in folds if fo["category"] == UNCLASSIFIABLE),
                         "sensorAbsentWithoutToken": sum(1 for fo in folds if fo.get("unclassifiable")),
                         "sensorSilenceSameRequest": sum(1 for fo in folds if fo.get("sensorSilence")),
                         "silenceStartSameRequest": sum(1 for fo in folds if fo.get("silenceStartSame")),
                         "startTermTies": sum(1 for fo in folds if fo["category"] == START_TERM_TIE),
                         "winsAvailability": sum(1 for fo in folds if fo.get("winAvailability")),
                         "availabilityEvaluable": sum(1 for fo in folds if fo.get("winAvailability") is not None),
                         "pairedDifferences": {"values": diffs, "mean": statistics.mean(diffs) if diffs else None,
                                               "min": min(diffs) if diffs else None,
                                               "max": max(diffs) if diffs else None}}
        rows[regime] = {"perRate": {"%g" % r: v for r, v in per.items()}, "highestRate": highest_rate(per)}
    return rows


def single_episode(e, scope_own, bc_view):
    """One episode, no selection (DECLARATION_OTEL.md P4, DECLARATION_TEASTORE.md: descriptive): every candidate
    sensor's first catch judged against the ledger's under H3 (a-c) and decision 57, fastest first."""
    best = {}
    for f in e["fires"]:
        if f["family"] == "E" or not f["counts"] or f["own"] != scope_own or (not bc_view and f["bc"]):
            continue
        s = "%s:%s:%s" % (f["ch"], f["svc"], f["tok"])
        if s not in best or f["ttd"] < best[s]["ttd"]:
            best[s] = f
    fE = col_fire(e, "E", True)
    fE = None if fE == "absent" else fE
    rows = []
    for s, f in sorted(best.items(), key=lambda kv: (kv[1]["ttd"], kv[0])):
        j = judge_fold(f, fE, e["holdSeconds"], e["_c"])
        rows.append({"sensor": s, "rule": f["rule"], "ttd": f["ttd"], "ledgerRule": j["ledgerRule"],
                     "ledgerTtd": j["ledgerTtd"], "lead": j["lead"], "category": j["category"], "win": j["win"],
                     "lower": f["ttd"] < (j["ledgerTtd"] if j["ledgerTtd"] is not None else e["holdSeconds"])})
    return {"block": e["block"], "campaignIndex": e.get("campaignIndex", 0), "ledgerRule": fE["rule"] if fE else None,
            "ledgerTtd": fE["ttd"] if fE else None, "sensors": rows,
            "categories": dict(Counter(r["category"] for r in rows)), "lowerThanLedger": sum(r["lower"] for r in rows)}


def highest_rate(per_rate):
    """The highest rate where P4 holds, else "none in {evaluable rates}"; every rate that is `—` (not evaluable: fewer
    than EPISODES episodes, or a family not at the operating point, B1) is named as "— at {rates}", also beside a hit
    (a `—` above the hit leaves the highest rate open)."""
    ev = [r for r in RATES if per_rate.get(r) is not None and per_rate[r].get("holds") is not None]
    missing = [r for r in RATES if r not in ev]
    dash = "— at {%s}" % ", ".join("%g" % r for r in missing) if missing else ""
    hit = [r for r in ev if per_rate[r]["holds"]]
    if hit:
        s = "%g" % hit[0]
    elif ev:
        s = "none in {%s}" % ", ".join("%g" % r for r in ev)
    else:
        return dash
    return s + ("; " + dash if dash else "")


# =========================================================================== H4: P1, P2

def first_failed(c, a, b):
    ts = [r.end for r in c["ledger"] if not r.ok and a <= r.end <= b]
    return min(ts) if ts else None


def classify_requests(reqs, lo, hi):
    out = Counter()
    for r in reqs:
        out["before" if r.end < lo else "after" if r.start > hi else "straddling"] += 1
    return dict(out)


def p1_interval(reqs, lo, hi, timeout):
    """H4: the expected first timeout over freeze instants in [lo, hi]. earliest = min start + T over requests not
    completed by lo (requests completing inside the interval are ambiguous and enter only here); latest = min start + T
    over requests not completed by hi. v2.1 passes hi + delta (M5): a request completing within delta of the pause
    event may have passed the paused service before the freeze."""
    e1 = [r.start + timeout for r in reqs if r.end > lo]
    e2 = [r.start + timeout for r in reqs if r.end > hi]
    return (min(e1) if e1 else None), (min(e2) if e2 else None)


def p1_delta(c):
    """M5 (decision 54, P1_AMBIGUITY_WINDOW_RULE): the cell's pre-onset median, over fault-free requests (ok, ended
    before startedMonotonic) whose trace has a span of the paused service, of (request end - the latest end of that
    service's spans in the request's trace), the span end mapped wall -> monotonic by the cell's fit. None: no such
    request."""
    lo, off, target = c["onset"]["lo"], c["align"]["offset"], c["target"]
    ends = c.get("spanEnds") or {}
    d = [r.end - (ends[r.token][target] - off) for r in c["ledger"]
         if r.ok and r.end < lo and r.token in ends and target in ends[r.token]]
    return (statistics.median(d) if d else None), len(d)


def p1_tolerance(c):
    """P1_TOLERANCE_RULE (decision 54): stamp granularities + (pause) Docker event granularity and the alignment
    residual + the cell's pre-onset median successful latency (bounds send-to-wait before the socket timeout)."""
    a = c["cmd"]["A"]["mono"]
    ok = [r.end - r.start for r in c["ledger"] if r.ok and r.end < a]
    parts = {"ledgerGranularity": c["ledgerStamps"]["monoGranularity"] or 0.0,
             "receiptGranularity": c.get("receiptGranularity") or 0.0,
             "sendToWait": statistics.median(ok) if ok else None}
    if (c.get("onset") or {}).get("hiKind", "docker-event") == "docker-event" and c["faultKind"] in dt.STOPPING:
        parts["dockerEventGranularity"] = 1.0 / NS_PER_S
        parts["alignmentResidual"] = c["align"]["residual"]
    if c.get("receiptAlign"):                       # TeaStore: the receipt's clock mapped onto the ledger's
        parts["receiptAlignmentResidual"] = c["receiptAlign"]["residual"]
    if parts["sendToWait"] is None:
        return None, parts
    return sum(parts.values()), parts


def pause_regime():
    """The system's one stopping-fault regime (Hotel search-pause, TeaStore auth-freeze, OTel frontend-pause)."""
    rs = [r for r in FAULT_REGIMES if FAULT_TARGETS[r][1] in dt.STOPPING]
    assert len(rs) == 1, "P1/P2 are declared for one pause regime per system: %s" % rs
    return rs[0]


def first_failed_row(c, a, b):
    rs = [r for r in c["ledger"] if not r.ok and a <= r.end <= b]
    return min(rs, key=lambda r: r.end) if rs else None


def predictions_p1(eps):
    out = []
    for e in [x for x in eps if x["regime"] == pause_regime()]:
        c = e["_c"]
        T = float(c["timing"].get("requestTimeoutSeconds", P2_DOBS_S))
        on = c["onset"]
        lo, hi = on["lo"], on["hi"]
        obs = first_failed(c, e["onset"]["mono"], e["end"]["mono"])
        row = {"rate": e["rate"], "block": e["block"], "cell": e["cell"], "lo": lo, "hi": hi,
               "intervalSeconds": (hi - lo) if hi is not None else None, "hiSource": on["hiSource"],
               "observed": (obs - lo) if obs is not None else None, "expected": None, "tolerance": None, "ok": None}
        if hi is None:
            out.append(row)
            continue
        delta, nd = p1_delta(c)
        row.update(delta=delta, deltaRequests=nd)
        if P1_AMBIGUITY and delta is None:          # M5: no fault-free request names the paused service: —
            row["deltaNote"] = "no pre-onset request with a span of %s: delta —, P1 —" % c["target"]
            out.append(row)
            continue
        amb_hi = hi + delta if P1_AMBIGUITY else hi
        if not P1_INTERVAL:                         # planted defect: v1's point expectation by schedule
            sched = sorted(r.sched for r in c["ledger"] if r.sched >= lo)
            hi = amb_hi = lo
            e1 = e2 = (sched[0] + T) if sched else None
        else:
            e1, e2 = p1_interval(c["ledger"], lo, amb_hi, T)
        tol, parts = p1_tolerance(c)
        row.update(expected=[(e1 - lo) if e1 is not None else None, (e2 - lo) if e2 is not None else None],
                   ambiguityWindow=[0.0, amb_hi - lo],
                   ambiguous=sum(1 for r in c["ledger"] if lo <= r.end <= amb_hi),
                   tolerance=tol, toleranceParts=parts, requestClasses=classify_requests(c["ledger"], lo, hi),
                   dispatchLagMax=max((r.start - r.sched for r in c["ledger"]), default=None))
        if obs is not None and e1 is not None and e2 is not None and tol is not None:
            row["ok"] = (e1 - tol) <= obs <= (e2 + tol)
            row["deviation"] = 0.0 if row["ok"] else ((obs - e2) if obs > e2 else (obs - e1))
            if not row["ok"] and P1_ERROR_ANSWER.get(SYSTEM) and obs < e1 - tol:
                fr = first_failed_row(c, e["onset"]["mono"], e["end"]["mono"])
                det = (c.get("ledgerDetail") or {}).get(fr.seq) if fr is not None else None
                row["firstFailedAnswer"] = det
                if det and det.get("errorAnswer"):        # P1_ERROR_ANSWER_RULE (TeaStore's declared alternative)
                    row["ok"], row["branch"] = True, "error answer before the timeout (declared alternative)"
        elif obs is None:
            row["ok"] = False
        out.append(row)
    ev = [x for x in out if x["ok"] is not None]
    for x in ev:                                    # F2: the branch through which an episode holds, always named
        if x["ok"]:
            x.setdefault("branch", P1_TIMEOUT_BRANCH)
    return {"perEpisode": out, "k": sum(1 for x in ev if x["ok"]), "n": len(ev), "notEvaluable": len(out) - len(ev),
            "holdsByBranch": dict(Counter(x["branch"] for x in ev if x["ok"])),
            "perRate": {"%g" % r: [sum(1 for x in ev if x["rate"] == r and x["ok"]), sum(1 for x in ev if x["rate"] == r)]
                        for r in RATES},
            "holds": (all(x["ok"] for x in ev) if ev and len(ev) == len(out) else None)}


P1_TIMEOUT_BRANCH = "timeout interval"


def p2_threshold(rate):
    return 1.0 + rate * P2_DOBS_S + P2_EPS


def predictions_p2(eps):
    out = {}
    for rate in RATES:
        es = sorted(eps_of(eps, pause_regime(), rate), key=episode_order)
        if not es:
            out["%g" % rate] = None
            continue
        counts, det = [], []
        for e in es:
            c, a = e["_c"], e["onset"]["mono"]
            t = first_failed(c, a, e["end"]["mono"])
            counts.append(v1.failed_before(c["ledger"], a, t if t is not None else a + e["holdSeconds"]))
            det.append(t is not None)
        thr = p2_threshold(rate)
        ok = [n <= thr for n in counts]
        out["%g" % rate] = {"k": sum(ok), "n": len(ok), "threshold": thr, "perEpisode": counts,
                            "failedRuleDetected": det, "holds": (sum(ok) >= P2_MIN) if len(ok) == EPISODES else None}
    return out


# =========================================================================== H11: P3

def p3_members(fam, tok):
    for key in (fam + ":" + tok, fam):
        if key in P3_TI:
            return bool(P3_TI[key]["trafficIndependent"])
    return False


def predictions_p3(eps):
    out = []
    for regime in FAULT_REGIMES:
        act = set((ACTUATOR.get(regime) or {}).get("metric", []))
        allowed = sorted(k for k, v in P3_TI.items() if v["trafficIndependent"]) if P3_RESTRICT else ["*"]
        if not allowed:
            out.append({"regime": regime, "state": DASH, "holds": None, "set": [],
                        "reason": "no family is traffic-independent by mechanism (registry P3_TRAFFIC_INDEPENDENT; "
                                  "actuator readback excluded, decision 26)"})
            continue
        sides = {}
        for rate in (RATES[0], RATES[-1]):
            es = sorted(eps_of(eps, regime, rate), key=episode_order)
            hits = []
            for e in es:
                best = None
                for f in e["fires"]:
                    if f["family"] == "E" or not f["counts"] or f["bc"]:
                        continue
                    if P3_RESTRICT and (not p3_members(f["family"], f["tok"]) or
                                        (f["svc"] == e["target"] and f["tok"] in act)):
                        continue
                    if best is None or f["ttd"] < best:
                        best = f["ttd"]
                hits.append(best)
            sides["%g" % rate] = v1.summarise(hits, [e["holdSeconds"] for e in es]) if es else None
        hi, lo = sides["%g" % RATES[0]], sides["%g" % RATES[-1]]
        cad = max(P3_CADENCE_S.values())
        if not hi or not lo or hi["n"] != EPISODES or lo["n"] != EPISODES:
            state, holds = "not evaluable", None
        elif hi["k"] == 0:
            state, holds = "untestable (no catch at %g/s)" % RATES[0], None
        else:
            holds = lo["penalisedMeanTtd"] <= hi["penalisedMeanTtd"] + cad
            state = "holds" if holds else "fails"
        out.append({"regime": regime, "state": state, "holds": holds, "set": allowed, "sides": sides})
    return out


# =========================================================================== H5: exposure

def exposure(cells, eps):
    valid = [c for c in cells if c["valid"]]
    if EXPOSURE_TRACES:
        edges = set()
        for c in valid:
            if c["target"] is None:
                edges |= c["spanEdges"]
        path, frontier = {ENTRY}, [ENTRY]
        while frontier:
            s = frontier.pop()
            for x, y in edges:
                if x == s and y not in path:
                    path.add(y)
                    frontier.append(y)
        pm = project_map()
        stores = set()
        for c in valid:
            if c["target"] is None and c["depends"]:
                for s in path:
                    for d in c["depends"].get(s, []):
                        if pm.role(SUT, d) == "data store":
                            stores.add(d)
        route_path = sorted(path | stores)
        projected = {"traceEdges": sorted("%s->%s" % e for e in edges), "dataStoresByDependsOn": sorted(stores)}
    else:
        route_path = sorted({k[1] for c in valid for k in c["prep"]} | {ENTRY})
        projected = {"traceEdges": [], "dataStoresByDependsOn": []}
    out = {"routePath": route_path, "projection": projected, "episodes": {}}
    sensors = set()
    for e in eps:
        c = e["_c"]
        n = sum(1 for r in c["ledger"] if e["onset"]["mono"] <= r.start <= e["end"]["mono"])
        out["episodes"][e["cell"]] = {"regime": e["regime"], "rate": e["rate"], "block": e["block"],
                                      "requestsStartedInWindow": n,
                                      "exposedServices": route_path if n >= 1 else []}
        sensors |= {"%s:%s:%s" % k for k in c["prep"]}
    exposed_any = set()
    for v in out["episodes"].values():
        exposed_any |= set(v["exposedServices"])
    never = sorted(s for s in sensors if s.split(":")[1] not in exposed_any)
    out["neverExposedSensors"] = never
    out["neverExposedServices"] = sorted({s.split(":")[1] for s in never})
    return out


# =========================================================================== v1 comparison

def v1_reference(campaign, root, dirs, path):
    """v1's reference verdicts: from its committed readout (the input digest must match this evidence), else by
    running v1 at its reference point."""
    if path:
        J = json.loads(Path(path).read_text())
        mine = v1.input_digest(root, dirs)["sha256"]
        if J["provenance"]["input"]["sha256"] != mine:
            raise SystemExit("v1 readout %s was computed on different evidence (input digest %s != %s)"
                             % (path, J["provenance"]["input"]["sha256"], mine))
        pred = J["reference"]["predictions"]
        verdicts = {k: v["reference"] for k, v in J["gridAgreement"].items()}
        source = "%s (input digest matches)" % path
    else:
        R = v1.run(campaign, grid=[v1.REF], variants=False)
        pred = dt.strip(R["reference"]["predictions"])
        verdicts = R["referenceVerdicts"]
        source = "v1.run at its reference point (in process)"
    perrate = {}
    for scope, rows in pred["P4"].items():
        for regime, x in rows.items():
            for r, v in x["perRate"].items():
                perrate["%s %s r%s" % (scope, regime, r)] = None if v is None else v.get("holds")
    return {"source": source, "predictions": pred, "verdicts": verdicts, "p4PerRate": perrate}


def v2_verdicts(pred):
    v = {"P1": pred["P1"]["holds"]}
    for r, x in pred["P2"].items():
        v["P2@%s" % r] = None if x is None else x["holds"]
    for x in pred["P3"]:
        for key in ("P3 %s S" % x["regime"], "P3 %s S:own" % x["regime"]):
            v[key] = x["state"]
    for scope, rows in pred["P4"].items():
        for regime, x in rows.items():
            v["%s %s" % (scope, regime)] = x["highestRate"]
            for r, y in x["perRate"].items():
                v["%s %s r%s" % (scope, regime, r)] = None if y is None else y.get("holds")
    return v


def moved_verdicts(old, pred, eps=()):
    """Every verdict that differs between v1 (reference) and v2 (primary), with the rule that moved it."""
    new = v2_verdicts(pred)
    oldv = dict(old["verdicts"], **old["p4PerRate"])
    rows = []
    for key in sorted(oldv):
        if key not in new or oldv[key] == new[key]:
            continue
        rows.append({"verdict": key, "v1": oldv[key], "v2": new[key], "reason": reason_for(key, old, pred, eps)})
    return rows


RULE_OF_FLAG = {"BC-actuator-readback": "decision 26", "BC-caller-span": "BC, AMENDMENT_3 content",
                "BC-caller-log": "BC by content", "BC-idle-cpu": "BC", "BC-downstream-absent": "BC",
                "BC-ledger-stopped-on-path": "BC"}


def v1_sensor_fate(sensor, e, y_fold):
    """What v2.1 did, in the same held-out episode, with the sensor v1 selected: the rule that removed or kept it."""
    if not sensor:
        return "v1 selected no sensor"
    ch, svc, tok = sensor.split(":", 2)
    c = e["_c"]
    meta = (c["prep"].get((ch, svc, tok)) or (None, None, None))[2]
    fam = family_of(c, ch, meta) if meta else None
    if fam is not None and e["kmap"].get(fam) is None:
        return "%s: family %s not at the operating point (H2/H7)" % (sensor, fam)
    fs = [f for f in e["fires"] if "%s:%s:%s" % (f["ch"], f["svc"], f["tok"]) == sensor and f["counts"]]
    if not fs:
        return "%s: no catch under v2.1's detector (H1 pooled baseline, relative floor, fitted K, MAD = 0 —)" % sensor
    if all(f["bc"] for f in fs):
        flags = sorted({x for f in fs for x in f["bc"]})
        return "%s: by construction in v2.1 (%s)" % (sensor, ", ".join("%s, %s" % (x, RULE_OF_FLAG.get(x, "BC"))
                                                                    for x in flags))
    if y_fold.get("sensor") == sensor:
        return "%s: v2.1 %s" % (sensor, CATEGORY_RULE.get(y_fold["category"], y_fold["category"]))
    return "%s: caught, but v2.1 selected %s (%s)" % (sensor, y_fold.get("sensor") or DASH,
                                                     CATEGORY_RULE.get(y_fold["category"], y_fold["category"]))


CATEGORY_RULE = {"same request": "same request (H3 c, row 15)", "lead within the margin": "lead within the margin (H3 b)",
                 "log lead not counted (no app stamp)": "log lead not counted (H3 b)", "not faster": "not faster (H3 a)",
                 "ledger missed (counted apart)": "ledger missed, counted apart (H3 d)",
                 "sensor missed": "sensor missed", "win": "win",
                 UNCLASSIFIABLE: "unclassifiable: the sensor's `absent` names no request (decision 57)"}


def reason_for(key, old, pred, eps=()):
    if key == "P1":
        p = pred["P1"]
        return ("H4 + M5: onset interval [startedMonotonic, effect bound], ambiguity window up to the pause event + "
                "delta (decision 54), interval expectation +- P1_TOLERANCE_RULE (decision 54), observed = the ledger's "
                "first `failed` catch; v1: point expectation by schedule +- 0.5 s, observed = E. v2.1 %d/%d, not "
                "evaluable %d." % (p["k"], p["n"], p["notEvaluable"]))
    if key.startswith("P2@"):
        r = key.split("@", 1)[1]
        return "P2 recomputed: v1 counts %s, v2 counts %s" % (
            (old["predictions"]["P2"].get(r) or {}).get("perEpisode"), (pred["P2"].get(r) or {}).get("perEpisode"))
    if key.startswith("P3"):
        return "H11 (decision 45): P3 restricted to families traffic-independent by mechanism; the registry set is empty"
    scope, regime = key.split()[0], key.split()[1]
    rates = [key.split()[2][1:]] if len(key.split()) > 2 else ["%g" % r for r in RATES]
    parts = []
    for r in rates:
        y = pred["P4"][scope][regime]["perRate"].get(r)
        x = ((old["predictions"]["P4"][scope][regime]["perRate"]).get(r) or {})
        if y is None:
            continue
        if y.get("note"):
            parts.append("r%s: %s" % (r, y["note"]))
            continue
        cats = Counter(fo["category"] for fo in y["folds"])
        v1w = sum(1 for fo in (x.get("folds") or []) if fo.get("win"))
        es = sorted(eps_of(eps, regime, float(r)), key=episode_order)
        fates = Counter()
        for fo in (x.get("folds") or []):
            i = fo.get("heldOut")
            if fo.get("win") and i is not None and i < len(es) and i < len(y["folds"]):
                fates[v1_sensor_fate(fo.get("sensor"), es[i], y["folds"][i])] += 1
        abs_e = sum(1 for fo in y["folds"] if fo.get("ledgerRule") == "absent")
        parts.append("r%s: v1 wins %d/%d%s; v2.1 wins %d/%d, folds: %s%s" % (
            r, v1w, len(x.get("folds") or []),
            (" (in v2.1, v1's winning sensor: %s)" % "; ".join("%s x%d" % kv for kv in sorted(fates.items())))
            if fates else "", y["wins"] or 0, len(y["folds"]),
            ", ".join("%s %d" % (CATEGORY_RULE.get(k, k), n) for k, n in sorted(cats.items())),
            ("; the ledger's first catch is `absent` in %d (H3 e)" % abs_e) if abs_e else ""))
    return "; ".join(parts) or "—"


# =========================================================================== v2 (v2-fix1) comparison

def v2_reference(root, dirs, path):
    """v2-fix1's committed readout (sweep_analysis_v2.json, 8cdad26): its input digest must match this evidence."""
    J = json.loads(Path(path).read_text())
    mine = input_digest(root, dirs)["sha256"]
    if J["provenance"]["input"]["sha256"] != mine:
        raise SystemExit("v2 readout %s was computed on different evidence (input digest %s != %s)"
                         % (path, J["provenance"]["input"]["sha256"], mine))
    return {"source": "%s (input digest matches)" % path, "predictions": J["predictions"],
            "verdicts": v2_verdicts(J["predictions"]), "kmaps": (J.get("kmaps") or {}).get("primary") or {},
            "scriptSha256": J.get("scriptSha256"), "settings": J.get("settings"), "version": J.get("version")}


def _verdict_text(v):
    return {True: "holds", False: "fails", None: DASH}.get(v, v) if not isinstance(v, str) else v


def _rate_summary(y):
    if y is None:
        return DASH + " (no episodes)"
    if y.get("note"):
        return y["note"]
    cats = Counter(fo["category"] for fo in y.get("folds") or [])
    return "wins %s/%d (%s)" % (y.get("wins") if y.get("wins") is not None else DASH, len(y.get("folds") or []),
                                ", ".join("%s %d" % kv for kv in sorted(cats.items())) or DASH)


def _k_change(old_k, new_kmap, fams):
    out = []
    for f in fams:
        a, b = (old_k or {}).get(f), (new_kmap or {}).get(f)
        out.append("%s %s -> %s" % (f, "%g" % a if a is not None else DASH, "%g" % b if b is not None else DASH))
    return ", ".join(out)


def reason_v21(key, old2, pred, kmaps, mad0):
    """Why a verdict moved between v2-fix1 and v2.1: the round-11 rule, with the folds or episodes that changed.
    kmaps: v2.1's primary regime -> rate -> {family: K}; mad0: rate -> set of scale-not-estimable sensor ids."""
    if key == "P1":
        o, n = old2["predictions"]["P1"], pred["P1"]
        oe = {(x["rate"], x["block"]): x for x in o["perEpisode"]}
        ch = []
        for x in n["perEpisode"]:
            y = oe.get((x["rate"], x["block"])) or {}
            if y.get("ok") != x.get("ok"):
                ch.append("r%g b%s %s -> %s (delta %s s; expected latest %s -> %s s; tolerance %s s; observed %s s)" % (
                    x["rate"], x["block"], _verdict_text(y.get("ok")), _verdict_text(x.get("ok")), f3(x.get("delta")),
                    f3((y.get("expected") or [None, None])[1]), f3((x.get("expected") or [None, None])[1]),
                    f3(x.get("tolerance")), f3(x.get("observed"))))
        return ("M5 (decision 54): ambiguity window [startedMonotonic, pause event + delta], delta = pre-onset median of "
                "(request end - paused service's span end), tolerance = measured timing terms; v2-fix1 %d/%d, v2.1 "
                "%d/%d, not evaluable %d; episodes that changed: %s" % (
                    o["k"], o["n"], n["k"], n["n"], n["notEvaluable"], "; ".join(ch) or "none"))
    if key.startswith("P2@"):
        r = key.split("@", 1)[1]
        return "not a round-11 rule (P2 unchanged): v2-fix1 counts %s, v2.1 counts %s" % (
            (old2["predictions"]["P2"].get(r) or {}).get("perEpisode"), (pred["P2"].get(r) or {}).get("perEpisode"))
    if key.startswith("P3"):
        return "not a round-11 rule (H11, decision 45, unchanged)"
    scope, regime = key.split()[0], key.split()[1]
    rates = [key.split()[2][1:]] if len(key.split()) > 2 else ["%g" % r for r in RATES]
    parts = []
    for r in rates:
        y = pred["P4"][scope][regime]["perRate"].get(r)
        x = old2["predictions"]["P4"][scope][regime]["perRate"].get(r)
        new_k = kmaps.get(regime, {}).get(float(r))
        old_k = old2["kmaps"].get(r)
        if y is not None and y.get("notEvaluable"):
            fams = y.get("familiesNotAtOperatingPoint") or ["E"]
            parts.append("r%s: v2-fix1 %s; v2.1 %s; K (v2-fix1 all sensors -> v2.1 scored set, M3/M4): %s" % (
                r, _rate_summary(x), y["note"], _k_change(old_k, new_k, fams)))
            continue
        if y is None or x is None:
            parts.append("r%s: v2-fix1 %s; v2.1 %s" % (r, _rate_summary(x), _rate_summary(y)))
            continue
        ch = []
        ofo = x.get("folds") or []
        for i, fo in enumerate(y["folds"]):
            of = ofo[i] if i < len(ofo) else {}
            if (of.get("sensor"), of.get("category")) == (fo["sensor"], fo["category"]):
                continue
            tags = []
            if fo.get("sameSilence"):
                tags.append("M1, decision 51: the ledger's `absent` names the request that ends its silence")
            if fo.get("sensorSilence"):
                tags.append("decision 57: the sensor's `absent` names the request that ends its silence")
            if fo["category"] == UNCLASSIFIABLE:
                tags.append("decision 57: unclassifiable, the sensor's silence-ending observation names no request")
            if of.get("sensor") and of["sensor"] in mad0.get(float(r), ()):
                tags.append("M2, decision 52: v2-fix1's sensor is scale-not-estimable")
            if of.get("sensor") != fo["sensor"]:
                tags.append("K (M3/M4): %s" % _k_change(old_k, new_k, SENSOR_FAMILIES))
            ch.append("ep%d `%s` %s -> `%s` %s%s" % (
                fo["heldOut"] + 1, of.get("sensor") or DASH, of.get("category") or DASH, fo["sensor"] or DASH,
                fo["category"], (" (%s)" % "; ".join(tags)) if tags else ""))
        parts.append("r%s: v2-fix1 %s; v2.1 %s%s" % (r, _rate_summary(x), _rate_summary(y),
                                                     ("; folds: " + "; ".join(ch)) if ch else ""))
    return "; ".join(parts) or DASH


def moved_vs_v2(old2, pred, kmaps, mad0):
    """Every verdict that differs between v2-fix1 and this version (primary), with the round-11 (or decision-57) rule that
    moved it."""
    new = v2_verdicts(pred)
    rows = []
    for key in sorted(set(old2["verdicts"]) | set(new)):
        a, b = old2["verdicts"].get(key), new.get(key)
        if a == b:
            continue
        rows.append({"verdict": key, "v2fix1": a, "v22": b, "reason": reason_v21(key, old2, pred, kmaps, mad0)})
    return rows


# =========================================================================== v2.1 / v2.2 comparison (decisions 57, 58)

P4_VIEWS = ("P4a", "P4b", "P4a withBC", "P4b withBC")
COMPARE_RULES = {"v2.1": ("decision 57", "decision 58", "decision 60", "F3", "G3"),
                 "v2.2": ("decision 58", "decision 60", "F3", "G3"), "v2.3": ("decision 60", "G3")}
COMPARISONS = ("v2.3", "v2.2", "v2.1")


def _old_cat(of):
    """An earlier readout's fold category under this version's labels (G3 renamed the unclassifiable label)."""
    c = of.get("category")
    return CATEGORY_ALIASES.get(c, c)
NOT_LISTED = "not decision 57/58 or a listed v2.3 fix"


def fold_rules(fo, of):
    """Which v2.2 / v2.3 rule accounts for a P4 fold whose (sensor, category) changed against an earlier readout."""
    tags = []
    if fo["category"] == "same request" and fo.get("sensorSilence"):
        tags.append("decision 57: the sensor's `absent` is ended by the ledger's catching request")
    elif fo["category"] == "same request" and fo.get("silenceStartSame"):
        tags.append("decision 58: the two silences start with the same request")
    if fo["category"] == UNCLASSIFIABLE:
        tags += fo.get("unclassifiableBy") or ["decision 57/58: no token"]
    if fo["category"] == START_TERM_TIE:
        tags.append("decision 60: the start term %s s is within the margin %s s (gap term %s s not counted)" % (
            fsmall((fo.get("decomposition") or {}).get("startDifference")), fsmall(fo.get("margin")),
            fsmall((fo.get("decomposition") or {}).get("gapDifference"))))
    if _old_cat(of) == "log lead not counted (no app stamp)" and fo["category"] != _old_cat(of):
        tags.append("F3: a json-line record's own stamp (v2.3)")
    return tags or [NOT_LISTED]


def _rule_ok(tags, allowed):
    return all(any(t.startswith(a) for a in allowed) for t in tags)


def reason_moved(key, old, pred, allowed):
    """Why a verdict moved against an earlier readout: the changed folds with the rule of each; `allowed` = the rules
    that may move it (anything else is named, never hidden)."""
    if not key.startswith("P4"):
        return "not a decision-57/58 rule: earlier %s, now %s" % (
            _verdict_text(old["verdicts"].get(key)), _verdict_text(v2_verdicts(pred).get(key)))
    scope, regime = key.split()[0], key.split()[1]
    rates = [key.split()[2][1:]] if len(key.split()) > 2 else ["%g" % r for r in RATES]
    parts = []
    for r in rates:
        y = pred["P4"][scope][regime]["perRate"].get(r)
        x = old["predictions"]["P4"][scope][regime]["perRate"].get(r)
        if y is None or x is None or y.get("notEvaluable") or x.get("notEvaluable"):
            parts.append("r%s: earlier %s; now %s" % (r, _rate_summary(x), _rate_summary(y)))
            continue
        ch = []
        ofo = x.get("folds") or []
        for i, fo in enumerate(y["folds"]):
            of = ofo[i] if i < len(ofo) else {}
            if (of.get("sensor"), _old_cat(of)) == (fo["sensor"], fo["category"]):
                continue
            tags = fold_rules(fo, of)
            ch.append("ep%d `%s` %s -> `%s` %s (%s)" % (
                fo["heldOut"] + 1, of.get("sensor") or DASH, of.get("category") or DASH, fo["sensor"] or DASH,
                fo["category"], "; ".join(tags if _rule_ok(tags, allowed) else tags + ["**unexpected**"])))
        parts.append("r%s: earlier %s; now %s%s" % (r, _rate_summary(x), _rate_summary(y),
                                                   ("; folds: " + "; ".join(ch)) if ch else ""))
    return "; ".join(parts) or DASH


def moved_vs(old, pred, allowed):
    """Every verdict that differs between an earlier readout (v2.1 or v2.2) and this one (primary)."""
    new = v2_verdicts(pred)
    rows = []
    for key in sorted(set(old["verdicts"]) | set(new)):
        a, b = old["verdicts"].get(key), new.get(key)
        if a == b:
            continue
        rows.append({"verdict": key, "old": a, "new": b, "reason": reason_moved(key, old, pred, allowed)})
    return rows


def fold_changes(old, res, allowed):
    """F12 (v2.2 review): every P4 fold whose selected sensor or category differs from the earlier readout, in every
    setting (primary, floor arm, reference K, per-system K) and every view (P4a, P4b, with and without BC), also where
    the verdict did not move; each with the rule that accounts for it."""
    out = []
    for setting in SETTINGS:
        old_s = ((old.get("settings") or {}).get(setting) or {}).get("P4") or {}
        for view in P4_VIEWS:
            for regime, x in res[setting]["P4"][view].items():
                for r, y in x["perRate"].items():
                    o = ((old_s.get(view) or {}).get(regime) or {}).get("perRate", {}).get(r)
                    if not y or not o:
                        continue
                    ofo = o.get("folds") or []
                    for i, fo in enumerate(y.get("folds") or []):
                        of = ofo[i] if i < len(ofo) else {}
                        if (of.get("sensor"), _old_cat(of)) == (fo["sensor"], fo["category"]):
                            continue
                        tags = fold_rules(fo, of)
                        out.append({"setting": setting, "view": view, "regime": regime, "rate": r,
                                    "block": fo["block"], "old": [of.get("sensor"), of.get("sensorRule"),
                                                                  of.get("category")],
                                    "new": [fo["sensor"], fo["sensorRule"], fo["category"]], "rules": tags,
                                    "explained": _rule_ok(tags, allowed)})
    return out


def comparison(old, pred, res, allowed):
    folds = fold_changes(old, res, allowed)
    return {"source": old["source"], "scriptSha256": old.get("scriptSha256"), "allowedRules": list(allowed),
            "moved": moved_vs(old, pred, allowed), "folds": folds,
            "foldsBySettingView": dict(Counter("%s / %s" % (x["setting"], x["view"]) for x in folds)),
            "foldsByRule": dict(Counter(t for x in folds for t in x["rules"])),
            "unexplained": sum(1 for x in folds if not x["explained"])}


def decision57_summary(pred):
    """Decision 57 per (scope, class, rate), primary: P4 folds whose selected sensor caught by `absent`, of them
    same-request through the silence-ending observation, unclassifiable (no token, no win), and the token sources."""
    rows, tot = [], Counter()
    for scope, regs in pred["P4"].items():
        for regime, x in regs.items():
            for r, y in x["perRate"].items():
                fos = [fo for fo in (y or {}).get("folds") or [] if fo.get("sensorRule") == "absent"]
                if not fos:
                    continue
                aa = [fo for fo in fos if fo.get("ledgerRule") == "absent"]
                row = {"scope": scope, "regime": regime, "rate": r, "foldsSensorAbsent": len(fos),
                       "sameRequest": sum(1 for fo in fos if fo.get("sensorSilence")),
                       "unclassifiableDecisive": sum(1 for fo in fos if fo["category"] == UNCLASSIFIABLE),
                       "withoutToken": sum(1 for fo in fos if fo.get("unclassifiable")),
                       "tokenSources": dict(Counter(fo.get("sensorSilenceSource") or DASH for fo in fos)),
                       "absentAbsent": len(aa),
                       "sameByStart": sum(1 for fo in aa if fo.get("silenceStartSame")),
                       "sameByStartOnly": sum(1 for fo in aa if fo.get("silenceStartSame") and not fo.get("sensorSilence")),
                       "startTermTie": sum(1 for fo in aa if fo["category"] == START_TERM_TIE),
                       "startTokenSources": dict(Counter(fo.get("sensorSilenceStartSource") or DASH for fo in aa)),
                       "decompositions": [dict(fo["decomposition"], block=fo["block"], lead=fo["lead"],
                                               category=fo["category"]) for fo in aa if fo.get("decomposition")]}
                rows.append(row)
                for k in ("foldsSensorAbsent", "sameRequest", "unclassifiableDecisive", "withoutToken", "absentAbsent",
                          "sameByStart", "sameByStartOnly", "startTermTie"):
                    tot[k] += row[k]
    return {"rows": rows, "totals": dict(tot)}


# =========================================================================== whole campaign

def run(campaign, v1_readout=None, compare=True, v2_readout=None, v21_readout=None, system="hotel",
        v22_readout=None, v23_readout=None):
    """compare False skips the v1 comparison (the planted-defect tests); v1_readout None runs v1 in process;
    v2_readout (v2-fix1's JSON) adds the v2-fix1 -> this version's moved-verdicts table (round-11 rules named);
    v21_readout / v22_readout (v2.1's / v2.2's JSON) add the moved-verdict tables and every changed P4 fold in every
    setting and view against them (decisions 57, 58 and the v2.3 fixes). campaign: one campaign directory or a list
    of them, all of one system; their cells are pooled (H1, decision 31: all fault-free time per system x rate, the
    sweep's no-fault cells and the quiet runs'; DECLARATION_QUIET_TEASTORE.md / _OTEL.md open questions 1-2). The v1,
    v2 and v2.1 comparisons are Hotel's and need one campaign."""
    with use_system(system):
        return _run(campaign, v1_readout, compare, v2_readout, v21_readout, v22_readout, v23_readout)


def system_io():
    """(find cells, load or list as not scored) per system."""
    return {"hotel": (v1.find_cells, load_or_invalid), "teastore": (teastore_find_cells, teastore_load_or_invalid),
            "otel": (otel_find_cells, otel_load_or_invalid)}[SYSTEM]


def find_and_load(campaigns):
    find, load = system_io()
    found, cells = [], []
    for i, campaign in enumerate(campaigns):
        root, dirs = find(campaign)
        found.append((root, dirs))
        for d in dirs:
            c = load(d)
            c["campaignIndex"] = i
            cells.append(c)
    return found, cells


def _run(campaign, v1_readout, compare, v2_readout, v21_readout, v22_readout=None, v23_readout=None):
    campaigns = [campaign] if isinstance(campaign, (str, Path)) else list(campaign)
    located, cells = find_and_load(campaigns)
    single = len(located) == 1
    if (v1_readout or v2_readout or v21_readout or v22_readout or v23_readout) and (SYSTEM != "hotel" or not single):
        raise SystemExit("the v1 / v2 / v2.1 / v2.2 / v2.3 comparisons are Hotel's and need exactly one campaign")
    compare = compare and SYSTEM == "hotel" and single
    root, dirs = located[0]
    valid = [c for c in cells if c["valid"]]
    ctx = make_ctx(valid)
    fits = fits_for(cells)
    rates = sorted({c["rate"] for c in valid}, reverse=True)
    lf = loco_fits(cells)
    ops = {arm: operating_point(cells, share, lf, ctx) for arm, share in ARMS.items()}
    kmaps = {"primary": kmaps_from(ops["primary"], rates), "arm": kmaps_from(ops["arm"], rates),
             "reference": {regime: {r: {f: K_REF for f in FAMILIES} for r in rates} for regime in FAULT_REGIMES},
             "systemK": kmaps_from(ops["primary"], rates, unit="system")}
    shares = {"primary": ARMS["primary"], "arm": ARMS["arm"], "reference": ARMS["primary"], "systemK": ARMS["primary"]}
    res = {}
    for s in SETTINGS:
        eps = analyse(cells, ctx, fits, kmaps[s], shares[s])
        res[s] = {"eps": eps, "primary": primary_table(eps, ops["arm"] if s == "arm" else ops["primary"]),
                  "P4": {"P4a": p4(eps, False, False), "P4b": p4(eps, True, False),
                         "P4a withBC": p4(eps, False, True), "P4b withBC": p4(eps, True, True)}}
    prim = res["primary"]["eps"]
    expo = exposure(cells, prim)
    pred = {"P1": predictions_p1(prim), "P2": predictions_p2(prim), "P3": predictions_p3(prim),
            "P4": {k: res["primary"]["P4"][k] for k in ("P4a", "P4b")}}
    old = v1_reference(campaign, root, dirs, v1_readout) if compare else None
    old2 = v2_reference(root, dirs, v2_readout) if v2_readout else None
    old21 = v2_reference(root, dirs, v21_readout) if v21_readout else None
    old22 = v2_reference(root, dirs, v22_readout) if v22_readout else None
    old23 = v2_reference(root, dirs, v23_readout) if v23_readout else None
    mad0 = {r: {"%s:%s:%s" % k for k in f.madZero} for r, f in fits.items()} if POOLED else {}
    found = Counter((c["regime"], c["rate"]) for c in cells)
    vcount = Counter((c["regime"], c["rate"]) for c in valid)
    hc = v1.harness_commit(root) if SYSTEM == "hotel" else (
        ", ".join(sorted({c["harnessCommit"] for c in cells if c.get("harnessCommit")})) or None)
    prov = {"harnessCommit": hc,
            "planSha256": sorted({c["planSha256"] for c in cells if c.get("planSha256")}),
            "admissionSha256": sorted({c["admissionSha256"] for c in cells if c.get("admissionSha256")}),
            "input": input_digest(root, dirs) if single else input_digest_multi(located),
            "inputV1Files": v1.input_digest(root, dirs) if SYSTEM == "hotel" and single else None}
    return {"system": SYSTEM, "campaign": root if single else [r for r, _ in located],
            "campaigns": [str(r) for r, _ in located], "cells": cells, "ctx": ctx, "fits": fits, "ops": ops, "kmaps": kmaps, "results": res,
            "predictions": pred, "exposure": expo, "v1": old, "moved": moved_verdicts(old, pred, prim) if old else None,
            "v2": old2, "movedVsV2": moved_vs_v2(old2, pred, kmaps["primary"], mad0) if old2 else None,
            "vs": {k: comparison(o, pred, res, COMPARE_RULES[k]) for k, o in (
                ("v2.1", old21), ("v2.2", old22), ("v2.3", old23)) if o},
            "decision57": decision57_summary(pred),
            "found": found,
            "valid": vcount, "provenance": prov, "secondary": secondary_table(prim),
            "perSensor": per_sensor(prim, expo)}


def input_digest_multi(found):
    """Several campaigns: the sha256 over each campaign's own digest (input_digest), in the order given."""
    per = [input_digest(r, d) for r, d in found]
    return {"files": sum(x["files"] for x in per),
            "sha256": hashlib.sha256("\n".join(x["sha256"] for x in per).encode()).hexdigest(), "perCampaign": per}


def input_digest(root, dirs):
    rows = []
    for p in [root / "runtime-admission.json"] + [d / f for d in dirs for f in READ_FILES]:
        if p.is_file():
            rows.append("%s\t%d" % (p.relative_to(root).as_posix(), p.stat().st_size))
    rows.sort()
    return {"files": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}


# =========================================================================== output

def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _git_head():
    try:
        import subprocess
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                              text=True).stdout.strip() or "?"
    except OSError:
        return "?"


def generic_clock_statement(stamped, n):
    src = ", ".join("%s: %s" % (f, AVAIL_SOURCES.get(f) or DASH) for f in FAMILIES)
    return ("log lines carry a Docker receive stamp in %d of %d valid cells; availability per family (decision 43, "
            "measured receive stamps only): %s." % (stamped, n, src))


def dash_outputs(R):
    """v2.2: every output that is — for this system by construction (a field the cells do not carry), with the reason;
    per-episode `—` (no events, no delta, n < episodes) is reported where it occurs."""
    valid = [c for c in R["cells"] if c["valid"]]
    out = []
    for f in SENSOR_FAMILIES:
        if not any(collects(c, f) for c in valid):
            why = sorted({(c.get("familyAbsent") or {}).get(f) for c in valid if (c.get("familyAbsent") or {}).get(f)})
            out.append({"output": "family %s (primary and secondary columns, operating point, P4 candidates)" % f,
                        "reason": "; ".join(why) or "no valid cell retained the family's channel"})
    for f in FAMILIES:
        if AVAIL_SOURCES.get(f) is None and any(collects(c, f) for c in valid):
            out.append({"output": "availability-clock P4 verdict for family %s" % f,
                        "reason": "no measured collector receive stamp (AVAILABILITY_SOURCES, decision 43)"})
    if not any(v["trafficIndependent"] for v in P3_TI.values()):
        out.append({"output": "P3 (every fault)", "reason": "no family is traffic-independent by mechanism (H11)"})
    if SYSTEM == "teastore":
        known = set(HARNESS_PROVENANCE["teastore"]["knownCommits"])
        odd = sorted({c.get("harnessCommit") for c in valid if c.get("harnessCommit") not in known}, key=str)
        if odd:
            out.append({"output": "harness provenance of %d cell(s)" % sum(
                1 for c in valid if c.get("harnessCommit") not in known),
                        "reason": "receipt source.frameworkCommit %s is not listed in HARNESS_PROVENANCE (F5): read, "
                                  "flagged" % ", ".join("`%s`" % x for x in odd)})
    if SYSTEM != "hotel":
        out.append({"output": "Docker pause event as the onset interval's upper bound (H4)",
                    "reason": "the cells keep no Docker events: the interval is [command issued, command returned]"})
        out.append({"output": "v1 / v2 / v2.1 comparisons", "reason": "Hotel only (no earlier analysis of this system)"})
    small = sorted({(c["regime"], c["rate"]) for c in valid if c["target"] is not None})
    n_by = Counter((c["regime"], c["rate"]) for c in valid if c["target"] is not None)
    few = [k for k in small if n_by[k] < EPISODES]
    if few:
        out.append({"output": "P2 and P4 verdicts ('k of %d') at %s" % (EPISODES, ", ".join(
            "%s r%g (n = %d)" % (short(r), x, n_by[(r, x)]) for r, x in few)),
                    "reason": "fewer episodes than declared (EPISODES); P4's single-episode comparison is reported "
                              "where n = 1, descriptive"})
    return out


def clocks_report(cells):
    out = {}
    for c in cells:
        if not c["valid"]:
            continue
        out[c["cell"]] = {"offset": c["align"]["offset"], "alignmentResidual": c["align"]["residual"],
                          "pairs": c["align"]["pairs"], "ledgerMonoGranularity": c["ledgerStamps"]["monoGranularity"],
                          "ledgerWallGranularity": c["ledgerStamps"]["wallGranularity"],
                          "logReceiptBound": c["logReceipt"]["bound"],
                          "logLinesWithBothStamps": c["logReceipt"]["linesWithBoth"],
                          "logServicesWithoutAppStamp": c["logReceipt"]["servicesWithoutAppStamp"],
                          "dockerStampDigits": c["logReceipt"]["dockerDigits"], "wholeSecondLogs": c["wsLogs"],
                          "onset": c.get("onset")}
    keys = sorted({k for c in cells if c["valid"] for k in c.get("spanKeys", [])})
    stamped = sum(1 for v in out.values() if v["dockerStampDigits"] is not None)
    return {"perCell": out, "spanEventKeys": keys, "availabilitySources": AVAIL_SOURCES,
            "cellsWithDockerLogStamps": [stamped, len(out)], "spanReceiveStamp": None,
            "statement": generic_clock_statement(stamped, len(out)) if SYSTEM != "hotel" else
                         "log lines carry a Docker receive stamp in %d of %d valid cells; the harness samplers (M, S) "
                         "and the ledger client (E) stamp at collection; no span carries a receive stamp (the trace "
                         "files hold only a per-query collection time), so span availability is —." % (stamped, len(out))}


def episode_detail(eps):
    out = []
    for e in eps:
        c = e["_c"]
        d = {k: v for k, v in e.items() if k not in ("fires", "_c")}
        d["probeWindows"] = c["probeWindows"]
        d["readStats"] = c["readStats"]
        d["fires"] = [[f["family"], "%s:%s:%s" % (f["ch"], f["svc"], f["tok"]), f["rule"], f["ttd"], f["dir"],
                       f["own"], f["onPath"], f["counts"], f["bc"], f["movedBy"]]
                      for f in sorted(e["fires"], key=lambda f: f["ttd"])]
        out.append(d)
    return out


def _rk(d):
    return {"%g" % r: x for r, x in d.items()}


def build_json(R):
    with use_system(R.get("system", "hotel")):
        return _build_json(R)


def _build_json(R):
    res = R["results"]
    ops = {}
    for arm, op in R["ops"].items():
        al = op["allSensors"]
        ops[arm] = {
            "share": op["share"],
            "fitted": {g: {"K": v["K"], "atOperatingPoint": {rg: _rk(x) for rg, x in v["atOperatingPoint"].items()}}
                       for g, v in op["fitted"].items()},
            "table": {g: {rg: _rk(t) for rg, t in tt.items()} for g, tt in op["table"].items()},
            "allSensors": {"label": al["label"],
                           "fitted": {g: {"K": v["K"], "atOperatingPoint": _rk(v["atOperatingPoint"])}
                                      for g, v in al["fitted"].items()},
                           "table": {g: _rk(t) for g, t in al["table"].items()}},
            "heldOutScaleNotEstimable": _rk(op["heldOutScaleNotEstimable"])}
    out = {
        "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(), "label": LABEL, "binding": list(BINDING),
        "system": SYSTEM, "campaigns": R.get("campaigns"),
        "scope": "instance (one SUT, one host, %s)" % (
            "one campaign" if len(R.get("campaigns") or [None]) == 1 else "%d campaigns pooled" % len(R["campaigns"])),
        "dashOutputs": dash_outputs(R),
        "script": "research/detection-time/sweep_analysis_v2.py", "scriptSha256": _sha(__file__),
        "parametersSha256": _sha(PARAMETERS), "v1Sha256": _sha(HERE / "sweep_analysis.py"),
        "detectionTimeSha256": _sha(HERE / "detection_time.py"), "frameworkCommit": _git_head(),
        "python": platform.python_version(), "campaign": str(R["campaign"]),
        "parameters": {n: REGISTRY[n]["value"] for n in sorted(PARAMS_USED)},
        "cells": {"found": {v1.rr_key(*k): n for k, n in sorted(R["found"].items(), key=lambda kv: v1.rr_key(*kv[0]))},
                  "valid": {v1.rr_key(*k): n for k, n in sorted(R["valid"].items(), key=lambda kv: v1.rr_key(*kv[0]))},
                  "notScored": [{"cell": c["cell"], "regime": c["regime"], "rate": c["rate"], "reason": c["reason"]}
                                for c in R["cells"] if not c["valid"]]},
        "provenance": R["provenance"], "clocks": clocks_report(R["cells"]),
        "version": VERSION,
        "baseline": {"%g" % r: {"cells": f.cells, "levelSensors": len(f.level),
                                "levelSensorsWithMinPoints": sum(1 for v in f.level.values() if v[2] >= MIN_POOLED),
                                "scaleNotEstimable": [{"sensor": "%s:%s:%s" % k, "median": f.level[k][0],
                                                       "n": f.level[k][2]} for k in f.madZero],
                                "resolution": {"/".join(str(x) for x in k): v for k, v in sorted(f.res.items(), key=str)},
                                "resolutionNote": "ledger: float-difference granularity of (end - start) latencies, "
                                                  "not an instrument resolution (never binding)"}
                     for r, f in R["fits"].items()} if POOLED else None,
        "absentGap": absent_gap_report(R),
        "operatingPoint": ops,
        "kmaps": {s: {rg: _rk(km) for rg, km in kk.items()} for s, kk in R["kmaps"].items()},
        "settings": {s: {"primary": res[s]["primary"], "P4": res[s]["P4"]} for s in SETTINGS},
        "predictions": R["predictions"], "secondary": R["secondary"], "perSensor": R["perSensor"],
        "exposure": R["exposure"],
        "v1": ({"source": R["v1"]["source"], "P1": R["v1"]["predictions"]["P1"], "verdicts": R["v1"]["verdicts"],
                "p4PerRate": R["v1"]["p4PerRate"]} if R.get("v1") else None),
        "movedVerdicts": R["moved"], "episodes": episode_detail(res["primary"]["eps"]),
        "v2": ({"source": R["v2"]["source"], "scriptSha256": R["v2"]["scriptSha256"], "verdicts": R["v2"]["verdicts"]}
               if R.get("v2") else None),
        "movedVerdictsVsV2": R.get("movedVsV2"),
        "comparisons": R.get("vs") or {},
        "decision57": R.get("decision57"), "readerStats": reader_stats(R["cells"]),
    }
    return dt.strip(out)


def f2(x):
    return DASH if x is None else "%.2f" % x


def f3(x):
    return DASH if x is None else "%.3f" % x


def fsmall(x):
    return DASH if x is None else "%.2g" % x


def short(regime):
    return regime.replace("-effect", "")


def absent_gap_report(R):
    """Minor (review): the ledger's `absent` fires before a timeout only where its gap is shorter than the client
    timeout. Per rate: the gap (ABSENT_GAP_MULT x the largest pooled fault-free completion gap), the timeout, and, in
    the stopping-fault episodes, how often `absent` came before the first `failed` (K-independent rules, read from
    the reference setting, where every family has a K)."""
    out = {}
    if not POOLED:
        return out
    stopping = [g for g in FAULT_REGIMES if FAULT_TARGETS[g][1] in dt.STOPPING]
    eps = R["results"]["reference"]["eps"]
    for rate, f in sorted(R["fits"].items(), reverse=True):
        cells = [c for c in R["cells"] if c["valid"] and c["rate"] == rate]
        T = sorted({float(c["timing"]["requestTimeoutSeconds"]) for c in cells
                    if c["timing"].get("requestTimeoutSeconds") is not None})
        gaps = {route: f.gap(("ledger", ENTRY, route + COMPLETIONS))
                for route in sorted({r.route for c in cells for r in c["ledger"]})}
        pe = [e for e in eps if e["regime"] in stopping and e["rate"] == rate]
        before = 0
        for e in pe:
            ab = [x["ttd"] for x in e["fires"] if x["family"] == "E" and x["rule"] == "absent"]
            fa = [x["ttd"] for x in e["fires"] if x["family"] == "E" and x["rule"] == "failed"]
            before += bool(ab) and (not fa or min(ab) < min(fa))
        out["%g" % rate] = {"gapSeconds": gaps, "timeoutSeconds": T,
                            "gapBelowTimeout": {rt: (None if (g is None or len(T) != 1) else g < T[0])
                                                for rt, g in gaps.items()},
                            "stoppingEpisodesAbsentBeforeFirstFailed": [before, len(pe)]}
    return out


def render_absent_gap(J):
    parts = []
    for r, x in J["absentGap"].items():
        T = x["timeoutSeconds"]
        for rt, g in x["gapSeconds"].items():
            below = x["gapBelowTimeout"][rt]
            parts.append("r%s %s: gap %s s %s timeout %s s%s; `absent` before the first `failed` in %d/%d pause episodes" % (
                r, rt, f3(g), {True: "<", False: ">=", None: "vs"}[below], "/".join("%g" % t for t in T) or DASH,
                {True: " (can fire before a timeout)", False: " (cannot fire before a timeout)", None: ""}[below],
                *x["stoppingEpisodesAbsentBeforeFirstFailed"]))
    return "; ".join(parts) or DASH


def fmt_k(k):
    return "%g" % k if k is not None else DASH


def op_cell(t, K, at):
    """One operating-point table cell: min K (cert / point) · alarms at the fitted K · /h [bound] · at K = K_REF."""
    if not t:
        return DASH
    x = next((y for y in t["perK"] if y["K"] == K), None) if (K is not None and at) else None
    ref = next(y for y in t["perK"] if y["K"] == K_REF)
    return "%s / %s · %s · %s [%s] · %d (%.1f/h)" % (
        fmt_k(t["minKCertified"]), fmt_k(t["minKPoint"]), x["alarms"] if x else DASH, f2(x["perHour"]) if x else DASH,
        f2(x["upperPerHour"]) if x else DASH, ref["alarms"], ref["perHour"])


def render_folds(w, scope, regime, r, v):
    pdiff = v["pairedDifferences"]
    w("- %s %s r%g (candidates %d; families not at the operating point: %s; paired differences ledger - "
      "sensor: mean %s [%s, %s] s; availability-clock wins %d of %d evaluable):" % (
          scope, short(regime), r, v["candidates"], ", ".join(v["familiesNotAtOperatingPoint"]) or "none",
          f3(pdiff["mean"]), f3(pdiff["min"]), f3(pdiff["max"]), v["winsAvailability"], v["availabilityEvaluable"]))
    for fo in v["folds"]:
        w("  - ep%d b%s: %s `%s` %s vs E `%s` %s; lead %s, margin %s (avail. %s); tied %d (win share %s); "
          "**%s**%s" % (
              fo["heldOut"] + 1, fo["block"], fo["sensor"] or DASH, fo["sensorRule"] or DASH,
              f3(fo["sensorTtd"]), fo["ledgerRule"] or DASH, f3(fo["ledgerTtd"]), f3(fo["lead"]),
              fsmall(fo["margin"]), fsmall(fo["marginAvailability"]), len(fo.get("tied") or []),
              "%d/%d" % tuple(fo["tiedWinShare"]) if fo.get("tiedWinShare") else DASH, fo["category"],
              (" (same silence: the ledger's `absent` is ended by this request, decision 51)" if fo.get("sameSilence")
               else "") + (" (the sensor's `absent` is ended by the ledger's catching request, decision 57)"
                           if fo.get("sensorSilence") else "")
              + (" (the two silences start with the same request, decision 58)" if fo.get("silenceStartSame") else "")
              + (" (%s)" % "; ".join(fo["unclassifiableBy"]) if fo.get("unclassifiableBy") else "")
              + (" [lead = %s start + %s gap + %s]" % (fsmall(fo["decomposition"]["startDifference"]),
                                                      fsmall(fo["decomposition"]["gapDifference"]),
                                                      fsmall(fo["decomposition"]["residual"]))
                 if fo.get("decomposition") else "")))


READER_STATS = ("bridgeMappings", "bridgeTokensWithSeveralTraces", "bridgeTracesWithSeveralTokens", "bridgeRowsDropped",
                "tracesWithoutToken",
                "probeTracesExcluded", "probeSpansExcluded", "spansIncomplete", "spansUnusable", "duplicateSpans",
                "journeysWithoutStart", "samplePairsSkipped", "logRecordsUntimed", "composeCliLines")


def reader_stats(cells):
    """F11: the readers' counts over the valid cells (drops are counted, never silent)."""
    tot = Counter()
    for c in cells:
        if c["valid"]:
            tot.update({k: v for k, v in (c.get("readStats") or {}).items() if isinstance(v, int)})
    return dict(tot)


def render_reader_stats(w, R):
    st = reader_stats(R["cells"])
    if SYSTEM == "hotel":
        return
    w("")
    w("Reader statistics over the valid cells (F11; a drop is counted, never silent): %s." % (
        "; ".join("%s %d" % (k, st.get(k, 0)) for k in READER_STATS)))


def render_comparison(w, label, cmp_):
    w("## Moved verdicts (%s -> v%s primary)" % (label, VERSION))
    w("")
    if cmp_ is None:
        w("Not computed (no %s readout given)." % label)
        w("")
        return
    if cmp_["moved"]:
        w("| verdict | %s | v%s | which rule moved it |" % (label, VERSION))
        w("|---|---|---|---|")
        for m in cmp_["moved"]:
            w("| %s | %s | %s | %s |" % (m["verdict"], _verdict_text(m["old"]), _verdict_text(m["new"]),
                                         m["reason"].replace("|", "/")))
    else:
        w("No verdict moved.")
    w("")
    fc = cmp_["folds"]
    prim = [x for x in fc if x["setting"] == "primary" and x["view"] in ("P4a", "P4b")]
    w("P4 folds whose selected sensor or category changed from %s, also where the verdict did not move (F12): %d in "
      "the primary no-BC view; **%d across all settings and BC views** (%s); by rule: %s; not explained by a rule "
      "expected for this comparison (%s): **%d**." % (
          label, len(prim), len(fc), ", ".join("%s %d" % kv for kv in sorted(cmp_["foldsBySettingView"].items()))
          or DASH, "; ".join("%s %d" % kv for kv in sorted(cmp_["foldsByRule"].items())) or DASH,
          ", ".join(cmp_["allowedRules"]), cmp_["unexplained"]))
    for x in prim:
        w("- %s %s r%s b%s: `%s` %s %s -> `%s` %s %s (%s)" % (
            x["view"], short(x["regime"]), x["rate"], x["block"], x["old"][0] or DASH, x["old"][1] or DASH,
            x["old"][2] or DASH, x["new"][0] or DASH, x["new"][1] or DASH, x["new"][2], "; ".join(x["rules"])))
    w("")


def render_moved(w, R):
    """Hotel: the moved-verdict tables against v2.3, v2.2, v2.1, v2-fix1 and v1."""
    for label in COMPARISONS:
        render_comparison(w, label, (R.get("vs") or {}).get(label))
    w("## Moved verdicts (v2-fix1 -> v%s primary)" % VERSION)
    w("")
    if R.get("movedVsV2") is None:
        w("Not computed (no v2 readout given).")
    elif R["movedVsV2"]:
        w("| verdict | v2-fix1 | v%s | which rule moved it |" % VERSION)
        w("|---|---|---|---|")
        for m in R["movedVsV2"]:
            w("| %s | %s | %s | %s |" % (m["verdict"], _verdict_text(m["v2fix1"]), _verdict_text(m["v22"]),
                                         m["reason"].replace("|", "/")))
    else:
        w("No verdict moved.")
    w("")
    w("## Moved verdicts (v1 reference -> v%s primary)" % VERSION)
    w("")
    if R.get("v1") is None:
        w("Not computed (v1 not run).")
    elif R["moved"]:
        w("| verdict | v1 | v%s | which rule moved it |" % VERSION)
        w("|---|---|---|---|")
        for m in R["moved"]:
            w("| %s | %s | %s | %s |" % (m["verdict"], m["v1"], m["v2"], m["reason"].replace("|", "/")))
    else:
        w("No verdict moved.")
    w("")


def render_decision57(w, R):
    d = R.get("decision57") or {"rows": [], "totals": {}}
    t = d["totals"]
    w("## Decision 57, 58 and 60: a sensor's `absent` and the requests that start and end its silence (P4, primary)")
    w("")
    w("A sensor's `absent` carries the token of the observation that ends its silence (decision 57) and of the one that "
      "starts it (decision 58; own token, else the trace's entry-root token). A pair with the ledger's catch is "
      "same-request when the ending observation is the ledger's catching request (57) or, for an `absent`-vs-`absent` "
      "pair, when the silence-starting records are one request (58); with a token missing it is unclassifiable (no win). "
      "An `absent`-vs-`absent` pair of different requests wins only if its start term exceeds the margin; the gap term "
      "never counts (60). Folds whose selected sensor caught by `absent`: %d; same-request by the ending observation "
      "(57): %d; `absent`-vs-`absent` pairs: %d, same-request by the starting records (58): %d (of them by the start "
      "only: %d); start term within the margin (60): %d; **unclassifiable pairs: %d** (decisive for the category: %d)." % (
          t.get("foldsSensorAbsent", 0), t.get("sameRequest", 0), t.get("absentAbsent", 0), t.get("sameByStart", 0),
          t.get("sameByStartOnly", 0), t.get("startTermTie", 0), t.get("withoutToken", 0),
          t.get("unclassifiableDecisive", 0)))
    if d["rows"]:
        w("")
        w("| scope | class | rate | folds with sensor `absent` | same request (57) | absent/absent | same request "
          "(58, start only) | start term within the margin (60) | unclassifiable (decisive) | token source (end; start) |")
        w("|---|---|---|---|---|---|---|---|---|---|")
        for x in d["rows"]:
            w("| %s | %s | %s | %d | %d | %d | %d (%d) | %d | %d (%d) | %s; %s |" % (
                x["scope"], short(x["regime"]), x["rate"], x["foldsSensorAbsent"], x["sameRequest"],
                x["absentAbsent"], x["sameByStart"], x["sameByStartOnly"], x["startTermTie"], x["withoutToken"],
                x["unclassifiableDecisive"], ", ".join("%s %d" % kv for kv in sorted(x["tokenSources"].items())),
                ", ".join("%s %d" % kv for kv in sorted(x["startTokenSources"].items())) or DASH))
        dec = [(x, y) for x in d["rows"] for y in x["decompositions"]]
        if dec:
            w("")
            w("Each `absent`-vs-`absent` lead, decomposed (decision 58): lead = start term (ledger's last completion - "
              "sensor's last observation before the silence, each from the onset in its own clock) + gap term "
              "(g_ledger - g_sensor) + residual (clipping at the onset, a whole-second log stamp, a catch moved out of "
              "a probe window). Decision 60: only the start term can make a win:")
            w("")
            for x, y in dec:
                w("- %s %s r%s b%s: lead %s s = %s + %s + %s (g_ledger %s, g_sensor %s); %s" % (
                    x["scope"], short(x["regime"]), x["rate"], y["block"], fsmall(y["lead"]),
                    fsmall(y["startDifference"]), fsmall(y["gapDifference"]), fsmall(y["residual"]),
                    fsmall(y["ledgerGap"]), fsmall(y["sensorGap"]), y["category"]))
    w("")


def render_single(w, se):
    """P4 with one episode (descriptive): the ledger's catch and every candidate's, fastest first."""
    if not se:
        return
    w("  - single episode b%s (descriptive): E `%s` %s; %d of %d candidate sensors lower than the ledger; H3 "
      "categories: %s" % (se["block"], se["ledgerRule"] or DASH, f3(se["ledgerTtd"]), se["lowerThanLedger"],
                          len(se["sensors"]), ", ".join("%s %d" % kv for kv in sorted(se["categories"].items())) or DASH))
    for x in se["sensors"][:REPORT_TOP]:
        w("    - `%s` `%s` %s (lead %s): %s" % (x["sensor"], x["rule"], f3(x["ttd"]), f3(x["lead"]), x["category"]))
    if len(se["sensors"]) > REPORT_TOP:
        w("    - (+%d more in the JSON)" % (len(se["sensors"]) - REPORT_TOP))


def render(R, J):
    with use_system(R.get("system", "hotel")):
        return _render(R, J)


def _render(R, J):
    L = []
    w = L.append
    pred = R["predictions"]
    camp = R["campaign"] if isinstance(R["campaign"], list) else [R["campaign"]]
    w("# Traffic sweep, %s: analysis v%s, %s (%s)" % (TITLE, VERSION, LABEL, " + ".join(Path(str(x)).name for x in camp)))
    w("")
    if SYSTEM != "hotel":
        w("**%s.** v2.4 (decisions 57, 58 and 60) and this system's reader were written from the harness code that writes the "
          "cells (%s) and tested on synthetic cells only; no %s cell was read before the freeze. **Scope: instance** "
          "(one SUT, one host; %d campaign(s) pooled). `—` = absent or not evaluable, never 0; every output that is `—` "
          "by construction is listed under \"Outputs that are — by construction\"." % (
              LABEL[0].upper() + LABEL[1:], param("SYSTEM_" + SYSTEM.upper())["harnessCommit"], TITLE, len(camp)))
    else:
      w("**%s.** v1's readout (e31e316), v2's readout (8cdad26), v2.1's readout (ee983bb), v2.2's readout (bc8e738), "
      "v2.3's readout (037e84e) and the reviews of v1, v2, v2.2 and v2.3 were read "
      "before v2.4 was written; v2.1's rules are protocol round 11 (decisions 51-55) and the v2 review's minors, v2.2's "
      "is decision 57 (round 12), v2.3's are decision 58 (round 13) and the v2.2 review's fixes, v2.4's is decision 60 "
      "(round 14) with the v2.3 review's minors, not the verdicts they move. **Scope: instance** (one SUT, one host, "
      "one campaign). `—` = absent or not evaluable, never 0. v2.1 (22e0d12) stays the record of the Hotel "
      "re-analysis; **v2.4 is the version to be frozen for TeaStore and OTel** before any of their cells is read "
      "(decision 60)." % (LABEL[0].upper() + LABEL[1:]))
    w("")
    w("Binding documents and inputs: " + "; ".join(BINDING) + ".")
    w("")
    w("Analysis: `%s` v%s (sha256 `%s`), parameters.json sha256 `%s`, on v1 `sweep_analysis.py` (sha256 `%s`) and "
      "`detection_time.py` (sha256 `%s`), HEAD `%s`, Python %s. v1 verdicts: %s. v2 verdicts: %s. v2.1 verdicts: %s. "
      "v2.2 verdicts: %s. v2.3 verdicts: %s." % (
          J["script"], VERSION, J["scriptSha256"], J["parametersSha256"], J["v1Sha256"],
          J["detectionTimeSha256"], J["frameworkCommit"], J["python"], R["v1"]["source"] if R.get("v1") else DASH,
          R["v2"]["source"] if R.get("v2") else DASH,
          *[((R.get("vs") or {}).get(k) or {}).get("source") or DASH for k in ("v2.1", "v2.2", "v2.3")]))
    w("")
    w("## Outputs that are — by construction")
    w("")
    for x in J["dashOutputs"]:
        w("- %s: %s." % (x["output"], x["reason"]))
    if not J["dashOutputs"]:
        w("- none")
    w("")
    w("## What was read")
    w("")
    w("| class | " + " | ".join("r%g valid/found" % r for r in RATES) + " |")
    w("|---|" + "---|" * len(RATES))
    for regime in (NOFAULT,) + FAULT_REGIMES:
        w("| %s | %s |" % (short(regime), " | ".join(
            ("%d/%d" % (R["valid"][(regime, r)], R["found"][(regime, r)])) if R["found"][(regime, r)] else DASH
            for r in RATES)))
    inv = J["cells"]["notScored"]
    w("")
    w("Cells not scored: %s." % ("; ".join("`%s` (%s)" % (x["cell"], x["reason"]) for x in inv) if inv else "none"))
    pv = R["provenance"]
    w("")
    w("Provenance: harness commit %s; plan sha256 %s; input digest `%s` over %d files%s." % (
        "`%s`" % pv["harnessCommit"] if pv["harnessCommit"] else DASH,
        ", ".join("`%s`" % x for x in pv["planSha256"]) or DASH, pv["input"]["sha256"], pv["input"]["files"],
        (" (v1's file set: `%s`, %d files)" % (pv["inputV1Files"]["sha256"], pv["inputV1Files"]["files"]))
        if pv.get("inputV1Files") else ""))
    if SYSTEM != "hotel":                           # F5: what the registry knows about the producing harness
        hp = HARNESS_PROVENANCE[SYSTEM]
        w("")
        w("Harness provenance (registry HARNESS_PROVENANCE, F5): reader built from `%s`; sweep cells produced by %s; "
          "quiet cells produced by %s; files read: %s; the cells' own commit: %s." % (
              hp["readerBuiltFrom"], hp["sweepCellsProducedBy"], hp["quietCellsProducedBy"], hp["filesReadUnchanged"],
              hp["cellsCarryCommit"]))
    render_reader_stats(w, R)
    w("")
    if SYSTEM == "hotel":
        render_moved(w, R)
    render_decision57(w, R)
    w("## Clocks and timing uncertainty (H3 b, H8)")
    w("")
    ck = J["clocks"]["perCell"]
    res_ = [v["alignmentResidual"] for v in ck.values()]
    rb = [v["logReceiptBound"] for v in ck.values() if v["logReceiptBound"] is not None]
    w("- Clock alignment, per cell wall = monotonic + offset over the ledger's paired stamps: residual median %s s, "
      "max %s s over %d cells." % (fsmall(statistics.median(res_)) if res_ else DASH,
                                   fsmall(max(res_)) if res_ else DASH, len(res_)))
    w("- Log receipt-delay bound per cell (max Docker stamp - app second): median %s s, range %s-%s s over %d cells; "
      "services with no app stamp: %s." % (f3(statistics.median(rb)) if rb else DASH, f3(min(rb)) if rb else DASH,
                                           f3(max(rb)) if rb else DASH, len(rb),
                                           ", ".join(sorted({s for v in ck.values() for s in v["logServicesWithoutAppStamp"]}))
                                           or "none"))
    w("- Availability (H8, decision 43): %s Span event keys read: %s." % (
        J["clocks"]["statement"], ", ".join("`%s`" % k for k in J["clocks"]["spanEventKeys"]) or DASH))
    w("- The ledger's `absent` gap against the client timeout, per rate (it fires before a timeout only where the gap is "
      "shorter): %s." % render_absent_gap(J))
    w("")
    w("## Scale not estimable (M2, decision 52): fault-free MAD = 0 at the baseline")
    w("")
    w("These sensors' level rules (spike, run3, median) are `—`: no catch, no false alarm; `appear` and `absent` are "
      "kept. Pooled per rate (the scoring baseline):")
    w("")
    for r, b in (J["baseline"] or {}).items():
        sn = b["scaleNotEstimable"]
        w("- r%s: %d of %d sensors with >= %d points%s" % (
            r, len(sn), b["levelSensorsWithMinPoints"], MIN_POOLED,
            (": " + ", ".join("`%s` (median %s, n %d)" % (x["sensor"], fsmall(x["median"]), x["n"]) for x in sn))
            if sn else ""))
    ho = {r: set(v) - {x["sensor"] for x in (J["baseline"] or {}).get(r, {}).get("scaleNotEstimable", [])}
          for r, v in J["operatingPoint"]["primary"]["heldOutScaleNotEstimable"].items()}
    w("- In a leave-one-cell-out fit only (the operating point), additionally: %s." % (
        "; ".join("r%s: %s" % (r, ", ".join("`%s`" % x for x in sorted(v))) for r, v in ho.items() if v) or "none"))
    w("- Resolution of ledger latency: a float-difference granularity of (end - start), not an instrument resolution "
      "(RESOLUTION_RULE; never binding).")
    w("")
    w("## Operating point (H2, H7; M3, M4): held-out false alarms per hour on the scored sensor set")
    w("")
    w("Target %g/h, met when the exact one-sided %g upper bound is <= the target (`FAR_MEETS_CRITERION` = %s). The "
      "scored set of a class is the detector its episodes are scored with: the spike path filter and the by-construction "
      "flags (no-BC view, as P4) applied exactly as in scoring, the detector restarted after each counted alarm "
      "(CALIBRATION_SET_RULE, decision 55). K per channel family within the system (`K_FIT_UNIT` = %s, decision 53): "
      "one K per family, the smallest grid K that meets the target at every (class, rate) where some grid K does; the "
      "per-system K (L, M, S, T together) is the `system` row. Quiet time per rate: the valid no-fault cells, each "
      "scored leave-one-cell-out. Cell: min K (cert / point) · alarms at the fitted K · /h [bound] · at K = %g." % (
          FAR_TARGET, FAR_CONF, FAR_MEETS, K_FIT_UNIT, K_REF))
    w("")
    for arm, op in R["ops"].items():
        w("**Floor %s (share %g of the baseline median)**: K per family %s; per-system K %s." % (
            arm, op["share"], ", ".join("%s %s" % (g, fmt_k(op["fitted"][g]["K"])) for g in FAMILIES),
            fmt_k(op["fitted"]["system"]["K"])))
        w("")
        w("| class | family | " + " | ".join("r%g" % r for r in RATES) + " |")
        w("|---|---|" + "---|" * len(RATES))
        for regime in FAULT_REGIMES:
            for g in list(FAMILIES) + ["system"]:
                K = op["fitted"][g]["K"]
                at = op["fitted"][g]["atOperatingPoint"][regime]
                if op["fitted"][g].get("notCollected"):
                    w("| %s | %s | %s |" % (short(regime), g, " | ".join([DASH + " (not collected)"] * len(RATES))))
                    continue
                w("| %s | %s | %s |" % (short(regime), g, " | ".join(
                    op_cell(op["table"][g][regime].get(r), K, at.get(r)) for r in RATES)))
        w("")
        al = op["allSensors"]
        w("*%s*, beside it (counted as v2 did; M2 applies): K %s; per-system K %s." % (
            al["label"][0].upper() + al["label"][1:],
            ", ".join("%s %s" % (g, fmt_k(al["fitted"][g]["K"])) for g in FAMILIES), fmt_k(al["fitted"]["system"]["K"])))
        w("")
        w("| family (all sensors) | " + " | ".join("r%g" % r for r in RATES) + " |")
        w("|---|" + "---|" * len(RATES))
        for g in list(FAMILIES) + ["system"]:
            K = al["fitted"][g]["K"]
            if al["fitted"][g].get("notCollected"):
                w("| %s | %s |" % (g, " | ".join([DASH + " (not collected)"] * len(RATES))))
                continue
            w("| %s | %s |" % (g, " | ".join(op_cell(al["table"][g].get(r), K, al["fitted"][g]["atOperatingPoint"].get(r))
                                             for r in RATES)))
        w("")
        w("Alarms left at the largest grid K (K = %g) on the scored set, by sensor and rule:" % K_GRID[-1])
        w("")
        n_left = len(L)
        for regime in FAULT_REGIMES:
            for g in SENSOR_FAMILIES:
                for r in RATES:
                    t = op["table"][g][regime].get(r)
                    if t and t["atLargestK"]:
                        top = sorted(t["atLargestK"].items(), key=lambda kv: (-kv[1], kv[0]))
                        w("- %s %s r%g: %s%s" % (short(regime), g, r, ", ".join("`%s` %d" % kv for kv in top[:REPORT_TOP]),
                                                 " (+%d more)" % (len(top) - REPORT_TOP) if len(top) > REPORT_TOP else ""))
        for r in RATES:
            t = op["table"]["E"][FAULT_REGIMES[0]].get(r)
            if t and t["atLargestK"]:
                top = sorted(t["atLargestK"].items(), key=lambda kv: (-kv[1], kv[0]))
                w("- every class E r%g: %s" % (r, ", ".join("`%s` %d" % kv for kv in top[:REPORT_TOP])))
        if len(L) == n_left:
            w("- none")
        w("")
    w("## Predictions (primary: K per family on the scored set, floor primary)")
    w("")
    if R.get("v1"):
        v1p1 = R["v1"]["predictions"]["P1"]
        w("- **P1 under v1's definition** (point, schedule wait + timeout +- 0.5 s, observed E): %d/%d, verdict %s." % (
            v1p1["k"], v1p1["n"], {True: "holds", False: "fails", None: DASH}[v1p1["holds"]]))
    p1 = pred["P1"]
    w("- **P1 under v%s's definition** (%s; H4 interval, ambiguity window [onset command, %s + delta] and "
      "tolerance as decided in decision 54, observed = first `failed` catch%s): %d/%d; per rate %s; not evaluable %d; "
      "holds by branch: %s; verdict **%s**." % (
          VERSION, short(pause_regime()),
          "Docker pause event" if SYSTEM == "hotel" else "command returned (no Docker events)",
          "; or an error answer before the timeout, the declared alternative" if P1_ERROR_ANSWER.get(SYSTEM) else "",
          p1["k"], p1["n"], ", ".join("r%s %d/%d" % (r, a, b) if b else "r%s %s" % (r, DASH)
                                      for r, (a, b) in p1["perRate"].items()),
          p1["notEvaluable"], ", ".join("%s %d" % kv for kv in sorted(p1.get("holdsByBranch", {}).items())) or DASH,
          {True: "holds", False: "fails", None: DASH}[p1["holds"]]))
    for r, v in pred["P2"].items():
        w("- **P2** r%s (failed before the first `failed` catch <= %.2f): %s." % (
            r, p2_threshold(float(r)), DASH if v is None else "%d/%d, counts %s, verdict %s" % (
                v["k"], v["n"], v["perEpisode"], {True: "holds", False: "fails", None: DASH + " (n < %d)" % EPISODES}[
                    v["holds"]])))
    for x in pred["P3"]:
        w("- **P3** %s: **%s**%s." % (short(x["regime"]), x["state"], (" (%s)" % x["reason"]) if x.get("reason") else ""))
    for scope in ("P4a", "P4b"):
        label = "outside the target, without BC" if scope == "P4a" else "the target's own sensors, without BC"
        for regime, x in pred["P4"][scope].items():
            parts = []
            for r in RATES:
                v = x["perRate"]["%g" % r]
                if v is None:
                    parts.append("r%g %s" % (r, DASH))
                elif v.get("singleEpisode") is not None:
                    parts.append("r%g %s (n = %d, single episode, descriptive)" % (r, DASH, v["n"]))
                elif v.get("note"):
                    parts.append("r%g %s (%s)" % (r, DASH, ", ".join(v.get("familiesNotAtOperatingPoint") or ["E"])
                                                 + " not at the operating point"))
                else:
                    parts.append("r%g %d/%d (ledger missed, sensor caught: %d)" % (
                        r, v["wins"], v["n"], v["ledgerMissedSensorCaught"]))
            w("- **%s** %s (%s; wins under H3 a-c, >= %d of %d, descriptive): %s; highest rate **%s**." % (
                scope, short(regime), label, P4_MIN, EPISODES, ", ".join(parts), x["highestRate"]))
    w("")
    w("### P4 folds (sensor rule vs ledger rule; lead, margin; category)")
    w("")
    dashed = []
    for scope in ("P4a", "P4b"):
        for regime, x in pred["P4"][scope].items():
            for r in RATES:
                v = x["perRate"]["%g" % r]
                if not v:
                    continue
                if v.get("note"):
                    w("- %s %s r%g: %s" % (scope, short(regime), r, v["note"]))
                    render_single(w, v.get("singleEpisode"))
                    dashed.append((scope, regime, r))
                    continue
                render_folds(w, scope, regime, r, v)
    w("")
    if dashed:
        w("### P4 folds under the reference K = %g where the primary is `—` (descriptive, not an operating point)" % K_REF)
        w("")
        for scope, regime, r in dashed:
            v = R["results"]["reference"]["P4"][scope][regime]["perRate"]["%g" % r]
            if v and not v.get("note"):
                render_folds(w, scope, regime, r, v)
        w("")
    w("**Beside the primary** (highest rate where P4 holds): floor arm (refitted K), K = %g reference (not an operating "
      "point), and the per-system K (decision 53's `beside`):" % K_REF)
    w("")
    w("| verdict | primary | floor arm (refitted K) | reference K = %g | per-system K |" % K_REF)
    w("|---|---|---|---|---|")
    for scope in ("P4a", "P4b", "P4a withBC", "P4b withBC"):
        for regime in FAULT_REGIMES:
            w("| %s %s | %s | %s | %s | %s |" % (scope, short(regime), *[
                R["results"][s]["P4"][scope][regime]["highestRate"] for s in SETTINGS]))
    w("")
    w("## Primary outcome: time to detection at the operating point, misses charged at the hold end")
    w("")
    w("Detected k/n · median [min-max] · **mean over all n** (with BC catches), then without BC; FA = held-out false "
      "alarms on the class's scored set at the family's K: alarms (/h, [bound]). `—` = channel missing or family not "
      "at the operating point for this class at this rate.")
    w("")
    cols = [c for c in COLUMNS if c != "E:own"]
    w("| class | rate | n | " + " | ".join("%s | %s no BC" % (c, c) for c in cols) + " | " +
      " | ".join("FA %s" % f for f in FAMILIES) + " |")
    w("|---|---|---|" + "---|---|" * len(cols) + "---|" * len(FAMILIES))
    for row in R["results"]["primary"]["primary"]:
        cells_ = []
        for c in cols:
            v = row["columns"].get(c)
            cells_ += [v1.fcol(v, "bc"), v1.fcol(v, "noBC") if c != "E" else "(= E)"]
        fa = []
        for f in FAMILIES:
            v = row["columns"].get(f)
            x = (v or {}).get("falseAlarms")
            fa.append(DASH if not x else "%d (%.1f [%.1f])" % (x["alarms"], x["perHour"], x["upperPerHour"]))
        w("| %s | %g | %d | %s | %s |" % (short(row["regime"]), row["rate"], row["n"], " | ".join(cells_), " | ".join(fa)))
    w("")
    w("## Secondary: failed requests scheduled before the first catch, with their H4 class")
    w("")
    w("Cell: failed requests per episode, median [min-max] (detected/n) · H4 class totals over the episodes "
      "straddling / after the onset interval (before: none can be, they are scheduled after the onset).")
    w("")
    w("| class | rate | n | " + " | ".join(cols) + " |")
    w("|---|---|---|" + "---|" * len(cols))
    for row in R["secondary"]:
        cells_ = []
        for c in cols:
            v = row["columns"].get(c)
            if v is None:
                cells_.append(DASH)
                continue
            h = v.get("byH4Class")
            cells_.append("%s (%d/%d) · %s" % (dt.fmt_t(v["failedBefore"]).replace(".00", ""), v["detected"], v["n"],
                                               "%d/%d" % (h["straddling"], h["after"]) + (
                                                   " (+%d before)" % h["before"] if h["before"] else "")
                                               if h else DASH))
        w("| %s | %g | %d | %s |" % (short(row["regime"]), row["rate"], row["n"], " | ".join(cells_)))
    w("")
    w("## P1 detail (H4, M5)")
    w("")
    for x in p1["perEpisode"]:
        tp = x.get("toleranceParts") or {}
        w("- r%g b%s: interval %s s (%s); delta %s s (from %s requests); ambiguity window [0, %s] s with %s requests "
          "completing in it; expected [%s, %s] +- %s s (%s); observed %s; classes %s; max dispatch lag %s s%s" % (
              x["rate"], x["block"], f3(x["intervalSeconds"]), x["hiSource"], fsmall(x.get("delta")),
              x.get("deltaRequests", DASH), f3((x.get("ambiguityWindow") or [None, None])[1]),
              x.get("ambiguous", DASH), f3((x["expected"] or [None, None])[0]),
              f3((x["expected"] or [None, None])[1]), f3(x["tolerance"]),
              ", ".join("%s %s" % (k, fsmall(v)) for k, v in tp.items()) or DASH, f3(x["observed"]),
              x.get("requestClasses") or DASH, f3(x.get("dispatchLagMax")),
              (" — (%s)" % x["deltaNote"]) if x.get("deltaNote") else
              (" holds via **%s**%s" % (x.get("branch"), (" (first failed: %s)" % json.dumps(
                  x["firstFailedAnswer"], sort_keys=True)) if x.get("firstFailedAnswer") else "")
               if x["ok"] else (" ✗" if x["ok"] is False else " —"))))
    w("")
    w("## Exposure (H5): recorded, the objective unchanged")
    w("")
    ex = R["exposure"]
    w("Route call path (projected from the no-fault traces, plus data stores by depends_on): %s. Trace edges: %s. "
      "Episodes with no request started in the fault window: %d of %d. Never-exposed sensors: %d, on services %s; a "
      "miss of such a sensor reads \"not exposed in this run\", never \"cannot detect\"." % (
          ", ".join(ex["routePath"]), ", ".join(ex["projection"]["traceEdges"]) or DASH,
          sum(1 for v in ex["episodes"].values() if v["requestsStartedInWindow"] == 0), len(ex["episodes"]),
          len(ex["neverExposedSensors"]), ", ".join(ex["neverExposedServices"]) or "none"))
    w("")
    w("## Defaults and declared limits")
    w("")
    for line in DEFAULTS:
        w("- " + line)
    for k, v in sorted(KNOWN_LIMITATIONS.items(), key=lambda kv: (kv[0][0], int(kv[0][1:]))):
        w("- Known limitation %s (%s review, registry KNOWN_LIMITATIONS): %s" % (k, "v2.3" if k[0] == "G" else "v2.2", v))
    w("- v2.3 fixes from the v2.2 review (registry V23_FIXES): %s." % "; ".join(
        "%s: %s" % kv for kv in V23_FIXES.items()))
    w("- v2.4 fixes from the v2.3 review (registry V24_FIXES): %s." % "; ".join(
        "%s: %s" % kv for kv in V24_FIXES.items()))
    w("- P1 (v%s): observed = the ledger's first `failed` catch, the rule the timeout model predicts. E also has "
      "`absent` (H3 e); it can fire before a timeout only where its gap is shorter than the timeout: %s. P2 uses the "
      "same `failed` catch, as v1." % (VERSION, render_absent_gap(J)))
    w("")
    return "\n".join(L)


DEFAULTS = [
    "Every tunable value is in research/protocol/parameters.json; the rule texts there (RESOLUTION_RULE, MARGIN_RULE, "
    "LOG_RECEIPT_RULE, P1_TOLERANCE_RULE, P1_AMBIGUITY_WINDOW_RULE, LEDGER_ABSENT_TOKEN_RULE, SCALE_NOT_ESTIMABLE_RULE, "
    "CALIBRATION_SET_RULE, P4_NOT_EVALUABLE_RULE, EXPOSURE_RULE) are what this script implements.",
    "Baseline (H1): per rate, every valid cell's fault-free time (no-fault cells whole, fault cells before "
    "startedMonotonic), scope probe rule, unscreened; n >= MIN_BASELINE_POOLED or —; MAD = 0 -> scale not estimable "
    "(M2), level rules —. Episodes at one rate share it (it is the other cells plus the episode's own pre-onset).",
    "Operating point (H2/H7, M3): no-fault cells only (decision 33; the quiet time per rate is in the table above, "
    "every campaign given pooled, H1); pre-onset time of fault cells is "
    "not added to the held-out quiet time. The calibrated detector of a class is its scored set: the family's no-BC "
    "column detector (own and outside sensors together, the path filter and BC flags as in scoring); P4a/P4b select "
    "single sensors from it, whose false-alarm count is at most the family's (engineering default, recorded). The "
    "with-BC column uses the same K. The ledger E keeps its BC catches (as in scoring) and is the same for every class.",
    "K (decision 53): one K per channel family within the system, over every (class, rate) where some grid K meets the "
    "target; where none does, the family is `—` there. The K grid is not extended after the fact (decision 55).",
    "Clock mapping: every monotonic <-> wall conversion uses the per-cell offset fitted on the ledger's own stamps "
    "(v1 used the barrier pair).",
    "M1 (decision 51) ties the ledger's `absent` to the completion that ends its silence; decision 57 ties a sensor's "
    "`absent` to the observation that ends its silence (its own token, else its trace's entry-root token); with "
    "neither, the pair is unclassifiable (no win) and counted.",
    "P4 in the availability clock is a sensitivity row (decision 43): spans have no receive stamp, so their "
    "availability verdict is —.",
    "Probe and caller-span variants are not recomputed: v2.1 implements the AMENDMENT_3 primaries (scope, content); "
    "v1's readout showed all six variant columns identical.",
    "Not implemented here: the H6 placement bounds and CELF (next step, METHODOLOGY_HARDENING.md §4), the H9 model, "
    "Chao2 and the quantile threshold for MAD = 0 sensors (W2, decision 52). v2.2+ reads Hotel, TeaStore (harness "
    "91c4967) and OTel (harness 6e37ec2) cells into one model; the rules are the same for all three, the system values "
    "are the registry's (SYSTEM_<SUT>, CLIENT_TIMEOUT_S_<SUT>, ROUTE_SERVICES_<SUT>, ACTUATOR_READBACK_<SUT>, ...).",
    "TeaStore and OTel (v2.2+): spans carry no token; a span's request is its trace's (TOKEN_SOURCES: TeaStore's auth "
    "bridge, OTel's originalTraceId); untokened probe traces are not read (PROBE_TRACE_RULE); the onset interval's "
    "upper bound is the command's return (no Docker events in the cells); several campaigns of one system are pooled "
    "(H1, decision 31); with fewer episodes than declared, P2 and P4 are — and P4's single episode is reported, "
    "descriptive. OTLP log records in otelcol.log are not read (L is application.log).",
]


def write_new(path, text):
    with open(path, "x", encoding="utf-8") as fh:           # exclusive create: never overwrites
        fh.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign", nargs="+", help="fetched campaign directory (holds runs/, or one child that does); "
                    "several directories of one system are pooled (sweep + quiet runs)")
    ap.add_argument("--system", default="hotel", choices=SYSTEMS, help="which reader (default hotel)")
    ap.add_argument("--out", required=True, help="NEW output directory; refused if it exists")
    ap.add_argument("--v1-readout", help="v1's committed sweep_analysis.json for the v1 moved-verdicts table")
    ap.add_argument("--v2-readout", help="v2-fix1's committed sweep_analysis_v2.json for the v2 moved-verdicts table")
    ap.add_argument("--v21-readout", help="v2.1's committed sweep_analysis_v2_1.json for the v2.1 moved-verdicts table")
    ap.add_argument("--v22-readout", help="v2.2's committed sweep_analysis_v2_2.json for the v2.2 moved-verdicts table")
    ap.add_argument("--v23-readout", help="v2.3's committed sweep_analysis_v2_3.json for the v2.3 moved-verdicts table")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists() or out.is_symlink():
        raise SystemExit("refusing to write into an existing path: %s" % out)
    camp = [Path(x) for x in a.campaign]
    R = run(camp[0] if len(camp) == 1 else camp, a.v1_readout, v2_readout=a.v2_readout, v21_readout=a.v21_readout,
            system=a.system, v22_readout=a.v22_readout, v23_readout=a.v23_readout)
    J = build_json(R)
    out.mkdir(parents=True)
    write_new(out / OUT_JSON, json.dumps(J, indent=1, sort_keys=True, default=sorted))
    write_new(out / OUT_MD, render(R, J))
    print("wrote", out / OUT_JSON, out / OUT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
