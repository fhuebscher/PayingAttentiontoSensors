"""OTel off-path pilot: the declared manifestation criteria, applied once to the retained cells.

Rules: research/traffic-sweep/DECLARATION_PILOT_OFFPATH_OTEL.md (frozen in commit 64854c2), section "Manifestation
criteria", plus its cell-validity rule. Written before any pilot cell was read and committed before it is run on them.
Reference implementation of the same rules (mirrored here, never imported at run time): `statistics_of` and `verdict` in
../observability-placement-runtime-otel-protocol/tests/test_otel_offpath_pilot.py (harness 8c53cb2);
tests/test_manifestation_offpath_pilot.py requires identical statistics and verdicts on the same synthetic cells.

Per cell (n = 1 per (fault, rate); a verdict is about that cell): onset = intervention.json
`freeze.commandIssuedOffsetSeconds` in a fault cell, the compiled plan's `timing.scoredWindowSeconds[0]` (pseudo onset)
in the no-fault cell; wall clock = request-ledger.json `barrierEpoch` + onset. Pre-onset [onset - 60 s, onset), hold
[onset, onset + 60 s). Spans from otelcol.log selected by START time, all statuses. A statistic with fewer than 20 items
in a segment is `—`.

Per (fault, rate), `manifests` iff (all of):
- productcatalog-cpu-throttle: median duration of productcatalogservice / oteldemo.ProductCatalogService/GetProduct /
  Server, hold over pre-onset, >= 2.0; same for frontend / grpc.oteldemo.ProductCatalogService/GetProduct / Client >= 1.25;
  the no-fault cell shows neither ratio (server < 2.0 and client < 1.25 at its pseudo onset).
- frontend-pause: of ledger rows (every route) SCHEDULED in [onset, onset + 45 s) at most 10 % ok, and of the
  route=checkout rows SENT in that window (startedAtEpoch - barrierEpoch) at most 10 % ok; the no-fault cell's rows
  scheduled in the same window >= 95 % ok.
- fraud-pause / accounting-pause: Consumer-kind spans of the target service started in the hold <= 10 % of those started
  in the pre-onset 60 s (pre-onset count >= 20); and route=checkout rows scheduled in the hold >= 95 % ok (>= 20 rows);
  and the no-fault cell at its pseudo onset has hold/pre > 10 % for that service and its checkout rows >= 95 % ok.
A cell counts only if its receipt state is `valid` AND an offline validate_cell / terminal replay passed (S1: its run ID is
in --replayed-valid, or --terminal-valid says the terminal's witness check covered every cell); the rate's no-fault cell
must count too, else `—`. A counted no-fault cell that fails its own precondition (checkout rows and all rows in its
pseudo hold >= 95 % ok, each with >= 20 rows) gives `—` for every fault at that rate.

A fault is kept for E iff it manifests at >= 1 rate. E-rate rule (coordinator default, user may veto): the lowest rate at
which every kept fault manifests, else the highest rate at which any does.

Reported, not part of any verdict (declaration N3 cross-check): per cell and route, the ledger rows whose `status`
disagrees with the witness row's `response_code` for the same token, and the witness rows whose `response_flags` is not '-'.

Usage: manifestation_offpath_pilot.py <campaign root> (--terminal-valid | --replayed-valid RUNID ...) --out <NEW .json>
"""
import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

FAULTS = ("productcatalog-cpu-throttle", "frontend-pause", "fraud-pause", "accounting-pause")
CONSUMERS = ("accountingservice", "frauddetectionservice")
CONSUMER_OF = {"fraud-pause": "frauddetectionservice", "accounting-pause": "accountingservice"}
SERVER = ("productcatalogservice", "oteldemo.ProductCatalogService/GetProduct", "Server")
CLIENT = ("frontend", "grpc.oteldemo.ProductCatalogService/GetProduct", "Client")
PRE_SECONDS = 60.0
HOLD_SECONDS = 60.0
FRONTEND_WINDOW_SECONDS = 45.0  # declared; the harness reference derives it as hold - requestTimeoutSeconds (15 s)
MIN_ITEMS = 20  # engineering default
SERVER_RATIO = 2.0
CLIENT_RATIO = 1.25
COLLAPSE_SHARE = 0.10  # consumer hold/pre bound; frontend-pause ok-share bound
OK_SHARE = 0.95
DASH = "—"

