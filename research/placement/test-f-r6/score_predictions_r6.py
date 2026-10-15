#!/usr/bin/env python3
"""Score R6's predictions FR6-* / TR6-* (DECLARATION_OTEL_R6.md, 0ee8d62, committed alone before launch) against R6's COMMITTED outputs only.
Committed before the scorer and transfer outputs are read. Modelled on test-f-seed2/score_predictions_fs.py; every sensor is looked up by its
full id (4971108 fixed a short-name lookup there). Scope: instance.

    uv run python research/placement/test-f-r6/score_predictions_r6.py --out research/placement/test-f-r6/PREDICTIONS_SCORED_R6
    uv run python research/placement/test-f-r6/score_predictions_r6.py --run-stopped --out ...   # a stop with no read relaunch: every row —

Rules, exactly the declaration's "decided from" column (SET6 = the frontier (effort<=any, runtime<=any) @6/T_r set, rate 25):
  FR6-V1  otel-r6.json rates.25.verdicts (SET6 rule) of fraud-pause-effect and accounting-pause-effect: both PASS hit; any FAIL miss;
          otherwise (a — or a missing verdict, no FAIL) undecided.
  FR6-V2  placement-r6.json rates.25, grid cell (any, any), points["6/T_r"].set contains metric:kafka:kafka.consumer_group.lag: hit;
          a set without it, the empty set included, miss; no such cell, point or set: undecided.
  FR6-L1  off-path test episodes (the two classes above) in otel-r6.json rates.25.episodes with ledger.ttd not null: at most 1 hit, else miss;
          undecided if fewer than 4 off-path episodes are listed (the scorer lists valid test episodes only).
  FR6-C   control check, NOT counted: frontend-pause-effect test episodes, as R2's FS-C: ledger ttd < 1 s and SET6 ttd >= ledger ttd in 2 of 2,
          and the mean of (ledger penalised - SET6 penalised) is 0 (|.| < 1e-9); undecided if fewer than 2 frontend episodes or SET6 absent.
  TR6-LAG transfer-r6/transfer.json, F's placement-f.json (ce6bfc1b...): both off-path class verdicts PASS hit; a — or missing verdict
          undecided; otherwise miss.
  TR6-R2  the same on R2's placement-fs1.json (633b89f1...): REPORTED, NOT COUNTED (not independent of TR6-LAG).
  TR6-PUR the same transfer, the rerun's placement-f3.json (674580e0...): hit iff at least one off-path class verdict is FAIL; miss iff both
          PASS; otherwise undecided.
  Consistency (budget item 2): transfer-r6-own/transfer.json (transfer_score.py on placement-r6.json) must reproduce otel-r6.json rates.25
          episodes (episode, ledger, SET6 entry, in order, same count) and the SET6 verdicts (class, improved, gE, verdict); otherwise every
          TR6-* row is undecided.
A `—` decides its prediction as undecided, neither hit nor miss. The tally counts FR6-V1, FR6-V2, FR6-L1, TR6-LAG and TR6-PUR (denominator 5).
Refused (exit, nothing written): an existing output; a transfer file whose readout sha256 is not the scorer's scoring readout; a transfer file
without exactly the declared placements (the three frozen ones, or the own one).
"""
import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
D = REPO / "research/placement/test-f-r6"
DEFAULTS = {"scored": D / "otel-r6.json", "placement": D / "placement-r6.json",
            "transfer": D / "transfer-r6/transfer.json", "transfer_own": D / "transfer-r6-own/transfer.json"}
RATE = "25"
SET6 = "frontier (effort<=any, runtime<=any) @6/T_r"
POINT, CELL = "6/T_r", ("any", "any")
OFF = ("fraud-pause-effect", "accounting-pause-effect")
FRONT = "frontend-pause-effect"
LAG = "metric:kafka:kafka.consumer_group.lag"
DASH = "—"
F_PLACEMENT = "ce6bfc1b9addbb1771b189c9330b1930f0d84c9890c1fd8d8e8cae0978d20a3d"       # research/placement/test-f/placement-f.json {lag}
RERUN_PLACEMENT = "674580e08353e667ea32d587091fc38327db6d68e1d3f2142fdd94c9e433b606"   # research/placement/test-f-rep1/placement-f3.json {purgatory.size}
R2_PLACEMENT = "633b89f1beea3b6896488aa41de82983ac84c80d2230a768938190f0d181e560"      # research/placement/test-f-seed2/placement-fs1.json {lag, flagd}
COUNTED = ("FR6-V1", "FR6-V2", "FR6-L1", "TR6-LAG", "TR6-PUR")
ORDER = ("FR6-V1", "FR6-V2", "FR6-L1", "FR6-C", "TR6-LAG", "TR6-R2", "TR6-PUR")
ROLE = {"FR6-C": "control check, not counted", "TR6-R2": "reported, not counted (not independent of TR6-LAG)"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p):
    return json.loads(Path(p).read_text())


