#!/usr/bin/env python3
"""Score R5's predictions TS5-* (DECLARATION_TEASTORE_R5.md, c61cde6, committed alone before launch) against R5's COMMITTED outputs only.
Committed before the R5 scorer and transfer outputs are read (as score_predictions_ts3.py, 493732b). Sensors by full id. Scope: instance.

    uv run python research/placement/test-ts-r5/score_predictions_ts5.py --scored research/placement/test-ts-r5/<R5 scorer out>.json \
        --placement research/placement/test-ts-r5/<R5 placement>.json --transfer <transfer of R1's sets>/transfer.json \
        --transfer-own <transfer of R5's own placement>/transfer.json --out research/placement/test-ts-r5/PREDICTIONS_SCORED_TS5
    uv run python research/placement/test-ts-r5/score_predictions_ts5.py --run-stopped --out ...   # R5 stopped: every row —

Rules, exactly the declaration's table (SET6 = frontier (effort<=any, runtime<=any) @6/T_r; REC = recommender-pause-effect, off path;
AUTH = auth-freeze-effect, on-path control; rates "1" and "10"):
  TS5-V1  scorer verdict of the REC SET6 rule at rate 1: PASS hit, FAIL miss, — (or none) undecided.
  TS5-V10 the same at rate 10.
  TS5-S   placement: the (any, any) @6/T_r set contains log:webui:d4d75ec135e6 at both rates: hit; — if the @6/T_r point (or its set) is
          absent at a rate; otherwise (the empty set included) miss.
  TS5-T1  transfer script, R1's placement-rep3r1.json (f7f5c04a...) at rate 1 ({webui line}): the REC verdict's `improved` is 2 of 2
          episodes in the pool: hit; fewer: miss; a — verdict (member absent, fewer than 2 valid test episodes) undecided.
  TS5-T10 the same transfer at rate 10 ({auth span}): `improved` at most 1 of 2: hit; 2 of 2: miss; — undecided.
  TS5-L   a CHECK, NOT COUNTED: the ledger alone (ledger.ttd null) misses every REC test episode of the scorer, 4 of 4; — if fewer than 4 listed.
  TS5-C   scorer episodes: the ledger detects (ledger.ttd not null) 4 of 4 AUTH test episodes: hit; fewer: miss; — if fewer than 4 listed.
  Consistency (budget item 2): the transfer of R5's OWN placement must reproduce the R5 scorer's per-episode outcomes (per rate: episode,
          ledger, SET6 entry, in order, same count) and its SET6 verdicts (class, improved, gE, verdict); otherwise TS5-T1 and TS5-T10 are —.
A `—` decides a prediction as undecided, neither hit nor miss. The tally counts TS5-V1, V10, S, T1, T10 and C (denominator 6).
Refused (exit, nothing written): an existing output; a transfer whose readout path or sha256 is not the scorer's `inputs.readout` /
`inputs.readoutSha256` (the declaration: the same file); a transfer file not holding exactly R1's placement; an own transfer, placement file
and scorer `inputs.placementSha256` that do not name one placement.
"""
import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SET6 = "frontier (effort<=any, runtime<=any) @6/T_r"
POINT, CELL = "6/T_r", ("any", "any")
REC, AUTH = "recommender-pause-effect", "auth-freeze-effect"
WEBUI = "log:webui:d4d75ec135e6"
RATES = ("1", "10")
DASH = "—"
R1_PLACEMENT = "f7f5c04a6422394d2fab11b97d8ef974643afec69b37688dc359f42e7a64e8de"   # research/placement/test-ts-placement/placement-rep3r1.json
COUNTED = ("TS5-V1", "TS5-V10", "TS5-S", "TS5-T1", "TS5-T10", "TS5-C")
ORDER = ("TS5-V1", "TS5-V10", "TS5-S", "TS5-T1", "TS5-T10", "TS5-L", "TS5-C")
ROLE = {"TS5-L": "check, not counted (true by construction if no request in the window touches recommender)"}
INPUTS = ("scored", "placement", "transfer", "transfer_own")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p):
    return json.loads(Path(p).read_text())


