#!/usr/bin/env python3
"""Replay oracle: the new representation at the OLD rules must reproduce `research/visibility-map/MAP_TABLE.md`.

    /usr/bin/python3 -B research/protocol/sensor_rep/replay.py [population ...] [--out tmp/protocol]

For each population: parse the retained evidence into events (parsers/<sut>.py), place the oracle's windows (fault
hold; no-fault pseudo window at the population's median fault offsets; the cell's own pre-window as baseline), fire
sensors with `catch.old_fire` / `catch.old_ledger`, gate by G3 per family over the family's posture set (where the
oracle did), and aggregate exactly as visibility.build_rows / map_table.py do: an episode is caught by a family when one
admissible sensor of a service other than the target fires (`outside`); `own` = the target's admissible sensors.
Then compare cell by cell with MAP_TABLE.md (n, ledger, L, M, S, Tsel, T) and print a per-row delta table.
`class` and `caught by construction` columns are not replayed (they are derived from the replayed columns plus
flags outside this module's scope); that is stated in the output, not hidden.

Engineering defaults (recorded): episodes = valid fault cells (cell-terminal candidateCellValid / validation status);
G3 tau = 0.05, inadmissible iff k > tau·n (lmt_detect.py:151); the comparison treats `—` as equal only to `—`.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "sensor_rep"
    import sensor_rep  # noqa: F401

from sensor_rep import catch, population, vectors  # noqa: E402

MAP_TABLE = population.REPO / "research" / "visibility-map" / "MAP_TABLE.md"
FAM = ("L", "M", "S", "Tsel", "T")


def parse_map_table(path=MAP_TABLE):
    rows = {}
    for line in Path(path).read_text().splitlines():
        if not line.startswith("| ") or line.startswith("| population") or line.startswith("|---"):
            continue
        c = [x.strip() for x in line.strip("|").split("|")]
        pop, fault = c[0], c[1].split(" (")[0]
        rows[(pop, fault)] = {"n": c[2], "ledger": c[3], "L": c[4], "M": c[5], "S": c[6], "Tsel": c[7], "T": c[8],
                              "class": c[9], "bc": c[10]}
    return rows


def windows_old(cells, P):
    """(window, pre) per cell under the oracle's placement."""
    offs = P.pseudo_offsets(cells)
    out = {}
    for c in cells:
        w = vectors.fault_window(c) if c["fault"] is not None and c["target"] else vectors.pseudo_window(c, offs)
        out[c["cell"]] = (w, vectors.pre_window(c, w["bounds"]))
    return out, offs


def replay_population(name, cells=None, parse_kw=None):
    cfg = population.POPULATIONS[name]
    P = population.parser(cfg["sut"])
    if cells is None:
        cells = population.load(name, parse_kw=parse_kw)
    wins, offs = windows_old(cells, P)
    fired, ledger = {}, {}
    extra = getattr(P, "old_extra_fire", None)        # per-SUT oracle extras (TeaStore log rate:high)
    for c in cells:
        if not c["valid"]:
            continue
        w, pre = wins[c["cell"]]
        f = catch.old_fire(c, c["streams"], w, pre)
        fired[c["cell"]] = f
        if c["target"]:
            ledger[c["cell"]] = catch.old_ledger(c["streams"], w, pre)
    if extra is not None:
        extra(cells, wins, fired)
    collects = cfg["collects"]

    def fam_of(sensor, posture, cell):
        ch, svc, name_ = sensor
        coll = cell["streams"].get((ch, svc, name_))
        collector = coll.meta["collector"] if coll is not None else None
        if collector is None:                         # span op whose only stream is `<op>:error`
            s2 = cell["streams"].get((ch, svc, name_ + ":error"))
            collector = s2.meta["collector"] if s2 is not None else None
        return P.family(ch, collector, posture)

    by_cell = {c["cell"]: c for c in cells}
    fam_fired = {}
    for cid, f in fired.items():
        c = by_cell[cid]
        ff = defaultdict(set)
        for sensor in f:
            fam = fam_of(sensor, c["posture"], c)
            if fam is not None:
                ff[fam].add(sensor)
        fam_fired[cid] = ff
    inadm, g3 = {}, {}
    for fam, postures in collects.items():
        nf = [c for c in cells if c["valid"] and c["target"] is None and c["posture"] in postures]
        bad, counts, n = catch.g3_inadmissible([fam_fired[c["cell"]].get(fam, set()) for c in nf])
        inadm[fam] = bad if fam in cfg["g3Families"] else set()
        g3[fam] = {"noFaultWindows": n, "inadmissible": len(bad), "applied": fam in cfg["g3Families"]}
    rows = {}
    for regime in sorted({c["regime"] for c in cells if c["target"]}):
        eps = [c for c in cells if c["valid"] and c["target"] and c["regime"] == regime]
        if not eps:
            continue
        led = [ledger[c["cell"]] for c in eps if ledger.get(c["cell"]) is not None]
        row = {"n": len(eps), "ledger": [sum(1 for r in led if r["shows"]), len(led)] if led else None,
               "ledgerUnknown": len(eps) - len(led), "target": eps[0]["target"], "faultKind": eps[0]["faultKind"],
               "families": {}, "episodes": []}
        for fam, postures in collects.items():
            fe = [c for c in eps if c["posture"] in postures]
            if not fe:
                continue
            out_k = own_k = 0
            for c in fe:
                s = fam_fired[c["cell"]].get(fam, set()) - inadm[fam]
                out_k += any(x[1] != c["target"] for x in s)
                own_k += any(x[1] == c["target"] for x in s)
            row["families"][fam] = {"n": len(fe), "outside": out_k, "own": own_k}
        for c in eps:
            fams = {}
            for fam, postures in collects.items():
                if c["posture"] not in postures:
                    continue
                s = fam_fired[c["cell"]].get(fam, set()) - inadm[fam]
                fams[fam] = {"outside": sorted("%s:%s:%s" % ((fam,) + x[1:]) for x in s if x[1] != c["target"]),
                             "own": sorted("%s:%s:%s" % ((fam,) + x[1:]) for x in s if x[1] == c["target"])}
            row["episodes"].append({"cell": c["cell"], "posture": c["posture"], "ledger": ledger.get(c["cell"]),
                                    "families": fams})
        rows[regime.replace("-effect", "")] = row
    return {"population": name, "cells": len(cells), "validCells": sum(1 for c in cells if c["valid"]),
            "pseudoOffsets": offs, "g3": g3, "rows": rows}


