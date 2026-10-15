#!/usr/bin/env python3
"""Campaign E block-split scorer: the frozen tiered placement's sets on the TEST blocks of one campaign (decision 95).

    uv run python research/placement/score_test_v3_2.py <v3.2 readout covering the test blocks> \
        --placement <frozen celf_v3_2 output> --training-readout <the placement's input readout> \
        --test-blocks 4 5 --out <NEW file.json> [--pass-rule <rule.json>] [--allow-unpinned]

STATUS: FROZEN in two steps (research/protocol/FREEZE_V32_20261013.md): this file's digest before the training
placement exists, and again after the one-line PINNED_PLACEMENTS pin. Scope of every number: **instance** (one SUT, one rate, the test blocks of one
campaign).

Like score_test_v3.py (frozen, imported for its helpers, never edited) with the campaign selected by BLOCK SET instead of
campaign index: the placement is solved on the training blocks (celf_v3_2.py on a readout read with `--blocks <train>`),
frozen, and this scorer scores every frozen set (each cell of the (max effort, max runtime) frontier at each named budget,
the comparators ledger alone / `full` / `out of the box` / declared) on the episodes of the TEST blocks only, with
celf_v3's unchanged objective (build_table with decision 72 `e-only` and decision 79/84 own-per-class `exclude`,
Objective `ttd`; a miss charged the hold; the ledger E in every set). D_E(S) = D over the test episodes; g_E(S) =
D_E(ledger alone) - D_E(S) >= 0 by construction. Sets are NEVER re-solved here.

INPUT CHECKS. (1) The scoring readout is a v3.2 readout (version, scriptSha256 = the installed reader or the pinned one,
v31ScriptSha256 = the frozen v3.1, the reader digests of v24 / detection_time / v1 equal the installed files, and its recorded
v32.parametersV32Sha256 = the pinned registry digest, or the live registry's while unpinned; the live registry must equal the
pin when one is set, F5; the placement's recorded registry digest is checked the same way). (2) The
placement is a celf_v3_2 output of the frozen celf_v3 (digest) and, when PINNED_PLACEMENTS has an entry for the system,
that digest. (3) The training readout is the placement's input readout (sha256) and its blocks are the placement's training
blocks. (4) The test blocks do not intersect the training blocks, the scoring readout holds every test block (its
blockSelection is all blocks or a superset), and the test episodes are selected by `episodes[].block` only. (5) An episode
key (regime, rate, block) twice among the test episodes is refused. Class counts are recorded (`classCounts`); the
expected count per class is not declared yet (EXPECTED_PER_CLASS None), so none is flagged.

A sensor placeable in the training readout but not in the scoring readout never fires here and is listed (decision 90's rule,
generalised). With decision 102 the N5 limitation of decision 88 does not apply to E.

PASS RULE (decision 99, round 30, with decisions 110 and 112; V32_PASS_RULE, editable only in the registry, its digest recorded in
every output): for each off-path class separately (fraud-pause-effect, accounting-pause-effect), the frozen set of the
unrestricted frontier cell at the budget the registry names (decision 112: `6/T_r`, two zero-alarm sensors evaluated in every
training fold, from candidates that recur in >= 2 training episodes of a class; decision 110's `3/T_r` and the `6/h` point are
scored and reported without a verdict) passes iff g = D(ledger alone) - D(S) > 0 over THAT class's test episodes (mean penalised-time difference, the class's
episodes only) and it improves at least minImprovedEpisodes (2) of them; a dash, never FAIL, if a member of the set is absent
from the scoring readout's ground set (decision 90) or fewer than minEpisodes (2) valid test episodes of the class exist
(decision 91). Rule form: a list of {"set", "rate", "class", "minGain", "minImprovedEpisodes", "minEpisodes"} (rate null = every
rate of the placement; minGain null = strictly positive). On-path classes and every other set carry no verdict. Verdicts are
listed per rate in `verdicts`. A rate that cannot be scored at all (no frozen grid, no calibration, no test episode) or a rule
whose point has no set (the rate has no hours, so no 3/T_r or 6/T_r) carries an explicit dash verdict per declared rule, with
the reason, never an empty list (review finding N1).

DECISION 102 (train-only calibration): the scoring readout is read with `--test-blocks` (= the registry's test blocks), so
the detectors it scores with were calibrated on the training blocks only; the scorer requires the readout's test episodes
to be flagged heldOut, the readout's recorded test blocks to be the test blocks, and its calibration to equal the training
readout's (detectors applied unchanged).

Split checks added after the independent review: `--test-blocks` must equal the test blocks the placement recorded (celf_v3_2
--split, fixed before launch); the training readout must hold no episode of a test block and share the scoring readout's
registry digests, campaigns, system and reader; test episodes are selected on (block, campaign-E epoch) (the readout tags each
episode with its study epoch). The class weights are recomputed on the test subset, so D_E is not comparable with the training
D (it is compared with the ledger's D_E in g_E).

Switches (flipped only by tests/test_score_test_v3_2.py, a planted defect each): REQUIRE_DECLARED_TEST, EPOCH_SELECT, TEST_ONLY, BLOCK_BY_NUMBER, FROZEN_SETS,
ABSENT_NEVER_FIRES, STRICT_IMPROVEMENT, REFUSE_OVERLAP, REQUIRE_TRAINING, REFUSE_DUPLICATE_EPISODES, ENFORCE_PINS,
NO_PASS_RULE_DASH, REQUIRE_HELD_OUT, SAME_CALIBRATION, CLASS_G.

DEVIATIONS FROM score_test_v3.py (group 10): block set instead of campaign index; frontier cells as frozen sets; a
parameterised pass rule (null) instead of decision 89's; no `--validation` requirement (E's fresh false alarms of frozen
sets are a dash: no validated path exists, as in decision 88).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import celf_v3 as cv  # noqa: E402  frozen
import celf_v3_2 as c2  # noqa: E402
import score_test_v3 as st  # noqa: E402  frozen; imported for absent_reasons and refuse only

VERSION = "score-test-v3.2"
SCOPE = "instance"
DASH = "—"
INF = math.inf
PARAMETERS_V32 = c2.PARAMETERS_V32
PINNED_PLACEMENTS = {"otel": "cea91ebd49858fbcdfda18cf1dde41f46a769c6b214a4af39351ed965400b859"}   # campaign E training placement research/placement/test-e/placement-e.json (FREEZE_V32_20261013.md step 2)
EXPECTED_PER_CLASS = None     # not declared yet (E's episodes per class and rate are fixed in its declaration)

TEST_ONLY = True                  # only test-block episodes are scored (False: every episode of the readout)
BLOCK_BY_NUMBER = True            # test episodes selected by block number (False: by the harness tag)
FROZEN_SETS = True                # frozen sets scored as frozen (False: re-solved on the scoring readout)
ABSENT_NEVER_FIRES = True         # a frozen member outside the scoring readout's V_r never fires (False: it fires)
STRICT_IMPROVEMENT = True         # improves = strictly below the ledger's (False: <=)
REFUSE_OVERLAP = True             # test and training blocks must be disjoint (False: accepted)
REQUIRE_TRAINING = True           # the training readout is required and checked (False: optional)
REQUIRE_DECLARED_TEST = True      # --test-blocks must equal the test blocks the placement recorded (False: any subset)
EPOCH_SELECT = True               # test episodes must be of the campaign-E epoch (False: any epoch's block-k episode)
REQUIRE_HELD_OUT = True           # decision 102: test episodes flagged heldOut, recorded test blocks = the test blocks
SAME_CALIBRATION = True           # decision 102: the scoring readout's calibration equals the training readout's
CLASS_G = True                    # decision 99: g is taken over the rule's class's episodes (False: over every test episode)
REFUSE_DUPLICATE_EPISODES = True  # an episode key twice among the test episodes is refused (False: both scored)
ENFORCE_PINS = True               # digests of celf_v3, the v3.1 script, the readout reader, the placement (False: not)
NO_PASS_RULE_DASH = True          # no declared rule -> verdict dash (False: a default rule PASS iff g_E > 0)
SWITCHES = ("REQUIRE_HELD_OUT", "SAME_CALIBRATION", "CLASS_G", "REQUIRE_DECLARED_TEST", "EPOCH_SELECT", "TEST_ONLY", "BLOCK_BY_NUMBER", "FROZEN_SETS", "ABSENT_NEVER_FIRES", "STRICT_IMPROVEMENT", "REFUSE_OVERLAP",
            "REQUIRE_TRAINING", "REFUSE_DUPLICATE_EPISODES", "ENFORCE_PINS", "NO_PASS_RULE_DASH")
DETECTION_TIME = REPO / "research" / "detection-time"
READER_DIGESTS = {"v24Sha256": DETECTION_TIME / "sweep_analysis_v2.py",
                  "detectionTimeSha256": DETECTION_TIME / "detection_time.py",
                  "v1Sha256": DETECTION_TIME / "sweep_analysis.py"}


def refuse(msg):
    st.refuse(msg)


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _registry():
    return {p["name"]: p["value"] for p in json.loads(PARAMETERS_V32.read_text())["parameters"]}


def pass_rule_registry():
    return _registry()["V32_PASS_RULE"]


E_SPLIT = _registry()["V32_E_SPLIT"]


# =========================================================================== input checks

def check_readout(J, allow_unpinned=False):
    if J.get("version") != "3.2":
        refuse("the scoring readout is not v3.2 (version %r)" % J.get("version"))
    installed = sha256(DETECTION_TIME / "sweep_analysis_v3_2.py")
    if ENFORCE_PINS:
        if J.get("v31ScriptSha256") != c2.PINNED_V31_SHA256:
            refuse("the readout was not built on the frozen v3.1 (%r)" % J.get("v31ScriptSha256"))
        want = c2.PINNED_V32_SHA256 or installed
        if J.get("scriptSha256") != want:
            refuse("readout scriptSha256 %r is not %s" % (J.get("scriptSha256"), want))
        if c2.PINNED_V32_SHA256 is None and not allow_unpinned:
            refuse("the v3.2 reader is not frozen (PINNED_V32_SHA256 is None): --allow-unpinned for exploration")
        c2.check_parameters_digest((J.get("v32") or {}).get("parametersV32Sha256"), "the scoring readout", allow_unpinned)
        for field, path in READER_DIGESTS.items():
            if J.get(field) != sha256(path):
                refuse("readout %s %r is not the installed %s" % (field, J.get(field), path.name))


def check_placement(P, psha, J, allow_unpinned=False):
    system = P.get("system")
    if ENFORCE_PINS:
        if (P.get("inputs") or {}).get("celfSha256") != c2.PINNED_CELF_SHA256:
            refuse("the placement was not produced with the frozen celf_v3")
        if P.get("version") != c2.VERSION:
            refuse("the placement is %r, not %s" % (P.get("version"), c2.VERSION))
        c2.check_parameters_digest((P.get("inputs") or {}).get("parametersV32Sha256"), "the placement", allow_unpinned)
        pin = PINNED_PLACEMENTS.get(system)
        if pin is None and not allow_unpinned:
            refuse("no pinned placement digest for %r (PINNED_PLACEMENTS): --allow-unpinned for exploration" % system)
        if pin is not None and pin != psha:
            refuse("placement sha256 %s is not the frozen %s" % (psha, pin))
    if system != J.get("system"):
        refuse("placement system %r, readout system %r" % (system, J.get("system")))


SAME_ACROSS_READOUTS = ("system", "scriptSha256", "v31ScriptSha256", "parametersSha256", "parametersV3Sha256",
                        "v32.parametersV32Sha256", "campaigns")


def _field(J, path):
    for part in path.split("."):
        J = J.get(part) if isinstance(J, dict) else None
    return J


def check_split(P, J, T, tsha, test_blocks):
    """Training readout = the placement's input; training blocks = the placement's; disjoint test; test blocks read."""
    train = (P.get("split") or {}).get("trainBlocks")
    if train is None:
        refuse("the placement records no training blocks (it was solved on an unsplit readout)")
    declared_test = (P.get("split") or {}).get("test")
    if REQUIRE_DECLARED_TEST:
        if declared_test is None:
            refuse("the placement records no declared test blocks (celf_v3_2 --split): the split is fixed before launch")
        if sorted(declared_test) != sorted(test_blocks):
            refuse("--test-blocks %s are not the declared test blocks %s" % (sorted(test_blocks), sorted(declared_test)))
    if REFUSE_OVERLAP and set(train) & set(test_blocks):
        refuse("test blocks %s overlap the training blocks %s" % (sorted(test_blocks), sorted(train)))
    if E_SPLIT["train"] is not None and sorted(test_blocks) != sorted(E_SPLIT["test"]):
        refuse("--test-blocks %s are not the registry test blocks %s (decision 100)" % (sorted(test_blocks),
                                                                                       sorted(E_SPLIT["test"])))
    if REQUIRE_HELD_OUT:
        rec = ((J.get("v32") or {}).get("blockSelection") or {}).get("testBlocks")
        if rec is None or sorted(rec) != sorted(test_blocks):
            refuse("the scoring readout recorded test blocks %s, not %s: it was not read with --test-blocks, so its "
                   "detectors were not calibrated on the training blocks only (decision 102)" % (rec, sorted(test_blocks)))
    if REQUIRE_TRAINING:
        if T is None:
            refuse("no training readout: that the placement's input is the training readout must be checked")
        if tsha != (P.get("inputs") or {}).get("readoutSha256"):
            refuse("training readout sha256 %s is not the placement's input readout %s" % (
                tsha, (P.get("inputs") or {}).get("readoutSha256")))
        tb = ((T.get("v32") or {}).get("blockSelection") or {}).get("blocks")
        if tb is None or sorted(tb) != sorted(train):
            refuse("the training readout's blocks %s are not the placement's training blocks %s" % (tb, sorted(train)))
        in_test = sorted({e["block"] for e in T["episodes"] if e["block"] in set(test_blocks)})
        if in_test:
            refuse("the training readout holds episodes of test block(s) %s" % in_test)
        if SAME_CALIBRATION and J.get("calibration") != T.get("calibration"):
            refuse("the scoring readout's calibration is not the training readout's: the detectors must be applied "
                   "unchanged (decision 102)")
        for field in SAME_ACROSS_READOUTS:
            a, b = _field(T, field), _field(J, field)
            if a != b:
                refuse("training and scoring readouts differ in %s (%r vs %r): the scoring must use the training "
                       "registry, campaign and reader" % (field, a, b))
    sel = ((J.get("v32") or {}).get("blockSelection") or {}).get("blocks")
    if sel is not None and not set(test_blocks) <= set(sel):
        refuse("the scoring readout read blocks %s, which do not hold every test block %s" % (sorted(sel),
                                                                                              sorted(test_blocks)))
    return {"checked": REQUIRE_TRAINING, "trainBlocks": sorted(train), "testBlocks": sorted(test_blocks),
            "scoringReadoutBlocks": sorted(sel) if sel is not None else "all"}


# =========================================================================== frozen sets

def frozen_sets(P, rk):
    """[(label, kind, members or None, info)] for one rate, all read from the frozen placement."""
    rows = []
    R = (P.get("rates") or {}).get(rk) or {}
    for c in R.get("grid") or []:
        for name, p in c["points"].items():
            lab = "frontier (effort<=%s, runtime<=%s) @%s" % (c["maxEffort"], c["maxRuntime"], name)
            rows.append((lab, "frontier", None if "set" not in p else list(p["set"]),
                         {"maxEffort": c["maxEffort"], "maxRuntime": c["maxRuntime"], "budgetName": name,
                          "budget": p.get("budget"), "note": p.get("note")}))
    comps = R.get("comparators") or {}
    rows.append(("ledger alone", "comparator", [], {}))
    if "groundSet" in R:
        rows.append(("full", "comparator", list(R["groundSet"]), {"source": "the frozen training ground set V_r"}))
    for name in sorted(comps):
        if name in ("ledger alone", "full"):
            continue
        c = comps[name]
        S = c.get("setMembers") if name == "out of the box" else c.get("sensors")
        rows.append((name, "comparator", S if isinstance(S, list) else None,
                     {"label": c.get("label"), "note": c.get("note") or (None if isinstance(S, list) else
                      "— (members not recorded as a list)")}))
    return rows


# =========================================================================== scoring

def tt(x):
    return None if x == INF else x


def dash_verdicts(rule, rk, reason):
    """N1: one explicit dash verdict per declared rule that applies at this rate, for a rate that cannot be scored."""
    return [{"rule": r, "episodesInPool": 0, "verdict": DASH, "reason": reason, "gE": None, "improved": None}
            for r in (rule or []) if r.get("rate") in (None, rk)]


def bare(note, rule, rk):
    return {"note": note, "verdicts": dash_verdicts(rule, rk, "not testable: " + note)}


def score_rate(J, P, rk, test_blocks, rule):
    R = (P.get("rates") or {}).get(rk) or {}
    if "grid" not in R:
        return bare("— (no frozen placement at this rate: %s)" % R.get("note"), rule, rk)
    if rk not in J["calibration"]["primary"]["perRate"]:
        return bare("— (no calibration at this rate in the scoring readout)", rule, rk)
    rate = float(rk)
    V, excluded = cv.ground_set(J, rate)
    Vset = set(V)
    rows = frozen_sets(P, rk)
    members_all = sorted({s for _, _, S, _ in rows if isinstance(S, list) for s in S})
    universe = V if ABSENT_NEVER_FIRES else sorted(Vset | set(members_all))
    table = cv.build_table(J, rate, universe, "e-only", "exclude")
    if TEST_ONLY:
        if BLOCK_BY_NUMBER:
            applies = set(((J.get("v32") or {}).get("blockSelection") or {}).get("applies") or [])
            idx = [i for i, e in enumerate(table.episodes) if e["block"] in test_blocks
                   and (not EPOCH_SELECT or e.get("studyEpoch") in applies)]
        else:                                         # planted: every episode with the campaign-B tag stands in for the split
            idx = [i for i, e in enumerate(table.episodes) if e.get("harness") == "B"]
    else:
        idx = list(range(len(table.episodes)))
    if not idx:
        return bare("— (no test episode at this rate)", rule, rk)
    if REQUIRE_HELD_OUT and TEST_ONLY and not all(table.episodes[i].get("heldOut") for i in idx):
        refuse("a test episode of the scoring readout is not flagged heldOut (its cell fed the calibration)")
    seen = {}
    for i in idx:
        e = table.episodes[i]
        k = (e["regime"], cv.rate_key(e["rate"]), e["block"])
        if k in seen and REFUSE_DUPLICATE_EPISODES:
            refuse("episode key %r twice among the test episodes (%r and %r)" % (k, seen[k], e.get("cell")))
        seen[k] = e.get("cell")
    obj = cv.Objective(table, idx, "ttd")
    pe = obj.pe
    episodes = []
    for k, i in enumerate(idx):
        e = table.episodes[i]
        episodes.append({"episode": e.get("cell"), "episodeKey": list(cv.episode_key(e)), "class": e["regime"],
                         "block": e["block"], "holdSeconds": e["holdSeconds"], "calibrated": e.get("calibrated") is True,
                         "ledger": {"ttd": tt(table.te[i]), "penalised": pe[k]}, "sets": {}})
    D_led = obj.D_ledger()
    if not FROZEN_SETS:                                # planted defect: every frontier set re-solved on the scoring readout
        costs_all, _ = cv.costs_of(J, rate)
        rows = [(lab, kind, (list((lambda sol: sol["preAdmitted"] + sol["chosen"])(cv.solve(
            obj, V, {s: costs_all[s] for s in V}, INF if info["budget"] == "inf" else info["budget"])))
            if (kind == "frontier" and S is not None) else S), info) for lab, kind, S, info in rows]
    sets, cache = {}, {}
    for lab, kind, S, info in rows:
        row = dict(info, kind=kind, freshFalseAlarms=FAR_NOTE)
        if S is None:
            row.update(sensors=None, D=None, DLedger=D_led, g=None)
            row["note"] = row.get("note") or "— (not declared)"
            sets[lab] = row
            continue
        key = tuple(sorted(S))
        if key in cache:                               # identical frozen set: scored once, the label points to it
            row.update(sameAs=cache[key])
            row["_ref"] = cache[key]
            sets[lab] = row
            continue
        cache[key] = lab
        absent = st.absent_reasons(J, rk, S, Vset, excluded)
        m = list(pe)
        for s in S:
            m = [min(a, b) for a, b in zip(m, obj.pen(s))]
        Dv = obj.D(S)
        if abs(Dv - sum(w * x for w, x in zip(obj.w, m))) > 1e-9 * max(1.0, abs(Dv)):
            raise AssertionError("the reported per-episode values do not compose to the reported D for %s" % lab)
        for k, i in enumerate(idx):
            raw = min([table.te[i]] + [table.T(s)[i] for s in S])
            better = (m[k] < pe[k]) if STRICT_IMPROVEMENT else (m[k] <= pe[k])
            episodes[k]["sets"][lab] = {"ttd": tt(raw), "penalised": m[k], "improvesOnLedger": better}
        row.update(sensors=sorted(S) if lab != "full" else "V_r frozen (%d)" % len(S), size=len(S), D=Dv,
                   DLedger=D_led, g=D_led - Dv,
                   detectedEpisodes=[sum(1 for k in range(len(idx)) if episodes[k]["sets"][lab]["ttd"] is not None),
                                     len(idx)],
                   absentFromScoringGroundSet={"count": len(absent), "sensors": absent}, _absent=absent)
        sets[lab] = row
    for lab, row in sets.items():                      # aliases take their target's numbers
        if "_ref" in row:
            tgt = sets[row.pop("_ref")]
            for k in ("sensors", "size", "D", "DLedger", "g", "detectedEpisodes", "absentFromScoringGroundSet"):
                row[k] = tgt[k]
            row["_absent"] = tgt["_absent"]
            for x in episodes:
                x["sets"][lab] = x["sets"][row["sameAs"]]
    if rule is None and not NO_PASS_RULE_DASH:         # planted defect: a default rule nobody declared
        rule = [{"set": "frontier (effort<=any, runtime<=any) @6/h", "rate": None, "class": None, "minGain": None,
                 "minImprovedEpisodes": None, "minEpisodes": None}]
    verdicts = [v for v in (verdict(r, rk, sets, episodes) for r in (rule or [])) if v is not None]
    for row in sets.values():
        row.pop("_absent", None)
    classes = {}
    for x in episodes:
        classes[x["class"]] = classes.get(x["class"], 0) + 1
    return {"rate": rate, "episodesScored": len(idx), "testBlocks": sorted({x["block"] for x in episodes}),
            "classCounts": dict(sorted(classes.items())),
            "classCountFlags": ({c: n for c, n in sorted(classes.items()) if n != EXPECTED_PER_CLASS}
                                if EXPECTED_PER_CLASS else None), "verdicts": verdicts,
            "groundSetSize": len(V), "episodesAtRateInReadout": len(table.episodes), "sets": sets,
            "episodes": episodes,
            "rules": {"bc": "e-only", "own": "exclude", "penalty": "ttd", "missAtHold": cv.MISS_AT_HOLD}}


FAR_NOTE = ("— (decision 88 analogue: fresh false alarms of the frozen sets on E's no-fault cells need a validated path; "
            "none exists)")
NO_RULE = {"verdict": DASH, "reason": "no pass rule declared (V32_PASS_RULE is null)"}


def verdict(rule, rk, sets, episodes):
    """One declared pass rule at rate rk (decision 99), or None where it does not apply at this rate."""
    if rule.get("rate") not in (None, rk):
        return None
    lab = rule["set"]
    row = sets.get(lab)
    pool = [x for x in episodes if rule.get("class") in (None, x["class"])]
    base = {"rule": rule, "episodesInPool": len(pool)}
    if row is None or row.get("D") is None:
        return dict(base, verdict=DASH, reason="the rule's set %r is missing or has no set at this rate%s" % (
            lab, (": " + row["note"]) if row and row.get("note") else ""))
    improved = sum(1 for x in pool if x["sets"][lab]["improvesOnLedger"])
    if CLASS_G and rule.get("class") is not None:      # g over THIS class's test episodes (uniform within one class)
        g = (math.fsum(x["ledger"]["penalised"] - x["sets"][lab]["penalised"] for x in pool) / len(pool)) if pool else None
    else:
        g = row["g"]
    absent = row.get("_absent") or {}
    out = dict(base, improved=improved, gE=g, gPositive=(cv.positive(g) if g is not None else None),
               absentFromScoringGroundSet=absent)
    if absent:
        out.update(verdict=DASH, reason="not testable (decision 90): member(s) of the rule's set absent from the scoring "
                   "readout's ground set: %s" % "; ".join("%s (%s)" % kv for kv in sorted(absent.items())))
        return out
    if not pool or (rule.get("minEpisodes") is not None and len(pool) < rule["minEpisodes"]):
        out.update(verdict=DASH, reason="not testable (decision 91): %d valid test episode(s) of the class, fewer than %s"
                   % (len(pool), rule.get("minEpisodes") if rule.get("minEpisodes") is not None else 1))
        return out
    reasons = []
    need = rule.get("minGain")
    if (g <= need) if need is not None else not cv.positive(g):
        reasons.append("g_E = %.6g is not above %s" % (g, need if need is not None else 0))
    if rule.get("minImprovedEpisodes") is not None and improved < rule["minImprovedEpisodes"]:
        reasons.append("improves %d of %d episodes (< %d)" % (improved, len(pool), rule["minImprovedEpisodes"]))
    out.update(verdict="FAIL" if reasons else "PASS",
               reason="; ".join(reasons) if reasons else "g_E = %.6g; improves %d of %d episodes" % (g, improved,
                                                                                                    len(pool)))
    return out


RULE_KEYS = {"set", "rate", "class", "minGain", "minImprovedEpisodes", "minEpisodes"}


def validate_rule(rules, P):
    """A declared pass rule (a list of rule objects) must name a frozen set and a placement rate; unknown keys are refused."""
    if rules is None:
        return None
    if isinstance(rules, dict):
        rules = [rules]
    if not isinstance(rules, list) or not rules:
        refuse("the pass rule must be a non-empty list of objects")
    out = []
    rates = list((P.get("rates") or {}))
    labels = {lab for r in rates for lab, _, _, _ in frozen_sets(P, r)}
    for rule in rules:
        if not isinstance(rule, dict) or not RULE_KEYS >= set(rule) or "set" not in rule:
            refuse("a pass rule must be an object with a `set` and keys from %s" % sorted(RULE_KEYS))
        rk = rule.get("rate")
        if rk is not None:
            rk = "%g" % rk if isinstance(rk, (int, float)) and not isinstance(rk, bool) else rk
            if rk not in rates:
                refuse("the pass rule's rate %r is not a rate of the placement %s" % (rule.get("rate"), rates))
        if rule["set"] not in labels:
            refuse("the pass rule's set %r is not a frozen set label of the placement" % rule["set"])
        out.append(dict(rule, rate=rk))
    return out


def score(J, P, psha, test_blocks, training=None, rule=None, allow_unpinned=False):
    celf_sha = c2.check_frozen_celf()
    rule = validate_rule(rule, P)
    check_readout(J, allow_unpinned)
    check_placement(P, psha, J, allow_unpinned)
    tr = check_split(P, J, training[0] if training else None, training[1] if training else None, set(test_blocks))
    rates = {rk: score_rate(J, P, rk, set(test_blocks), rule) for rk in sorted(P["rates"], key=float)}
    return {"version": VERSION, "scope": SCOPE, "system": J.get("system"), "splitCheck": tr,
            "deviation": cv.DEVIATION_80, "freshFalseAlarms": FAR_NOTE, "passRule": rule,
            "passRuleNote": "no pass rule declared (V32_PASS_RULE is null)" if rule is None else
            "decision 99 (V32_PASS_RULE in the registry, digest recorded)",
            "switches": {k: globals()[k] for k in SWITCHES}, "celfSha256": celf_sha, "rates": rates,
            "limitation": "the scoring readout calibrates its detectors on the training blocks only (decision 102); exposure and the P1-P4 tables of the scoring readout still read every valid cell (report-only)"}


# =========================================================================== output

def fmt(x):
    return DASH if x is None else ("%.3f" % x)


def markdown(res):
    L = ["# Campaign E test scoring (%s, scope %s)" % (res["version"], res["scope"]), "",
         "System `%s`; test blocks %s; training blocks %s. Penalty `ttd` (a miss charged the hold); D and g_E in "
         "seconds; g_E = D_E(ledger alone) - D_E(S). Pass rule: %s." % (
             res["system"], res["splitCheck"]["testBlocks"], res["splitCheck"]["trainBlocks"], res["passRuleNote"]),
         "Fresh false alarms of every frozen set: %s." % res["freshFalseAlarms"],
         "Deviation: %s." % res["deviation"], "Limitation: %s." % res["limitation"], ""]
    for rk, r in res["rates"].items():
        L.append("## r%s" % rk)
        if "sets" not in r:
            L += ["", r["note"], ""]
            for v in r.get("verdicts") or []:
                L.append("- `%s` on `%s`: **%s** (%s)." % (v["rule"].get("class") or "all classes", v["rule"]["set"],
                                                          v["verdict"], v["reason"]))
            L.append("")
            continue
        L += ["", "Test episodes: %d (%s). Ground set of the scoring readout: %d sensors." % (
            r["episodesScored"], ", ".join("%s %d" % kv for kv in r["classCounts"].items()), r["groundSetSize"]), "",
            "| set | size | absent from V_r | D_E(S) | D_E(ledger) | g_E | detected |",
            "|---|---|---|---|---|---|---|"]
        for lab, s in r["sets"].items():
            if s.get("D") is None:
                L.append("| %s | — | — | — | %s | — | — | %s |" % (lab, fmt(s["DLedger"]), s.get("note") or DASH))
                continue
            ab = s["absentFromScoringGroundSet"]
            L.append("| %s%s | %s | %s | %s | %s | %s | %d/%d |" % (
                lab, (" (= %s)" % s["sameAs"]) if s.get("sameAs") else "", s["size"], ab["count"], fmt(s["D"]),
                fmt(s["DLedger"]), fmt(s["g"]), s["detectedEpisodes"][0], s["detectedEpisodes"][1]))
        L += ["", "Verdicts (decision 99, per class; on-path classes carry none):" if r["verdicts"] else
              "Verdicts: none (%s)." % res["passRuleNote"], ""]
        for v in r["verdicts"]:
            L.append("- `%s` on `%s`: **%s** (%s); g over the class's %d test episode(s) = %s." % (
                v["rule"].get("class") or "all classes", v["rule"]["set"], v["verdict"], v["reason"],
                v["episodesInPool"], fmt(v.get("gE"))))
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="v3.2 readout whose episodes include the test blocks")
    ap.add_argument("--placement", required=True, help="frozen celf_v3_2 output")
    ap.add_argument("--training-readout", required=True, help="the placement's input readout (checked)")
    ap.add_argument("--test-blocks", nargs="+", type=int, required=True)
    ap.add_argument("--allow-unpinned", action="store_true")
    ap.add_argument("--out", required=True, help="NEW <file>.json; <file>.md beside it; refused if either exists")
    a = ap.parse_args(argv)
    out = Path(a.out)
    md = out.with_suffix(".md")
    if out.suffix != ".json":
        refuse("--out must end in .json")
    for p in (out, md):
        if p.exists() or p.is_symlink():
            refuse("to write into an existing path: %s" % p)
    J = json.loads(Path(a.readout).read_text())
    P = json.loads(Path(a.placement).read_text())
    T = json.loads(Path(a.training_readout).read_text())
    rule = pass_rule_registry()                          # registry only (decision 99); its digest is recorded below
    res = score(J, P, sha256(a.placement), a.test_blocks, (T, sha256(a.training_readout)), rule, a.allow_unpinned)
    res["inputs"] = {"readout": str(a.readout), "readoutSha256": sha256(a.readout), "placement": str(a.placement),
                     "placementSha256": sha256(a.placement), "trainingReadout": a.training_readout,
                     "trainingReadoutSha256": sha256(a.training_readout),
                     "parametersV32Sha256": sha256(PARAMETERS_V32), "pinnedParametersV32": c2.PINNED_PARAMETERS_V32_SHA256,
                     "script": str(Path(__file__).resolve().relative_to(REPO)), "scriptSha256": sha256(__file__),
                     "python": sys.version}
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(res, indent=1, sort_keys=True, allow_nan=False))
    with open(md, "x", encoding="utf-8") as fh:
        fh.write(markdown(res))
    print("wrote", out)
    print("wrote", md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
