"""Fail-closed filesystem primitives (non-negotiable property #5).

Two distinct patterns from the canonical drivers, generalized:

1. Refuse to overwrite a path that already exists (gate_setup.py's
   cmd_readiness: "FATAL: {local_output} already exists; move it aside",
   gate_setup.py:261-262). Used for `write_new_json` and for local output
   directories such as `fetched-readiness/`.

2. A single-flight lock so overlapping attempts cannot corrupt each other's
   gate documents (campaign_setup.py cmd_auto, gate_setup.py:263-279): two
   overlapping `auto` runs on 2026-09-01 (05:31:59 / 05:33:00) let the second
   steal the first's gate-plan.json mid-flight. The fix is an
   `os.O_CREAT | os.O_EXCL` lock file, held for the duration of the mutating
   work and always removed on exit (including on exception).

A third pattern -- archive rather than delete -- covers the `auto` flow's
`archive_previous` (campaign_setup.py:219-234): live gate documents are moved
aside to a timestamped directory before new ones are written, so "iterate
setup under one SETUP-CAMPAIGN authorization" never loses the previous
attempt's evidence either.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .errors import ConcurrentRunError, PathAlreadyExists
from .freshness import now, stamp

__all__ = [
    "refuse_existing",
    "SingleFlightLock",
    "archive_live_documents",
]


def refuse_existing(path: Path) -> None:
    """Fail closed with `PathAlreadyExists` if `path` (file, dir, or symlink) exists."""
    if path.exists() or path.is_symlink():
        raise PathAlreadyExists(path)


class SingleFlightLock:
    """Exclusive lock file guarding a mutating run.

    Reproduces campaign_setup.py's `cmd_auto` lock exactly: `O_CREAT |
    O_EXCL` (atomic create-or-fail, no TOCTOU window), the lock file's body
    records `pid=<pid> at=<timestamp>` for postmortem, and the lock is always
    released on the way out -- including on an exception -- via
    `Path.unlink(missing_ok=True)`.

    Usage::

        with SingleFlightLock(gates_dir / ".auto.lock"):
            ... mutating work ...

    Raises `ConcurrentRunError` immediately (before entering the `with` body)
    if another attempt already holds the lock; never blocks or retries --
    silently waiting would be its own way of eventually corrupting a
    concurrently-written document.
    """

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path

    def __enter__(self) -> "SingleFlightLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ConcurrentRunError(self.lock_path) from exc
        os.write(handle, f"pid={os.getpid()} at={stamp(now())}\n".encode())
        os.close(handle)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.lock_path.unlink(missing_ok=True)
        return None


def archive_live_documents(gates_dir: Path, names: tuple[str, ...], *,
                            commit: str, extra_dirs: tuple[str, ...] = ()) -> Path | None:
    """Move any of `names`/`extra_dirs` present under `gates_dir` into a fresh
    `attempt-<timestamp>-<commit[:8]>/` directory, preserving them rather than
    letting the next write silently replace them.

    Generalizes campaign_setup.py's `archive_previous` (campaign_setup.py:
    219-234). Returns the archive directory, or `None` if nothing was present
    (matching the canonical function's early return).
    """
    present = [name for name in names if (gates_dir / name).exists()]
    present_dirs = [name for name in extra_dirs if (gates_dir / name).exists()]
    if not present and not present_dirs:
        return None
    destination = gates_dir / f"attempt-{stamp(now()).replace(':', '')}-{commit[:8]}"
    destination.mkdir(parents=True, exist_ok=True)
    for name in present:
        shutil.move(str(gates_dir / name), str(destination / name))
    for name in present_dirs:
        shutil.move(str(gates_dir / name), str(destination / name))
    return destination
