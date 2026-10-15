#!/usr/bin/env python3
"""Validate and print the curated five-module readiness ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsplacement.readiness import load_and_validate


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path,
                        default=ROOT / "research/five-module-readiness.json")
    args = parser.parse_args()
    report = load_and_validate(args.ledger, ROOT)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