def set6_verdicts(R):
    """{class: verdict string} of the SET6 rule (a class without one is absent)."""
    return {v["rule"]["class"]: v["verdict"] for v in R.get("verdicts") or [] if v["rule"].get("set") == SET6 and v["rule"].get("class")}


def fr6_v1(R):
    ver = set6_verdicts(R)
    got = {c: ver.get(c, DASH) for c in OFF}
    if any(v == "FAIL" for v in got.values()):
        return False, got
    if all(v == "PASS" for v in got.values()):
        return True, got
    return None, got


def fr6_v2(P):
    R = (P.get("rates") or {}).get(RATE) or {}
    cell = next((c for c in R.get("grid") or [] if (c.get("maxEffort"), c.get("maxRuntime")) == CELL), None)
    pt = None if cell is None else (cell.get("points") or {}).get(POINT)
    if pt is None or not isinstance(pt.get("set"), list):
        return None, {"set": None, "why": "no (any, any) cell, no %s point or no set at rate %s" % (POINT, RATE)}
    return LAG in pt["set"], {"set": pt["set"]}


def fr6_l1(R):
    off = [e for e in R.get("episodes") or [] if e.get("class") in OFF]
    led = sum(1 for e in off if e["ledger"]["ttd"] is not None)
    n = {"ledgerDetected": led, "offPathEpisodes": len(off)}
    return (None if len(off) < 4 else led <= 1), n


def fr6_c(R):
    fe = [e for e in R.get("episodes") or [] if e.get("class") == FRONT]
    if len(fe) < 2 or any(SET6 not in (e.get("sets") or {}) for e in fe):
        return None, {"frontendEpisodes": len(fe), "why": "fewer than 2 frontend test episodes, or the SET6 set absent from one"}
    lt = [e["ledger"]["ttd"] for e in fe]
    st = [e["sets"][SET6]["ttd"] for e in fe]
    first = all(l is not None and l < 1 and s is not None and s >= l for l, s in zip(lt, st))
    g = sum(e["ledger"]["penalised"] - e["sets"][SET6]["penalised"] for e in fe) / len(fe)
    return first and abs(g) < 1e-9, {"ledgerTtd": lt, "setTtd": st, "gFrontend": g, "frontendEpisodes": len(fe)}


def transfer_rate(T, placement_sha):
    t = [x for x in T["transfers"] if x.get("placementSha256") == placement_sha]
    if len(t) != 1:
        raise SystemExit("refusing: transfer file holds %d transfers of placement %s..., not 1" % (len(t), placement_sha[:8]))
    return t[0]["rates"].get(RATE) or {}


def both_pass(R):
    ver = set6_verdicts(R)
    got = {c: ver.get(c, DASH) for c in OFF}
    if any(v not in ("PASS", "FAIL") for v in got.values()):
        return None, got
    return all(v == "PASS" for v in got.values()), got


def tr6_pur(R):
    ver = set6_verdicts(R)
    got = {c: ver.get(c, DASH) for c in OFF}
    if any(v == "FAIL" for v in got.values()):
        return True, got
    if all(v == "PASS" for v in got.values()):
        return False, got
    return None, got


def consistency(S, T_own):
    """[] if the own-placement transfer reproduces the scorer's rate-25 SET6 episodes and verdicts, else the mismatches."""
    ref, R = S["rates"].get(RATE) or {}, transfer_rate(T_own, S["inputs"]["placementSha256"])
    bad = []
    want = [(v["rule"].get("class"), v.get("improved"), v.get("gE"), v["verdict"]) for v in ref.get("verdicts") or [] if v["rule"].get("set") == SET6]
    got = [(v["rule"].get("class"), v.get("improved"), v.get("gE"), v["verdict"]) for v in R.get("verdicts") or []]
    if not want or got != want:
        bad.append(["verdicts", got, want])
    ea, eb = R.get("episodes") or [], ref.get("episodes") or []
    if len(ea) != len(eb):
        bad.append(["episode count", len(ea), len(eb)])
    for a, b in zip(ea, eb):
        if (a["episode"], a["ledger"], a["sets"].get(SET6)) != (b["episode"], b["ledger"], b["sets"].get(SET6)):
            bad.append(["episode", a["episode"], b["episode"]])
    return bad


