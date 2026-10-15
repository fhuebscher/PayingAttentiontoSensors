"""The gate-document envelope, and the SUT-owned literals inside it.

`build_gate_document` was written against TeaStore's envelope: three decision
literals, `bindings`/`authorization` as the payload key, and two or three
authority flags. Hotel's own validators demand a different decision literal
for GATE-SETUP and GATE-RUN, file every gate's body under `bindings`, and
compare `set(document)` against an exact key set that includes
`setupAuthorized` and `externalMutationAuthorized`. `gate_envelope` is what
lets one library assemble documents both SUTs' validators accept; these tests
pin that an adapter which declares nothing keeps TeaStore's shape exactly, and
that a half-declared override fails closed instead of falling back.
"""
import pytest

from obsplacement.gate_driver.errors import ContractViolation
from obsplacement.gate_driver.gate_documents import (
    DECISION_GATE_PLAN,
    DECISION_GATE_RUN,
    DECISION_GATE_SETUP,
    GateEnvelope,
    build_gate_document,
    gate_envelope,
)


class BareAdapter:
    """An adapter that declares no envelope at all -- e.g. TeaStore's."""


class DeclaringAdapter:
    GATE_ENVELOPES = {
        "GATE-PLAN": {
            "decision": "approve-exact-plan", "payload_key": "bindings",
            "flags": {"runtimeAuthorized": False, "setupAuthorized": False,
                      "externalMutationAuthorized": False, "promotionAuthorized": False},
        },
        "GATE-SETUP": GateEnvelope(
            decision="authorize-exact-one-shot-setup", payload_key="bindings",
            flags={"setupAuthorized": True, "externalMutationAuthorized": True,
                   "runtimeAuthorized": False, "promotionAuthorized": False},
        ),
        "GATE-RUN": {
            "decision": "authorize-exact-run", "payload_key": "bindings",
            "flags": {"runtimeAuthorized": True, "externalMutationAuthorized": True,
                      "promotionAuthorized": False},
        },
    }


@pytest.mark.parametrize("gate,decision,payload_key", [
    ("GATE-PLAN", DECISION_GATE_PLAN, "bindings"),
    ("GATE-SETUP", DECISION_GATE_SETUP, "authorization"),
    ("GATE-RUN", DECISION_GATE_RUN, "authorization"),
])
def test_an_adapter_that_declares_nothing_gets_the_canonical_envelope(
    gate, decision, payload_key,
):
    envelope = gate_envelope(BareAdapter(), gate)
    assert envelope.decision == decision
    assert envelope.payload_key == payload_key
    assert envelope.flags["promotionAuthorized"] is False


def test_a_declared_envelope_replaces_every_literal():
    envelope = gate_envelope(DeclaringAdapter(), "GATE-SETUP")
    assert envelope.decision == "authorize-exact-one-shot-setup"
    assert envelope.payload_key == "bindings"
    assert envelope.flags == {
        "setupAuthorized": True, "externalMutationAuthorized": True,
        "runtimeAuthorized": False, "promotionAuthorized": False,
    }


def test_a_declared_envelope_is_accepted_as_a_mapping_or_as_a_GateEnvelope():
    assert gate_envelope(DeclaringAdapter(), "GATE-PLAN").payload_key == "bindings"
    assert gate_envelope(DeclaringAdapter(), "GATE-RUN").decision == "authorize-exact-run"


def test_the_returned_flags_are_a_copy_a_caller_cannot_mutate_into_the_declaration():
    envelope = gate_envelope(DeclaringAdapter(), "GATE-RUN")
    envelope.flags["promotionAuthorized"] = True
    assert DeclaringAdapter.GATE_ENVELOPES["GATE-RUN"]["flags"]["promotionAuthorized"] is False


class HalfDeclaringAdapter:
    __name__ = "half_declaring_adapter"
    GATE_ENVELOPES = {"GATE-PLAN": {"decision": "approve-exact-plan",
                                     "payload_key": "bindings",
                                     "flags": {"promotionAuthorized": False}}}


def test_a_declaration_missing_a_gate_fails_closed_rather_than_defaulting():
    """Half a declaration is a contract defect: falling back to a default the
    SUT's own validator would then reject is the failure this prevents."""
    with pytest.raises(ContractViolation) as excinfo:
        gate_envelope(HalfDeclaringAdapter(), "GATE-SETUP")
    assert "GATE_ENVELOPES['GATE-SETUP']" in excinfo.value.missing[0]


@pytest.mark.parametrize("override", [
    {"payload_key": "bindings", "flags": {"promotionAuthorized": False}},
    {"decision": "", "payload_key": "bindings", "flags": {"promotionAuthorized": False}},
    {"decision": "d", "payload_key": "", "flags": {"promotionAuthorized": False}},
    {"decision": "d", "payload_key": "bindings", "flags": {}},
    {"decision": "d", "payload_key": "bindings", "flags": {"promotionAuthorized": "false"}},
    {"decision": "d", "payload_key": "bindings", "flags": ["promotionAuthorized"]},
    "not-an-envelope",
])
def test_a_malformed_declaration_fails_closed(override):
    class Malformed:
        __name__ = "malformed_adapter"
        GATE_ENVELOPES = {"GATE-RUN": override}

    with pytest.raises(ContractViolation):
        gate_envelope(Malformed(), "GATE-RUN")


def test_build_gate_document_files_the_payload_under_the_declared_key():
    envelope = gate_envelope(DeclaringAdapter(), "GATE-RUN")
    document = build_gate_document(
        kind="hotel-candidate-gate-run-v1", gate="GATE-RUN",
        decision=envelope.decision, typed_approval="APPROVE GATE-RUN ...",
        approved_by="Florian Huebscher", approved_at="2026-09-04T00:00:00Z",
        payload={envelope.payload_key: {"campaignId": "hotel-v1-x"}},
        flags=envelope.flags,
    )
    assert set(document) == {
        "schemaVersion", "kind", "gate", "decision", "typedApproval",
        "approvedBy", "approvedAt", "bindings", "runtimeAuthorized",
        "externalMutationAuthorized", "promotionAuthorized",
    }
    assert document["decision"] == "authorize-exact-run"
    assert document["promotionAuthorized"] is False
