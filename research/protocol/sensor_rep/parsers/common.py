"""Shared helpers for the per-SUT parsers: loading existing research modules by path (never edited), the cell record.

A parsed cell is a dict:
  sut, population, cell (repo-relative path), posture, regime, block, valid, target, faultKind, noFault,
  base     {clock: barrier instant in that clock}   offsets of windows are measured from here
  t0       {clock: lower bound of the old rule's pre-window, None = unbounded}
  duration measurement length in seconds (tiles never pass base + duration)
  fault    {clock: (start, end)} or None
  events   [Event]
  channels {channel: {"present": bool, "collectors": [...], "resolution": ..., "file": ...}}  (missing file -> present False)
  stats    parser statistics (lines, unparsed, untimed records, ...)
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[2]
RESEARCH = REPO / "research"
_LOADED = {}


def load(name, path):
    """Import a module by path once (as research/otel-offpath/adapter.py:50-62 does)."""
    path = Path(path)
    if path not in _LOADED:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _LOADED[path] = module
    return _LOADED[path]


def symptoms():
    return load("sensor_rep_symptoms", RESEARCH / "s4-conjunction" / "symptoms.py")


def lmt():
    return load("sensor_rep_lmt_detect", RESEARCH / "lmt-pilot" / "lmt_detect.py")


def rel(p):
    p = Path(p).resolve()
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def new_cell(sut, population, path, posture, regime, block, valid, target, fault_kind):
    return {"sut": sut, "population": population, "cell": rel(path), "posture": posture, "regime": regime,
            "block": block, "valid": bool(valid), "target": target, "faultKind": fault_kind,
            "noFault": target is None, "base": {}, "t0": {}, "duration": None, "fault": None,
            "events": [], "channels": {}, "stats": {}}