def fmt_fam(v):
    if not v or not v["n"]:
        return "—"
    return "%d/%d%s" % (v["outside"], v["n"], " (own %d)" % v["own"] if v["own"] else "")


def fmt_row(r):
    return {"n": str(r["n"]), "ledger": "%d/%d" % tuple(r["ledger"]) if r["ledger"] else "— (no ledger)",
            **{f: fmt_fam(r["families"].get(f)) for f in FAM}}


def compare(results, table=None):
    table = table or parse_map_table()
    lines = ["| population | fault | column | MAP_TABLE | replay | agree (cause if not) |", "|---|---|---|---|---|---|"]
    agree = total = 0
    deltas = []
    for res in results:            # reverse direction: a MAP_TABLE row of a replayed population the replay lacks
        pop = res["population"]
        for (tp, tf) in table:
            if tp == pop and tf not in res["rows"]:
                deltas.append((pop, tf, "row", "present", "absent", "UNEXPLAINED: replay produced no row"))
                total += 1
    for res in results:
        pop = res["population"]
        for fault, r in res["rows"].items():
            mine = fmt_row(r)
            ref = table.get((pop, fault))
            if ref is None:
                deltas.append((pop, fault, "row", "absent", "present"))
                continue
            for col in ("n", "ledger") + FAM:
                total += 1
                ok = mine[col] == ref[col]
                agree += ok
                cause = CAUSES.get((pop, col), "")
                if not ok:
                    deltas.append((pop, fault, col, ref[col], mine[col], cause or "UNEXPLAINED"))
                lines.append("| %s | %s | %s | %s | %s | %s |" % (pop, fault, col, ref[col], mine[col],
                                                                  "yes" if ok else "**no**: " + (cause or "UNEXPLAINED")))
    return {"agree": agree, "total": total, "deltas": deltas, "table": lines}


VISIBILITY = population.REPO / "research" / "visibility-map" / "visibility.json"
ADAPTER_OUT = {"otel-v3": population.REPO / "research" / "otel-offpath" / "out" / "adapter-otel-v3-evidence-20261002.json"}
CAUSES = {   # (population, column) -> why the MAP_TABLE cell cannot match; printed beside each delta. A cause here
             # explains that the cell has no oracle; it is not evidence about the replayed value (the adapter check is)
    ("otel-v3", "L"): "MAP_TABLE has no OTel detection (visibility.py: '— (no detection adapter for OTel Demo)'); "
                      "the replay value is checked against research/otel-offpath/adapter.py's committed output instead",
    ("otel-v3", "M"): "as L",
    ("otel-v3", "T"): "as L",
}


