#!/usr/bin/env python3
"""Sensor representation, NEW rule, on retained evidence: vocab.json, vectors.jsonl, catches.jsonl, manifest.json.

    /usr/bin/python3 -B research/protocol/sensor_rep/run.py [population ...] [--out tmp/protocol] [--k 4] [--tau 0.05]
                                                          [--replay]

Writes a NEW directory `<out>/<UTC stamp>/` and refuses to overwrite one that exists. `--replay` also runs the old-rule
replay against MAP_TABLE.md and writes `replay.json` + `replay.md` beside the outputs.

Per population (one campaign, never pooled):
1. parse every cell into events (parsers/<sut>.py); group into streams;
2. hold length L = median fault hold (wall clock) of the valid fault cells; no-fault windows = tiles of length L of
   every valid no-fault cell (vectors.tiles), per posture; n_eff = number of tiles, stated with the number of cells;
3. vocabulary and thresholds per (population, posture) from those tiles (`vocab.json`);
4. G3: every no-fault tile scored against the other cells' tiles (leave-one-cell-out), k/n_eff per sensor;
5. every valid fault cell's hold window scored against the full baseline of its posture (`catches.jsonl`), each catch
   with its kinds, the window statistic, the baseline (median, threshold, n, nCells, basis), G3 k/n_eff and
   admissibility, outside/own (G2), the MAP family, and the stream metadata;
6. a per-(regime, family) summary (`manifest.json` -> summary) in the MAP_TABLE shape, admissible outside catches.
Engineering defaults: see catch.py (rule), vectors.py (windows), population.py (posture tables), events.py (metadata);
the ledger is collected in every posture (harness, posture-independent); channels a posture collects otherwise follow
the population's posture table; vectors.jsonl holds rows with count > 0 only (a collected channel's missing row is 0;
the cell's collected channels are listed in the manifest).
"""
import argparse
import datetime as dt
import hashlib
import json
import platform
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "sensor_rep"
    import sensor_rep  # noqa: F401

from sensor_rep import catch, population, replay, vectors  # noqa: E402
from sensor_rep.events import robust, sensor_id  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = population.REPO
FAMILY_CHANNEL = {"L": "log", "M": "metric", "S": "metric", "T": "span", "Tsel": "span", "C": "span", "Csel": "span"}


def collected_channels(cfg, cell):
    chans = {"ledger"}
    for fam, postures in cfg["collects"].items():
        if cell["posture"] in postures:
            chans.add(FAMILY_CHANNEL[fam])
    present = {k.split(":")[0] for k, v in cell["channels"].items() if v.get("present")}
    return chans & present


def hold_length(cells):
    hs = [c["fault"]["wall"][1] - c["fault"]["wall"][0] for c in cells if c["valid"] and c["fault"] and c["target"]]
    return statistics.median(hs) if hs else None


def pre_values(cell, w):
    pre = vectors.pre_window(cell, w["bounds"])
    return {k: vectors.select(s, pre) for k, s in cell["streams"].items() if catch.has_level(k[0], k[2])}


