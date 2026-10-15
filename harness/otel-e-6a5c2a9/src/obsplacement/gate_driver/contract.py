"""The SUT module interface contract, and the per-SUT configuration object.

Reading the four canonical drivers (scratchpad/gate-drivers/{gate_setup,
gate_run,campaign_setup,campaign_status}.py) end to end shows every
SUT-specific fact enters through exactly two loaded modules -- here called
the *adapter* (bindings, sentence derivation, document validation --
TeaStore's `candidate_runtime_adapter.py`) and the *transport* (everything
that talks to the target host -- TeaStore's `candidate_transport.py`) -- plus
one attribute sourced from a third, the *installer*
(`RELEASE_BINDING_KEYS`, see `module_loader.load_binding_keys`).

This module defines that boundary as `typing.Protocol` classes (documentation
and static-checking aid) plus small `check_*_contract` runtime probes (fail
closed with `ContractViolation` and the exact missing member names, rather
than failing 40 lines later with an opaque `AttributeError` inside a
half-finished mutation). A SUT integrator -- e.g. whoever finishes Hotel's
multi-cell orchestrator -- implements these members however they like
(one module or three, any internal structure); the contract is the surface,
not the shape behind it.

`SutConfig` is the "thin per-SUT configuration" the rest of this library is
parameterized by. Every field here corresponds to something a canonical
driver currently hardcodes as a module-level constant (ROOT, FRAMEWORK,
PLAN_DIR, GATES, CAMPAIGN_ID, STUDY, CHANGE, "fb14srv5", "root", "stig", ...).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .errors import ContractViolation
from .freshness import PREFLIGHT_MAX_AGE_SECONDS

__all__ = [
    "SutConfig",
    "AdapterProtocol",
    "TransportProtocol",
    "CampaignIdentity",
    "campaign_identity",
    "check_adapter_contract",
    "check_transport_contract",
    "git_head_commit",
]


@runtime_checkable
class AdapterProtocol(Protocol):
    """What the driver library needs from a SUT's "candidate_runtime_adapter"-shaped module.

    Every method here is called, by name, from the canonical drivers:
      - inspect_campaign        gate_setup.py:66, gate_run.py:96, campaign_setup.py:163
      - plan_binding            gate_setup.py:118
      - validate_gate_plan      gate_setup.py:122
      - expected_gate_plan_text gate_setup.py:94, :101
      - setup_authorization     gate_setup.py:130
      - expected_gate_setup_text gate_setup.py:143, :151
      - validate_readiness      gate_run.py:79
      - run_authorization       gate_run.py:83
      - expected_gate_run_text  gate_run.py:138, :147
      - authorize_from_files    gate_run.py:169
      - canonical_sha256        used throughout for document digests
      - PLAN_KIND / SETUP_KIND / RUN_KIND   document "kind" tags
      - EXECUTION_USER          the user the SUT's services execute as
    `canonical_sha256` may simply be `hashing.canonical_sha256` re-exported;
    it is required on the contract because every canonical driver calls it as
    `adapter.canonical_sha256`, not as a free function.
    """

    PLAN_KIND: str
    SETUP_KIND: str
    RUN_KIND: str
    EXECUTION_USER: str

    def inspect_campaign(self, plan_dir: Path, framework_commit: str): ...
    def plan_binding(self, bindings): ...
    def validate_gate_plan(self, document: dict, bindings) -> str: ...
    def expected_gate_plan_text(self, bindings) -> str: ...
    def setup_authorization(self, bindings, gate_plan_sha, target_proof,
                             release_manifest, *, setup_id, execution_user,
                             not_before, authorization_deadline) -> dict: ...
    def expected_gate_setup_text(self, authorization: dict) -> str: ...
    def validate_readiness(self, readiness: dict, bindings, *, readiness_parent: Path) -> str: ...
    def run_authorization(self, bindings, gate_plan_sha, readiness_sha, *,
                           readiness, campaign_id, not_before,
                           authorization_deadline) -> dict: ...
    def expected_gate_run_text(self, authorization: dict) -> str: ...
    def authorize_from_files(self, plan_dir, gate_plan_path, readiness_path,
                              gate_run_path, *, framework_commit): ...
    def canonical_sha256(self, document) -> str: ...


@runtime_checkable
class TransportProtocol(Protocol):
    """What the driver library needs from a SUT's "candidate_transport"-shaped module.

    Traced back to: subprocess_runner (every *_runner wrapper in the
    canonical scripts), build_release_bundle (gate_setup.py:86,
    campaign_setup.py:305), build_capture_spec (gate_setup.py:234,
    campaign_setup.py:379), build_runtime_package (gate_run.py:177),
    BoundedSetupController.{probe,setup,admit_readiness} (gate_setup.py:74,
    :193-203, :255-267), BoundedCampaignController.{launch,_status}
    (gate_run.py:183-192, :378-392). `remote_output_exists`, `remote_precheck`,
    and `remote_status` generalize the ad hoc `ssh ... test -e` check and the
    remote-python-snippet replay inlined in gate_run.py's cmd_dryrun
    (gate_run.py:284-393) into three named contract points -- see
    flows/gate_run_flow.py's docstring for why the actual remote mechanics
    stay behind the contract instead of being reproduced as generic string
    templates here.
    """

    def subprocess_runner(self, argv, data=None): ...
    def build_release_bundle(self, bindings, *, bundle_path, manifest_path) -> dict: ...
    def build_capture_spec(self, bindings, release_binding, *, archive_path) -> str: ...
    def build_runtime_package(self, package) -> dict: ...
    def remote_output_exists(self, remote_input: dict) -> bool: ...
    def remote_precheck(self, package, remote_input: dict) -> dict: ...
    def remote_status(self, remote_input: dict, package_sha256: str) -> dict: ...

    # Constructible controllers -- BoundedSetupController(bindings=..., runner=...)
    # exposes .probe() / .setup(...) / .admit_readiness(...) (gate_setup.py:74,
    # :193-203, :255-267); BoundedCampaignController(framework_commit=...,
    # release_binding=..., runner=...) exposes .launch(...) (gate_run.py:
    # 183-192). Only existence is checked here (like every other contract
    # member) -- constructor and method signatures are enforced by use, the
    # same way the canonical drivers themselves never introspect signatures.
    BoundedSetupController: type
    BoundedCampaignController: type


@dataclass(frozen=True)
class CampaignIdentity:
    """The three binding facts SETUP-CAMPAIGN pins, independent of a SUT's field names."""

    descriptor_sha256: str
    plan_sha256: str
    run_count: int


