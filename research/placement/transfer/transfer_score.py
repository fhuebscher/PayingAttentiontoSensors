#!/usr/bin/env python3
"""Transfer of frozen sensor sets to a new run (BUDGET_OVERNIGHT_20261015.md, bfc9417, analysis item 2). POST HOC to the sets; scope instance.

    uv run python research/placement/transfer/transfer_score.py <new run's scoring readout> --test-blocks 4 5 \
        --placement <earlier run's frozen placement.json> [--placement ...] --out <NEW dir>

For each earlier placement, its frozen frontier set at the point POINT (any effort, any runtime) is taken per rate, and only that set
is scored on the new run's scoring readout with score_test_v3_2.score_rate, imported and never edited: per test episode the earliest
counted fire of the set's members (by-construction fires and the faulted service's own sensors excluded exactly as the scorer
excludes them) against the ledger alone, a miss charged the hold, improvement strict, and the verdict per class (and rate) in the
form of the system's registered pass rule (OTel: V32_PASS_RULE; TeaStore: V36_PASS_RULE). A member absent from the new run's ground
set makes that verdict — (decision 90), never a miss. The selection is frozen; the thresholds are the new run's own training
calibration (the scoring readout's).

EVERY RATE OF THE PLACEMENT is passed to score_rate, so a rate that cannot be scored carries score_rate's own explicit dash verdict
per rule (its N1 rule) with the reason: no frozen grid at the rate, no POINT in the (any, any) cell (the cell is passed with no
point, so the rule's set is missing), a POINT with no set (no hours), or no calibration at the rate in the scoring readout. The
rules are the registered rules for the POINT label at the placement's rates (a registered rule at a rate the placement does not
have is listed under `rulesNotApplicable`) and are validated by score_test_v3_2.validate_rule against the placement's view; a
placement with no POINT set at any rate is refused there (it holds no set the rule names).

INPUT CHECKS MADE (the scoring readout's; they do not involve the placement):
  - the readout check of the system's scorer wrapper, unchanged and in full: score_test_v3_3.check_readout (OTel: v3.3 layer, then
    the v3.2 layer and the v24 / detection-time / v1 reader digests) or score_test_v3_6.check_readout (TeaStore: v3.6, v3.3 and
    v3.2 layers); the reader and registry pins it checks belong to the readout, so they apply to a foreign set as they do to an own one;
  - celf_v3_2.check_frozen_celf (the installed celf_v3 is the frozen one), as score_test_v3_2.score makes it;
  - the readout's recorded test blocks (v32.blockSelection.testBlocks) equal --test-blocks (the readout half of decision 102's
    REQUIRE_HELD_OUT; the episode half, every test episode flagged heldOut, and the duplicate-episode refusal are inside score_rate);
  - --test-blocks equal the registry's V32_E_SPLIT test blocks and the readout's blockSelection.blocks hold every test block, as
    the check_split that both wrappers inherit makes them;
  - the placement's system equals the readout's.
INPUT CHECKS SKIPPED, because each one ties the scoring to the placement's OWN run and the placement belongs to another run by design:
  - check_placement (the celf_v3_x version and digest, the placement's registry digests, PINNED_PLACEMENTS);
  - check_split's placement parts: the training readout is the placement's input readout and holds the placement's training blocks
    (REQUIRE_TRAINING), --test-blocks equal the placement's declared test blocks (REQUIRE_DECLARED_TEST), the test blocks do not
    overlap the placement's training blocks (REFUSE_OVERLAP), the scoring readout's calibration equals the placement's training
    readout's (SAME_CALIBRATION), and the two readouts agree on SAME_ACROSS_READOUTS.
The output records the readout sha256, the rule registry's path and live sha256 (V32 for OTel, V36 for TeaStore) beside its pin,
and the digests of this script and score_test_v3_2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "research" / "placement"))
import celf_v3_2 as c2  # noqa: E402  frozen
import score_test_v3_2 as s2  # noqa: E402  frozen; imported, never edited

VERSION = "transfer-score-v2"
POINT = "6/T_r"                       # the frozen frontier point the pass rule names
CELL = ("any", "any")                 # (maxEffort, maxRuntime) of the rule's frontier cell
SYSTEMS = ("otel", "teastore")
LABEL = "frontier (effort<=%s, runtime<=%s) @%s"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _refuse_system(system):
    raise SystemExit("refusing: no registered pass rule for system %r (only %s)" % (system, ", ".join(SYSTEMS)))


def rule_for(system):
    """The system's registered pass rule, unchanged: OTel V32_PASS_RULE (score_test_v3_2), TeaStore V36_PASS_RULE (celf_v3_6)."""
    if system == "otel":
        return s2.pass_rule_registry()
    if system == "teastore":
        import celf_v3_6 as c6
        return json.loads(json.dumps(c6._registry36()["V36_PASS_RULE"]))
    _refuse_system(system)


