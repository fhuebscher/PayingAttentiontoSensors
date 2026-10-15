#!/usr/bin/env python3
"""OTel Demo's `AdapterProtocol` surface, delegating into `candidate_runtime.py`.

`obsplacement.gate_driver.contract.AdapterProtocol` names eleven callables,
four document-kind tags and one execution user. The OTel orchestrator owns
every one of those computations already -- but under a different vocabulary
and, in four places, a different *signature*:

| contract                | candidate_runtime            |
|-------------------------|------------------------------|
| `inspect_campaign`      | `inspect_compiled_plan(root)` |
| `plan_binding`          | `operational_binding(bindings, **five)` |
| `validate_gate_plan`    | same name, returns `(document, sha)` not `sha` |
| `setup_authorization`   | `setup_binding(plan, plan_sha)` |
| `run_authorization`     | `run_binding(plan, plan_sha, readiness, readiness_sha, ...)` |
| `authorize_from_files`  | same name, six paths not four |

This module is the translation layer and nothing else. It reimplements no
validator, derives no sentence text of its own (every `expected_*_text` is
`candidate_runtime`'s, verbatim) and performs no remote action.

Two seams are worth stating out loud because they are not pure translation:

1. **`plan_binding` needs three digests the plan does not carry.**
   `operational_binding` binds the GATE-PLAN to `repositoryBundleSha256`,
   `upstreamBundleSha256` and `expectedMaterializedSourceSha256`. None of
   those is a property of the compiled plan; all three are produced by
   `candidate_transport.build_release_bundle`, which the flow layer calls
   *after* `inspect_campaign` and *before* `plan_binding`
   (`campaign_setup_flow.cmd_auto`, and `gate_setup_flow.cmd_prepare` ->
   `cmd_record_plan`). So `Bindings` is mutable in exactly one direction:
   the transport calls `bind_release(...)` on it, once, and `plan_binding`
   fails closed with a named error if that has not happened. Hotel did not
   need this because its plan binding carries no bundle identity.

2. **`setup_authorization` ignores three of its keyword arguments.**
   OTel's GATE-SETUP binding is validated with `_exact(...)` against a fixed
   key set, so a `setupId`, `notBefore` or `authorizationDeadline` added here
   would be rejected by the orchestrator's own `validate_gate_setup_reference`.
   OTel bounds GATE-SETUP freshness on `approvedAt` against
   `MAX_GATE_AGE_SECONDS` (900 s) instead of on a carried deadline, so
   `SutConfig.setup_window_hours` has no effect on this SUT -- stated here
   rather than left as a silently dead configuration field.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

__all__ = [
    "PLAN_KIND", "SETUP_KIND", "RUN_KIND", "EXECUTION_USER",
    "TRANSPORT_USER", "TARGET_HOST", "STUDY_EPOCH", "CHANGE_ID",
    "Bindings", "inspect_campaign", "plan_binding", "validate_gate_plan",
    "expected_gate_plan_text", "setup_authorization", "expected_gate_setup_text",
    "validate_readiness", "run_authorization", "expected_gate_run_text",
    "authorize_from_files", "canonical_sha256", "GATE_ENVELOPES",
    "preflight_captured_at", "release_binding",
]

# The three envelope literals this SUT's own validators demand, declared through
# the shared library's opt-in extension point (`gate_documents.gate_envelope`).
# Without this the library builds documents from its canonical TeaStore-shaped
# defaults, and `validate_gate_plan` refuses them on the first real `auto`:
#   FATAL: GATE-PLAN keys differ: expected [... 'binding' ...],
#                                 observed [... 'bindings' ...]
# Derived from the validators in `candidate_runtime.py`, not from the error:
#   - all three file their body under "binding" (singular), where the library
#     defaults to "bindings" for GATE-PLAN and "authorization" for the other two
#     (`validate_gate_plan` :1790, `validate_gate_setup` :1893,
#      `validate_gate_run_reference` :3037 each read `document["binding"]`).
#   - GATE-SETUP's decision is "authorize-one-shot-exact-setup", not the library
#     default "authorize-exact-setup-only". GATE-PLAN's and GATE-RUN's match.
#   - flags match the defaults, and GATE-RUN genuinely has no `runtimeAuthorized`
#     key: its validator compares `set(document)` exactly, so adding one is
#     refused just as firmly as omitting one.
# A partial declaration raises ContractViolation rather than falling back, so
# all three gates are stated even where the default would have sufficed.

def preflight_captured_at(readiness) -> str:
    """When the target captured this readiness: OTel spells it `readinessObservedAt`.

    The shared library measures its 900-second preflight window against this
    value (`gate_run_flow.derive_run_authorization` / `cmd_execute`). Its
    default field name is TeaStore's `capturedAt`, which no OTel readiness
    document carries, so without this bridge `oneshot` refuses with "readiness
    carries no preflight capture timestamp" *after* readiness has already been
    admitted. Hotel declares the same bridge for its own `observedAt`.

    Re-read, not re-derived: `validate_readiness` has already checked this
    field against the runtime policy's freshness bound.
    """
    value = readiness.get("readinessObservedAt") if isinstance(readiness, Mapping) else None
    if not isinstance(value, str) or not value:
        raise runtime.GateError("readiness carries no readinessObservedAt timestamp")
    return value


def release_binding(readiness) -> dict:
    """The installed release binding: OTel spells it `installedBindings`.

    `gate_run_flow.cmd_execute` hands this to `BoundedCampaignController` as
    `release_binding=`. Its default field name is TeaStore's `release`, which
    no OTel readiness document can carry: `validate_readiness_reference`
    pins the top-level key set with `_exact(...)` to
    {schemaVersion, kind, studyEpoch, gatePlanSha256, gateSetupSha256,
     setupReceiptSha256, installedBindings, bindingSha256, target, producer,
     readinessObservedAt, runCount, runtimeReady, candidateEvidenceAuthorized,
     promotionAuthorized, seams}, so adding a `release` alias to the document
    would be refused by OTel's own validator as firmly as omitting one.

    `installedBindings` is the corresponding field, not a substitute chosen
    for convenience: it is `installed_bindings(setup_receipt, ...)`'s output
    (candidate_runtime.py:2374), it is the same projection the driver builds
    as `release_binding = {key: receipt[key] for key in binding_keys}` for
    `build_capture_spec`/`admit_readiness`, and OTel's own execution package
    reads exactly `package.readiness["installedBindings"]` in this role
    (candidate_runtime.py:3261-3263, :3336-3337).

    Re-read, not re-derived: `validate_readiness` has already checked this
    field against the gate-plan binding before this is called.
    """
    value = readiness.get("installedBindings") if isinstance(readiness, Mapping) else None
    if not isinstance(value, Mapping) or not value:
        raise runtime.GateError("readiness carries no installedBindings projection")
    return dict(value)

GATE_ENVELOPES = {
    "GATE-PLAN": {
        "decision": "approve-exact-plan",
        "payload_key": "binding",
        "flags": {"runtimeAuthorized": False, "promotionAuthorized": False},
    },
    "GATE-SETUP": {
        "decision": "authorize-one-shot-exact-setup",
        "payload_key": "binding",
        "flags": {"runtimeAuthorized": False, "promotionAuthorized": False},
    },
    "GATE-RUN": {
        "decision": "authorize-one-shot-exact-run",
        "payload_key": "binding",
        "flags": {"promotionAuthorized": False},
    },
}

# One module name shared with `candidate_transport`, so the 3.6k-line
# orchestrator is executed exactly once per process even though `SutConfig`
# names two separate files that both load it.
_RUNTIME_MODULE_NAME = "otel_candidate_runtime_orchestrator"
_PILOT_MODULE_NAME = "otel_candidate_pilot_compiler"


def _load(name: str, filename: str):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - real file
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(_RUNTIME_MODULE_NAME, "candidate_runtime.py")
# The active epoch's compiler: candidate_pilot.py, or the one the committed study-epoch selector swaps in
# (candidate_runtime.CONTROLLER_PATHS["candidate-compiler"]); the same file name, so the frozen path is unchanged.
pilot = _load(_PILOT_MODULE_NAME, Path(runtime.CONTROLLER_PATHS["candidate-compiler"]).name)

PLAN_KIND = runtime.PLAN_KIND
SETUP_KIND = runtime.SETUP_KIND
RUN_KIND = runtime.RUN_KIND
STUDY_EPOCH = runtime.STUDY_EPOCH
CHANGE_ID = runtime.CHANGE_ID

# Read off the reviewed target contract rather than retyped: the allocation
# file is itself digested into every GATE-PLAN (`targetContractSha256`), so
# sourcing the identity from it means this module cannot drift away from the
# thing the gate binds. `target_allocation()` re-verifies the file against
# the orchestrator's own expected projection before returning it.
_ALLOCATION = runtime.target_allocation()
TARGET_HOST = _ALLOCATION["host"]
TRANSPORT_USER = _ALLOCATION["transportUsers"][0]
EXECUTION_USER = _ALLOCATION["executionIdentities"][0]["user"]

canonical_sha256 = runtime.canonical_sha256

# The campaign identity every derived path is named after, and the identity
# the shared gate-driver library validates as a slug. `operational_binding`
# requires SAFE_NAME and <= 40 characters.
#
# This is the HYPHENATED spelling, identical to `drivers/gate_driver_config.py`
# `CONFIG.campaign_id`, and it must stay hyphenated: the shared library's
# `gate_run_flow._SAFE_CAMPAIGN_SLUG` (`[a-z0-9][a-z0-9-]{0,63}`) rejects an
# underscore, and that validator is shared with TeaStore and Hotel, which
# carry 177 valid cells between them -- widening it for this SUT's spelling
# is not available.
#
# The underscore form this used to derive here has NOT gone away; it moved to
# the one place that wanted it, `operational_binding`'s Compose project name
# (`candidate_runtime.compose_project_for`). The campaign id and the Compose
# project are two different strings and the code now says so. Every target-side
# guard that binds a PATH to this id -- `candidate_remote.validate_package`'s
# `root.name != document["campaignId"]` and `_bounded_abort_identity`'s
# `EXPECTED_ARTIFACT_PARENT / campaignId` -- keeps holding byte-exactly,
# because the paths follow the id rather than the Compose name.
CAMPAIGN_ID = "otel-demo-offpath-v1"
# A selector-activated epoch is its own campaign (the hyphenated epoch id; operational_binding caps it at 40
# characters and derives the Compose project, the artifact root and the release root from it).
if runtime.is_sweep_epoch():
    CAMPAIGN_ID = runtime.STUDY_EPOCH


class Bindings:
    """What `inspect_campaign` returns: the plan replay plus what binds to it.

    `contract.campaign_identity` reads `descriptor_sha256`, `plan_sha256` and
    `run_ids` off this object; everything else is for this module and
    `candidate_transport`. Deliberately a plain class rather than a frozen
    dataclass: `bind_release` and `bind_gate_plan` are the two documented
    one-way transitions described in the module docstring.
    """

    def __init__(self, plan_bindings, *, framework_commit: str, campaign_id: str,
                 plan_dir: Path):
        self.plan_bindings = plan_bindings
        self.framework_commit = framework_commit
        self.campaign_id = campaign_id
        self.plan_dir = Path(plan_dir)
        self.repository_bundle_sha256: Optional[str] = None
        self.upstream_bundle_sha256: Optional[str] = None
        self.expected_materialized_source_sha256: Optional[str] = None
        self.gate_plan: Optional[dict] = None
        self.gate_plan_sha256: Optional[str] = None

    # -- the three facts contract.campaign_identity reads -------------------
    @property
    def descriptor_sha256(self) -> str:
        return self.plan_bindings.descriptor_sha256

    @property
    def plan_sha256(self) -> str:
        return self.plan_bindings.plan_sha256

    @property
    def run_ids(self):
        return self.plan_bindings.run_ids

    def bind_release(self, *, repository_bundle_sha256: str,
                     upstream_bundle_sha256: str,
                     expected_materialized_source_sha256: str) -> None:
        """Record the three digests `operational_binding` needs. Idempotent.

        Rebinding to *different* values raises: within one derivation the
        GATE-PLAN sentence must be a function of one release, not of whichever
        bundle was built last.
        """
        new = (repository_bundle_sha256, upstream_bundle_sha256,
               expected_materialized_source_sha256)
        old = (self.repository_bundle_sha256, self.upstream_bundle_sha256,
               self.expected_materialized_source_sha256)
        if old != (None, None, None) and old != new:
            raise runtime.GateError(
                "release identity was already bound to different bundle digests"
            )
        (self.repository_bundle_sha256, self.upstream_bundle_sha256,
         self.expected_materialized_source_sha256) = new

    def require_release(self) -> None:
        if None in (self.repository_bundle_sha256, self.upstream_bundle_sha256,
                    self.expected_materialized_source_sha256):
            raise runtime.GateError(
                "GATE-PLAN binding needs the release bundle digests; "
                "candidate_transport.build_release_bundle has not run for these bindings"
            )

    def require_gate_plan(self) -> tuple:
        if self.gate_plan is None or self.gate_plan_sha256 is None:
            raise runtime.GateError(
                "no validated GATE-PLAN is bound; validate_gate_plan must run first"
            )
        return self.gate_plan, self.gate_plan_sha256


# Attempts whose run IDs already exist on a host, per study epoch. Reusing one
# would give a promotable cell the identity of an unpromotable one. Append, never
# remove. The epoch is part of every runKey, so a v3 attempt 1 has run IDs no v2
# attempt ever had; the v2 rows are recorded for the history, not to block v3.
SPENT_ATTEMPTS_BY_EPOCH = {
    "otel-demo-candidate-pilot-v2": {
        1: "run 1, the 2026-09-18 fb14srv6 shakedown, unpromotable by OTEL_RUN1_SHAKEDOWN_DECLARATION.md",
        2: "run 2, 2026-09-24, failed terminal validation (OTEL_RUN2_STOPPING_RULE.md)",
        3: "run 3, 2026-09-24, terminal-valid 18/18 (OTEL_RUN3_RESULT.md)",
    },
    "otel-demo-candidate-pilot-v3": {
        1: "v3r1, 2026-09-30, terminal-valid 24/24 (main repo research/otel-postures/RESULT.md)",
        2: "v3 attempt 2, 2026-10-01, launched from otel-postures-20260930 64ba7c9",
    },
    "otel-demo-offpath-v1": {},
    "otel-traffic-sweep-v1": {
        1: "sweep attempt 1, 2026-10-03, activation 6380cce, stopped at cell 8 (trace completeness 20/21 under M1); "
           "7/8 valid; main repo research/traffic-sweep/STOP_OTEL_ATTEMPT1.md",
    },
    # 2026-10-04: the quiet calibration epoch's first launch was attempt 1.
    "otel-quiet-calibration-v1": {
        1: "quiet attempt 1, 2026-10-04, activation 6e37ec2, plan 5cec5a69, stopped at cell 8 (r10-b02-04: 50 "
           "consecutive requests without their productcatalogservice span, decision 25); 7/8 valid; main repo "
           "research/traffic-sweep/STOP_QUIET_OTEL_A1.md",
        # 2026-10-10: run A's relaunch 1 ran all 40 cells on fb14srv6 (harness 6a47d0b, plan bb1eb1fc, terminal-valid, fetched and
        # byte-verified 647/647). Run A2 (protocol decision 68) is therefore attempt 3.
        2: "quiet attempt 2 (run A, relaunch 1), 2026-10-05, harness 6a47d0b, plan bb1eb1fc, terminal-valid 40/40; main repo "
           "research/traffic-sweep/AMENDMENT_QUIET_OTEL_1.md",
    },
    # 2026-10-09: the repeat-episodes epoch (campaign B) has run nothing; its first launch is attempt 1.
    # 2026-10-10: B attempt 1 ran on fb14srv6 (launched 2026-10-09 15:23Z, terminal 18:38Z) and was fetched (receipt
    # terminal-valid, 36 cell directories, host and local sha256 lists identical, 619/619). A relaunch of B is attempt 2.
    "otel-repeat-episodes-v1": {
        1: "campaign B attempt 1, 2026-10-09, harness c4aa313, plan 3aaf5923, fetch receipt terminal-valid, 36 cells, "
           "byte-verified 619/619; main repo research/traffic-sweep/DECLARATION_B_OTEL.md",
    },
    # 2026-10-11: campaign C (otel-repeat-episodes-c-v1, decision 82) has run nothing; its first launch is attempt 1.
    # 2026-10-12: C attempt 1 ran on fb14srv6 (launched 2026-10-11 00:47Z, terminal 04:01Z; remote-terminal 36/36 valid) and
    # was fetched by a manual tar (host and local sha256 lists identical, 619/619). A relaunch of C is attempt 2.
    "otel-repeat-episodes-c-v1": {
        1: "campaign C attempt 1, 2026-10-11, harness 8018a19, plan ece8caa0, remote-terminal 36/36 valid, fetched and "
           "byte-verified 619/619; main repo research/traffic-sweep/DECLARATION_C_OTEL.md",
    },
    # 2026-10-12: the load pilot (otel-load-pilot-v1, BUDGET_D.md amendment 1) had run nothing at its epoch commit.
    # 2026-10-12: it then ran on fb14srv6 (launched 03:52Z, host terminal 04:33Z; remote-terminal 6/6 valid, fetched and
    # byte-verified 107/107; main repo research/placement/pilot-load/RESULT_P1.md). A relaunch of the pilot is attempt 2.
    "otel-load-pilot-v1": {
        1: "load pilot attempt 1, 2026-10-12, harness 7b20ec4, plan aea94eb9, remote-terminal 6/6 valid, fetched and "
           "byte-verified 107/107; main repo research/traffic-sweep/DECLARATION_PILOT_LOAD_OTEL.md",
    },
    # 2026-10-13: the off-path manifestation pilot (otel-offpath-pilot-v1, BUDGET_E.md) had run nothing at its epoch commit.
    # 2026-10-12: it then ran on fb14srv6 (launched 09:37Z, stopped 09:57Z at its cell 2: productcatalogservice memcg-OOM-killed at
    # its upstream 20 MiB limit, restarted by Docker, the container-health guard invalidated the cell; 2 attempted, 1 valid; fetched
    # and byte-verified 40/40; BUDGET_E amendment 1, decision 108). A relaunch of v1 is attempt 2; the next pilot is v2.
    "otel-offpath-pilot-v1": {
        1: "off-path pilot v1 attempt 1, 2026-10-12, harness 8c53cb2, plan 8b3d7aa8, stopped at cell 2 (productcatalogservice OOM at "
           "20 MiB, 100 req/s), 2 attempted / 1 valid, fetched and byte-verified 40/40; main repo "
           "research/traffic-sweep/DECLARATION_PILOT_OFFPATH_OTEL.md",
    },
    # 2026-10-12: the second off-path pilot (otel-offpath-pilot-v2, BUDGET_E amendment 1, decision 108) had run nothing at its epoch commit.
    # 2026-10-12: it then ran on fb14srv6 (launched 11:52:54Z, terminal 12:42:08Z; 8 attempted / 8 valid; fetched and byte-verified
    # 147/147; offline terminal replay pass 8/8 at ff29b93). A relaunch of v2 is attempt 2; the next campaign is E.
    "otel-offpath-pilot-v2": {
        1: "off-path pilot v2 attempt 1, 2026-10-12, harness ff29b93, plan a929b4d9, 8 attempted / 8 valid, fetched and "
           "byte-verified 147/147; main repo research/traffic-sweep/DECLARATION_PILOT_OFFPATH_V2_OTEL.md",
    },
    # 2026-10-12: campaign E (otel-offpath-e-v1, BUDGET_E, decisions 95-102) had run nothing at its epoch commit.
    # 2026-10-13: it then ran on fb14srv6 (launcher started 03:37:40Z, host unit 03:43:15Z, terminal 05:35:08Z; 20 of 20 cells valid; fetched and
    # byte-verified 357/357; offline terminal replay pass 20/20). A relaunch of E is attempt 2; the next campaign is F.
    "otel-offpath-e-v1": {
        1: "campaign E attempt 1, 2026-10-13, harness 6a5c2a9, plan 503bf014, 20 attempted / 20 valid, fetched and byte-verified 357/357; "
           "main repo research/traffic-sweep/DECLARATION_E_OTEL.md and research/placement/test-e/RESULT_E.md",
    },
    # 2026-10-14: campaign F (otel-offpath-f-v1, BUDGET_F) has run nothing; its first launch is attempt 1.
    "otel-offpath-f-v1": {},
}
SPENT_ATTEMPTS = SPENT_ATTEMPTS_BY_EPOCH[STUDY_EPOCH]


def inspect_campaign(plan_dir, framework_commit: str) -> Bindings:
    """Materialize-or-verify the plan directory, then replay it.

    `candidate_pilot.materialize` is exclusive-create-or-byte-compare, so
    calling it on an existing directory is a *verification* (it raises
    `ProtocolError` if a retained copy differs), not a regeneration. That
    makes `propose-campaign` work from a cold checkout without a separate
    compile step, and makes a tampered plan directory fail closed.

    `inspect_compiled_plan` then re-derives the schedule from the descriptor,
    proves the posture catalog, executes every guarded entrypoint against a
    stubbed PATH and re-reads the target allocation -- all offline. Nothing
    here contacts the target.
    """
    plan_dir = Path(plan_dir)
    attempt = pilot.campaign_attempt()
    if attempt in SPENT_ATTEMPTS:
        raise runtime.GateError(
            f"attempt {attempt} is spent ({SPENT_ATTEMPTS[attempt]}); the launcher must set "
            f"{pilot.ATTEMPT_ENVIRONMENT} to an unspent attempt"
        )
    pilot.materialize(plan_dir, runtime.DESCRIPTOR, attempt)
    return Bindings(
        runtime.inspect_compiled_plan(plan_dir),
        framework_commit=framework_commit,
        campaign_id=CAMPAIGN_ID,
        plan_dir=plan_dir,
    )


def plan_binding(bindings: Bindings) -> dict:
    bindings.require_release()
    return runtime.operational_binding(
        bindings.plan_bindings,
        framework_commit=bindings.framework_commit,
        campaign_id=bindings.campaign_id,
        repository_bundle_sha256=bindings.repository_bundle_sha256,
        upstream_bundle_sha256=bindings.upstream_bundle_sha256,
        expected_materialized_source_sha256=bindings.expected_materialized_source_sha256,
    )


def expected_gate_plan_text(bindings: Bindings) -> str:
    return runtime.expected_gate_plan_text(plan_binding(bindings))


def validate_gate_plan(document: Any, bindings: Bindings) -> str:
    """Project the orchestrator's `(document, digest)` onto the contract's `digest`.

    The validated document is retained on `bindings` because
    `setup_authorization` and `run_authorization` need the GATE-PLAN itself
    and the flow layer hands them only its digest. The digest returned here
    and the digest recorded on the bindings are the same value by
    construction, so a caller cannot end up authorizing against one plan
    while reporting another.
    """
    checked, digest = runtime.validate_gate_plan(document, bindings.plan_bindings)
    bindings.gate_plan = checked
    bindings.gate_plan_sha256 = digest
    return digest


def setup_authorization(bindings: Bindings, gate_plan_sha, target_proof,
                        release_manifest, *, setup_id, execution_user,
                        not_before, authorization_deadline) -> dict:
    """OTel's GATE-SETUP binding.

    `setup_id`, `not_before` and `authorization_deadline` are accepted and
    unused -- see the module docstring's seam 2. `target_proof` and
    `release_manifest` are likewise unused: `setup_binding` reads every fact
    it needs out of the GATE-PLAN, which already binds the bundle digests and
    the target contract digest. Re-reading them from the manifest file would
    introduce a second source for facts the gate document has already fixed
    (the same reasoning Hotel's installer shim gives for ignoring them).
    """
    plan, plan_sha = bindings.require_gate_plan()
    if gate_plan_sha != plan_sha:
        raise runtime.GateError("GATE-SETUP is being derived against a different GATE-PLAN")
    if execution_user != EXECUTION_USER:
        raise runtime.GateError(
            f"configured execution user {execution_user!r} is not the "
            f"allocation's {EXECUTION_USER!r}"
        )
    return runtime.setup_binding(plan, plan_sha)


def expected_gate_setup_text(authorization: Mapping[str, Any]) -> str:
    return runtime.expected_gate_setup_text(authorization)


def validate_readiness(readiness, bindings: Bindings, *, readiness_parent) -> str:
    """Freshness-checked readiness validation; returns the canonical digest.

    `readiness_parent` is accepted and unused: OTel's readiness document is
    self-describing (it carries `gateSetupSha256`, `setupReceiptSha256` and
    `installedBindings`, all re-validated against the GATE-PLAN here), so
    there is no sibling capture directory to cross-check it against the way
    Hotel's retained-versus-convenience copy needs.
    """
    plan, plan_sha = bindings.require_gate_plan()
    return runtime.validate_readiness(
        readiness, plan, plan_sha, now=datetime.now(timezone.utc),
    )


def run_authorization(bindings: Bindings, gate_plan_sha, readiness_sha, *,
                      readiness, campaign_id, not_before,
                      authorization_deadline) -> dict:
    plan, plan_sha = bindings.require_gate_plan()
    if gate_plan_sha != plan_sha:
        raise runtime.GateError("GATE-RUN is being derived against a different GATE-PLAN")
    if campaign_id is not None:
        # A straight equality compare, and it has to stay one. The driver config,
        # `CAMPAIGN_ID` above and `plan["binding"]["campaignId"]` are now all the
        # same hyphenated string, so there is nothing to normalise. The previous
        # `.replace("-", "_")` here existed only to bridge a spelling difference
        # that no longer exists; re-introducing any normalisation would make this
        # check accept two campaign identities that differ, which is exactly what
        # it is here to refuse. The underscore form lives in
        # `candidate_runtime.compose_project_for` and nowhere else.
        if campaign_id != plan["binding"]["campaignId"]:
            raise runtime.GateError("GATE-RUN campaign identity differs from the GATE-PLAN")
    return runtime.run_binding(
        plan, plan_sha, readiness, readiness_sha,
        not_before=not_before, authorization_deadline=authorization_deadline,
    )


def expected_gate_run_text(authorization: Mapping[str, Any]) -> str:
    return runtime.expected_gate_run_text(authorization)


def authorize_from_files(plan_dir, gate_plan_path, readiness_path,
                         gate_run_path, *, framework_commit):
    """Replay the whole chain from disk, exactly as the orchestrator does.

    The contract names four paths; OTel's `authorize_from_files` needs six --
    the GATE-SETUP document and the fetched setup receipt as well. Both are
    siblings of `gate_plan_path` at the conventional `GatePaths` names, so
    they are located rather than invented, and a missing one raises the
    orchestrator's own "cannot read" error naming the file.
    """
    gates = Path(gate_plan_path).parent
    # `install-receipt.json` is the DRIVER's record of the install; it is not the
    # setup receipt. It carries 13 keys about the transport and names the real
    # 34-key target-side receipt in `setupReceiptPath`, attested by
    # `setupReceiptSha256` (a canonical digest, not a digest of the file bytes).
    # Passing the driver record here made the remote refuse with "setup receipt
    # keys differ: expected [34] observed [13]". Resolve and VERIFY rather than
    # simply pointing at a different file: the digest is what makes this the
    # document the install actually attested to.
    install = json.loads((gates / "install-receipt.json").read_text(encoding="utf-8"))
    setup_receipt_path = Path(install["setupReceiptPath"])
    if canonical_sha256(json.loads(setup_receipt_path.read_text(encoding="utf-8"))) != install["setupReceiptSha256"]:
        raise runtime.GateError(
            "setup receipt does not match the digest its install receipt attests to"
        )
    return runtime.authorize_from_files(
        Path(plan_dir),
        Path(gate_plan_path),
        gates / "gate-setup.json",
        setup_receipt_path,
        Path(readiness_path),
        Path(gate_run_path),
    )
