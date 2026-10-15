"""GATE-SETUP flow: prepare -> record-plan -> install -> readiness.

Generalizes gate_setup.py's four subcommands (gate_setup.py:63-271) against
`contract.SutConfig` + the loaded adapter/transport modules. Unlike the
canonical script, these functions never print and never call
`sys.exit`/`SystemExit`: they return structured results or raise one of
`errors.GateDriverError`'s subclasses, so a thin per-SUT CLI (or a test) can
decide how to present a failure. All disk paths come from a `gate_paths.
GatePaths` built from `config.gates_dir`.

Overwrite policy (non-negotiable property #5): documents that record "this
exact typed sentence was matched" (gate-plan.json, setup-authorization.json)
are written with `json_io.write_new_json` -- fail closed against a silent
second record under a different sentence/setup-id. Documents that are
natural, idempotent outputs of a mutation an operator may legitimately retry
(install-receipt.json, target-proof.json, the release bundle/manifest,
readiness-admission.json) stay overwritable via `json_io.write_json`, exactly
as the canonical script leaves them. `fetched-readiness/` is guarded by
`fs_guards.refuse_existing` before capture, exactly reproducing
gate_setup.py's cmd_readiness guard (gate_setup.py:261-262).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from .contract import SutConfig
from .freshness import deadline_after, now, stamp
from .fs_guards import SingleFlightLock, refuse_existing
from .gate_documents import build_gate_document, gate_envelope
from .gate_paths import GatePaths
from .json_io import read_json, write_json, write_new_json
from .sentence import verify_typed_sentence
from .traced_runner import traced_runner

__all__ = [
    "PrepareResult",
    "RecordPlanResult",
    "cmd_prepare",
    "cmd_record_plan",
    "cmd_install",
    "cmd_readiness",
]


def _recorded_setup_id(authorization, proposed: str) -> str:
    """The setup id the authorization document itself carries, if it carries one.

    Falls back to `proposed` only when the adapter's authorization has no
    `setupId` at all -- never when it has a different one.
    """
    if isinstance(authorization, dict):
        recorded = authorization.get("setupId")
        if isinstance(recorded, str) and recorded:
            return recorded
    return proposed


@dataclass(frozen=True)
class PrepareResult:
    bindings: object
    target_proof: dict
    release_manifest: dict
    gate_plan_sentence: str


def cmd_prepare(config: SutConfig, adapter, transport, paths: GatePaths, *,
                 framework_commit: str) -> PrepareResult:
    """Local + read-only remote work; returns the GATE-PLAN sentence to type.

    Reproduces gate_setup.py:63-95. The release bundle/manifest are rebuilt
    unconditionally on every `prepare` (deleting any prior copy first) --
    this is deliberately *not* fail-closed, since nothing has been approved
    yet and re-running `prepare` before a sentence exists must stay
    idempotent.
    """
    bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
    proof = transport.BoundedSetupController(bindings=bindings).probe()
    write_json(paths.target_proof, proof)

    for path in (paths.release_bundle, paths.release_manifest):
        if path.exists() or path.is_symlink():
            path.unlink()
    manifest = transport.build_release_bundle(
        bindings, bundle_path=paths.release_bundle, manifest_path=paths.release_manifest,
    )
    return PrepareResult(
        bindings=bindings, target_proof=proof, release_manifest=manifest,
        gate_plan_sentence=adapter.expected_gate_plan_text(bindings),
    )


@dataclass(frozen=True)
class RecordPlanResult:
    gate_plan_sha256: str
    setup_id: str
    gate_setup_sentence: str


def cmd_record_plan(config: SutConfig, adapter, paths: GatePaths, *,
                     framework_commit: str, typed: str) -> RecordPlanResult:
    """Verify the typed GATE-PLAN sentence, record it, derive GATE-SETUP.

    Reproduces gate_setup.py:98-144. Raises `sentence.SentenceMismatch` on
    any divergence -- see that module's docstring; the caller decides how to
    report it (the canonical driver exits 2).
    """
    bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
    expected = verify_typed_sentence(typed, adapter.expected_gate_plan_text(bindings))

    envelope = gate_envelope(adapter, "GATE-PLAN")
    gate_plan = build_gate_document(
        kind=adapter.PLAN_KIND, gate="GATE-PLAN", decision=envelope.decision,
        typed_approval=expected, approved_by=config.approved_by,
        approved_at=stamp(now()),
        payload={envelope.payload_key: adapter.plan_binding(bindings)},
        flags=envelope.flags,
    )
    gate_plan_sha256 = adapter.validate_gate_plan(dict(gate_plan), bindings)
    write_new_json(paths.gate_plan, gate_plan)

    proof = read_json(paths.target_proof)
    manifest = read_json(paths.release_manifest)
    setup_id = secrets.token_hex(16)
    moment = now()
    authorization = adapter.setup_authorization(
        bindings, gate_plan_sha256, proof, manifest,
        setup_id=setup_id, execution_user=config.execution_user,
        not_before=stamp(moment),
        authorization_deadline=deadline_after(config.setup_window_hours, at=moment),
    )
    write_new_json(paths.setup_authorization, authorization)
    # Record the setup id the authorization actually carries, not the one this
    # function proposed. A SUT whose own validator constrains the shape of a
    # setup id (Hotel's `SETUP_ID` regex refuses a bare `token_hex(16)`) mints
    # a conforming one inside `setup_authorization`; reporting the proposed id
    # afterwards would print an identifier that appears in no document and in
    # no typed sentence.
    setup_id = _recorded_setup_id(authorization, setup_id)

    return RecordPlanResult(
        gate_plan_sha256=gate_plan_sha256, setup_id=setup_id,
        gate_setup_sentence=adapter.expected_gate_setup_text(authorization),
    )


def cmd_install(config: SutConfig, adapter, transport, paths: GatePaths, *,
                 framework_commit: str, typed: str, trace_path: Path) -> dict:
    """Verify the typed GATE-SETUP sentence, then MUTATE the target.

    Reproduces gate_setup.py:147-206. Runs under `paths.auto_lock` -- the
    same lock `campaign_setup_flow.cmd_auto` holds for its own install step
    -- so a manual `cmd_install` cannot interleave with an overlapping
    `cmd_auto` and corrupt the same install-receipt.json/gate-setup.json.
    """
    with SingleFlightLock(paths.auto_lock):
        bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
        # Re-validate (not just re-hash) the recorded gate-plan.json before
        # trusting it: a corrupted-but-well-formed file must not silently
        # pass here just because nothing has re-checked its shape since
        # cmd_record_plan wrote it.
        adapter.validate_gate_plan(dict(read_json(paths.gate_plan)), bindings)
        authorization = read_json(paths.setup_authorization)
        expected = verify_typed_sentence(typed, adapter.expected_gate_setup_text(authorization))

        envelope = gate_envelope(adapter, "GATE-SETUP")
        gate_setup = build_gate_document(
            kind=adapter.SETUP_KIND, gate="GATE-SETUP", decision=envelope.decision,
            typed_approval=expected, approved_by=config.approved_by,
            approved_at=stamp(now()), payload={envelope.payload_key: authorization},
            flags=envelope.flags,
        )
        write_new_json(paths.gate_setup, gate_setup)

        runner = traced_runner(transport.subprocess_runner, trace_path)
        controller = transport.BoundedSetupController(bindings=bindings, runner=runner)
        receipt = controller.setup(
            gate_plan_path=paths.gate_plan, target_proof_path=paths.target_proof,
            release_manifest_path=paths.release_manifest, gate_setup_path=paths.gate_setup,
            bundle_path=paths.release_bundle,
        )
        write_json(paths.install_receipt, receipt)
        return receipt


def cmd_readiness(config: SutConfig, adapter, transport, paths: GatePaths, *,
                   framework_commit: str, binding_keys, trace_path: Path) -> dict:
    """Collect target-generated readiness under the existing GATE-SETUP.

    Reproduces gate_setup.py:209-271. `binding_keys` must come from
    `module_loader.load_binding_keys` -- never a hardcoded list (property #2).
    Runs under `paths.auto_lock`, same as `cmd_install` and `cmd_auto`.
    """
    with SingleFlightLock(paths.auto_lock):
        bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
        adapter.validate_gate_plan(dict(read_json(paths.gate_plan)), bindings)
        receipt = read_json(paths.install_receipt)
        release_binding = {key: receipt[key] for key in binding_keys}

        if paths.capture_spec.exists() or paths.capture_spec.is_symlink():
            paths.capture_spec.unlink()
        transport.build_capture_spec(bindings, release_binding, archive_path=paths.capture_spec)

        runner = traced_runner(transport.subprocess_runner, trace_path)
        controller = transport.BoundedSetupController(bindings=bindings, runner=runner)

        refuse_existing(paths.fetched_readiness)
        admission = controller.admit_readiness(
            archive_path=paths.capture_spec, release_binding=release_binding,
            local_output=paths.fetched_readiness,
        )
        write_json(paths.readiness_admission, admission)
        return admission
