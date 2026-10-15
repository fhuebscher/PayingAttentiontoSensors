"""Shared fakes for the gate_driver test suite.

These fakes exist purely so the flow layer (gate_setup_flow.py,
gate_run_flow.py, campaign_setup_flow.py, campaign_status_flow.py) can be
exercised end to end without any real SUT adapter/transport module -- none of
TeaStore's candidate_runtime_adapter.py / candidate_transport.py exist in
this checkout (they live only in the separate runtime worktree). They
satisfy `obsplacement.gate_driver.contract.AdapterProtocol` /
`TransportProtocol` well enough for `check_adapter_contract` /
`check_transport_contract` to pass, and are deliberately simple rather than
faithful to any one SUT's real business logic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from obsplacement.gate_driver.contract import SutConfig
from obsplacement.gate_driver.freshness import now, stamp
from obsplacement.gate_driver.hashing import canonical_sha256


@dataclass
class FakeBindings:
    framework_commit: str
    run_ids: tuple = ("a01", "a02", "a03")
    descriptor_sha256: str = "desc" + "0" * 60
    plan_sha256: str = "plan" + "0" * 60
    framework_tree: str = "tree" + "0" * 60
    cells: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if not self.cells:
            self.cells = tuple(self.run_ids)


@dataclass
class FakePackage:
    readiness: dict
    validated_at: object


class FakeCommandResult:
    def __init__(self, returncode=0, stdout=b"ok", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeGatePlanRejected(Exception):
    """Marker exception a test uses to simulate a corrupted-but-well-formed
    gate-plan.json that `validate_gate_plan` must catch, as opposed to a
    plain `canonical_sha256` re-hash that would hash it fine either way."""


class FakeAdapter:
    """Satisfies AdapterProtocol with deterministic, inspectable behavior."""

    PLAN_KIND = "fake-candidate-gate-plan-v1"
    SETUP_KIND = "fake-candidate-gate-setup-v1"
    RUN_KIND = "fake-candidate-gate-run-v1"
    EXECUTION_USER = "fakeuser"

    def __init__(self):
        self.calls = []
        self.reject_gate_plan_reason: str | None = None

    def inspect_campaign(self, plan_dir, framework_commit):
        self.calls.append(("inspect_campaign", framework_commit))
        return FakeBindings(framework_commit=framework_commit)

    def plan_binding(self, bindings):
        return {"frameworkCommit": bindings.framework_commit, "runs": list(bindings.run_ids)}

    def validate_gate_plan(self, document, bindings):
        if self.reject_gate_plan_reason is not None:
            raise FakeGatePlanRejected(self.reject_gate_plan_reason)
        return canonical_sha256(document)

    def expected_gate_plan_text(self, bindings) -> str:
        return (f"APPROVE GATE-PLAN framework={bindings.framework_commit} "
                f"plan={bindings.plan_sha256}")

    def setup_authorization(self, bindings, gate_plan_sha, target_proof,
                             release_manifest, *, setup_id, execution_user,
                             not_before, authorization_deadline) -> dict:
        return {
            "setupId": setup_id,
            "releaseRoot": f"/releases/{setup_id}",
            "executionUser": execution_user,
            "notBefore": not_before,
            "authorizationDeadline": authorization_deadline,
            "gatePlanSha256": gate_plan_sha,
            "experimentalCellsAuthorized": 0,
        }

    def expected_gate_setup_text(self, authorization: dict) -> str:
        return (f"APPROVE GATE-SETUP setupId={authorization['setupId']} "
                f"deadline={authorization['authorizationDeadline']}")

    def validate_readiness(self, readiness, bindings, *, readiness_parent) -> str:
        return canonical_sha256(readiness)

    def run_authorization(self, bindings, gate_plan_sha, readiness_sha, *,
                           readiness, campaign_id, not_before,
                           authorization_deadline) -> dict:
        return {
            "campaignId": campaign_id,
            "runCount": len(bindings.run_ids),
            "authorizedRunIds": list(bindings.run_ids),
            "oneShot": True,
            "retryAllowed": False,
            "readinessSha256": readiness_sha,
            "runtimePreflightCapturedAt": readiness.get("capturedAt"),
            "notBefore": not_before,
            "authorizationDeadline": authorization_deadline,
        }

    def expected_gate_run_text(self, authorization: dict) -> str:
        return (f"APPROVE GATE-RUN campaign={authorization['campaignId']} "
                f"deadline={authorization['authorizationDeadline']}")

    def authorize_from_files(self, plan_dir, gate_plan_path, readiness_path,
                              gate_run_path, *, framework_commit) -> FakePackage:
        readiness = json.loads(Path(readiness_path).read_text())
        release = dict(readiness.get("release") or {})
        release.setdefault("resultsRoot", "/results/fake")
        release.setdefault("exclusiveLeasePath", "/lease/fake")
        release.setdefault("releaseRoot", "/releases/fake")
        return FakePackage(readiness={"release": release}, validated_at=now())

    def canonical_sha256(self, document) -> str:
        return canonical_sha256(document)


class FakeSetupController:
    def __init__(self, bindings, runner=None):
        self.bindings = bindings
        self.runner = runner

    def probe(self) -> dict:
        return {"capturedAt": stamp(now()), "candidateV4Root": {"exists": True}}

    def setup(self, *, gate_plan_path, target_proof_path, release_manifest_path,
              gate_setup_path, bundle_path) -> dict:
        if self.runner is not None:
            self.runner(["fake-install", str(gate_setup_path)])
        return {
            "releaseRoot": "/releases/fake",
            "imageBuildReceiptSha256": "fakeimagesha",
            "bindingKeyA": "valueA",
            "bindingKeyB": "valueB",
        }

    def admit_readiness(self, *, archive_path, release_binding, local_output) -> dict:
        if self.runner is not None:
            self.runner(["fake-readiness", str(archive_path)])
        local_output.mkdir(parents=True, exist_ok=True)
        readiness_document = {
            "capturedAt": stamp(now()),
            "release": release_binding,
            "readinessCanonicalSha256": "fakereadinesssha",
        }
        (local_output / "readiness.json").write_text(json.dumps(readiness_document))
        return {"readinessCanonicalSha256": "fakereadinesssha"}


class FakeCampaignController:
    def __init__(self, framework_commit, release_binding, runner=None):
        self.framework_commit = framework_commit
        self.release_binding = release_binding
        self.runner = runner

    def launch(self, package_path, *, local_output) -> dict:
        if self.runner is not None:
            self.runner(["fake-launch", str(package_path)])
        return {"state": "running", "systemdState": {"activeState": "active"}}


class FakeTransport:
    """Satisfies TransportProtocol. Toggle failure modes via constructor flags."""

    BoundedSetupController = FakeSetupController
    BoundedCampaignController = FakeCampaignController

    def __init__(self, *, remote_output_exists=False, precheck_ok=True,
                 precheck_detail="", status_document=None):
        self.calls = []
        self._remote_output_exists = remote_output_exists
        self._precheck_ok = precheck_ok
        self._precheck_detail = precheck_detail
        self._status_document = status_document or {
            "state": "running", "systemdState": {"activeState": "active"},
            "terminalExists": False, "abortExists": False,
        }

    def subprocess_runner(self, argv, data=None):
        self.calls.append(tuple(argv))
        return FakeCommandResult()

    def build_release_bundle(self, bindings, *, bundle_path, manifest_path) -> dict:
        bundle_path.write_bytes(b"fake-bundle")
        manifest = {"bundleSha256": "fakebundlesha", "bundleBytes": len(b"fake-bundle")}
        manifest_path.write_text(json.dumps(manifest))
        return manifest

    def build_capture_spec(self, bindings, release_binding, *, archive_path) -> str:
        archive_path.write_bytes(b"fake-capture-spec")
        return "fakecapturespecsha"

    def build_runtime_package(self, package) -> dict:
        return {
            "kind": "fake-candidate-runtime-package-v1",
            "campaignId": "fake-campaign-v1",
            "releaseRoot": package.readiness["release"].get("releaseRoot", "/releases/fake"),
            "resultsRoot": package.readiness["release"]["resultsRoot"],
            "cells": ["a01", "a02", "a03"],
            "setupId": "fakesetupid",
            "releaseBindingSha256": canonical_sha256(package.readiness["release"]),
        }

    def remote_output_exists(self, remote_input: dict) -> bool:
        return self._remote_output_exists

    def remote_precheck(self, package, remote_input: dict) -> dict:
        return {"ok": self._precheck_ok, "detail": self._precheck_detail}

    def remote_status(self, remote_input: dict, package_sha256: str) -> dict:
        return self._status_document


def make_config(tmp_path: Path, **overrides) -> SutConfig:
    root = overrides.pop("root", tmp_path / "runtime-root")
    root.mkdir(parents=True, exist_ok=True)
    defaults = dict(
        slug="fake-sut",
        study="fake-sut-candidate-pilot-v1",
        change="admit-fake-sut-candidate-runtime",
        campaign_id="fake-sut-candidate-pilot-v1",
        root=root,
        plan_dir=root / ".local/candidate-v4/fake-sut/plan-0000",
        gates_dir=tmp_path / "gates",
        adapter_module="modules/fake-sut/execution/candidate_runtime_adapter.py",
        transport_module="modules/fake-sut/execution/candidate_transport.py",
        installer_module="modules/fake-sut/execution/candidate_release_installer.py",
        target_host="fbtest1",
        transport_user="root",
        execution_user="fakeuser",
        supported_postures=frozenset({"none", "selected", "full"}),
    )
    defaults.update(overrides)
    return SutConfig(**defaults)
