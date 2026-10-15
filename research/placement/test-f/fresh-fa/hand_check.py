#!/usr/bin/env python3
"""POST HOC hand cross-check of fresh_fa_f.py: re-derive one cell's metric series from the RAW otelcol.log with a small parser written
here (not the adapter's), and count the samples beyond the spike threshold. The level m and threshold thr per sensor are taken from
the reader's fit (out/reader_detail.json, written by reader_detail.py), the series, the window and the count are independent.

    uv run python research/placement/test-f/fresh-fa/hand_check.py <cell dir> <sensor id> [--detail out/reader_detail.json]

Series rules re-stated from adapter.metric_series (module docstring there): a monotonic cumulative Sum -> per attribute-set rate between
consecutive exports (same StartTimestamp), summed over attribute sets at the later export time; a Gauge -> the value, summed over
attribute sets at each export time. Only resources with service.name = kafka.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PFX = re.compile(r"^otelcol-1\s+\|\s?")
TS = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?) \+0000 UTC")


def epoch(s):
    m = TS.search(s)
    d = m.group(1)
    frac = 0.0
    if "." in d:
        d, f = d.split(".")
        frac = float("0." + f)
    return datetime.strptime(d, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() + frac


def raw_series(path, metric, service="kafka"):
    """[(t, x)] of `metric` of resource service.name == service, straight from the debug exporter text."""
    pts = defaultdict(list)          # attrs -> [(ts, start, value)]
    kind, mono, svc, name, attrs, ts, start = None, False, None, None, [], None, None
    in_res = in_attr = False
    cum = {}
    with open(path, errors="replace") as fh:
        for raw in fh:
            s = PFX.sub("", raw.rstrip("\n")).strip()
            if s.startswith("ResourceMetrics #"):
                svc, in_res, name = None, False, None
            elif s.startswith("Resource attributes:"):
                in_res = True
            elif in_res and s.startswith("-> service.name:"):
                svc = s.split("Str(", 1)[1].rstrip(")")
            elif s.startswith("ScopeMetrics #"):
                in_res = False
            elif s.startswith("Metric #"):
                name = None
            elif s.startswith("-> Name:"):
                name = s.split(":", 1)[1].strip()
            elif s.startswith("-> DataType:"):
                kind = s.split(":", 1)[1].strip()
            elif s.startswith("-> IsMonotonic:"):
                mono = s.split(":", 1)[1].strip() == "true"
            elif s.startswith("-> AggregationTemporality:"):
                cum[name] = s.split(":", 1)[1].strip() == "Cumulative"
            elif s.startswith("NumberDataPoints #"):
                attrs, in_attr = [], False
            elif s == "Data point attributes:":
                in_attr = True
            elif in_attr and s.startswith("->"):
                attrs.append(s)
            elif s.startswith("StartTimestamp:"):
                in_attr, start = False, epoch(s)
            elif s.startswith("Timestamp:"):
                ts = epoch(s)
            elif s.startswith("Value:") and name == metric and svc == service:
                pts[("|".join(attrs))].append((ts, start, float(s.split(":", 1)[1])))
                pts["__meta__"] = (kind, mono, cum.get(name))
    kind, mono, cumulative = pts.pop("__meta__")
    acc = defaultdict(float)
    for rows in pts.values():
        rows.sort()
        if kind == "Sum" and mono and cumulative:
            for (ta, sa, va), (tb, sb, vb) in zip(rows, rows[1:]):
                if tb > ta and sb == sa and vb >= va:
                    acc[tb] += (vb - va) / (tb - ta)
        else:
            for t, _, v in rows:
                acc[t] += v
    return sorted(acc.items())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cell")
    ap.add_argument("sensor")
    ap.add_argument("--detail", default=str(Path(__file__).resolve().parent / "out/reader_detail.json"))
    a = ap.parse_args(argv)
    _, svc, metric = a.sensor.split(":", 2)
    det = json.loads(Path(a.detail).read_text())[a.sensor]
    cell = next(c for c in det if c["cell"].endswith(Path(a.cell).name))
    m = cell["lvl"][0]
    thr = cell["rules"]["spike"]["thr"]["up"]
    ser = raw_series(Path(a.cell) / "otelcol.log", metric, svc)
    win = [(t, x) for t, x in ser if cell["t0wall"] <= t <= cell["endwall"]]
    up = [(t, x) for t, x in win if x - m > thr]
    down = [(t, x) for t, x in win if m - x > thr]
    print(json.dumps({"cell": Path(a.cell).name, "sensor": a.sensor, "rawSamplesInWindow": len(win), "readerSamplesInWindow": cell["n"],
                      "m": m, "spikeThr": thr, "rawMin": min(x for _, x in win), "rawMax": max(x for _, x in win),
                      "rawBeyondUp": len(up), "rawBeyondDown": len(down),
                      "readerSpikeAlarms": len(cell["rules"]["spike"]["alarms"]),
                      "firstBeyond": (up + down)[:5]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
