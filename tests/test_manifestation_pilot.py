"""Synthetic check of research/placement/manifestation_pilot.py: a slowed server span manifests, an unchanged one does not,
and too few spans give `—`."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "manifestation_pilot", Path(__file__).resolve().parents[1] / "research/placement/manifestation_pilot.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)

T0 = 1_800_000_000.0  # onset, epoch seconds


def _ts(t):
    import datetime as dt
    d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    return d.strftime("%Y-%m-%d %H:%M:%S") + ".%09d +0000 UTC" % round((t % 1) * 1e9)


def _log(tmp, slow_server, slow_client, n=40):
    out = []
    for svc, name, kind, slow in (("productcatalogservice", "oteldemo.ProductCatalogService/GetProduct", "Server", slow_server),
                                  ("frontend", "grpc.oteldemo.ProductCatalogService/GetProduct", "Client", slow_client)):
        out.append("otelcol-1  |      -> service.name: Str(%s)" % svc)
        for i in range(n):
            for start, dur in ((T0 - 50 + i, 0.001), (T0 + 5 + i, 0.001 * slow)):
                out += ["otelcol-1  | Span #0", "otelcol-1  |     Name           : %s" % name,
                        "otelcol-1  |     Kind           : %s" % kind,
                        "otelcol-1  |     Start time     : %s" % _ts(start), "otelcol-1  |     End time       : %s" % _ts(start + dur)]
    p = tmp / ("log-%s-%s-%d" % (slow_server, slow_client, n))
    p.write_text("\n".join(out) + "\n")
    return p


def _cell(kind, r):
    return {"kind": kind, "valid": True, "ratios": r}


def test_ratios_and_verdicts(tmp_path):
    hit = mp.ratios(_log(tmp_path, 3, 1.5), T0, 60)
    flat = mp.ratios(_log(tmp_path, 1, 1), T0, 60)
    assert abs(hit["server"]["ratio"] - 3) < 1e-3 and abs(hit["client"]["ratio"] - 1.5) < 1e-3
    assert abs(flat["server"]["ratio"] - 1) < 1e-3
    assert mp.rate_verdict([_cell("throttle", hit), _cell("throttle", hit), _cell("no-fault", flat)]) == "manifests"
    assert mp.rate_verdict([_cell("throttle", hit), _cell("throttle", flat), _cell("no-fault", flat)]) == "does not manifest"
    assert mp.rate_verdict([_cell("throttle", hit), _cell("throttle", hit), _cell("no-fault", hit)]) == "does not manifest"
    few = mp.ratios(_log(tmp_path, 3, 1.5, n=10), T0, 60)
    assert few["server"]["ratio"] is None
    assert mp.rate_verdict([_cell("throttle", few), _cell("throttle", hit), _cell("no-fault", flat)]) == "—"
    assert mp.rate_verdict([_cell("throttle", hit), _cell("no-fault", flat)]) == "—"
