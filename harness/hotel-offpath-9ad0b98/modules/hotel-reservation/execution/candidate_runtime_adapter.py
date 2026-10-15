#!/usr/bin/env python3
"""Hotel's `AdapterProtocol` surface, delegating into `candidate_runtime.py`.

`obsplacement.gate_driver.contract.AdapterProtocol` names fifteen members the
four Hotel driver scripts call by name. Hotel's orchestrator
(`candidate_runtime.py`, ~4000 lines) already implements every one of the
underlying behaviours, but under different names, different signatures, and
in two cases behind a leading underscore. This module is the translation
layer: it owns no governance logic of its own, derives no sentence text of
its own, and validates nothing the orchestrator does not already validate.
Every member below either re-exports an orchestrator symbol verbatim or
adapts an argument list, and each adaptation says why.

Deliberate properties:

* **The orchestrator is untouched.** Nothing here writes back into
  `candidate_runtime.py`; the file is loaded once (see `_load_runtime`) and
  only read from. Adding this file therefore does not move
  `controllerSha256` -- `CONTROLLER_PATHS` in the orchestrator enumerates the
  thirteen files whose bytes are hashed into the plan binding, and this file
  is not one of them.
* **Nothing here builds an approval sentence.** `expected_gate_plan_text` /
  `expected_gate_setup_text` / `expected_gate_run_text` are straight
  re-exports of the orchestrator's own derivations. There is no f-string in
  this file that assembles sentence text.
* **Every adaptation fails closed.** Where the library hands over a value the
  orchestrator would otherwise have recomputed (a plan digest, an execution
  user), the value is cross-checked against the orchestrator's own
  computation and a mismatch raises `GateError` rather than being preferred,
  ignored, or repaired.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "PLAN_KIND", "SETUP_KIND", "RUN_KIND", "EXECUTION_USER", "GATE_ENVELOPES",
    "GATES_DIR", "RuntimeAdmission",
    "new_setup_id", "new_campaign_id",
    "inspect_campaign", "plan_binding", "validate_gate_plan",
    "expected_gate_plan_text", "setup_authorization", "expected_gate_setup_text",
    "validate_readiness", "preflight_captured_at", "run_authorization",
    "expected_gate_run_text", "authorize_from_files", "canonical_sha256",
]

# One module object for the orchestrator, shared by this module, the
# transport shim, and anything else in the same process that loads it under
# this name. `SutConfig.adapter_module` / `.transport_module` name two
# different files, but both of them load `candidate_runtime.py`; without a
# shared module name the 4000-line file would be executed twice and the two
# copies' `GateError` classes would not compare equal under `except`.
_RUNTIME_MODULE_NAME = "hotel_candidate_runtime_orchestrator"


def _load_runtime():
    existing = sys.modules.get(_RUNTIME_MODULE_NAME)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parent / "candidate_runtime.py"
    spec = importlib.util.spec_from_file_location(_RUNTIME_MODULE_NAME, path)
    if spec is None or spec.loader is None:  # pragma: no cover - unreachable for a real file
        raise ImportError(f"cannot load the Hotel orchestrator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RUNTIME_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


runtime = _load_runtime()

ROOT = Path(__file__).resolve().parents[3]

# The gates directory the four Hotel driver scripts operate in. This must stay
# byte-identical to `SutConfig.gates_dir` in
# `modules/hotel-reservation/drivers/gate_driver_config.py`; that file lives
# in a different worktree, so the two declarations cannot import each other.
# `tests/test_hotel_gate_driver_config.py` pins them equal so a rebind of one
# without the other fails a test rather than a campaign.
GATES_DIR = ROOT / ".local/candidate-v4/hotel-reservation/gates"

PLAN_KIND = runtime.PLAN_KIND
SETUP_KIND = runtime.SETUP_KIND
RUN_KIND = runtime.RUN_KIND
EXECUTION_USER = runtime.TARGET["executionUser"]

# The one transport the orchestrator's runtime policy allows.
TRANSPORT_ID = "ssh-compose"

canonical_sha256 = runtime.canonical_sha256
"""Hotel's digest formula, re-exported rather than reimplemented.

