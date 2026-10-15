#!/usr/bin/env python3
"""S4 relevance baseline: AMENDMENT_1.md section 4, computed once over the frozen symptom bags.

    /usr/bin/python3 research/s4-conjunction/relevance.py --self-check
    /usr/bin/python3 research/s4-conjunction/relevance.py tmp/s4-symptoms/<stamp> [--out tmp/s4-relevance]

Reads bags.jsonl, vocab.json, summary.json and manifest.json of one symptoms.py run, refuses to proceed
unless the manifest's script SHA-256 equals the committed research/s4-conjunction/symptoms.py, and writes
relevance.json and tables.md to a NEW UTC-stamped directory. Every table is per generation (never pooled
across generations, S-G), names its denominator, carries 0/n (never dropped) and prints exclusions.

Order of computation (frozen): C1 bridge (P1) first; if it fails, S-B stops the run and nothing else
is written. Then per-symbol tables, per-sensor tables, pairs (triples when allowed), mutual information,
R(p) with G1-G6, predictions, true-by-construction flags. Readings of the amendment's text where it is
ambiguous are listed in READINGS and written into the output, so that the run is reproducible as-is.
"""
import argparse
import datetime as dt
import hashlib
import itertools
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYMPTOMS = HERE / "symptoms.py"
TAU_DEFAULT = 0.05
TRIPLE_LIMIT = 200          # section 4: triples only when <= 200 sensors fire in >= 1 episode of the generation
EXACT_SETS = 20             # DEFINITIONS section 8: exact optimum by union enumeration up to 20 distinct R sets
MAX_K = 8                   # budget range reported for max f_all / f_any
APW = "a-p-w"
SPAN_POSTURES = ("full", "kieker-native")   # postures that export spans: Hotel/TeaStore `full`, G-old's only posture
NON_SYMPTOMS = ("present", "?", "missing")  # symbols that never make a sensor fire (section 4, "Sensor firing")

READINGS = [
    "R1 `log:level:*`, `log:template:novel` and `log:exception:*` belong to no sensor of the section 2 universe "
    "(one log sensor per template; a throwable record has no template). They are in the symbol tables only, "
    "never in the sensor tables, the combinations or R(p). The count of fault rows whose only log symptom is "
    "an exception class is printed so the reading's cost is visible.",
    "R2 A template sensor `log:<svc>:<tid>` fires iff its `log:template:<tid>` symbol is in the row and G3-admissible "
    "(vocab.json, tau = 5 %) or its `log:rate:<tid>:high` symbol is in the row (calibrated on the same no-fault "
    "windows by construction; it has no false-alarm column in vocab.json, so G3 is not applied to it).",
    "R3 G3 for metric symbols is per (service, symbol), as section 4 says ('log templates and metric symbols'), "
    "not per sensor as DEFINITIONS G3 said.",
    "R4 G-old's only posture `kieker-native` exports spans and is treated as its `full`. The span-symbol, "
    "combination and R(p) populations of every generation are the valid fault cells of that posture.",
    "R5 Combinations (pairs, triples) are computed on the span-exporting episodes only, so that sensors of all "
    "three modalities live in one population; log/metric-only pairs on the other postures are not computed.",
    "R6 The false-alarm denominator of a span symbol or span sensor is the no-fault pseudo rows of the "
    "span-exporting posture (24 per posture on H-B), because span symbols are silent under the other postures "
    "by construction; log and metric symbols use every posture except a-p-w, per posture and pooled.",
    "R7 P1 (C1 bridge) is checked on the sprint's population: for T-new that includes the a-p-w cells "
    "(11/11, 0/9, 0/12 are only reachable with them). A15 governs the section 4 tables, not the identity check.",
    "R8 Mutual information: the no-fault class is every pseudo row of the symbol's population (G-old: all "
    "11 per baseline run, 330 rows), as section 4 says 'one no-fault class made of the pseudo rows'. The class "
    "sizes are printed beside every value.",
    "R9 G-old fault-row admissibility uses the vocab key `<svc>/window:<regime>` (the pseudo rows of the fault "
    "family's own D_f); Hotel/TeaStore use `<svc>/window`. A pseudo row's class is its own `pseudoFor` family.",
    "R10 Amendment P4 and DEFINITIONS P2-P4 are evaluated on the span-exporting posture episodes (24 on H-B); "
    "the other postures are shown beside them. Amendment P5 reads the `cell` row, as its text says, over all "
    "valid cells including a-p-w (its denominators 11 and 9 require them). Amendment P6 counts a run when some "
    "non-target service row carries a metric spike and that same row carries no `log:level:*`.",
    "R11 Optimum f_all / f_any per budget k: unit sensor cost, no activation dependencies (the op-level trace "
    "ids have no catalogue closure); exact over unions of distinct R sets when <= 20 sets, else greedy, labelled. "
    "Level sets over the catalogue domain are `--` (no domain is defined for op-level trace ids).",
]

TRUE_BY_CONSTRUCTION = {
    "TBC1": "a paused service's `metric:cpu:spike_down`/`plateau_down` and its `span:<op>:missing_expected` (amendment 9)",
    "TBC2": "a crashed service's restart lines are novel templates; its exception classes appear in its callers (amendment 9)",
    "TBC3": "span symbols are silent under `none` / `sample-zero` (DEFINITIONS 11, amendment 9)",
    "TBC4": "a template in every no-fault cell is inadmissible under G3 regardless of the fault (amendment 9)",
    "TBC5": "on T-new/T-16 `log:template:novel`, `log:rate:*:high` and every log false-alarm count of 0 are true by "
            "construction: the no-fault cells contain 0 application records (amendment 7, 9)",
    "TBC6": "C1's agreement with the sprint is a check, not a finding (DEFINITIONS 11)",
    "TBC7": "under R+ (G2 off) a paused target's CPU event and a crash target's restart lines (DEFINITIONS 11)",
    "TBC8": "`log:level:warn` on TeaStore crash cells is the sprint's ServiceLoadBalancer count (amendment 9)",
    "TBC9": "on TeaStore, log4j records carry no timestamp and enter the `cell` row only, so every log4j-only "
            "template is 0/n in a `fault`-row table by construction (amendment 3.6)",
}


# --------------------------------------------------------------------------- loading and provenance

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def committed_sha(path):
    """SHA-256 of the file as committed at HEAD (None when git is unavailable)."""
    try:
        rel = Path(path).resolve().relative_to(Path(subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=str(HERE), check=True).stdout.strip()))
        blob = subprocess.run(["git", "show", "HEAD:" + rel.as_posix()], capture_output=True, cwd=str(HERE), check=True).stdout
        return hashlib.sha256(blob).hexdigest()
    except Exception:  # noqa: BLE001
        return None


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(HERE), check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return None


def load_bags(bag_dir, symptoms_path=SYMPTOMS, require_commit=True):
    bag_dir = Path(bag_dir)
    manifest = json.loads((bag_dir / "manifest.json").read_text())
    on_disk = sha256_file(symptoms_path)
    if manifest.get("script") != on_disk:
        raise SystemExit("refusing: manifest script sha %s != %s (%s)" % (manifest.get("script"), on_disk, symptoms_path))
    committed = committed_sha(symptoms_path) if require_commit else None
    if require_commit and committed is not None and committed != on_disk:
        raise SystemExit("refusing: %s differs from its committed version (%s != %s)" % (symptoms_path, on_disk, committed))
    rows = [json.loads(l) for l in (bag_dir / "bags.jsonl").read_text().splitlines() if l.strip()]
    vocab = json.loads((bag_dir / "vocab.json").read_text())
    summary = json.loads((bag_dir / "summary.json").read_text())
    return rows, vocab, summary, manifest, {"scriptSha": on_disk, "committedSha": committed}


# --------------------------------------------------------------------------- populations

def is_no_fault(r):
    return r["regime"].startswith(("no-fault", "baseline"))


def sensor_of(sym, service):
    """Symbol -> (sensor id, is_symptom). is_symptom False for present / ? / missing (they never fire a sensor).
    Returns (None, False) for symbols that belong to no sensor (reading R1)."""
    p = sym.split(":")
    if p[0] == "log":
        if p[1] == "template" and p[2] != "novel":
            return "log:%s:%s" % (service, p[2]), True
        if p[1] == "rate":
            return "log:%s:%s" % (service, p[2]), True
        return None, False
    if p[0] == "metric":
        return "metric:%s:%s" % (service, p[1]), p[2] not in NON_SYMPTOMS
    if p[0] == "span":
        op, ssym = sym[len("span:"):].rsplit(":", 1)
        return "span:%s:%s" % (service, op), ssym not in NON_SYMPTOMS
    return None, False


def modality(sensor):
    return sensor.split(":", 1)[0]


