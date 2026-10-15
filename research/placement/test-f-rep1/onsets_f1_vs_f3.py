"""Compare per-cell fault onsets and run order of F attempt 1 and attempt 3 (post hoc, 2026-10-15).

Reads the two byte-verified execution packages and writes onsets_f1_vs_f3.json beside this file.
Run: uv run python research/placement/test-f-rep1/onsets_f1_vs_f3.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PACKAGES = {
    "f1": ROOT / "tmp/otel-f-evidence/f1-fetch/x/.controller/execution-package.json",
    "f3": ROOT / "tmp/otel-f-evidence/f3-fetch2/x/.controller/execution-package.json",
}


def cells(path):
    pkg = json.loads(path.read_text())
    return [
        {
            "ordinal": c["ordinalPosition"],
            "cell": c["compiledArtifactRoot"],
            "faultOnsetSeconds": c["timing"]["faultOnsetSeconds"],
            "faultOnsetPhaseOffsetSeconds": c["timing"]["faultOnsetPhaseOffsetSeconds"],
        }
        for c in sorted(pkg["cells"], key=lambda c: c["ordinalPosition"])
    ]


def main():
    a, b = cells(PACKAGES["f1"]), cells(PACKAGES["f3"])
    assert len(a) == len(b) == 25, (len(a), len(b))
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    out = {
        "cellsF1": len(a), "cellsF3": len(b),
        "identicalOrderAndOnsets": not diffs, "differences": diffs, "cells": a,
    }
    (pathlib.Path(__file__).parent / "onsets_f1_vs_f3.json").write_text(json.dumps(out, indent=1) + "\n")
    print("identical:", not diffs, "differences:", len(diffs))


if __name__ == "__main__":
    main()