The shared library ships its own `hashing.canonical_sha256`, which differs
from the orchestrator's `canonical_bytes` in one keyword: the library relies
on `json.dumps`'s default `ensure_ascii=True`, the orchestrator passes
`ensure_ascii=False`. The two agree on every ASCII-only document and diverge
the moment one carries a non-ASCII character. Rather than make the two
formulas agree (which would touch the library on Hotel's behalf, for a seam
no Hotel document crosses), the adapter re-exports the orchestrator's
formula, so exactly one formula ever hashes a Hotel gate document -- the one
whose output the orchestrator's own validators compare against.
"""

plan_binding = runtime.plan_binding
expected_gate_plan_text = runtime.expected_gate_plan_text
expected_gate_setup_text = runtime.expected_gate_setup_text
expected_gate_run_text = runtime.expected_gate_run_text

# Hotel's own validators demand envelope literals the shared library would
# otherwise hardcode to TeaStore's. Declaring them here is what lets
# `gate_documents.build_gate_document` assemble a document
# `candidate_runtime.validate_gate_{plan,setup,run}` accepts:
#   - GATE-SETUP's decision is "authorize-exact-one-shot-setup", not the
#     library default "authorize-exact-setup-only" (validate_gate_setup).
#   - GATE-RUN's decision is "authorize-exact-run", not the library default
#     "authorize-one-shot-exact-run" (validate_gate_run).
#   - all three file their body under "bindings", not "authorization"
#     (each validator reads `document["bindings"]`).
#   - each gate's flag set is exact: the validators compare `set(document)`
#     against a fixed key set, so a missing *or* an extra flag is refused.
GATE_ENVELOPES = {
    "GATE-PLAN": {
        "decision": "approve-exact-plan",
        "payload_key": "bindings",
        "flags": {
            "runtimeAuthorized": False,
            "setupAuthorized": False,
            "externalMutationAuthorized": False,
            "promotionAuthorized": False,
        },
    },
    "GATE-SETUP": {
        "decision": "authorize-exact-one-shot-setup",
        "payload_key": "bindings",
        "flags": {
            "setupAuthorized": True,
            "externalMutationAuthorized": True,
            "runtimeAuthorized": False,
            "promotionAuthorized": False,
        },
    },
    "GATE-RUN": {
        "decision": "authorize-exact-run",
        "payload_key": "bindings",
        "flags": {
            "runtimeAuthorized": True,
            "externalMutationAuthorized": True,
            "promotionAuthorized": False,
        },
    },
}

_STAMP = "%Y%m%dt%H%M%Sz"


def _stamp(at: datetime | None = None) -> str:
    moment = at if at is not None else datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime(_STAMP)


def new_setup_id(at: datetime | None = None) -> str:
    """Mint a setup identity the orchestrator's `SETUP_ID` regex accepts.

    The library proposes `secrets.token_hex(16)`. Hotel's `setup_binding`
    refuses anything that is not
    `hotel-setup-v1-<yyyymmdd>t<hhmmss>z-<8 hex>`, so a conforming identity is
    minted here and returned inside the authorization document; the flow layer
    then records the id the authorization actually carries rather than the one
    it proposed, so exactly one setup id exists anywhere in the chain.
    """
    return f"hotel-setup-v1-{_stamp(at)}-{secrets.token_hex(4)}"


def new_campaign_id(at: datetime | None = None) -> str:
    """Mint a per-run campaign identity the orchestrator's `CAMPAIGN_ID` accepts.

    `SutConfig.campaign_id` is a *study-level* label
    ("hotel-reservation-candidate-pilot-v1", the orchestrator's `STUDY_EPOCH`)
    and can never match `hotel-v1-<yyyymmdd>t<hhmmss>z-<8 hex>`, which
    identifies one one-shot campaign. `run_authorization` below refuses to
    proceed unless the study label it was handed is the orchestrator's own,
    then mints the per-run identity; both are recoverable from the returned
    binding (`studyEpoch` and `campaignId`).
    """
    return f"hotel-v1-{_stamp(at)}-{secrets.token_hex(4)}"


@dataclasses.dataclass(frozen=True)
class RuntimeAdmission:
    """What `authorize_from_files` returns: an admission plus the library's accessor.

    `gate_run_flow.cmd_execute` reads `package.readiness["release"]` off
    whatever `authorize_from_files` returns (a TeaStore-shaped package
    object). `candidate_runtime.admit_runtime` returns a plain admission
    `dict`, which has no such attribute, so this wrapper carries the admission
    verbatim in `document` and exposes the release binding the library asks
    for. Nothing here re-derives or alters the admission.
    """

    document: dict[str, Any]
    readiness: dict[str, Any]


def _json(path: Path, where: str) -> dict[str, Any]:
    return runtime._json_file(Path(path), where)


def _gate_plan() -> dict[str, Any]:
    return _json(GATES_DIR / "gate-plan.json", "GATE-PLAN")


def _gate_setup() -> dict[str, Any]:
    return _json(GATES_DIR / "gate-setup.json", "GATE-SETUP")


def inspect_campaign(plan_dir, framework_commit: str):
    """Hotel's bindings for `framework_commit`.

    `plan_dir` is accepted and unused: the library passes each SUT's
    materialized-plan directory, but Hotel's `Bindings` carry no
    plan-directory concept -- `inspect_bindings` compiles the plan from the
    pinned campaign descriptor and hashes the thirteen controller files named
    in `CONTROLLER_PATHS`, both located relative to the orchestrator's own
    `ROOT`. Dropping the argument is deliberate, not an oversight.
    """
    return runtime.inspect_bindings(framework_commit)


def validate_gate_plan(document, bindings) -> str:
    """Validate the GATE-PLAN document, then return its digest.

    The orchestrator's `validate_gate_plan` returns the validated document;
    the library's contract expects a sha256 (it is used as
    `gate_plan_sha256`). Hashing the *validated* return value, rather than the
    argument, keeps the digest and the validation inseparable.
    """
    return canonical_sha256(runtime.validate_gate_plan(document, bindings))


def setup_authorization(bindings, gate_plan_sha, target_proof, release_manifest, *,
                        setup_id, execution_user, not_before,
                        authorization_deadline) -> dict[str, Any]:
    """Hotel's GATE-SETUP binding, from the GATE-PLAN already recorded on disk.

    Adaptations, each fail-closed:

    * `setup_binding` needs the whole GATE-PLAN *document* (it hashes it),
      not the digest the library passes. The document is re-read from the
      gates directory and its digest is compared against `gate_plan_sha`; a
      mismatch means the file changed under the flow and raises.
    * `execution_user` is compared against the orchestrator's own
      `TARGET["executionUser"]` rather than trusted.
    * `release_manifest` is projected onto exactly the three keys
      `setup_binding` accepts; it refuses any other key set.
    * `setup_id` is re-minted unless the proposed one already satisfies
      `SETUP_ID` -- see `new_setup_id`.
    * `target_proof`, `not_before` and `authorization_deadline` are unused:
      Hotel binds no target-proof document into its setup authorization (the
      operational target is pinned in the orchestrator's `TARGET`), and
      GATE-SETUP freshness is enforced by `validate_gate_setup` against the
      runtime policy's `maximumGateAgeSeconds`, not by a deadline field
      carried in the document.
    """
    gate_plan = _gate_plan()
    if canonical_sha256(gate_plan) != gate_plan_sha:
        raise runtime.GateError("recorded GATE-PLAN differs from the digest under authorization")
    if execution_user != EXECUTION_USER:
        raise runtime.GateError("driver execution user differs from the runtime target")
    if not isinstance(release_manifest, Mapping):
        raise runtime.GateError("release manifest is not an object")
    missing = [
        key for key in ("bundleSha256", "bundleSizeBytes", "manifestCanonicalSha256")
        if key not in release_manifest
    ]
    if missing:
        raise runtime.GateError(f"release manifest is missing bundle identity: {missing}")
    bundle = {
        key: release_manifest[key]
        for key in ("bundleSha256", "bundleSizeBytes", "manifestCanonicalSha256")
    }
    identity = setup_id if runtime.SETUP_ID.fullmatch(str(setup_id)) else new_setup_id()
    return runtime.setup_binding(bindings, gate_plan, bundle, identity)


def validate_readiness(readiness, bindings, *, readiness_parent) -> str:
    """Validate target-produced readiness, then return its digest.

    The orchestrator's `validate_readiness` takes two arguments the contract
    does not pass: the GATE-SETUP document the readiness must be bound to
    (re-read from the gates directory), and the artifact parent under which
    the readiness capture's `readiness-<captureId>/` tree must live -- which
    is exactly the library's `readiness_parent`, only spelled
    `artifact_parent` there.
    """
    return canonical_sha256(
        runtime.validate_readiness(readiness, bindings, _gate_setup(), Path(readiness_parent))
    )


def preflight_captured_at(readiness) -> str:
    """When the target captured this readiness: Hotel spells it `observedAt`.

    The shared library measures its 900-second preflight window against this
    value (`gate_run_flow.derive_run_authorization` / `cmd_execute`); its
    default field name is TeaStore's `capturedAt`, which no Hotel readiness
    document carries. Re-read, not re-derived: `validate_readiness` has
    already checked the same field against the runtime policy's
    `maximumGateAgeSeconds`.
    """
    value = readiness.get("observedAt") if isinstance(readiness, Mapping) else None
    if not isinstance(value, str) or not value:
        raise runtime.GateError("readiness carries no observedAt timestamp")
    return value


def run_authorization(bindings, gate_plan_sha, readiness_sha, *, readiness,
                      campaign_id, not_before, authorization_deadline) -> dict[str, Any]:
    """Hotel's GATE-RUN binding.

    Calls the orchestrator's `_run_binding` directly. That name is private by
    convention, and this crossing is deliberate: `_run_binding` is the only
    place Hotel's run binding is constructed, `validate_gate_run` recomputes
    it and compares, and reimplementing it here would create a second
    construction that could drift from the validator. The alternative --
    adding a public alias inside `candidate_runtime.py` -- would move
    `controllerSha256` and rebind the plan, for no behavioural gain.

    Adaptations, each fail-closed: the GATE-PLAN and GATE-SETUP documents are
    re-read from the gates directory (`_run_binding` hashes both) and the
    supplied digests are checked against them; `campaign_id` must be the
    study-level label and is replaced by a freshly minted per-run identity
    (see `new_campaign_id`); `not_before` is unused, since GATE-RUN's lower
    freshness bound is the runtime policy's clock-skew allowance applied to
    `approvedAt`, not a document field.
    """
    gate_plan = _gate_plan()
    gate_setup = _gate_setup()
    if canonical_sha256(gate_plan) != gate_plan_sha:
        raise runtime.GateError("recorded GATE-PLAN differs from the digest under authorization")
    if canonical_sha256(readiness) != readiness_sha:
        raise runtime.GateError("readiness differs from the digest under authorization")
    if campaign_id != runtime.STUDY_EPOCH:
        raise runtime.GateError(
            "run authorization was handed a campaign identity that is not this study's epoch"
        )
    return runtime._run_binding(
        bindings, gate_plan, gate_setup, readiness, TRANSPORT_ID,
        new_campaign_id(), authorization_deadline,
    )


def authorize_from_files(plan_dir, gate_plan_path, readiness_path, gate_run_path, *,
                         framework_commit: str) -> RuntimeAdmission:
    """Full offline re-admission from the four documents on disk.

    Two adaptations:

    * `admit_runtime` needs the GATE-SETUP path and the readiness *artifact
      parent* as well; the first comes from the gates directory, the second
      is the readiness document's own parent directory.
    * The library's path convention puts readiness at
      `fetched-readiness/readiness.json`, while Hotel's capture retains it at
      `fetched-readiness/readiness-<captureId>/readiness.json` and
      `admit_runtime` refuses any other path (it recomputes the expected one
      from the document's `artifactRoot`). `BoundedSetupController.
      admit_readiness` therefore also writes a plain copy at the library's
      conventional path; this function binds the admission to the *retained*
      document and refuses to proceed unless the copy is byte-identical to
      it, so the copy can never become a second, divergent source of truth.
    """
    readiness_path = Path(readiness_path)
    parent = readiness_path.parent
    convenience = _json(readiness_path, "fetched target-produced readiness")
    retained_path = (
        parent
        / runtime._safe_relative(convenience.get("artifactRoot"), "readiness artifact root")
        / "readiness.json"
    )
    retained = _json(retained_path, "retained target-produced readiness")
    if runtime.canonical_bytes(retained) != runtime.canonical_bytes(convenience):
        raise runtime.GateError(
            "the fetched-readiness copy differs from the retained target-produced receipt"
        )
    admission = runtime.admit_runtime(
        framework_commit, Path(gate_plan_path), GATES_DIR / "gate-setup.json",
        retained_path, parent, Path(gate_run_path),
    )
    receipt = _json(GATES_DIR / "install-receipt.json", "setup install receipt")
    return RuntimeAdmission(document=admission, readiness={"release": receipt})
