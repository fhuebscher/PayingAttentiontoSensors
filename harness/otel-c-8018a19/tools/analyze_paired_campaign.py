#!/usr/bin/env python3
"""Analyze a fetched randomized posture campaign at the run/block level."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from obsplacement.paired_analysis import analyze_directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = analyze_directory(args.campaign)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
