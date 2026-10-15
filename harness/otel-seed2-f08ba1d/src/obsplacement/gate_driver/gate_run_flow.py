"""GATE-RUN flow: derive -> dry-run -> execute, plus the oneshot wiring point.

Generalizes gate_run.py's subcommands (gate_run.py:74-462) against
`contract.SutConfig` + the loaded adapter/transport modules.

Two remote-touching concerns in the canonical `cmd_dryrun` are deliberately
NOT reproduced here as generic string templates: the inlined remote Python
snippet that imports the installed `candidate_release_installer.py` and
calls its private `_installed_release_binding` / `_installed_readiness_binding`
/ `runtime_preflight` (gate_run.py:311-332), and the raw `ssh`/`scp`
plumbing around it (gate_run.py:286-393). Those are genuinely
installer-internal mechanics, not a stable cross-SUT interface -- what *is*
universal is that a dry run must replay them before any sentence is derived,
so the contract exposes that as three named points a SUT's transport module
implements however it needs to: `remote_output_exists`, `remote_precheck`,
`remote_status`. `run_dry_run` below is the generic orchestration around
those three calls (build the probe package locally, never touch anything
remote through them, refuse to proceed on any failure).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .contract import SutConfig
from .errors import GateDriverError, MissingDerivationReceipt, RunAuthorizationDrift
from .freshness import deadline_after, now, require_fresh, stamp
from .fs_guards import SingleFlightLock
from .gate_documents import DRY_RUN_APPROVER_MARKER, build_gate_document, gate_envelope
from .gate_paths import GatePaths
from .json_io import read_json, write_json, write_new_json
from .sentence import verify_typed_sentence
from .traced_runner import traced_runner

__all__ = [
    "RefreshFailed",
    "RunAuthorizationDerivation",
    "derive_run_authorization",
    "cmd_refresh",
    "DryRunResult",
    "run_dry_run",
    "cmd_execute",
]

# gate_run.py's dry-run check that a derived campaignId is a safe slug
# (gate_run.py:284), generalized.
_SAFE_CAMPAIGN_SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class RefreshFailed(GateDriverError):
    """The injected readiness-refresh step failed, or left required files missing."""


@dataclass(frozen=True)
class RunAuthorizationDerivation:
    bindings: object
    readiness: dict
    readiness_sha256: str
    authorization: dict
    sentence: str


def derive_run_authorization(config: SutConfig, adapter, paths: GatePaths, *,
                              framework_commit: str) -> RunAuthorizationDerivation:
    """Build the run authorization from readiness already fetched on this host.

    Reproduces gate_run.py's `derive()` (gate_run.py:74-90). Writes
    run-authorization.json unconditionally (`write_json`, not
    `write_new_json`): this document is meant to be regenerated on every
    refresh, right up until a typed GATE-RUN sentence is verified against it
    in `cmd_execute` -- refusing to overwrite it here would break the
    refresh-immediately-before-typing discipline that keeps the preflight
    fresh (non-negotiable property #3).

    Also writes `run-authorization-receipt.json`: a library-owned record of
    what this derivation was validated against (never a key stuffed into the
    adapter-owned `authorization` document itself -- some SUTs' own
    validators recompute and byte-compare that document, see
    `GatePaths.run_authorization_receipt`'s docstring). `cmd_execute` re-reads
    this receipt to catch a substituted gate-plan.json or a stale preflight
    between derivation and execution.

    Runs under `paths.run_lock` (`fs_guards.SingleFlightLock`), separate from
    `paths.auto_lock`, so overlapping derivations cannot interleave writes to
    run-authorization.json/its receipt.
    """
    with SingleFlightLock(paths.run_lock):
        readiness = read_json(paths.fetched_readiness_document)
        gate_plan = read_json(paths.gate_plan)
        bindings = adapter.inspect_campaign(config.plan_dir, framework_commit)
        # Validating call (not a plain hash): a corrupted-but-well-formed
        # gate-plan.json is caught here instead of silently hashing fine.
        gate_plan_sha256 = adapter.validate_gate_plan(dict(gate_plan), bindings)
        readiness_sha256 = adapter.validate_readiness(
            readiness, bindings, readiness_parent=paths.fetched_readiness,
        )
        preflight_captured_at = _preflight_captured_at(adapter, readiness)
        moment = now()
        # The preflight is consumed here, not merely recorded: a readiness
        # document that is already outside the window must never become a
        # run authorization whose sentence is printed for typing.
        require_fresh(preflight_captured_at, config.preflight_max_age_seconds, at=moment)
        authorization = adapter.run_authorization(
            bindings, gate_plan_sha256, readiness_sha256, readiness=readiness,
            campaign_id=config.campaign_id, not_before=stamp(moment),
            authorization_deadline=deadline_after(config.run_window_hours, at=moment),
        )
        write_json(paths.run_authorization, authorization)
        write_json(paths.run_authorization_receipt, {
            "schemaVersion": 1,
            "kind": "run-authorization-derivation-receipt-v1",
            "campaignId": config.campaign_id,
            "frameworkCommit": framework_commit,
            "gatePlanCanonicalSha256": gate_plan_sha256,
            "readinessCanonicalSha256": readiness_sha256,
            "preflightCapturedAt": preflight_captured_at,
            "derivedAt": stamp(moment),
        })
        return RunAuthorizationDerivation(
            bindings=bindings, readiness=readiness, readiness_sha256=readiness_sha256,
            authorization=authorization, sentence=adapter.expected_gate_run_text(authorization),
        )


def _preflight_captured_at(adapter, readiness: dict) -> str:
    """When the target captured the preflight this readiness document reports.

    The library's freshness window (non-negotiable property #3) is only as
    real as the timestamp it is measured against, and that timestamp's field
    name is SUT-owned: TeaStore's readiness carries `capturedAt`, Hotel's
    carries `observedAt`. An adapter that defines `preflight_captured_at(
    readiness)` names its own field; otherwise `capturedAt` is read. Fails
    closed with `GateDriverError` when the result is not a string -- the
    previous behaviour recorded `None` and let `cmd_execute` die with a
    `TypeError` from datetime arithmetic, which is a crash, not a refusal.
    """
    hook = getattr(adapter, "preflight_captured_at", None)
    value = hook(readiness) if callable(hook) else readiness.get("capturedAt")
    if not isinstance(value, str) or not value:
        raise GateDriverError(
            "readiness carries no preflight capture timestamp "
            "(adapter.preflight_captured_at or readiness['capturedAt'])"
        )
    return value


def _release_binding(adapter, readiness: dict) -> dict:
    """The installed release binding this readiness reports, by the SUT's own name.

    Same opt-in shape as `_preflight_captured_at` and `gate_documents.
    gate_envelope`: the field name is SUT-owned, so an adapter that defines
    `release_binding(readiness)` names its own, and an adapter that defines
    nothing gets TeaStore's `readiness["release"]` unchanged. No existing SUT
    changes behaviour and nothing here is widened -- a declaration is consumed
    where one exists, exactly as `GATE_ENVELOPES` is.

    OTel's readiness has an `_exact()`-enforced top-level key set with no
    `release` in it at all (its spelling is `installedBindings`), so without
    this the `BoundedCampaignController` construction in `cmd_execute` dies
    with a bare `KeyError: 'release'` *after* gate-run.json has already been
    written -- i.e. after the one-shot marker is spent. Fails closed with
    `GateDriverError` naming both the hook and the default field rather than
    handing a `None` to a controller.
    """
    hook = getattr(adapter, "release_binding", None)
    try:
        value = hook(readiness) if callable(hook) else readiness["release"]
    except (KeyError, TypeError) as exc:
        raise GateDriverError(
            "readiness carries no installed release binding "
            "(adapter.release_binding or readiness['release'])"
        ) from exc
    if not isinstance(value, dict) or not value:
        raise GateDriverError(
            "readiness carries no installed release binding "
            "(adapter.release_binding or readiness['release'])"
        )
    return value


def cmd_refresh(config: SutConfig, adapter, paths: GatePaths, *,
                 framework_commit: str,
                 refresh_readiness: Callable[[], int]) -> RunAuthorizationDerivation:
    """Re-run readiness for a fresh preflight, then derive the run authorization.

    `refresh_readiness` is injected because the canonical scripts show two
    different valid ways to refresh -- gate_run.py's `cmd_refresh` shells out
    to `campaign_setup.py auto` (requires a live SETUP-CAMPAIGN
    authorization; gate_run.py:102-106), while `cmd_emit` instead calls
    `gate_setup.py readiness` directly under a still-live GATE-SETUP
    authorization when the SETUP-CAMPAIGN one has expired (gate_run.py:
    428-431). Both are "some way to make fetched-readiness/readiness.json
    fresh again"; this function only cares that it happened. Raises
    `RefreshFailed` fail-closed if the callable reports failure or if either
    required file is missing immediately afterward (gate_run.py:108-122,
    :432-437 -- "a concurrent run moved it").
    """
    rc = refresh_readiness()
    if rc != 0:
        raise RefreshFailed(f"readiness refresh exited {rc}")
    for required, label in (
        (paths.gate_plan, "gate-plan.json"),
        (paths.fetched_readiness_document, "fetched-readiness/readiness.json"),
    ):
        if not required.is_file():
            raise RefreshFailed(
                f"{label} is missing immediately after a successful refresh; "
                "a concurrent run may have moved it"
            )
    return derive_run_authorization(config, adapter, paths, framework_commit=framework_commit)


@dataclass(frozen=True)
class DryRunResult:
    ok: bool
    reasons: tuple
    remote_input: dict | None


def run_dry_run(config: SutConfig, adapter, transport, paths: GatePaths, *,
                 framework_commit: str, scratch_dir: Path) -> DryRunResult:
    """Replay every condition the remote will enforce, without emitting a sentence.

    Reproduces the intent of gate_run.py's `cmd_dryrun` (gate_run.py:
    218-401): build the exact package a real GATE-RUN would build, using a
    probe document explicitly marked `DRY_RUN_APPROVER_MARKER` and written
    only to `scratch_dir` (never to `paths.gates_dir`), then check campaignId
    safety, that the remote output path is free, and the transport's own
    pre-launch replay -- all before returning. Nothing here can launch
    anything: `transport.remote_*` calls are read-only/precheck-only by
    contract. Never raises for an expected failure -- every check failure is
    accumulated into `reasons` so a caller sees everything wrong at once,
    matching the canonical script's `failed` list (gate_run.py:280-299).
    """
    authorization = read_json(paths.run_authorization)
    envelope = gate_envelope(adapter, "GATE-RUN")
    probe_document = build_gate_document(
        kind=adapter.RUN_KIND, gate="GATE-RUN", decision=envelope.decision,
        typed_approval=adapter.expected_gate_run_text(authorization),
        approved_by=DRY_RUN_APPROVER_MARKER, approved_at=stamp(now()),
        payload={envelope.payload_key: authorization}, flags=envelope.flags,
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)
    probe_path = scratch_dir / "gate-run.probe.json"
    write_json(probe_path, probe_document)

    try:
        package = adapter.authorize_from_files(
            config.plan_dir, paths.gate_plan, paths.fetched_readiness_document,
            probe_path, framework_commit=framework_commit,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a dry-run reason, not raised
        return DryRunResult(False, (f"authorize_from_files: {type(exc).__name__}: {exc}",), None)

    try:
        remote_input = transport.build_runtime_package(package)
    except Exception as exc:  # noqa: BLE001
        return DryRunResult(False, (f"build_runtime_package: {type(exc).__name__}: {exc}",), None)
    probe_package_path = scratch_dir / "runtime-package.probe.json"
    write_json(probe_package_path, remote_input)

    reasons = []
    campaign_id = remote_input.get("campaignId", "")
    if _SAFE_CAMPAIGN_SLUG.fullmatch(campaign_id) is None:
        reasons.append(f"campaignId {campaign_id!r} is not a safe slug")

    try:
        if transport.remote_output_exists(remote_input):
            reasons.append("remote output path already exists")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"remote_output_exists: {type(exc).__name__}: {exc}")

    try:
        precheck = transport.remote_precheck(package, remote_input)
        if not precheck.get("ok"):
            reasons.append(f"remote precheck failed: {precheck.get('detail', '<no detail>')}")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"remote_precheck: {type(exc).__name__}: {exc}")

    try:
        # Keyed exactly as `campaign_status_flow.poll_once` keys it: sha256 of
        # the bytes `write_json` puts on disk. `cmd_execute` writes
        # runtime-package.json with the same `write_json`, so the probe file's
        # digest here is the digest the watcher will later present for the
        # real package. `adapter.canonical_sha256(remote_input)` is a
        # different serialization (no indent) and never matched.
        package_sha256 = hashlib.sha256(probe_package_path.read_bytes()).hexdigest()
        transport.remote_status(remote_input, package_sha256)
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"remote_status: {type(exc).__name__}: {exc}")

    return DryRunResult(not reasons, tuple(reasons), remote_input)


def cmd_execute(config: SutConfig, adapter, transport, paths: GatePaths, *,
                 framework_commit: str, typed: str, trace_path: Path) -> dict:
    """Verify the typed GATE-RUN sentence, then LAUNCH the one-shot campaign.

    Reproduces gate_run.py:142-195, plus three guarantees the canonical
    script left to its own re-derivation logic that this generic flow must
    make real itself rather than delegate to a SUT adapter (defence in depth
    stays -- a SUT's own checks are never removed or weakened by this):

    1. Preflight-capture age (non-negotiable property #3): `require_fresh`
       against both when the run-authorization derivation itself happened
       and when the underlying runtime preflight was captured, using
       `config.preflight_max_age_seconds` (`freshness.PREFLIGHT_MAX_AGE_SECONDS`
       by default). Raises `errors.PreflightExpired`.
    2. Byte-exact re-derivation / plan-digest equality: `gate-plan.json` is
       re-hashed right now and compared against the digest recorded in
       `run-authorization-receipt.json` at derivation time -- catching a
       plan file (or campaign identity) substituted between derive and
       execute. Raises `errors.RunAuthorizationDrift`.
    3. Schedule immutability has no generic hook here -- the library has no
       concept of a compiled cell schedule; a SUT with one (e.g. Hotel's
       `_assert_scheduled_cell`) enforces it in its own runtime, not here.

    Both checks read `paths.run_authorization_receipt`, written only by
    `derive_run_authorization`; its absence (e.g. a hand-authored
    run-authorization.json, or a receipt removed independently of its
    authorization) fails closed with `errors.MissingDerivationReceipt` rather
    than assuming freshness.

    `write_new_json(paths.gate_run, ...)` remains the structural guarantee
    that a one-shot campaign cannot be launched twice under the same
    run-authorization: a second `cmd_execute` call against an unmoved
    gate-run.json raises `PathAlreadyExists` before any remote call is made.
    Runs under `paths.run_lock`, same as `derive_run_authorization`.
    """
    with SingleFlightLock(paths.run_lock):
        if not paths.run_authorization_receipt.is_file():
            raise MissingDerivationReceipt(paths.run_authorization_receipt)
        receipt = read_json(paths.run_authorization_receipt)

        require_fresh(receipt["derivedAt"], config.preflight_max_age_seconds)
        require_fresh(receipt["preflightCapturedAt"], config.preflight_max_age_seconds)

        if receipt["campaignId"] != config.campaign_id:
            raise RunAuthorizationDrift("campaignId", receipt["campaignId"], config.campaign_id)

        fresh_gate_plan_sha256 = adapter.canonical_sha256(read_json(paths.gate_plan))
        if fresh_gate_plan_sha256 != receipt["gatePlanCanonicalSha256"]:
            raise RunAuthorizationDrift(
                "gatePlanCanonicalSha256", receipt["gatePlanCanonicalSha256"], fresh_gate_plan_sha256,
            )

        authorization = read_json(paths.run_authorization)
        expected = verify_typed_sentence(typed, adapter.expected_gate_run_text(authorization))

        envelope = gate_envelope(adapter, "GATE-RUN")
        gate_run_document = build_gate_document(
            kind=adapter.RUN_KIND, gate="GATE-RUN", decision=envelope.decision,
            typed_approval=expected, approved_by=config.approved_by,
            approved_at=stamp(now()), payload={envelope.payload_key: authorization},
            flags=envelope.flags,
        )
        write_new_json(paths.gate_run, gate_run_document)

        package = adapter.authorize_from_files(
            config.plan_dir, paths.gate_plan, paths.fetched_readiness_document,
            paths.gate_run, framework_commit=framework_commit,
        )
        remote_input = transport.build_runtime_package(package)
        if transport.remote_output_exists(remote_input):
            raise GateDriverError("remote output path already exists")
        write_json(paths.runtime_package, remote_input)

        runner = traced_runner(transport.subprocess_runner, trace_path)
        controller = transport.BoundedCampaignController(
            framework_commit=framework_commit,
            release_binding=_release_binding(adapter, package.readiness),
            runner=runner,
        )
        result = controller.launch(paths.runtime_package, local_output=paths.campaign_result)
        write_json(paths.campaign_terminal, result)
        return result