def run_population(name, k=catch.K, tau=catch.TAU, cells=None, vec_out=None):
    cfg = population.POPULATIONS[name]
    P = population.parser(cfg["sut"])
    if cells is None:
        cells = population.load(name)
    L = hold_length(cells)
    if L is None:
        raise SystemExit("%s: no valid fault cell, no hold length" % name)
    by_posture = defaultdict(list)
    for c in cells:
        if c["valid"] and c["target"] is None:
            by_posture[c["posture"]].append(c)
    bases, tile_stats = {}, {}
    for posture, nf in sorted(by_posture.items()):
        B = catch.Baseline(posture)
        for c in nf:
            chans = collected_channels(cfg, c)
            for w in vectors.tiles(c, L):
                st = {kk: v for kk, v in catch.window_stats(c["streams"], w, L).items() if kk[0] in chans}
                B.add(c["cell"], w["index"], chans, st)
                tile_stats[(c["cell"], w["index"])] = (w, st, chans)
                if vec_out is not None:
                    write_vectors(vec_out, name, c, w, chans)
        bases[posture] = B
    # ---- vocabulary
    vocab = {}
    for posture, B in bases.items():
        V = {}
        for key in sorted(B.keys()):
            hist = B.view(key)
            counts = [n for _, n, _ in hist]
            levels = [x for _, _, x in hist if x is not None]
            pres = [c for c, n, _ in hist if n > 0]
            m = None
            for _, _, _, rows in B.tiles:
                if key in rows and rows[key][2] is not None:
                    m = rows[key][2]
                    break
            e = {"windowsPresent": len(pres), "nEff": len(hist), "cellsPresent": len(set(pres)),
                 "nCells": len({c for c, _, _ in hist})}
            if len(hist) >= catch.MIN_BASELINE:
                cm, cmad = robust(counts)
                e["count"] = {"median": cm, "mad": cmad, "thr": max(k * 1.4826 * cmad, catch.COUNT_FLOOR)}
            if len(levels) >= catch.MIN_BASELINE:
                lm, lmad = robust(levels)
                e["level"] = {"median": lm, "mad": lmad,
                              "thr": max(k * 1.4826 * lmad, catch.level_floor(key[0], key[2], lm)), "n": len(levels)}
            if m is not None:
                e["meta"] = {kk: v for kk, v in m.items() if kk != "posture"}
            V[sensor_id(*key)] = e
        vocab[posture] = {"nEffWindows": {ch: len(B.windows(ch)) for ch in ("log", "span", "metric", "ledger")},
                          "nCells": len({t[0] for t in B.tiles}), "holdSeconds": L, "tokens": V}
    # ---- G3 (leave one cell out)
    g3 = {}
    for posture, B in bases.items():
        cells_p = {c["cell"]: c for c in by_posture[posture]}
        tl = [(cid, chans, st, pre_values(cells_p[cid], w))
              for (cid, i), (w, st, chans) in tile_stats.items() if cid in cells_p]
        g3[posture] = catch.g3_loo(B, tl, k=k, tau=tau, n_cells=vocab[posture]["nCells"])
    # ---- fault cells
    catches, episodes = [], []
    for c in cells:
        if not (c["valid"] and c["target"] and c["fault"]):
            continue
        B = bases.get(c["posture"])
        chans = collected_channels(cfg, c)
        w = vectors.fault_window(c)
        st = {kk: v for kk, v in catch.window_stats(c["streams"], w, L).items() if kk[0] in chans}
        if vec_out is not None:
            write_vectors(vec_out, name, c, w, chans)
        if B is None:
            episodes.append({"cell": c["cell"], "posture": c["posture"], "regime": c["regime"], "target": c["target"],
                             "noBaseline": True, "channels": sorted(chans), "fired": []})
            continue
        f = catch.new_fire(st, B, chans, pre_values=pre_values(c, w), k=k)
        fired = []
        for key, v in sorted(f.items()):
            ch, svc, tok = key
            s = c["streams"].get(key)
            m = s.meta if s is not None else (vocab[c["posture"]]["tokens"].get(sensor_id(*key), {}).get("meta") or {})
            gg = g3[c["posture"]].get(key)
            if gg is None:                      # token absent from every no-fault tile: fired in none of them
                n_ch = len(B.windows(ch))
                gg = {"k": 0, "nEff": n_ch, "nCells": vocab[c["posture"]]["nCells"],
                      "admissible": True if n_ch else None}
            fam = P.family(ch, m.get("collector"), c["posture"])
            row = {"population": name, "cell": c["cell"], "posture": c["posture"], "regime": c["regime"],
                   "target": c["target"], "window": {"kind": "fault", "start": w["bounds"]["wall"][0],
                                                     "end": w["bounds"]["wall"][1], "holdSeconds": L},
                   "sensor": sensor_id(*key), "channel": ch, "service": svc, "token": tok, "family": fam,
                   "kinds": v["kinds"], "x": v["x"], "baseline": v["baseline"],
                   "g3": None if gg is None else {"k": gg["k"], "nEff": gg["nEff"], "nCells": gg["nCells"]},
                   "admissible": None if gg is None else gg["admissible"],
                   "outside": svc != c["target"], "meta": {kk: vv for kk, vv in m.items() if kk != "posture"}}
            catches.append(row)
            fired.append(row)
        episodes.append({"cell": c["cell"], "posture": c["posture"], "regime": c["regime"], "target": c["target"],
                         "channels": sorted(chans), "fired": fired})
    summary = summarise(cfg, episodes)
    return {"population": name, "sut": cfg["sut"], "holdSeconds": L, "vocab": vocab, "g3": g3, "catches": catches,
            "summary": summary, "cells": cells,
            "nEff": {p: {"windows": v["nEffWindows"], "cells": v["nCells"]} for p, v in vocab.items()}}