class Generation:
    """One generation's rows, split into episodes (fault cells), pseudo rows (no-fault cells) and cell rows.
    Never holds rows of another generation (S-G)."""

    def __init__(self, gen, rows, vocab):
        self.gen = gen
        self.vocab = vocab
        self.tau = vocab.get("admissibilityShare", TAU_DEFAULT)
        R = [r for r in rows if r["generation"] == gen]
        self.all_rows = R
        self.apw_rows = sum(1 for r in R if r.get("label") == APW)
        self.invalid_rows = sum(1 for r in R if not r["valid"])
        V = [r for r in R if r["valid"] and r.get("label") != APW]
        self.services = sorted({r["service"] for r in V})
        self.postures = sorted({r["posture"] for r in V})
        self.regimes = sorted({r["regime"] for r in V if not is_no_fault(r)})
        self.span_posture = next((p for p in SPAN_POSTURES if p in self.postures), None)
        # episodes: cell -> {service: fault row}; pseudo units: (cell, window) -> {service: row}; cell rows likewise
        self.fault = defaultdict(dict)
        self.pseudo = defaultdict(dict)
        self.cellrow = defaultdict(dict)
        self.meta = {}
        for r in V:
            k = r["window"]["kind"]
            if k == "fault":
                self.fault[r["cell"]][r["service"]] = r
                self.meta[r["cell"]] = r
            elif k == "pseudo":
                self.pseudo[(r["cell"], r["window"]["start"], r["window"]["end"])][r["service"]] = r
                self.meta[(r["cell"], r["window"]["start"], r["window"]["end"])] = r
            elif k == "cell":
                self.cellrow[r["cell"]][r["service"]] = r
        # symbols per modality seen anywhere in the valid non-a-p-w rows (0/n is never dropped)
        self.symbols = sorted({s for r in V for s in r["symbols"]})
        self.fault_or_pseudo_symbols = {s for r in V if r["window"]["kind"] != "cell" for s in r["symbols"]}
        self.sensors = sorted({sensor_of(s, r["service"])[0] for r in V if r["window"]["kind"] != "cell"
                               for s in r["symbols"] if sensor_of(s, r["service"])[0]})

    # ---- populations
    def episodes(self, regime, postures):
        return sorted(c for c, m in self.meta.items() if isinstance(c, str) and c in self.fault
                      and m["regime"] == regime and m["posture"] in postures)

    def pseudo_units(self, regime, postures):
        """No-fault units that calibrate `regime`: Hotel/TeaStore every pseudo row of the postures; G-old the pseudo
        rows whose pseudoFor names the family (one per baseline run per D_f)."""
        out = []
        for u in self.pseudo:
            m = self.meta[u]
            if m["posture"] not in postures:
                continue
            pf = m["window"].get("pseudoFor")
            if pf and regime not in pf:
                continue
            out.append(u)
        return sorted(out, key=str)

    def postures_for(self, sym_or_sensor):
        return (self.span_posture,) if sym_or_sensor.startswith("span:") else tuple(self.postures)

    # ---- admissibility (G3, from vocab.json)
    def vocab_key(self, service, regime, pseudo_for=None):
        nf = self.vocab.get("noFaultWindows", {})
        fam = (pseudo_for or [regime])[0] if (pseudo_for or regime) else None
        for k in ("%s/window:%s" % (service, fam), "%s/window" % service):
            if k in nf:
                return k
        for k in nf:      # a G-old key that lists several families sharing one D_f
            if k.startswith(service + "/window:") and fam in k.split(":", 1)[1].split("+"):
                return k
        return None

    def admissible(self, sym, service, regime, pseudo_for=None):
        """G3: a log template or metric symbol is admissible iff it fired in <= floor(tau * n0) calibrating no-fault
        windows. Other symbols (span, level, novel, rate, exception) are not subject to G3 (reading R2)."""
        if not (sym.startswith("log:template:") and sym != "log:template:novel") and not sym.startswith("metric:"):
            return True
        k = self.vocab_key(service, regime, pseudo_for)
        if k is None:
            return True
        n0 = self.vocab["noFaultWindows"][k]
        fa = self.vocab.get("symbolNoFaultWindows", {}).get(k, {}).get(sym, 0)
        return fa <= math.floor(self.tau * n0)

    def firing(self, row, admissibility=True):
        """Sensors that fire in a row (section 4 rule): a symptom symbol other than present / ? / missing, admissible."""
        m = row
        pf = m["window"].get("pseudoFor")
        out = set()
        for s in row["symbols"]:
            sensor, symptom = sensor_of(s, row["service"])
            if not sensor or not symptom:
                continue
            if admissibility and not self.admissible(s, row["service"], m["regime"], pf):
                continue
            out.add(sensor)
        return out


# --------------------------------------------------------------------------- C1 bridge (P1)

SPRINT_HB = {  # DETECTION_RESULT.md, H-B tables: (regime, detector) -> {posture: k/24}, FA over 72
    ("reservation-pause-effect", "level"): ({"none": 24, "sample-zero": 24, "full": 24}, 0),
    ("reservation-pause-effect", "metric-target"): ({"none": 23, "sample-zero": 24, "full": 24}, 0),
    ("reservation-pause-effect", "metric-other"): ({"none": 24, "sample-zero": 24, "full": 24}, 10),
    ("reservation-pause-effect", "trace-error"): ({"none": 0, "sample-zero": 0, "full": 24}, 0),
    ("search-pause-effect", "level"): ({"none": 0, "sample-zero": 0, "full": 0}, 0),
    ("search-pause-effect", "metric-target"): ({"none": 24, "sample-zero": 23, "full": 24}, 4),
    ("search-pause-effect", "metric-other"): ({"none": 24, "sample-zero": 24, "full": 24}, 6),
    ("search-pause-effect", "trace-error"): ({"none": 0, "sample-zero": 0, "full": 24}, 0),
}
SPRINT_HB_N = 24
SPRINT_HB_N0 = 72
SPRINT_SWEEP_WARN = {"reservation-pause-effect": 72, "search-pause-effect": 0, "fa": 0}   # sweep row "warn+", pooled over postures
SPRINT_TNEW = {"warn+": {"persistence-crash-effect": (11, 11), "auth-freeze-effect": (0, 9), "no-fault": (0, 12)},
               "error+": {"persistence-crash-effect": (0, 11), "auth-freeze-effect": (0, 9), "no-fault": (0, 12)}}


def level_hit(rows_by_svc, levels=("warn", "error", "fatal")):
    return any(("log:level:" + lv) in r["symbols"] for r in rows_by_svc.values() for lv in levels)


def metric_hit(rows_by_svc, services):
    return any(("metric:cpu:spike_up" in r["symbols"] or "metric:cpu:spike_down" in r["symbols"])
               for s, r in rows_by_svc.items() if s in services)


def trace_error_hit(rows_by_svc):
    return any(s.startswith("span:") and s.endswith(":error") for r in rows_by_svc.values() for s in r["symbols"])


def bridge_hotel(rows, gen="H-B"):
    """The sprint's four detectors reconstructed from the bags: level = any `log:level:*` in any service's fault
    row; metric-target / metric-other = target's / the other services' `metric:cpu:spike_*`; trace-error = any
    `span:*:error`. Over all postures; FA per target over the 72 no-fault pseudo rows (24 per posture)."""
    V = [r for r in rows if r["generation"] == gen and r["valid"]]
    fault, pseudo, meta = defaultdict(dict), defaultdict(dict), {}
    for r in V:
        if r["window"]["kind"] == "fault":
            fault[r["cell"]][r["service"]] = r
            meta[r["cell"]] = r
        elif r["window"]["kind"] == "pseudo":
            pseudo[r["cell"]][r["service"]] = r
            meta[r["cell"]] = r
    out, fa = {}, {}
    targets = sorted({meta[c]["target"] for c in fault})
    regimes = sorted({meta[c]["regime"] for c in fault})
    postures = sorted({meta[c]["posture"] for c in fault})
    for reg in regimes:
        for p in postures:
            cells = [c for c in fault if meta[c]["regime"] == reg and meta[c]["posture"] == p]
            tgt = {meta[c]["target"] for c in cells}
            tgt = tgt.pop() if len(tgt) == 1 else None
            others = lambda c: [s for s in fault[c] if s != meta[c]["target"]]
            out[(reg, p)] = {
                "n": len(cells),
                "level": sum(level_hit(fault[c]) for c in cells),
                "metric-target": sum(metric_hit(fault[c], [meta[c]["target"]]) for c in cells),
                "metric-other": sum(metric_hit(fault[c], others(c)) for c in cells),
                "trace-error": sum(trace_error_hit(fault[c]) for c in cells),
                "error+": sum(level_hit(fault[c], ("error", "fatal")) for c in cells),
                "target": tgt,
            }
    for tgt in targets:
        for p in postures + ["*"]:
            units = [u for u in pseudo if p == "*" or meta[u]["posture"] == p]
            fa[(tgt, p)] = {
                "n0": len(units),
                "level": sum(level_hit(pseudo[u]) for u in units),
                "metric-target": sum(metric_hit(pseudo[u], [tgt]) for u in units),
                "metric-other": sum(metric_hit(pseudo[u], [s for s in pseudo[u] if s != tgt]) for u in units),
                "trace-error": sum(trace_error_hit(pseudo[u]) for u in units),
                "error+": sum(level_hit(pseudo[u], ("error", "fatal")) for u in units),
            }
    return out, fa


