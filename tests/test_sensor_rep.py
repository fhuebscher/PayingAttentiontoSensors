"""Sensor representation (research/protocol/sensor_rep): fixtures only, no evidence dependency.

Layer: unit. Channel independence of the catch rule; planted appear / disappear / move on a flat fixture (and no catch
without a plant); planted G3 (a sensor firing in 2 of 3 no-fault windows is inadmissible under the old arithmetic; 2 of 6
leave-one-cell-out tiles under the new one);
parser round-trip on a synthetic Hotel cell with missing channels rendered `—`; the OTel parser sees exactly the
adapter's log records and its typed templating collapses parameter-only differences.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "protocol"))

from sensor_rep import catch, events, vectors  # noqa: E402
from sensor_rep.parsers import common, hotel, otel  # noqa: E402

T0 = 1_790_000_000.0


def _cell(cid, duration=40.0, fault=None):
    return {"cell": cid, "base": {"wall": T0, "mono": 0.0}, "t0": {"wall": T0, "mono": None}, "duration": duration,
            "fault": fault, "channels": {}, "posture": "full"}


def _streams(channel, rows):
    """rows: [(token, t_offset, value)] -> streams on the wall clock."""
    m = events.meta(channel=channel, collector="fx", clock="wall", resolution="per-record", source="application",
                    level=None, posture="full", role="?", onPath=None, projected="?")
    return events.group([events.Event(channel, "svc", tok, T0 + t, v, m) for tok, t, v in rows])


def _baseline(channel, nf_rows, L=10.0):
    B = catch.Baseline("full")
    tiles = []
    for i, rows in enumerate(nf_rows):
        c = _cell("nf%d" % i)
        st = _streams(channel, rows)
        for w in vectors.tiles(c, L):
            x = catch.window_stats(st, w, L)
            B.add(c["cell"], w["index"], {channel}, x)
            tiles.append((c["cell"], {channel}, x, None))
    return B, tiles


def _steady(tok, rate_per_10s=2, until=40.0, offset=0.5, value=1.0):
    step = 10.0 / rate_per_10s
    out, t = [], offset
    while t < until:
        out.append((tok, t, value))
        t += step
    return out


# ----------------------------------------------------------------------------- channel independence

@pytest.mark.parametrize("channel,suffix", [("log", ""), ("span", ":error"), ("ledger", ":failed")])
def test_channel_independence(channel, suffix):
    """The same count series as log records, span errors or failed requests gives the same verdicts."""
    def tok(name):
        return name + suffix
    nf = [_steady(tok("a")) + _steady(tok("gone")) for _ in range(3)]
    B, _ = _baseline(channel, nf)
    fault_rows = (_steady(tok("a"), until=10.0) + [(tok("a"), 10.0 + 0.1 * i, 1.0) for i in range(9)] +
                  _steady(tok("a"), until=40.0, offset=20.5) + [(tok("new"), 15.0, 1.0)] +
                  _steady(tok("gone"), until=10.0))
    st = _streams(channel, fault_rows)
    w = vectors.window("fault", 0, {"wall": (T0 + 10.0, T0 + 20.0), "mono": (10.0, 20.0)})
    got = catch.new_fire(catch.window_stats(st, w, 10.0), B, {channel})
    verdict = {k[2][:len(k[2]) - len(suffix)] if suffix else k[2]: sorted(v["kinds"]) for k, v in got.items()}
    assert verdict == {"a": ["count_up"], "new": ["appear"], "gone": ["count_down", "disappear"]}, verdict


# ----------------------------------------------------------------------------- planted appear / disappear / move

def _flat_metric(cell_rows_tok="cpu", level=3.0, until=40.0):
    return [(cell_rows_tok, float(t) + 0.25, level + 0.1 * (t % 3)) for t in range(int(until))]


def test_planted_appear_disappear_move_and_flat_is_silent():
    nf = [_flat_metric() for _ in range(3)]
    B, _ = _baseline("metric", nf)
    w = vectors.window("fault", 0, {"wall": (T0 + 10.0, T0 + 20.0), "mono": (10.0, 20.0)})
    flat = catch.new_fire(catch.window_stats(_streams("metric", _flat_metric()), w, 10.0), B, {"metric"})
    assert flat == {}, flat                                        # non-vacuity: no plant, no catch
    stepped = [(tok, t, v + (6.0 if 10.0 <= t <= 20.0 else 0.0)) for tok, t, v in _flat_metric()]
    got = catch.new_fire(catch.window_stats(_streams("metric", stepped), w, 10.0), B, {"metric"})
    assert got[("metric", "svc", "cpu")]["kinds"] == ["level_up"], got
    # appear / disappear on logs, and the disappear needs a token the posture collects
    nf_logs = [_steady("tmpl-a") for _ in range(3)]
    BL, _ = _baseline("log", nf_logs)
    planted = _steady("tmpl-a", until=10.0) + _steady("tmpl-a", until=40.0, offset=20.5) + [("tmpl-new", 12.0, 1.0)]
    got = catch.new_fire(catch.window_stats(_streams("log", planted), w, 10.0), BL, {"log"})
    assert sorted(got[("log", "svc", "tmpl-new")]["kinds"]) == ["appear"]
    assert "disappear" in got[("log", "svc", "tmpl-a")]["kinds"]
    not_collected = catch.new_fire(catch.window_stats(_streams("log", planted), w, 10.0), BL, {"span"})
    assert not_collected == {}                                     # a channel the cell does not collect never fires


def test_old_rule_matches_symptoms_on_the_same_series():
    """The old (oracle) metric rule on streams equals symptoms.metric_symbols on the raw series."""
    S = common.symptoms()
    series = [(T0 + i, 3.0 + 0.1 * (i % 3)) for i in range(40)] + [(T0 + 46, 0.0), (T0 + 50, 0.0), (T0 + 55, 0.0)]
    st = _streams("metric", [("cpu", t - T0, v) for t, v in series])
    c = _cell("x", 120.0)
    w = vectors.window("fault", 0, {"wall": (T0 + 45.0, T0 + 60.0)})
    got = catch.old_fire(c, st, w, vectors.pre_window(c, w["bounds"]))
    ref = {k.rsplit(":", 1)[1] for k in S.metric_symbols(series, "cpu", T0, (T0 + 45.0, T0 + 60.0))}
    assert got[("metric", "svc", "cpu")] == ref == {"spike_down", "plateau_down"}


# ----------------------------------------------------------------------------- planted G3

def test_planted_g3_two_of_three_is_inadmissible():
    bad, counts, n = catch.g3_inadmissible([{"x"}, {"x"}, set()])
    assert bad == {"x"} and counts["x"] == 2 and n == 3
    bad, _, _ = catch.g3_inadmissible([set(), set(), set()])
    assert bad == set()
    # new rule, leave-one-cell-out: a burst in 2 of 6 no-fault cells (one tile each). Each burst tile is scored against
    # the other five cells (median 0, MAD 0 -> floor 2) and fires count_up; a quiet tile sees [10, 10, 0, 0, 0]
    # (median 0) and does not. With 5 cells a quiet tile would see median 5 and fire `disappear` (k = 5): a bimodal
    # token is noisy either way, which is what G3 is for.
    nf = [[("burst", 5.0 + 0.1 * j, 1.0) for j in range(10)] if i < 2 else [] for i in range(6)]
    nf = [r + _steady("calm", until=10.0) for r in nf]
    B1 = catch.Baseline("full")
    tl = []
    for i, rows in enumerate(nf):
        c = _cell("nf%d" % i, duration=10.0)
        x = catch.window_stats(_streams("log", rows), vectors.tiles(c, 10.0)[0], 10.0)
        B1.add(c["cell"], 0, {"log"}, x)
        tl.append((c["cell"], {"log"}, x, None))
    G = catch.g3_loo(B1, tl)
    g = G[("log", "svc", "burst")]
    assert (g["k"], g["nEff"], g["nCells"], g["admissible"]) == (2, 6, 6, False), g
    assert G[("log", "svc", "calm")] == {"k": 0, "nEff": 6, "nCells": 6, "admissible": True}
    # n_eff = 0 is not reported as admissible
    assert catch.g3_loo(catch.Baseline("full"), []) == {}


# ----------------------------------------------------------------------------- parser round-trip, missing channel -> —

def _iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))


def _hotel_attempt(d, b0=5000.0):
    _w(d / "cell-contract.json", {"runKey": {"block": 1, "posture": "full", "regime": "reservation-pause-effect"}})
    _w(d / "cell-terminal.json", {"candidateCellValid": True})
    _w(d / "opportunity-plan.json", {"barrierAt": _iso(T0), "barrierMonotonic": b0, "durationSeconds": 120.0,
                                     "workloadId": "hotel-search-v1"})
    _w(d / "fault-receipt.json", {"appliedMonotonic": b0 + 45.0, "revertingMonotonic": b0 + 60.0,
                                  "targetService": "reservation", "faultKind": "pause"})
    smp = []
    for i in range(25):
        t = 5.0 * i
        smp.append({"at": _iso(T0 + t), "monotonic": b0 + t, "services": {
            "frontend": {"cpuUsageUsec": int(1e6 * 0.2 * t), "memoryCurrent": 10_000_000, "psiCpuSomeTotalUsec": 0,
                         "psiIoSomeTotalUsec": 0, "psiMemorySomeTotalUsec": 0, "rbytes": 0, "wbytes": 0}}})
    _w(d / "system-samples.json", {"intervalSeconds": 5, "samples": smp})
    goaway = "%s ERROR: [transport] Client received GoAway with error code ENHANCE_YOUR_CALM" % \
        dt.datetime.fromtimestamp(T0 + 77, dt.timezone.utc).strftime("%Y/%m/%d %H:%M:%S")
    lines = ['frontend-1  | {"level":"info","time":"%s","message":"TLS disabled."}' % (_iso(T0 + 1)[:19] + "Z"),
             "frontend-1  | \x1b[90m%sZ\x1b[0m \x1b[31mERR\x1b[0m \x1b[1ma.go:1\x1b[0m\x1b[36m >\x1b[0m reservation failed id=7"
             % _iso(T0 + 50)[:19],
             "frontend-1  | " + goaway,
             'frontend-1  | OBSPLACEMENT_WITNESS {"x":1}',
             "compose cli line"]
    _w(d / "application.log", "\n".join(lines))
    rows = []
    for i in range(120):
        s = b0 + i
        ok = not (45.0 <= i <= 60.0 and i % 2)
        rows.append(json.dumps({"actualStartMonotonic": s, "actualEndMonotonic": s + 0.01, "outcome": "completed",
                                "statusCode": 200 if ok else 503}))
    _w(d / "opportunity-ledger.jsonl", "\n".join(rows) + "\n")
    return d


def test_parser_roundtrip_missing_channel_is_dash(tmp_path):
    S = common.symptoms()
    d = _hotel_attempt(tmp_path / "runs" / "effect" / "reservation-pause" / "b01" / "p01-full" / "attempt-01")
    cell = hotel.parse_cell(d, "fx")
    assert cell["target"] == "reservation" and cell["fault"]["mono"] == (5045.0, 5060.0)
    assert cell["fault"]["wall"] == pytest.approx((T0 + 45.0, T0 + 60.0))
    ev = cell.pop("events")
    streams = events.group(ev)
    # logs: the same template ids as symptoms' own parse of the same lines; witness and compose CLI lines are not records
    recs, _ = S.parse_stream([x.split(" | ", 1)[1] for x in (d / "application.log").read_text().splitlines()
                              if " | " in x], S.HOTEL_LAYOUTS)
    want = sorted(S.template_id(r["framework"], r["level"], r["key"], r["msg"]) for r in recs)
    assert sorted(e.token for e in ev if e.channel == "log") == want and len(want) == 3
    assert cell["stats"]["knownPeriodic"] and cell["stats"]["composeCliLines"] == 1
    assert {e.meta["level"] for e in ev if e.channel == "log"} == {"info", "error"}
    # ledger: one event per row, failures on the `:failed` token
    led = [e for e in ev if e.channel == "ledger"]
    assert len(led) == 120 and sum(1 for e in led if e.token.endswith(":failed")) == 8
    # missing channels render `—`, present-but-empty render 0
    w = vectors.fault_window(cell)
    counts = vectors.channel_counts(cell, streams, w)
    assert counts["metric:docker-stats"] == "—" and counts["span"] == "—"
    assert counts["log"] == 1 and counts["ledger"] == 16 and counts["metric:cgroup-sampler"] > 0
    # the old ledger rule on the parsed events equals ledger_check.cell on the files
    lc = common.load("fx_ledger_check", common.RESEARCH / "hotel-selected" / "ledger_check.py")
    mine = catch.old_ledger(streams, w, vectors.pre_window(cell, w["bounds"]))
    assert mine == lc.cell(d)


# ----------------------------------------------------------------------------- OTel parser and the masking fix

def test_otel_log_records_match_adapter_and_templating_is_typed():
    A = otel.adapter()
    lines = A.FIXTURE_LOG.splitlines()
    mine, _ = otel.parse_log_records(lines)
    ref = A.parse_otelcol(lines)["logs"]
    assert {s: [r["t"] for r in v] for s, v in mine.items()} == {s: [r["t"] for r in v] for s, v in ref.items()}
    assert sum(len(v) for v in mine.values()) > 0
    base = {"level": None, "scope": "recommendation"}
    a = dict(base, body="Receive ListRecommendations for product ids:['66VCHSJNUP', 'L9ECAV7KIM']", attrs={})
    b = dict(base, body="Receive ListRecommendations for product ids:['OLJCESPC7Z', '2ZYFJ3GM2N', 'LS4PSXUNUM']", attrs={})
    assert otel.template(a, "symptoms")[0] != otel.template(b, "symptoms")[0]      # the defect, reproduced
    assert otel.template(a)[0] == otel.template(b)[0]                               # fixed: literal parameterised
    site = {"code.filepath": "/usr/src/app/recommendation_server.py", "code.function": "ListRecommendations",
            "code.lineno": "47"}
    ta, how = otel.template(dict(a, attrs=site))
    assert how == "callsite" and ta == otel.template(dict(b, attrs=site))[0]
    assert otel.literal_params("don't drop 'x' [1, 2] {'k': 1} (oops") == "don't drop <str> <list> <dict> (oops"


def test_fallback_to_own_pre_window_when_level_baseline_is_thin():
    """< MIN_BASELINE tiles with a level for the token -> the window median is judged against the cell's own pre-window;
    without enough pre-window samples there is no verdict (never a catch)."""
    nf = [[("op", 2.0, 0.010)], [], []]                        # one tile with a level, the rest without records
    B, _ = _baseline("span", nf)
    w = vectors.window("fault", 0, {"wall": (T0 + 10.0, T0 + 20.0), "mono": (10.0, 20.0)})
    x = catch.window_stats(_streams("span", [("op", 15.0, 0.500)]), w, 10.0)
    pre = {("span", "svc", "op"): [0.010, 0.011, 0.009, 0.010]}
    got = catch.new_fire(x, B, {"span"}, pre_values=pre)
    lvl = got[("span", "svc", "op")]["baseline"]["level"]
    assert "level_up" in got[("span", "svc", "op")]["kinds"] and lvl["basis"] == "own pre-window (fallback)"
    got = catch.new_fire(x, B, {"span"}, pre_values={("span", "svc", "op"): [0.010]})
    assert ("span", "svc", "op") not in got                    # `?`: no verdict, so no catch