def rec_verdict(R):
    """The REC SET6 verdict dict of a rate, or None."""
    v = [x for x in R.get("verdicts") or [] if x["rule"].get("class") == REC and x["rule"].get("set") == SET6]
    return v[0] if len(v) == 1 else None


def ts5_v(S, rk):
    v = rec_verdict((S["rates"].get(rk) or {}))
    got = None if v is None else v["verdict"]
    n = {"rate": rk, "verdict": got if got is not None else DASH, "gE": None if v is None else v.get("gE"), "improved": None if v is None else v.get("improved")}
    return {"PASS": True, "FAIL": False}.get(got), n


def ts5_s(P):
    sets = {}
    for rk in RATES:
        R = (P.get("rates") or {}).get(rk) or {}
        cell = next((c for c in R.get("grid") or [] if (c.get("maxEffort"), c.get("maxRuntime")) == CELL), None)
        pt = None if cell is None else (cell.get("points") or {}).get(POINT)
        sets[rk] = pt["set"] if pt is not None and isinstance(pt.get("set"), list) else None
    if any(s is None for s in sets.values()):
        return None, {"sets": sets, "why": "the @6/T_r point (or its set) is absent at a rate"}
    return all(WEBUI in s for s in sets.values()), {"sets": sets}


def transfer_rates(T, placement_sha):
    t = [x for x in T["transfers"] if x.get("placementSha256") == placement_sha]
    if len(t) != 1:
        raise SystemExit("refusing: transfer file holds %d transfers of placement %s..., not 1" % (len(t), placement_sha[:8]))
    return t[0]["rates"], t[0].get("members")


def ts5_t(T, rk, want_all):
    rates, members = transfer_rates(T, R1_PLACEMENT)
    v = rec_verdict(rates.get(rk) or {})
    n = {"rate": rk, "members": (members or {}).get(rk), "verdict": DASH if v is None else v["verdict"],
         "improved": None if v is None else v.get("improved"), "episodesInPool": None if v is None else v.get("episodesInPool"),
         "absentFromScoringGroundSet": None if v is None else v.get("absentFromScoringGroundSet")}
    if v is None or v["verdict"] not in ("PASS", "FAIL") or v.get("improved") is None or v.get("episodesInPool") != 2:
        return None, n
    return (v["improved"] == 2) if want_all else (v["improved"] <= 1), n


def episodes(S, cls):
    return [dict(e, rate=rk) for rk in RATES for e in (S["rates"].get(rk) or {}).get("episodes") or [] if e.get("class") == cls]


def ts5_l(S):
    rec = episodes(S, REC)
    miss = sum(1 for e in rec if e["ledger"]["ttd"] is None)
    n = {"ledgerMissed": miss, "recEpisodes": len(rec)}
    return (None if len(rec) < 4 else miss == len(rec)), n


def ts5_c(S):
    au = episodes(S, AUTH)
    det = sum(1 for e in au if e["ledger"]["ttd"] is not None)
    n = {"ledgerDetected": det, "authEpisodes": len(au)}
    return (None if len(au) < 4 else det == len(au)), n


def consistency(S, T_own):
    rates, _ = transfer_rates(T_own, S["inputs"]["placementSha256"])
    bad = []
    for rk in sorted(S["rates"], key=float):
        ref, R = S["rates"][rk], rates.get(rk) or {}
        want = [(v["rule"].get("class"), v.get("improved"), v.get("gE"), v["verdict"]) for v in ref.get("verdicts") or [] if v["rule"].get("set") == SET6]
        got = [(v["rule"].get("class"), v.get("improved"), v.get("gE"), v["verdict"]) for v in R.get("verdicts") or []]
        if not want or got != want:
            bad.append([rk, "verdicts", got, want])
        ea, eb = R.get("episodes") or [], ref.get("episodes") or []
        if len(ea) != len(eb):
            bad.append([rk, "episode count", len(ea), len(eb)])
        for a, b in zip(ea, eb):
            if (a["episode"], a["ledger"], a["sets"].get(SET6)) != (b["episode"], b["ledger"], b["sets"].get(SET6)):
                bad.append([rk, "episode", a["episode"], b["episode"]])
    return bad


