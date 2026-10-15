"""The interactive oneshot launch route (non-negotiable property #3, primary route).

Generalizes gate_run.py's `cmd_oneshot` (gate_run.py:465-491) exactly:
refresh the preflight, dry-run it, prompt the operator on stdin, and execute
-- all inside one process, so no conversational round trip can let the
900-second preflight window lapse between deriving the sentence and typing
it. That exact failure (round trip lapsed the window; nothing launched,
nothing spent, but a launch attempt was lost) happened on 2026-09-04; see
`10k_footview.md`'s "Launch-path lesson" row. This function is the fix,
independent of any one SUT's refresh/dry-run/execute implementations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

__all__ = ["OneshotOutcome", "run_oneshot", "run_oneshot_unattended"]


@dataclass(frozen=True)
class OneshotOutcome:
    returncode: int
    stage: str  # "refresh" | "dryrun" | "aborted-empty-input" | "aborted-no-input" | "execute"


def run_oneshot(refresh: Callable[[], int], dryrun: Callable[[], int],
                 execute: Callable[[str], int], *,
                 prompt: Callable[[str], str] = input,
                 announce: Callable[[str], None] | None = print) -> OneshotOutcome:
    """Refresh, dry-run, prompt, execute -- in that order, in one process.

    `refresh`/`dryrun` return a process-style exit code (0 = success);
    anything else aborts before the next step and before any sentence could
    be typed. `execute(typed)` is only ever called with a non-empty,
    already-stripped string obtained from `prompt`. If `prompt` raises
    `EOFError` or `KeyboardInterrupt`, or returns an empty/whitespace-only
    string, nothing is launched: this mirrors gate_run.py:483-490 verbatim,
    including that an aborted prompt is reported distinctly from a failed
    dry run so a caller/test can tell *why* nothing launched.

    Human approval stays exactly where it belongs: `run_oneshot` never
    fabricates or infers `typed` -- it only ever forwards whatever the
    operator actually typed at `prompt` to `execute`.
    """
    if refresh() != 0:
        return OneshotOutcome(1, "refresh")
    if dryrun() != 0:
        return OneshotOutcome(1, "dryrun")
    if announce is not None:
        announce("=" * 72)
        announce("Paste the GATE-RUN sentence above, then press Enter.")
        announce("Anything else aborts. Nothing has been launched yet.")
        announce("=" * 72)
    try:
        typed = prompt("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return OneshotOutcome(1, "aborted-no-input")
    if not typed:
        return OneshotOutcome(1, "aborted-empty-input")
    return OneshotOutcome(execute(typed), "execute")


def run_oneshot_unattended(refresh: Callable[[], int], dryrun: Callable[[], int],
                            derive_sentence: Callable[[], str],
                            execute: Callable[[str], int], *,
                            announce: Callable[[str], None] | None = print) -> OneshotOutcome:
    """Refresh, dry-run, then execute with the harness-derived sentence -- no prompt.

    The operator removed the interactive approval on 2026-09-05 (TeaStore
    campaign #7 launch): the human decision is the SETUP-CAMPAIGN sentence
    and the choice to run `oneshot`; waiting on a second keyboard round trip
    only spends the 900-second preflight window. `derive_sentence` must
    return the harness's own `expected_gate_run_text` of the authorization
    on disk -- `execute` still verifies whatever it is handed byte-exactly
    against that same derivation, so this function cannot smuggle a
    sentence past `cmd_execute`; it can only hand it the one it would have
    accepted anyway. An empty derivation aborts exactly like an empty
    prompt.
    """
    if refresh() != 0:
        return OneshotOutcome(1, "refresh")
    if dryrun() != 0:
        return OneshotOutcome(1, "dryrun")
    typed = derive_sentence().strip()
    if not typed:
        return OneshotOutcome(1, "aborted-empty-input")
    if announce is not None:
        announce("== executing GATE-RUN with the harness-derived sentence (no prompt) ==")
        announce(typed)
    return OneshotOutcome(execute(typed), "execute")
