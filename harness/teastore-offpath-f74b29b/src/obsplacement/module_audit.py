"""Enforce that every SUT-specific implementation file has a ledger class."""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path


PATH_RE = re.compile(r"^\s*- path:\s*(\S+)\s*$")
CLASS_RE = re.compile(r"^\s+class:\s*(\S+)\s*$")
IGNORED_NAMES = {"README.md", "source.lock", "extension-ledger.yaml"}


def ledger_entries(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    pending: str | None = None
    for line in path.read_text().splitlines():
        if match := PATH_RE.match(line):
            pending = match.group(1)
        elif pending and (match := CLASS_RE.match(line)):
            entries[pending] = match.group(1)
            pending = None
    return entries


def audit(module: Path) -> dict:
    entries = ledger_entries(module / "extension-ledger.yaml")
    files = {
        str(path.relative_to(module)): path
        for path in module.rglob("*")
        if path.is_file()
        and path.name not in IGNORED_NAMES
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    missing = sorted(set(files) - set(entries))
    stale = sorted(set(entries) - set(files))
    lines = Counter()
    for relative, path in files.items():
        if relative in entries:
            with path.open(errors="replace") as handle:
                lines[entries[relative]] += sum(1 for _ in handle)
    return {
        "module": module.name,
        "verdict": "pass" if not missing and not stale else "blocked",
        "classified_files": len(files) - len(missing),
        "unclassified_files": missing,
        "stale_ledger_entries": stale,
        "lines_by_class": dict(sorted(lines.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path)
    args = parser.parse_args()
    import json
    result = audit(args.module)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
