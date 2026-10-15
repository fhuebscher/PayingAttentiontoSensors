"""One catch rule over window vectors, in two parameterisations, plus G3.

NEW rule (protocol draft 3 §2, PLAN part 2; the one to be accepted at the gate):
  baseline = the no-fault windows (tiles) of the SAME (population, posture), leave-one-cell-out when the window being
  scored is itself a no-fault tile; per sensor `channel:service:token`:
  - appear     count > 0 and the token occurs in no baseline window (not in the vocabulary);
  - disappear  count == 0, the cell collects the channel, and the baseline per-window median count >= 1;
  - move       a window statistic outside median ± max(K·1.4826·MAD, floor) of the same statistic over the baseline
               windows: `count` for every channel except metric (a metric's sample count is the sampler cadence, not
               signal), and `level` = window median value (metric value, span duration, ledger `:ok` latency);
               fewer than MIN_BASELINE baseline windows IN WHICH THE TOKEN HAS A LEVEL (the level is undefined in a
               tile without records) -> fallback to the cell's own pre-window (level only: the window median against
               the pre-window samples, i.e. the old plateau rule); fewer than MIN_BASELINE pre-window samples -> no
               verdict (`?`, never a catch). For a no-fault tile scored in G3 the pre-window is [t0, tile start),
               empty for tile 0. On the retained evidence of 2026-10-02 the fallback was never used (0 of 2,522
               catches), because every level token had >= 3 tiles with records.
  There is NO spike detector in the new rule: `move` compares the window median only. The old rule's single-sample
  spike_up/spike_down are not carried over (rule choice owed to the user, README note 3).
  appear / disappear need >= 1 baseline window (not MIN_BASELINE); count and level moves need >= MIN_BASELINE.
  Comparisons are inclusive (`>=` the threshold), as symptoms.py.
  G3: every no-fault tile is scored the same way against the other cells' tiles; a sensor that fires in k of n_eff
  tiles is inadmissible iff k > TAU·n_eff (lmt_detect.py:151 arithmetic). Reported as k/n_eff with the number of
  distinct cells behind n_eff (tiles of one cell are not independent). n_eff = 0 -> `admissible: null` (not reported
  as admissible); a token absent from every tile gets k = 0 of the channel's n_eff (run.py), never `g3: null`.
  Floors: count 2 (symptoms.BURST_FLOOR); span latency 1 ms (symptoms.LAT_FLOOR_S); ledger latency 1 ms
  (ledger_check.py); metrics as `floor()` below (symptoms.FLOOR, lmt_detect.SYS_FLOORS, else 2 % of the baseline
  median, symptoms.MEM_REL_FLOOR). K = 4 (symptoms.K). The ledger is scored on the same K × floor grid as the sensors
  (draft 3, decision 9).

OLD rule (the oracle's, for the replay against MAP_TABLE.md only): per sensor against the cell's OWN pre-window,
  exactly as symptoms.{log,metric,span}_symbols + lmt_detect.family + relevance.sensor_of read them:
  log template present; metric spike/plateau up/down at K·1.4826·MAD vs pre (MIN_BASELINE pre samples, else `?`);
  span error / latency_high / missing_expected per operation; ledger (pooled over routes) failed in window or
  in-window median > ok-pre median + max(3·raw MAD, 1 ms) (ledger_check.py; raw MAD, not 1.4826-scaled);
  TeaStore logs additionally `rate:high` (count vs leave-one-cell-out no-fault pseudo windows, floor 2,
  symptoms.calibrate). G3 per family over the pseudo windows of the family's posture set.
"""
import statistics
from collections import Counter, defaultdict

from .events import robust, sensor_id
from .parsers import common
from .vectors import select

K = 4.0
TAU = 0.05
MIN_BASELINE = 3
COUNT_FLOOR = 2.0
LAT_FLOOR_S = 0.001
LEDGER_FLOOR_MS = 1.0
OLD_LEDGER_K = 3.0          # ledger_check.py: max(3 x MAD, 1 ms), raw MAD
MEM_REL_FLOOR = 0.02


def metric_floor(resource, baseline_median):
    S = common.symptoms()
    L = common.lmt()
    if resource in L.SYS_FLOORS:
        return L.SYS_FLOORS[resource]
    if resource in S.FLOOR:
        return S.FLOOR[resource]
    return MEM_REL_FLOOR * abs(baseline_median)


def level_floor(channel, token, baseline_median):
    if channel == "metric":
        return metric_floor(token, baseline_median)
    if channel == "span":
        return LAT_FLOOR_S
    if channel == "ledger":
        return LEDGER_FLOOR_MS
    return None


def has_level(channel, token):
    if channel == "metric":
        return True
    if channel == "span":
        return not token.endswith(":error")
    if channel == "ledger":
        return token.endswith(":ok")
    return False


