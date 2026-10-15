#!/usr/bin/env python3
"""Replay and validate retained TeaStore native-token correlation evidence."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).parents[3]
EXTRACTOR_PATH = Path(__file__).parents[1] / "witness/extract_native_token_correlation.py"
SCHEMA_PATH = Path(__file__).parents[1] / "witness/native-token-correlation.schema.json"


def _extractor():
    spec = importlib.util.spec_from_file_location(
        "teastore_native_token_extractor_for_validation", EXTRACTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load correlation extractor: {EXTRACTOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_retained(root: Path) -> dict[str, Any]:
    root = Path(root)
    blockers: list[str] = []
    rows: Any = None
    receipt: Any = None
    expected_rows: Any = None
    expected_receipt: Any = None
    try:
        module = _extractor()
        mapping_bytes = module._file_bytes(
            root / "native-token-correlation.json", "native-token correlation")
        rows = module._strict_json(mapping_bytes, "native-token correlation")
        receipt_bytes = module._file_bytes(
            root / "native-token-correlation-extraction.json",
            "native-token correlation extraction receipt",
        )
        receipt = module._strict_json(
            receipt_bytes, "native-token correlation extraction receipt")
        schema = module._strict_json(
            module._file_bytes(SCHEMA_PATH, "native-token correlation schema"),
            "native-token correlation schema",
        )
        jsonschema.Draft202012Validator(schema, format_checker=None).validate(rows)
        for row in rows:
            core = {
                "token": row["token"],
                "nativeTraceId": module.canonical_native_trace_id(row["nativeTraceId"]),
                "service": row["service"],
            }
            if row["mappingId"] != module._mapping_id(core):
                raise module.CorrelationError("mappingId does not bind its exact row")
        expected_rows, expected_receipt = module.reconcile(
            auth_log=root / "auth.log",
            journey_ledger=root / "journey-ledger.jsonl",
            traces=root / "traces.json",
            run_receipt=root / "receipt.json",
            service_log_capture_receipt=root / "service-log-capture.json",
            posture_proof=root / "posture-proof.json",
        )
        if rows != expected_rows:
            raise module.CorrelationError(
                "retained correlation rows differ from independent source replay")
        if receipt != expected_receipt:
            raise module.CorrelationError(
                "retained extraction receipt differs from independent source replay")
    except (
        OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
        jsonschema.ValidationError,
    ) as exc:
        blockers.append(f"{type(exc).__name__}: {exc}")
    return {
        "schema": "teastore.native-token-correlation-validation-report",
        "schemaVersion": 1,
        "outcome": "pass" if not blockers else "blocked",
        "mappingRows": len(rows) if isinstance(rows, list) else None,
        "replayedRows": len(expected_rows) if isinstance(expected_rows, list) else None,
        "receiptReconciled": receipt == expected_receipt and receipt is not None,
        "runtimeActionsExecuted": False,
        "blockers": blockers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args(argv)
    report = validate_retained(args.artifact_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["outcome"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
