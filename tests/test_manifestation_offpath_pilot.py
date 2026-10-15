"""Synthetic check of research/placement/manifestation_offpath_pilot.py against DECLARATION_PILOT_OFFPATH_OTEL.md (64854c2).

Covers: each fault manifests / does not manifest / `—` (the 20-item minimum, the failed no-fault precondition S2, an invalid or
absent cell), send-time selection of the frontend-pause checkouts, the 10 % bounds, the E-rate rule, the N3 witness
cross-check (reported only), the CLI, and identical statistics and verdicts to the harness reference functions
(`statistics_of`, `verdict`, `parse_spans` in ../observability-placement-runtime-otel-protocol/tests/test_otel_offpath_pilot.py,
extracted from the file by AST and run on the same synthetic cells; skipped if that sibling worktree is absent)."""
import ast
import importlib.util
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manifestation_offpath_pilot", REPO / "research/placement/manifestation_offpath_pilot.py")
mo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mo)

REFERENCE_FILE = REPO.parent / "observability-placement-runtime-otel-protocol/tests/test_otel_offpath_pilot.py"
T = 1_800_000_000.0  # barrier epoch
TIMING = {"requestTimeoutSeconds": 15.0, "faultHoldSeconds": 60}
CONSUMER_SERVICES = ("frauddetectionservice", "accountingservice")
FAULTS = mo.FAULTS


# ---------------------------------------------------------------------------------------------- the harness reference
def _reference():
    if not REFERENCE_FILE.exists():
        pytest.skip("harness reference test file not present: %s" % REFERENCE_FILE)
    tree = ast.parse(REFERENCE_FILE.read_text())
    wanted = {"_parse_stamp", "parse_spans", "statistics_of", "verdict"}
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {n.name for n in body} == wanted
    namespace = {"re": re, "json": json, "statistics": statistics, "datetime": datetime, "timezone": timezone, "Path": Path,
                 "CONSUMERS": ("accountingservice", "frauddetectionservice")}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(REFERENCE_FILE), "exec"), namespace)
    return namespace


# ------------------------------------------------------------------------------------------------ synthetic cells
def _stamp(epoch, digits):
    moment = datetime.fromtimestamp(epoch, timezone.utc)
    base = moment.strftime("%Y-%m-%d %H:%M:%S")
    if digits == 0:
        return base + " +0000 UTC"
    return base + "." + ("%09d" % min(int((epoch % 1) * 1e9), 999_999_999))[:digits] + " +0000 UTC"


def _block(service, name, kind, start, end, digits):
    return ["otelcol-1  | ResourceSpans #0", "otelcol-1  | Resource attributes:",
            "otelcol-1  |      -> process.runtime.name: Str(x)", "otelcol-1  |      -> service.name: Str(%s)" % service,
            "otelcol-1  | ScopeSpans #0", "otelcol-1  | Span #0", "otelcol-1  |     Trace ID       : abc",
            "otelcol-1  |     Parent ID      : ", "otelcol-1  |     Name           : %s" % name,
            "otelcol-1  |     Kind           : %s" % kind, "otelcol-1  |     Start time     : %s" % _stamp(start, digits),
            "otelcol-1  |     End time       : %s" % _stamp(end, digits), "otelcol-1  |     Status code    : Unset",
            "otelcol-1  | Events:", "otelcol-1  | SpanEvent #0", "otelcol-1  |      -> Name: exception"]


def _spread(t0, n, window):
    lo = t0 - 60.0 if window == "pre" else t0
    return [lo + 60.0 * (k + 0.5) / n for k in range(n)]