_STAMP = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:\.(\d+))? \+0000 UTC")
_SERVICE = re.compile(r"\s*-> service\.name: Str\((.*)\)\s*$")
_SPAN = re.compile(r"\s*Span #\d+\s*$")
_FIELD = re.compile(r"\s+(Name|Kind|Start time|End time)\s+: (.*)$")
_FIELD_KEY = {"Name": "name", "Kind": "kind", "Start time": "start", "End time": "end"}


def parse_stamp(text):
    """'2026-10-11 01:39:21.70747085 +0000 UTC' -> epoch seconds; 0 to 9 fraction digits (the frontend's has 2, .NET's 7)."""
    match = _STAMP.fullmatch(text.strip())
    if not match:
        raise ValueError("unparsable span timestamp %r" % text)
    moment = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return moment.timestamp() + (int(match.group(2)[:9].ljust(9, "0")) / 1e9 if match.group(2) else 0.0)


def iter_spans(log_path):
    """Yield dicts (service, name, kind, start, end) for every complete span of a collector debug-exporter log; the service
    is the service.name of the ResourceSpans block the span sits in; a block lacking a field is skipped."""
    service, current = None, None
    with Path(log_path).open("rb") as handle:
        for raw in handle:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            payload = line.partition("| ")[2] if "| " in line else line
            if current is None and "service.name" not in payload and "Span #" not in payload and "ResourceSpans #" not in payload:
                continue
            match = _SERVICE.match(payload)
            if match:
                service, current = match.group(1), None
                continue
            if payload.startswith("ResourceSpans #"):
                service, current = None, None
            elif _SPAN.match(payload):
                current = {"service": service}
            elif current is not None:
                field = _FIELD.match(payload)
                if field:
                    key = _FIELD_KEY[field.group(1)]
                    current[key] = parse_stamp(field.group(2)) if key in ("start", "end") else field.group(2).strip()
                    if all(k in current for k in ("name", "kind", "start", "end")):
                        yield current
                        current = None


def _median(values):
    return statistics.median(values) if len(values) >= MIN_ITEMS else None


def _ratio(pre, hold):
    """median(hold) / median(pre), or None: fewer than 20 spans in a segment, or a pre-onset median of 0 (undefined)."""
    before, during = _median(pre), _median(hold)
    if before is None or during is None or before == 0:
        return None
    return during / before


def statistics_of(root, scenario, timing):
    """Every statistic of the declared criteria for one cell: (statistics, counts). `statistics` has the keys of the
    harness reference function; `counts` carries the extra numbers a reader needs."""
    root = Path(root)
    ledger = json.loads((root / "request-ledger.json").read_text())
    if scenario is None:
        onset = timing["scoredWindowSeconds"][0]  # the pseudo onset, from the compiled plan
    else:
        onset = json.loads((root / "intervention.json").read_text())["freeze"]["commandIssuedOffsetSeconds"]
    if HOLD_SECONDS - float(timing["requestTimeoutSeconds"]) != FRONTEND_WINDOW_SECONDS:
        raise SystemExit("plan requestTimeoutSeconds %r does not give the declared 45 s window" % timing["requestTimeoutSeconds"])
    barrier_epoch = ledger["barrierEpoch"]
    t0 = barrier_epoch + onset
    pre_window, hold_window = (t0 - PRE_SECONDS, t0), (t0, t0 + HOLD_SECONDS)

    server, client = {"pre": [], "hold": []}, {"pre": [], "hold": []}
    consumer = {service: {"pre": 0, "hold": 0} for service in CONSUMERS}
    parsed = 0
    for span in iter_spans(root / "otelcol.log"):
        parsed += 1
        start = span["start"]
        segment = "pre" if pre_window[0] <= start < pre_window[1] else "hold" if hold_window[0] <= start < hold_window[1] else None
        if segment is None:
            continue
        key = (span["service"], span["name"], span["kind"])
        if key == SERVER:
            server[segment].append(span["end"] - start)
        elif key == CLIENT:
            client[segment].append(span["end"] - start)
        if span["kind"] == "Consumer" and span["service"] in consumer:
            consumer[span["service"]][segment] += 1

    rows = ledger["requests"]
    in_hold = [r for r in rows if onset <= r["scheduledOffsetSeconds"] < onset + HOLD_SECONDS]
    early = [r for r in rows if onset <= r["scheduledOffsetSeconds"] < onset + FRONTEND_WINDOW_SECONDS]
    checkouts = [r for r in in_hold if r["route"] == "checkout"]
    # the frontend-pause checkout rows are selected by SEND time: a checkout waits up to 20 s for its cart POST
    early_checkouts = [r for r in rows if r["route"] == "checkout"
                       and onset <= r["startedAtEpoch"] - barrier_epoch < onset + FRONTEND_WINDOW_SECONDS]

    def tally(selected):
        return {"rows": len(selected), "ok": sum(r["outcome"] == "ok" for r in selected)}

    def spans_block(group):
        return {"pre": len(group["pre"]), "hold": len(group["hold"]),
                "preMedianMs": statistics.median(group["pre"]) * 1e3 if group["pre"] else None,
                "holdMedianMs": statistics.median(group["hold"]) * 1e3 if group["hold"] else None}

    stats = {
        "onset": onset, "consumer": consumer,
        "serverRatio": _ratio(server["pre"], server["hold"]), "clientRatio": _ratio(client["pre"], client["hold"]),
        "checkout": tally(checkouts), "rows": tally(in_hold), "earlyRows": tally(early), "earlyCheckout": tally(early_checkouts),
    }
    counts = {"spansParsed": parsed, "ledgerRows": len(rows), "server": spans_block(server), "client": spans_block(client)}
    return stats, counts


