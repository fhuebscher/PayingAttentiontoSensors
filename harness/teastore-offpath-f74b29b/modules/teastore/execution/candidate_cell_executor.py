#!/usr/bin/env python3
"""Gate-internal TeaStore candidate-cell producer entry point.

This entry point is reachable only from ``candidate_remote_controller``.  It
does not accept schedule, timing, posture, fault, host, or evidence-label
arguments: every such value comes from one immutable cell contract.  The
underlying producer lives in ``performance_campaign.execute_candidate_cell`` so
the diagnostic CLI and ``run_one`` remain direct-runtime denials.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[3]


class CellExecutionError(ValueError):
    """The exact candidate contract cannot be produced safely."""


def _reject_constant(value: str) -> NoReturn:
    raise CellExecutionError(f"non-finite JSON value is forbidden: {value}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CellExecutionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _contract(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise CellExecutionError("candidate cell contract is not a regular file")
    payload = path.read_bytes()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise CellExecutionError("candidate cell contract changed while being read")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
        )
    except CellExecutionError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CellExecutionError(f"candidate cell contract is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CellExecutionError("candidate cell contract is not an object")
    required = {
        "schemaVersion", "contract", "campaignId", "campaignSha256",
        "gatePlanSha256", "runtimeReadinessSha256", "gateRunSha256",
        "frameworkCommit", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "runId", "runKey", "ordinalPosition",
        "compiledArtifactRoot", "coldStart", "target", "runtimeInputs",
        "workload", "posture", "window", "faultGroundTruth",
        "pathGroundTruth", "attemptPolicy", "requiredArtifacts", "terminalPolicy",
    }
    if set(value) != required or value.get("schemaVersion") != 1 or (
        value.get("contract") != "teastore-candidate-cell-invocation-v1"
        or value.get("coldStart") is not True
        or value.get("target", {}).get("host") != "fb14srv5"
        or value.get("attemptPolicy") != {
            "attempt": 1, "startedBeforeFirstExternalMutation": True,
            "retryAllowed": False, "substitutionAllowed": False,
            "rerandomizationAllowed": False,
        }
        or value.get("terminalPolicy", {}).get("promotionAuthorized") is not False
    ):
        raise CellExecutionError("candidate cell contract identity or boundary differs")
    return value


def _producer_module():
    path = Path(__file__).with_name("performance_campaign.py")
    spec = importlib.util.spec_from_file_location(
        "teastore_candidate_cell_performance_producer", path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise CellExecutionError("cannot load TeaStore performance producer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    producer = getattr(module, "execute_candidate_cell", None)
    if not callable(producer):
        raise CellExecutionError(
            "candidate cell producer is absent; diagnostic run_one cannot substitute"
        )
    return producer


def execute(contract_path: Path, output: Path) -> dict[str, Any]:
    contract = _contract(contract_path)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise CellExecutionError("candidate output exists before first attempt")
    key = contract["runKey"]
    expected_suffix = (
        "runs",
        key["regime"],
        f"b{key['block']:02d}-{contract['ordinalPosition']:02d}-{key['posture']}",
    )
    if len(output.parts) < 3 or tuple(output.parts[-3:]) != expected_suffix:
        raise CellExecutionError("candidate output path differs from frozen campaign identity")
    return dict(_producer_module()(contract, output))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = execute(args.contract, args.output)
    except Exception as exc:  # noqa: BLE001 - emit one bounded failure record
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CellExecutionError", "execute"]
