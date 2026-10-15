"""Append-only audit trail for actions taken under a SETUP-CAMPAIGN authorization.

Generalizes campaign_setup.py's `audit()` (campaign_setup.py:97-103): one
JSON object per line, sorted keys, always appended, never rewritten.
"""
from __future__ import annotations

import json
from pathlib import Path

from .freshness import now, stamp

__all__ = ["append_audit"]


def append_audit(path: Path, *, event: str, **fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps({"at": stamp(now()), "event": event, **fields},
                                 sort_keys=True) + "\n")