def compare_adapter(res, path):
    """Episode-level check of an OTel replay (run with templating='symptoms') against adapter.py's committed output:
    admissible outside/own sensor sets per family (L, M, T) and the ledger verdict."""
    d = json.loads(Path(path).read_text())
    ref = {e["cell"]: e for e in d["episodes"]}
    kinds = {"log", "metric", "latency", "error", "missing_expected"}

    def strip(xs):          # adapter ids carry `=<kind>` (adapter.sensors_of); the sensor is the part before it
        out = []
        for x in xs:
            head, _, tail = x.rpartition("=")
            out.append(head if head and set(tail.split("+")) <= kinds else x)
        return sorted(out)
    n = same = 0
    diffs = []
    for row in res["rows"].values():
        for e in row["episodes"]:
            key = "/".join(e["cell"].split("/")[-2:])
            r = ref.get(key)
            n += 1
            if r is None:
                diffs.append((key, "absent"))
                continue
            bad = []
            for fam, v in e["families"].items():
                rv = r["families"].get(fam) or {"outside": [], "own": []}
                if strip(rv["outside"]) != v["outside"] or strip(rv["own"]) != v["own"]:
                    bad.append((fam, len(rv["outside"]), len(v["outside"]), len(rv["own"]), len(v["own"])))
            rl, ml = r.get("ledger"), e["ledger"]
            if (rl is None) != (ml is None) or (rl and rl["shows"] != ml["shows"]):
                bad.append("ledger")
            if bad:
                diffs.append((key, bad))
            else:
                same += 1
    return {"episodes": n, "identical": same, "diffs": diffs[:20], "oracle": population.common.rel(path)}


def compare_episodes(results, path=VISIBILITY):
    """Episode-level check, stronger than the table: per valid fault cell, the admissible outside and own sensor sets
    per family and the ledger verdict must equal visibility.json's (C/Csel/Mm are not MAP_TABLE columns: skipped)."""
    if not Path(path).exists():
        return None
    vis = json.loads(Path(path).read_text())["populations"]
    out = {}
    for res in results:
        V = vis.get(res["population"])
        if V is not None and not any(e.get("families") for e in V["episodes"]):
            V = None                                   # ledger-only oracle (OTel): nothing to compare per family
        if V is None:
            out[res["population"]] = None
            continue
        ref = {e["cell"]: e for e in V["episodes"]}
        n = same = 0
        diffs = []
        for fault, row in res["rows"].items():
            for e in row["episodes"]:
                r = next((x for k, x in ref.items() if e["cell"].endswith(k)), None)
                n += 1
                if r is None:
                    diffs.append((e["cell"], "absent from visibility.json"))
                    continue
                bad = []
                for fam, v in e["families"].items():
                    rv = r["families"].get(fam)
                    if rv is None or sorted(rv["outside"]) != v["outside"] or sorted(rv["own"]) != v["own"]:
                        bad.append(fam)
                if set(r["families"]) - {"C", "Csel", "Mm"} != set(e["families"]):
                    bad.append("family-set")
                rl, ml = r.get("ledger"), e["ledger"]
                if (rl is None) != (ml is None) or (rl is not None and (rl["shows"] != ml["shows"] or
                                                                        rl["inWindow"] != ml["inWindow"] or
                                                                        rl["failedInWindow"] != ml["failedInWindow"])):
                    bad.append("ledger")
                if bad:
                    diffs.append((e["cell"], bad))
                else:
                    same += 1
        out[res["population"]] = {"episodes": n, "identical": same, "diffs": diffs[:20]}
    return out


def main(argv):
    population.register_late()
    pops = [a for a in argv if not a.startswith("--")] or [p for p in population.POPULATIONS
                                                           if (population.REPO / population.POPULATIONS[p]["x"]).exists()]
    results, adapter_checks = [], {}
    for p in pops:
        print("replaying", p, file=sys.stderr)
        kw = {"templating": "symptoms"} if p in ADAPTER_OUT else None
        r = replay_population(p, parse_kw=kw)
        if p in ADAPTER_OUT and ADAPTER_OUT[p].exists():
            r["adapterCheck"] = adapter_checks[p] = compare_adapter(r, ADAPTER_OUT[p])
        results.append(r)
    cmp_ = compare(results)
    print("\n".join(cmp_["table"]))
    print("\nagreement: %d/%d (population x fault x column cells)" % (cmp_["agree"], cmp_["total"]))
    for d in cmp_["deltas"]:
        print("DELTA", d)
    ep = compare_episodes(results)
    for p, v in (ep or {}).items():
        print("episode-level vs visibility.json: %s %s" % (p, "—" if v is None else "%d/%d identical (sensor sets per "
              "family + ledger verdict); diffs %s" % (v["identical"], v["episodes"], v["diffs"][:5])))
    cmp_["episodes"] = ep
    for p, v in adapter_checks.items():
        print("episode-level vs %s: %s %d/%d identical; diffs %s" % (v["oracle"], p, v["identical"], v["episodes"],
                                                                    v["diffs"][:5]))
    cmp_["adapter"] = adapter_checks
    return results, cmp_


if __name__ == "__main__":
    main(sys.argv[1:])
