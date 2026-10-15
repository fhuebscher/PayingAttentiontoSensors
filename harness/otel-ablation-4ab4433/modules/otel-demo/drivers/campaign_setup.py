#!/usr/bin/env python3
"""Campaign-bound setup driver for OTel Demo candidate-v4.

One typed SETUP-CAMPAIGN sentence authorizes repeated setup attempts while
campaign identity is unchanged; GATE-RUN always requires its own fresh typed
sentence regardless (see obsplacement.gate_driver.campaign_authorization's
module docstring). Mirrors scratchpad/gate-drivers/campaign_setup.py:

  propose-campaign            emit the SETUP-CAMPAIGN sentence to type
  authorize-campaign --typed  record it after a byte-exact match
  record-probe                store the posture-connection-probe receipt that
                              `auto` requires (v2 descriptor precondition)
  auto                        prepare + install + readiness, no typing
  status                      show the current authorization

The v2 study epoch declares `tools/posture_connection_probe.sh` as a
GATE-SETUP precondition (descriptor `setupPreconditions[0]`): the five
in-code-SDK source guards were once proven only by text match and missed
currencyservice's `initLogger()` (2026-09-06); only counting OTLP connections
per posture sees a missed SDK init. `record-probe` parses the probe's
transcript and binds the receipt to the pinned upstream commit and the probe
script's bytes; `auto` refuses without a receipt that still matches both, so
an upstream re-pin or a probe-script edit invalidates the receipt by itself.

STATUS: mated to OTel's orchestrator (2026-09-05); see gate_driver_config.py.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_driver_config import CONFIG, DRIVER_SCRATCH  # noqa: E402

from obsplacement.gate_driver import campaign_setup_flow as flow  # noqa: E402
from obsplacement.gate_driver.contract import (  # noqa: E402
    check_adapter_contract,
    check_transport_contract,
    git_head_commit,
)
from obsplacement.gate_driver.errors import GateDriverError  # noqa: E402
from obsplacement.gate_driver.freshness import now, stamp  # noqa: E402
from obsplacement.gate_driver.gate_paths import GatePaths  # noqa: E402
from obsplacement.gate_driver.json_io import read_json, write_json  # noqa: E402
from obsplacement.gate_driver.module_loader import load_sut_module  # noqa: E402

PATHS = GatePaths(CONFIG.gates_dir)

# The posture-connection-probe receipt `auto` requires. Lives beside the gate
# documents, is overwritten by every `record-probe` (a newer probe of the same
# release supersedes an older one; there is nothing to archive), and is bound
# to the exact probe script bytes and pinned upstream commit it was run for.
PROBE_TOOL = "modules/otel-demo/tools/posture_connection_probe.sh"
PROBE_RECEIPT = CONFIG.gates_dir / "posture-probe-receipt.json"
PROBE_RECEIPT_KIND = "otel-demo-posture-connection-probe-receipt-v1"
_PROBE_COUNT = re.compile(r"^OTEL_PLACEMENT_ENABLED=(false|true) otlp-connections=(\d+) ", re.MULTILINE)
_PROBE_OK = re.compile(r"^PROBE OK: disabled posture is silent, enabled posture exports$", re.MULTILINE)


def parse_probe_transcript(text: str) -> dict:
    """Read the two per-posture connection counts and the PROBE OK line out of
    the probe's stdout. Pure; raises GateDriverError on anything but a clean
    two-posture pass (disabled == 0 and enabled >= 1)."""
    counts = {posture: int(count) for posture, count in _PROBE_COUNT.findall(text)}
    if set(counts) != {"false", "true"}:
        raise GateDriverError(
            "probe transcript does not report exactly one connection count per posture"
        )
    if _PROBE_OK.search(text) is None:
        raise GateDriverError("probe transcript has no PROBE OK line")
    if counts["false"] != 0 or counts["true"] < 1:
        raise GateDriverError(
            f"probe counts are not a pass: disabled={counts['false']} enabled={counts['true']}"
        )
    return {"disabledOtlpConnections": counts["false"], "enabledOtlpConnections": counts["true"]}


def _probe_script_sha256() -> str:
    return hashlib.sha256((CONFIG.root / PROBE_TOOL).read_bytes()).hexdigest()


def build_probe_receipt(adapter, transcript: str, *, materialized_root: str,
                        framework_commit: str, at=None) -> dict:
    counts = parse_probe_transcript(transcript)
    allocation = adapter.runtime.target_allocation()
    return {
        "schemaVersion": 1,
        "kind": PROBE_RECEIPT_KIND,
        "result": "PROBE OK",
        **counts,
        "probeTool": PROBE_TOOL,
        "probeScriptSha256": _probe_script_sha256(),
        "upstreamCommit": allocation["source"]["upstreamCommit"],
        "materializedRoot": str(materialized_root),
        "transcriptSha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        "frameworkCommit": framework_commit,
        "recordedAt": stamp(at if at is not None else now()),
        "runtimeAuthorized": False,
    }


def require_probe_receipt(adapter, receipt_path: Optional[Path] = None) -> dict:
    """Fail closed unless a probe receipt exists for these exact probe-script
    bytes and this exact upstream pin. No time window: the precondition is
    per release, not per hour, and both bindings move when the release does.

    `receipt_path` is late-bound on purpose. A `receipt_path: Path =
    PROBE_RECEIPT` default is evaluated at import, so the module global could
    never be patched and the guard's own test was passing only while no receipt
    happened to exist on disk. It stopped testing anything the moment a real one
    was recorded (2026-09-15).
    """
    if receipt_path is None:
        receipt_path = PROBE_RECEIPT
    if not receipt_path.is_file():
        raise GateDriverError(
            "no posture-probe receipt: run modules/otel-demo/tools/posture_connection_probe.sh "
            "against the materialized tree, then `campaign_setup.py record-probe --transcript <file> "
            "--materialized-root <dir>` (v2 descriptor precondition posture-connection-probe-ok)"
        )
    receipt = read_json(receipt_path)
    expected_upstream = adapter.runtime.target_allocation()["source"]["upstreamCommit"]
    if (
        receipt.get("kind") != PROBE_RECEIPT_KIND
        or receipt.get("result") != "PROBE OK"
        or receipt.get("disabledOtlpConnections") != 0
        or not isinstance(receipt.get("enabledOtlpConnections"), int)
        or receipt["enabledOtlpConnections"] < 1
        or receipt.get("runtimeAuthorized") is not False
    ):
        raise GateDriverError("posture-probe receipt is not a clean two-posture pass")
    if receipt.get("probeScriptSha256") != _probe_script_sha256():
        raise GateDriverError(
            "posture-probe receipt was recorded for different probe-script bytes; re-run the probe"
        )
    if receipt.get("upstreamCommit") != expected_upstream:
        raise GateDriverError(
            "posture-probe receipt was recorded for a different upstream pin; re-run the probe"
        )
    return receipt


def modules():
    adapter = load_sut_module(
        CONFIG.root, CONFIG.adapter_module, "otel_candidate_runtime_adapter",
    )
    transport = load_sut_module(
        CONFIG.root, CONFIG.transport_module, "otel_candidate_transport",
    )
    check_adapter_contract(adapter, label=CONFIG.adapter_module)
    check_transport_contract(transport, label=CONFIG.transport_module)
    return adapter, transport


def cmd_propose() -> int:
    adapter, _ = modules()
    commit = git_head_commit(CONFIG.root)
    pending = flow.cmd_propose(CONFIG, adapter, PATHS, framework_commit=commit)
    print(f"  descriptor {pending['invariants']['descriptorCanonicalSha256']}")
    print(f"  plan       {pending['invariants']['compiledPlanCanonicalSha256']}")
    print(f"  runs       {pending['invariants']['runs']}")
    print(f"  deadline   {pending['deadline']}")
    print()
    print("TYPE THIS EXACT SENTENCE TO AUTHORIZE THE SETUP CAMPAIGN:")
    print(pending["expectedText"])
    return 0


def cmd_authorize(typed: str) -> int:
    try:
        record = flow.cmd_authorize(CONFIG, PATHS, typed=typed)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}")
        return 2
    print("typed SETUP-CAMPAIGN sentence matches derivation exactly")
    print(f"valid until {record['deadline']}")
    print("setup may now iterate across framework commits without re-typing;")
    print("GATE-RUN still requires its own fresh typed sentence.")
    return 0


def cmd_record_probe(transcript: Path, materialized_root: Path) -> int:
    adapter, _ = modules()
    commit = git_head_commit(CONFIG.root)
    try:
        receipt = build_probe_receipt(
            adapter, Path(transcript).read_text(encoding="utf-8"),
            materialized_root=str(materialized_root), framework_commit=commit,
        )
    except (OSError, GateDriverError) as exc:
        print(f"FATAL: {exc}")
        return 2
    write_json(PROBE_RECEIPT, receipt)
    print(f"posture-probe receipt recorded at {PROBE_RECEIPT}")
    print(f"  disabled otlp-connections {receipt['disabledOtlpConnections']}")
    print(f"  enabled  otlp-connections {receipt['enabledOtlpConnections']}")
    print(f"  upstream {receipt['upstreamCommit']} probe-script {receipt['probeScriptSha256'][:12]}")
    return 0


def cmd_auto() -> int:
    adapter, transport = modules()
    commit = git_head_commit(CONFIG.root)
    try:
        require_probe_receipt(adapter)
        admission = flow.cmd_auto(
            CONFIG, adapter, transport, PATHS, framework_commit=commit,
            trace_dir=DRIVER_SCRATCH,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}")
        return 1
    print(f"frameworkCommit {commit} (may advance under this authorization)")
    print("READINESS ADMITTED")
    print(f"  readinessCanonicalSha256 {admission.get('readinessCanonicalSha256')}")
    return 0


def cmd_status() -> int:
    adapter, _ = modules()
    commit = git_head_commit(CONFIG.root)
    print(f"HEAD {commit}")
    report = flow.cmd_status(CONFIG, adapter, PATHS, framework_commit=commit)
    if not report.has_campaign:
        print("no SETUP-CAMPAIGN authorization recorded")
        return 0
    print(f"authorized {report.approved_at} deadline {report.deadline} live={report.live}")
    print(f"invariants match={report.invariants_match}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("propose-campaign")
    authorize = sub.add_parser("authorize-campaign")
    authorize.add_argument("--typed", required=True)
    probe = sub.add_parser("record-probe")
    probe.add_argument("--transcript", type=Path, required=True,
                       help="stdout of posture_connection_probe.sh, saved to a file")
    probe.add_argument("--materialized-root", type=Path, required=True,
                       help="the materialized tree the probe was run against")
    sub.add_parser("auto")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "propose-campaign":
        return cmd_propose()
    if args.command == "authorize-campaign":
        return cmd_authorize(args.typed)
    if args.command == "record-probe":
        return cmd_record_probe(args.transcript, args.materialized_root)
    if args.command == "status":
        return cmd_status()
    return cmd_auto()


if __name__ == "__main__":
    raise SystemExit(main())