def _share(block):
    return None if block["rows"] < MIN_ITEMS else block["ok"] / block["rows"]


def _pct(value):
    return "?" if value is None else "%.1f %%" % (100 * value)


def verdict(fault, stats, nofault):
    """(verdict, reason) for one fault at one rate from a counted fault cell's statistics and the rate's counted no-fault
    cell's statistics. The reason is for `—` and for `does not manifest`; `manifests` has none."""
    n_checkout, n_rows = _share(nofault["checkout"]), _share(nofault["rows"])
    if n_checkout is None or n_rows is None or min(n_checkout, n_rows) < OK_SHARE:
        return DASH, ("no-fault precondition S2 failed: checkout rows %d (>= %d needed), ok %s; all rows %d, ok %s; both must be >= 95 %%"
                      % (nofault["checkout"]["rows"], MIN_ITEMS, _pct(n_checkout), nofault["rows"]["rows"], _pct(n_rows)))

    if fault in CONSUMER_OF:
        service = CONSUMER_OF[fault]
        pre, during = stats["consumer"][service]["pre"], stats["consumer"][service]["hold"]
        base_pre, base_during = nofault["consumer"][service]["pre"], nofault["consumer"][service]["hold"]
        s_checkout = _share(stats["checkout"])
        if pre < MIN_ITEMS or base_pre < MIN_ITEMS or s_checkout is None:
            return DASH, ("fewer than %d items: %s Consumer spans pre-onset %d, no-fault pre-onset %d, fault-cell hold checkout rows %d"
                          % (MIN_ITEMS, service, pre, base_pre, stats["checkout"]["rows"]))
        effect = during <= COLLAPSE_SHARE * pre
        route_ok = s_checkout >= OK_SHARE
        quiet = base_during > COLLAPSE_SHARE * base_pre and n_checkout >= OK_SHARE
        if effect and route_ok and quiet:
            return "manifests", None
        return "does not manifest", ("consumer spans hold %d / pre %d (need <= 10 %%): %s; checkout ok %s (need >= 95 %%): %s; "
                                     "no-fault hold %d / pre %d (need > 10 %%): %s"
                                     % (during, pre, effect, _pct(s_checkout), route_ok, base_during, base_pre, quiet))
    if fault == "productcatalog-cpu-throttle":
        ratios = (stats["serverRatio"], stats["clientRatio"], nofault["serverRatio"], nofault["clientRatio"])
        if None in ratios:
            return DASH, ("a ratio is undefined (fewer than %d spans in a segment, or a pre-onset median of 0): fault server %s client %s, "
                          "no-fault server %s client %s" % ((MIN_ITEMS,) + tuple("?" if r is None else "%.3f" % r for r in ratios)))
        effect = stats["serverRatio"] >= SERVER_RATIO and stats["clientRatio"] >= CLIENT_RATIO
        quiet = nofault["serverRatio"] < SERVER_RATIO and nofault["clientRatio"] < CLIENT_RATIO
        if effect and quiet:
            return "manifests", None
        return "does not manifest", ("fault server %.3f (>= 2.0) client %.3f (>= 1.25): %s; no-fault server %.3f client %.3f (< 2.0, < 1.25): %s"
                                     % (ratios[0], ratios[1], effect, ratios[2], ratios[3], quiet))
    if fault == "frontend-pause":
        s_rows, s_checkout, n_early = _share(stats["earlyRows"]), _share(stats["earlyCheckout"]), _share(nofault["earlyRows"])
        if s_rows is None or s_checkout is None or n_early is None:
            return DASH, ("fewer than %d rows in the first 45 s: fault-cell rows %d, checkout rows sent %d, no-fault rows %d"
                          % (MIN_ITEMS, stats["earlyRows"]["rows"], stats["earlyCheckout"]["rows"], nofault["earlyRows"]["rows"]))
        effect = s_rows <= COLLAPSE_SHARE and s_checkout <= COLLAPSE_SHARE
        if effect and n_early >= OK_SHARE:
            return "manifests", None
        return "does not manifest", ("first 45 s ok: all rows %s (need <= 10 %%), checkouts sent %s (need <= 10 %%); no-fault rows %s (need >= 95 %%)"
                                     % (_pct(s_rows), _pct(s_checkout), _pct(n_early)))
    raise ValueError(fault)