def bridge_teastore(rows, gen="T-new"):
    """The sprint's cell-level level detector: any alert-level symbol in any service's `cell` row, over every valid
    cell including a-p-w (reading R7). warn+ and error+."""
    V = [r for r in rows if r["generation"] == gen and r["valid"] and r["window"]["kind"] == "cell"]
    cells = defaultdict(dict)
    meta = {}
    for r in V:
        cells[r["cell"]][r["service"]] = r
        meta[r["cell"]] = r
    out = {}
    for name, levels in (("warn+", ("warn", "error", "fatal")), ("error+", ("error", "fatal"))):
        res = {}
        for c, svcs in cells.items():
            key = "no-fault" if is_no_fault(meta[c]) else meta[c]["regime"]
            k, n = res.get(key, (0, 0))
            res[key] = (k + int(level_hit(svcs, levels)), n + 1)
        out[name] = res
    return out


def check_p1(rows):
    """P1: the named DETECTION_RESULT rows must match exactly. Returns (passed, report)."""
    report = {"hotel": {}, "teastore": {}, "mismatches": []}
    if any(r["generation"] == "H-B" for r in rows):
        det, fa = bridge_hotel(rows, "H-B")
        for (reg, d), (exp_by_p, exp_fa) in SPRINT_HB.items():
            tgt = reg.split("-")[0]
            for p, exp in exp_by_p.items():
                got = det.get((reg, p), {}).get(d)
                n = det.get((reg, p), {}).get("n")
                report["hotel"]["%s/%s/%s" % (reg, p, d)] = {"got": got, "n": n, "expected": exp, "expectedN": SPRINT_HB_N}
                if got != exp or n != SPRINT_HB_N:
                    report["mismatches"].append("H-B %s %s %s: got %s/%s expected %s/%s" % (reg, p, d, got, n, exp, SPRINT_HB_N))
            got_fa, n0 = fa.get((tgt, "*"), {}).get(d), fa.get((tgt, "*"), {}).get("n0")
            report["hotel"]["%s/FA/%s" % (reg, d)] = {"got": got_fa, "n0": n0, "expected": exp_fa, "expectedN0": SPRINT_HB_N0}
            if got_fa != exp_fa or n0 != SPRINT_HB_N0:
                report["mismatches"].append("H-B %s FA %s: got %s/%s expected %s/%s" % (reg, d, got_fa, n0, exp_fa, SPRINT_HB_N0))
        # sweep row warn+ pooled over postures
        for reg in ("reservation-pause-effect", "search-pause-effect"):
            got = sum(det[(reg, p)]["level"] for p in ("none", "sample-zero", "full") if (reg, p) in det)
            n = sum(det[(reg, p)]["n"] for p in ("none", "sample-zero", "full") if (reg, p) in det)
            report["hotel"]["sweep-warn+/%s" % reg] = {"got": got, "n": n, "expected": SPRINT_SWEEP_WARN[reg], "expectedN": 72}
            if got != SPRINT_SWEEP_WARN[reg] or n != 72:
                report["mismatches"].append("H-B sweep warn+ %s: got %s/%s expected %s/72" % (reg, got, n, SPRINT_SWEEP_WARN[reg]))
        got_fa = fa.get(("reservation", "*"), {}).get("level")
        report["hotel"]["sweep-warn+/FA"] = {"got": got_fa, "n0": 72, "expected": 0}
        if got_fa != 0:
            report["mismatches"].append("H-B sweep warn+ FA: got %s/72 expected 0/72" % got_fa)
        report["hotelDetail"] = {"%s/%s" % k: v for k, v in det.items()}
        report["hotelFalseAlarms"] = {"%s/%s" % k: v for k, v in fa.items()}
    else:
        report["mismatches"].append("H-B absent from the bags")
    if any(r["generation"] == "T-new" for r in rows):
        ts = bridge_teastore(rows, "T-new")
        report["teastore"] = ts
        for key, (ek, en) in SPRINT_TNEW["warn+"].items():
            got = ts["warn+"].get(key, (None, None))
            if tuple(got) != (ek, en):
                report["mismatches"].append("T-new warn+ %s: got %s/%s expected %s/%s" % (key, got[0], got[1], ek, en))
        for key, (ek, en) in SPRINT_TNEW["error+"].items():      # sweep row error+, checked beside warn+ (not a P1 gate row)
            got = ts["error+"].get(key, (None, None))
            report.setdefault("teastoreErrorPlus", {})[key] = {"got": list(got), "expected": [ek, en], "match": tuple(got) == (ek, en)}
    else:
        report["mismatches"].append("T-new absent from the bags")
    return not report["mismatches"], report


# --------------------------------------------------------------------------- tables

def count_table(G, items, keyfn, postures_of, _unused, item_in_row):
    """Generic per-item x class x service table. items: symbols or sensors. keyfn(item) -> service filter
    (None = any service, i.e. the pooled-over-services row). Returns nested dicts with k/n, exclusions, FA."""
    table = {}
    classes = list(G.regimes)
    for item in items:
        posts = postures_of(item)
        per = {}
        for reg in classes:
            eps = G.episodes(reg, posts)
            pseu = G.pseudo_units(reg, posts)
            per_svc = {}
            svc_filter = keyfn(item)
            for s in (G.services if svc_filter is None else [svc_filter]):
                have = [c for c in eps if s in G.fault[c]]
                k = sum(item_in_row(item, G.fault[c][s]) for c in have)
                have0 = [u for u in pseu if s in G.pseudo[u]]
                k0 = sum(item_in_row(item, G.pseudo[u][s]) for u in have0)
                per_svc[s] = {"k": k, "n": len(have), "excluded": len(eps) - len(have), "fa": k0, "n0": len(have0),
                              "excluded0": len(pseu) - len(have0)}
            # pooled over services: an episode counts if any of its rows carries the item
            kp = sum(any(item_in_row(item, r) for r in G.fault[c].values()) for c in eps)
            k0p = sum(any(item_in_row(item, r) for r in G.pseudo[u].values()) for u in pseu)
            per_svc["*"] = {"k": kp, "n": len(eps), "excluded": 0, "fa": k0p, "n0": len(pseu), "excluded0": 0}
            per[reg] = per_svc
        table[item] = {"postures": list(posts), "classes": per}
    return table


def symbol_in_row(sym, row):
    return sym in row["symbols"]


def per_posture_tables(G, items, postures_of, item_in_row, keyfn=lambda i: None):
    """Same counts per posture (log/metric symbols only; span symbols have one posture)."""
    out = {}
    for p in G.postures:
        sub = [i for i in items if p in postures_of(i)]
        if not sub:
            continue
        out[p] = count_table(G, sub, keyfn, lambda i, p=p: (p,), None, item_in_row)
    return out


def sensor_in_row_factory(G, admissibility=True):
    cache = {}

    def f(sensor, row):
        key = (id(row), admissibility)
        if key not in cache:
            cache[key] = G.firing(row, admissibility)
        fired = cache[key]
        if sensor.endswith(":*"):                      # modality aggregates: `log:*`, `log:<svc>:*`
            pre = sensor[:-1]
            return any(x.startswith(pre) for x in fired)
        return sensor in fired
    return f


def sensor_items(G):
    """Sensors plus modality aggregates per service (`log:<svc>:*`) and pooled (`log:*`)."""
    mods = sorted({modality(s) for s in G.sensors})
    agg = ["%s:*" % m for m in mods] + ["%s:%s:*" % (m, s) for m in mods for s in G.services
                                         if any(x.startswith("%s:%s:" % (m, s)) for x in G.sensors)]
    return list(G.sensors) + agg


def sensor_service(sensor):
    p = sensor.split(":")
    return None if p[1] == "*" else p[1]


# --------------------------------------------------------------------------- combinations

def combinations(G, admissibility=True):
    """Pairs (and triples when allowed) of sensors on the span-exporting episodes, per class: single, conjunction
    and union counts. redundant: conj == min(single); complementary: union > max(single)."""
    posts = (G.span_posture,) if G.span_posture else ()
    out = {"population": "valid fault cells of posture %s" % (G.span_posture,), "classes": {}}
    fired_by_class = {}
    all_firing = set()
    for reg in G.regimes:
        eps = G.episodes(reg, posts)
        bits = defaultdict(int)
        for i, c in enumerate(eps):
            for r in G.fault[c].values():
                for s in G.firing(r, admissibility):
                    bits[s] |= 1 << i
        fired_by_class[reg] = (eps, bits)
        all_firing |= set(bits)
    n_firing = len(all_firing)
    out["sensorsFiringInAnyEpisode"] = n_firing
    out["triplesComputed"] = n_firing <= TRIPLE_LIMIT
    for reg, (eps, bits) in fired_by_class.items():
        n = len(eps)
        sensors = sorted(bits)
        pairs = []
        for a, b in itertools.combinations(sensors, 2):
            ka, kb = bin(bits[a]).count("1"), bin(bits[b]).count("1")
            conj, uni = bin(bits[a] & bits[b]).count("1"), bin(bits[a] | bits[b]).count("1")
            pairs.append({"a": a, "b": b, "ka": ka, "kb": kb, "conj": conj, "union": uni,
                          "redundant": conj == min(ka, kb), "complementary": uni > max(ka, kb)})
        entry = {"n": n, "sensors": len(sensors), "pairs": pairs,
                 "pairsRedundant": sum(p["redundant"] for p in pairs),
                 "pairsComplementary": sum(p["complementary"] for p in pairs),
                 "pairsBothFullConjunction": sum(p["conj"] == n for p in pairs)}
        if out["triplesComputed"]:
            best_pair_union = {}
            for p in pairs:
                best_pair_union[(p["a"], p["b"])] = p["union"]
            triples = []
            for a, b, c in itertools.combinations(sensors, 3):
                uni = bin(bits[a] | bits[b] | bits[c]).count("1")
                conj = bin(bits[a] & bits[b] & bits[c]).count("1")
                sub = max(best_pair_union[(a, b)], best_pair_union[(a, c)], best_pair_union[(b, c)])
                if uni > sub:                                  # complementary beyond every sub-pair (stated rule)
                    triples.append({"a": a, "b": b, "c": c, "conj": conj, "union": uni, "bestPairUnion": sub})
            entry["triplesTotal"] = math.comb(len(sensors), 3)
            entry["triplesComplementaryBeyondPairs"] = triples
        out["classes"][reg] = entry
    return out


