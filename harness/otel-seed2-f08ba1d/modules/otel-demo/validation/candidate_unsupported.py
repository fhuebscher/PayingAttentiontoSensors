#!/usr/bin/env python3
"""Exact terminal validator for the UNSUPPORTED v1 OTel Demo epoch.

This validator is scoped to study epoch ``otel-demo-candidate-pilot-v1``: it
reads no empirical result tree and accepts no gate package.  It replays the
frozen 18 v1 cell identities, the provenance-only target-allocation digest,
the denial of attempts, numeric results, gates, mutation, and promotion, and
the ledger's ``scope`` block naming ``otel-demo-candidate-pilot-v2`` as the
successor.  It says nothing about any v2 cell; the v2 epoch's terminal
validator is ``candidate_terminal.py``.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_PATH = ROOT / "modules/otel-demo/execution/candidate_runtime.py"
EVIDENCE_PATH = ROOT / "modules/otel-demo/execution/candidate-unsupported.json"
EXPECTED_CELLS = 18


class UnsupportedValidationError(ValueError):
    """The frozen non-running disposition or ledger differs."""


def _runtime():
    spec = importlib.util.spec_from_file_location(
        "otel_candidate_unsupported_runtime", RUNTIME_PATH
    )
    if spec is None or spec.loader is None:
        raise UnsupportedValidationError("UNSUPPORTED runtime validator cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_unsupported_disposition(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact design/ledger denial and normalize the error surface."""

    runtime = _runtime()
    try:
        checked = runtime.validate_unsupported_evidence(document)
    except Exception as exc:
        raise UnsupportedValidationError(
            f"OTel UNSUPPORTED disposition failed closed: {exc}"
        ) from exc
    if (
        checked["executionDisposition"] != "unsupported"
        or checked["empiricalResultState"] != "UNSUPPORTED"
        or len(checked["cellLedger"]) != EXPECTED_CELLS
        or checked["maximumEvidenceLabel"] is not None
        or checked["canonical"] is not False
        or checked["promotionAuthorized"] is not False
        or any(checked["permissions"].values())
        or checked["targetBinding"]["runtimeAuthority"] is not False
        or checked["targetBinding"]["externalMutationAllowed"] is not False
        or any(row["externalAttempt"] is not False for row in checked["cellLedger"])
        or any(row["numericResults"] is not None for row in checked["cellLedger"])
        or any(
            row["empiricalResultState"] != "UNSUPPORTED"
            for row in checked["cellLedger"]
        )
    ):
        raise UnsupportedValidationError(
            "OTel UNSUPPORTED result, permission, attempt, or numeric ceiling differs"
        )
    return checked


def load_and_validate() -> dict[str, Any]:
    runtime = _runtime()
    try:
        document = runtime.strict_json_bytes(
            runtime._read_file(EVIDENCE_PATH, "OTel UNSUPPORTED evidence"),
            "OTel UNSUPPORTED evidence",
        )
    except Exception as exc:
        raise UnsupportedValidationError(
            f"cannot read exact OTel UNSUPPORTED evidence: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise UnsupportedValidationError("OTel UNSUPPORTED evidence is not an object")
    return validate_unsupported_disposition(document)


def terminal_report() -> dict[str, Any]:
    evidence = load_and_validate()
    cells = [
        {
            "runId": row["runId"],
            "runKey": copy.deepcopy(row["runKey"]),
            "state": row["empiricalResultState"],
            "externalAttempt": row["externalAttempt"],
            "numericResults": row["numericResults"],
            "reasonIds": list(row["reasonIds"]),
        }
        for row in evidence["cellLedger"]
    ]
    return {
        "schemaVersion": 1,
        "kind": "otel-demo-candidate-unsupported-terminal-v1",
        "studyEpoch": evidence["studyEpoch"],
        "executionDisposition": "unsupported",
        "empiricalResultState": "UNSUPPORTED",
        "targetBinding": copy.deepcopy(evidence["targetBinding"]),
        "expectedCells": EXPECTED_CELLS,
        "observedCells": 0,
        "validCells": 0,
        "unsupportedCells": EXPECTED_CELLS,
        "cells": cells,
        "verdict": "unsupported",
        "maximumEvidenceLabel": None,
        "canonical": False,
        "promotionAuthorized": False,
    }


def validate_campaign(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Reject result-bearing call shapes; this route accepts no campaign input."""

    if _args or _kwargs:
        raise UnsupportedValidationError(
            "UNSUPPORTED terminal accepts no empirical root, result tree, or gate package"
        )
    return terminal_report()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    print(json.dumps(terminal_report(), indent=2, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "UnsupportedValidationError", "load_and_validate", "terminal_report",
    "validate_campaign", "validate_unsupported_disposition",
]