def readout_checks(J, test_blocks):
    """The scoring readout's checks that do not involve the placement (module docstring); returns what was checked."""
    system = J.get("system")
    if system == "otel":
        import score_test_v3_3 as w
        reg, pin = c2.PARAMETERS_V32, c2.PINNED_PARAMETERS_V32_SHA256
    elif system == "teastore":
        import celf_v3_6 as c6
        import score_test_v3_6 as w
        reg, pin = c6.PARAMETERS_V36, c6.PINNED_PARAMETERS_V36_SHA256
    else:
        _refuse_system(system)
    w.check_readout(J)                                   # allow_unpinned False, as the wrappers' main() runs it
    celf = c2.check_frozen_celf()
    tb = sorted(test_blocks)
    sel = (J.get("v32") or {}).get("blockSelection") or {}
    if sel.get("testBlocks") is None or sorted(sel["testBlocks"]) != tb:
        raise SystemExit("refusing: the scoring readout recorded test blocks %s, not --test-blocks %s (decision 102)"
                         % (sel.get("testBlocks"), tb))
    if s2.E_SPLIT["train"] is not None and tb != sorted(s2.E_SPLIT["test"]):
        raise SystemExit("refusing: --test-blocks %s are not the registry test blocks %s (decision 100)" % (tb, sorted(s2.E_SPLIT["test"])))
    if sel.get("blocks") is not None and not set(tb) <= set(sel["blocks"]):
        raise SystemExit("refusing: the scoring readout read blocks %s, which do not hold every test block %s" % (sorted(sel["blocks"]), tb))
    return {"system": system, "checkReadout": "%s.check_readout" % w.__name__, "celfSha256": celf,
            "recordedTestBlocks": sorted(sel["testBlocks"]), "scoringReadoutBlocks": sorted(sel["blocks"]) if sel.get("blocks") is not None else "all",
            "ruleRegistry": str(Path(reg).resolve().relative_to(REPO)), "ruleRegistrySha256": sha(reg), "pinnedRuleRegistrySha256": pin}


def frozen_view(P):
    """Every rate of P, holding only P's frozen set at POINT in the CELL frontier cell (no comparators, no ground set). A rate with
    no grid keeps its note; a CELL cell without POINT is kept with no point; a rate without a CELL cell keeps an empty grid, so
    score_rate gives each rule its own dash verdict in all three cases."""
    rates = {}
    for rk, R in (P.get("rates") or {}).items():
        if "grid" not in R:
            rates[rk] = {"note": R.get("note")}
            continue
        grid = []
        for c in R.get("grid") or []:
            if (c.get("maxEffort"), c.get("maxRuntime")) != CELL:
                continue
            pts = c.get("points") or {}
            if POINT in pts and "set" in pts[POINT] and not isinstance(pts[POINT]["set"], list):
                raise SystemExit("refusing: rate %s point %s set is not a list" % (rk, POINT))
            grid.append({"maxEffort": CELL[0], "maxRuntime": CELL[1], "points": {POINT: dict(pts[POINT])} if POINT in pts else {}})
        rates[rk] = {"grid": grid}
    return {"system": P.get("system"), "rates": rates}


def members_of(V, rk):
    """(members or None, why there is no set): an empty list is an empty set, None a missing set."""
    R = V["rates"][rk]
    if "grid" not in R:
        return None, "— (no frozen placement at this rate: %s)" % R.get("note")
    if not R["grid"]:
        return None, "— (no (%s, %s) frontier cell at this rate)" % CELL
    p = R["grid"][0]["points"].get(POINT)
    if p is None:
        return None, "— (no %s point in the (%s, %s) cell)" % ((POINT,) + CELL)
    if "set" not in p:
        return None, "— (the %s point has no set: %s)" % (POINT, p.get("note"))
    return list(p["set"]), None


def _rk(r):
    return "%g" % r if isinstance(r, (int, float)) and not isinstance(r, bool) else r


