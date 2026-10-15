#!/usr/bin/env python3
"""GATE-SETUP driver for OTel Demo candidate-v4.

Thin per-SUT wrapper: all governance logic lives in
`obsplacement.gate_driver.gate_setup_flow`; this file only supplies OTel's
`SutConfig` (see gate_driver_config.py), loads OTel's adapter/transport
modules, and prints. Subcommands mirror
scratchpad/gate-drivers/gate_setup.py exactly:

  prepare      local + read-only remote work; emits the GATE-PLAN sentence
  record-plan  verifies a user-typed GATE-PLAN sentence, records it,
               then emits the GATE-SETUP sentence
  install      MUTATES the target: exact release install + real image build
  readiness    collect target-generated readiness under the live GATE-SETUP

Typed sentences are never authored here -- see
obsplacement.gate_driver.sentence's module docstring.

STATUS: mated to OTel's orchestrator through the three shims named in
gate_driver_config.py (2026-09-05); see that file's CONTRACT STATUS section.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_driver_config import CONFIG, DRIVER_SCRATCH  # noqa: E402

from obsplacement.gate_driver import gate_setup_flow as flow  # noqa: E402
from obsplacement.gate_driver.contract import (  # noqa: E402
    check_adapter_contract,
    check_transport_contract,
    git_head_commit,
)
from obsplacement.gate_driver.gate_paths import GatePaths  # noqa: E402
from obsplacement.gate_driver.module_loader import load_binding_keys, load_sut_module  # noqa: E402

PATHS = GatePaths(CONFIG.gates_dir)


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


def cmd_prepare() -> int:
    adapter, transport = modules()
    commit = git_head_commit(CONFIG.root)
    print(f"frameworkCommit {commit}")
    print("== read-only target probe (fb14srv6) ==")
    result = flow.cmd_prepare(CONFIG, adapter, transport, PATHS, framework_commit=commit)
    print(f"  capturedAt   {result.target_proof.get('capturedAt')}")
    print("== build exact release bundle ==")
    print(f"  bundleSha256 {result.release_manifest.get('bundleSha256')}")
    # OTel's manifest names this `bundleSizeBytes` (the key `setup_binding`
    # binds a GATE-SETUP to), not TeaStore's `bundleBytes`.
    print(f"  bundleBytes  {result.release_manifest.get('bundleSizeBytes')}")
    print()
    print("TYPE THIS EXACT SENTENCE TO RE-APPROVE GATE-PLAN:")
    print(result.gate_plan_sentence)
    return 0


def cmd_record_plan(typed: str) -> int:
    adapter, _ = modules()
    commit = git_head_commit(CONFIG.root)
    try:
        result = flow.cmd_record_plan(
            CONFIG, adapter, PATHS, framework_commit=commit, typed=typed,
        )
    except Exception as exc:  # noqa: BLE001 - report and exit non-zero, never raise to the shell
        print(f"FATAL: {exc}")
        return 2
    print("typed GATE-PLAN sentence matches harness derivation exactly")
    print(f"recorded gatePlanSha256 {result.gate_plan_sha256}")
    print(f"setupId     {result.setup_id}")
    print()
    print("TYPE THIS EXACT SENTENCE TO AUTHORIZE GATE-SETUP (valid 15 minutes):")
    print(result.gate_setup_sentence)
    return 0


def cmd_install(typed: str) -> int:
    adapter, transport = modules()
    commit = git_head_commit(CONFIG.root)
    trace_path = DRIVER_SCRATCH / "install-trace.log"
    try:
        receipt = flow.cmd_install(
            CONFIG, adapter, transport, PATHS, framework_commit=commit,
            typed=typed, trace_path=trace_path,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}")
        return 2
    print("typed GATE-SETUP sentence matches harness derivation exactly")
    print(f"   command trace -> {trace_path}")
    print(f"installed at {receipt.get('releaseRoot')}")
    return 0


def cmd_readiness() -> int:
    adapter, transport = modules()
    commit = git_head_commit(CONFIG.root)
    # Property #2: binding keys are sourced fresh from the installed
    # framework every call, never a hand-copied literal.
    binding_keys = load_binding_keys(CONFIG.root, CONFIG.installer_module)
    trace_path = DRIVER_SCRATCH / "readiness-trace.log"
    try:
        admission = flow.cmd_readiness(
            CONFIG, adapter, transport, PATHS, framework_commit=commit,
            binding_keys=binding_keys, trace_path=trace_path,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}")
        return 2
    print(f"   command trace -> {trace_path}")
    print("READINESS ADMITTED")
    print(f"  readinessCanonicalSha256 {admission.get('readinessCanonicalSha256')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    record = sub.add_parser("record-plan")
    record.add_argument("--typed", required=True)
    install = sub.add_parser("install")
    install.add_argument("--typed", required=True)
    sub.add_parser("readiness")
    args = parser.parse_args()
    if args.command == "prepare":
        return cmd_prepare()
    if args.command == "record-plan":
        return cmd_record_plan(args.typed)
    if args.command == "readiness":
        return cmd_readiness()
    return cmd_install(args.typed)


if __name__ == "__main__":
    raise SystemExit(main())
