#!/usr/bin/env python3
"""Build a null-preserving descriptive objective index across local SUT runs.

This intentionally does not rank SUTs: their goals, loads, faults, and evidence
ceilings are not matched. It is a compact MLflow/dashboard input showing what
is actually observed and what remains unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ELIGIBLE_QUALIFICATIONS = {"candidate-evidence", "canonical-evidence"}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
        return result if math.isfinite(result) else None
    return None


def build_comparison(dataset_path: Path) -> dict[str, Any]:
    raw = dataset_path.read_bytes()
    dataset = json.loads(raw)
    directions = dataset.get("objectiveDirections", {})
    rows = dataset.get("rows", [])
    grouped: dict[tuple[str, str, str, str, str, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("campaign", "unknown")),
            str(row.get("sut", "unknown")),
            str(row.get("family", "unknown")),
            str(row.get("posture", "unknown")),
            str(row.get("curatedQualification", "unlisted-evidence")),
            row.get("sutAttributionBound") is True,
        )
        grouped[key].append(row)

    groups = []
    for (campaign, sut, family, posture, qualification, sut_bound), members in sorted(grouped.items()):
        objectives = {}
        for objective in directions:
            observed = [number for row in members
                        if (number := _finite(row.get("objectives", {}).get(objective))) is not None]
            objectives[objective] = {
                "observedRuns": len(observed),
                "missingRuns": len(members) - len(observed),
                "median": median(observed) if observed else None,
                "minimum": min(observed) if observed else None,
                "maximum": max(observed) if observed else None,
            }
        groups.append({
            "campaign": campaign,
            "sut": sut,
            "family": family,
            "posture": posture,
            "curatedQualification": qualification,
            "sutAttributionBound": sut_bound,
            "descriptiveUnbound": not sut_bound,
            "candidateRowEligible": sut_bound and qualification in ELIGIBLE_QUALIFICATIONS,
            "runCount": len(members),
            "goals": sorted({str(row.get("goal", "unknown")) for row in members}),
            "objectives": objectives,
        })

    coverage = {}
    bound_rows = [row for row in rows if row.get("sutAttributionBound") is True]
    suts = sorted({str(row.get("sut", "unknown")) for row in bound_rows})
    for objective in directions:
        observed_suts = sorted({
            str(row.get("sut", "unknown")) for row in bound_rows
            if _finite(row.get("objectives", {}).get(objective)) is not None
        })
        coverage[objective] = {
            "sutsWithAnyObservation": observed_suts,
            "sutCount": len(observed_suts),
            "missingForAllObservedSuts": not observed_suts,
        }

    try:
        source_dataset = dataset_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        source_dataset = dataset_path.resolve().as_posix()
    return {
        "schemaVersion": 1,
        "asOf": dataset.get("asOf"),
        "sourceDataset": source_dataset,
        "sourceDatasetSha256": hashlib.sha256(raw).hexdigest(),
        "policy": {
            "descriptiveOnly": True,
            "crossSutRankingAllowed": False,
            "unknownsRemainNull": True,
            "unboundRowsExcludedFromSutCoverage": True,
            "reason": (
                "Goals, offered loads, faults, windows, and scientific qualifications are not "
                "matched across SUTs; group summaries cannot establish a Pareto ordering."),
        },
        "observedSuts": suts,
        "objectiveDirections": directions,
        "objectiveCoverage": coverage,
        "groups": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "research/ml-readiness.json")
    args = parser.parse_args()
    print(json.dumps(build_comparison(args.dataset), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
