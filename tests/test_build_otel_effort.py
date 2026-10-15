"""research/placement/declared/build_otel_effort.py regenerates the committed otel.effort.json.

Layer: integration over real inputs (readout, placement, both posture catalogs, materialize.py at a pinned commit in the
sibling runtime worktree).  The sibling worktree and tmp/otel-v2-admission are environmental: absent, the tests skip.
Check 1 passes (equality modulo generatedAt).  Check 2 is the planted defect: one rule's tier changed inside the
generator (not in a copy of the output), and the equality check must then fail.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research/placement/declared/build_otel_effort.py"
COMMITTED = ROOT / "research/placement/declared/otel.effort.json"


def load_generator():
    spec = importlib.util.spec_from_file_location("build_otel_effort", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen():
    mod = load_generator()
    needed = [mod.CATALOG_CURRENT, mod.CATALOG_V3, mod.READOUT, mod.PLACEMENT, mod.ENVOY, mod.OTELCOL, mod.RESULT]
    missing = [str(p) for p in needed if not p.exists()]
    if missing:
        pytest.skip(f"environmental inputs absent: {missing}")
    try:
        mod.materialize_bytes()
    except Exception as exc:  # pinned commit not in the sibling worktree
        pytest.skip(f"materialize.py at {mod.MATERIALIZE_REV} unavailable: {exc}")
    return mod


def run(mod, out: Path) -> dict:
    assert mod.main(["--out", str(out)]) == 0
    return json.loads(out.read_text())


def strip_date(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("generatedAt")
    return doc


def test_regenerates_committed_file_modulo_generated_at(gen, tmp_path):
    out = tmp_path / "otel.effort.json"
    regen = run(gen, out)
    committed = json.loads(COMMITTED.read_text())
    assert strip_date(regen) == strip_date(committed)
    assert list(regen) == list(committed)  # key order too: the digest is over bytes
    stamped = out.read_text().replace(f'"generatedAt": "{regen["generatedAt"]}"',
                                      f'"generatedAt": "{committed["generatedAt"]}"')
    assert stamped == COMMITTED.read_text()


def test_refuses_to_overwrite(gen, tmp_path):
    out = tmp_path / "exists.json"
    out.write_text("keep")
    assert gen.main(["--out", str(out)]) == 2
    assert out.read_text() == "keep"


def test_planted_rule_tier_change_is_caught(gen, tmp_path, monkeypatch):
    planted = {k: dict(v) for k, v in gen.RULES.items()}
    planted["R-WITNESS"]["effortTier"] = 0  # the defect: witness lines reclassified as tier 0
    monkeypatch.setattr(gen, "RULES", planted)
    regen = run(gen, tmp_path / "planted.json")
    committed = json.loads(COMMITTED.read_text())
    assert strip_date(regen) != strip_date(committed)
    assert regen["countsByTier"] != committed["countsByTier"]
