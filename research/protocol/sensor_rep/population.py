"""Population registry and loading: which retained evidence, which parser, which posture collects which family.

Engineering defaults (recorded):
- a population is one campaign (never pooled: draft 3 and visibility.py "populations never pooled"); "per (SUT,
  posture)" in the protocol is read as per (population, posture) on retained evidence.
- `collects` is the oracle's posture table (lmt_detect / analyse.py FAMILY_POSTURES for Hotel; visibility.py's
  "collected" derivation for TeaStore: logs in every posture, spans under selected (Tsel) / full (T); OTel: the
  adapter's FAMILY_POSTURES, every posture except `none`). It decides only which episodes a family is scored over.
- `g3Families`: families the ORACLE gated by G3 (Hotel: every family; TeaStore: L only, spans not calibrated). The new
  rule gates every channel, always.
"""
from pathlib import Path

from .events import group
from .parsers import common, hotel

REPO = common.REPO

POPULATIONS = {
    "hotel-lmt2": {"sut": "hotel", "x": "tmp/hotellmt2-evidence/x", "collects": hotel.COLLECTS["lmt2"],
                   "g3Families": ("L", "M", "S", "T", "Tsel")},
    "hotel-sel1": {"sut": "hotel", "x": "tmp/hotelsel1-evidence/x", "collects": hotel.COLLECTS["sel1"],
                   "g3Families": ("L", "M", "S", "T", "Tsel")},
    "hotel-int1": {"sut": "hotel", "x": "tmp/hotelint1-evidence/x", "collects": hotel.COLLECTS["int1"],
                   "g3Families": ("L", "M", "S", "T", "Tsel")},
}


def parser(sut):
    if sut == "hotel":
        return hotel
    if sut == "teastore":
        from .parsers import teastore
        return teastore
    if sut == "otel":
        from .parsers import otel
        return otel
    raise SystemExit("no parser for %s" % sut)


def register_late():
    """TeaStore / OTel entries (their parser modules define the posture tables)."""
    try:
        from .parsers import teastore
    except ImportError:
        teastore = None
    try:
        from .parsers import otel
    except ImportError:
        otel = None
    if teastore is not None:
        POPULATIONS.setdefault("teastore-T16", {"sut": "teastore", "x": "tmp/teastore16-evidence/x/teastore-candidate-pilot-v1",
                                                "collects": teastore.COLLECTS, "g3Families": ("L",)})
    if otel is not None:
        POPULATIONS.setdefault("otel-v3", {"sut": "otel", "x": "tmp/otel-v3-evidence", "collects": otel.COLLECTS,
                                           "g3Families": ("L", "M", "T")})


def load(name, limit=None, parse_kw=None):
    """Parse every cell of a population. Returns list of cells with `streams` (events grouped; raw events dropped).
    parse_kw: extra parser options (OTel: templating="symptoms" for the adapter replay)."""
    cfg = POPULATIONS[name]
    P = parser(cfg["sut"])
    x = REPO / cfg["x"]
    if not x.exists():
        raise FileNotFoundError(str(x))
    cells = []
    for d in P.cell_dirs(x)[:limit]:
        c = P.parse_cell(d, name, **(parse_kw or {}))
        c["streams"] = group(c.pop("events"))
        cells.append(c)
    return cells
