#!/usr/bin/env python3
"""Campaign-bound setup driver for Hotel Reservation candidate-v4.

One typed SETUP-CAMPAIGN sentence authorizes repeated setup attempts while
campaign identity is unchanged; GATE-RUN always requires its own fresh typed
sentence regardless (see obsplacement.gate_driver.campaign_authorization's
module docstring). Mirrors scratchpad/gate-drivers/campaign_setup.py:

  propose-campaign            emit the SETUP-CAMPAIGN sentence to type
  authorize-campaign --typed  record it after a byte-exact match
  auto                        prepare + install + readiness, no typing
  status                      show the current authorization

STATUS: mated to Hotel's orchestrator (2026-09-05); see gate_driver_config.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_driver_config import CONFIG, DRIVER_SCRATCH  # noqa: E402

from obsplacement.gate_driver import campaign_setup_flow as flow  # noqa: E402
from obsplacement.gate_driver.contract import (  # noqa: E402
    check_adapter_contract,
    check_transport_contract,
    git_head_commit,
)
from obsplacement.gate_driver.gate_paths import GatePaths  # noqa: E402
from obsplacement.gate_driver.module_loader import load_sut_module  # noqa: E402

PATHS = GatePaths(CONFIG.gates_dir)


def modules():
    adapter = load_sut_module(
        CONFIG.root, CONFIG.adapter_module, "hotel_candidate_runtime_adapter",
    )
    transport = load_sut_module(
        CONFIG.root, CONFIG.transport_module, "hotel_candidate_transport",
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


def cmd_auto() -> int:
    adapter, transport = modules()
    commit = git_head_commit(CONFIG.root)
    try:
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
    sub.add_parser("auto")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "propose-campaign":
        return cmd_propose()
    if args.command == "authorize-campaign":
        return cmd_authorize(args.typed)
    if args.command == "status":
        return cmd_status()
    return cmd_auto()


if __name__ == "__main__":
    raise SystemExit(main())