# --------------------------------------------------------------------------- mutual information

def mi_bits(pairs):
    """Plug-in I(X;C) in bits from (x, c) observations, 0 log 0 = 0."""
    n = len(pairs)
    if n == 0:
        return None
    pxc, px, pc = Counter(pairs), Counter(x for x, _ in pairs), Counter(c for _, c in pairs)
    return sum(v / n * math.log2((v / n) / ((px[x] / n) * (pc[c] / n))) for (x, c), v in pxc.items())


def mutual_information(G):
    """I(sigma; C) per symbol, per service and pooled; classes = fault regimes + one no-fault class of pseudo rows."""
    out = {}
    for sym in G.symbols:
        posts = G.postures_for(sym)
        per = {}
        for s in G.services + ["*"]:
            obs = []
            for reg in G.regimes:
                for c in G.episodes(reg, posts):
                    if s == "*":
                        obs.append((any(sym in r["symbols"] for r in G.fault[c].values()), reg))
                    elif s in G.fault[c]:
                        obs.append((sym in G.fault[c][s]["symbols"], reg))
            for u in G.pseudo:
                if G.meta[u]["posture"] not in posts:
                    continue
                if s == "*":
                    obs.append((any(sym in r["symbols"] for r in G.pseudo[u].values()), "no-fault"))
                elif s in G.pseudo[u]:
                    obs.append((sym in G.pseudo[u][s]["symbols"], "no-fault"))
            per[s] = {"bits": mi_bits(obs), "n": len(obs), "classSizes": dict(Counter(c for _, c in obs))}
        out[sym] = per
    return out


# --------------------------------------------------------------------------- R(p), gates, objective

def build_R(G):
    """R(p) per span-exporting episode: sensors that fire admissibly in the episode's fault row of their service.
    G2 primary excludes the target service's sensors; R+ keeps them. G1, G5, G6 are applied in the bags."""
    posts = (G.span_posture,) if G.span_posture else ()
    eps = []
    for reg in G.regimes:
        for c in G.episodes(reg, posts):
            m = G.meta[c]
            rplus, r_noadm = set(), set()
            for s, row in G.fault[c].items():
                rplus |= G.firing(row, True)
                r_noadm |= G.firing(row, False)
            tgt = m["target"]
            R = {x for x in rplus if sensor_service(x) != tgt}
            g3_removed = {x for x in r_noadm if sensor_service(x) != tgt} - R
            eps.append({"cell": c, "regime": reg, "target": tgt, "R": sorted(R), "Rplus": sorted(rplus),
                        "G2removed": sorted(rplus - R), "G3removed": sorted(g3_removed),
                        "composition": dict(Counter(modality(x) for x in R)),
                        "metricWithoutLog": ("metric" in {modality(x) for x in R}) and ("log" not in {modality(x) for x in R})})
    return eps


def f_all(sets, S):
    return sum(1 for R in sets if R and R <= S)


def f_any(sets, S):
    return sum(1 for R in sets if R & S)


def optimum(eps, key="R", max_k=MAX_K):
    """max f_all / f_any per budget k (unit costs). Exact over unions of distinct R sets when <= EXACT_SETS,
    else greedy (labelled). Bitmask arithmetic: sensor i <-> bit i."""
    sets = [frozenset(e[key]) for e in eps]
    distinct = sorted({R for R in sets if R}, key=sorted)
    universe = sorted(set().union(*distinct)) if distinct else []
    out = {"distinctSets": len(distinct), "universe": len(universe), "perK": {}, "method": None}
    if not distinct:
        return out
    idx = {s: i for i, s in enumerate(universe)}
    bits = [sum(1 << idx[x] for x in R) for R in distinct]
    mult = Counter(sum(1 << idx[x] for x in R) for R in sets if R)
    exact = len(distinct) <= EXACT_SETS
    out["method"] = ("exact (union enumeration over %d distinct R sets)" % len(distinct)) if exact else ("greedy (%d distinct sets > %d)" % (len(distinct), EXACT_SETS))
    K = min(max_k, len(universe))
    if exact:
        m = len(bits)
        unions = [0] * (1 << m)
        for mask in range(1, 1 << m):
            low = mask & -mask
            unions[mask] = unions[mask ^ low] | bits[low.bit_length() - 1]
        cands = {U for U in unions[1:] if bin(U).count("1") <= K}
        f_all_of = {U: sum(mult[b] for b in mult if b & ~U == 0) for U in cands}
        for k in range(1, K + 1):
            ck = [U for U in cands if bin(U).count("1") <= k]
            best_all = max((f_all_of[U] for U in ck), default=0)
            if math.comb(len(universe), k) <= 200_000:
                best_any = max(f_any(sets, frozenset(c)) for c in itertools.combinations(universe, k))
                any_method = "exact"
            else:
                best_any, any_method = greedy(sets, universe, k, f_any), "greedy"
            arg_all = sorted([sorted(universe[i] for i in range(len(universe)) if U >> i & 1) for U in ck if f_all_of[U] == best_all], key=len)[:3]
            out["perK"][k] = {"f_all": best_all, "f_any": best_any, "f_anyMethod": any_method, "argmaxAll": arg_all}
    else:
        for k in range(1, K + 1):
            out["perK"][k] = {"f_all": greedy(sets, universe, k, f_all), "f_any": greedy(sets, universe, k, f_any), "f_anyMethod": "greedy"}
    return out


def greedy(sets, universe, k, f):
    S = frozenset()
    for _ in range(k):
        rest = [x for x in universe if x not in S]
        if not rest:
            break
        best = max(rest, key=lambda x: (f(sets, S | {x}), -len(x), x))
        S = S | {best}
    return f(sets, S)


# --------------------------------------------------------------------------- predictions

def ge(k, n, thr):
    return k is not None and n is not None and k >= thr