def threshold(values, floor, k=K, scale=1.4826):
    m, mad = robust(values)
    return m, max(k * scale * mad, floor)


# =========================================================================== OLD rule (oracle replay)

def old_sensor_name(channel, token):
    if channel == "span" and token.endswith(":error"):
        return token[:-len(":error")]
    return token


def old_fire(cell, streams, w, pre):
    """{(channel, service, name): set(kinds)} for one window, oracle semantics. Ledger handled by old_ledger."""
    out = defaultdict(set)
    spans = defaultdict(dict)
    for (ch, svc, tok), s in streams.items():
        if ch == "log":
            if select(s, w):
                out[(ch, svc, tok)].add("present")
        elif ch == "metric":
            p = select(s, pre)
            x = select(s, w)
            if len(p) < MIN_BASELINE or not x:
                continue
            m, mad = robust(p)
            thr = max(K * 1.4826 * mad, metric_floor(tok, m))
            if any(v - m >= thr for v in x):
                out[(ch, svc, tok)].add("spike_up")
            if any(m - v >= thr for v in x):
                out[(ch, svc, tok)].add("spike_down")
            if len(x) >= MIN_BASELINE:
                mi = statistics.median(x)
                if mi - m >= thr:
                    out[(ch, svc, tok)].add("plateau_up")
                if m - mi >= thr:
                    out[(ch, svc, tok)].add("plateau_down")
        elif ch == "span":
            spans[(svc, old_sensor_name(ch, tok))][tok.endswith(":error")] = s
    for (svc, op), d in spans.items():
        s = d.get(False)
        if s is None:
            continue
        ins = select(s, w)
        p = select(s, pre)
        if ins:
            if d.get(True) is not None and select(d[True], w):
                out[("span", svc, op)].add("error")
            if len(p) >= MIN_BASELINE:
                m, mad = robust(p)
                if statistics.median(ins) - m >= max(K * 1.4826 * mad, LAT_FLOOR_S):
                    out[("span", svc, op)].add("latency_high")
        elif p:
            out[("span", svc, op)].add("missing_expected")
    return out


def old_ledger(streams, w, pre, k=OLD_LEDGER_K, scale=1.0, floor=LEDGER_FLOOR_MS):
    """ledger_check.cell's rule over the ledger streams pooled across routes. None = unknown (no ok pre request or no
    request in the window), as visibility.ledger_rule."""
    pre_ok, inside, failed = [], [], 0
    for (ch, svc, tok), s in streams.items():
        if ch != "ledger":
            continue
        x = select(s, w)
        inside += x
        if tok.endswith(":ok"):
            pre_ok += select(s, pre)
        else:
            failed += len(x)
    if not pre_ok or not inside:
        return None
    m, mad = robust(pre_ok)
    in_med = statistics.median(inside)
    return {"inWindow": len(inside), "failedInWindow": failed, "preMedianMs": m, "inMedianMs": in_med,
            "shows": failed > 0 or in_med > m + max(k * scale * mad, floor)}


def old_rate_high(log_counts, nf_counts_by_cell, own_cell):
    """symptoms.calibrate's `log:rate:<tid>:high`: count - m >= max(K·1.4826·MAD, 2) over the no-fault pseudo windows
    of other cells (absent = 0), needs >= 3 of them. log_counts {(svc, tid): n}; nf_counts_by_cell {cell: {svc: {tid: n}}}
    restricted to cells whose stream for svc exists."""
    out = set()
    for (svc, tid), n in log_counts.items():
        hist = [c.get(svc, {}).get(tid, 0) for cell, c in nf_counts_by_cell.items() if cell != own_cell and svc in c]
        if len(hist) >= MIN_BASELINE:
            m, thr = threshold(hist, COUNT_FLOOR)
            if n - m >= thr:
                out.add(("log", svc, tid))
    return out


def g3_inadmissible(fired_by_window, tau=TAU):
    """fired_by_window: list of sets of sensors (one per no-fault window). Returns (inadmissible set, counts, n)."""
    n = len(fired_by_window)
    counts = Counter(x for f in fired_by_window for x in f)
    return {x for x, k in counts.items() if n and k > tau * n}, counts, n


# =========================================================================== NEW rule

class Baseline:
    """No-fault tile statistics of one (population, posture): one entry per tile of every no-fault cell,
    `(cell, index, channels present, {(ch, svc, tok): (count, level, meta)})`. A token absent from a tile whose cell
    has the channel counts 0 there (absence of a record in a collected channel is a measured zero)."""

    def __init__(self, posture):
        self.posture = posture
        self.tiles = []
        self._keys = set()

    def add(self, cell_id, index, channels_present, rows):
        self.tiles.append((cell_id, index, frozenset(channels_present), rows))
        self._keys |= set(rows)

    def keys(self):
        return self._keys

    def windows(self, channel, exclude_cell=None):
        return [t for t in self.tiles if channel in t[2] and t[0] != exclude_cell]

    def view(self, key, exclude_cell=None):
        out = []
        for c, _, _, rows in self.windows(key[0], exclude_cell):
            n, lv, _ = rows.get(key, (0, None, None))
            out.append((c, n, lv))
        return out