def summarise(cfg, episodes):
    """Per regime: ledger k/n (admissible ledger catches) and per family outside k/n (own k), admissible catches only,
    over the episodes whose posture collects the family. Inadmissible / no-G3 catches are counted beside."""
    out = {}
    for regime in sorted({e["regime"] for e in episodes}):
        eps = [e for e in episodes if e["regime"] == regime]
        row = {"n": len(eps), "families": {}}
        led = [e for e in eps if not e.get("noBaseline")]
        row["ledger"] = [sum(1 for e in led if any(r["channel"] == "ledger" and r["admissible"] for r in e["fired"])),
                         len(led)]
        row["ledgerAnyG3"] = sum(1 for e in led if any(r["channel"] == "ledger" for r in e["fired"]))
        for fam, postures in cfg["collects"].items():
            fe = [e for e in led if e["posture"] in postures]
            if not fe:
                continue
            sel = lambda e, outside: [r for r in e["fired"] if r["family"] == fam and r["outside"] == outside]
            row["families"][fam] = {
                "n": len(fe),
                "outside": sum(1 for e in fe if any(r["admissible"] for r in sel(e, True))),
                "own": sum(1 for e in fe if any(r["admissible"] for r in sel(e, False))),
                "outsideIgnoringG3": sum(1 for e in fe if sel(e, True)),
                "kinds": dict(Counter(kd for e in fe for r in sel(e, True) if r["admissible"] for kd in r["kinds"]))}
        out[regime.replace("-effect", "")] = row
    return out


