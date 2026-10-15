"""The two shims that mate Hotel's orchestrator to the shared gate driver.

`modules/hotel-reservation/execution/candidate_runtime_adapter.py` and
`candidate_transport.py` translate `obsplacement.gate_driver.contract`'s
adapter/transport surface onto `candidate_runtime.py`. That library lives in a
different worktree, so the tests here exercise the shims against the
orchestrator's own validators instead of against the library: the load-bearing
question is not "does the shim have the right method names" (the library's
`check_adapter_contract` answers that, and
`tests/test_hotel_gate_driver_config.py` in the drivers worktree asserts it)
but "does a document assembled the way the library assembles it survive
`validate_gate_plan` / `validate_gate_setup` / `validate_gate_run`".

Every remote call is unreachable in these tests: each one is refused by a
local guard before any ssh/scp is attempted, and the tests assert exactly that
refusal.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = load(
    "hotel_gate_driver_adapter_test",
    "modules/hotel-reservation/execution/candidate_runtime_adapter.py",
)
transport = load(
    "hotel_gate_driver_transport_test",
    "modules/hotel-reservation/execution/candidate_transport.py",
)
installer = load(
    "hotel_gate_driver_installer_test",
    "modules/hotel-reservation/execution/candidate_release_installer.py",
)
runtime = adapter.runtime


# The shared library's default (TeaStore-shaped) envelope literals, copied
# here only so a test can prove they are refused -- `gate_documents.py` lives
# in the drivers worktree and cannot be imported from this one.
LIBRARY_DEFAULT_ENVELOPES = {
    "GATE-PLAN": {
        "decision": "approve-exact-plan", "payload_key": "bindings",
        "flags": {"runtimeAuthorized": False, "promotionAuthorized": False},
    },
    "GATE-SETUP": {
        "decision": "authorize-exact-setup-only", "payload_key": "authorization",
        "flags": {"runtimeAuthorized": False, "promotionAuthorized": False},
    },
    "GATE-RUN": {
        "decision": "authorize-one-shot-exact-run", "payload_key": "authorization",
        "flags": {"promotionAuthorized": False},
    },
}


def bindings() -> object:
    ceiling = runtime.posture_ceiling()
    return runtime.Bindings(
        framework_commit="a" * 40,
        framework_tree="b" * 40,
        descriptor_sha256="c" * 64,
        compiled_plan_sha256="9877376014b7fcd6fb2fc8f5b25b4e3e9bcae00884e49f5437923520deb2c484",
        runtime_policy_sha256="d" * 64,
        controller_sha256={
            name: hashlib.sha256(name.encode()).hexdigest()
            for name in runtime.CONTROLLER_PATHS
        },
        run_count=24,
        unsupported_postures=tuple(runtime.unsupported_posture_ids(ceiling)),
        source_cost_comparison_state=ceiling["sourceCostComparisonState"],
    )


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_gate_document(*, kind, gate, envelope, typed_approval, approved_by,
                        approved_at, payload) -> dict:
    """Assemble a document exactly as `gate_documents.build_gate_document` does.

    Mirrors that function's body (envelope keys first, then the gate-specific
    payload filed under the envelope's `payload_key`, then the envelope's
    flags). Reproduced rather than imported because the shared library is not
    checked out in this worktree.
    """
    document = {
        "schemaVersion": 1,
        "kind": kind,
        "gate": gate,
        "decision": envelope["decision"],
        "typedApproval": typed_approval,
        "approvedBy": approved_by,
        "approvedAt": approved_at,
    }
    document[envelope["payload_key"]] = payload
    document.update(envelope["flags"])
    return document


# --------------------------------------------------------------------------
# The envelope declaration is what makes the library's documents admissible.
# --------------------------------------------------------------------------

def test_declared_gate_plan_envelope_produces_a_document_the_orchestrator_accepts():
    binding = bindings()
    document = build_gate_document(
        kind=adapter.PLAN_KIND, gate="GATE-PLAN",
        envelope=adapter.GATE_ENVELOPES["GATE-PLAN"],
        typed_approval=adapter.expected_gate_plan_text(binding),
        approved_by="Florian Huebscher", approved_at=stamp(datetime.now(timezone.utc)),
        payload=adapter.plan_binding(binding),
    )
    assert adapter.validate_gate_plan(document, binding) == runtime.canonical_sha256(document)


def test_library_default_gate_plan_envelope_is_refused():
    """Without the declaration, the library's own literals build a document
    Hotel refuses -- which is why `GATE_ENVELOPES` exists at all."""
    binding = bindings()
    document = build_gate_document(
        kind=adapter.PLAN_KIND, gate="GATE-PLAN",
        envelope=LIBRARY_DEFAULT_ENVELOPES["GATE-PLAN"],
        typed_approval=adapter.expected_gate_plan_text(binding),
        approved_by="Florian Huebscher", approved_at=stamp(datetime.now(timezone.utc)),
        payload=adapter.plan_binding(binding),
    )
    with pytest.raises(runtime.GateError):
        adapter.validate_gate_plan(document, binding)


def gate_plan_document(binding, approved_at: datetime) -> dict:
    return build_gate_document(
        kind=adapter.PLAN_KIND, gate="GATE-PLAN",
        envelope=adapter.GATE_ENVELOPES["GATE-PLAN"],
        typed_approval=adapter.expected_gate_plan_text(binding),
        approved_by="Florian Huebscher", approved_at=stamp(approved_at),
        payload=adapter.plan_binding(binding),
    )


BUNDLE = {
    "bundleSha256": "3" * 64,
    "bundleSizeBytes": 4096,
    "manifestCanonicalSha256": "4" * 64,
}


def test_declared_gate_setup_envelope_produces_a_document_the_orchestrator_accepts(tmp_path):
    binding = bindings()
    moment = datetime.now(timezone.utc)
    gate_plan = gate_plan_document(binding, moment - timedelta(seconds=30))
    setup_binding = runtime.setup_binding(
        binding, gate_plan, BUNDLE, adapter.new_setup_id(),
    )
    document = build_gate_document(
        kind=adapter.SETUP_KIND, gate="GATE-SETUP",
        envelope=adapter.GATE_ENVELOPES["GATE-SETUP"],
        typed_approval=adapter.expected_gate_setup_text(setup_binding),
        approved_by="Florian Huebscher", approved_at=stamp(moment),
        payload=setup_binding,
    )
    assert runtime.validate_gate_setup(document, binding, gate_plan) == document


def test_library_default_gate_setup_envelope_is_refused():
    binding = bindings()
    moment = datetime.now(timezone.utc)
    gate_plan = gate_plan_document(binding, moment - timedelta(seconds=30))
    setup_binding = runtime.setup_binding(
        binding, gate_plan, BUNDLE, adapter.new_setup_id(),
    )
    document = build_gate_document(
        kind=adapter.SETUP_KIND, gate="GATE-SETUP",
        envelope=LIBRARY_DEFAULT_ENVELOPES["GATE-SETUP"],
        typed_approval=adapter.expected_gate_setup_text(setup_binding),
        approved_by="Florian Huebscher", approved_at=stamp(moment),
        payload=setup_binding,
    )
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_setup(document, binding, gate_plan)


def readiness_document(moment: datetime) -> dict:
    """The three fields `_run_binding` reads off readiness, nothing more."""
    return {
        "captureId": "hotel-readiness-v1-20260830t000000z-deadbeef",
        "observedAt": stamp(moment),
        "kind": runtime.READINESS_KIND,
    }


def run_fixture(*, envelope):
    binding = bindings()
    moment = datetime.now(timezone.utc)
    gate_plan = gate_plan_document(binding, moment - timedelta(seconds=60))
    setup_binding = runtime.setup_binding(binding, gate_plan, BUNDLE, adapter.new_setup_id())
    gate_setup = build_gate_document(
        kind=adapter.SETUP_KIND, gate="GATE-SETUP",
        envelope=adapter.GATE_ENVELOPES["GATE-SETUP"],
        typed_approval=adapter.expected_gate_setup_text(setup_binding),
        approved_by="Florian Huebscher", approved_at=stamp(moment - timedelta(seconds=30)),
        payload=setup_binding,
    )
    readiness = readiness_document(moment - timedelta(seconds=10))
    deadline = stamp(moment + timedelta(seconds=18000))
    run_binding = runtime._run_binding(
        binding, gate_plan, gate_setup, readiness,
        adapter.TRANSPORT_ID, adapter.new_campaign_id(), deadline,
    )
    document = build_gate_document(
        kind=adapter.RUN_KIND, gate="GATE-RUN", envelope=envelope,
        typed_approval=adapter.expected_gate_run_text(run_binding),
        approved_by="Florian Huebscher", approved_at=stamp(moment),
        payload=run_binding,
    )
    return document, binding, gate_plan, gate_setup, readiness


def test_declared_gate_run_envelope_produces_a_document_the_orchestrator_accepts():
    document, binding, gate_plan, gate_setup, readiness = run_fixture(
        envelope=adapter.GATE_ENVELOPES["GATE-RUN"],
    )
    assert runtime.validate_gate_run(
        document, binding, gate_plan, gate_setup, readiness,
    ) == document


def test_library_default_gate_run_envelope_is_refused():
    document, binding, gate_plan, gate_setup, readiness = run_fixture(
        envelope=LIBRARY_DEFAULT_ENVELOPES["GATE-RUN"],
    )
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_run(document, binding, gate_plan, gate_setup, readiness)


# --------------------------------------------------------------------------
# Identity minting: the library's proposals cannot satisfy Hotel's regexes.
# --------------------------------------------------------------------------

def test_minted_setup_and_campaign_identities_match_the_orchestrator_regexes():
    assert runtime.SETUP_ID.fullmatch(adapter.new_setup_id())
    assert runtime.CAMPAIGN_ID.fullmatch(adapter.new_campaign_id())


def test_the_library_proposed_identities_would_not_have_matched():
    """Pins why the shim re-mints rather than forwarding."""
    assert runtime.SETUP_ID.fullmatch("0123456789abcdef0123456789abcdef") is None
    assert runtime.CAMPAIGN_ID.fullmatch(runtime.STUDY_EPOCH) is None


def test_setup_authorization_re_mints_a_non_conforming_setup_id(tmp_path, monkeypatch):
    binding = bindings()
    gate_plan = gate_plan_document(binding, datetime.now(timezone.utc))
    monkeypatch.setattr(adapter, "GATES_DIR", tmp_path)
    (tmp_path / "gate-plan.json").write_bytes(runtime.canonical_bytes(gate_plan) + b"\n")
    authorization = adapter.setup_authorization(
        binding, runtime.canonical_sha256(gate_plan), None, BUNDLE,
        setup_id="0123456789abcdef0123456789abcdef",
        execution_user=adapter.EXECUTION_USER,
        not_before="2026-09-04T00:00:00Z",
        authorization_deadline="2026-09-04T06:00:00Z",
    )
    assert runtime.SETUP_ID.fullmatch(authorization["setupId"])
    assert authorization["setupId"] != "0123456789abcdef0123456789abcdef"
    # The study label stays recoverable from the same document.
    assert authorization["studyEpoch"] == runtime.STUDY_EPOCH


def test_setup_authorization_refuses_a_digest_that_does_not_match_the_recorded_plan(
    tmp_path, monkeypatch,
):
    binding = bindings()
    gate_plan = gate_plan_document(binding, datetime.now(timezone.utc))
    monkeypatch.setattr(adapter, "GATES_DIR", tmp_path)
    (tmp_path / "gate-plan.json").write_bytes(runtime.canonical_bytes(gate_plan) + b"\n")
    with pytest.raises(runtime.GateError):
        adapter.setup_authorization(
            binding, "0" * 64, None, BUNDLE, setup_id=adapter.new_setup_id(),
            execution_user=adapter.EXECUTION_USER, not_before="2026-09-04T00:00:00Z",
            authorization_deadline="2026-09-04T06:00:00Z",
        )


def test_setup_authorization_refuses_a_foreign_execution_user(tmp_path, monkeypatch):
    binding = bindings()
    gate_plan = gate_plan_document(binding, datetime.now(timezone.utc))
    monkeypatch.setattr(adapter, "GATES_DIR", tmp_path)
    (tmp_path / "gate-plan.json").write_bytes(runtime.canonical_bytes(gate_plan) + b"\n")
    with pytest.raises(runtime.GateError):
        adapter.setup_authorization(
            binding, runtime.canonical_sha256(gate_plan), None, BUNDLE,
            setup_id=adapter.new_setup_id(), execution_user="stig",
            not_before="2026-09-04T00:00:00Z",
            authorization_deadline="2026-09-04T06:00:00Z",
        )


def run_authorization_fixture(tmp_path, monkeypatch):
    binding = bindings()
    moment = datetime.now(timezone.utc)
    gate_plan = gate_plan_document(binding, moment - timedelta(seconds=60))
    setup_binding = runtime.setup_binding(binding, gate_plan, BUNDLE, adapter.new_setup_id())
    gate_setup = build_gate_document(
        kind=adapter.SETUP_KIND, gate="GATE-SETUP",
        envelope=adapter.GATE_ENVELOPES["GATE-SETUP"],
        typed_approval=adapter.expected_gate_setup_text(setup_binding),
        approved_by="Florian Huebscher", approved_at=stamp(moment - timedelta(seconds=30)),
        payload=setup_binding,
    )
    monkeypatch.setattr(adapter, "GATES_DIR", tmp_path)
    (tmp_path / "gate-plan.json").write_bytes(runtime.canonical_bytes(gate_plan) + b"\n")
    (tmp_path / "gate-setup.json").write_bytes(runtime.canonical_bytes(gate_setup) + b"\n")
    return binding, gate_plan, readiness_document(moment - timedelta(seconds=10))


def test_run_authorization_mints_a_per_run_campaign_id_from_the_study_label(
    tmp_path, monkeypatch,
):
    binding, gate_plan, readiness = run_authorization_fixture(tmp_path, monkeypatch)
    authorization = adapter.run_authorization(
        binding, runtime.canonical_sha256(gate_plan),
        runtime.canonical_sha256(readiness), readiness=readiness,
        campaign_id=runtime.STUDY_EPOCH, not_before="2026-09-04T00:00:00Z",
        authorization_deadline="2026-09-04T05:00:00Z",
    )
    assert runtime.CAMPAIGN_ID.fullmatch(authorization["campaignId"])
    # Both identities stay recoverable from the one document.
    assert authorization["studyEpoch"] == runtime.STUDY_EPOCH
    assert authorization["deadline"] == "2026-09-04T05:00:00Z"


def test_run_authorization_refuses_a_campaign_identity_that_is_not_the_study_epoch(
    tmp_path, monkeypatch,
):
    binding, gate_plan, readiness = run_authorization_fixture(tmp_path, monkeypatch)
    with pytest.raises(runtime.GateError):
        adapter.run_authorization(
            binding, runtime.canonical_sha256(gate_plan),
            runtime.canonical_sha256(readiness), readiness=readiness,
            campaign_id="some-other-study", not_before="2026-09-04T00:00:00Z",
            authorization_deadline="2026-09-04T05:00:00Z",
        )


def test_run_authorization_refuses_a_readiness_digest_that_does_not_match(
    tmp_path, monkeypatch,
):
    binding, gate_plan, readiness = run_authorization_fixture(tmp_path, monkeypatch)
    with pytest.raises(runtime.GateError):
        adapter.run_authorization(
            binding, runtime.canonical_sha256(gate_plan), "0" * 64, readiness=readiness,
            campaign_id=runtime.STUDY_EPOCH, not_before="2026-09-04T00:00:00Z",
            authorization_deadline="2026-09-04T05:00:00Z",
        )


# --------------------------------------------------------------------------
# Digest formula ownership.
# --------------------------------------------------------------------------

def test_adapter_canonical_sha256_is_the_orchestrator_formula_for_non_ascii():
    document = {"note": "Hôtel réservation — ünicode"}
    assert adapter.canonical_sha256(document) == runtime.canonical_sha256(document)
    # The shared library's own formula (json.dumps' default ensure_ascii=True)
    # would produce a different digest for the same document; the adapter
    # re-exports Hotel's, so exactly one formula hashes a Hotel document.
    library_formula = hashlib.sha256(
        json.dumps(document, allow_nan=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert library_formula != adapter.canonical_sha256(document)


# --------------------------------------------------------------------------
# Transport shim.
# --------------------------------------------------------------------------

def release_binding() -> dict:
    setup_id = adapter.new_setup_id()
    return {
        "setupId": setup_id,
        "bundleSha256": BUNDLE["bundleSha256"],
        "bundleSizeBytes": BUNDLE["bundleSizeBytes"],
        "manifestCanonicalSha256": BUNDLE["manifestCanonicalSha256"],
        "installedEntriesSha256": "5" * 64,
        "gateSetupCanonicalSha256": "6" * 64,
    }


def test_release_binding_keys_are_the_installer_modules_only_declaration():
    binding = release_binding()
    assert set(installer.RELEASE_BINDING_KEYS) == set(binding)
    assert len(installer.RELEASE_BINDING_KEYS) == len(set(installer.RELEASE_BINDING_KEYS))


def test_capture_spec_round_trips_the_setup_identity(tmp_path):
    binding = release_binding()
    archive = tmp_path / "capture-spec.tar"
    digest = transport.build_capture_spec(bindings(), binding, archive_path=archive)
    assert digest == hashlib.sha256(archive.read_bytes()).hexdigest()
    spec = transport._read_capture_spec(archive)
    assert spec["setupId"] == binding["setupId"]


def test_capture_spec_refuses_a_release_binding_without_a_hotel_setup_identity(tmp_path):
    with pytest.raises(runtime.GateError):
        transport.build_capture_spec(
            bindings(), {"setupId": "not-a-hotel-setup-id"},
            archive_path=tmp_path / "capture-spec.tar",
        )


def test_admit_readiness_refuses_a_capture_spec_from_a_different_install(tmp_path):
    """Reaches no ssh: the identity disagreement is caught locally first."""
    archive = tmp_path / "capture-spec.tar"
    transport.build_capture_spec(bindings(), release_binding(), archive_path=archive)
    with pytest.raises(runtime.GateError):
        transport.BoundedSetupController(bindings=bindings()).admit_readiness(
            archive_path=archive, release_binding=release_binding(),
            local_output=tmp_path / "fetched-readiness",
        )


def admission_document(campaign_id: str | None = None) -> dict:
    body = {
        "schemaVersion": 1,
        "kind": runtime.ADMISSION_KIND,
        "bindings": {"campaignId": campaign_id or adapter.new_campaign_id()},
        "runtimeAuthorized": True,
        "externalMutationAuthorized": True,
        "promotionAuthorized": False,
        "issuedAt": "2026-09-04T00:00:00Z",
    }
    return {**body, "admissionCanonicalSha256": runtime.canonical_sha256(body)}


def test_build_runtime_package_carries_the_admission_verbatim():
    document = admission_document()
    package = transport.build_runtime_package(
        adapter.RuntimeAdmission(document=document, readiness={"release": {}})
    )
    assert package["admission"] == document
    assert package["campaignId"] == document["bindings"]["campaignId"]
    assert package["admissionCanonicalSha256"] == document["admissionCanonicalSha256"]
    # The campaign identity must survive the shared flow layer's safe-slug check.
    assert package["campaignId"].replace("-", "").isalnum()


def test_build_runtime_package_refuses_something_that_is_not_an_admission():
    with pytest.raises(runtime.GateError):
        transport.build_runtime_package({"not": "an admission"})


def test_remote_precheck_reports_a_package_that_does_not_carry_its_own_admission():
    document = admission_document()
    package = adapter.RuntimeAdmission(document=document, readiness={"release": {}})
    remote_input = transport.build_runtime_package(package)
    tampered = copy.deepcopy(remote_input)
    tampered["admission"]["bindings"]["campaignId"] = adapter.new_campaign_id()
    result = transport.remote_precheck(package, tampered)
    assert result["ok"] is False and "differs" in result["detail"]


def test_launch_refuses_a_package_whose_identity_does_not_match_its_admission(tmp_path):
    """Reaches no ssh: the mismatch is caught before the detached controller."""
    document = admission_document()
    package = transport.build_runtime_package(
        adapter.RuntimeAdmission(document=document, readiness={"release": {}})
    )
    package["campaignId"] = adapter.new_campaign_id()
    package_path = tmp_path / "runtime-package.json"
    package_path.write_bytes(runtime.canonical_bytes(package) + b"\n")
    with pytest.raises(runtime.GateError):
        transport.BoundedCampaignController(
            framework_commit="a" * 40, release_binding=release_binding(),
        ).launch(package_path, local_output=tmp_path / "campaign-result")


def test_launch_controller_refuses_a_release_binding_without_a_setup_identity():
    with pytest.raises(runtime.GateError):
        transport.BoundedCampaignController(
            framework_commit="a" * 40, release_binding={"setupId": "nope"},
        )


def test_probe_declares_that_it_is_not_a_remote_observation():
    proof = transport.BoundedSetupController(bindings=bindings()).probe()
    assert proof["remoteObservation"] is False
    assert proof["operationalTarget"]["target"] == runtime.TARGET["target"]
    body = {
        key: value for key, value in proof.items()
        if key != "declarationCanonicalSha256"
    }
    assert proof["declarationCanonicalSha256"] == runtime.canonical_sha256(body)


def test_the_shims_never_author_an_approval_sentence():
    for relative in (
        "modules/hotel-reservation/execution/candidate_runtime_adapter.py",
        "modules/hotel-reservation/execution/candidate_transport.py",
        "modules/hotel-reservation/execution/candidate_release_installer.py",
    ):
        text = (ROOT / relative).read_text()
        assert 'f"APPROVE' not in text and "f'APPROVE" not in text


def test_both_shims_share_one_loaded_orchestrator_module():
    """One `candidate_runtime.py` object per process, not three."""
    assert transport.runtime is adapter.runtime