def score(paths):
    S, P, T, T_own = (load(paths[k]) for k in INPUTS)
    for name, X in (("transfer", T), ("transfer_own", T_own)):
        if X.get("readoutSha256") != S["inputs"]["readoutSha256"] or X.get("readout") != S["inputs"]["readout"]:
            raise SystemExit("refusing: %s readout %s (%s) is not the scorer's inputs.readout %s (%s)" % (
                name, X.get("readout"), X.get("readoutSha256"), S["inputs"]["readout"], S["inputs"]["readoutSha256"]))
    if [x.get("placementSha256") for x in T["transfers"]] != [R1_PLACEMENT]:
        raise SystemExit("refusing: the transfer file does not hold exactly R1's placement (f7f5c04a...)")
    if [x.get("placementSha256") for x in T_own["transfers"]] != [S["inputs"]["placementSha256"]] or sha(paths["placement"]) != S["inputs"]["placementSha256"]:
        raise SystemExit("refusing: the own transfer, the placement file and the scorer do not name one placement")
    res = {"TS5-V1": ts5_v(S, "1"), "TS5-V10": ts5_v(S, "10"), "TS5-S": ts5_s(P)}
    bad = consistency(S, T_own)
    for i, rk, want_all in (("TS5-T1", "1", True), ("TS5-T10", "10", False)):
        ok, n = ts5_t(T, rk, want_all)
        res[i] = (None, dict(n, consistencyFailed=bad)) if bad else (ok, n)
    res["TS5-L"], res["TS5-C"] = ts5_l(S), ts5_c(S)
    inputs = {(str(Path(p).resolve().relative_to(REPO)) if Path(p).resolve().is_relative_to(REPO) else str(p)): sha(p) for p in paths.values()}
    return res, {"consistencyCheck": "pass" if not bad else "fail", "consistencyMismatches": bad}, inputs


def rows_of(res):
    return [{"id": i, "result": DASH if res[i][0] is None else ("hit" if res[i][0] else "miss"), "counted": i in COUNTED,
             "role": ROLE.get(i, "counted prediction"), "numbers": res[i][1]} for i in ORDER]


def write(out, rows, extra, inputs):
    oj, om = Path(str(out) + ".json"), Path(str(out) + ".md")
    if oj.exists() or om.exists():
        raise SystemExit("refusing: output exists (new evidence never overwrites old)")
    c = [r for r in rows if r["counted"]]
    tally = {"hit": sum(r["result"] == "hit" for r in c), "miss": sum(r["result"] == "miss" for r in c),
             "undecided": sum(r["result"] == DASH for r in c), "of": len(c)}
    rec = dict(extra, scope="instance", rows=rows, tally=tally, inputs=inputs,
               scriptSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    oj.write_text(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    om.write_text("# R5 predictions scored (instance)\n\nCounted: %(hit)d hit, %(miss)d miss, %(undecided)d undecided, of %(of)d.\n\n" % tally +
                  "| id | result | counted | numbers |\n|---|---|---|---|\n" +
                  "".join("| %s | %s | %s | `%s` |\n" % (r["id"], r["result"], "yes" if r["counted"] else "no (%s)" % r["role"],
                                                       json.dumps(r["numbers"], sort_keys=True, ensure_ascii=False)) for r in rows))
    print("wrote", oj, om)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="NEW output stem (writes <stem>.json and <stem>.md)")
    ap.add_argument("--run-stopped", action="store_true", help="R5 stopped (no read relaunch): every prediction —, no input read")
    for k in INPUTS:
        ap.add_argument("--" + k.replace("_", "-"))
    a = ap.parse_args(argv)
    if a.run_stopped:
        res = {i: (None, {"why": "the run stopped (declaration: undecided)"}) for i in ORDER}
        return write(a.out, rows_of(res), {"runStopped": True}, {})
    missing = [k for k in INPUTS if getattr(a, k) is None]
    if missing:
        ap.error("required unless --run-stopped: " + ", ".join("--" + k.replace("_", "-") for k in missing))
    res, extra, inputs = score({k: getattr(a, k) for k in INPUTS})
    return write(a.out, rows_of(res), dict(extra, runStopped=False), inputs)


if __name__ == "__main__":
    main()
