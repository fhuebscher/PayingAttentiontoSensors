#!/usr/bin/env python3
"""Print a compact one-line status for the running Hotel Reservation campaign.

Read-only. Mirrors scratchpad/gate-drivers/campaign_status.py: exits 3 on a
terminal state so a watcher loop (mirroring campaign_watch.sh) stops
polling. Terminal detection is `obsplacement.gate_driver.terminal_status.
is_terminal` -- identical logic to TeaStore's, since campaign_status.py's
terminal check has no SUT-specific content (see that module's docstring).

STATUS: mated to Hotel's orchestrator (2026-09-05) through
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


def main() -> int:
    transport = load_sut_module(
        CONFIG.root, CONFIG.transport_module, "hotel_candidate_transport",
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
    return 3 if result.terminal else 0


if __name__ == "__main__":
    raise SystemExit(main())
