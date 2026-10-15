#!/usr/bin/env python3
"""Print a compact one-line status for the running OTel Demo campaign.

Read-only. Mirrors scratchpad/gate-drivers/campaign_status.py: exits 3 on a
terminal state so a watcher loop (mirroring campaign_watch.sh) stops
polling. Terminal detection is `obsplacement.gate_driver.terminal_status.
is_terminal` -- identical logic to TeaStore's, since campaign_status.py's
terminal check has no SUT-specific content (see that module's docstring).

STATUS: mated to OTel's orchestrator (2026-09-05) through
`candidate_transport.remote_status`, which projects the detached ssh
supervisor's liveness into the shared watcher vocabulary.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_driver_config import CONFIG  # noqa: E402

from obsplacement.gate_driver.campaign_status_flow import poll_once  # noqa: E402
from obsplacement.gate_driver.contract import check_transport_contract  # noqa: E402
from obsplacement.gate_driver.gate_paths import GatePaths  # noqa: E402
from obsplacement.gate_driver.module_loader import load_sut_module  # noqa: E402

PATHS = GatePaths(CONFIG.gates_dir)


# `terminal_status.is_terminal` is an OR of four independent fail-safes, and
# every one of them fires on an identity that has not launched yet: the state
# is outside {running, starting, started} and systemd's ActiveState is
# `inactive`. That is the right default for the shared library -- over-reporting
# terminal only stops a watcher, while under-reporting it would keep one
# polling a campaign that has ended -- and it is deliberately NOT weakened
# here, because Hotel and TeaStore rely on it.
#
# What is OTel-specific is that this project's watcher may legitimately be
# started *before* the unit exists (the launcher chains `oneshot` and the
# watcher, and `systemd-run` lands a second or two later). `not-launched` is
# a state only `candidate_transport.remote_status` can produce, and only when
# the ssh poll succeeded and systemd answered `LoadState=not-found`: a real
# distinction from "ran and was collected", which answers `loaded`. So it is
# treated as pre-terminal here, in the per-SUT driver, rather than by
# loosening the shared predicate for three SUTs.
PRE_TERMINAL_STATES = ("not-launched",)


def main() -> int:
    transport = load_sut_module(
        CONFIG.root, CONFIG.transport_module, "otel_candidate_transport",
    )
    check_transport_contract(transport, label=CONFIG.transport_module)

    result = poll_once(CONFIG, transport, PATHS)
    status = result.status
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    systemd = status.get("systemdState", {}) or {}
    print(
        f"{stamp} state={status.get('state', 'UNKNOWN')} "
        f"systemd={systemd.get('activeState', '?')}/{systemd.get('subState', '?')} "
        f"result={systemd.get('result', '?')} "
        f"journalRows={status.get('journalRows', '?')} "
        f"terminal={status.get('terminalExists', False)} "
        f"abort={status.get('abortExists', False)} "
        f"lease={status.get('leaseHeld', '?')}"
    )
    if status.get("state") in PRE_TERMINAL_STATES:
        return 0
    return 3 if result.terminal else 0


if __name__ == "__main__":
    raise SystemExit(main())