def predictions(gens, symtab, sentab, Rsets, p1_ok, p2_tid):
    """DEFINITIONS section 10 (D-P1..D-P7) and amendment section 8 (A-P1..A-P6), each held / failed / --."""
    P = {}
    HB, G, TN = gens.get("H-B"), gens.get("G-old"), gens.get("T-new")

    def count(gen, reg, fn):
        eps = Rsets[gen]
        rows = [e for e in eps if e["regime"] == reg]
        return sum(fn(e) for e in rows), len(rows)

    P["D-P1"] = {"text": "C1 reproduces DETECTION_RESULT exactly (sprint)", "held": p1_ok, "tbc": "TBC6"}
    P["A-P1"] = {"text": "same, with U4 reconstructed from templates", "held": p1_ok, "tbc": "TBC6"}
    if HB and "H-B" in Rsets:
        k, n = count("H-B", "reservation-pause-effect", lambda e: any(x.startswith("log:frontend:") for x in e["R"]))
        k2, n2 = count("H-B", "search-pause-effect", lambda e: any(x.startswith("log:frontend:") for x in e["R"]))
        P["D-P2"] = {"text": "H-B: log:frontend in R(p) >= 20/24 reservation-pause and 0/24 search-pause (G3 on)",
                     "values": {"reservation": "%d/%d" % (k, n), "search": "%d/%d" % (k2, n2)}, "held": k >= 20 and k2 == 0}
        k, n = count("H-B", "search-pause-effect", lambda e: e["metricWithoutLog"])
        P["D-P3"] = {"text": "H-B search-pause: >= 20/24 episodes with a metric sensor and no log sensor in R(p)",
                     "values": {"search": "%d/%d" % (k, n)}, "held": k >= 20}
        eps = Rsets["H-B"]
        distinct = {frozenset(e["R"]) for e in eps}
        by_reg = defaultdict(set)
        for e in eps:
            by_reg[e["regime"]].add(frozenset(e["R"]))
        shared = set.intersection(*by_reg.values()) if len(by_reg) > 1 else set()
        P["D-P4"] = {"text": "H-B: >= 2 distinct R sets over the 48 episodes; no R set in both regimes",
                     "values": {"distinct": len(distinct), "episodes": len(eps), "sharedAcrossRegimes": len(shared)},
                     "held": len(distinct) >= 2 and not shared}
        # amendment P2: log:level:error in frontend's fault row in >= 20/24 full reservation-pause; server.go:271 template carries it;
        # search-pause: no log:level:* in any service in >= 20/24
        posts = (HB.span_posture,)
        res = HB.episodes("reservation-pause-effect", posts)
        srch = HB.episodes("search-pause-effect", posts)
        k = sum("log:level:error" in HB.fault[c].get("frontend", {"symbols": []})["symbols"] for c in res)
        carried = sum(any(("log:template:" + t) in HB.fault[c].get("frontend", {"symbols": []})["symbols"] for t in p2_tid) for c in res) if p2_tid else None
        k2 = sum(not any(s.startswith("log:level:") for r in HB.fault[c].values() for s in r["symbols"]) for c in srch)
        P["A-P2"] = {"text": "H-B full: log:level:error in frontend fault row >= 20/24 reservation-pause, carried by server.go:271's template; "
                             "search-pause no log:level:* in any service >= 20/24",
                     "values": {"reservation-error": "%d/%d" % (k, len(res)), "server.go:271 template present": ("%s/%d" % (carried, len(res))) if carried is not None else "?",
                                "search-no-level": "%d/%d" % (k2, len(srch)), "server.go:271 tids": sorted(p2_tid or [])},
                     "held": k >= 20 and (carried is not None and carried >= 20) and k2 >= 20}
        # amendment P3: missing_expected for the paused service's own op >= 20/24 each regime; span error for a frontend op >= 20/24
        vals, ok = {}, True
        for reg, eps_ in (("reservation-pause-effect", res), ("search-pause-effect", srch)):
            tgt = reg.split("-")[0]
            km = sum(any(s.startswith("span:") and s.endswith(":missing_expected") for s in HB.fault[c].get(tgt, {"symbols": []})["symbols"]) for c in eps_)
            ke = sum(any(s.startswith("span:") and s.endswith(":error") for s in HB.fault[c].get("frontend", {"symbols": []})["symbols"]) for c in eps_)
            vals[reg] = {"target missing_expected": "%d/%d" % (km, len(eps_)), "frontend span error": "%d/%d" % (ke, len(eps_))}
            ok &= km >= 20 and ke >= 20
        P["A-P3"] = {"text": "H-B full: span:<op>:missing_expected for the paused service's own operation >= 20/24 per regime; "
                             "span:<op>:error for a frontend operation >= 20/24", "values": vals, "held": ok, "tbc": "TBC1 (missing_expected)"}
        # amendment P4: some log:rate:<tid>:high outside the target service in >= 12/24 reservation-pause (per posture)
        vals = {}
        for p in HB.postures:
            eps_ = HB.episodes("reservation-pause-effect", (p,))
            k = sum(any(s.startswith("log:rate:") for svc, r in HB.fault[c].items() if svc != HB.meta[c]["target"] for s in r["symbols"]) for c in eps_)
            vals[p] = "%d/%d" % (k, len(eps_))
        kf = int(vals[HB.span_posture].split("/")[0])
        P["A-P4"] = {"text": "H-B: a log:rate:<tid>:high outside the target in >= 12/24 reservation-pause episodes (evaluated on `full`, R10)",
                     "values": vals, "held": kf >= 12}
    if TN:
        # amendment P5: log:exception:ClientException in auth's cell row, >= 8/11 persistence-crash and 0/9 auth-freeze (all valid cells incl. a-p-w)
        allrows = [r for r in TN.all_rows if r["valid"] and r["window"]["kind"] == "cell" and r["service"] == "auth"]
        pc = [r for r in allrows if r["regime"] == "persistence-crash-effect"]
        af = [r for r in allrows if r["regime"] == "auth-freeze-effect"]
        k1 = sum("log:exception:ClientException" in r["symbols"] for r in pc)
        k2 = sum("log:exception:ClientException" in r["symbols"] for r in af)
        P["A-P5"] = {"text": "T-new: log:exception:ClientException in auth's cell row >= 8/11 persistence-crash and 0/9 auth-freeze (valid cells, all postures)",
                     "values": {"persistence-crash": "%d/%d" % (k1, len(pc)), "auth-freeze": "%d/%d" % (k2, len(af))},
                     "held": k1 >= 8 and k2 == 0 and len(pc) == 11 and len(af) == 9, "tbc": "TBC2 (consistency, disclosed look)"}
    if G and "G-old" in Rsets:
        # DEFINITIONS P5
        def nonself_log(e):
            return any(modality(x) == "log" for x in e["R"])
        vals = {}
        for reg in ("auth_freeze", "persistence_crash", "db_crash"):
            k, n = count("G-old", reg, nonself_log)
            vals[reg] = "%d/%d" % (k, n)
        ka, kp, kd = (int(vals[r].split("/")[0]) for r in ("auth_freeze", "persistence_crash", "db_crash"))
        P["D-P5"] = {"text": "G-old (G2 on): non-self log sensor in R(p): auth_freeze <= 2/10, persistence_crash >= 8/10, db_crash <= 2/10",
                     "values": vals, "held": ka <= 2 and kp >= 8 and kd <= 2}
        # DEFINITIONS P6 (second half; C4 is not computable from the bags)
        fam_metric = defaultdict(int)
        fam_mwl = defaultdict(int)
        for e in Rsets["G-old"]:
            if any(modality(x) == "metric" for x in e["R"]):
                fam_metric[e["regime"]] += 1
            fam_mwl[e["regime"]] += e["metricWithoutLog"]
        fams = [f for f in G.regimes if fam_metric[f] > 0]
        P["D-P6"] = {"text": "G-old: C4 old metric-without-log = 0/total (--, needs ground_truth.json, not in the bags); gated R(p) has "
                             ">= 1 metric-without-log episode in every family where a metric sensor enters R(p) at all",
                     "values": {"familiesWithMetricInR": {f: fam_metric[f] for f in fams}, "metricWithoutLog": {f: fam_mwl[f] for f in fams}, "C4": "--"},
                     "held": all(fam_mwl[f] >= 1 for f in fams) if fams else None}
        # amendment P6: >= 2 families with a metric spike in some non-target service row and no log:level:* in that row, >= 5/10 runs
        posts = (G.span_posture,)
        fam_ok = {}
        for reg in G.regimes:
            eps_ = G.episodes(reg, posts)
            k = 0
            for c in eps_:
                tgt = G.meta[c]["target"]
                hit = False
                for svc, r in G.fault[c].items():
                    if svc == tgt:
                        continue
                    if any(s.startswith("metric:") and ":spike_" in s for s in r["symbols"]) and not any(s.startswith("log:level:") for s in r["symbols"]):
                        hit = True
                k += hit
            fam_ok[reg] = "%d/%d" % (k, len(eps_))
        q = sum(int(v.split("/")[0]) >= 5 for v in fam_ok.values())
        P["A-P6"] = {"text": "G-old: >= 2 fault families with metric:*:spike_* in a non-target service row and no log:level:* in that row in >= 5/10 runs",
                     "values": fam_ok, "familiesQualifying": q, "held": q >= 2}
    P["D-P7"] = {"text": "H-A vs H-B same regime-level composition", "held": None, "values": "-- (H-A dropped, A14)"}
    P["A-P7"] = {"text": "withdrawn in the amendment (template counts were already in section 7)", "held": None, "values": "--"}
    return P


# --------------------------------------------------------------------------- P2 template identification (server.go:271)

def server_go_271_tids(manifest, symptoms_mod):
    """Template ids of frontend records with caller services/frontend/server.go:271 in one H-B reservation-pause
    `full` cell, re-parsed from the manifest's own input file (sha-checked). Needed because bags carry tids only."""
    cands = [i for i in manifest.get("inputs", []) if i["generation"] == "H-B" and i["path"].endswith("application.log")
             and "/effect/reservation-pause" in i["path"] and "-full/" in i["path"]]
    for i in cands:
        p = Path(i["path"])
        if not p.exists() or sha256_file(p) != i["sha256"]:
            continue
        tids = set()
        streams = defaultdict(list)
        for raw in p.read_text(errors="replace").splitlines():
            if " | " not in raw:
                continue
            prefix, payload = raw.split(" | ", 1)
            streams[prefix.strip().rsplit("-", 1)[0]].append(payload)
        recs, _ = symptoms_mod.parse_stream(streams.get("frontend", []), symptoms_mod.HOTEL_LAYOUTS)
        for r in recs:
            if r["key"] == "services/frontend/server.go:271" and r["level"] == "error":
                tids.add(symptoms_mod.template_id(r["framework"], r["level"], r["key"], r["msg"]))
        if tids:
            return sorted(tids), str(p)
    return [], None


