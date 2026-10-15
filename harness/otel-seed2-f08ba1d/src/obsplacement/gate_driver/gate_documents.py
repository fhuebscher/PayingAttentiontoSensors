"""The GATE-PLAN / GATE-SETUP / GATE-RUN document envelope, factored out once.

All three documents share the same envelope shape across the canonical
drivers (gate_setup.py:110-121 GATE-PLAN, :159-170 GATE-SETUP; gate_run.py:
155-165 GATE-RUN): `schemaVersion`, `kind` (SUT-owned), `gate` (the fixed
governance-gate name), `decision` (a fixed literal per gate -- the decision
label describes the *governance action*, not anything SUT-specific, so it is
universal), `typedApproval` (always the verified `expected` string, never the
raw `typed` one -- see sentence.verify_typed_sentence), `approvedBy`,
`approvedAt`, then gate-specific payload plus the `runtimeAuthorized` /
`promotionAuthorized` flags that keep each gate's authority scoped to
exactly what it approved.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import ContractViolation

__all__ = [
    "DECISION_GATE_PLAN",
    "DECISION_GATE_SETUP",
    "DECISION_GATE_RUN",
    "DRY_RUN_APPROVER_MARKER",
    "GateEnvelope",
    "gate_envelope",
    "build_gate_document",
]

DECISION_GATE_PLAN = "approve-exact-plan"
DECISION_GATE_SETUP = "authorize-exact-setup-only"
DECISION_GATE_RUN = "authorize-one-shot-exact-run"

# gate_run.py:237 -- the dry-run probe document is written to scratch, never
# to the gates directory, and is unmistakably not a human approval even if
# someone finds it on disk later.
DRY_RUN_APPROVER_MARKER = "DRY-RUN PLUMBING PROBE - NOT A HUMAN APPROVAL"


def build_gate_document(*, kind: str, gate: str, decision: str,
                         typed_approval: str, approved_by: str, approved_at: str,
                         payload: dict, flags: dict, schema_version: int = 1) -> dict:
    """Assemble a gate document envelope.

    `payload` is the gate-specific body (`{"bindings": ...}` for GATE-PLAN,
    `{"authorization": ...}` for GATE-SETUP/GATE-RUN). `flags` carries the
    scoping booleans (`runtimeAuthorized`, `promotionAuthorized`, ...) --
    passed explicitly rather than defaulted, so a caller cannot forget to
    scope a new gate down and accidentally widen its authority.
    """
    document = {
        "schemaVersion": schema_version,
        "kind": kind,
        "gate": gate,
        "decision": decision,
        "typedApproval": typed_approval,
        "approvedBy": approved_by,
        "approvedAt": approved_at,
    }
    document.update(payload)
    document.update(flags)
    return document


@dataclass(frozen=True)
class GateEnvelope:
    """The three envelope literals a SUT owns for one gate.

    `decision` is the fixed decision label, `payload_key` the single key the
    gate-specific body is filed under, and `flags` the authority-scoping
    booleans. The canonical (TeaStore-shaped) values are the defaults below;
    a SUT whose own validators demand different literals declares them --
    Hotel's `validate_gate_setup` requires `decision ==
    "authorize-exact-one-shot-setup"`, files its body under `"bindings"`, and
    demands four flags (`setupAuthorized`/`externalMutationAuthorized` as well
    as `runtimeAuthorized`/`promotionAuthorized`), so a library that hardcoded
    TeaStore's three literals could not build a document Hotel would accept.
    """

    decision: str
    payload_key: str
    flags: dict


DEFAULT_GATE_ENVELOPES = {
    "GATE-PLAN": GateEnvelope(
        decision=DECISION_GATE_PLAN, payload_key="bindings",
        flags={"runtimeAuthorized": False, "promotionAuthorized": False},
    ),
    "GATE-SETUP": GateEnvelope(
        decision=DECISION_GATE_SETUP, payload_key="authorization",
        flags={"runtimeAuthorized": False, "promotionAuthorized": False},
    ),
    "GATE-RUN": GateEnvelope(
        decision=DECISION_GATE_RUN, payload_key="authorization",
        flags={"promotionAuthorized": False},
    ),
}


def gate_envelope(adapter, gate: str) -> GateEnvelope:
    """The envelope literals for `gate`, SUT-declared if the adapter declares any.

    An adapter opts in by exposing `GATE_ENVELOPES`, a mapping from gate name
    to a `GateEnvelope` (or to a mapping with the same three keys). An adapter
    that exposes nothing gets the canonical defaults, so no existing SUT
    changes behaviour. An adapter that exposes a *malformed* or *incomplete*
    `GATE_ENVELOPES` fails closed with `ContractViolation` rather than
    silently falling back to a default that its own validators would then
    reject -- a half-declared envelope is a contract defect, not a shorthand.
    """
    default = DEFAULT_GATE_ENVELOPES[gate]
    declared = getattr(adapter, "GATE_ENVELOPES", None)
    if declared is None:
        return default
    try:
        override = declared[gate]
    except (TypeError, KeyError, IndexError) as exc:
        raise ContractViolation(
            getattr(adapter, "__name__", "adapter module"), (f"GATE_ENVELOPES[{gate!r}]",),
        ) from exc
    if isinstance(override, GateEnvelope):
        decision, payload_key, flags = override.decision, override.payload_key, override.flags
    else:
        try:
            decision = override["decision"]
            payload_key = override["payload_key"]
            flags = override["flags"]
        except (TypeError, KeyError) as exc:
            raise ContractViolation(
                getattr(adapter, "__name__", "adapter module"),
                (f"GATE_ENVELOPES[{gate!r}].decision/.payload_key/.flags",),
            ) from exc
    if (
        not isinstance(decision, str) or not decision
        or not isinstance(payload_key, str) or not payload_key
        or not isinstance(flags, dict) or not flags
        or any(not isinstance(key, str) for key in flags)
        or any(not isinstance(value, bool) for value in flags.values())
    ):
        raise ContractViolation(
            getattr(adapter, "__name__", "adapter module"),
            (f"GATE_ENVELOPES[{gate!r}] is not a (str, str, dict[str, bool]) envelope",),
        )
    return GateEnvelope(decision=decision, payload_key=payload_key, flags=dict(flags))