def window_stats(streams, w, tile_length=None):
    """{(ch, svc, tok): (count, level, meta)} for one window. With tile_length, the count is normalised to it:
    count x tile_length / (window length in that stream's clock), so a 15.06 s hold and 15.0 s tiles compare per second
    (draft 3 §2: counts normalised per second; an open-loop schedule has MAD 0, so an unnormalised count difference of
    two requests from window length alone would cross the floor). Raw counts stay in vectors.jsonl."""
    out = {}
    for k, s in streams.items():
        vals = select(s, w)
        lv = statistics.median(vals) if vals and has_level(k[0], k[2]) else None
        n = len(vals)
        if tile_length and n:
            b = w["bounds"].get(s.meta["clock"])
            if b and b[0] is not None and b[1] > b[0]:
                n = n * tile_length / (b[1] - b[0])
        out[k] = (n, lv, s.meta)
    return out


def new_fire(xstats, base, channels_present, exclude_cell=None, pre_values=None, k=K):
    """Score one window. xstats from window_stats; pre_values {(ch, svc, tok): [values]} for the fallback.
    Returns {(ch, svc, tok): {"kinds": [...], "x": {...}, "baseline": {...}}} for sensors that fire."""
    out = {}
    keys = set(xstats) | {key for key in base.keys() if key[0] in channels_present}
    for key in keys:
        ch, svc, tok = key
        if ch not in channels_present:
            continue
        cnt, lv, _ = xstats.get(key, (0, None, None))
        hist = base.view(key, exclude_cell)
        n = len(hist)
        if n == 0:
            continue
        counts = [c for _, c, _ in hist]
        kinds, info = [], {"n": n, "nCells": len({c for c, _, _ in hist})}
        present = sum(1 for c in counts if c > 0)
        if cnt > 0 and present == 0:
            kinds.append("appear")
        med_c = statistics.median(counts)
        if cnt == 0 and med_c >= 1:
            kinds.append("disappear")
        if ch != "metric" and n >= MIN_BASELINE and (cnt > 0 or present > 0):
            m, thr = threshold(counts, COUNT_FLOOR, k)
            info["count"] = {"median": m, "thr": thr}
            if cnt - m >= thr:
                kinds.append("count_up")
            elif m - cnt >= thr:
                kinds.append("count_down")
        if lv is not None:
            levels = [x for _, _, x in hist if x is not None]
            if len(levels) >= MIN_BASELINE:
                m, thr = threshold(levels, level_floor(ch, tok, statistics.median(levels)), k)
                info["level"] = {"median": m, "thr": thr, "n": len(levels), "basis": "no-fault windows"}
            elif pre_values is not None and len(pre_values.get(key, ())) >= MIN_BASELINE:
                pv = pre_values[key]
                m, thr = threshold(pv, level_floor(ch, tok, statistics.median(pv)), k)
                info["level"] = {"median": m, "thr": thr, "n": len(pv), "basis": "own pre-window (fallback)"}
            else:
                info["level"] = None             # `?`: no verdict
            if info["level"]:
                if lv - info["level"]["median"] >= info["level"]["thr"]:
                    kinds.append("level_up")
                elif info["level"]["median"] - lv >= info["level"]["thr"]:
                    kinds.append("level_down")
        if kinds:
            out[key] = {"kinds": kinds, "x": {"count": cnt, "level": lv}, "baseline": info}
    return out


def g3_loo(base, tiles, k=K, tau=TAU, n_cells=None):
    """G3 for the new rule: every no-fault tile scored against the other cells' tiles. tiles: list of
    (cell_id, chans, xstats, pre_values). Returns {(ch, svc, tok): {"k", "nEff", "nCells", "admissible"}} for every
    baseline key and every key that fired; nEff = tiles of cells that collect the channel."""
    fired_windows = defaultdict(list)
    for cid, chans, st, pv in tiles:
        f = new_fire(st, base, chans, exclude_cell=cid, pre_values=pv, k=k)
        for ch in chans:
            fired_windows[ch].append({kk for kk in f if kk[0] == ch})
    if n_cells is None:
        n_cells = len({t[0] for t in tiles})
    G = {}
    for ch, sets in fired_windows.items():
        n = len(sets)
        cnt = Counter(x for s in sets for x in s)
        for key in {kk for kk in base.keys() if kk[0] == ch} | set(cnt):
            G[key] = {"k": cnt.get(key, 0), "nEff": n, "nCells": n_cells,
                      "admissible": (cnt.get(key, 0) <= tau * n) if n else None}
    return G


def sid(key):
    return sensor_id(*key)
