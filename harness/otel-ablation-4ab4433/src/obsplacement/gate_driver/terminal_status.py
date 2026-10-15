"""Pure terminal-state detection for a running campaign, factored out of campaign_status.py.

campaign_status.py is deliberately read-only and prints one line per poll,
then exits 3 to signal "stop watching" (campaign_watch.sh treats exit code 3
as the terminal signal). The actual terminal/non-terminal decision
(campaign_status.py:46-50) is pure boolean logic over the status document the
target's installed `campaign-status` CLI returns -- it has no SUT-specific
content itself (it only reads generic fields: `state`, `systemdState.
activeState`, `terminalExists`, `abortExists`), so it belongs here rather
than being re-derived per SUT.
"""
from __future__ import annotations

__all__ = ["is_terminal", "NON_TERMINAL_STATES", "NON_TERMINAL_ACTIVE_STATES"]

# campaign_status.py:46-50's two "still running" vocabularies, named.
NON_TERMINAL_STATES = ("running", "starting", "started")
NON_TERMINAL_ACTIVE_STATES = ("active", "activating")


def is_terminal(status: dict) -> bool:
    """True iff the campaign has reached a terminal state.

    Reproduces campaign_status.py:46-50 exactly:

        terminal = (
            state.lower() not in ("running", "starting", "started")
            or terminal_flag or abort_flag
            or active not in ("active", "activating")
        )

    `state` is lower-cased before comparison (source data casing is not
    guaranteed); `activeState` is compared as-is (systemd's vocabulary is
    already a fixed lowercase set, so the canonical script never lower-cases
    it either). Any of the four independent terminal signals -- state
    outside the running vocabulary, a terminal-result file present, an abort
    file present, or systemd itself outside its active vocabulary -- is
    sufficient on its own; this is an OR of independent fail-safes, not a
    single source of truth.
    """
    state = str(status.get("state", "UNKNOWN")).lower()
    systemd = status.get("systemdState") or {}
    active = systemd.get("activeState", "?")
    terminal_flag = bool(status.get("terminalExists", False))
    abort_flag = bool(status.get("abortExists", False))
    return (
        state not in NON_TERMINAL_STATES
        or terminal_flag
        or abort_flag
        or active not in NON_TERMINAL_ACTIVE_STATES
    )