def transfer(J, P, test_blocks, checks=None):
    """{rate: score_rate(...)} for every rate of P on readout J, under the system's rule for the POINT label at P's rates."""
    if J.get("system") != P.get("system"):
        raise SystemExit("refusing: placement system %r, readout system %r" % (P.get("system"), J.get("system")))
    checks = checks or readout_checks(J, test_blocks)
    V = frozen_view(P)
    label = LABEL % (CELL + (POINT,))
    rules = [r for r in rule_for(J.get("system")) if r.get("set") == label]
    not_applicable = [r for r in rules if r.get("rate") is not None and _rk(r["rate"]) not in V["rates"]]
    rules = [r for r in rules if r not in not_applicable]
    if not rules:
        raise SystemExit("refusing: no registered pass rule for %r applies at the placement's rates %s" % (label, sorted(V["rates"])))
    rules = s2.validate_rule(rules, V)
    out, members, why = {}, {}, {}
    for rk in sorted(V["rates"], key=float):
        out[rk] = s2.score_rate(J, V, rk, set(test_blocks), rules)
        members[rk], why[rk] = members_of(V, rk)
    return {"label": label, "members": members, "membersMissing": {rk: w for rk, w in why.items() if w}, "rules": rules,
            "rulesNotApplicable": not_applicable, "readoutChecks": checks, "rates": out}


def _members_cell(t, rk):
    S = t["members"].get(rk)
    if S is None:
        return t["membersMissing"].get(rk, "— (missing)")
    return ", ".join(S) if S else "(empty set)"


def markdown(res):
    w = ["# Transfer of frozen sets (POST HOC to the sets; instance)", "",
         "Readout `%s` (sha256 `%s`); test blocks %s; point %s; rule registry `%s` sha256 `%s` (pin `%s`)." % (
             res["readout"], res["readoutSha256"], res["testBlocks"], res["point"], res["readoutChecks"]["ruleRegistry"],
             res["readoutChecks"]["ruleRegistrySha256"], res["readoutChecks"]["pinnedRuleRegistrySha256"]), "",
         "| placement | rate | members | class | improved | g (s) | verdict | reason | absent members |",
         "|---|---|---|---|---|---|---|---|---|"]
    for t in res["transfers"]:
        for rk, R in t["rates"].items():
            for v in R.get("verdicts") or [{"rule": {"class": "—"}, "verdict": "—", "reason": R.get("note") or "— (no verdict)"}]:
                absent = v.get("absentFromScoringGroundSet") or {}
                w.append("| %s | %s | %s | %s | %s/%s | %s | %s | %s | %s |" % (
                    t["placement"], rk, _members_cell(t, rk), v["rule"].get("class"), "—" if v.get("improved") is None else v["improved"],
                    v.get("episodesInPool", "—"), "—" if v.get("gE") is None else "%.3f" % v["gE"], v["verdict"],
                    v.get("reason") or "", "; ".join("%s (%s)" % kv for kv in sorted(absent.items())) or "none"))
        for r in t["rulesNotApplicable"]:
            w.append("| %s | %s | %s | %s | — | — | — | not applicable: the rule's rate is not a rate of the placement | — |" % (
                t["placement"], _rk(r["rate"]), "—", r.get("class")))
    return "\n".join(w) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("readout", help="the new run's scoring readout (v3.3 OTel or v3.6 TeaStore)")
    ap.add_argument("--test-blocks", nargs="+", type=int, required=True)
    ap.add_argument("--placement", action="append", required=True, help="an earlier run's frozen placement (repeatable)")
    ap.add_argument("--out", required=True, help="NEW directory")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        raise SystemExit("refusing: output exists (new evidence never overwrites old): %s" % out)
    J = json.loads(Path(a.readout).read_text())
    checks = readout_checks(J, a.test_blocks)
    res = {"version": VERSION, "label": "POST HOC to the frozen sets (declared before the new run's fetch was read); instance scope",
           "readout": a.readout, "readoutSha256": sha(a.readout), "testBlocks": sorted(a.test_blocks), "point": POINT,
           "readoutChecks": checks, "scriptSha256": sha(__file__), "scoreTestV32Sha256": sha(s2.__file__), "transfers": []}
    for p in a.placement:
        t = transfer(J, json.loads(Path(p).read_text()), a.test_blocks, checks)
        t.pop("readoutChecks")
        res["transfers"].append(dict(t, placement=p, placementSha256=sha(p)))
    out.mkdir(parents=True)
    (out / "transfer.json").write_text(json.dumps(res, indent=1, sort_keys=True, allow_nan=False))
    md = markdown(res)
    (out / "transfer.md").write_text(md)
    print(md, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