def campaign_identity(bindings) -> CampaignIdentity:
    """Read campaign identity off whatever `adapter.inspect_campaign` returned.

    Two binding shapes exist today and both are legitimate: TeaStore's
    `CampaignBindings` carries `plan_sha256` and the tuple `run_ids`; Hotel's
    `Bindings` carries `compiled_plan_sha256` and the integer `run_count`
    (its 24 cells have no stable run-id vocabulary before the schedule is
    compiled). `campaign_authorization` used to read TeaStore's names
    directly, so `propose-campaign` raised `AttributeError` on Hotel before
    any sentence could be derived. Fails closed with `ContractViolation`
    naming the missing member when neither spelling is present -- never
    guesses a run count.
    """
    descriptor = getattr(bindings, "descriptor_sha256", None)
    plan = getattr(bindings, "plan_sha256", None)
    if plan is None:
        plan = getattr(bindings, "compiled_plan_sha256", None)
    run_ids = getattr(bindings, "run_ids", None)
    run_count = len(set(run_ids)) if run_ids is not None else getattr(bindings, "run_count", None)
    missing = tuple(
        name for name, value in (
            ("descriptor_sha256", descriptor),
            ("plan_sha256 | compiled_plan_sha256", plan),
            ("run_ids | run_count", run_count),
        ) if value is None
    )
    if missing:
        raise ContractViolation("campaign bindings", missing)
    return CampaignIdentity(str(descriptor), str(plan), int(run_count))


def check_adapter_contract(module, *, label: str = "adapter module") -> None:
    """Fail closed with `ContractViolation` naming every missing member."""
    required = (
        "PLAN_KIND", "SETUP_KIND", "RUN_KIND", "EXECUTION_USER",
        "inspect_campaign", "plan_binding", "validate_gate_plan",
        "expected_gate_plan_text", "setup_authorization",
        "expected_gate_setup_text", "validate_readiness", "run_authorization",
        "expected_gate_run_text", "authorize_from_files", "canonical_sha256",
    )
    missing = tuple(name for name in required if not hasattr(module, name))
    if missing:
        raise ContractViolation(label, missing)


