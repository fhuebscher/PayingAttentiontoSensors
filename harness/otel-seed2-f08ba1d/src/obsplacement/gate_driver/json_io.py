"""Canonical JSON read/write, shared verbatim by every canonical driver.

Every one of the four scripts in scratchpad/gate-drivers/ defines the same
`write_json`/`read_json` pair (e.g. gate_setup.py:52-60, gate_run.py:63-71,
campaign_setup.py:86-94) with identical formatting: `allow_nan=False` (a NaN
in a gate document is a bug, never a legitimate value), `indent=2,
sort_keys=True` (stable, diffable, and required for the sha256 the adapter
computes over these documents to be deterministic), and a trailing newline.
This module is that pair, once, plus a fail-closed variant for documents that
must never be silently replaced.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import PathAlreadyExists

__all__ = ["write_json", "write_new_json", "read_json"]


def write_json(path: Path, document) -> None:
    """Write `document` as canonical JSON, creating parent directories.

    Overwrites unconditionally -- callers that must not clobber a prior
    document should use `write_new_json` instead. This function exists for
    the legitimate overwrite cases the canonical drivers also have (e.g. a
    freshly rebuilt release bundle manifest, or an `auto` flow that has
    already archived the prior attempt via `fs_guards.archive_live_documents`).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    )


def write_new_json(path: Path, document) -> None:
    """Write `document`, failing closed if `path` already exists.

    Generalizes gate_setup.py's cmd_readiness guard ("FATAL: {local_output}
    already exists; move it aside", gate_setup.py:261-262) from the one path
    it protected into a primitive usable for every gate document. Prefer this
    over `write_json` for gate-plan.json / gate-setup.json / gate-run.json /
    run-authorization.json in the one-shot (non-`auto`) flow, where a second
    write silently replacing the first is exactly the failure mode that cost
    a campaign (see errors.ConcurrentRunError's docstring for the 2026-09-01
    incident this line of defense is part of).

    Uses `os.open(..., O_CREAT | O_EXCL)` -- the same atomic create-or-fail
    primitive `fs_guards.SingleFlightLock` already uses -- rather than a
    separate `exists()` check followed by a write: a plain `mv`/`os.replace`
    onto `path` from outside this function, landing in the gap between a
    check and a write, would otherwise go undetected. The bytes written are
    byte-identical to `write_json`'s (`indent=2, sort_keys=True,
    allow_nan=False`, trailing newline) so every existing reader of these
    files sees the same format either way.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        raise PathAlreadyExists(path) from exc
    try:
        os.write(handle, payload)
    finally:
        os.close(handle)


def read_json(path: Path):
    return json.loads(path.read_text())
