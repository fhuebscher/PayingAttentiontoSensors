"""Byte-exact typed-sentence verification -- the single most load-bearing seam.

Non-negotiable property #1 (see task/handover docs): the agent never authors a
typed authorization sentence. A driver may *derive* the sentence the operator
is expected to type (that derivation lives in the SUT's adapter module, e.g.
`expected_gate_plan_text(bindings)`), and it may *verify* a supplied string
against that derivation, but it must never construct, "fix up", fuzzy-match,
or fall back to an approximation of it. This module is the only place that
comparison happens, so every driver goes through the same fail-closed check.

Every one of the four canonical scripts in scratchpad/gate-drivers/ implements
this same six-line pattern by hand:

    if typed.strip() != expected:
        print("FATAL: typed ... sentence does not match harness derivation")
        print(f"  expected: {expected}")
        print(f"  typed   : {typed.strip()}")
        return 2
    print("typed ... sentence matches harness derivation exactly")

(gate_setup.py:102-107 cmd_record_plan, gate_setup.py:152-157 cmd_install,
gate_run.py:148-153 cmd_execute, campaign_setup.py:188-192 cmd_authorize).
`verify_typed_sentence` is that pattern, once.
"""
from __future__ import annotations

from .errors import SentenceMismatch

__all__ = ["verify_typed_sentence", "SentenceMismatch"]


def verify_typed_sentence(typed: str, expected: str) -> str:
    """Fail closed unless `typed` matches `expected` byte-for-byte.

    Only the surrounding whitespace a terminal/editor tends to add (leading
    and trailing) is stripped before comparison -- matching every canonical
    driver's `typed.strip() != expected` check. Internal whitespace,
    capitalization, and punctuation are never normalized: an approver who
    fat-fingers the sentence must be told, not silently corrected.

    Returns `expected` (never `typed`) on success, so the caller stores the
    canonical derivation as the recorded `typedApproval`, exactly as every
    canonical driver does. Raises `SentenceMismatch(expected, typed_stripped)`
    on any divergence -- the caller decides how to surface that (the
    canonical drivers print both strings and exit 2).
    """
    candidate = typed.strip()
    if candidate != expected:
        raise SentenceMismatch(expected, candidate)
    return expected
