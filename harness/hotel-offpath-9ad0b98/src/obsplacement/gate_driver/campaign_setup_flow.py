"""SETUP-CAMPAIGN flow: propose -> authorize -> auto -> status.

Generalizes campaign_setup.py's four subcommands (campaign_setup.py:160-413)
against `contract.SutConfig` + `campaign_authorization.py` +
`fs_guards.SingleFlightLock`. GATE-RUN is deliberately not reachable from
anything here -- see campaign_authorization.py's module docstring.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from .audit_log import append_audit
from .campaign_authorization import (
    build_campaign_record,
    build_pending_document,
    invariants_for,
    verify_live_invariants,
)
from .contract import SutConfig
from .errors import GateDriverError, NoLiveCampaign
from .freshness import deadline_after, now, parse, stamp
from .fs_guards import SingleFlightLock
from .gate_setup_flow import _recorded_setup_id
from .gate_documents import build_gate_document, gate_envelope
from .gate_paths import GatePaths
from .hashing import canonical_sha256
from .json_io import read_json, write_json
from .module_loader import load_binding_keys
from .traced_runner import traced_runner

__all__ = [
    "cmd_propose",
    "cmd_authorize",
    "require_live_campaign_from_disk",
    "cmd_auto",
    "StatusReport",
    "cmd_status",
]


def cmd_propose(config: SutConfig, adapter, paths: GatePaths, *,
                 framework_commit: str) -> dict:
    """Emit the SETUP-CAMPAIGN sentence to type. Reproduces campaign_setup.py:160-180."""
    bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
    pending = build_pending_document(config, bindings, framework_commit=framework_commit)
    write_json(paths.setup_campaign_pending, pending)
    return pending


def cmd_authorize(config: SutConfig, paths: GatePaths, *, typed: str) -> dict:
    """Record a live SETUP-CAMPAIGN authorization. Reproduces campaign_setup.py:183-216.

    Recomputes the deadline from `pending["proposedAt"]` (recorded by
    `cmd_propose`/`build_pending_document` at proposal time, never trusted
    bare) and `config.setup_campaign_window_hours`, and refuses to authorize
    if `pending["deadline"]` does not match -- an operator with filesystem
    access between propose and authorize could otherwise edit both
    `pending["deadline"]` and `pending["expectedText"]` consistently and have
    `verify_typed_sentence` alone never notice the forged deadline.
    """
    if not paths.setup_campaign_pending.is_file():
        raise NoLiveCampaign("nothing proposed; run propose-campaign first")
    pending = read_json(paths.setup_campaign_pending)
    expected_deadline = deadline_after(
        config.setup_campaign_window_hours, at=parse(pending["proposedAt"]),
    )
    if pending["deadline"] != expected_deadline:
        raise GateDriverError(
            "SETUP-CAMPAIGN deadline does not match the configured window: "
            f"pending={pending['deadline']!r} expected={expected_deadline!r}"
        )
    record = build_campaign_record(pending, typed, approved_by=config.approved_by)
    write_json(paths.setup_campaign_authorization, record)
    paths.setup_campaign_pending.unlink()
    append_audit(paths.setup_campaign_audit, event="campaign-authorized",
                 authorizationSha256=canonical_sha256(record), deadline=record["deadline"])
    return record


def require_live_campaign_from_disk(config: SutConfig, adapter, paths: GatePaths, *,
                                     framework_commit: str, at=None) -> dict:
    """Fail closed unless a live, undrifted SETUP-CAMPAIGN authorization is recorded.

    Reproduces campaign_setup.py's `require_campaign()` (campaign_setup.py:
    133-157): `NoLiveCampaign` if nothing was ever authorized,
    `errors.CampaignDrift` if campaign identity moved, `errors.
    CampaignExpired` if the deadline passed.
    """
    if not paths.setup_campaign_authorization.is_file():
        raise NoLiveCampaign(
            "no SETUP-CAMPAIGN authorization recorded; run 'propose-campaign', "
            "then have the operator type the sentence"
        )
    record = read_json(paths.setup_campaign_authorization)
    bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
    verify_live_invariants(record, config, bindings, at=at)
    return record


def cmd_auto(config: SutConfig, adapter, transport, paths: GatePaths, *,
             framework_commit: str, trace_dir: Path) -> dict:
    """Prepare + install + readiness, no typing, under a live SETUP-CAMPAIGN authorization.

    Reproduces campaign_setup.py's `cmd_auto` / `_cmd_auto_locked`
    (campaign_setup.py:256-397). The whole body runs inside
    `fs_guards.SingleFlightLock(paths.auto_lock)` -- see that class's
    docstring for the 2026-09-01 overlapping-run incident this prevents.
    Live setup documents are archived (not deleted) before being
    regenerated, via `GatePaths.archive_previous_setup`.
    """
    with SingleFlightLock(paths.auto_lock):
        record = require_live_campaign_from_disk(
            config, adapter, paths, framework_commit=framework_commit,
        )
        append_audit(paths.setup_campaign_audit, event="auto-begin",
                     frameworkCommit=framework_commit)
        paths.archive_previous_setup(commit=framework_commit)

        bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
        proof = transport.BoundedSetupController(bindings=bindings).probe()
        write_json(paths.target_proof, proof)

        for path in (paths.release_bundle, paths.release_manifest):
            if path.exists() or path.is_symlink():
                path.unlink()
        transport.build_release_bundle(
            bindings, bundle_path=paths.release_bundle, manifest_path=paths.release_manifest,
        )

        plan_envelope = gate_envelope(adapter, "GATE-PLAN")
        gate_plan = build_gate_document(
            kind=adapter.PLAN_KIND, gate="GATE-PLAN", decision=plan_envelope.decision,
            typed_approval=adapter.expected_gate_plan_text(bindings),
            approved_by=config.approved_by, approved_at=stamp(now()),
            payload={plan_envelope.payload_key: adapter.plan_binding(bindings)},
            flags=plan_envelope.flags,
        )
        gate_plan_sha256 = adapter.validate_gate_plan(dict(gate_plan), bindings)
        write_json(paths.gate_plan, gate_plan)

        setup_id_moment = now()
        setup_id = secrets.token_hex(16)
        authorization = adapter.setup_authorization(
            bindings, gate_plan_sha256, proof,
            read_json(paths.release_manifest),
            setup_id=setup_id, execution_user=config.execution_user,
            not_before=stamp(setup_id_moment),
            authorization_deadline=deadline_after(config.setup_window_hours, at=setup_id_moment),
        )
        write_json(paths.setup_authorization, authorization)
        # See gate_setup_flow._recorded_setup_id: the audit trail records the
        # id the authorization carries, never the one this flow proposed.
        setup_id = _recorded_setup_id(authorization, setup_id)

        setup_envelope = gate_envelope(adapter, "GATE-SETUP")
        gate_setup = build_gate_document(
            kind=adapter.SETUP_KIND, gate="GATE-SETUP", decision=setup_envelope.decision,
            typed_approval=adapter.expected_gate_setup_text(authorization),
            approved_by=config.approved_by, approved_at=stamp(now()),
            payload={setup_envelope.payload_key: authorization},
            flags=setup_envelope.flags,
        )
        write_json(paths.gate_setup, gate_setup)
        append_audit(paths.setup_campaign_audit, event="setup-derived",
                     setupId=setup_id, gatePlanSha256=gate_plan_sha256,
                     frameworkCommit=framework_commit)

        install_runner = traced_runner(
            transport.subprocess_runner, trace_dir / "auto-install-trace.log",
        )
        install_controller = transport.BoundedSetupController(
            bindings=bindings, runner=install_runner,
        )
        receipt = install_controller.setup(
            gate_plan_path=paths.gate_plan, target_proof_path=paths.target_proof,
            release_manifest_path=paths.release_manifest, gate_setup_path=paths.gate_setup,
            bundle_path=paths.release_bundle,
        )
        write_json(paths.install_receipt, receipt)
        append_audit(paths.setup_campaign_audit, event="installed", setupId=setup_id,
                     imageBuildReceiptSha256=receipt.get("imageBuildReceiptSha256"))

        binding_keys = sorted(load_binding_keys(config.root, config.installer_module))
        release_binding = {key: receipt[key] for key in binding_keys}
        if paths.capture_spec.exists() or paths.capture_spec.is_symlink():
            paths.capture_spec.unlink()
        transport.build_capture_spec(bindings, release_binding, archive_path=paths.capture_spec)

        readiness_runner = traced_runner(
            transport.subprocess_runner, trace_dir / "auto-readiness-trace.log",
        )
        readiness_controller = transport.BoundedSetupController(
            bindings=bindings, runner=readiness_runner,
        )
        admission = readiness_controller.admit_readiness(
            archive_path=paths.capture_spec, release_binding=release_binding,
            local_output=paths.fetched_readiness,
        )
        write_json(paths.readiness_admission, admission)
        append_audit(paths.setup_campaign_audit, event="readiness-admitted",
                     setupId=setup_id,
                     readinessCanonicalSha256=admission.get("readinessCanonicalSha256"))
        return admission


@dataclass(frozen=True)
class StatusReport:
    has_campaign: bool
    approved_at: str | None = None
    deadline: str | None = None
    live: bool | None = None
    invariants_match: bool | None = None


def cmd_status(config: SutConfig, adapter, paths: GatePaths, *,
                framework_commit: str, at=None) -> StatusReport:
    """Reproduces campaign_setup.py's `cmd_status` (campaign_setup.py:400-413)."""
    if not paths.setup_campaign_authorization.is_file():
        return StatusReport(has_campaign=False)
    record = read_json(paths.setup_campaign_authorization)
    moment = at if at is not None else now()
    live = moment < parse(record["deadline"])
    bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
    invariants_match = record.get("invariants") == invariants_for(config, bindings)
    return StatusReport(
        has_campaign=True, approved_at=record["approvedAt"], deadline=record["deadline"],
        live=live, invariants_match=invariants_match,
    )
