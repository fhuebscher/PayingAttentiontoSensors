"""Windows and window vectors.

A window is `{"kind", "index", "bounds": {clock: (lo, hi)}, "hiOpen": bool}`; kinds:
  fault  the fault cell's hold (receipt / intervention bounds, both clocks);
  pseudo a no-fault cell's window at the population's median fault offsets (the old rule's G3 calibration window);
  tile   non-overlapping sub-windows of a cell, of the hold's length, from the barrier (the new rule's no-fault windows);
  pre    the cell's own pre-window [t0, fault start) (old rule baseline, and the new rule's fallback), upper edge open.
Engineering defaults (recorded):
- membership is inclusive at both edges (symptoms.in_window) except `pre` (upper edge open, symptoms.metric_symbols);
- a log window's lower edge is floored to the whole second (symptoms.log_symbols whole_seconds=True): log stamps have
  1 s resolution in Hotel, so a record stamped in the window's first second counts. Applied to every SUT and window
  kind except `pre`. Consequence (ledger row): log counts span up to 1 s more than the window that
  catch.window_stats normalises by (about 7 % at a 15 s hold), and adjacent tiles share that second;
- tiles start at the barrier in each clock, length = the population's median fault hold, and stop at
  base + duration (a partial last tile is dropped, except one that overruns the end by < 0.1 % of its length: Hotel
  int1's hold is 15.0002 s, and 120 / 15.0002 would otherwise drop the eighth tile); tiles of one cell are NOT independent (n_eff is stated per cell
  and per window everywhere it is used).
A vector row (written to vectors.jsonl) is `{cell, window{kind,index,start,end,clock}, service, channel, token, count,
median, mad, min, max, resolution}`; the in-memory row also keeps `values` (never written).
"""
import math

from .events import robust


TILE_OVERRUN = 1e-3     # a last tile overrunning the measurement end by < 0.1 % of its length is kept


def window(kind, index, bounds, hi_open=False):
    return {"kind": kind, "index": index, "bounds": bounds, "hiOpen": hi_open}


def select(stream, w):
    lo, hi = w["bounds"].get(stream.meta["clock"], (None, None))
    if hi is None:
        return []
    if stream.channel == "log" and w["kind"] != "pre" and lo is not None:
        lo = float(int(lo))
    return stream.select(lo, hi, hi_open=w["hiOpen"])


def fault_window(cell):
    return window("fault", 0, dict(cell["fault"]))


def pre_window(cell, start_bounds):
    """[t0, start) per clock; start_bounds = {clock: (start, _)}."""
    return window("pre", 0, {c: (cell["t0"].get(c), b[0]) for c, b in start_bounds.items()}, hi_open=True)


def pseudo_window(cell, offsets):
    return window("pseudo", 0, {c: (cell["base"][c] + a, cell["base"][c] + b) for c, (a, b) in offsets.items()
                                if c in cell["base"]})


def tiles(cell, length):
    n = int(math.floor(cell["duration"] / length + TILE_OVERRUN))
    return [window("tile", i, {c: (cell["base"][c] + i * length, cell["base"][c] + (i + 1) * length)
                               for c in cell["base"]}) for i in range(n)]


def summary(values):
    if not values:
        return {"count": 0, "median": None, "mad": None, "min": None, "max": None}
    m, mad = robust(values)
    return {"count": len(values), "median": m, "mad": mad, "min": min(values), "max": max(values)}


def vector_rows(cell, streams, w, keep_values=False):
    out = []
    for (ch, svc, tok), s in sorted(streams.items()):
        vals = select(s, w)
        b = w["bounds"].get(s.meta["clock"])
        r = {"cell": cell["cell"], "window": {"kind": w["kind"], "index": w["index"], "clock": s.meta["clock"],
                                              "start": b[0] if b else None, "end": b[1] if b else None},
             "service": svc, "channel": ch, "token": tok, "resolution": s.meta["resolution"]}
        r.update(summary(vals))
        if keep_values:
            r["values"] = vals
        out.append(r)
    return out


def channel_counts(cell, streams, w):
    """{channel key: records in w, or `—` when the cell did not retain that channel}. Channel keys are the parser's
    (`log`, `span`, `ledger`, `metric` or `metric:<collector>`). Absence is not zero: a missing file is `—`, a present
    channel with nothing in the window is 0."""
    out = {}
    for key, ch in sorted(cell["channels"].items()):
        if not ch.get("present"):
            out[key] = "—"
            continue
        channel, _, collector = key.partition(":")
        n = 0
        for (c, _, _), s in streams.items():
            if c == channel and (not collector or s.meta.get("collector") == collector):
                n += len(select(s, w))
        out[key] = n
    return out