def load_symptoms():
    import importlib.util
    spec = importlib.util.spec_from_file_location("s4_symptoms", SYMPTOMS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- rendering

def kn(d):
    return "%d/%d" % (d["k"], d["n"]) if d["n"] else "--"


def fa(d):
    return "%d/%d" % (d["fa"], d["n0"]) if d["n0"] else "--"


def md_symbol_table(G, table, title, only_firing=True):
    """Markdown: symbol x class (pooled over services) with k/n and FA; per-service blocks for firing symbols."""
    lines = ["### %s" % title, ""]
    classes = G.regimes
    head = "| symbol | postures | " + " | ".join("%s k/n (FA k/n0)" % c for c in classes) + " |"
    lines += [head, "|" + "---|" * (len(classes) + 2)]
    zero = []
    for sym, d in table.items():
        cells = []
        fired = False
        for c in classes:
            p = d["classes"][c]["*"]
            fired |= p["k"] > 0 or p["fa"] > 0
            cells.append("%s (%s)" % (kn(p), fa(p)))
        if only_firing and not fired:
            zero.append((sym, {c: "%s (%s)" % (kn(d["classes"][c]["*"]), fa(d["classes"][c]["*"])) for c in classes}))
            continue
        lines.append("| `%s` | %s | %s |" % (sym, "+".join(d["postures"]), " | ".join(cells)))
    if zero:
        lines += ["", "%d symbols with 0 detections and 0 false alarms in every class (0/n, never dropped; denominators per class as above): "
                  % len(zero) + ", ".join("`%s`" % s for s, _ in zero)]
    lines.append("")
    return lines


def md_symbol_per_service(G, table, title):
    lines = ["### %s" % title, ""]
    classes = G.regimes
    lines += ["| symbol | service | " + " | ".join("%s k/n excl (FA k/n0)" % c for c in classes) + " |", "|" + "---|" * (len(classes) + 2)]
    for sym, d in table.items():
        for s in G.services:
            row = [d["classes"][c][s] for c in classes]
            if not any(x["k"] or x["fa"] for x in row):
                continue
            lines.append("| `%s` | %s | %s |" % (sym, s, " | ".join("%s%s (%s)" % (kn(x), (" x%d" % x["excluded"]) if x["excluded"] else "", fa(x)) for x in row)))
    lines.append("")
    return lines


def render(out):
    L = ["# S4 relevance baseline: generated tables (%s)" % out["generatedAt"], "",
         "Scope label: instance, per generation, never pooled. Every cell is k/n with the denominator named; "
         "`--` is no data; `x<m>` beside a per-service count is the number of episodes of that class with no row for the service (excluded).", ""]
    L += ["## Provenance", "", "- bags: `%s`" % out["bagDir"], "- symptoms.py sha256: `%s` (committed: `%s`)" % (out["provenance"]["scriptSha"], out["provenance"]["committedSha"]),
          "- framework commit at this run: `%s`" % out["frameworkCommit"], "- python: %s" % out["python"], ""]
    L += ["## Readings of the amendment text (recorded, not tuned)", ""] + ["- %s" % r for r in READINGS] + [""]
    L += ["## P1 / C1 bridge", "", "PASS" if out["p1"]["passed"] else "FAIL", ""]
    for k, v in sorted(out["p1"]["report"].get("hotel", {}).items()):
        L.append("- H-B %s: got %s/%s, expected %s/%s%s" % (k, v.get("got"), v.get("n", v.get("n0")), v.get("expected"), v.get("expectedN", v.get("expectedN0", "")),
                                                        "" if v.get("got") == v.get("expected") else "  **MISMATCH**"))
    for lv, res in out["p1"]["report"].get("teastore", {}).items():
        L.append("- T-new %s: %s" % (lv, ", ".join("%s %d/%d" % (k, v[0], v[1]) for k, v in sorted(res.items()))))
    L += ["- mismatches: %s" % (out["p1"]["report"]["mismatches"] or "none"), ""]
    if not out["p1"]["passed"] and not out.get("replicationRun"):
        return "\n".join(L)
    for gen, gd in out["generations"].items():
        G = gd["_G"]
        L += ["## Generation %s" % gen, "",
              "- services: %s; postures: %s; span-exporting posture: %s; fault classes: %s" % (", ".join(G.services), ", ".join(G.postures), G.span_posture, ", ".join(G.regimes)),
              "- episodes per class per posture: %s" % json.dumps(gd["episodesPerClassPosture"]),
              "- no-fault pseudo units per posture: %s; per class (G-old per-family): %s" % (json.dumps(gd["pseudoPerPosture"]), json.dumps(gd["pseudoPerClass"])),
              "- rows excluded: a-p-w %d, invalid %d (both in the bags, in no table)" % (G.apw_rows, G.invalid_rows),
              "- symbols: %d (log %d, metric %d, span %d); sensors: %d; fault rows whose only log symptom is an exception class (reading R1): %d"
              % (len(G.symbols), *[sum(1 for s in G.symbols if s.startswith(m + ":")) for m in ("log", "metric", "span")], len(G.sensors), gd["exceptionOnlyRows"]),
              "- true by construction here: %s" % "; ".join(gd["tbcFlags"]), ""]
        L += md_symbol_table(G, gd["symbols"]["pooled"], "%s: per symbol x fault class, pooled over postures (span: `%s` only) and over services" % (gen, G.span_posture))
        for p, t in gd["symbols"]["perPosture"].items():
            L += md_symbol_table(G, t, "%s: per symbol x fault class, posture `%s`, pooled over services" % (gen, p))
        L += md_symbol_per_service(G, gd["symbols"]["pooled"], "%s: per symbol x fault class, per service (postures pooled; symbols with any detection or false alarm)" % gen)
        L += md_symbol_table(G, gd["sensors"]["pooled"], "%s: per sensor x fault class (firing rule, G3 applied; `<mod>:*` = any sensor of the modality, `<mod>:<svc>:*` = any of the service)" % gen, only_firing=True)
        for p, t in gd["sensors"]["perPosture"].items():
            L += md_symbol_table(G, t, "%s: per sensor x fault class, posture `%s`" % (gen, p))
        # combinations
        cb = gd["combinations"]
        L += ["### %s: combinations on %s (sensors firing in >= 1 episode: %d; triples %s)" % (gen, cb["population"], cb["sensorsFiringInAnyEpisode"], "computed" if cb["triplesComputed"] else "not computed (> %d)" % TRIPLE_LIMIT), "",
              "| class | n | sensors firing | pairs | redundant (conj = min single) | complementary (union > max single) | pairs with conjunction = n | triples beyond every sub-pair |", "|---|---|---|---|---|---|---|---|"]
        for c, e in cb["classes"].items():
            L.append("| %s | %d | %d | %d | %d | %d | %d | %s |" % (c, e["n"], e["sensors"], len(e["pairs"]), e["pairsRedundant"], e["pairsComplementary"], e["pairsBothFullConjunction"],
                                                                 ("%d of %d" % (len(e["triplesComplementaryBeyondPairs"]), e["triplesTotal"])) if "triplesTotal" in e else "--"))
        L.append("")
        for c, e in cb["classes"].items():
            comp = [p for p in e["pairs"] if p["complementary"]]
            if comp:
                L += ["Complementary pairs, %s (n = %d): " % (c, e["n"]) + "; ".join("`%s`(%d)+`%s`(%d) union %d conj %d" % (p["a"], p["ka"], p["b"], p["kb"], p["union"], p["conj"]) for p in comp), ""]
        # MI
        L += ["### %s: mutual information I(symbol; class), bits, plug-in (ranking aid, no test)" % gen, "", "| symbol | pooled bits (n; class sizes) | per service (bits, n) |", "|---|---|---|"]
        for sym, per in sorted(gd["mi"].items(), key=lambda kv: -(kv[1]["*"]["bits"] or 0)):
            if not per["*"]["bits"]:
                continue
            L.append("| `%s` | %.3f (%d; %s) | %s |" % (sym, per["*"]["bits"], per["*"]["n"], json.dumps(per["*"]["classSizes"]),
                                                       "; ".join("%s %.3f (%d)" % (s, v["bits"], v["n"]) for s, v in per.items() if s != "*" and v["bits"])))
        L += ["", "symbols with I = 0 bits pooled: %d of %d" % (sum(1 for per in gd["mi"].values() if not per["*"]["bits"]), len(gd["mi"])), ""]
        # R(p)
        rp = gd["R"]
        L += ["### %s: R(p) with G1-G6 (span-exporting episodes)" % gen, "",
              "- episodes: %d; |R| distribution: %s; distinct R sets: %d; empty R: %d; G4 metric-without-log: %d" % (rp["n"], json.dumps(rp["sizeDist"]), rp["distinct"], rp["empty"], rp["g4"]),
              "- composition per class: %s" % json.dumps(rp["compositionPerClass"]),
              "- G2 removed (target-service sensors) per class: %s; G3 removed per class: %s" % (json.dumps(rp["g2PerClass"]), json.dumps(rp["g3PerClass"])),
              "- max f_all / f_any per k (%s): %s" % (rp["optimum"]["method"], "; ".join("k=%s all %d any %d (%s)" % (k, v["f_all"], v["f_any"], v["f_anyMethod"]) for k, v in rp["optimum"]["perK"].items())),
              "- R+ (G2 off): distinct %d; max f_all per k: %s" % (rp["optimumPlus"]["distinctSets"], "; ".join("k=%s %d" % (k, v["f_all"]) for k, v in rp["optimumPlus"]["perK"].items())),
              "- level sets over the catalogue domain: -- (R11)", ""]
    L += ["## Predictions", "", "| id | prediction | values | verdict |", "|---|---|---|---|"]
    for pid, p in out["predictions"].items():
        v = "held" if p["held"] else ("failed" if p["held"] is False else "--")
        L.append("| %s | %s | %s | %s%s |" % (pid, p["text"], json.dumps(p.get("values", "")), v, (" (%s)" % p["tbc"]) if p.get("tbc") else ""))
    L += ["", "## True-by-construction register", ""] + ["- %s: %s" % (k, v) for k, v in TRUE_BY_CONSTRUCTION.items()]
    return "\n".join(L)


# --------------------------------------------------------------------------- driver

def analyse(rows, vocab, summary, manifest, prov, bag_dir, symptoms_mod=None, replication=False):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {"generatedAt": stamp, "bagDir": str(bag_dir), "provenance": prov, "frameworkCommit": git_commit(),
           "python": sys.version.split()[0], "readings": READINGS, "trueByConstruction": TRUE_BY_CONSTRUCTION,
           "bagsManifestScript": manifest.get("script"), "bagsFrameworkCommit": manifest.get("frameworkCommit")}
    ok, rep = check_p1(rows)
    out["p1"] = {"passed": ok, "report": rep}
    # ponytail: P1 compares against the sprint population; a fresh run (REPLICATION_DECLARATION Amendment B) reports it, ungated
    out["replicationRun"] = replication
    if not ok and not replication:
        out["stopRule"] = "S-B: P1 failed; no relevance, conjunction or MI value is reported"
        return out
    gens = {g: Generation(g, rows, vocab.get(g, {})) for g in sorted({r["generation"] for r in rows})}
    out["generations"] = {}
    Rsets = {}
    for g, G in gens.items():
        gd = {"_G": G}
        gd["episodesPerClassPosture"] = {reg: {p: len(G.episodes(reg, (p,))) for p in G.postures} for reg in G.regimes}
        gd["pseudoPerPosture"] = {p: sum(1 for u in G.pseudo if G.meta[u]["posture"] == p) for p in G.postures}
        gd["pseudoPerClass"] = {reg: len(G.pseudo_units(reg, G.postures)) for reg in G.regimes}
        gd["exceptionOnlyRows"] = sum(1 for c in G.fault for r in G.fault[c].values()
                                      if any(s.startswith("log:exception:") for s in r["symbols"]) and not any(modality(x) == "log" for x in G.firing(r, False)))
        sym_pooled = count_table(G, G.symbols, lambda i: None, G.postures_for, None, symbol_in_row)
        sym_post = per_posture_tables(G, [s for s in G.symbols if not s.startswith("span:")], G.postures_for, symbol_in_row)
        gd["symbols"] = {"pooled": sym_pooled, "perPosture": sym_post}
        sir = sensor_in_row_factory(G, True)
        items = sensor_items(G)
        sen_pooled = count_table(G, items, lambda i: None, G.postures_for, None, sir)
        sen_post = per_posture_tables(G, [s for s in items if not s.startswith("span:")], G.postures_for, sir)
        gd["sensors"] = {"pooled": sen_pooled, "perPosture": sen_post}
        gd["combinations"] = combinations(G)
        gd["mi"] = mutual_information(G)
        eps = build_R(G)
        Rsets[g] = eps
        sizes = Counter(len(e["R"]) for e in eps)
        comp = defaultdict(Counter)
        g2 = defaultdict(int)
        g3 = defaultdict(int)
        for e in eps:
            comp[e["regime"]]["+".join(sorted(e["composition"])) or "empty"] += 1
            g2[e["regime"]] += len(e["G2removed"])
            g3[e["regime"]] += len(e["G3removed"])
        gd["R"] = {"n": len(eps), "episodes": eps, "sizeDist": dict(sorted(sizes.items())), "distinct": len({frozenset(e["R"]) for e in eps}),
                   "empty": sum(1 for e in eps if not e["R"]), "g4": sum(e["metricWithoutLog"] for e in eps),
                   "compositionPerClass": {k: dict(v) for k, v in comp.items()}, "g2PerClass": dict(g2), "g3PerClass": dict(g3),
                   "optimum": optimum(eps, "R"), "optimumPlus": optimum(eps, "Rplus")}
        flags = []
        if G.span_posture and len(G.postures) > 1:
            flags.append("TBC3 (span tables are `%s` only)" % G.span_posture)
        if g in ("T-new", "T-16"):
            flags += ["TBC5 (every log FA is 0/n0 and every template is novel by construction)", "TBC9 (log4j templates are cell-row only)", "TBC8"]
        if g.startswith("H-B"):
            flags += ["TBC1 (target's cpu spike_down/plateau_down and missing_expected)"]
        if g == "G-old":
            flags += ["TBC1 (auth_freeze target), TBC2 (crash families' restart templates and exception classes)"]
        gd["tbcFlags"] = flags
        out["generations"][g] = gd
    p2_tid, p2_src = ([], None)
    if symptoms_mod is not None:
        p2_tid, p2_src = server_go_271_tids(manifest, symptoms_mod)
    out["p2TemplateIds"] = {"tids": p2_tid, "source": p2_src}
    out["predictions"] = predictions(gens, None, None, Rsets, ok, p2_tid)
    return out


def strip_private(o):
    if isinstance(o, dict):
        return {k: strip_private(v) for k, v in o.items() if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(o, list):
        return [strip_private(x) for x in o]
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return o


def print_headline(out):
    print("P1:", "PASS" if out["p1"]["passed"] else "FAIL", out["p1"]["report"]["mismatches"] or "")
    if not out["p1"]["passed"] and not out.get("replicationRun"):
        return
    for g, gd in out["generations"].items():
        G = gd["_G"]
        print("\n== %s  classes %s  span posture %s" % (g, G.regimes, G.span_posture))
        print("  episodes/class/posture", json.dumps(gd["episodesPerClassPosture"]), " pseudo/posture", json.dumps(gd["pseudoPerPosture"]))
        for item, d in gd["sensors"]["pooled"].items():
            if item.endswith(":*"):
                print("  %-28s" % item, "  ".join("%s %s (FA %s)" % (c[:14], kn(d["classes"][c]["*"]), fa(d["classes"][c]["*"])) for c in G.regimes))
        rp = gd["R"]
        print("  R(p): n %d sizes %s distinct %d empty %d G4 %d comp %s" % (rp["n"], rp["sizeDist"], rp["distinct"], rp["empty"], rp["g4"], json.dumps(rp["compositionPerClass"])))
        cb = gd["combinations"]
        print("  combinations: firing sensors %d triples %s; per class: %s" % (cb["sensorsFiringInAnyEpisode"], cb["triplesComputed"],
              {c: (e["sensors"], len(e["pairs"]), e["pairsRedundant"], e["pairsComplementary"]) for c, e in cb["classes"].items()}))
    print("\nPredictions:")
    for pid, p in out["predictions"].items():
        print("  %-5s %-6s %s" % (pid, "held" if p["held"] else ("failed" if p["held"] is False else "--"), json.dumps(p.get("values", ""))))


def run(args):
    rows, vocab, summary, manifest, prov = load_bags(args.bags, require_commit=not args.no_commit_check)
    root = Path(args.out)
    out_dir = root / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if out_dir.exists():
        sys.exit("refusing to overwrite %s" % out_dir)
    out = analyse(rows, vocab, summary, manifest, prov, args.bags, load_symptoms(), replication=getattr(args, "replication", False))
    out_dir.mkdir(parents=True)
    (out_dir / "tables.md").write_text(render(out))
    (out_dir / "relevance.json").write_text(json.dumps(strip_private(out), indent=1, sort_keys=True, default=list))
    print_headline(out)
    print("wrote", out_dir)
    return out_dir


# --------------------------------------------------------------------------- self-check (fixtures; planted defects)

def _fixture_rows():
    """A two-class Hotel-like generation FX with 4 full + 4 none fault cells per class and 4 + 4 no-fault cells."""
    rows = []

    def row(cell, posture, regime, kind, service, symbols, target=None, pseudo_for=None, valid=True, label=None):
        rows.append({"generation": "FX", "system": "hotel", "cell": cell, "run": "r", "block": 1, "posture": posture,
                     "regime": regime, "valid": valid, "target": target, "label": label,
                     "window": {"kind": kind, "start": 100.0, "end": 115.0, "pseudoFor": pseudo_for},
                     "service": service, "symbols": sorted(symbols), "counts": {s: 1 for s in symbols}, "derived": []})

    for p in ("full", "none"):
        for i in range(4):
            c = "%s/res%d" % (p, i)
            fe = ["log:level:error", "log:template:aaa", "log:template:common"] + (["span:HTTP_GET:present", "span:HTTP_GET:error"] if p == "full" else [])
            row(c, p, "res-pause", "fault", "frontend", fe, "reservation")
            row(c, p, "res-pause", "fault", "reservation", ["metric:cpu:spike_down"] + (["span:Check:missing_expected"] if p == "full" else []), "reservation")
            if i < 2:
                row(c, p, "res-pause", "fault", "geo", ["metric:cpu:spike_up"], "reservation")   # geo row missing in 2 of 4
            c = "%s/srch%d" % (p, i)
            row(c, p, "srch-pause", "fault", "frontend", ["log:template:common", "metric:cpu:spike_up"] + (["span:HTTP_GET:present"] if p == "full" else []), "search")
            row(c, p, "srch-pause", "fault", "reservation", ["metric:cpu:?"], "search")
            row(c, p, "srch-pause", "fault", "geo", ["log:exception:Boom"], "search")
            c = "%s/nf%d" % (p, i)
            row(c, p, "no-fault-cost", "pseudo", "frontend", ["log:template:common"] + (["span:HTTP_GET:present"] if p == "full" else []))
            row(c, p, "no-fault-cost", "pseudo", "reservation", ["metric:cpu:spike_up"] if i == 0 else [])
            row(c, p, "no-fault-cost", "pseudo", "geo", [])
    row("apw/x", "auth-persistence-webui", "res-pause", "fault", "frontend", ["log:level:error"], "reservation", label=APW)
    vocab = {"FX": {"admissibilityShare": 0.05,
                    "noFaultWindows": {"frontend/window": 8, "reservation/window": 8, "geo/window": 8},
                    "symbolNoFaultWindows": {"frontend/window": {"log:template:common": 8}, "reservation/window": {"metric:cpu:spike_up": 2, "metric:cpu:spike_down": 1}},
                    "templatesNoFaultCells": {"frontend": {"log:template:common": 8}}}}
    return rows, vocab


def self_check():
    rows, vocab = _fixture_rows()
    G = Generation("FX", rows, vocab["FX"])
    assert G.span_posture == "full" and G.regimes == ["res-pause", "srch-pause"] and G.postures == ["full", "none"], (G.span_posture, G.regimes, G.postures)
    assert G.apw_rows == 1 and len(G.episodes("res-pause", ("full",))) == 4 and len(G.episodes("res-pause", G.postures)) == 8
    # firing rule: present / ? / exception-only never fire; inadmissible template does not fire; rate:high fires it (R2)
    fe = G.fault["full/res0"]["frontend"]
    assert G.firing(fe) == {"log:frontend:aaa", "span:frontend:HTTP_GET"}, G.firing(fe)
    assert G.firing(G.fault["full/srch0"]["reservation"]) == set()
    assert G.firing(G.fault["full/srch0"]["geo"]) == set()                     # exception class belongs to no sensor (R1)
    assert G.firing(G.fault["full/srch0"]["frontend"]) == {"metric:frontend:cpu"}  # `common` inadmissible (8/8 > floor(0.4))
    assert G.firing(G.fault["full/srch0"]["frontend"], admissibility=False) == {"metric:frontend:cpu", "log:frontend:common"}
    rated = dict(fe, symbols=fe["symbols"] + ["log:rate:common:high"])
    assert "log:frontend:common" in G.firing(rated)
    # planted defect: metric admissibility must bite when the vocab says so (spike_down 1/8 > floor(0.05*8) = 0)
    assert G.firing(G.fault["full/res0"]["reservation"]) == {"span:reservation:Check"}, G.firing(G.fault["full/res0"]["reservation"])
    # symbol table: denominators, exclusions, FA
    T = count_table(G, ["log:level:error", "metric:cpu:spike_up"], lambda i: None, G.postures_for, None, symbol_in_row)
    d = T["log:level:error"]["classes"]["res-pause"]
    assert (d["frontend"]["k"], d["frontend"]["n"], d["*"]["k"], d["*"]["n"], d["*"]["fa"], d["*"]["n0"]) == (8, 8, 8, 8, 0, 8), d
    assert d["geo"]["n"] == 4 and d["geo"]["excluded"] == 4, d["geo"]
    d = T["metric:cpu:spike_up"]["classes"]["srch-pause"]["*"]
    assert (d["k"], d["n"], d["fa"], d["n0"]) == (8, 8, 2, 8), d
    Ts = count_table(G, ["span:HTTP_GET:error"], lambda i: None, G.postures_for, None, symbol_in_row)["span:HTTP_GET:error"]["classes"]["res-pause"]["*"]
    assert (Ts["k"], Ts["n"], Ts["n0"]) == (4, 4, 4), Ts                        # span: full posture only (R6)
    # sensor aggregates
    sir = sensor_in_row_factory(G)
    S = count_table(G, sensor_items(G), lambda i: None, G.postures_for, None, sir)
    assert S["log:*"]["classes"]["res-pause"]["*"]["k"] == 8 and S["log:*"]["classes"]["srch-pause"]["*"]["k"] == 0
    assert S["metric:*"]["classes"]["res-pause"]["*"]["k"] == 4                # geo's spike_up (no vocab entry: admissible) in the 2 cells per posture that have a geo row
    # combinations: log:frontend:aaa and span:frontend:HTTP_GET both fire in 4/4 -> redundant; metric+log union
    cb = combinations(G)
    e = cb["classes"]["res-pause"]
    pr = {(p["a"], p["b"]): p for p in e["pairs"]}
    assert pr[("log:frontend:aaa", "span:frontend:HTTP_GET")]["redundant"] and pr[("log:frontend:aaa", "span:frontend:HTTP_GET")]["conj"] == 4
    assert cb["triplesComputed"]
    # MI: a symbol that separates res-pause from everything else perfectly
    mi = mutual_information(G)
    obs = [(True, "a")] * 4 + [(False, "b")] * 4
    assert abs(mi_bits(obs) - 1.0) < 1e-9
    assert mi["log:level:error"]["frontend"]["bits"] > mi["log:template:common"]["frontend"]["bits"] == 0.0
    # R(p): G2 removes the target's sensors; G4 count; optimum
    eps = build_R(G)
    r0 = next(e for e in eps if e["cell"] == "full/res0")
    assert r0["R"] == ["log:frontend:aaa", "metric:geo:cpu", "span:frontend:HTTP_GET"] and r0["G2removed"] == ["span:reservation:Check"], r0
    s0 = next(e for e in eps if e["cell"] == "full/srch0")
    assert s0["R"] == ["metric:frontend:cpu"] and s0["metricWithoutLog"] and s0["G3removed"] == ["log:frontend:common"], s0
    opt = optimum(eps)
    assert opt["perK"][1]["f_all"] == 4 and opt["perK"][1]["f_any"] == 4 and opt["perK"][4]["f_all"] == 8, opt
    # G4 synthetic (DEFINITIONS): metric event, no log event -> R has metric and no log
    assert "metric" in s0["composition"] and "log" not in s0["composition"]
    # provenance: a manifest sha that is not the committed symptoms.py is refused
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "manifest.json").write_text(json.dumps({"script": "0" * 64}))
        for n in ("bags.jsonl", "vocab.json", "summary.json"):
            (d / n).write_text("{}" if n.endswith(".json") else "")
        try:
            load_bags(d, require_commit=False)
            raise AssertionError("sha mismatch not refused")
        except SystemExit as ex:
            assert "refusing" in str(ex)
    # rendering and JSON round-trip on the fixture
    out = {"generatedAt": "fx", "bagDir": "fx", "provenance": {"scriptSha": "x", "committedSha": "x"}, "frameworkCommit": None, "python": "x",
           "p1": {"passed": True, "report": {"hotel": {}, "teastore": {}, "mismatches": []}}, "generations": {}, "predictions": {}}
    gd = {"_G": G, "episodesPerClassPosture": {}, "pseudoPerPosture": {}, "pseudoPerClass": {}, "exceptionOnlyRows": 0,
          "symbols": {"pooled": T, "perPosture": {}}, "sensors": {"pooled": S, "perPosture": {}}, "combinations": cb, "mi": mi,
          "R": {"n": len(eps), "episodes": eps, "sizeDist": {}, "distinct": 2, "empty": 0, "g4": 4, "compositionPerClass": {}, "g2PerClass": {}, "g3PerClass": {},
                "optimum": opt, "optimumPlus": optimum(eps, "Rplus")}, "tbcFlags": []}
    out["generations"]["FX"] = gd
    text = render(out)
    assert "| `log:level:error` | full+none | 8/8 (0/8) | 0/8 (0/8) |" in text, text
    json.dumps(strip_private(out), default=list)
    print("self-check ok")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bags", nargs="?", help="a tmp/s4-symptoms/<stamp>/ directory")
    ap.add_argument("--out", default="tmp/s4-relevance", help="output root; a new <utc-stamp>/ dir is created under it")
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--replication", action="store_true", help="fresh run, not the sprint population: report P1 without gating (S-B)")
    ap.add_argument("--no-commit-check", action="store_true", help="skip the git HEAD comparison (tests)")
    a = ap.parse_args(argv)
    if a.self_check:
        self_check()
        return
    if not a.bags:
        ap.error("bags directory required")
    run(a)


if __name__ == "__main__":
    main()
