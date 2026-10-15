#!/usr/bin/env python3
"""GATE-RUN driver for OTel Demo candidate-v4: the one authorization
that permits experimental cells.

Thin per-SUT wrapper around `obsplacement.gate_driver.gate_run_flow` and
`obsplacement.gate_driver.oneshot`. Subcommands:

  refresh   re-run readiness for a fresh preflight, then derive the run
            authorization (prints the sentence the harness derived)
  dryrun    replay every condition the remote will enforce, no launch
  oneshot   refresh -> dry-run -> execute, all in one process and WITHOUT
            a prompt: the driver hands `cmd_execute` the sentence the
            harness itself derived (`adapter.expected_gate_run_text` of
            run-authorization.json), and `cmd_execute` still verifies it
            byte-exactly against that same derivation before anything
            launches. The operator removed the interactive approval on
            2026-09-05: the human decision is the typed SETUP-CAMPAIGN
            sentence and the choice to run `oneshot`; a second keyboard
            round trip only spends the 900-second preflight window.
  execute   verify a sentence and launch the campaign (kept for the
            manual route; `oneshot` calls it)
  archive-run
            move aborted run-phase gate state aside (Hotel lesson 9); the
            write-new-json documents refuse to be overwritten, so an abort
            otherwise blocks the next derivation

`oneshot --reuse-install` refreshes readiness only (`gate_setup.py
readiness` under the existing GATE-SETUP and install receipt) instead of
re-running the whole `campaign_setup.py auto` (bundle upload + image
rebuild). OTel's orchestrator mints a fresh readiness capture id per
capture, so the prior `fetched-readiness/` is archived aside first and a
new capture lands in its place; this narrows the window, it does not
widen it -- the preflight is genuinely re-captured on the target and
`cmd_execute` still enforces its age.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_driver_config import CONFIG, DRIVER_SCRATCH  # noqa: E402

from obsplacement.gate_driver import gate_run_flow as flow  # noqa: E402
from obsplacement.gate_driver.contract import (  # noqa: E402
    check_adapter_contract,
    check_transport_contract,
    git_head_commit,
)
from obsplacement.gate_driver.gate_paths import GatePaths  # noqa: E402
from obsplacement.gate_driver.json_io import read_json  # noqa: E402
from obsplacement.gate_driver.module_loader import load_sut_module  # noqa: E402
from obsplacement.gate_driver.oneshot import run_oneshot_unattended  # noqa: E402

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


def _driver(name: str) -> list[str]:
    return [sys.executable, "-u", str(Path(__file__).resolve().parent / name)]


def refresh_readiness_via_campaign_setup() -> int:
    """Full refresh: bundle, install, image build and readiness via campaign_setup.py auto."""
    result = subprocess.run(_driver("campaign_setup.py") + ["auto"], capture_output=True)
    if result.returncode != 0:
        print("FATAL: readiness refresh failed")
        print(result.stdout.decode("utf-8", "replace")[-2000:])
        print(result.stderr.decode("utf-8", "replace")[-2000:])
    return result.returncode


def refresh_readiness_only() -> int:
    """Readiness-only refresh under the existing GATE-SETUP and install receipt.

    Archives the prior `fetched-readiness/` (gate_setup_flow.cmd_readiness
    refuses to write into an existing one) and re-captures. Returns 2 when
    nothing is installed to reuse so the caller can fall back to the full
    refresh; 1 on failure.
    """
    if not PATHS.install_receipt.is_file():
        print("no install-receipt.json: nothing is installed to reuse")
        return 2
    fetched = PATHS.fetched_readiness
    # `gate_setup_flow.cmd_readiness` calls `refuse_existing(fetched)`, so the
    # prior capture has to move aside before a re-capture. OTel's capture is a
    # plain scp of one readiness.json (no tarball), so unlike Hotel there is no
    # second stale artefact to chase -- but the archive-never-delete rule is
    # the same, and it is what keeps the aborted attempt's evidence.
    archive = fetched.with_name(
        "archived-preflight-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    if fetched.exists():
        fetched.rename(archive)
        print(f"   archived prior readiness -> {archive.name}")
    sys.stdout.flush()
    result = subprocess.run(_driver("gate_setup.py") + ["readiness"], cwd=str(CONFIG.root))
    if result.returncode != 0 or not PATHS.fetched_readiness_document.is_file():
        print("FATAL: readiness-only refresh failed")
        return 1
    return 0


def _print_derivation(derivation) -> None:
    authorization = derivation.authorization
    # This is display only, and it was written against TeaStore's authorization
    # shape: `compiledPlanCanonicalSha256`, `readinessCaptureId` and `deadline`
    # do not exist on an OTel authorization, whose equivalents are
    # `gatePlanSha256`, `runtimeReadinessSha256` and `authorizationDeadline`.
    # A KeyError here aborted a run whose authorization had already derived
    # correctly, so every lookup is now tolerant: a printer must never be able
    # to stop a launch.
    def field(*names):
        for name in names:
            if name in authorization:
                return authorization[name]
        return "-"

    print(f"  campaign      {field('campaignId')}")
    print(f"  plan          {field('gatePlanSha256', 'compiledPlanCanonicalSha256')}")
    print(f"  readiness     {derivation.readiness_sha256}")
    print(f"  capture       {field('runtimeReadinessSha256', 'readinessCaptureId')} "
          f"observed {field('readinessObservedAt')}")
    print(f"  deadline      {field('authorizationDeadline', 'deadline')}")
    print()
    print("HARNESS-DERIVED GATE-RUN SENTENCE (valid 15 minutes):")
    print(derivation.sentence)


def cmd_refresh(*, reuse_install: bool = False) -> int:
    adapter, _ = modules()
    commit = git_head_commit(CONFIG.root)
    print(f"frameworkCommit {commit}")
    print("== re-running readiness for a fresh preflight ==")
    print("   (the preflight must be under 15 minutes old at execution)")
    refresh = refresh_readiness_via_campaign_setup
    if reuse_install:
        if PATHS.install_receipt.is_file():
            print("   readiness only (reusing the installed release)")
            refresh = refresh_readiness_only
        else:
            print("   nothing installed to reuse; falling back to the full refresh")
    try:
        derivation = flow.cmd_refresh(
            CONFIG, adapter, PATHS, framework_commit=commit, refresh_readiness=refresh,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}")
        return 1
    _print_derivation(derivation)
    return 0


def cmd_dryrun() -> int:
    adapter, transport = modules()
    commit = git_head_commit(CONFIG.root)
    if not PATHS.run_authorization.is_file():
        # A dry run before anything is derived is an operator mistake, not a
        # defect; report it the way every other subcommand reports a refusal
        # instead of letting a bare FileNotFoundError traceback reach a
        # launcher script that only reads the exit code.
        print("FATAL: no run-authorization.json; run 'gate_run.py refresh' first")
        return 2
    try:
        result = flow.run_dry_run(
            CONFIG, adapter, transport, PATHS, framework_commit=commit,
            scratch_dir=DRIVER_SCRATCH / "dryrun",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}")
        return 2
    if result.ok:
        print("DRY RUN OK - local plumbing and the target's own validators accept it")
        remote_input = result.remote_input or {}
        print(f"  campaignId  {remote_input.get('campaignId')}")
        print(f"  admission   {remote_input.get('admissionCanonicalSha256')}")
        print("  (no launch attempted; probe document is scratch-only)")
        return 0
    print("DRY RUN FAILED - the remote would refuse this package:")
    for reason in result.reasons:
        print(f"    {reason}")
    return 1


def cmd_execute(typed: str) -> int:
    adapter, transport = modules()
    commit = git_head_commit(CONFIG.root)
    trace_path = DRIVER_SCRATCH / "campaign-trace.log"
    try:
        result = flow.cmd_execute(
            CONFIG, adapter, transport, PATHS, framework_commit=commit,
            typed=typed, trace_path=trace_path,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc}")
        return 2
    print("GATE-RUN sentence matches harness derivation exactly")
    print("== LAUNCHED CAMPAIGN (one shot, no retry) ==")
    print(result)
    return 0


def harness_sentence() -> str:
    """The sentence the harness derives for the run authorization on disk --
    the only place this driver ever obtains one."""
    adapter, _ = modules()
    return adapter.expected_gate_run_text(read_json(PATHS.run_authorization))


def cmd_oneshot(*, reuse_install: bool = False) -> int:
    outcome = run_oneshot_unattended(
        lambda: cmd_refresh(reuse_install=reuse_install), cmd_dryrun,
        harness_sentence, cmd_execute,
    )
    if outcome.stage == "dryrun":
        print("\nAborting: the remote would refuse this package.")
    elif outcome.stage == "aborted-empty-input":
        print("empty derivation; nothing launched")
    return outcome.returncode


RUN_PHASE_DOCUMENTS = (
    "run-authorization.json", "run-authorization-receipt.json", "gate-run.json",
    "runtime-package.json", "campaign-terminal.json",
)


def cmd_archive_run() -> int:
    """Move the run-phase gate state aside after an abort. Hotel lesson 9.

    `gate_run_flow` writes `gate-run.json` and `run-authorization.json` with
    `write_new_json` -- a second derivation refuses rather than silently
    recording a different sentence under the same name. That is right, and it
    means an aborted attempt leaves state the next attempt cannot write over.
    Hotel spent one launch attempt discovering this with no archiver in hand;
    here it is a subcommand, and it archives rather than deletes, because the
    refused documents are the only local record of the attempt that failed.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = CONFIG.gates_dir / f"archived-run-{stamp}-aborted"
    moved = []
    for name in RUN_PHASE_DOCUMENTS:
        path = CONFIG.gates_dir / name
        if path.exists() or path.is_symlink():
            archive.mkdir(parents=True, exist_ok=True)
            path.rename(archive / name)
            moved.append(name)
    result = PATHS.campaign_result
    if result.exists():
        archive.mkdir(parents=True, exist_ok=True)
        result.rename(archive / result.name)
        moved.append(result.name)
    if not moved:
        print("no run-phase gate state to archive")
        return 0
    print(f"archived {len(moved)} item(s) -> {archive}")
    for name in moved:
        print(f"   {name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--reuse-install", action="store_true")
    sub.add_parser("dryrun")
    oneshot = sub.add_parser("oneshot")
    oneshot.add_argument(
        "--reuse-install", action="store_true",
        help="refresh readiness only under the existing install; skip bundle upload and image rebuild",
    )
    execute = sub.add_parser("execute")
    execute.add_argument("--typed", required=True)
    sub.add_parser(
        "archive-run",
        help="move aborted run-phase gate state aside so the next attempt can derive",
    )
    args = parser.parse_args()
    if args.command == "refresh":
        return cmd_refresh(reuse_install=args.reuse_install)
    if args.command == "dryrun":
        return cmd_dryrun()
    if args.command == "oneshot":
        return cmd_oneshot(reuse_install=args.reuse_install)
    if args.command == "archive-run":
        return cmd_archive_run()
    return cmd_execute(args.typed)


if __name__ == "__main__":
    raise SystemExit(main())
