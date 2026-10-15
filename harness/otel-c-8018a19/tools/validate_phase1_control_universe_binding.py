#!/usr/bin/env python3
"""Recompute every ``research/phase1-control-universe.json`` file digest and compare.

The matrix binds control-universe claims to source files by sha256. A digest is only
honest if the bound file and the matrix that records its digest move together. Two
failure modes exist and they need different readers:

``--worktree`` (default)
    Compare the recorded digests against the files on disk. This is what
    ``tests/test_phase1_control_universe.py::test_matrix_is_bound_to_current_authoritative_sources``
    already does; the mode exists here so the same code answers both questions.

``--staged``
    Compare against the *git index* -- exactly the bytes the next commit will
    contain, whether or not each file was individually staged. This is the mode that
    catches a split commit: staging ``modules/otel-demo/materialize.py`` without
    ``research/phase1-control-universe.json`` (or the reverse) leaves the index
    carrying a matrix whose digest describes bytes that are not in the commit, and
    the binding is then a lie. Wire it as a pre-commit hook:

        #!/bin/sh
        exec python3 tools/validate_phase1_control_universe_binding.py --staged

Exit status is 0 when every binding agrees and 1 otherwise; every disagreement is
printed, not just the first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterator, Optional

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = "research/phase1-control-universe.json"

# A reader maps a repository-relative path to its bytes, or None when the path is
# absent from whatever revision the reader speaks for.
Reader = Callable[[str], Optional[bytes]]


def iter_bindings(document: object, where: str = "$") -> Iterator[tuple[str, dict]]:
    """Yield every ``{"path": ..., "sha256": ...}`` object anywhere in the matrix.

    Deliberately structural rather than keyed on ``sourceBindings`` /
    ``runtimeEvidenceBindings``: a new binding list added later is covered without
    anyone remembering to widen this checker.
    """
    if isinstance(document, dict):
        if isinstance(document.get("path"), str) and isinstance(document.get("sha256"), str):
            yield where, document
        for key, value in document.items():
            yield from iter_bindings(value, f"{where}.{key}")
    elif isinstance(document, list):
        for index, value in enumerate(document):
            yield from iter_bindings(value, f"{where}[{index}]")


def evaluate(matrix_bytes: bytes, read_bytes: Reader) -> list[str]:
    """Return one message per binding whose recorded digest does not match."""
    try:
        matrix = json.loads(matrix_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return [f"{MATRIX_PATH} is not readable JSON: {exc}"]
    problems: list[str] = []
    seen: set[str] = set()
    for where, binding in iter_bindings(matrix):
        relative = binding["path"]
        seen.add(relative)
        payload = read_bytes(relative)
        if payload is None:
            problems.append(f"{where} {relative}: bound file is absent")
            continue
        actual = hashlib.sha256(payload).hexdigest()
        if actual != binding["sha256"]:
            problems.append(
                f"{where} {relative}: matrix records {binding['sha256']} "
                f"but the bytes hash to {actual} -- commit {relative} and "
                f"{MATRIX_PATH} together"
            )
    if not seen:
        problems.append(f"{MATRIX_PATH} declares no path/sha256 bindings at all")
    return problems


def worktree_reader(root: Path) -> Reader:
    def read(relative: str) -> Optional[bytes]:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            return None
        return path.read_bytes()

    return read


def index_reader(root: Path) -> Reader:
    def read(relative: str) -> Optional[bytes]:
        result = subprocess.run(
            ["git", "cat-file", "blob", f":{relative}"],
            cwd=str(root), capture_output=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    return read


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged", action="store_true",
        help="check the git index (the bytes the next commit will carry)",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    read_bytes = index_reader(root) if arguments.staged else worktree_reader(root)
    matrix_bytes = read_bytes(MATRIX_PATH)
    if matrix_bytes is None:
        print(f"{MATRIX_PATH} is absent", file=sys.stderr)
        return 1
    problems = evaluate(matrix_bytes, read_bytes)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        source = "the git index" if arguments.staged else "the working tree"
        print(
            f"{len(problems)} phase1 control-universe binding(s) disagree with {source}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