def score(paths):
    S, P = load(paths["scored"]), load(paths["placement"])
    T, T_own = load(paths["transfer"]), load(paths["transfer_own"])
    rd = S["inputs"]["readoutSha256"]
    for name, X in (("transfer", T), ("transfer_own", T_own)):
        if X.get("readoutSha256") != rd:
            raise SystemExit("refusing: %s readout sha256 %s is not the scorer's scoring readout %s" % (name, X.get("readoutSha256"), rd))
    if sorted(x.get("placementSha256") for x in T["transfers"]) != sorted((F_PLACEMENT, RERUN_PLACEMENT, R2_PLACEMENT)):
        raise SystemExit("refusing: transfer file placements are not exactly F's, the rerun's and R2's")
    if [x.get("placementSha256") for x in T_own["transfers"]] != [S["inputs"]["placementSha256"]] or sha(paths["placement"]) != S["inputs"]["placementSha256"]:
        raise SystemExit("refusing: the own transfer, the placement file and the scorer do not name one placement")
    R = S["rates"][RATE]
    res = {}
    res["FR6-V1"] = fr6_v1(R)
    res["FR6-V2"] = fr6_v2(P)
    res["FR6-L1"] = fr6_l1(R)
    res["FR6-C"] = fr6_c(R)
    bad = consistency(S, T_own)
    for i, ps, fn in (("TR6-LAG", F_PLACEMENT, both_pass), ("TR6-R2", R2_PLACEMENT, both_pass), ("TR6-PUR", RERUN_PLACEMENT, tr6_pur)):
        ok, n = fn(transfer_rate(T, ps))
        if bad:
            ok, n = None, dict(n, consistencyFailed=bad)
        res[i] = (ok, dict(n, placementSha256=ps))
    inputs = {str(Path(p).resolve().relative_to(REPO)) if Path(p).resolve().is_relative_to(REPO) else str(p): sha(p) for p in paths.values()}
    return res, {"consistencyCheck": "pass" if not bad else "fail", "consistencyMismatches": bad}, inputs


def rows_of(res):
    return [{"id": i, "result": DASH if res[i][0] is None else ("hit" if res[i][0] else "miss"), "counted": i in COUNTED,
             "role": ROLE.get(i, "counted prediction"), "numbers": res[i][1]} for i in ORDER]


def write(out, rows, extra, inputs):
    oj, om = Path(str(out) + ".json"), Path(str(out) + ".md")
    if oj.exists() or om.exists():
        raise SystemExit("refusing: output exists")
    c = [r for r in rows if r["counted"]]
    tally = {"hit": sum(r["result"] == "hit" for r in c), "miss": sum(r["result"] == "miss" for r in c),
             "undecided": sum(r["result"] == DASH for r in c), "of": len(c)}
    rec = dict(extra, scope="instance", rows=rows, tally=tally, inputs=inputs,
               scriptSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    oj.write_text(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    om.write_text("# R6 predictions scored (instance)\n\nCounted: %(hit)d hit, %(miss)d miss, %(undecided)d undecided, of %(of)d.\n\n" % tally +
                  "| id | result | counted | numbers |\n|---|---|---|---|\n" +
                  "".join("| %s | %s | %s | `%s` |\n" % (r["id"], r["result"], "yes" if r["counted"] else "no (%s)" % r["role"],
                                                       json.dumps(r["numbers"], sort_keys=True, ensure_ascii=False)) for r in rows))
    print("wrote", oj, om)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="NEW output stem (writes <stem>.json and <stem>.md)")
    ap.add_argument("--run-stopped", action="store_true", help="R6 stopped with no read relaunch: every prediction —, no input read")
    for k, v in DEFAULTS.items():
        ap.add_argument("--" + k.replace("_", "-"), default=str(v))
    a = ap.parse_args(argv)
    if a.run_stopped:
        res = {i: (None, {"why": "the run stopped with no read relaunch (declaration: every prediction —)"}) for i in ORDER}
        return write(a.out, rows_of(res), {"runStopped": True}, {})
    paths = {k: getattr(a, k) for k in DEFAULTS}
    res, extra, inputs = score(paths)
    return write(a.out, rows_of(res), dict(extra, runStopped=False), inputs)


if __name__ == "__main__":
    main()