def write_vectors(fh, name, cell, w, chans):
    """Raw (unnormalised) window vectors of the collected channels, count > 0 rows only."""
    for r in vectors.vector_rows(cell, cell["streams"], w):
        if r["count"] == 0 or r["channel"] not in chans:
            continue
        r["population"], r["posture"] = name, cell["posture"]
        fh.write(json.dumps(r, sort_keys=True) + "\n")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(HERE),
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def fmt_summary(name, summary, fams=("L", "M", "S", "Tsel", "T")):
    lines = []
    for fault, r in summary.items():
        cells = []
        for f in fams:
            v = r["families"].get(f)
            cells.append("—" if not v else "%d/%d%s" % (v["outside"], v["n"], " (own %d)" % v["own"] if v["own"] else ""))
        lines.append("| %s | %s | %d | %d/%d | %s |" % (name, fault, r["n"], r["ledger"][0], r["ledger"][1], " | ".join(cells)))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("populations", nargs="*")
    ap.add_argument("--out", default=str(REPO / "tmp" / "protocol"))
    ap.add_argument("--k", type=float, default=catch.K)
    ap.add_argument("--tau", type=float, default=catch.TAU)
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args(argv)
    population.register_late()
    pops = a.populations or [p for p in population.POPULATIONS if (REPO / population.POPULATIONS[p]["x"]).exists()]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(a.out) / stamp
    if out.exists():
        sys.exit("refusing to overwrite %s" % out)
    out.mkdir(parents=True)
    vocab_all, summaries, neff, inputs, rep_results, stats = {}, {}, {}, [], [], {}
    with open(out / "vectors.jsonl", "w") as vf, open(out / "catches.jsonl", "w") as cf:
        for p in pops:
            print("population", p, file=sys.stderr)
            cells = population.load(p)
            res = run_population(p, a.k, a.tau, cells=cells, vec_out=vf)
            for r in res["catches"]:
                cf.write(json.dumps(r, sort_keys=True) + "\n")
            vocab_all[p] = {"holdSeconds": res["holdSeconds"], "postures": res["vocab"],
                            "g3": {post: {sensor_id(*kk): v for kk, v in G.items()} for post, G in res["g3"].items()}}
            summaries[p] = res["summary"]
            neff[p] = res["nEff"]
            stats[p] = {"cells": len(cells), "validCells": sum(1 for c in cells if c["valid"]),
                        "knownPeriodic": sorted({x for c in cells for x in c["stats"].get("knownPeriodic", [])}),
                        "parser": dict(sum((Counter({kk: v for kk, v in c["stats"].items() if isinstance(v, int)})
                                            for c in cells), Counter())),
                        "channelsPerCell": {c["cell"]: sorted(collected_channels(population.POPULATIONS[p], c))
                                            for c in cells}}
            for c in cells:
                for ch in c["channels"].values():
                    f = Path(REPO / c["cell"] / ch["file"]) if ch.get("file") else None
                    if f is not None and f.exists():
                        inputs.append({"population": p, "path": str(f.relative_to(REPO)), "bytes": f.stat().st_size,
                                       "sha256": sha256(f)})
            if a.replay:
                if p in replay.ADAPTER_OUT:      # the oracle used the adapter's templating: re-parse with it
                    del cells
                    r = replay.replay_population(p, parse_kw={"templating": "symptoms"})
                    if replay.ADAPTER_OUT[p].exists():
                        r["adapterCheck"] = replay.compare_adapter(r, replay.ADAPTER_OUT[p])
                    rep_results.append(r)
                else:
                    rep_results.append(replay.replay_population(p, cells=cells))
                    del cells
            else:
                del cells
    (out / "vocab.json").write_text(json.dumps(vocab_all, indent=1, sort_keys=True, default=str))
    md = ["| population | fault | n | ledger | L | M | S | Tsel | T |", "|---|---|---|---|---|---|---|---|---|"]
    for p in pops:
        md += fmt_summary(p, summaries[p])
    (out / "summary.md").write_text("\n".join(md) + "\n")
    scripts = sorted(HERE.rglob("*.py"))
    reused = [REPO / "research" / x for x in ("s4-conjunction/symptoms.py", "lmt-pilot/lmt_detect.py",
                                               "sprint-draft2/detection.py", "otel-offpath/adapter.py",
                                               "visibility-map/visibility.py", "project-map/project_map.json")]
    manifest = {"generatedAt": stamp, "argv": sys.argv[1:], "python": platform.python_version(),
                "frameworkCommit": git_commit(), "rule": {"K": a.k, "tau": a.tau, "minBaseline": catch.MIN_BASELINE,
                                                          "countFloor": catch.COUNT_FLOOR, "latFloorS": catch.LAT_FLOOR_S,
                                                          "ledgerFloorMs": catch.LEDGER_FLOOR_MS},
                "scripts": {str(s.relative_to(REPO)): sha256(s) for s in scripts},
                "reused": {str(s.relative_to(REPO)): sha256(s) for s in reused if s.exists()},
                "nEff": neff, "summary": summaries, "populations": stats, "inputs": inputs}
    if a.replay:
        cmp_ = replay.compare(rep_results)
        (out / "replay.json").write_text(json.dumps({"results": rep_results, "agree": cmp_["agree"], "total": cmp_["total"],
                                                     "deltas": cmp_["deltas"]}, indent=1, default=str))
        (out / "replay.md").write_text("\n".join(cmp_["table"]) + "\n\nagreement: %d/%d\n" % (cmp_["agree"], cmp_["total"]))
        manifest["replay"] = {"agree": cmp_["agree"], "total": cmp_["total"], "deltas": cmp_["deltas"],
                              "episodesVsVisibilityJson": replay.compare_episodes(rep_results),
                              "episodesVsAdapterOutput": {r["population"]: r["adapterCheck"] for r in rep_results
                                                          if "adapterCheck" in r}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True, default=str))
    print("\n".join(md))
    if a.replay:
        print("replay agreement %d/%d" % (manifest["replay"]["agree"], manifest["replay"]["total"]))
    print("wrote", out)


if __name__ == "__main__":
    main()