def make_cell(cell_dir, run_id, scenario, *, onset=60.007, state="valid", prod_n=(100, 100), server_factor=1.0, client_factor=1.0,
              cons_pre=None, cons_hold=None, checkout_every=10, fail_all_in=None, fail_checkout_in=None, ok_checkout_every=None,
              leak_products=0, leak_checkouts=0, late_checkouts=(), omit_files=False):
    """One retained cell. 10 requests per second for 180 s (a checkout every `checkout_every`-th row, the rest product GETs).
    Rows scheduled inside `fail_all_in` (offset range) fail; checkouts scheduled inside `fail_checkout_in` fail; every
    `ok_checkout_every`-th checkout of the pseudo hold fails (the S2 case). `leak_products` / `leak_checkouts`: that many
    product rows (scheduled from the onset) / checkouts (scheduled from onset - 1 s) are ok although `fail_all_in` says fail.
    `late_checkouts` = [(scheduled offset, sent offset, outcome)] extra checkout rows."""
    cell_dir.mkdir(parents=True)
    (cell_dir / "receipt.json").write_text(json.dumps({"runId": run_id, "state": state}))
    if omit_files:
        return
    t0 = T + onset
    if scenario is not None:
        (cell_dir / "intervention.json").write_text(json.dumps({"freeze": {"commandIssuedOffsetSeconds": onset}}))
    rows = []
    for i in range(1800):
        sched = i / 10.0
        route = "checkout" if i % checkout_every == 0 else "product"
        sent = sched + (0.5 if route == "checkout" else 0.0)
        ok = True
        if fail_all_in and fail_all_in[0] <= sched < fail_all_in[1]:
            ok = False
        if route == "checkout" and fail_checkout_in and fail_checkout_in[0] <= sched < fail_checkout_in[1]:
            ok = False
        if route == "checkout" and ok_checkout_every and onset <= sched < onset + 60 and (i // checkout_every) % ok_checkout_every == 0:
            ok = False
        if not ok and fail_all_in and fail_all_in[0] <= sched < fail_all_in[1]:
            if route == "product" and sched >= onset and leak_products > 0:
                leak_products, ok = leak_products - 1, True
            elif route == "checkout" and sched >= onset - 1.0 and leak_checkouts > 0:
                leak_checkouts, ok = leak_checkouts - 1, True
        rows.append((sched, sent, route, ok))
    for sched, sent, outcome in late_checkouts:
        rows.append((sched, sent, "checkout", outcome == "ok"))
    requests = [{"requestToken": "opq-%s-%d" % (run_id, i), "scheduledOffsetSeconds": s, "startedAtEpoch": T + sent, "route": route,
                 "outcome": "ok" if ok else "timeout", "status": 200 if ok else None, "dependsOn": None}
                for i, (s, sent, route, ok) in enumerate(rows)]
    (cell_dir / "request-ledger.json").write_text(json.dumps(
        {"kind": "otel-demo-mix-ledger-v1", "barrierEpoch": T, "requestTimeoutSeconds": 15.0, "requests": requests}))
    witness = [{"request_token": r["requestToken"], "response_code": 200 if r["outcome"] == "ok" else 504, "response_flags": "-"}
               for r in requests]
    (cell_dir / "application-witness.json").write_text(json.dumps({"rows": witness}))

    cons_pre = {**{s: 60 for s in CONSUMER_SERVICES}, **(cons_pre or {})}
    cons_hold = {**{s: 60 for s in CONSUMER_SERVICES}, **(cons_hold or {})}
    lines = ["otelcol-1  | Timestamp: 2026-10-12 00:00:00.123456789 +0000 UTC", "otelcol-1  | Body: Str(stray)"]
    for window, n in zip(("pre", "hold"), prod_n):
        for k, start in enumerate(_spread(t0, n, window)):
            lines += _block("productcatalogservice", "oteldemo.ProductCatalogService/GetProduct", "Server", start,
                            start + 0.001 * (server_factor if window == "hold" else 1.0), 9)
            lines += _block("frontend", "grpc.oteldemo.ProductCatalogService/GetProduct", "Client", start,
                            start + 0.0012 * (client_factor if window == "hold" else 1.0), 9)
            lines += _block("frontend", "GET /api/x", "Server", start, start + 0.01, 2)      # the frontend's 2-digit stamps
    for service in CONSUMER_SERVICES:
        digits = 7 if service == "accountingservice" else 9
        for window, counts in (("pre", cons_pre), ("hold", cons_hold)):
            for start in _spread(t0, counts[service], window) if counts[service] else []:
                lines += _block(service, "orders receive", "Consumer", start, start + 0.05, digits)
    for start in (t0 - 100.0, t0 + 70.0):  # outside both windows: never counted
        lines += _block("frauddetectionservice", "orders receive", "Consumer", start, start + 0.05, 0)
        lines += _block("productcatalogservice", "oteldemo.ProductCatalogService/GetProduct", "Server", start, start + 5.0, 9)
    lines += _block("frauddetectionservice", "orders internal", "Internal", t0 - 30.0, t0 - 29.9, 9)  # not Kind=Consumer
    lines += _block("checkoutservice", "orders publish", "Producer", t0 + 30.0, t0 + 30.1, 9)
    (cell_dir / "otelcol.log").write_text("\n".join(lines) + "\n")


def make_campaign(root, rates=(100.0, 150.0), cells=None, states=None):
    """root/.controller/execution-package.json plus one retained cell per (scenario, rate); `cells` maps (scenario, rate) to
    make_cell options, `states` maps the same key to a receipt state; a key mapped to None is planned but not retained."""
    cells, states = cells or {}, states or {}
    package, n = [], 0
    for rate in rates:
        for scenario in (None,) + FAULTS:
            n += 1
            run_id = "run%02d" % n
            onset = 60.0 + n / 1000.0
            timing = {**TIMING, "requestsPerSecond": rate, "scoredWindowSeconds": [onset, onset + 60.0], "faultOnsetSeconds": onset}
            package.append({"runId": run_id, "fault": {"scenario": scenario}, "timing": timing})
            if (scenario, rate) in cells and cells[(scenario, rate)] is None:
                continue
            opts = {**DEFAULTS[scenario], **cells.get((scenario, rate), {})}
            d = root / "runs" / ("calibration" if scenario is None else "effect/" + scenario) / ("r%d-b01-%02d-full" % (rate, n))
            make_cell(d, run_id, scenario, onset=onset, state=states.get((scenario, rate), "valid"), **opts)
    (root / ".controller").mkdir(parents=True)
    (root / ".controller" / "execution-package.json").write_text(json.dumps({"cells": package}))
    return root


# the cell each fault produces when it manifests; the no-fault cell shows none of the effects
DEFAULTS = {
    None: {},
    "productcatalog-cpu-throttle": {"server_factor": 20.0, "client_factor": 1.5},
    "frontend-pause": {"fail_all_in": (60.0, 120.1)},
    "fraud-pause": {"cons_hold": {"frauddetectionservice": 3}},        # 3 <= 10 % of 60
    "accounting-pause": {"cons_hold": {"accountingservice": 6}},       # 6 == 10 % of 60 (the bound is inclusive)
}


def run(root, valid=None):
    return mo.analyse(root, valid)


def verdicts(result, fault):
    return {rate: row["verdict"] for rate, row in result["verdicts"][fault].items()}


# ------------------------------------------------------------------------------------------------------- manifests
def test_every_fault_manifests_at_every_rate_and_the_lowest_rate_is_the_e_rate(tmp_path):
    res = run(make_campaign(tmp_path))
    for fault in FAULTS:
        assert verdicts(res, fault) == {"100": "manifests", "150": "manifests"}, (fault, res["verdicts"][fault])
    assert all(res["keptForE"].values())
    assert res["eRate"]["rate"] == 100.0
    assert all(c["valid"] and c["witnessCrossCheck"]["unwitnessedLedgerRows"] == 0 for c in res["cells"])
    assert all(p["passes"] for p in res["noFaultPrecondition"].values())


def test_statistics_use_the_onset_of_the_right_source_and_the_declared_windows(tmp_path):
    res = run(make_campaign(tmp_path))
    by = {(c["fault"], c["rate"]): c for c in res["cells"]}
    # fault cell: intervention.json onset; no-fault cell: the plan's scoredWindowSeconds[0]
    assert by[("fraud-pause", 100.0)]["statistics"]["onset"] == pytest.approx(60.0 + 4 / 1000.0)
    assert by[(None, 100.0)]["statistics"]["onset"] == pytest.approx(60.0 + 1 / 1000.0)
    s = by[("fraud-pause", 100.0)]["statistics"]
    # pre 60 + the Internal-kind and out-of-window spans are not counted; the hold keeps the 3 planted spans only
    assert s["consumer"]["frauddetectionservice"] == {"pre": 60, "hold": 3}
    assert s["consumer"]["accountingservice"] == {"pre": 60, "hold": 60}
    assert by[("productcatalog-cpu-throttle", 100.0)]["statistics"]["serverRatio"] == pytest.approx(20.0, rel=1e-2)
    assert by[("productcatalog-cpu-throttle", 100.0)]["statistics"]["clientRatio"] == pytest.approx(1.5, rel=1e-2)
    assert by[(None, 100.0)]["statistics"]["serverRatio"] == pytest.approx(1.0, rel=1e-2)
    fp = by[("frontend-pause", 100.0)]["statistics"]
    assert fp["earlyRows"] == {"rows": 450, "ok": 0} and fp["rows"] == {"rows": 600, "ok": 0}
    assert fp["earlyCheckout"] == {"rows": 45, "ok": 0} and fp["checkout"] == {"rows": 60, "ok": 0}


# ------------------------------------------------------------------------------------------------ does not manifest
@pytest.mark.parametrize("fault,options", [
    ("fraud-pause", {"cons_hold": {"frauddetectionservice": 60}}),                      # a consumer that works through its pause
    ("fraud-pause", {"cons_hold": {"frauddetectionservice": 7}}),                       # 7 > 10 % of 60
    ("accounting-pause", {"cons_hold": {"accountingservice": 3}, "fail_checkout_in": (60.0, 120.0)}),  # the pause takes checkout down
    ("accounting-pause", {"cons_hold": {"accountingservice": 3}, "ok_checkout_every": 10}),            # checkout 90 % ok < 95 %
    ("productcatalog-cpu-throttle", {"server_factor": 1.0, "client_factor": 1.0}),      # a throttle that does not bind
    ("productcatalog-cpu-throttle", {"server_factor": 20.0, "client_factor": 1.2}),     # the client ratio below 1.25
    ("productcatalog-cpu-throttle", {"server_factor": 1.9, "client_factor": 1.5}),      # the server ratio below 2.0
    ("frontend-pause", {"fail_all_in": None}),                                          # a pause that never bites
    ("frontend-pause", {"fail_all_in": (60.0, 120.0), "leak_checkouts": 5}),            # 5 of 45 checkouts sent ok = 11.1 % > 10 %
    ("frontend-pause", {"fail_all_in": (60.0, 120.0), "leak_products": 46}),            # 46 of 450 rows ok = 10.2 % > 10 %
])
def test_a_fault_whose_effect_is_absent_does_not_manifest(tmp_path, fault, options):
    res = run(make_campaign(tmp_path, rates=(100.0,), cells={(fault, 100.0): options}))
    assert res["verdicts"][fault]["100"]["verdict"] == "does not manifest", res["verdicts"][fault]["100"]
    assert res["verdicts"][fault]["100"]["reason"]
    assert not res["keptForE"][fault] and res["eRate"]["rate"] is not None and res["eRate"]["rate"] == 100.0


def test_the_no_fault_cell_showing_the_effect_stops_a_fault_from_manifesting(tmp_path):
    cells = {(None, 100.0): {"cons_hold": {"frauddetectionservice": 2}, "server_factor": 20.0, "client_factor": 1.5}}
    res = run(make_campaign(tmp_path, rates=(100.0,), cells=cells))
    assert res["verdicts"]["fraud-pause"]["100"]["verdict"] == "does not manifest"            # no-fault consumer collapse too
    assert res["verdicts"]["productcatalog-cpu-throttle"]["100"]["verdict"] == "does not manifest"   # no-fault ratios too
    assert res["verdicts"]["accounting-pause"]["100"]["verdict"] == "manifests"


def test_the_frontend_pause_bounds_are_inclusive_at_ten_percent(tmp_path):
    for n, (leak, kind) in enumerate(((45, "leak_products"), (4, "leak_checkouts"))):   # 45/450 = 10 % exactly; 4/45 = 8.9 %
        res = run(make_campaign(tmp_path / str(n), rates=(100.0,), cells={
            ("frontend-pause", 100.0): {"fail_all_in": (60.0, 120.0), kind: leak}}))
        assert res["verdicts"]["frontend-pause"]["100"]["verdict"] == "manifests", (kind, res["verdicts"]["frontend-pause"]["100"])


# ------------------------------------------------------------------------------------------------------------- `—`
def test_a_failed_no_fault_precondition_gives_dash_for_every_fault_at_that_rate_only(tmp_path):
    cells = {(None, 100.0): {"ok_checkout_every": 10}}          # 5 of the pseudo hold's 60 checkouts fail (91.7 % ok); the cell is valid
    res = run(make_campaign(tmp_path, cells=cells))
    for fault in FAULTS:
        assert res["verdicts"][fault]["100"]["verdict"] == mo.DASH, fault
        assert "S2" in res["verdicts"][fault]["100"]["reason"]
        assert res["verdicts"][fault]["150"]["verdict"] == "manifests"
    assert res["noFaultPrecondition"]["100"]["passes"] is False and res["noFaultPrecondition"]["150"]["passes"] is True
    assert 0.9 <= res["noFaultPrecondition"]["100"]["checkoutOkShare"] < 0.95
    assert res["eRate"]["rate"] == 150.0


def test_a_no_fault_cell_with_failing_rows_fails_the_precondition(tmp_path):
    cells = {(None, 100.0): {"fail_all_in": (60.0, 66.0)}}      # 59 of 600 rows fail in the pseudo hold (90.2 % ok)
    res = run(make_campaign(tmp_path, rates=(100.0,), cells=cells))
    pre = res["noFaultPrecondition"]["100"]
    assert pre["rowsOkShare"] == pytest.approx(0.9, abs=0.01) and pre["passes"] is False
    assert all(res["verdicts"][f]["100"]["verdict"] == mo.DASH for f in FAULTS)


def test_the_precondition_needs_20_checkout_rows_and_20_rows(tmp_path):
    cells = {(None, 100.0): {"checkout_every": 40}}             # 15 checkouts in the 60 s pseudo hold
    res = run(make_campaign(tmp_path, rates=(100.0,), cells=cells))
    assert res["noFaultPrecondition"]["100"]["checkoutRows"] == 15 and res["noFaultPrecondition"]["100"]["passes"] is False
    assert all(res["verdicts"][f]["100"]["verdict"] == mo.DASH for f in FAULTS)


@pytest.mark.parametrize("fault,options", [
    ("fraud-pause", {"cons_pre": {"frauddetectionservice": 19}, "cons_hold": {"frauddetectionservice": 0}}),   # 19 < 20 pre-onset
    ("accounting-pause", {"cons_pre": {"accountingservice": 19}, "cons_hold": {"accountingservice": 0}}),
    ("fraud-pause", {"checkout_every": 40, "cons_hold": {"frauddetectionservice": 0}}),                         # 15 < 20 checkout rows
    ("productcatalog-cpu-throttle", {"prod_n": (19, 100), "server_factor": 20.0, "client_factor": 1.5}),        # 19 < 20 pre spans
    ("productcatalog-cpu-throttle", {"prod_n": (100, 19), "server_factor": 20.0, "client_factor": 1.5}),        # 19 < 20 hold spans
    ("frontend-pause", {"checkout_every": 40, "fail_all_in": (60.0, 120.0)}),                                   # 12 checkouts sent < 20
])
def test_fewer_than_twenty_items_in_a_segment_gives_dash(tmp_path, fault, options):
    res = run(make_campaign(tmp_path, rates=(100.0,), cells={(fault, 100.0): options}))
    row = res["verdicts"][fault]["100"]
    assert row["verdict"] == mo.DASH and "20" in row["reason"], row
    assert not res["keptForE"][fault]


def test_the_no_fault_cell_with_too_few_consumer_spans_gives_dash_for_that_consumer_only(tmp_path):
    cells = {(None, 100.0): {"cons_pre": {"frauddetectionservice": 10}, "cons_hold": {"frauddetectionservice": 10}}}
    res = run(make_campaign(tmp_path, rates=(100.0,), cells=cells))
    assert res["verdicts"]["fraud-pause"]["100"]["verdict"] == mo.DASH
    assert res["verdicts"]["accounting-pause"]["100"]["verdict"] == "manifests"


def test_a_cell_counts_only_if_valid_and_replayed_and_an_uncounted_cell_is_not_read(tmp_path):
    cells = {("fraud-pause", 100.0): {"omit_files": True}}
    states = {("fraud-pause", 100.0): "blocked"}
    root = make_campaign(tmp_path, rates=(100.0,), cells=cells, states=states)     # a blocked cell with no artifacts at all
    res = run(root)
    row = res["verdicts"]["fraud-pause"]["100"]
    assert row["verdict"] == mo.DASH and "blocked" in row["reason"]
    assert res["verdicts"]["accounting-pause"]["100"]["verdict"] == "manifests"
    # --replayed-valid: a receipt-valid cell whose run ID the offline replay did not pass does not count
    root2 = make_campaign(tmp_path / "b", rates=(100.0,))
    all_ids = {c["runId"] for c in run(root2)["cells"]}
    res2 = run(root2, valid=all_ids - {"run04"})                                    # run04 = the fraud-pause cell
    assert res2["verdicts"]["fraud-pause"]["100"]["verdict"] == mo.DASH and "replayed" in res2["verdicts"]["fraud-pause"]["100"]["reason"]
    assert res2["verdicts"]["accounting-pause"]["100"]["verdict"] == "manifests"
    res3 = run(root2, valid=all_ids - {"run01"})                                    # run01 = the no-fault cell: every fault `—`
    assert all(res3["verdicts"][f]["100"]["verdict"] == mo.DASH for f in FAULTS)


def test_a_planned_cell_with_no_receipt_is_dash_and_an_absent_no_fault_cell_makes_the_rate_dash(tmp_path):
    cells = {("frontend-pause", 150.0): None, (None, 150.0): None}
    res = run(make_campaign(tmp_path, cells=cells))
    assert verdicts(res, "frontend-pause") == {"100": "manifests", "150": mo.DASH}
    assert verdicts(res, "fraud-pause") == {"100": "manifests", "150": mo.DASH}
    assert res["eRate"]["rate"] == 100.0


# ------------------------------------------------------------------------------------------------ send-time selection
def test_the_frontend_pause_checkouts_are_selected_by_send_time_not_scheduled_time(tmp_path):
    """A checkout scheduled before the onset but sent in the first 45 s counts (it failed); one scheduled in the first 45 s but
    sent after it does not (it was served after the unpause)."""
    onset = 60.007
    late = [(onset - 5.0, onset + 10.0, "timeout"), (onset + 30.0, onset + 50.0, "ok")]
    d = tmp_path / "cell"
    make_cell(d, "x", "frontend-pause", onset=onset, fail_all_in=(60.0, 120.0), late_checkouts=late)
    s, _ = mo.statistics_of(d, "frontend-pause", {**TIMING, "scoredWindowSeconds": [0, 0]})
    clean = tmp_path / "clean"
    make_cell(clean, "y", "frontend-pause", onset=onset, fail_all_in=(60.0, 120.0))
    base, _ = mo.statistics_of(clean, "frontend-pause", {**TIMING, "scoredWindowSeconds": [0, 0]})
    assert s["earlyCheckout"]["rows"] == base["earlyCheckout"]["rows"] + 1 and s["earlyCheckout"]["ok"] == base["earlyCheckout"]["ok"]
    assert s["checkout"]["rows"] == base["checkout"]["rows"] + 1 and s["checkout"]["ok"] == base["checkout"]["ok"] + 1   # scheduled view
    assert s["earlyRows"]["rows"] == base["earlyRows"]["rows"] + 1   # the extra row scheduled at onset+30 is an early row (scheduled time)


def test_a_checkout_sent_just_outside_the_45_s_window_is_not_counted(tmp_path):
    onset = 60.007
    for sent, rows in ((onset + 44.9, 1), (onset + 45.1, 0)):
        d = tmp_path / ("c%s" % sent)
        make_cell(d, "x", "frontend-pause", onset=onset, fail_all_in=(60.0, 120.0), checkout_every=10_000,
                  late_checkouts=[(onset + 1.0, sent, "ok")])
        s, _ = mo.statistics_of(d, "frontend-pause", {**TIMING, "scoredWindowSeconds": [0, 0]})
        assert s["earlyCheckout"]["rows"] == rows            # the only other checkout (row 0) was sent at 0.5 s, before the onset


# --------------------------------------------------------------------------------------------------- E-rate rule
M, N, D = "manifests", "does not manifest", mo.DASH


def _grid(a, b, c, d):
    """one (rate 100, rate 150) pair per fault in the order throttle, frontend, fraud, accounting"""
    return {f: {100.0: p[0], 150.0: p[1]} for f, p in zip(FAULTS, (a, b, c, d))}


def test_e_rate_is_the_lowest_rate_with_every_kept_fault_manifesting():
    kept, rate, _ = mo.e_rate(_grid((M, M), (M, M), (M, M), (M, M)), [100.0, 150.0])
    assert kept == list(FAULTS) and rate == 100.0
    # the throttle only binds at 150; every kept fault manifests there only
    assert mo.e_rate(_grid((N, M), (M, M), (M, M), (M, M)), [100.0, 150.0])[1:2] == (150.0,)
    # a fault that manifests nowhere is not kept, so it does not hold the rate back
    kept, rate, _ = mo.e_rate(_grid((N, N), (M, M), (M, M), (M, M)), [100.0, 150.0])
    assert "productcatalog-cpu-throttle" not in kept and rate == 100.0


def test_e_rate_falls_back_to_the_highest_rate_at_which_any_fault_manifests():
    kept, rate, rule = mo.e_rate(_grid((M, N), (N, M), (M, D), (N, N)), [100.0, 150.0])
    assert kept == ["productcatalog-cpu-throttle", "frontend-pause", "fraud-pause"] and rate == 150.0 and "highest" in rule
    assert mo.e_rate(_grid((M, N), (N, N), (D, N), (N, N)), [100.0, 150.0])[1] == 100.0
    assert mo.e_rate(_grid((N, N), (D, N), (N, D), (N, N)), [100.0, 150.0])[:2] == ([], None)
    # a `—` at a rate is not a manifestation: fraud is `—` at 100, so 100 does not have every kept fault manifesting
    assert mo.e_rate(_grid((M, M), (M, M), (D, M), (M, M)), [100.0, 150.0])[1] == 150.0


# --------------------------------------------------------------------------------------------- N3 cross-check
def test_the_witness_cross_check_counts_status_disagreements_and_response_flags_per_route(tmp_path):
    d = tmp_path / "cell"
    make_cell(d, "x", None, onset=60.0)
    ledger = json.loads((d / "request-ledger.json").read_text())
    rows = ledger["requests"]
    products = [r for r in rows if r["route"] == "product"]
    checkouts = [r for r in rows if r["route"] == "checkout"]
    witness = json.loads((d / "application-witness.json").read_text())
    by = {w["request_token"]: w for w in witness["rows"]}
    by[products[0]["requestToken"]]["response_code"] = 503            # ledger 200, witness 503: disagrees
    by[products[0]["requestToken"]]["response_flags"] = "UO"          # and an overflow flag
    by[products[1]["requestToken"]]["response_flags"] = "UO"          # flagged but the code agrees
    by[checkouts[0]["requestToken"]]["response_code"] = "200"         # a string code that agrees after int()
    by[checkouts[1]["requestToken"]]["response_code"] = 500           # disagrees
    by[checkouts[2]["requestToken"]]["response_flags"] = "DC"
    del by[products[2]["requestToken"]]                               # unwitnessed
    witness["rows"] = [w for w in witness["rows"] if w["request_token"] in by] + [
        {"request_token": "opq-stranger", "response_code": 200, "response_flags": "UO"}]
    (d / "application-witness.json").write_text(json.dumps(witness))
    out = mo.witness_cross_check(d)
    assert out["byRoute"]["product"] == {"ledgerRows": len(products), "statusDisagrees": 1, "witnessFlagsNotDash": 2}
    assert out["byRoute"]["checkout"] == {"ledgerRows": len(checkouts), "statusDisagrees": 1, "witnessFlagsNotDash": 1}
    assert out["byRoute"]["?unknown-token"]["witnessFlagsNotDash"] == 1
    assert (out["unwitnessedLedgerRows"], out["unknownWitnessRows"]) == (1, 1)


def test_the_cross_check_never_changes_a_verdict(tmp_path):
    root = make_campaign(tmp_path, rates=(100.0,))
    before = run(root)
    for witness in root.glob("runs/**/application-witness.json"):
        data = json.loads(witness.read_text())
        for row in data["rows"][:50]:
            row["response_code"], row["response_flags"] = 503, "UO"
        witness.write_text(json.dumps(data))
    after = run(root)
    assert before["verdicts"] == after["verdicts"] and before["eRate"] == after["eRate"]
    assert sum(r["statusDisagrees"] for c in after["cells"] for r in c["witnessCrossCheck"]["byRoute"].values()) > 0


# ------------------------------------------------------------------------------------------------------- parser
def test_the_span_parser_reads_zero_to_nine_fraction_digits_and_skips_events_and_metrics(tmp_path):
    lines = []
    for digits in (0, 2, 7, 9):
        lines += _block("svc%d" % digits, "n", "Consumer", T + 0.123456789, T + 1.5, digits)
    lines += ["otelcol-1  |      -> Name: process.runtime.dotnet.gc.collections.count", "otelcol-1  | Metric #0"]
    p = tmp_path / "otelcol.log"
    p.write_text("\n".join(lines) + "\n")
    spans = list(mo.iter_spans(p))
    assert [s["service"] for s in spans] == ["svc0", "svc2", "svc7", "svc9"]
    assert [s["start"] - T for s in spans] == pytest.approx([0.0, 0.12, 0.1234567, 0.123456789], abs=1e-6)
    assert all(s["kind"] == "Consumer" and s["name"] == "n" for s in spans)
    bad = tmp_path / "bad.log"
    bad.write_text("otelcol-1  |      -> service.name: Str(x)\notelcol-1  | Span #0\notelcol-1  |     Start time     : yesterday\n")
    with pytest.raises(ValueError):
        list(mo.iter_spans(bad))


def test_a_zero_pre_onset_median_gives_no_ratio_not_a_crash():
    assert mo._ratio([0.0] * 25, [0.001] * 25) is None          # undefined: `—` (the harness reference would divide by zero)
    assert mo._ratio([0.001] * 25, [0.0] * 25) == 0.0
    assert mo._ratio([0.001] * 19, [0.002] * 25) is None and mo._ratio([0.001] * 25, [0.002] * 19) is None


# ------------------------------------------------------------------------------------------------------------ CLI
def test_cli_refuses_an_existing_output_writes_a_new_one_and_prints_the_rule(tmp_path, capsys):
    root = make_campaign(tmp_path / "campaign")
    out = tmp_path / "out.json"
    out.write_text("{}")
    with pytest.raises(SystemExit):
        mo.main([str(root), "--terminal-valid", "--out", str(out)])
    assert out.read_text() == "{}"
    new = tmp_path / "new.json"
    mo.main([str(root), "--terminal-valid", "--out", str(new)])
    doc = json.loads(new.read_text())
    assert doc["eRate"]["rate"] == 100.0 and doc["validity"] == "terminal-valid" and len(doc["cells"]) == 10
    assert "kept for E" in capsys.readouterr().out
    replay = tmp_path / "replay.json"
    mo.main([str(root), "--replayed-valid", "run01", "run04", "--out", str(replay)])
    doc = json.loads(replay.read_text())
    assert doc["verdicts"]["fraud-pause"]["100"]["verdict"] == "manifests" and doc["verdicts"]["accounting-pause"]["100"]["verdict"] == mo.DASH


def test_cli_requires_a_validity_mode(tmp_path):
    with pytest.raises(SystemExit):
        mo.main([str(tmp_path), "--out", str(tmp_path / "o.json")])


# ------------------------------------------------------------------------- identical to the harness reference functions
VARIANTS = {
    "all-manifest": {},
    "fraud-keeps-working": {("fraud-pause", 100.0): {"cons_hold": {"frauddetectionservice": 60}}},
    "accounting-checkout-down": {("accounting-pause", 100.0): {"cons_hold": {"accountingservice": 3}, "fail_checkout_in": (60.0, 120.0)}},
    "throttle-unbound": {("productcatalog-cpu-throttle", 100.0): {"server_factor": 1.0, "client_factor": 1.0}},
    "throttle-client-low": {("productcatalog-cpu-throttle", 100.0): {"client_factor": 1.2}},
    "frontend-never-bites": {("frontend-pause", 100.0): {"fail_all_in": None}},
    "frontend-late-checkouts": {("frontend-pause", 100.0): {
        "fail_all_in": (60.0, 120.0), "late_checkouts": [(55.0, 70.0, "timeout"), (90.0, 112.0, "ok"), (95.0, 96.0, "ok")]}},
    "frontend-leak-ten-percent": {("frontend-pause", 100.0): {
        "fail_all_in": (60.0, 120.0), "late_checkouts": [(60.0 + 0.05 + 0.1 * k, 60.0 + 0.05 + 0.1 * k, "ok") for k in range(5)]}},
    "no-fault-checkout-90": {(None, 100.0): {"ok_checkout_every": 10}},
    "no-fault-rows-90": {(None, 100.0): {"fail_all_in": (60.0, 66.0)}},
    "no-fault-sparse-checkout": {(None, 100.0): {"checkout_every": 40}},
    "no-fault-shows-effect": {(None, 100.0): {"cons_hold": {"frauddetectionservice": 2}, "server_factor": 20.0, "client_factor": 1.5}},
    "sparse-consumer": {("fraud-pause", 100.0): {"cons_pre": {"frauddetectionservice": 19}, "cons_hold": {"frauddetectionservice": 0}}},
    "sparse-nofault-consumer": {(None, 100.0): {"cons_pre": {"accountingservice": 5}, "cons_hold": {"accountingservice": 5}}},
    "sparse-throttle-spans": {("productcatalog-cpu-throttle", 100.0): {"prod_n": (19, 100), "server_factor": 20.0}},
    "sparse-frontend-checkouts": {("frontend-pause", 100.0): {"checkout_every": 40, "fail_all_in": (60.0, 120.0)}},
}


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_statistics_and_verdicts_are_identical_to_the_harness_reference(tmp_path, name):
    ref = _reference()
    root = make_campaign(tmp_path, rates=(100.0,), cells=VARIANTS[name])
    package = json.loads((root / ".controller/execution-package.json").read_text())["cells"]
    mine, theirs = {}, {}
    for cell in package:
        scenario, timing = cell["fault"]["scenario"], cell["timing"]
        d = next(root.glob("runs/**/%s" % ("r100-b01-%s-full" % cell["runId"][3:])))
        mine[scenario], extra = mo.statistics_of(d, scenario, timing)
        assert extra["spansParsed"] > 0
        theirs[scenario] = ref["statistics_of"](d, {"fault": {"scenario": scenario}, "timing": timing})
        assert mine[scenario] == theirs[scenario], (name, scenario)
    for fault in FAULTS:
        got = mo.verdict(fault, mine[fault], mine[None])[0]
        want = ref["verdict"](fault, theirs[fault], theirs[None])
        assert got == want, (name, fault, got, want)
    # the script's end-to-end verdicts agree with the reference too (every cell valid)
    res = run(root)
    for fault in FAULTS:
        assert res["verdicts"][fault]["100"]["verdict"] == ref["verdict"](fault, theirs[fault], theirs[None]), (name, fault)


def test_the_variants_exercise_every_verdict_of_every_fault(tmp_path):
    """The identity test is only as strong as the verdicts it sees: `manifests`, `does not manifest` and `—` each occur for
    every fault across the variants (the script's own verdicts; the identity test ties them to the reference)."""
    seen = {f: set() for f in FAULTS}
    for name, cells in VARIANTS.items():
        res = run(make_campaign(tmp_path / name, rates=(100.0,), cells=cells))
        for fault in FAULTS:
            seen[fault].add(res["verdicts"][fault]["100"]["verdict"])
    assert all(v == {"manifests", "does not manifest", mo.DASH} for v in seen.values()), seen


def test_the_span_parser_is_identical_to_the_harness_reference_on_real_and_synthetic_text(tmp_path):
    ref = _reference()
    real = tmp_path / "real.log"
    lines = _block("accountingservice", "orders receive", "Consumer", 1790000000.8160382, 1790000001.0075244, 7)
    lines += _block("frontend", "x", "Client", 1790000000.5, 1790000000.51, 2) + _block("a", "b", "Producer", T, T + 1, 0)
    lines += ["otelcol-1  | Metric #0", "otelcol-1  |      -> Name: m", "garbage without a pipe", "otelcol-1  | Span #5",
              "otelcol-1  |     Name           : incomplete", "otelcol-1  | ResourceSpans #1"]
    real.write_text("\n".join(lines) + "\n")
    mine = list(mo.iter_spans(real))
    theirs = ref["parse_spans"](real.read_text())
    assert mine == theirs and len(mine) == 3
