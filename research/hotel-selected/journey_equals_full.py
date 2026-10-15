#!/usr/bin/env python3
"""Offline check (2026-09-29, before any selected-posture code): on lmt2, does tracing only the services the GET /hotels
workload reaches equal `full`?  Per full cell: spans per service.  Per cost block: per-service CPU-s delta metrics->full
(the step that switches tracing on), split into journey and idle services.  Usage: journey_equals_full.py <x dir>"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

x = Path(sys.argv[1])
spans, cells = Counter(), 0
for a in sorted((x / "runs").glob("**/p*-full/attempt-01")):
    cells += 1
    spans.update(e["service"] for e in json.loads((a / "traces-normalized.json").read_text())["events"])
journey = sorted(spans)
print("full cells:", cells, "| spans per service (all full cells):", dict(sorted(spans.items())))

cpu = defaultdict(dict)   # block -> posture -> {service: cpu-s}
for a in sorted((x / "runs" / "cost").glob("b*/p*-*/attempt-01")):
    cpu[a.parts[-3]][a.parts[-2].split("-", 1)[1]] = json.loads((a / "cost-cgroup.json").read_text())["containersCpuSeconds"]
services = sorted(next(iter(cpu.values()))["full"])
idle = [s for s in services if s not in spans]
print("services with 0 spans in every full cell:", idle)
for b, p in sorted(cpu.items()):
    d = {s: p["full"][s] - p["metrics"][s] for s in services}
    print(b, "metrics->full CPU-s  journey %+.3f  idle %+.3f  | idle per service %s" % (
        sum(d[s] for s in journey if s in d), sum(d[s] for s in idle),
        {s: round(d[s], 3) for s in idle}))
