"""OTel load pilot: the declared manifestation criterion, applied once per rate.

Rules: research/traffic-sweep/DECLARATION_PILOT_LOAD_OTEL.md ("Manifestation criterion", its engineering defaults, and
"Review fixes" S1/S2). Written before any pilot cell exists and committed before it is run on them.

Per cell: spans from otelcol.log selected by start time; pre-onset [onset - 60 s, onset), hold [onset, onset + hold).
Server = productcatalogservice / oteldemo.ProductCatalogService/GetProduct / Server; client = frontend /
grpc.oteldemo.ProductCatalogService/GetProduct / Client; every status. Ratio = median(hold) / median(pre); a segment
with fewer than MIN_SPANS spans gives None (`—`). Onset: intervention.json freeze.commandIssuedOffsetSeconds in a fault
cell, the execution package's timing.scoredWindowSeconds[0] in a no-fault cell; wall clock = request-ledger barrierEpoch
+ offset.

Per rate: `manifests` iff both valid throttle cells have server ratio >= 2.0 and client ratio >= 1.25 and the valid
no-fault cell has server ratio < 2.0 and client ratio < 1.25; `—` with fewer than 2 valid throttle cells, no valid
no-fault cell, or any ratio None; else `does not manifest`. Valid (S1) = receipt state `valid` and the cell's run ID in
--replayed-valid (the offline validate_cell replay), or every cell under --terminal-valid.

Usage: manifestation_pilot.py <campaign root> (--terminal-valid | --replayed-valid RUNID ...) --out <NEW .json>
"""
import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

SERVER = ("productcatalogservice", "oteldemo.ProductCatalogService/GetProduct", "Server")
CLIENT = ("frontend", "grpc.oteldemo.ProductCatalogService/GetProduct", "Client")
PRE_SECONDS = 60.0
SERVER_RATIO = 2.0
CLIENT_RATIO = 1.25
MIN_SPANS = 20  # declaration S2, engineering default


def _epoch(text):
    """'2026-10-11 01:39:21.70747085 +0000 UTC' -> float seconds (nanosecond digits kept)."""
    date, clock = text.split()[:2]
    whole, _, frac = clock.partition(".")
    base = dt.datetime.strptime(date + " " + whole, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
    return base.timestamp() + (int(frac.ljust(9, "0")[:9]) / 1e9 if frac else 0.0)


def spans(log_path):
    """Yield (service, name, kind, start, end) for every span in a collector debug-exporter log."""
    service = span = None
    for raw in Path(log_path).open(errors="replace"):
        line = raw.split("|", 1)[1].strip() if "|" in raw else raw.strip()
        if line.startswith("-> service.name: Str("):
            service = line[len("-> service.name: Str("):-1]
        elif line.startswith("Span #"):
            span = {}
        elif span is not None and ":" in line:
            key, _, val = line.partition(":")
            span[key.strip()] = val.strip()
            if key.strip() == "End time":
                if {"Name", "Kind", "Start time"} <= span.keys():
                    yield service, span["Name"], span["Kind"], _epoch(span["Start time"]), _epoch(span["End time"])
                span = None


def ratios(log_path, onset, hold):
    seg = {SERVER: ([], []), CLIENT: ([], [])}
    for svc, name, kind, start, end in spans(log_path):
        key = (svc, name, kind)
        if key in seg:
            if onset - PRE_SECONDS <= start < onset:
                seg[key][0].append(end - start)
            elif onset <= start < onset + hold:
                seg[key][1].append(end - start)
    out = {}
    for label, key in (("server", SERVER), ("client", CLIENT)):
        pre, hld = seg[key]
        r = None
        if len(pre) >= MIN_SPANS and len(hld) >= MIN_SPANS and statistics.median(pre) > 0:
            r = statistics.median(hld) / statistics.median(pre)
        out[label] = {"ratio": r, "preSpans": len(pre), "holdSpans": len(hld),
                      "preMedianMs": statistics.median(pre) * 1e3 if pre else None,
                      "holdMedianMs": statistics.median(hld) * 1e3 if hld else None}
    return out


def rate_verdict(cells):
    thr = [c for c in cells if c["kind"] == "throttle" and c["valid"]]
    nof = [c for c in cells if c["kind"] == "no-fault" and c["valid"]]
    if len(thr) < 2 or not nof:
        return "—"
    rs = [c["ratios"][k]["ratio"] for c in thr + nof[:1] for k in ("server", "client")]
    if any(r is None for r in rs):
        return "—"
    hit = all(c["ratios"]["server"]["ratio"] >= SERVER_RATIO and c["ratios"]["client"]["ratio"] >= CLIENT_RATIO for c in thr)
    quiet = nof[0]["ratios"]["server"]["ratio"] < SERVER_RATIO and nof[0]["ratios"]["client"]["ratio"] < CLIENT_RATIO
    return "manifests" if hit and quiet else "does not manifest"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--terminal-valid", action="store_true")
    g.add_argument("--replayed-valid", nargs="*")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    if out.exists():
        sys.exit("refusing: %s exists" % out)
    root = Path(a.root)
    pkg = json.loads((root / ".controller" / "execution-package.json").read_text())
    timing = {c["runId"]: c.get("timing", {}) for c in pkg["cells"]}
    cells = []
    for receipt in sorted(root.glob("runs/**/receipt.json")):
        d = receipt.parent
        rc = json.loads(receipt.read_text())
        run_id = rc.get("runId")
        throttle = "cpu-throttle" in d.as_posix()
        if throttle:
            onset_off = json.loads((d / "intervention.json").read_text())["freeze"]["commandIssuedOffsetSeconds"]
        else:
            onset_off = timing[run_id]["scoredWindowSeconds"][0]
        hold = float(timing[run_id].get("holdSeconds", 60))
        barrier = json.loads((d / "request-ledger.json").read_text())["barrierEpoch"]
        valid = rc.get("state") == "valid" and (a.terminal_valid or run_id in (a.replayed_valid or []))
        cells.append({"cell": d.relative_to(root).as_posix(), "runId": run_id, "rate": d.name.split("-")[0],
                      "kind": "throttle" if throttle else "no-fault", "valid": valid, "receiptState": rc.get("state"),
                      "onsetOffsetSeconds": onset_off, "ratios": ratios(d / "otelcol.log", barrier + onset_off, hold)})
    rates = sorted({c["rate"] for c in cells}, key=lambda r: float(r[1:].replace("p", ".")))
    res = {"criterion": "DECLARATION_PILOT_LOAD_OTEL.md", "root": str(root), "cells": cells,
           "verdict": {r: rate_verdict([c for c in cells if c["rate"] == r]) for r in rates}}
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    for r in rates:
        print(r, res["verdict"][r])


if __name__ == "__main__":
    main()