def check_transport_contract(module, *, label: str = "transport module") -> None:
    """Fail closed with `ContractViolation` naming every missing member."""
    required = (
        "subprocess_runner", "build_release_bundle", "build_capture_spec",
        "build_runtime_package", "remote_output_exists", "remote_precheck",
        "remote_status", "BoundedSetupController", "BoundedCampaignController",
    )
    missing = tuple(name for name in required if not hasattr(module, name))
    if missing:
        raise ContractViolation(label, missing)


def git_head_commit(root: Path) -> str:
    """The framework commit, read from Git -- never hand-maintained.

    Generalizes `head_commit()` (gate_run.py:51-56, campaign_setup.py:65-71,
    both identical). gate_setup.py is the one canonical script that instead
    hardcodes a module-level `FRAMEWORK` constant updated once per
    gate-rebinding commit -- callers that need that exact behaviour (pinning
    the framework commit used to derive the GATE-PLAN sentence to the commit
    it was authored against, independent of what HEAD has moved to since)
    should pass their own pinned string instead of calling this function; the
    two are deliberately different tools; see gate_setup.py:23-24.
    """
    result = subprocess.run(
        ("git", "-C", str(root), "rev-parse", "HEAD"),
        check=True, capture_output=True,
    )
    return result.stdout.decode("ascii").strip()


@dataclass(frozen=True)
class SutConfig:
    """The thin per-SUT configuration this library is parameterized by.

    Every field replaces a module-level constant currently hardcoded in the
    canonical drivers. None of it is optional-with-a-guessed-default for the
    fields that name a real host/user/identifier -- a SUT integrator must
    supply them explicitly, the same way a new gate-rebinding event requires
    editing the one hardcoded line in gate_setup.py today.
    """

    # Identity
    slug: str                      # e.g. "teastore", "hotel-reservation"
    study: str                     # STUDY, e.g. "teastore-candidate-pilot-v1"
    change: str                    # CHANGE, e.g. "admit-teastore-candidate-runtime"
    campaign_id: str               # CAMPAIGN_ID

    # Filesystem layout (all under the SUT's pinned runtime worktree)
    root: Path                     # ROOT: the runtime worktree this config drives
    plan_dir: Path                 # PLAN_DIR
    gates_dir: Path                # GATES

    # SUT module locations, relative to `root` -- see AdapterProtocol /
    # TransportProtocol. May point at the same file if a SUT combines roles.
    adapter_module: str
    transport_module: str
    installer_module: str

    # Target environment
    target_host: str               # e.g. "fb14srv5"
    transport_user: str            # the ssh login used to reach target_host, e.g. "root"
    execution_user: str            # the user the SUT's services execute as, e.g. "stig" / "fhuebscher"

    # Posture vocabulary this SUT actually supports (fail-closed check point
    # for SUTs like Hotel where "none"/"selected" are structurally unsupported)
    supported_postures: frozenset

    approved_by: str = "Florian Huebscher"
    setup_window_hours: int = 6
    run_window_hours: int = 11
    setup_campaign_window_hours: int = 168  # D22 (user, 2026-09-12): one typed sentence per SUT per week; was 12
    preflight_max_age_seconds: int = PREFLIGHT_MAX_AGE_SECONDS
    ssh_connect_timeout_seconds: int = 15

    def __post_init__(self):
        if not self.supported_postures:
            raise ValueError(f"{self.slug}: supported_postures must be non-empty")

    def validate_postures(self, postures) -> None:
        """Fail closed if any requested posture is outside this SUT's supported set.

        Exists because Hotel's posture shape is structurally different from
        TeaStore's: "none"/"selected" are `unsupported` there (no
        upstream service-level source guard), not merely untested. A generic
        driver that assumed TeaStore's {none, selected, full} vocabulary
        would silently accept an unsupported Hotel posture instead of
        refusing it before a typed sentence is even derived.
        """
        requested = frozenset(postures)
        unsupported = requested - self.supported_postures
        if unsupported:
            raise ValueError(
                f"{self.slug}: posture(s) {sorted(unsupported)} unsupported; "
                f"supported={sorted(self.supported_postures)}"
            )
