"""research/lanes/pooled_lanes.py: POST HOC exploratory pooled lane evidence.

Layer: unit, SYNTHETIC episodes (no readout file) plus one check on the committed readouts. The rule that matters (a fire with
`counts` false is never used in any lane time) carries the one planted-defect check: the module switch COUNTED_ONLY is flipped and
the same assertion is shown to fail, so the check exists, ran, and was seen failing on a planted defect.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "research" / "placement", ROOT / "research"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
_spec = importlib.util.spec_from_file_location("pooled_lanes", ROOT / "research" / "lanes" / "pooled_lanes.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


def fire(fam, sid, rule, ttd, own=False, counts=True, bc=()):
    return [fam, sid, rule, ttd, None, own, False, counts, list(bc), 0.0]


def episode(fires, target="persistence", kind="degradation"):
    return {"fires": sorted(fires, key=lambda f: f[3]), "target": target, "faultKind": kind}


def test_uncounted_fire_never_enters_a_lane_time_and_defect_is_seen():
    # an earlier fire with counts False must not set any time; the counted fire (no BC flag) is 9.0, the flagged one 5.0
    fires = [fire("L", "log:registry:aaa", "appear", 1.0, counts=False),
             fire("L", "log:registry:aaa", "appear", 5.0, bc=["BC-caller-log"]),
             fire("L", "log:registry:bbb", "appear", 9.0)]
    lane = pl.lane_times(fires)
    assert (lane["ttdCounted"], lane["ttdByConstruction"], lane["ttdAny"]) == (9.0, 5.0, 5.0)
    pl.COUNTED_ONLY = False
    try:
        bad = pl.lane_times(fires)
        assert (bad["ttdCounted"], bad["ttdByConstruction"], bad["ttdAny"]) != (9.0, 5.0, 5.0)   # the planted defect is visible
        assert bad["ttdAny"] == 1.0
    finally:
        pl.COUNTED_ONLY = True


def test_lanes_split_by_family_prefix_and_own_flag():
    e = episode([fire("T", "span:persistence:op", "absent", 2.0, own=True, bc=["BC-downstream-absent"]),
                 fire("L", "log:registry:1b6e", "appear", 10.0, bc=["BC-caller-log"]),
                 fire("L", "log:webui:zzz", "appear", 3.0),
                 fire("E", "ledger:fe:r", "spike", 4.0)])
    ln = pl.episode_lanes(e, "teastore", {"log:registry:1b6e"}, set())
    assert ln["own"]["ttdByConstruction"] == 2.0 and ln["own"]["ttdCounted"] is None
    assert ln["coordinator"]["ttdAny"] == 10.0 and ln["coordinator"]["ttdCounted"] is None
    assert ln["coordinatorStrict"]["ttdAny"] == 10.0
    assert ln["ledger"]["ttdCounted"] == 4.0
    assert ln["lag"] is None                                  # TeaStore: n/a, `—` not 0
    hotel = pl.episode_lanes(e, "hotel", set(), set())
    assert hotel["coordinator"] is None                       # structural absence is None (`—`), never a 0/N


def test_classification_of_coordinator_outcomes():
    hit = {"ttdCounted": 1.0, "ttdByConstruction": None, "ttdAny": 1.0}
    bc_only = {"ttdCounted": None, "ttdByConstruction": 2.0, "ttdAny": 2.0}
    miss = {"ttdCounted": None, "ttdByConstruction": None, "ttdAny": None}
    cl = pl.classify_coordinator
    assert cl("teastore", "persistence", "degradation", hit) == "hit-counted"
    assert cl("teastore", "auth", "pause", bc_only) == "d"
    assert cl("hotel", "search", "pause", None) == "a"
    assert cl("otel", "frontend", "pause", miss) == "c"            # not a Kafka group member
    assert cl("teastore", "persistence", "degradation", miss) == "b"
    assert cl("otel", "accountingservice", "pause", miss) == "e"   # a member paused and nothing fired: unexplained


def test_spearman_known_values():
    assert pl.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert pl.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert pl.spearman([1, 2, 3], [1, 2, 3]) is None              # fewer than 4 pairs
    assert pl.spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None        # constant variable


def test_committed_readouts_reproduce_the_two_lanes_md_numbers():
    if not (pl.LANES_JSON.exists() and all((pl.SWEEP / u["dir"] / u["file"]).exists() for u in pl.USED)):
        pytest.skip("committed readouts or LANES json absent")
    recs, _ = pl.collect()
    L = pl.strict_ids()[1]
    checks = pl.cross_checks(recs, L)
    assert [c["ok"] for c in checks] == [True, True, True], checks
    assert len(recs) == 56 + 56 + 15 + 48                          # every fault episode of the used readouts, once