def e_rate(verdicts, rates):
    """verdicts[fault][rate] -> 'manifests' | 'does not manifest' | '—'. Returns (kept faults, E rate or None, rule applied)."""
    kept = [f for f in FAULTS if any(verdicts[f][r] == "manifests" for r in rates)]
    if not kept:
        return kept, None, "no fault manifests at any rate"
    every = [r for r in sorted(rates) if all(verdicts[f][r] == "manifests" for f in kept)]
    if every:
        return kept, every[0], "lowest rate at which every kept fault manifests"
    anyone = [r for r in sorted(rates) if any(verdicts[f][r] == "manifests" for f in FAULTS)]
    return kept, anyone[-1], "no rate has every kept fault manifesting: highest rate at which any does"


def witness_cross_check(cell_dir):
    """N3, reported only: per route, ledger rows whose status differs from the witness response_code for the same token, and
    witness rows whose response_flags is not '-'."""
    ledger = json.loads((cell_dir / "request-ledger.json").read_text())["requests"]
    witness = json.loads((cell_dir / "application-witness.json").read_text())["rows"]
    route_of = {r["requestToken"]: r["route"] for r in ledger}
    by_token = {}
    for row in witness:
        by_token.setdefault(row["request_token"], row)

    def code(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    routes = {}

    def entry(route):
        return routes.setdefault(route, {"ledgerRows": 0, "statusDisagrees": 0, "witnessFlagsNotDash": 0})

    unwitnessed = 0
    for r in ledger:
        e = entry(r["route"])
        e["ledgerRows"] += 1
        w = by_token.get(r["requestToken"])
        if w is None:
            unwitnessed += 1
        elif r["status"] != code(w["response_code"]):
            e["statusDisagrees"] += 1
    unknown = 0
    for row in witness:
        route = route_of.get(row["request_token"])
        if route is None:
            unknown += 1
            route = "?unknown-token"
        if row.get("response_flags") != "-":
            entry(route)["witnessFlagsNotDash"] += 1
    return {"ledgerRows": len(ledger), "witnessRows": len(witness), "unwitnessedLedgerRows": unwitnessed,
            "unknownWitnessRows": unknown, "byRoute": dict(sorted(routes.items()))}


def analyse(root, valid_run_ids=None):
    """valid_run_ids None = --terminal-valid (the receipt's `valid` is enough); else the offline-replayed run IDs."""
    root = Path(root)
    package = json.loads((root / ".controller" / "execution-package.json").read_text())
    planned = {}
    for c in package["cells"]:
        scenario = (c.get("fault") or {}).get("scenario")
        if scenario is not None and scenario not in FAULTS:
            raise SystemExit("unknown scenario %r in the plan" % scenario)
        planned[c["runId"]] = {"scenario": scenario, "timing": c["timing"], "rate": float(c["timing"]["requestsPerSecond"])}
    receipts = {}
    for receipt in sorted(root.glob("runs/**/receipt.json")):
        run_id = json.loads(receipt.read_text()).get("runId")
        if run_id not in planned:
            raise SystemExit("%s: run ID %r is not in the plan" % (receipt, run_id))
        if run_id in receipts:
            raise SystemExit("run ID %r has two receipts" % run_id)
        receipts[run_id] = receipt.parent

    cells = {}
    for run_id, plan in planned.items():
        d = receipts.get(run_id)
        cell = {"runId": run_id, "fault": plan["scenario"], "rate": plan["rate"], "cell": None, "receiptState": None,
                "valid": False, "invalidReason": None, "statistics": None, "counts": None, "witnessCrossCheck": None}
        if d is None:
            cell["invalidReason"] = "no receipt retained for this planned run"
        else:
            state = json.loads((d / "receipt.json").read_text()).get("state")
            cell.update(cell=d.relative_to(root).as_posix(), receiptState=state)
            if state != "valid":
                cell["invalidReason"] = "receipt state %r, not valid" % state
            elif valid_run_ids is not None and run_id not in valid_run_ids:
                cell["invalidReason"] = "run ID not in --replayed-valid (offline replay did not pass)"
            else:
                cell["valid"] = True
                cell["statistics"], cell["counts"] = statistics_of(d, plan["scenario"], plan["timing"])
                cell["witnessCrossCheck"] = witness_cross_check(d)
        cells[run_id] = cell

    rates = sorted({c["rate"] for c in cells.values()})
    nofault, precondition = {}, {}
    for rate in rates:
        found = [c for c in cells.values() if c["rate"] == rate and c["fault"] is None]
        nofault[rate] = found[0] if len(found) == 1 else None
        n = nofault[rate]
        pre = {"runId": n["runId"] if n else None, "valid": bool(n and n["valid"]), "passes": None}
        if n and n["valid"]:
            s = n["statistics"]
            sc, sr = _share(s["checkout"]), _share(s["rows"])
            pre.update(checkoutRows=s["checkout"]["rows"], checkoutOkShare=sc, rows=s["rows"]["rows"], rowsOkShare=sr,
                       passes=sc is not None and sr is not None and min(sc, sr) >= OK_SHARE)
        precondition[rate] = pre

    results = {f: {} for f in FAULTS}
    for fault in FAULTS:
        for rate in rates:
            found = [c for c in cells.values() if c["rate"] == rate and c["fault"] == fault]
            cell, base = (found[0] if len(found) == 1 else None), nofault[rate]
            out = {"faultRunId": cell["runId"] if cell else None, "noFaultRunId": base["runId"] if base else None}
            if cell is None:
                out.update(verdict=DASH, reason="the plan has no (or more than one) %s cell at this rate" % fault)
            elif not cell["valid"]:
                out.update(verdict=DASH, reason="fault cell does not count: " + cell["invalidReason"])
            elif base is None or not base["valid"]:
                out.update(verdict=DASH, reason="the rate's no-fault cell does not count: "
                           + (base["invalidReason"] if base else "the plan has no (or more than one) no-fault cell at this rate"))
            else:
                v, why = verdict(fault, cell["statistics"], base["statistics"])
                out.update(verdict=v, reason=why)
            results[fault][rate] = out
    kept, chosen, rule = e_rate({f: {r: results[f][r]["verdict"] for r in rates} for f in FAULTS}, rates)
    return {
        "criterion": "research/traffic-sweep/DECLARATION_PILOT_OFFPATH_OTEL.md (64854c2)", "root": str(root),
        "cells": list(cells.values()),
        "noFaultPrecondition": {"%g" % r: precondition[r] for r in rates},
        "verdicts": {f: {"%g" % r: results[f][r] for r in rates} for f in FAULTS},
        "keptForE": {f: f in kept for f in FAULTS},
        "eRate": {"rate": chosen, "rule": rule},
    }


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
    res = analyse(a.root, None if a.terminal_valid else set(a.replayed_valid or []))
    res["validity"] = "terminal-valid" if a.terminal_valid else {"replayed-valid": sorted(a.replayed_valid or [])}
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    for fault in FAULTS:
        for rate, row in res["verdicts"][fault].items():
            print("%-28s %6s  %s" % (fault, rate, row["verdict"]))
    print("kept for E:", [f for f in FAULTS if res["keptForE"][f]], "| E rate:", res["eRate"]["rate"], "(%s)" % res["eRate"]["rule"])


if __name__ == "__main__":
    main()
