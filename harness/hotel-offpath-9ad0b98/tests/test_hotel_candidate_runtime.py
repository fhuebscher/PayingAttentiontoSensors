from __future__ import annotations

import copy
import dataclasses
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODULE = ROOT / "modules/hotel-reservation"


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime = load("hotel_candidate_runtime_test", "modules/hotel-reservation/execution/candidate_runtime.py")
cell = load("hotel_candidate_cell_test", "modules/hotel-reservation/execution/candidate_cell.py")
workload = load("hotel_candidate_workload_test", "modules/hotel-reservation/workload/candidate_search.py")
resources = load("hotel_candidate_resources_test", "modules/hotel-reservation/collectors/candidate_resources.py")
witness = load("hotel_candidate_witness_test", "modules/hotel-reservation/witness/candidate_evidence.py")
terminal = load("hotel_candidate_terminal_test", "modules/hotel-reservation/validation/candidate_terminal.py")
fault = load("hotel_candidate_fault_test", "modules/hotel-reservation/faults/compose_pause.py")
materialize = load("hotel_candidate_materialize_test", "modules/hotel-reservation/candidate_materialize.py")
system = load("hotel_candidate_system_test", "modules/hotel-reservation/collectors/system_state.py")
lmt_faults = load("hotel_candidate_lmt_faults_test", "modules/hotel-reservation/faults/lmt_faults.py")
module_audit = load("hotel_candidate_module_audit_test", "src/obsplacement/module_audit.py")


def bindings() -> object:
    ceiling = runtime.posture_ceiling()
    return runtime.Bindings(
        framework_commit="a" * 40,
        framework_tree="b" * 40,
        descriptor_sha256="c" * 64,
        compiled_plan_sha256="9877376014b7fcd6fb2fc8f5b25b4e3e9bcae00884e49f5437923520deb2c484",
        runtime_policy_sha256="d" * 64,
        controller_sha256={name: hashlib.sha256(name.encode()).hexdigest() for name in runtime.CONTROLLER_PATHS},
        run_count=24,
        unsupported_postures=tuple(runtime.unsupported_posture_ids(ceiling)),
        source_cost_comparison_state=ceiling["sourceCostComparisonState"],
    )


def admission(root: Path, *, transport_id: str = "ssh-compose") -> dict:
    body = {
        "schemaVersion": 1,
        "kind": runtime.ADMISSION_KIND,
        "bindings": {
            "frameworkCommit": "a" * 40,
            "frameworkTree": "b" * 40,
            "descriptorCanonicalSha256": "c" * 64,
            "compiledPlanCanonicalSha256": runtime._load_compiler().EXPECTED_PLAN_SHA256,
            "runtimePolicyCanonicalSha256": "d" * 64,
            "controllerSha256": {},
            "runCount": runtime.CELL_COUNT,
            "maximumEvidenceLabel": "candidate-evidence",
            "canonical": False,
            "absoluteCostOrLatencyCanonical": False,
            "nuisanceRecordedEveryCell": list(runtime.NUISANCE_FACTORS),
            "unsupportedPostures": runtime.unsupported_posture_ids(runtime.posture_ceiling()),
            "sourceCostComparisonState": "unsupported",
            "targetContract": copy.deepcopy(runtime.TARGET_PROJECTION),
            "gatePlanCanonicalSha256": "e" * 64,
            "gateSetupCanonicalSha256": "2" * 64,
            "readinessCanonicalSha256": "f" * 64,
            "readinessCaptureId": "hotel-readiness-v1-20260830t000000z-deadbeef",
            "readinessObservedAt": "2026-08-30T00:00:00Z",
            "transportId": transport_id,
            "target": "fb14srv4",
            "transportUser": "root",
            "setupUser": "root",
            "executionUser": "fhuebscher",
            "executionUid": 1007,
            "executionGid": 1007,
            "supplementalGids": [27, 998],
            "dockerGid": 998,
            "dockerVersion": "29.6.1",
            "authorizedParent": runtime.TARGET["authorizedParent"],
            "releaseParent": runtime.TARGET["releaseParent"],
            "checkoutRoot": runtime.TARGET["checkoutRoot"],
            "campaignId": "hotel-v1-20260830t010203z-deadbeef",
            "artifactRoot": str(root),
            "artifactParent": str(root.parent),
            "leaseRoot": str(root.parent),
            "leasePath": str(root.parent / ".lease"),
            "controlRoot": runtime.TARGET["controlRoot"],
            "projectPrefix": "hotel_candidate_v4",
            "ports": {"frontend": 35005, "jaegerQuery": 36685},
            "foreignProject": None,
            "bundleSha256": "3" * 64,
            "installationManifestCanonicalSha256": "4" * 64,
            "deadline": "2099-01-01T00:00:00Z",
            "maximumWallSeconds": 18000,
            "cleanupReserveSeconds": 300,
            "stopCondition": "first-invalid-cell-or-deadline-before-cleanup-reserve",
            "cleanupActions": [
                "unpause-owned-fault-target-if-needed",
                "docker-compose-down-volumes-remove-orphans",
                "verify-zero-owned-containers-networks-volumes",
                "release-exact-campaign-lease-even-if-cleanup-fails",
            ],
        },
        "gatePlanCanonicalSha256": "e" * 64,
        "gateSetupCanonicalSha256": "2" * 64,
        "readinessCanonicalSha256": "f" * 64,
        "gateRunCanonicalSha256": "1" * 64,
        "runtimeAuthorized": True,
        "externalMutationAuthorized": True,
        "promotionAuthorized": False,
        "issuedAt": "2026-08-30T00:00:00Z",
    }
    return {**body, "admissionCanonicalSha256": runtime.canonical_sha256(body)}


def _journal_digests(document: dict) -> dict:
    """The two digests `replay_runtime_journal` binds every row to."""
    return {
        "compiled_plan_sha256": document["bindings"]["compiledPlanCanonicalSha256"],
        "admission_sha256": document["admissionCanonicalSha256"],
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def root_observation(admission_document: dict) -> dict:
    projects = [row["project"] for row in runtime.cell_contracts(admission_document)]
    return {
        "schemaVersion": 1, "kind": "hotel-srv4-root-terminal-observation-v1",
        "campaignId": admission_document["bindings"]["campaignId"],
        "observedAt": "2026-08-30T01:00:00Z", "projectsChecked": projects,
        "state": "observed",
        "ownedResourcesRemaining": {
            project: {"containers": [], "networks": [], "volumes": []}
            for project in projects
        },
        "failures": [], "foreignProjectMutated": False,
    }


def sealed_terminal_archive(campaign_id: str, admission_document: dict, name: str, terminal_document: dict) -> bytes:
    observation = root_observation(admission_document)
    payloads = {
        "runtime-admission.json": runtime.canonical_bytes(admission_document) + b"\n",
        name: runtime.canonical_bytes(terminal_document) + b"\n",
        "root-cleanup-observation.json": runtime.canonical_bytes(observation) + b"\n",
    }
    entries = [
        {"tree": "control", "path": path, "size": len(payload),
         "sha256": hashlib.sha256(payload).hexdigest()}
        for path, payload in sorted(payloads.items())
    ]
    seal_body = {
        "schemaVersion": 1, "kind": "hotel-srv4-terminal-tree-seal-v1",
        "campaignId": campaign_id, "sealedAt": "2026-08-30T01:00:00Z",
        "entries": entries, "entriesCanonicalSha256": runtime.canonical_sha256(entries),
        "rootObservationSha256": runtime.canonical_sha256(observation),
        "ownedResourcesState": "observed",
        "ownedResourcesRemaining": observation["ownedResourcesRemaining"],
    }
    payloads["terminal-tree-seal.json"] = runtime.canonical_bytes({
        **seal_body, "sealCanonicalSha256": runtime.canonical_sha256(seal_body),
    }) + b"\n"
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        for path, payload in payloads.items():
            member = tarfile.TarInfo(f"control/{campaign_id}/{path}")
            member.size = len(payload)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(payload))
    return archive_buffer.getvalue()


def readiness_facts(seam: str, setup: dict) -> dict:
    target = runtime.TARGET
    setup_binding = setup["bindings"]
    facts = {
        "installed-bundle-bytes": {
            "bundleSha256": setup_binding["bundleSha256"],
            "bundleSizeBytes": setup_binding["bundleSizeBytes"],
            "manifestCanonicalSha256": setup_binding["manifestCanonicalSha256"],
            "expectedEntriesSha256": "a" * 64,
            "observedEntriesSha256": "a" * 64,
            "installedFileCount": 42,
        },
        "target-execution-identity": {
            "transportUser": "root", "setupUser": "root",
            "executionUser": "fhuebscher", "uid": 1007, "gid": 1007,
            "supplementaryGids": [27, 998], "accountMutationObserved": False,
        },
        "docker-runtime-and-membership": {
            "serverVersion": "29.6.1", "socketGid": 998,
            "executionUserGids": [998, 1007],
            "daemonReachableAsExecutionUser": True, "composeAvailable": True,
        },
        "campaign-path-ownership": {
            "paths": {key: target[key] for key in (
                "authorizedParent", "releaseParent", "checkoutRoot", "artifactParent", "leaseRoot",
                "leasePath", "controlRoot",
            )},
            "ownership": [
                {"path": target["releaseParent"], "uid": 0, "gid": 0,
                 "traversable": True, "writable": False, "symlink": False},
                {"path": target["checkoutRoot"], "uid": 0, "gid": 0,
                 "traversable": True, "writable": False, "symlink": False},
                {"path": target["artifactParent"], "uid": 1007, "gid": 1007,
                 "traversable": True, "writable": True, "symlink": False},
                {"path": target["leaseRoot"], "uid": 0, "gid": 0,
                 "traversable": True, "writable": False, "symlink": False},
                {"path": target["controlRoot"], "uid": 0, "gid": 0,
                 "traversable": False, "writable": False, "symlink": False},
            ],
            "preSetupAbsent": [target["releaseParent"], target["artifactParent"], target["leasePath"]],
            "leasePathAbsent": True,
        },
        "fixed-ports-free": {"observations": [
            {"port": 35005, "listeners": []}, {"port": 36685, "listeners": []},
        ]},
        "foreign-project-preserved": {
            # Host condition v2 (2026-09-21): verified absence of any foreign
            # Compose project or container, recorded before and after.
            "project": None, "beforeFingerprint": "b" * 64,
            "afterFingerprint": "b" * 64,
            "configPath": None,
            "beforeStateCounts": {},
            "afterStateCounts": {},
            "beforeResources": [],
            "afterResources": [], "mutationActions": [],
        },
        "target-runner-executable-replay": {
            "argv": [
                "/usr/sbin/runuser", "--user", "fhuebscher", "--",
                "/usr/bin/python3", "-I",
                target["checkoutRoot"] + "/modules/hotel-reservation/execution/candidate_runtime.py",
                "--target-self-check", setup_binding["manifestCanonicalSha256"],
            ],
            "returnCode": 0,
            "stdout": {
                "kind": "hotel-srv4-target-self-check-v1", "status": "pass",
                "manifestCanonicalSha256": setup_binding["manifestCanonicalSha256"],
                "executionUid": 1007, "executionGid": 1007,
            },
            "stderr": "",
        },
        "terminal-validator-executable-replay": {
            "argv": [
                "/usr/sbin/runuser", "--user", "fhuebscher", "--",
                "/usr/bin/python3", "-I",
                target["checkoutRoot"] + "/modules/hotel-reservation/validation/candidate_terminal.py",
                "--self-check",
            ],
            "returnCode": 0,
            "stdout": {"kind": "hotel-candidate-terminal-self-check-v1", "status": "pass"},
            "stderr": "",
        },
    }[seam]
    return {"schemaVersion": 1, "kind": "hotel-srv4-readiness-evidence-v1",
            "checkId": seam, "facts": facts}


def planted_readiness_defect(seam: str, setup: dict) -> dict:
    value = readiness_facts(seam, setup)
    facts = value["facts"]
    if seam == "installed-bundle-bytes": facts["observedEntriesSha256"] = "0" * 64
    elif seam == "target-execution-identity": facts["uid"] = 1008
    elif seam == "docker-runtime-and-membership": facts["serverVersion"] = "29.6.0"
    elif seam == "campaign-path-ownership": facts["ownership"][0]["symlink"] = True
    elif seam == "fixed-ports-free": facts["observations"][0]["listeners"] = ["foreign"]
    elif seam == "foreign-project-preserved": facts["afterFingerprint"] = "0" * 64
    elif seam == "target-runner-executable-replay": facts["returnCode"] = 1
    else: facts["returnCode"] = 1
    return value


def test_runtime_policy_and_exact_cell_contracts(tmp_path: Path):
    policy = runtime._validate_policy(runtime._json_file(runtime.POLICY, "policy"))
    # The cell budget is the frozen compiler's TOTAL_RUNS, never a literal.
    assert policy["maximumCells"] == runtime.CELL_COUNT == runtime._load_compiler().TOTAL_RUNS
    assert policy["ports"] == {"frontend": 35005, "jaegerQuery": 36685}
    assert policy["allowedTransports"] == {"ssh-compose": runtime.TARGET}
    assert policy["targetProjection"] == runtime.TARGET_PROJECTION
    assert set(runtime.TARGET_PROJECTION) == {
        "status", "host", "transportUsers", "setupUsers", "executionIdentities",
        "releaseParent", "artifactParent", "leasePath", "projectPrefix",
        "reservedPorts", "freshReadinessAfter", "readinessRequirements",
    }
    assert policy["claimCeiling"]["nuisanceRecordedEveryCell"] == list(runtime.NUISANCE_FACTORS)
    assert policy["foreignProject"] is None
    assert policy["hostCondition"]["poolingBoundary"] == runtime.POOLING_BOUNDARY
    assert "must not be pooled" in runtime.POOLING_BOUNDARY
    contracts = runtime.cell_contracts(admission(tmp_path / "campaign"))
    assert len(contracts) == len({row["runId"] for row in contracts}) == runtime.CELL_COUNT
    assert len({row["project"] for row in contracts}) == runtime.CELL_COUNT
    assert {row["fault"] for row in contracts} == {
        None, "search-pause", "reservation-pause", "profile-cpu-throttle", "rate-net-delay",
    }
    # LMT+S pilot: 80 cells, each (fault, posture) pair 4 times, never sample-zero.
    assert runtime.CELL_COUNT == 80
    assert {row["runKey"]["posture"] for row in contracts} == {"none", "metrics", "selected", "full"}
    for fault_id in (None, "search-pause", "reservation-pause", "profile-cpu-throttle", "rate-net-delay"):
        for posture in ("none", "metrics", "selected", "full"):
            assert sum(
                1 for row in contracts
                if row["fault"] == fault_id and row["runKey"]["posture"] == posture
            ) == 4
    assert all(row["canonical"] is False and row["promotionAuthorized"] is False for row in contracts)
    assert all(row["nuisanceFactors"] == list(runtime.NUISANCE_FACTORS) for row in contracts)
    assert all(row["foreignProject"] is None for row in contracts)


def test_every_hotel_extension_is_classified():
    report = module_audit.audit(MODULE)
    assert report["verdict"] == "pass"
    assert report["unclassified_files"] == []
    assert report["stale_ledger_entries"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("runtimeAuthorized", False),
        ("externalMutationAuthorized", False),
        ("promotionAuthorized", True),
        ("admissionCanonicalSha256", "0" * 64),
    ],
)
def test_cell_contracts_watch_admission_authority_defects(tmp_path: Path, field: str, value: object):
    document = admission(tmp_path / "campaign")
    document[field] = value
    with pytest.raises(runtime.GateError):
        runtime.cell_contracts(document)


def test_typed_plan_receipt_is_exact_and_cannot_authorize_runtime():
    current = bindings()
    document = {
        "schemaVersion": 1,
        "kind": runtime.PLAN_KIND,
        "gate": "GATE-PLAN",
        "decision": "approve-exact-plan",
        "typedApproval": runtime.expected_gate_plan_text(current),
        "approvedBy": "human-reviewer",
        "approvedAt": "2026-08-29T23:00:00Z",
        "bindings": runtime.plan_binding(current),
        "runtimeAuthorized": False,
        "setupAuthorized": False,
        "externalMutationAuthorized": False,
        "promotionAuthorized": False,
    }
    assert runtime.validate_gate_plan(document, current) is document
    attacked = copy.deepcopy(document)
    attacked["runtimeAuthorized"] = True
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_plan(attacked, current)


def test_gate_setup_is_distinct_fresh_one_shot_and_cannot_authorize_runtime():
    current = bindings()
    plan = {
        "schemaVersion": 1, "kind": runtime.PLAN_KIND, "gate": "GATE-PLAN",
        "decision": "approve-exact-plan", "typedApproval": runtime.expected_gate_plan_text(current),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-30T00:00:00Z",
        "bindings": runtime.plan_binding(current), "runtimeAuthorized": False,
        "setupAuthorized": False, "externalMutationAuthorized": False,
        "promotionAuthorized": False,
    }
    now = datetime(2026, 8, 30, 0, 1, tzinfo=timezone.utc)
    bound = runtime.setup_binding(
        current, plan,
        {"bundleSha256": "8" * 64, "bundleSizeBytes": 1234,
         "manifestCanonicalSha256": "9" * 64},
        "hotel-setup-v1-20260830t000100z-deadbeef",
    )
    receipt = {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-exact-one-shot-setup",
        "typedApproval": runtime.expected_gate_setup_text(bound),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-30T00:01:00Z",
        "bindings": bound, "setupAuthorized": True,
        "externalMutationAuthorized": True, "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }
    assert runtime.validate_gate_setup(receipt, current, plan, clock=lambda: now) is receipt
    attacked = copy.deepcopy(receipt)
    attacked["runtimeAuthorized"] = True
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_setup(attacked, current, plan, clock=lambda: now)


def test_gate_run_watches_stale_and_short_deadline(monkeypatch):
    current = bindings()
    plan = {
        "schemaVersion": 1,
        "kind": runtime.PLAN_KIND,
        "gate": "GATE-PLAN",
        "decision": "approve-exact-plan",
        "typedApproval": runtime.expected_gate_plan_text(current),
        "approvedBy": "human-reviewer",
        "approvedAt": "2026-08-29T23:00:00Z",
        "bindings": runtime.plan_binding(current),
        "runtimeAuthorized": False,
        "setupAuthorized": False,
        "externalMutationAuthorized": False,
        "promotionAuthorized": False,
    }
    now = datetime(2026, 8, 30, 0, 1, tzinfo=timezone.utc)
    setup_binding = runtime.setup_binding(
        current, plan,
        {"bundleSha256": "8" * 64, "bundleSizeBytes": 1234,
         "manifestCanonicalSha256": "9" * 64},
        "hotel-setup-v1-20260830t000000z-deadbeef",
    )
    setup = {
        "schemaVersion": 1,
        "kind": runtime.SETUP_KIND,
        "gate": "GATE-SETUP",
        "decision": "authorize-exact-one-shot-setup",
        "typedApproval": runtime.expected_gate_setup_text(setup_binding),
        "approvedBy": "human-reviewer",
        "approvedAt": "2026-08-29T23:30:00Z",
        "bindings": setup_binding,
        "setupAuthorized": True,
        "externalMutationAuthorized": True,
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }
    readiness = {
        "captureId": "hotel-readiness-v1-20260830t000059z-deadbeef",
        "observedAt": (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
    }
    binding = runtime._run_binding(
        current, plan, setup, readiness, "ssh-compose",
        "hotel-v1-20260830t000100z-deadbeef",
        (now + timedelta(seconds=18000)).isoformat().replace("+00:00", "Z"),
    )
    receipt = {
        "schemaVersion": 1,
        "kind": runtime.RUN_KIND,
        "gate": "GATE-RUN",
        "decision": "authorize-exact-run",
        "typedApproval": runtime.expected_gate_run_text(binding),
        "approvedBy": "human-reviewer",
        "approvedAt": now.isoformat().replace("+00:00", "Z"),
        "bindings": binding,
        "runtimeAuthorized": True,
        "externalMutationAuthorized": True,
        "promotionAuthorized": False,
    }
    assert runtime.validate_gate_run(receipt, current, plan, setup, readiness, clock=lambda: now) is receipt
    stale = copy.deepcopy(receipt)
    stale["approvedAt"] = (now - timedelta(seconds=901)).isoformat().replace("+00:00", "Z")
    with pytest.raises(runtime.GateError, match="stale"):
        runtime.validate_gate_run(stale, current, plan, setup, readiness, clock=lambda: now)
    stale_readiness = {
        "captureId": "hotel-readiness-v1-20260829t234559z-cafebabe",
        "observedAt": (now - timedelta(seconds=901)).isoformat().replace("+00:00", "Z"),
    }
    stale_readiness_binding = runtime._run_binding(
        current, plan, setup, stale_readiness, "ssh-compose",
        "hotel-v1-20260830t000100z-deadbeef",
        (now + timedelta(seconds=18000)).isoformat().replace("+00:00", "Z"),
    )
    stale_readiness_receipt = {
        **receipt,
        "bindings": stale_readiness_binding,
        "typedApproval": runtime.expected_gate_run_text(stale_readiness_binding),
    }
    with pytest.raises(runtime.GateError, match="target-produced readiness"):
        runtime.validate_gate_run(
            stale_readiness_receipt, current, plan, setup, stale_readiness,
            clock=lambda: now,
        )
    short = copy.deepcopy(receipt)
    short["bindings"]["deadline"] = (now + timedelta(seconds=17699)).isoformat().replace("+00:00", "Z")
    short["typedApproval"] = runtime.expected_gate_run_text(short["bindings"])
    with pytest.raises(runtime.GateError, match="insufficient"):
        runtime.validate_gate_run(short, current, plan, setup, readiness, clock=lambda: now)


def test_readiness_replays_every_check_and_watches_planted_failure(tmp_path: Path):
    current = bindings()
    plan = {
        "schemaVersion": 1, "kind": runtime.PLAN_KIND, "gate": "GATE-PLAN",
        "decision": "approve-exact-plan", "typedApproval": runtime.expected_gate_plan_text(current),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-29T23:00:00Z",
        "bindings": runtime.plan_binding(current), "runtimeAuthorized": False,
        "setupAuthorized": False, "externalMutationAuthorized": False,
        "promotionAuthorized": False,
    }
    setup_binding = runtime.setup_binding(
        current, plan,
        {"bundleSha256": "8" * 64, "bundleSizeBytes": 1234,
         "manifestCanonicalSha256": "9" * 64},
        "hotel-setup-v1-20260830t000000z-deadbeef",
    )
    setup = {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-exact-one-shot-setup",
        "typedApproval": runtime.expected_gate_setup_text(setup_binding),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-30T00:00:00Z",
        "bindings": setup_binding, "setupAuthorized": True,
        "externalMutationAuthorized": True, "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }
    capture_id = "hotel-readiness-v1-20260830t000100z-deadbeef"
    artifact_root = tmp_path / ("readiness-" + capture_id)
    artifact_root.mkdir()
    seams = []
    for index, seam in enumerate(runtime.READINESS_SEAMS):
        evidence = artifact_root / f"{index:02d}-pass.json"
        failure = artifact_root / f"{index:02d}-failure.json"
        write_json(evidence, readiness_facts(seam, setup))
        planted = planted_readiness_defect(seam, setup)
        write_json(failure, planted)
        with pytest.raises(runtime.GateError) as rejected:
            runtime.replay_readiness_seam(seam, planted, current, setup)
        seams.append({
            "id": seam,
            "evidencePath": evidence.name,
            "evidenceSha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "failureWitnessPath": failure.name,
            "failureWitnessSha256": hashlib.sha256(failure.read_bytes()).hexdigest(),
            "expectedFailureDiagnostic": str(rejected.value),
        })
    observed = datetime(2026, 8, 30, 0, 1, tzinfo=timezone.utc)
    document = {
        "schemaVersion": 4,
        "kind": runtime.READINESS_KIND,
        "studyEpoch": runtime.STUDY_EPOCH,
        "changeId": runtime.CHANGE_ID,
        "bindings": runtime.plan_binding(current),
        "gateSetupCanonicalSha256": runtime.canonical_sha256(setup),
        "captureId": capture_id,
        "artifactRoot": artifact_root.name,
        "observedAt": observed.isoformat().replace("+00:00", "Z"),
        "setupCompletedAt": "2026-08-30T00:00:30Z",
        "hostObserved": "fb14srv4",
        "producer": {
            "target": "fb14srv4", "transportUser": "root",
            "entrypoint": (
                runtime.TARGET["checkoutRoot"] + "/"
                + runtime.CONTROLLER_PATHS["candidate-runtime"]
                ),
                "entrypointSha256": current.controller_sha256["candidate-runtime"],
                "captureId": capture_id,
                "cellsRun": 0,
        },
        "seams": seams,
        "promotionAuthorized": False,
    }
    assert runtime.validate_readiness(
        document, current, setup, tmp_path, clock=lambda: observed,
    ) is document
    attacked = copy.deepcopy(document)
    attacked["seams"][3]["expectedFailureDiagnostic"] = "forged"
    with pytest.raises(runtime.GateError, match="diagnostic"):
        runtime.validate_readiness(attacked, current, setup, tmp_path, clock=lambda: observed)
    stale_clock = observed + timedelta(seconds=901)
    with pytest.raises(runtime.GateError, match="stale"):
        runtime.validate_readiness(
            document, current, setup, tmp_path, clock=lambda: stale_clock,
        )
    replacement_id = "hotel-readiness-v1-20260830t001602z-cafebabe"
    replacement_root = tmp_path / ("readiness-" + replacement_id)
    shutil.copytree(artifact_root, replacement_root)
    replacement = copy.deepcopy(document)
    replacement["captureId"] = replacement_id
    replacement["artifactRoot"] = replacement_root.name
    replacement["observedAt"] = stale_clock.isoformat().replace("+00:00", "Z")
    replacement["producer"]["captureId"] = replacement_id
    assert runtime.validate_readiness(
        replacement, current, setup, tmp_path, clock=lambda: stale_clock,
    ) is replacement
    (artifact_root / "00-pass.json").write_text('{"forged":true}\n')
    with pytest.raises(runtime.GateError, match="digest"):
        runtime.validate_readiness(document, current, setup, tmp_path, clock=lambda: observed)
    forged_producer = copy.deepcopy(document)
    forged_producer["producer"]["cellsRun"] = 1
    with pytest.raises(runtime.GateError, match="identity"):
        runtime.validate_readiness(
            forged_producer, current, setup, tmp_path, clock=lambda: observed,
        )


def test_setup_freshness_is_consumed_only_for_setup_mutation():
    current = bindings()
    plan = {
        "schemaVersion": 1, "kind": runtime.PLAN_KIND, "gate": "GATE-PLAN",
        "decision": "approve-exact-plan", "typedApproval": runtime.expected_gate_plan_text(current),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-29T20:00:00Z",
        "bindings": runtime.plan_binding(current), "runtimeAuthorized": False,
        "setupAuthorized": False, "externalMutationAuthorized": False,
        "promotionAuthorized": False,
    }
    bound = runtime.setup_binding(
        current, plan,
        {"bundleSha256": "8" * 64, "bundleSizeBytes": 1234,
         "manifestCanonicalSha256": "9" * 64},
        "hotel-setup-v1-20260830t000000z-deadbeef",
    )
    setup = {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-exact-one-shot-setup",
        "typedApproval": runtime.expected_gate_setup_text(bound),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-29T20:01:00Z",
        "bindings": bound, "setupAuthorized": True,
        "externalMutationAuthorized": True, "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }
    much_later = datetime(2026, 8, 30, 0, 1, tzinfo=timezone.utc)
    with pytest.raises(runtime.GateError, match="stale"):
        runtime.validate_gate_setup(setup, current, plan, clock=lambda: much_later)
    assert runtime.validate_gate_setup(
        setup, current, plan, clock=lambda: much_later, require_fresh=False,
    ) is setup


def test_setup_installer_consumes_fresh_gate_and_uses_operational_upload_path(
    monkeypatch, tmp_path: Path,
):
    current = bindings()
    now = datetime(2026, 8, 30, 0, 1, tzinfo=timezone.utc)
    plan = {
        "schemaVersion": 1, "kind": runtime.PLAN_KIND, "gate": "GATE-PLAN",
        "decision": "approve-exact-plan", "typedApproval": runtime.expected_gate_plan_text(current),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-30T00:00:00Z",
        "bindings": runtime.plan_binding(current), "runtimeAuthorized": False,
        "setupAuthorized": False, "externalMutationAuthorized": False,
        "promotionAuthorized": False,
    }
    bundle = tmp_path / "bundle.tar"
    bundle.write_bytes(b"reviewed-bundle")
    bound = runtime.setup_binding(
        current, plan,
        {"bundleSha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
         "bundleSizeBytes": bundle.stat().st_size,
         "manifestCanonicalSha256": "9" * 64},
        "hotel-setup-v1-20260830t000100z-deadbeef",
    )
    setup = {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-exact-one-shot-setup",
        "typedApproval": runtime.expected_gate_setup_text(bound),
        "approvedBy": "human-reviewer", "approvedAt": "2026-08-30T00:01:00Z",
        "bindings": bound, "setupAuthorized": True,
        "externalMutationAuthorized": True, "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }
    receipt = {
        "kind": "hotel-srv4-install-receipt-v1",
        "bundleSha256": bound["bundleSha256"],
        "manifestCanonicalSha256": bound["manifestCanonicalSha256"],
        "gateSetupCanonicalSha256": runtime.canonical_sha256(setup),
        "cellsRun": 0, "runtimeStarted": False, "foreignMutation": False,
    }
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        output = "" if command[0] == "scp" else json.dumps(receipt)
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    assert runtime.SshSetupInstaller().install(
        bundle, setup, bindings=current, gate_plan=plan, clock=lambda: now,
    ) == receipt
    assert commands[0][-1] == "root@fb14srv4:" + runtime.TARGET["uploadPath"]


def test_reconnect_controls_live_only_on_detached_controller():
    assert callable(runtime.DetachedSshController.status)
    assert callable(runtime.DetachedSshController.refetch_and_replay)
    assert callable(runtime.DetachedSshController.capture_readiness)
    assert not hasattr(runtime.SshSetupInstaller, "status")
    assert not hasattr(runtime.SshSetupInstaller, "refetch_and_replay")


def test_readiness_capture_executes_installed_target_producer_and_fetches_exact_tree(
    monkeypatch, tmp_path: Path,
):
    setup_id = "hotel-setup-v1-20260830t000000z-deadbeef"
    capture_id = "hotel-readiness-v1-20260830t000100z-deadbeef"
    root_name = "readiness-" + capture_id
    readiness = {
        "schemaVersion": 4, "kind": runtime.READINESS_KIND,
        "captureId": capture_id,
        "artifactRoot": root_name, "hostObserved": "fb14srv4",
        "producer": {"cellsRun": 0}, "promotionAuthorized": False,
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        directory = tarfile.TarInfo(root_name)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o700
        archive.addfile(directory)
        payload = runtime.canonical_bytes(readiness) + b"\n"
        info = tarfile.TarInfo(root_name + "/readiness.json")
        info.size = len(payload)
        info.mode = 0o600
        archive.addfile(info, io.BytesIO(payload))
    archive_bytes = buffer.getvalue()
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if "--target-readiness" in command:
            return subprocess.CompletedProcess(
                command, 0, json.dumps(readiness), "",
            )
        kwargs["stdout"].write(archive_bytes)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    capture = runtime.DetachedSshController().capture_readiness(
        setup_id, tmp_path / "capture", capture_id=capture_id,
    )
    assert commands[0] == [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
        "root@fb14srv4", "/usr/bin/python3", "-I",
        runtime.TARGET["checkoutRoot"] + "/"
        + runtime.CONTROLLER_PATHS["candidate-runtime"],
        "--target-readiness", setup_id,
        "--readiness-capture-id", capture_id,
    ]
    assert commands[1][-4:] == [runtime.TARGET["artifactParent"], "-czf", "-", root_name]
    assert capture["cellsRun"] == 0
    assert Path(capture["readinessPath"]).is_file()
    recovered = runtime.DetachedSshController().capture_readiness(
        setup_id, tmp_path / "capture", capture_id=capture_id,
    )
    assert recovered == capture
    assert len(commands) == 3


def test_command_transport_is_fixed_to_root_srv4_then_runuser_fhuebscher():
    remote = runtime.CommandComposeTransport(
        "ssh-compose", "fb14srv4", runtime.TARGET["checkoutRoot"]
    )
    assert remote._base()[:13] == [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--",
        "root@fb14srv4", "/usr/sbin/runuser", "--user", "fhuebscher", "--",
        "/usr/bin/python3", "-I",
    ]
    with pytest.raises(runtime.GateError):
        runtime.CommandComposeTransport("ssh-compose", "another-host", "/tmp/repo")


def test_remote_setup_launch_and_status_programs_are_syntax_checked_and_fixed():
    compile(runtime.REMOTE_ONE_SHOT_INSTALL, "hotel-srv4-setup", "exec")
    compile(runtime.REMOTE_DETACHED_LAUNCH, "hotel-srv4-launch", "exec")
    compile(runtime.REMOTE_STATUS, "hotel-srv4-status", "exec")
    compile(runtime.REMOTE_REFETCH_ARCHIVE, "hotel-srv4-refetch", "exec")
    assert "root@fb14srv4" not in runtime.REMOTE_DETACHED_LAUNCH
    assert '"--supervise-admission"' in runtime.REMOTE_DETACHED_LAUNCH
    assert '"campaign-abort.json"' in runtime.REMOTE_DETACHED_LAUNCH
    assert "os.O_EXCL" in runtime.REMOTE_DETACHED_LAUNCH
    assert "pass_fds=(lease_fd,)" in runtime.REMOTE_DETACHED_LAUNCH
    assert '"--lease-fd",str(lease_fd)' in runtime.REMOTE_DETACHED_LAUNCH
    assert '"--root-terminal-observe-admission"' in runtime.REMOTE_DETACHED_LAUNCH
    assert '"ownedResourcesRemaining":{}' not in runtime.REMOTE_DETACHED_LAUNCH
    assert "os.ftruncate(lease_fd,0)" in runtime.REMOTE_DETACHED_LAUNCH
    assert "remaining < 17700 or remaining > 18005" in runtime.REMOTE_DETACHED_LAUNCH
    # Host condition v2: the install script refuses ANY foreign Compose project or
    # container and records the (empty) inventory; the dps_training_k pin is gone.
    assert "a foreign Compose project or container is present" in runtime.REMOTE_ONE_SHOT_INSTALL
    assert 'startswith("hotel_candidate_v4")' in runtime.REMOTE_ONE_SHOT_INSTALL
    assert "/home/cgade/tests_2/dps.training_k" not in runtime.REMOTE_ONE_SHOT_INSTALL
    assert runtime.TARGET["artifactParent"] in runtime.REMOTE_REFETCH_ARCHIVE
    assert runtime.TARGET["controlRoot"] in runtime.REMOTE_REFETCH_ARCHIVE
    assert 'arcname="evidence/"+campaign' in runtime.REMOTE_REFETCH_ARCHIVE
    assert 'arcname="control/"+campaign' in runtime.REMOTE_REFETCH_ARCHIVE


def test_embedded_remote_checker_watches_compatibility_rollback_abort_and_owner_defects():
    planted_filter = runtime.REMOTE_ONE_SHOT_INSTALL.replace(
        "bundle.extractall(CHECKOUT)",
        'bundle.extractall(CHECKOUT,filter="data")',
    )
    with pytest.raises(runtime.GateError, match="Python-3.9"):
        runtime.validate_embedded_remote_programs(installer=planted_filter)

    planted_no_rollback = runtime.REMOTE_ONE_SHOT_INSTALL.replace(
        "shutil.rmtree(path)", "pass # planted missing rollback",
    )
    with pytest.raises(runtime.GateError, match="rollback safety"):
        runtime.validate_embedded_remote_programs(installer=planted_no_rollback)

    planted_no_abort = runtime.REMOTE_DETACHED_LAUNCH.replace(
        '"campaign-abort.json"', '"campaign-abort.removed"',
    )
    with pytest.raises(runtime.GateError, match="supervised-abort"):
        runtime.validate_embedded_remote_programs(launcher=planted_no_abort)

    planted_forged_cleanup = runtime.REMOTE_DETACHED_LAUNCH.replace(
        '"--root-terminal-observe-admission"', '"--planted-skip-root-observation"',
    )
    with pytest.raises(runtime.GateError, match="supervised-abort"):
        runtime.validate_embedded_remote_programs(launcher=planted_forged_cleanup)

    planted_no_preflock_attempt = runtime.REMOTE_DETACHED_LAUNCH.replace(
        '"launch-attempt.json"', '"launch-attempt.removed"', 1,
    )
    with pytest.raises(runtime.GateError, match="supervised-abort"):
        runtime.validate_embedded_remote_programs(launcher=planted_no_preflock_attempt)

    planted_no_owner = runtime.REMOTE_STATUS.replace(
        'owner.get("campaignId")==campaign', "False # planted owner blindness",
    )
    with pytest.raises(runtime.GateError, match="lease-owner"):
        runtime.validate_embedded_remote_programs(status=planted_no_owner)


def test_python39_compatible_one_shot_rolls_back_exact_created_roots_for_retry(tmp_path: Path):
    parent = tmp_path / "release"
    checkout = parent / "checkout"
    artifact = tmp_path / "artifact"
    lease_root = tmp_path / "leases"
    lease_path = lease_root / ".hotel-candidate-v1.lock"
    upload = tmp_path / "bundle.tar"
    payload = b"reviewed payload without manifest to plant a post-extraction failure\n"
    with tarfile.open(upload, mode="w:") as bundle:
        member = tarfile.TarInfo("payload.txt")
        member.size = len(payload)
        member.mode = 0o644
        bundle.addfile(member, io.BytesIO(payload))
    bundle_bytes = upload.read_bytes()
    setup = {
        "kind": "hotel-candidate-gate-setup-v1",
        "setupAuthorized": True,
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
        "bindings": {
            "operationalTarget": {
                "target": "fb14srv4", "transportUser": "root", "setupUser": "root",
                "executionUser": "fhuebscher", "executionUid": 1007,
                "executionGid": 1007, "dockerGid": 998,
                "authorizedParent": str(parent), "releaseParent": str(parent),
                "checkoutRoot": str(checkout), "artifactParent": str(artifact),
                "leaseRoot": str(lease_root), "leasePath": str(lease_path),
                "controlRoot": str(parent / "control"), "uploadPath": str(upload),
            },
            "readinessProbeAuthorized": True,
            "readinessCaptureMode": "repeatable-append-only-zero-cell",
            "cellsAuthorized": 0,
            "bundleSizeBytes": len(bundle_bytes),
            "bundleSha256": hashlib.sha256(bundle_bytes).hexdigest(),
            "manifestCanonicalSha256": "0" * 64,
            "setupId": "hotel-setup-v1-20260830t010203z-deadbeef",
        },
    }
    code = runtime.REMOTE_ONE_SHOT_INSTALL
    for old, new in (
        (runtime.TARGET["checkoutRoot"], str(checkout)),
        (runtime.TARGET["artifactParent"], str(artifact)),
        (runtime.TARGET["leasePath"], str(lease_path)),
        (runtime.TARGET["leaseRoot"], str(lease_root)),
        (runtime.TARGET["uploadPath"], str(upload)),
        (runtime.TARGET["authorizedParent"], str(parent)),
    ):
        code = code.replace(old, new)
    fake_environment = '''
os.geteuid=lambda: 0
os.chown=lambda *args,**kwargs: None
os.fchown=lambda *args,**kwargs: None
pwd.getpwnam=lambda name: pwd.struct_passwd(("fhuebscher","x",1007,1007,"","/tmp","/bin/sh"))
grp.getgrall=lambda: [grp.struct_group(("sudo","x",27,["fhuebscher"])),grp.struct_group(("docker","x",998,["fhuebscher"]))]
class FakeCompleted:
    def __init__(self,stdout): self.stdout=stdout; self.stderr=""; self.returncode=0
def fake_run(argv,**kwargs):
    if argv[:2]==["docker","ps"]:
        return FakeCompleted("")
    if argv[:3]==["docker","compose","ls"]:
        return FakeCompleted('[]')
    return FakeCompleted("29.6.1\\n")
subprocess.run=fake_run
# This laptop has neither target spelling of runuser; stand in for fb14srv4
# by taking the first (fb14srv4-preferred) candidate.
binpath=lambda name,cands: cands[0]
'''
    code = code.replace(
        "created=[]; install_complete=False",
        fake_environment + "\ncreated=[]; install_complete=False",
    ).replace(
        "if not port_free(35005) or not port_free(36685):",
        "if False:",
    )
    system_python = Path("/usr/bin/python3")
    assert system_python.is_file()
    for attempt in range(2):
        if attempt:
            upload.write_bytes(bundle_bytes)
        result = subprocess.run(
            [str(system_python), "-I", "-c", code], input=json.dumps(setup),
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        assert result.returncode != 0
        assert "install-manifest.json" in result.stderr
        assert "already exists" not in result.stderr
        assert not parent.exists()
        assert not artifact.exists()
        assert not upload.exists()


def test_status_discovers_retained_abort_without_launch_receipt(tmp_path: Path):
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    control = tmp_path / "control"
    campaign = control / campaign_id
    campaign.mkdir(parents=True)
    document = admission(Path(runtime.TARGET["artifactParent"]) / campaign_id)
    abort = runtime._campaign_abort_document(
        document, failure_type="PlantedPrePopenFailure",
        failure_message="planted", child_return_code=None,
        execution_receipt_present=False,
    )
    write_json(campaign / "campaign-abort.json", abort)
    code = runtime.REMOTE_STATUS.replace(
        runtime.TARGET["controlRoot"], str(control),
    ).replace(runtime.TARGET["leasePath"], str(tmp_path / ".lease"))
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], input=campaign_id,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status["terminal"] is True
    assert status["completionArtifact"] == "campaign-abort.json"
    assert status["launchPresent"] is False
    assert status["pid"] is None

    abort["kind"] = "planted-wrong-kind"
    write_json(campaign / "campaign-abort.json.tmp", abort)
    (campaign / "campaign-abort.json.tmp").replace(campaign / "campaign-abort.json")
    planted = subprocess.run(
        [sys.executable, "-I", "-c", code], input=campaign_id,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert planted.returncode != 0


def test_remote_launcher_retains_abort_for_planted_pre_popen_failure(tmp_path: Path):
    now = datetime.now(timezone.utc)
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    control_root = tmp_path / "control"
    checkout = tmp_path / "checkout"
    lease_path = tmp_path / ".lease"
    control_root.mkdir()
    checkout.mkdir()
    document = admission(tmp_path / "evidence" / campaign_id)
    document["bindings"].update({
        "campaignId": campaign_id,
        "releaseParent": str(control_root.parent),
        "checkoutRoot": str(checkout),
        "controlRoot": str(control_root),
        "leasePath": str(lease_path),
        "readinessObservedAt": now.isoformat().replace("+00:00", "Z"),
        "deadline": (now + timedelta(seconds=18000)).isoformat().replace("+00:00", "Z"),
    })
    document["issuedAt"] = now.isoformat().replace("+00:00", "Z")
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    code = runtime.REMOTE_DETACHED_LAUNCH.replace(
        runtime.TARGET["controlRoot"], str(control_root),
    ).replace(
        runtime.TARGET["checkoutRoot"], str(checkout),
    ).replace(
        runtime.TARGET["leasePath"], str(lease_path),
    ).replace(
        "import datetime,fcntl,hashlib,json,os,re,signal,stat,subprocess,sys",
        "import datetime,fcntl,hashlib,json,os,re,signal,stat,subprocess,sys\n"
        "os.chown=lambda *args,**kwargs: None; os.fchown=lambda *args,**kwargs: None",
    ).replace(
        'command=[binpath("python3",PYTHON_CANDIDATES),"-I",',
        'command=["/definitely/missing-python","-I",',
    ).replace(
        'binpath("python3",PYTHON_CANDIDATES)',
        'cands_first(PYTHON_CANDIDATES)',
    ).replace(
        'RUNUSER_CANDIDATES=("/usr/sbin/runuser","/sbin/runuser")',
        'RUNUSER_CANDIDATES=("/usr/sbin/runuser","/sbin/runuser")\n'
        'def cands_first(cands): return cands[0]',
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        input=json.dumps(document), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert result.returncode != 0
    abort_path = control_root / campaign_id / "campaign-abort.json"
    retained = runtime._json_file(abort_path, "pre-Popen abort")
    assert runtime.validate_campaign_abort(retained, document, campaign_id) == retained
    assert retained["failureType"] == "FileNotFoundError"
    assert not (control_root / campaign_id / "launch.json").exists()
    reusable = os.open(lease_path, os.O_RDWR)
    try:
        fcntl.flock(reusable, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(reusable, fcntl.LOCK_UN)
    finally:
        os.close(reusable)


def test_status_attributes_a_shared_locked_lease_to_its_successor(tmp_path: Path):
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    successor_id = "hotel-v1-20260830t020304z-feedface"
    control_root = tmp_path / "control"
    campaign = control_root / campaign_id
    campaign.mkdir(parents=True)
    document = admission(Path(runtime.TARGET["artifactParent"]) / campaign_id)
    abort = runtime._campaign_abort_document(
        document, failure_type="PlantedTerminal",
        failure_message="predecessor terminal", child_return_code=1,
        execution_receipt_present=False,
    )
    write_json(campaign / "campaign-abort.json", abort)
    lease_path = tmp_path / ".lease"
    write_json(lease_path, {
        "campaignId": successor_id,
        "admissionCanonicalSha256": "0" * 64,
    })
    held = os.open(lease_path, os.O_RDWR)
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    code = runtime.REMOTE_STATUS.replace(
        runtime.TARGET["controlRoot"], str(control_root),
    ).replace(runtime.TARGET["leasePath"], str(lease_path))
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", code], input=campaign_id,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    finally:
        fcntl.flock(held, fcntl.LOCK_UN)
        os.close(held)
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status["terminal"] is True
    assert status["leaseLocked"] is True
    assert status["leaseOwnedByCampaign"] is False
    assert status["leaseLockedByCampaign"] is False


def test_detached_launch_independently_consumes_freshness_and_full_budget(monkeypatch):
    now = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
    document = admission(
        Path(runtime.TARGET["artifactParent"])
        / "hotel-v1-20260830t010000z-deadbeef"
    )
    document["bindings"]["campaignId"] = "hotel-v1-20260830t010000z-deadbeef"
    document["bindings"]["artifactRoot"] = (
        runtime.TARGET["artifactParent"] + "/hotel-v1-20260830t010000z-deadbeef"
    )
    document["bindings"]["leaseRoot"] = runtime.TARGET["leaseRoot"]
    document["bindings"]["leasePath"] = runtime.TARGET["leasePath"]
    document["bindings"]["readinessObservedAt"] = "2026-08-30T00:59:59Z"
    document["bindings"]["deadline"] = "2026-08-30T06:00:00Z"
    document["issuedAt"] = "2026-08-30T01:00:00Z"
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    assert runtime.validate_launch_admission(document, clock=lambda: now) is document

    stale = copy.deepcopy(document)
    stale["issuedAt"] = "2026-08-30T00:44:59Z"
    stale_body = {key: value for key, value in stale.items() if key != "admissionCanonicalSha256"}
    stale["admissionCanonicalSha256"] = runtime.canonical_sha256(stale_body)
    monkeypatch.setattr(
        runtime.DetachedSshController, "_ssh",
        lambda *_args, **_kwargs: pytest.fail("stale admission reached SSH"),
    )
    with pytest.raises(runtime.GateError, match="admission.*stale"):
        runtime.DetachedSshController().launch(stale, clock=lambda: now)

    short = copy.deepcopy(document)
    short["bindings"]["deadline"] = "2026-08-30T05:54:59Z"
    short_body = {key: value for key, value in short.items() if key != "admissionCanonicalSha256"}
    short["admissionCanonicalSha256"] = runtime.canonical_sha256(short_body)
    with pytest.raises(runtime.GateError, match="full planned mutation"):
        runtime.validate_launch_admission(short, clock=lambda: now)


def test_target_supervisor_rechecks_full_budget_at_child_start():
    now = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
    document = admission(
        Path(runtime.TARGET["artifactParent"])
        / "hotel-v1-20260830t010000z-deadbeef"
    )
    document["bindings"]["readinessObservedAt"] = "2026-08-30T00:59:59Z"
    document["bindings"]["deadline"] = "2026-08-30T06:00:00Z"
    document["issuedAt"] = "2026-08-30T01:00:00Z"
    assert runtime.validate_supervisor_start_window(
        document, clock=lambda: now,
    ) == datetime(2026, 8, 30, 6, 0, tzinfo=timezone.utc)

    delayed = now + timedelta(seconds=301)
    with pytest.raises(runtime.GateError, match="full runtime budget"):
        runtime.validate_supervisor_start_window(document, clock=lambda: delayed)


def test_execute_campaign_cleans_and_releases_before_terminal_validation(tmp_path: Path):
    document = admission(tmp_path / "campaign")

    class FakeTransport:
        transport_id = "ssh-compose"
        target = "fb14srv4"

        def __init__(self):
            self.events = []

        def acquire_lease(self, _admission):
            self.events.append("lease")
            return {"acquired": True}

        def preflight(self, _admission):
            self.events.append("preflight")
            return {"passed": True}

        def prepare_campaign(self, admission):
            self.events.append("prepare")
            Path(admission["bindings"]["artifactRoot"]).mkdir(mode=0o700)
            return {"prepared": True}

        def record_attempt_start(self, _admission, contract):
            self.events.append("attempt:" + contract["runId"])
            return {"kind": "hotel-candidate-attempt-start-v1", "runId": contract["runId"]}

        def run_cell(self, _admission, contract):
            self.events.append(contract["runId"])
            return {"candidateCellValid": True, "runId": contract["runId"]}

        def cleanup(self, _admission):
            self.events.append("cleanup")
            return {"ownedResourcesRemaining": []}

        def release_lease(self, _admission):
            self.events.append("release")
            return {"released": True}

        def validate_campaign(self, _admission):
            self.events.append("validate")
            return {"candidateCampaignValid": True}

    transport = FakeTransport()
    result = runtime.execute_campaign(document, transport)
    assert result["status"] == "complete"
    assert result["attemptedCells"] == runtime.CELL_COUNT
    first_run = runtime.cell_contracts(document)[0]["runId"]
    assert transport.events[3:5] == ["attempt:" + first_run, first_run]
    assert transport.events[-3:] == ["cleanup", "release", "validate"]


def test_execute_campaign_always_attempts_release_when_cleanup_raises(tmp_path: Path):
    document = admission(tmp_path / "campaign")

    class FailingCleanup:
        transport_id = "ssh-compose"
        target = "fb14srv4"

        def __init__(self): self.events = []
        def acquire_lease(self, _admission): self.events.append("lease"); return {"acquired": True}
        def preflight(self, _admission): return {"passed": False}
        def prepare_campaign(self, _admission): raise AssertionError("not reached")
        def run_cell(self, _admission, _contract): raise AssertionError("not reached")
        def validate_campaign(self, _admission): raise AssertionError("not reached")
        def cleanup(self, _admission): self.events.append("cleanup"); raise RuntimeError("planted cleanup failure")
        def release_lease(self, _admission): self.events.append("release"); return {"released": True}

    transport = FailingCleanup()
    result = runtime.execute_campaign(document, transport)
    assert transport.events[-2:] == ["cleanup", "release"]
    assert result["status"] == "cleanup-failed"
    assert result["leaseRelease"]["released"] is True


class OrchestratedTransport:
    """A fake target transport that records exactly what the driver dispatched."""

    transport_id = "ssh-compose"
    target = "fb14srv4"

    def __init__(self, *, blocked_ordinal: int | None = None, raise_at: int | None = None,
                 campaign_valid: bool = True):
        self.blocked_ordinal = blocked_ordinal
        self.raise_at = raise_at
        self.campaign_valid = campaign_valid
        self.dispatched: list[str] = []
        self.attempts: list[str] = []

    def acquire_lease(self, _admission): return {"acquired": True}
    def preflight(self, _admission): return {"passed": True}

    def prepare_campaign(self, document):
        Path(document["bindings"]["artifactRoot"]).mkdir(mode=0o700)
        return {"prepared": True}

    def record_attempt_start(self, _admission, contract):
        self.attempts.append(contract["runId"])
        return {"kind": "hotel-candidate-attempt-start-v1", "runId": contract["runId"]}

    def run_cell(self, _admission, contract):
        self.dispatched.append(contract["runId"])
        if self.raise_at is not None and contract["ordinal"] == self.raise_at:
            raise RuntimeError("planted cell producer defect")
        if self.blocked_ordinal is not None and contract["ordinal"] == self.blocked_ordinal:
            return {"candidateCellValid": False, "runId": contract["runId"]}
        return {"candidateCellValid": True, "runId": contract["runId"]}

    def cleanup(self, _admission): return {"ownedResourcesRemaining": []}
    def release_lease(self, _admission): return {"released": True}

    def validate_campaign(self, _admission):
        return {"candidateCampaignValid": self.campaign_valid}


def test_runtime_journal_chains_every_cell_and_replays_offline(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    transport = OrchestratedTransport()
    result = runtime.execute_campaign(document, transport)
    assert result["status"] == "complete"
    journal = tmp_path / "campaign" / runtime.JOURNAL_NAME
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    contracts = runtime.cell_contracts(document)
    assert [row["runId"] for row in rows] == [row["runId"] for row in contracts]
    assert rows[0]["previousRecordSha256"] == "0" * 64
    for index, row in enumerate(rows):
        body = {key: value for key, value in row.items() if key != "recordSha256"}
        assert row["kind"] == runtime.JOURNAL_KIND
        assert row["sequence"] == index
        assert row["state"] == "valid"
        assert row["recordSha256"] == runtime.canonical_sha256(body)
        if index:
            assert row["previousRecordSha256"] == rows[index - 1]["recordSha256"]
    replay = runtime.replay_runtime_journal(
        journal, contracts, campaign_id=document["bindings"]["campaignId"],
        **_journal_digests(document),
    )
    assert replay["rows"] == replay["validCells"] == runtime.CELL_COUNT
    assert replay["terminalStop"] is False and replay["complete"] is True
    assert result["journal"] == replay


def test_runtime_journal_is_bound_to_its_own_campaign(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    runtime.execute_campaign(document, OrchestratedTransport())
    journal = tmp_path / "campaign" / runtime.JOURNAL_NAME
    contracts = runtime.cell_contracts(document)
    with pytest.raises(runtime.GateError):
        runtime.replay_runtime_journal(
            journal, contracts, campaign_id="hotel-v1-20260830t010203z-feedface",
            **_journal_digests(document),
        )
    with pytest.raises(runtime.GateError):
        runtime.replay_runtime_journal(
            journal, contracts, campaign_id="not-a-campaign", **_journal_digests(document),
        )


@pytest.mark.parametrize(
    ("row_index", "field", "value"),
    [
        (5, "state", "stopped"),
        (5, "runId", "no-fault-cost-b01-full-a01"),
        (5, "previousRecordSha256", "0" * 64),
        (5, "campaignId", "hotel-v1-20260830t010203z-feedface"),
        (0, "sequence", 7),
    ],
)
def test_runtime_journal_replay_watches_tamper(
    tmp_path: Path, row_index: int, field: str, value: object,
):
    document = admission(tmp_path / "campaign")
    runtime.execute_campaign(document, OrchestratedTransport())
    journal = tmp_path / "campaign" / runtime.JOURNAL_NAME
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    rows[row_index][field] = value
    journal.write_text(
        "".join(runtime.canonical_bytes(row).decode() + "\n" for row in rows)
    )
    with pytest.raises(runtime.GateError):
        runtime.replay_runtime_journal(
            journal, runtime.cell_contracts(document),
            campaign_id=document["bindings"]["campaignId"],
            **_journal_digests(document),
        )


def test_runtime_journal_refuses_a_record_after_its_terminal_stop(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    contracts = runtime.cell_contracts(document)
    runtime.execute_campaign(document, OrchestratedTransport(blocked_ordinal=2))
    journal = tmp_path / "campaign" / runtime.JOURNAL_NAME
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [row["state"] for row in rows] == ["valid", "stopped"]
    # Re-chain a well-formed successor onto the stopped record: the chain is
    # intact, but a campaign that has already abstained may not continue.
    body = {
        key: value for key, value in rows[-1].items() if key != "recordSha256"
    }
    body.update({
        "sequence": 2, "previousRecordSha256": rows[-1]["recordSha256"],
        "runId": contracts[2]["runId"], "runKey": contracts[2]["runKey"],
        "ordinal": contracts[2]["ordinal"], "state": "valid",
        "cellReceiptCanonicalSha256": "a" * 64, "reason": None,
    })
    successor = {**body, "recordSha256": runtime.canonical_sha256(body)}
    with journal.open("a") as handle:
        handle.write(runtime.canonical_bytes(successor).decode() + "\n")
    with pytest.raises(runtime.GateError):
        runtime.replay_runtime_journal(
            journal, contracts, campaign_id=document["bindings"]["campaignId"],
            **_journal_digests(document),
        )


def test_blocked_cell_stops_the_campaign_and_retains_one_abstaining_abort(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    contracts = runtime.cell_contracts(document)
    transport = OrchestratedTransport(blocked_ordinal=3)
    result = runtime.execute_campaign(document, transport)

    # One-shot: the blocked cell is the last thing dispatched, with no retry,
    # no substitution, and nothing after it.
    assert result["status"] == "stopped-invalid-cell"
    assert transport.dispatched == [row["runId"] for row in contracts[:3]]
    assert transport.attempts == transport.dispatched
    assert result["attemptedCells"] == 3

    journal = tmp_path / "campaign" / runtime.JOURNAL_NAME
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    assert [row["state"] for row in rows] == ["valid", "valid", "stopped"]
    assert rows[-1]["runId"] == contracts[2]["runId"]
    assert rows[-1]["cellReceiptCanonicalSha256"] is None and rows[-1]["reason"]
    replay = runtime.replay_runtime_journal(
        journal, contracts, campaign_id=document["bindings"]["campaignId"],
        **_journal_digests(document),
    )
    assert replay["validCells"] == 2 and replay["terminalStop"] is True
    assert replay["complete"] is False

    abort_path = tmp_path / "campaign" / runtime.CONTROLLER_ABORT_NAME
    abort = json.loads(abort_path.read_text())
    assert runtime.validate_controller_abort(
        abort, document, document["bindings"]["campaignId"],
    ) == abort
    assert abort["stage"] == "cell-execution"
    assert abort["validCells"] == 2
    assert abort["journalRows"] == 3
    assert abort["attemptedCells"] == 3
    assert abort["experimentalState"] == "ABSTAINED"
    assert abort["retryAllowed"] is False
    assert abort["candidateCampaignValid"] is False
    assert abort["promotionAuthorized"] is False
    assert abort["journalChainHeadSha256"] == rows[-1]["recordSha256"]
    assert result["campaignAbort"] == abort


def test_abstention_is_durable_before_the_cleanup_phase_runs(tmp_path: Path):
    """Cleanup can fail or hang; a terminal non-result must not depend on it."""
    document = admission(tmp_path / "campaign")
    abort_path = tmp_path / "campaign" / runtime.CONTROLLER_ABORT_NAME
    observed: dict[str, bool] = {}

    class LateCleanup(OrchestratedTransport):
        def cleanup(self, document_):
            observed["abortExistsAtCleanup"] = abort_path.is_file()
            raise RuntimeError("planted cleanup failure after the abort")

    transport = LateCleanup(blocked_ordinal=2)
    result = runtime.execute_campaign(document, transport)
    assert observed["abortExistsAtCleanup"] is True
    # The pre-cleanup abstention is never restated or replaced by the later
    # cleanup-failure status.
    abort = json.loads(abort_path.read_text())
    assert abort["stage"] == "cell-execution"
    assert abort["failureType"] == "InvalidCell"
    assert abort["validCells"] == 1
    assert result["campaignAbort"] == abort
    assert result["status"] == "cleanup-failed"


def test_raising_cell_is_charged_to_the_journal_before_it_propagates(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    transport = OrchestratedTransport(raise_at=2)
    result = runtime.execute_campaign(document, transport)
    assert result["status"] == "runtime-error"
    assert transport.dispatched == [
        row["runId"] for row in runtime.cell_contracts(document)[:2]
    ]
    rows = [
        json.loads(line)
        for line in (tmp_path / "campaign" / runtime.JOURNAL_NAME).read_text().splitlines()
    ]
    assert [row["state"] for row in rows] == ["valid", "stopped"]
    assert "planted cell producer defect" in rows[-1]["reason"]
    abort = json.loads((tmp_path / "campaign" / runtime.CONTROLLER_ABORT_NAME).read_text())
    assert abort["stage"] == "cell-execution"
    assert abort["validCells"] == 1
    assert abort["experimentalState"] == "ABSTAINED"


def test_on_sigterm_raises_terminated():
    with pytest.raises(runtime.Terminated):
        runtime._on_sigterm(signal.SIGTERM, None)


def test_terminated_mid_cell_retains_an_abort_before_dying(tmp_path: Path):
    """Section 3.4: a delivered SIGTERM must not simply kill the process with
    no stop record. `_on_sigterm` converts SIGTERM into `Terminated`
    (BaseException); this exercises the outer `except BaseException` handler
    directly -- calling `_on_sigterm`/raising `Terminated` mid-cell -- rather
    than sending a real signal to the test process itself."""
    document = admission(tmp_path / "campaign")

    class TerminatedMidCell(OrchestratedTransport):
        def run_cell(self, admission_, contract):
            if contract["ordinal"] == 2:
                raise runtime.Terminated()
            return super().run_cell(admission_, contract)

    transport = TerminatedMidCell()
    with pytest.raises(runtime.Terminated):
        runtime.execute_campaign(document, transport)

    # Cleanup/release still ran -- a stop record must never come at the cost
    # of stranding an owned Docker/lease resource. Cell 2 raises `Terminated`
    # before it ever calls the base `run_cell`, so only cell 1 was dispatched.
    assert transport.dispatched == [
        row["runId"] for row in runtime.cell_contracts(document)[:1]
    ]

    abort = json.loads((tmp_path / "campaign" / runtime.CONTROLLER_ABORT_NAME).read_text())
    assert abort["stage"] == "cell-execution"
    assert abort["experimentalState"] == "ABSTAINED"
    assert abort["retryAllowed"] is False
    assert abort["validCells"] == 1

    rows = [
        json.loads(line)
        for line in (tmp_path / "campaign" / runtime.JOURNAL_NAME).read_text().splitlines()
    ]
    assert [row["state"] for row in rows] == ["valid"]


def test_execute_campaign_restores_the_previous_sigterm_handler(tmp_path: Path):
    """The SIGTERM disposition change is scoped to one `execute_campaign`
    call; it must never leak into whatever process runs many campaigns (or
    a test suite) across calls."""
    previous = signal.getsignal(signal.SIGTERM)
    document = admission(tmp_path / "campaign")
    runtime.execute_campaign(document, OrchestratedTransport())
    assert signal.getsignal(signal.SIGTERM) is previous

    document2 = admission(tmp_path / "campaign2")

    class TerminatedMidCell(OrchestratedTransport):
        def run_cell(self, admission_, contract):
            if contract["ordinal"] == 1:
                raise runtime.Terminated()
            return super().run_cell(admission_, contract)

    with pytest.raises(runtime.Terminated):
        runtime.execute_campaign(document2, TerminatedMidCell())
    assert signal.getsignal(signal.SIGTERM) is previous


def test_clean_campaign_writes_no_abort_and_no_quarantine(tmp_path: Path):
    """Negative control for the abort path."""
    document = admission(tmp_path / "campaign")
    result = runtime.execute_campaign(document, OrchestratedTransport())
    artifact = tmp_path / "campaign"
    assert result["status"] == "complete"
    assert result["campaignAbort"] is None
    assert not (artifact / runtime.CONTROLLER_ABORT_NAME).exists()
    assert list(artifact.iterdir()) == [artifact / runtime.JOURNAL_NAME]
    assert not any(
        path.name.endswith(cell.BLOCKED_EVIDENCE_SUFFIX)
        for path in artifact.rglob("*")
    )
    assert runtime._terminal_execution_receipt(
        _write_receipt(tmp_path / "receipt.json", result),
        document, document["bindings"]["campaignId"],
    ) is True


def _write_receipt(path: Path, receipt: dict) -> Path:
    path.write_bytes(runtime.canonical_bytes(receipt) + b"\n")
    return path


def test_non_complete_receipt_is_terminal_only_when_it_abstains(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    result = runtime.execute_campaign(document, OrchestratedTransport(blocked_ordinal=1))
    campaign_id = document["bindings"]["campaignId"]
    assert runtime._terminal_execution_receipt(
        _write_receipt(tmp_path / "abstained.json", result), document, campaign_id,
    ) is True
    stripped = {**result, "campaignAbort": None}
    assert runtime._terminal_execution_receipt(
        _write_receipt(tmp_path / "stripped.json", stripped), document, campaign_id,
    ) is False
    forged = copy.deepcopy(result)
    forged["campaignAbort"]["retryAllowed"] = True
    assert runtime._terminal_execution_receipt(
        _write_receipt(tmp_path / "forged.json", forged), document, campaign_id,
    ) is False
    forged_identity = copy.deepcopy(result)
    forged_identity["campaignAbort"]["campaignId"] = "hotel-v1-20260830t010203z-feedface"
    assert runtime._terminal_execution_receipt(
        _write_receipt(tmp_path / "forged-identity.json", forged_identity), document, campaign_id,
    ) is False
    forged_digest = copy.deepcopy(result)
    forged_digest["campaignAbort"]["abortCanonicalSha256"] = "a" * 64
    assert runtime._terminal_execution_receipt(
        _write_receipt(tmp_path / "forged-digest.json", forged_digest), document, campaign_id,
    ) is False


def test_compiled_schedule_is_immutable_across_the_whole_driver(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    contracts = runtime.frozen_cell_contracts(document)
    assert [row["ordinal"] for row in contracts] == list(range(1, runtime.CELL_COUNT + 1))

    # A cell that differs from its compiled position raises rather than adapting.
    drifted = copy.deepcopy(contracts[4])
    # Drift to another SUPPORTED posture, so the refusal is the schedule check
    # and not an unsupported-posture reject.
    drifted["runKey"]["posture"] = "selected" if drifted["runKey"]["posture"] != "selected" else "metrics"
    with pytest.raises(runtime.GateError):
        runtime._assert_scheduled_cell(contracts, 5, drifted)
    with pytest.raises(runtime.GateError):
        runtime._assert_scheduled_cell(contracts, 6, contracts[4])
    with pytest.raises(runtime.GateError):
        runtime._assert_scheduled_cell(contracts, 25, contracts[4])
    with pytest.raises(runtime.GateError, match="outside the compiled schedule"):
        runtime._assert_scheduled_cell(contracts, runtime.CELL_COUNT + 1, contracts[4])


def test_driver_refuses_an_admission_bound_to_another_compiled_plan(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    document["bindings"]["compiledPlanCanonicalSha256"] = "0" * 64
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    transport = OrchestratedTransport()
    with pytest.raises(runtime.GateError):
        runtime.execute_campaign(document, transport)
    assert transport.dispatched == []


def test_deadline_reserve_stops_the_campaign_and_abstains(tmp_path: Path):
    document = admission(tmp_path / "campaign")
    document["bindings"]["deadline"] = "2026-01-01T00:00:00Z"
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    transport = OrchestratedTransport()
    result = runtime.execute_campaign(
        document, transport, clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result["status"] == "stopped-deadline"
    assert transport.dispatched == []
    abort = json.loads((tmp_path / "campaign" / runtime.CONTROLLER_ABORT_NAME).read_text())
    assert abort["stage"] == "cell-execution"
    assert abort["validCells"] == 0 and abort["journalRows"] == 0
    assert abort["journalChainHeadSha256"] == "0" * 64
    assert abort["experimentalState"] == "ABSTAINED"


def test_one_shot_never_dispatches_a_cell_twice(tmp_path: Path):
    document = admission(tmp_path / "campaign")

    class RetryHungryTransport(OrchestratedTransport):
        def run_cell(self, document_, contract):
            if contract["runId"] in self.dispatched:
                raise AssertionError("compiled cell was dispatched a second time")
            return super().run_cell(document_, contract)

    transport = RetryHungryTransport(blocked_ordinal=4)
    result = runtime.execute_campaign(document, transport)
    assert result["status"] == "stopped-invalid-cell"
    assert len(transport.dispatched) == len(set(transport.dispatched)) == 4


def test_target_transport_explicitly_releases_persistent_flock_and_retains_cleanup(
    monkeypatch, tmp_path: Path,
):
    artifact = tmp_path / "campaign"
    artifact.mkdir()
    lease_path = tmp_path / ".persistent-hotel.lock"
    document = admission(artifact)
    document["bindings"]["leasePath"] = str(lease_path)
    document["bindings"]["leaseRoot"] = str(tmp_path)
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    owner = {
        "schemaVersion": 1,
        "kind": "hotel-candidate-runtime-lease-v1",
        "campaignId": document["bindings"]["campaignId"],
        "admissionCanonicalSha256": document["admissionCanonicalSha256"],
        "deadline": document["bindings"]["deadline"],
        "projectPrefix": document["bindings"]["projectPrefix"],
        "ports": document["bindings"]["ports"],
    }
    lease_path.write_bytes(runtime.canonical_bytes(owner) + b"\n")
    lease_fd = os.open(lease_path, os.O_RDWR)
    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    monkeypatch.setattr(runtime.os, "getuid", lambda: 1007)
    monkeypatch.setattr(runtime.os, "getgid", lambda: 1007)
    monkeypatch.setattr(runtime.os, "getgroups", lambda: [27, 998])
    transport = runtime.TargetComposeTransport(document, lease_fd)
    projects = [row["project"] for row in runtime.cell_contracts(document)]
    transport._cleanup_receipt = {
        "ownedResourcesRemaining": [], "projectsChecked": projects,
    }
    assert transport.acquire_lease(document)["acquired"] is True
    release = transport.release_lease(document)
    assert release["releaseMechanism"] == "root-supervisor-release-after-terminal-seal"
    assert release["persistentLeaseFileRetained"] is True
    assert lease_path.is_file()
    cleanup = runtime._json_file(artifact / "campaign-cleanup.json", "cleanup")
    assert cleanup == {
        "schemaVersion": 1,
        "kind": "hotel-candidate-campaign-cleanup-v1",
        "ownedProjects": projects,
        "ownedResourcesRemaining": {"containers": [], "networks": [], "volumes": []},
        "foreignResourcesMutated": False,
        "leaseReleased": False,
        "artifactDeletionAttempted": False,
    }
    reusable = os.open(lease_path, os.O_RDWR)
    try:
        fcntl.flock(reusable, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(reusable, fcntl.LOCK_UN)
    finally:
        os.close(reusable)


def test_target_transport_watches_corrupt_retained_cleanup(monkeypatch, tmp_path: Path):
    artifact = tmp_path / "campaign"
    artifact.mkdir()
    lease_path = tmp_path / ".persistent-hotel.lock"
    document = admission(artifact)
    document["bindings"]["leasePath"] = str(lease_path)
    document["bindings"]["leaseRoot"] = str(tmp_path)
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    owner = {
        "campaignId": document["bindings"]["campaignId"],
        "admissionCanonicalSha256": document["admissionCanonicalSha256"],
    }
    lease_path.write_bytes(runtime.canonical_bytes(owner) + b"\n")
    lease_fd = os.open(lease_path, os.O_RDWR)
    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    monkeypatch.setattr(runtime.os, "getuid", lambda: 1007)
    monkeypatch.setattr(runtime.os, "getgid", lambda: 1007)
    monkeypatch.setattr(runtime.os, "getgroups", lambda: [27, 998])
    transport = runtime.TargetComposeTransport(document, lease_fd)
    projects = [row["project"] for row in runtime.cell_contracts(document)]
    transport._cleanup_receipt = {
        "ownedResourcesRemaining": [], "projectsChecked": projects,
    }
    write_exact = runtime._write_exclusive_json

    def plant_corrupt_cleanup(path, value, **kwargs):
        planted = copy.deepcopy(value)
        planted["leaseReleased"] = True
        write_exact(path, planted, **kwargs)

    monkeypatch.setattr(runtime, "_write_exclusive_json", plant_corrupt_cleanup)
    with pytest.raises(runtime.GateError, match="retained campaign cleanup differs"):
        transport.release_lease(document)


def test_target_release_does_not_reacquire_against_a_planted_successor(
    monkeypatch, tmp_path: Path,
):
    artifact = tmp_path / "campaign"
    artifact.mkdir()
    lease_path = tmp_path / ".persistent-hotel.lock"
    document = admission(artifact)
    document["bindings"]["leasePath"] = str(lease_path)
    document["bindings"]["leaseRoot"] = str(tmp_path)
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    owner = {
        "campaignId": document["bindings"]["campaignId"],
        "admissionCanonicalSha256": document["admissionCanonicalSha256"],
    }
    lease_path.write_bytes(runtime.canonical_bytes(owner) + b"\n")
    lease_fd = os.open(lease_path, os.O_RDWR)
    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    monkeypatch.setattr(runtime.os, "getuid", lambda: 1007)
    monkeypatch.setattr(runtime.os, "getgid", lambda: 1007)
    monkeypatch.setattr(runtime.os, "getgroups", lambda: [27, 998])
    transport = runtime.TargetComposeTransport(document, lease_fd)
    transport._cleanup_receipt = {
        "ownedResourcesRemaining": [],
        "projectsChecked": [row["project"] for row in runtime.cell_contracts(document)],
    }
    real_flock = fcntl.flock
    successor_active = False
    child_unlock_attempted = False

    def planted_successor(descriptor, operation):
        nonlocal successor_active, child_unlock_attempted
        if successor_active and operation & fcntl.LOCK_EX:
            raise BlockingIOError("planted successor owns the shared lease")
        result = real_flock(descriptor, operation)
        if descriptor == lease_fd and operation == fcntl.LOCK_UN:
            child_unlock_attempted = True
        return result

    monkeypatch.setattr(runtime.fcntl, "flock", planted_successor)
    release = transport.release_lease(document)
    assert successor_active is False
    assert child_unlock_attempted is False
    assert release["released"] is True
    assert (artifact / "campaign-cleanup.json").is_file()


@pytest.mark.parametrize("return_code", (None, 78, 137))
def test_target_supervisor_retains_and_validates_preexecute_or_abrupt_abort(
    monkeypatch, tmp_path: Path, return_code: int | None,
):
    # supervise_target_controller runs ON fb14srv4 and resolves its own
    # runuser/python3 spelling there; this laptop has neither, so stand in for
    # fb14srv4 by taking the first (fb14srv4-preferred) candidate. The argv
    # assertion below still pins the exact spelling fb14srv4 resolves to.
    monkeypatch.setattr(
        runtime, "_resolve_target_binary", lambda name, candidates: candidates[0]
    )
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    control_root = tmp_path / "control"
    control = control_root / campaign_id
    control.mkdir(parents=True)
    lease_path = tmp_path / ".lease"
    artifact = tmp_path / "evidence" / campaign_id
    # The installer creates the artifact parent; the supervisor writes the
    # execution-user copy of the admission beside the child's receipt path.
    artifact.parent.mkdir(parents=True)
    document = admission(artifact)
    supervisor_now = datetime(2026, 8, 30, 0, 0, 1, tzinfo=timezone.utc)
    document["bindings"].update({
        "campaignId": campaign_id,
        "controlRoot": str(control_root),
        "checkoutRoot": str(ROOT),
        "leasePath": str(lease_path),
        "leaseRoot": str(tmp_path),
        "readinessObservedAt": "2026-08-30T00:00:00Z",
        "deadline": "2026-08-30T05:00:01Z",
    })
    document["issuedAt"] = "2026-08-30T00:00:01Z"
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    admission_path = control / "runtime-admission.json"
    receipt_path = control / "execution-receipt.json"
    abort_path = control / "campaign-abort.json"
    write_json(admission_path, document)
    lease_path.write_bytes(runtime.canonical_bytes({
        "campaignId": campaign_id,
        "admissionCanonicalSha256": document["admissionCanonicalSha256"],
    }) + b"\n")
    lease_fd = os.open(lease_path, os.O_RDWR)
    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    monkeypatch.setitem(runtime.TARGET, "controlRoot", str(control_root))
    monkeypatch.setitem(runtime.TARGET, "checkoutRoot", str(ROOT))
    monkeypatch.setitem(runtime.TARGET, "leasePath", str(lease_path))
    monkeypatch.setattr(runtime.os, "geteuid", lambda: 0)
    monkeypatch.setattr(runtime.os, "fchown", lambda *_args: None)
    observed = []
    monkeypatch.setattr(
        runtime, "_root_terminal_observation_and_seal",
        lambda *_args, **_kwargs: observed.append(return_code) or {},
    )

    class ExitedController:
        pid = 4242
        def wait(self, timeout): return return_code
        def poll(self): return return_code

    calls = []

    def planted_controller(*args, **kwargs):
        calls.append((args, kwargs))
        if return_code is None:
            raise OSError("planted pre-Popen target-controller failure")
        return ExitedController()

    result = runtime.supervise_target_controller(
        admission_path, receipt_path, abort_path, lease_fd,
        popen_factory=planted_controller,
        clock=lambda: supervisor_now,
    )
    assert result["completionArtifact"] == "campaign-abort.json"
    retained = runtime._json_file(abort_path, "retained abort")
    assert runtime.validate_campaign_abort(retained, document, campaign_id) == retained
    assert retained["childReturnCode"] == return_code
    assert observed == [return_code]
    assert retained["candidateCampaignValid"] is False
    assert calls[0][0][0][:6] == [
        "/usr/sbin/runuser", "--user", "fhuebscher", "--", "/usr/bin/python3", "-I",
    ]
    assert calls[0][1]["pass_fds"] == (lease_fd,)
    assert calls[0][1]["start_new_session"] is False

    planted = copy.deepcopy(retained)
    planted["candidateCampaignValid"] = True
    planted_body = {key: value for key, value in planted.items() if key != "abortCanonicalSha256"}
    planted["abortCanonicalSha256"] = runtime.canonical_sha256(planted_body)
    with pytest.raises(runtime.GateError, match="terminal semantics"):
        runtime.validate_campaign_abort(planted, document, campaign_id)

    reusable = os.open(lease_path, os.O_RDWR)
    try:
        fcntl.flock(reusable, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(reusable, fcntl.LOCK_UN)
    finally:
        os.close(reusable)


def test_execute_campaign_turns_terminal_validation_exception_into_durable_state(tmp_path: Path):
    document = admission(tmp_path / "campaign")

    class InvalidTerminal:
        transport_id = "ssh-compose"
        target = "fb14srv4"

        def acquire_lease(self, _admission): return {"acquired": True}
        def preflight(self, _admission): return {"passed": True}

        def prepare_campaign(self, admission):
            Path(admission["bindings"]["artifactRoot"]).mkdir(mode=0o700)
            return {"prepared": True}

        def record_attempt_start(self, _admission, contract):
            return {"kind": "hotel-candidate-attempt-start-v1", "runId": contract["runId"]}
        def run_cell(self, _admission, contract):
            return {"candidateCellValid": True, "runId": contract["runId"]}
        def cleanup(self, _admission): return {"ownedResourcesRemaining": []}
        def release_lease(self, _admission): return {"released": True}
        def validate_campaign(self, _admission):
            raise RuntimeError("planted terminal validation defect")

    result = runtime.execute_campaign(document, InvalidTerminal())
    assert result["status"] == "stopped-invalid-campaign"
    assert result["attemptedCells"] == runtime.CELL_COUNT
    assert result["errors"] == [{
        "phase": "campaign-validation",
        "type": "RuntimeError",
        "message": "planted terminal validation defect",
    }]
    # Every cell was valid, but the campaign still abstains rather than
    # claiming a partial result.
    assert result["journal"]["validCells"] == runtime.CELL_COUNT
    assert result["journal"]["complete"] is True
    assert result["campaignAbort"]["stage"] == "terminal-validation"
    assert result["campaignAbort"]["experimentalState"] == "ABSTAINED"


def test_refetch_retains_invalid_terminal_without_claiming_pass_replay(monkeypatch, tmp_path: Path):
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    document = admission(Path(runtime.TARGET["artifactParent"]) / campaign_id)
    document["bindings"]["artifactParent"] = runtime.TARGET["artifactParent"]
    document["bindings"]["artifactRoot"] = runtime.TARGET["artifactParent"] + "/" + campaign_id
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    execution = {
        "schemaVersion": 1,
        "kind": "hotel-candidate-execution-receipt-v1",
        "status": "stopped-invalid-campaign",
        "scheduledCells": runtime.CELL_COUNT,
        "attemptedCells": runtime.CELL_COUNT,
        "records": [{"runId": f"run-{index}", "receipt": {}} for index in range(runtime.CELL_COUNT)],
        "cleanup": {"ownedResourcesRemaining": []},
        "leaseRelease": {"released": True},
        "errors": [{
            "phase": "campaign-validation", "type": "TerminalError",
            "message": "planted invalid campaign",
        }],
        "runtimeAuthorized": True,
        "promotionAuthorized": False,
    }
    archive_bytes = sealed_terminal_archive(
        campaign_id, document, "execution-receipt.json", execution,
    )
    monkeypatch.setattr(runtime.DetachedSshController, "status", lambda _self, _campaign: {
        "running": False, "terminal": True,
        "completionArtifact": "execution-receipt.json",
        "executionReceiptPresent": True, "campaignAbortPresent": False,
        # A successor now owns the shared persistent flock.  That must not
        # make this already-terminal predecessor non-refetchable.
        "leasePresent": True, "leaseLocked": True,
        "leaseOwnedByCampaign": False, "leaseLockedByCampaign": False,
    })

    def fake_run(command, **kwargs):
        kwargs["stdout"].write(archive_bytes)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runtime, "validate_local_replay_binding",
        lambda _admission: pytest.fail("invalid terminal attempted a pass replay"),
    )
    result = runtime.DetachedSshController().refetch_and_replay(
        campaign_id, tmp_path / "fetched",
    )
    assert result["targetExecutionStatus"] == "stopped-invalid-campaign"
    assert result["localReplayPerformed"] is False
    assert result["status"] == "target-terminal-retained-no-pass-replay"
    assert (tmp_path / "fetched/local-terminal-refetch.json").is_file()


def test_refetch_retains_supervisor_abort_and_never_attempts_pass_replay(
    monkeypatch, tmp_path: Path,
):
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    document = admission(Path(runtime.TARGET["artifactParent"]) / campaign_id)
    document["bindings"]["artifactParent"] = runtime.TARGET["artifactParent"]
    document["bindings"]["artifactRoot"] = runtime.TARGET["artifactParent"] + "/" + campaign_id
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    abort = runtime._campaign_abort_document(
        document, failure_type="PlantedPackageValidationFailure",
        failure_message="planted", child_return_code=78,
        execution_receipt_present=False,
    )
    archive_bytes = sealed_terminal_archive(
        campaign_id, document, "campaign-abort.json", abort,
    )
    monkeypatch.setattr(runtime.DetachedSshController, "status", lambda _self, _campaign: {
        "running": False, "terminal": True,
        "completionArtifact": "campaign-abort.json",
        "executionReceiptPresent": False, "campaignAbortPresent": True,
        "leasePresent": True, "leaseLocked": False,
        "leaseOwnedByCampaign": True, "leaseLockedByCampaign": False,
    })

    def fake_run(command, **kwargs):
        kwargs["stdout"].write(archive_bytes)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runtime, "validate_local_replay_binding",
        lambda _admission: pytest.fail("campaign abort attempted a pass replay"),
    )
    result = runtime.DetachedSshController().refetch_and_replay(
        campaign_id, tmp_path / "fetched-abort",
    )
    assert result["targetExecutionStatus"] == "campaign-abort"
    assert result["status"] == "target-abort-retained-no-pass-replay"
    assert result["localReplayPerformed"] is False
    assert result["targetAbortCanonicalSha256"] == abort["abortCanonicalSha256"]


def test_terminal_tree_seal_watches_post_terminal_receipt_rewrite(tmp_path):
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    control = tmp_path / "control" / campaign_id
    artifact = tmp_path / "evidence" / campaign_id
    control.mkdir(parents=True); artifact.mkdir(parents=True)
    document = admission(artifact)
    document["bindings"]["campaignId"] = campaign_id
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    abort = runtime._campaign_abort_document(
        document, failure_type="Planted", failure_message="before seal",
        child_return_code=137, execution_receipt_present=False,
    )
    write_json(control / "runtime-admission.json", document)
    write_json(control / "campaign-abort.json", abort)
    observation = root_observation(document)
    write_json(control / "root-cleanup-observation.json", observation)
    entries = [{
        "tree": "control", "path": path.name, "size": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    } for path in sorted(control.iterdir())]
    seal_body = {
        "schemaVersion": 1, "kind": "hotel-srv4-terminal-tree-seal-v1",
        "campaignId": campaign_id, "sealedAt": "2026-08-30T01:00:00Z",
        "entries": entries, "entriesCanonicalSha256": runtime.canonical_sha256(entries),
        "rootObservationSha256": runtime.canonical_sha256(observation),
        "ownedResourcesState": "observed",
        "ownedResourcesRemaining": observation["ownedResourcesRemaining"],
    }
    write_json(control / "terminal-tree-seal.json", {
        **seal_body, "sealCanonicalSha256": runtime.canonical_sha256(seal_body),
    })
    runtime.validate_terminal_tree_seal(control, artifact, document)
    attacked = copy.deepcopy(abort); attacked["failureMessage"] = "rewritten after seal"
    write_json(control / "campaign-abort.json", attacked)
    with pytest.raises(runtime.GateError, match="retained bytes"):
        runtime.validate_terminal_tree_seal(control, artifact, document)


def test_terminal_tree_seal_watches_cleanup_semantic_forgery(tmp_path):
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    control = tmp_path / "control" / campaign_id
    artifact = tmp_path / "evidence" / campaign_id
    control.mkdir(parents=True); artifact.mkdir(parents=True)
    document = admission(artifact)
    document["bindings"]["campaignId"] = campaign_id
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    abort = runtime._campaign_abort_document(
        document, failure_type="Planted", failure_message="semantic attacks",
        child_return_code=137, execution_receipt_present=False,
    )
    write_json(control / "runtime-admission.json", document)
    write_json(control / "campaign-abort.json", abort)

    def seal(observation: dict, *, claimed=None):
        write_json(control / "root-cleanup-observation.json", observation)
        entries = [{
            "tree": "control", "path": path.name, "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        } for path in sorted(control.iterdir()) if path.name != "terminal-tree-seal.json"]
        seal_body = {
            "schemaVersion": 1, "kind": "hotel-srv4-terminal-tree-seal-v1",
            "campaignId": campaign_id, "sealedAt": "2026-08-30T01:00:00Z",
            "entries": entries, "entriesCanonicalSha256": runtime.canonical_sha256(entries),
            "rootObservationSha256": runtime.canonical_sha256(observation),
            "ownedResourcesState": observation.get("state"),
            "ownedResourcesRemaining": (
                observation.get("ownedResourcesRemaining") if claimed is None else claimed
            ),
        }
        write_json(control / "terminal-tree-seal.json", {
            **seal_body, "sealCanonicalSha256": runtime.canonical_sha256(seal_body),
        })

    live = root_observation(document)
    first = live["projectsChecked"][0]
    live["ownedResourcesRemaining"][first]["containers"] = ["live-container-id"]
    seal(live, claimed={})
    with pytest.raises(runtime.GateError, match="retained bytes"):
        runtime.validate_terminal_tree_seal(control, artifact, document)

    for planted in (
        {**root_observation(document), "projectsChecked": []},
        {**root_observation(document), "ownedResourcesRemaining": {}},
        {**root_observation(document), "ownedResourcesRemaining": {
            **root_observation(document)["ownedResourcesRemaining"],
            first: {"containers": [], "networks": []},
        }},
    ):
        seal(planted)
        with pytest.raises(runtime.GateError, match="observation"):
            runtime.validate_terminal_tree_seal(control, artifact, document)

    seal(root_observation(document))
    (control / "root-cleanup-observation.json").unlink()
    with pytest.raises(runtime.GateError, match="root cleanup observation"):
        runtime.validate_terminal_tree_seal(control, artifact, document)


def test_root_terminal_observation_checks_all_projects_and_retains_typed_unknown(
    monkeypatch, tmp_path,
):
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    control = tmp_path / "control" / campaign_id
    artifact = tmp_path / "evidence" / campaign_id
    control.mkdir(parents=True); artifact.mkdir(parents=True)
    document = admission(artifact)
    document["bindings"].update({"campaignId": campaign_id, "controlRoot": str(control.parent)})
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    write_json(control / "runtime-admission.json", document)
    calls = []

    def planted_observation(command, **_kwargs):
        calls.append(command)
        if len(calls) == 7:
            return subprocess.CompletedProcess(command, 1, "", "planted Docker observation failure")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runtime.subprocess, "run", planted_observation)
    monkeypatch.setattr(runtime.os, "fchown", lambda *_args: None)
    seal = runtime._root_terminal_observation_and_seal(document, control)
    observation = runtime._json_file(
        control / "root-cleanup-observation.json", "root cleanup observation",
    )
    assert len(calls) == runtime.CELL_COUNT * 3
    assert observation["state"] == "unknown"
    assert observation["ownedResourcesRemaining"] is None
    assert observation["failures"] == [{
        "project": observation["projectsChecked"][2], "resource": "containers",
        "type": "GateError",
        "message": "root terminal observation cannot list ps for "
        + observation["projectsChecked"][2],
    }]
    assert seal["ownedResourcesState"] == "unknown"
    assert seal["ownedResourcesRemaining"] is None


def test_local_replay_requires_exact_clean_admitted_revision_and_controllers(monkeypatch, tmp_path: Path):
    current = bindings()
    document = admission(tmp_path / "campaign")
    document["bindings"].update(runtime.plan_binding(current))
    monkeypatch.setattr(runtime, "inspect_bindings", lambda _commit: current)
    assert runtime.validate_local_replay_binding(document) == current
    changed = dataclasses.replace(
        current,
        controller_sha256={**current.controller_sha256, "candidate-terminal": "0" * 64},
    )
    monkeypatch.setattr(runtime, "inspect_bindings", lambda _commit: changed)
    with pytest.raises(runtime.GateError, match="local replay revision"):
        runtime.validate_local_replay_binding(document)
    changed_descriptor = dataclasses.replace(current, descriptor_sha256="0" * 64)
    monkeypatch.setattr(runtime, "inspect_bindings", lambda _commit: changed_descriptor)
    with pytest.raises(runtime.GateError, match="local replay revision"):
        runtime.validate_local_replay_binding(document)


def make_plan(run_id: str = "no-fault-cost-b01-none-a01") -> dict:
    return workload.build_plan(
        run_id,
        runtime._load_compiler().EXPECTED_PLAN_SHA256,
        datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc),
        1000.0,
        created_at=datetime(2026, 8, 30, 0, 59, tzinfo=timezone.utc),
    )


def make_ledger(plan: dict, path: Path) -> list[dict]:
    previous = "0" * 64
    rows = []
    for index, opportunity in enumerate(plan["opportunities"]):
        result = {
            **opportunity,
            "actualStartMonotonic": 1000.0 + opportunity["scheduledMonotonicOffsetSeconds"],
            "actualEndMonotonic": 1000.01 + opportunity["scheduledMonotonicOffsetSeconds"],
            "startedAt": opportunity["scheduledAt"],
            "endedAt": opportunity["scheduledAt"],
            "outcome": "completed",
            "statusCode": 200,
            "error": None,
            "terminalSettled": True,
        }
        row = workload._ledger_record(result, index, previous, plan)
        rows.append(row)
        previous = row["recordSha256"]
    path.write_bytes(b"".join(workload.canonical_bytes(row) + b"\n" for row in rows))
    return rows


def test_opportunity_chain_watches_reorder_and_naive_time(tmp_path: Path):
    plan = make_plan()
    ledger = tmp_path / "ledger.jsonl"
    rows = make_ledger(plan, ledger)
    assert workload.validate_ledger(plan, ledger)["offered"] == 1200
    rows[7]["recordSequence"] = 8
    ledger.write_bytes(b"".join(workload.canonical_bytes(row) + b"\n" for row in rows))
    with pytest.raises(workload.LedgerError):
        workload.validate_ledger(plan, ledger)
    with pytest.raises(workload.LedgerError, match="timezone aware"):
        workload.build_plan(
            plan["runId"], plan["compiledPlanSha256"],
            datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc), 1000.0,
            created_at=datetime(2026, 8, 30, 0, 59),
        )


def test_emitted_byte_replay_is_scoped_and_never_claims_wire_bytes():
    row = {
        "schema": "hotel-source-emitted-span-v1",
        "service": "frontend",
        "traceId": "1" * 16,
        "spanId": "2" * 16,
        "startedAtUnixNano": 110,
        "endedAtUnixNano": 120,
        "compactThriftSpanBytes": 91,
        "wireBytes": False,
    }
    document = resources.parse_emissions(
        "prefix OBSPLACEMENT_EMISSION " + json.dumps(row), 100, 200
    )
    assert resources.validate_emissions(document) == {
        "schemaVersion": 1,
        "kind": "hotel-candidate-emission-validation-v1",
        "verdict": "pass",
        "eventCount": 1,
        "compactThriftSpanBytes": 91,
        "wireBytes": None,
        "wireBytesState": "unsupported",
    }
    attacked = copy.deepcopy(row)
    attacked["wireBytes"] = True
    with pytest.raises(resources.ResourceError):
        resources.parse_emissions("OBSPLACEMENT_EMISSION " + json.dumps(attacked), 100, 200)


def test_cpu_replay_rejects_foreign_or_missing_application_scope():
    identities = {f"{index:064x}": service for index, service in enumerate(resources.APPLICATION_SERVICES, 1)}

    def sample(at: float, value: float):
        rows = [
            {"service": service, "containerId": container, "cpuPercent": value}
            for container, service in identities.items()
        ]
        return {
            "capturedAtEpoch": 100.0 + at,
            "capturedAtMonotonic": at,
            "containers": rows,
            "applicationCpuPercent": len(rows) * value,
        }

    document = {
        "schemaVersion": 1,
        "contract": resources.RESOURCE_CONTRACT,
        "project": "hotel_candidate_v4_deadbeef_01",
        "applicationServices": list(resources.APPLICATION_SERVICES),
        "containerIdentities": identities,
        "windowStartMonotonic": 10.0,
        "windowEndMonotonic": 12.0,
        "intervalSeconds": 1.0,
        "samples": [sample(10.0, 10.0), sample(11.0, 20.0), sample(12.0, 30.0)],
        "captureComplete": True,
            "applicationCpuSeconds": 3.0,
    }
    assert resources.validate_cpu(document)["applicationCpuSeconds"] == pytest.approx(3.0)
    attacked = copy.deepcopy(document)
    attacked["samples"][0]["containers"][0]["service"] = "mongo"
    with pytest.raises(resources.ResourceError, match="scope"):
        resources.validate_cpu(attacked)


def test_cpu_collector_waits_for_the_admitted_measurement_barrier(monkeypatch):
    current = [95.0]
    observed_sample_times = []

    def monotonic():
        return current[0]

    def sleep(seconds):
        current[0] += seconds

    identities = {
        str(index) * 64: service
        for index, service in enumerate(resources.APPLICATION_SERVICES, 1)
    }

    def sample(_identities):
        observed_sample_times.append(current[0])
        rows = [
            {"service": service, "containerId": container, "cpuPercent": 10.0}
            for container, service in identities.items()
        ]
        return {
            "capturedAtEpoch": 1.0,
            "capturedAtMonotonic": current[0],
            "containers": rows,
            "applicationCpuPercent": 100.0,
        }

    monkeypatch.setattr(resources.time, "monotonic", monotonic)
    monkeypatch.setattr(resources.time, "sleep", sleep)
    result = resources.collect_cpu(
        "hotel_candidate_v4_deadbeef_01", identities,
        100.0, 101.0, interval_seconds=0.5, sample=sample,
    )
    # One pre-barrier priming call (not retained), then admitted samples from
    # FIRST_SAMPLE_LEAD_SECONDS before the barrier: docker stats returns 1-2 s
    # after it is issued, and the replay integrates from the window start only.
    lead = resources.FIRST_SAMPLE_LEAD_SECONDS
    assert observed_sample_times == [95.0, 100.0 - lead, 99.0, 99.5, 100.0, 100.5]
    assert [row["capturedAtMonotonic"] for row in result["samples"]] == [
        100.0 - lead, 99.0, 99.5, 100.0, 100.5]
    assert result["captureComplete"] is True
    # Only the in-window part of the samples is integrated: 1.0 s at 100 %.
    assert abs(result["applicationCpuSeconds"] - 1.0) < 1e-9


def test_fault_truth_requires_independent_precondition_and_observed_recovery():
    receipt = {
        "schemaVersion": 1,
        "faultKind": "pause",
        "scenario": "search-pause",
        "targetService": "search",
        "scheduledAtSeconds": 45,
        "requestedOutageSeconds": 15,
        "startedAt": "2026-08-30T01:00:45Z",
        "endedAt": "2026-08-30T01:01:01Z",
        "manifested": True,
        "outageObserved": True,
        "recovered": True,
        "successful": True,
        "preState": {"running": True, "paused": False},
        "preRouteAvailable": True,
        "duringState": {"running": True, "paused": True},
        "recoveryState": {"running": True, "paused": False},
        "startedMonotonic": 1045.0,
        "appliedMonotonic": 1045.2,
        "revertingMonotonic": 1059.9,
        "unpausedAtMonotonic": 1060.0,
        "readyAtMonotonic": 1060.5,
        "endedMonotonic": 1061.0,
        "commands": [
            {"action": "pause", "returnCode": 0, "stdout": "", "stderr": ""},
            {"action": "unpause", "returnCode": 0, "stdout": "", "stderr": ""},
        ],
        "error": None,
        "actualOutageSeconds": 15.0,
    }
    validated = witness.validate_fault_receipt(
        receipt, "search-pause", barrier_monotonic=1000.0,
    )
    assert validated["state"] == "supported"
    assert validated["faultKind"] == "pause"
    assert validated["detectionWindowMonotonic"] == [1045.2, 1059.9]
    # A pause receipt is not a degradation receipt: the scenario picks the shape.
    with pytest.raises(witness.WitnessError, match="fields differ"):
        witness.validate_fault_receipt(receipt, "profile-cpu-throttle")
    wrong_kind = copy.deepcopy(receipt)
    wrong_kind["faultKind"] = "degradation"
    with pytest.raises(witness.WitnessError):
        witness.validate_fault_receipt(wrong_kind, "search-pause")
    attacked = copy.deepcopy(receipt)
    attacked["preRouteAvailable"] = False
    with pytest.raises(witness.WitnessError):
        witness.validate_fault_receipt(attacked, "search-pause")
    late = copy.deepcopy(receipt)
    late["startedMonotonic"] = 1048.0
    late["appliedMonotonic"] = 1048.2
    with pytest.raises(witness.WitnessError, match="45-second"):
        witness.validate_fault_receipt(
            late, "search-pause", barrier_monotonic=1000.0,
        )


def test_real_compose_merge_applies_posture_to_all_ten_tracing_services(tmp_path):
    services = (
        "frontend", "search", "geo", "rate", "reservation", "profile",
        "user", "recommendation", "review", "attractions",
    )
    base = tmp_path / "compose.yml"
    base.write_text("services:\n" + "".join(
        f"  {name}:\n    image: placeholder\n" for name in terminal.COMPOSE_SERVICES
    ))
    overlay = MODULE / "deployment/compose.observability-placement.yml"
    # (others, frontend): uniform on, uniform off, and `selected` = frontend alone.
    for others, front in (("1", "1"), ("0", "0"), ("0", "1")):
        environment = {
            **os.environ,
            "HR_JAEGER_SAMPLE_RATIO": others,
            "HR_JAEGER_DISABLED": "false" if others == "1" else "true",
            "HR_FRONTEND_JAEGER_SAMPLE_RATIO": front,
            "HR_FRONTEND_JAEGER_DISABLED": "false" if front == "1" else "true",
            "HR_SOURCE_SHA256": "a" * 64,
        }
        rendered = subprocess.run(
            ["docker", "compose", "-f", str(base), "-f", str(overlay),
             "config", "--format", "json"],
            check=True, capture_output=True, text=True, env=environment,
        )
        document = json.loads(rendered.stdout)
        expected = {name: front if name == "frontend" else others for name in services}
        assert {
            name: str(document["services"][name]["environment"]["JAEGER_SAMPLE_RATIO"])
            for name in services
        } == expected
        assert {
            name: str(document["services"][name]["environment"]["JAEGER_DISABLED"]).lower()
            for name in services
        } == {name: "false" if value == "1" else "true" for name, value in expected.items()}
    # Planted: frontend's own pair unset must not silently default to tracing on.
    environment = {**os.environ, "HR_JAEGER_SAMPLE_RATIO": "0", "HR_SOURCE_SHA256": "a" * 64}
    for key in ("HR_FRONTEND_JAEGER_SAMPLE_RATIO", "HR_FRONTEND_JAEGER_DISABLED"):
        environment.pop(key, None)
    refused = subprocess.run(
        ["docker", "compose", "-f", str(base), "-f", str(overlay), "config", "--format", "json"],
        capture_output=True, text=True, env=environment,
    )
    assert refused.returncode != 0 and "HR_FRONTEND_JAEGER" in refused.stderr


def test_partial_posture_trace_admits_only_traced_services():
    frontend_only = [
        {"traceId": "a" * 16, "spanId": "01", "parentSpanId": None,
         "service": "frontend", "parentService": None},
        {"traceId": "a" * 16, "spanId": "02", "parentSpanId": "01",
         "service": "frontend", "parentService": "frontend"},
    ]
    witness._validate_partial_trace("a" * 16, frontend_only, frozenset({"frontend"}))
    leaked = copy.deepcopy(frontend_only) + [
        {"traceId": "a" * 16, "spanId": "03", "parentSpanId": "02",
         "service": "search", "parentService": "frontend"},
    ]
    with pytest.raises(witness.WitnessError, match="untraced service"):
        witness._validate_partial_trace("a" * 16, leaked, frozenset({"frontend"}))
    with pytest.raises(witness.WitnessError):
        witness._validate_partial_trace("a" * 16, [], frozenset({"frontend"}))
    assert witness.SUPPORTED_POSTURES == ("none", "metrics", "selected", "full")
    assert "selected" not in witness.EMPTY_CAPTURE_POSTURES


def test_native_trace_edges_are_same_trace_parent_bound_and_acyclic():
    required = [["frontend", "search"], ["search", "geo"]]
    valid = [
        {"traceId": "a" * 16, "spanId": "01", "parentSpanId": None,
         "service": "frontend", "parentService": None},
        {"traceId": "a" * 16, "spanId": "02", "parentSpanId": "01",
         "service": "search", "parentService": "frontend"},
        {"traceId": "a" * 16, "spanId": "03", "parentSpanId": "02",
         "service": "geo", "parentService": "search"},
    ]
    witness._validate_native_trace("a" * 16, valid, required)
    planted = []
    missing = copy.deepcopy(valid); missing[2]["parentSpanId"] = "ff"; planted.append(missing)
    wrong = copy.deepcopy(valid); wrong[2]["parentService"] = "frontend"; planted.append(wrong)
    cross_trace = copy.deepcopy(valid); cross_trace[2]["parentSpanId"] = "99"; planted.append(cross_trace)
    cycle = copy.deepcopy(valid); cycle[0]["parentSpanId"] = "03"; cycle[0]["parentService"] = "geo"; planted.append(cycle)
    for defect in planted:
        with pytest.raises(witness.WitnessError):
            witness._validate_native_trace("a" * 16, defect, required)


def test_full_correlation_requires_bijective_opportunity_token_to_native_root(tmp_path):
    plan = make_plan("no-fault-cost-b01-full-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    application_log = "\n".join(
        "OBSPLACEMENT_WITNESS " + json.dumps({
            "schema": "hotel-application-request-witness-v1", "opaqueToken": row["opaqueToken"],
            "method": "GET", "routePattern": "/hotels", "statusCode": 200,
            "startedAtUnixNano": 1, "endedAtUnixNano": 2,
        }, separators=(",", ":")) for row in ledger
    ) + "\n"
    shape = [
        ("frontend", "HTTP GET /hotels", None),
        ("search", "/search.Search/Nearby", 0),
        ("geo", "/geo.Geo/Nearby", 1),
        ("rate", "/rate.Rate/GetRates", 1),
        ("reservation", "/reservation.Reservation/CheckAvailability", 0),
        ("profile", "/profile.Profile/GetProfiles", 0),
    ]
    events = []
    for trace_index, row in enumerate(ledger, 1):
        trace_id = f"{trace_index:016x}"
        for span_index, (service, operation, parent_index) in enumerate(shape, 1):
            events.append({
                "traceId": trace_id, "spanId": f"{span_index:016x}",
                "parentSpanId": None if parent_index is None else f"{parent_index + 1:016x}",
                "service": service,
                "parentService": None if parent_index is None else shape[parent_index][0],
                "operation": operation, "tags": (
                    {"obsplacement.opaque_token": row["opaqueToken"]} if parent_index is None else {}
                ),
            })
    normalized = {
        "schemaVersion": 1, "normalizer": "hotel-reservation-jaeger-v1",
        "queryLimitReached": False, "events": events,
    }
    result = witness.correlate(
        plan, ledger, application_log, normalized, posture="full", scenario=None,
        fault_receipt=None, raw={}, capture_terminal={},
        unsupported_postures=runtime.posture_ceiling()["unsupportedPostures"],
    )
    assert all(row["state"] == "supported" for row in result["rows"])
    planted = copy.deepcopy(normalized)
    planted["events"][6]["tags"]["obsplacement.opaque_token"] = ledger[0]["opaqueToken"]
    with pytest.raises(witness.WitnessError, match="bijective|multiple"):
        witness.correlate(
            plan, ledger, application_log, planted, posture="full", scenario=None,
            fault_receipt=None, raw={}, capture_terminal={},
            unsupported_postures=runtime.posture_ceiling()["unsupportedPostures"],
        )


def test_selected_correlation_admits_frontend_only_traces_and_rejects_a_leaked_span(tmp_path):
    """`selected` traces frontend alone: one tagged frontend root per request plus frontend's own
    client spans. The normal-path edges cannot exist, so the path is reported not reconstructed."""
    plan = make_plan("no-fault-cost-b01-selected-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    application_log = "\n".join(
        "OBSPLACEMENT_WITNESS " + json.dumps({
            "schema": "hotel-application-request-witness-v1", "opaqueToken": row["opaqueToken"],
            "method": "GET", "routePattern": "/hotels", "statusCode": 200,
            "startedAtUnixNano": 1, "endedAtUnixNano": 2,
        }, separators=(",", ":")) for row in ledger
    ) + "\n"
    shape = [
        ("frontend", "HTTP GET /hotels", None),
        ("frontend", "/search.Search/Nearby", 0),
        ("frontend", "/reservation.Reservation/CheckAvailability", 0),
        ("frontend", "/profile.Profile/GetProfiles", 0),
    ]
    events = []
    for trace_index, row in enumerate(ledger, 1):
        trace_id = f"{trace_index:016x}"
        for span_index, (service, operation, parent_index) in enumerate(shape, 1):
            events.append({
                "traceId": trace_id, "spanId": f"{span_index:016x}",
                "parentSpanId": None if parent_index is None else f"{parent_index + 1:016x}",
                "service": service,
                "parentService": None if parent_index is None else shape[parent_index][0],
                "operation": operation, "tags": (
                    {"obsplacement.opaque_token": row["opaqueToken"]} if parent_index is None else {}
                ),
            })
    normalized = {
        "schemaVersion": 1, "normalizer": "hotel-reservation-jaeger-v1",
        "queryLimitReached": False, "events": events,
    }
    kwargs = dict(posture="selected", scenario=None, fault_receipt=None, raw={}, capture_terminal={},
                  unsupported_postures=runtime.posture_ceiling()["unsupportedPostures"])
    result = witness.correlate(plan, ledger, application_log, normalized, **kwargs)
    assert all(row["state"] == "supported" and row["reconstructed"] is False for row in result["rows"])
    assert result["emptyCaptureProof"] is None
    leaked = copy.deepcopy(normalized)
    leaked["events"][1]["service"] = "search"
    with pytest.raises(witness.WitnessError, match="untraced service"):
        witness.correlate(plan, ledger, application_log, leaked, **kwargs)
    missing = copy.deepcopy(normalized)
    missing["events"] = [e for e in missing["events"] if e["traceId"] != "0000000000000001"]
    with pytest.raises(witness.WitnessError, match="bijective"):
        witness.correlate(plan, ledger, application_log, missing, **kwargs)


# LMT+S pilot collection ladder, stated as literals so the fixtures below do
# not derive their expectations from the code under test.
PILOT_LOG_LEVEL = {"none": "fatal", "metrics": "info", "selected": "info", "full": "info"}
PILOT_SAMPLER_POSTURES = ("metrics", "selected", "full")
PILOT_CLASSIFICATION = {
    "none": "logs-fatal-sampler-off-tracer-disabled",
    "metrics": "logs-info-sampler-on-tracer-disabled",
    "selected": "logs-info-sampler-on-tracer-frontend-only",
    "full": "logs-info-sampler-on-tracer-full-sampling",
}
# What `docker events` records on the target container for each fault: compose
# pause/unpause, two `docker update --cpus` calls, and nothing for an nsenter tc.
PILOT_FAULT_EVENT_ACTIONS = {
    None: [], "search-pause": ["pause", "unpause"], "reservation-pause": ["pause", "unpause"],
    "profile-cpu-throttle": ["update", "update"], "rate-net-delay": [],
}
PILOT_FAULT_TARGETS = {
    "search-pause": "search", "reservation-pause": "reservation",
    "profile-cpu-throttle": "profile", "rate-net-delay": "rate",
}


def _pilot_identities() -> dict[str, str]:
    return {f"{index:064x}": service for index, service in enumerate(terminal.APPLICATION_SERVICES, 1)}


def _docker_event(container: str, service: str, action: str, at: int) -> dict:
    return {
        "status": action, "id": container, "from": "obsplacement/hotel-reservation-candidate",
        "Type": "container", "Action": action,
        "Actor": {"ID": container, "Attributes": {"com.docker.compose.service": service}},
        "scope": "local", "time": at, "timeNano": at * 1_000_000_000,
    }


def _write_system_evidence(
    root: Path, identities: dict[str, str], *, barrier: float = 1000.0,
    fault: str | None = None,
) -> None:
    """Write the always-on LMT+S artifacts exactly as candidate_cell.run_cell does."""
    services = sorted(identities.values())
    daemons = ("docker.service", "containerd.service")
    start = {
        "label": "window-start", "at": "2026-08-30T01:00:00Z", "monotonic": barrier + 0.01,
        "containersUsageUsec": {name: 1_000_000 * index for index, name in enumerate(services, 1)},
        "daemonsUsageUsec": {unit: 5_000_000 for unit in daemons},
    }
    end = {
        "label": "window-end", "at": "2026-08-30T01:02:00Z", "monotonic": barrier + 120.02,
        "containersUsageUsec": {
            name: value + 2_500_000 for name, value in start["containersUsageUsec"].items()
        },
        "daemonsUsageUsec": {unit: value + 300_000 for unit, value in start["daemonsUsageUsec"].items()},
    }
    write_json(root / "cost-cgroup.json", system.cost_document(start, end))
    write_json(root / "system-samples.json", {
        "schemaVersion": 1, "kind": "hotel-lmt-system-samples-v1",
        "intervalSeconds": system.SAMPLE_INTERVAL_SECONDS,
        "samples": [
            {
                "monotonic": barrier + 5.0 * tick, "at": "2026-08-30T01:00:00Z",
                "services": {
                    name: {
                        "cpuUsageUsec": 1_000_000 + tick, "memoryCurrent": 4096,
                        "rbytes": 0, "wbytes": 0, "psiCpuSomeTotalUsec": 0,
                        "psiMemorySomeTotalUsec": 0, "psiIoSomeTotalUsec": None,
                    }
                    for name in services
                },
            }
            for tick in range(25)
        ],
    })
    write_json(root / "tcp-snapshots.json", {
        "schemaVersion": 1, "kind": "hotel-lmt-tcp-snapshots-v1",
        "snapshots": [
            {
                "label": label, "at": "2026-08-30T01:00:30Z", "monotonic": barrier + offset,
                "services": {
                    name: {"ips": [f"172.18.0.{index}"], "established": []}
                    for index, name in enumerate(services, 2)
                },
            }
            for label, offset in (("pre-fault", 30), ("during-fault", 52))
        ],
    })
    by_service = {service: container for container, service in identities.items()}
    events = [
        _docker_event(container, service, "start", 1) for container, service in sorted(identities.items())
    ]
    if fault is not None:
        target = PILOT_FAULT_TARGETS[fault]
        events.extend(
            _docker_event(by_service[target], target, action, 45 + 15 * index)
            for index, action in enumerate(PILOT_FAULT_EVENT_ACTIONS[fault])
        )
    (root / "docker-events.jsonl").write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events)
    )
    write_json(root / "docker-events.json", {
        "schemaVersion": 1, "kind": "hotel-lmt-docker-events-v1",
        "startedAt": "2026-08-30T00:59:59Z", "stoppedAt": "2026-08-30T01:02:03Z",
        "rows": len(events), "stderr": "",
    })


def _empty_capture_cell(root: Path, posture: str = "none") -> tuple[dict, dict]:
    """One sealed no-fault cell for a tracer-disabled (empty-capture) posture."""
    assert posture in ("none", "metrics")
    document = admission(root.parent)
    contract = next(
        row for row in runtime.cell_contracts(document)
        if row["runId"] == f"no-fault-cost-b01-{posture}-a01"
    )
    contract = {**contract, "runtimeArtifactRoot": str(root)}
    root.mkdir(parents=True)
    write_json(root / "cell-contract.json", contract)
    plan = make_plan(contract["runId"])
    write_json(root / "opportunity-plan.json", plan)
    rows = make_ledger(plan, root / "opportunity-ledger.jsonl")
    ledger_validation = workload.validate_ledger(plan, root / "opportunity-ledger.jsonl")
    write_json(root / "workload-reconciliation.json", {
        "schemaVersion": 1,
        "kind": "hotel-candidate-workload-reconciliation-v1",
        "planSha256": plan["planCanonicalSha256"],
        "ledgerSha256": hashlib.sha256((root / "opportunity-ledger.jsonl").read_bytes()).hexdigest(),
        "offered": 1200,
        "terminalSettled": 1200,
        "completed": 1200,
        "failed": 0,
        "firstRecordSha256": rows[0]["recordSha256"],
        "lastRecordSha256": rows[-1]["recordSha256"],
        "validation": ledger_validation,
    })
    log_rows = []
    for row in rows:
        log_rows.append("OBSPLACEMENT_WITNESS " + json.dumps({
            "schema": "hotel-application-request-witness-v1",
            "opaqueToken": row["opaqueToken"],
            "method": "GET",
            "routePattern": "/hotels",
            "statusCode": 200,
            "startedAtUnixNano": 1_000_000_000,
            "endedAtUnixNano": 1_000_000_001,
        }, separators=(",", ":")))
    application_log = "\n".join(log_rows) + "\n"
    (root / "application.log").write_text(application_log)
    window_start_us = int(workload.parse_iso(plan["barrierAt"], "barrierAt").timestamp() * 1_000_000)
    raw = {
        "schemaVersion": 1,
        "collector": "jaeger-query-api-v1",
        "collectedAtEpoch": 1.0,
        "window": {"startUs": window_start_us, "endUs": window_start_us + 125_000_000},
        "limitPerService": 10000,
        "queries": [{
            "service": "frontend",
            "url": "http://jaeger/api/traces",
            "traceCount": 0,
            "response": {"data": [], "errors": None},
        }],
    }
    normalized = terminal.jaeger_normalizer.normalize(raw)
    capture = {
        "schemaVersion": 1,
        "kind": "hotel-jaeger-capture-terminal-v1",
        "queriesComplete": True,
        "collectorTailComplete": True,
        "backendReadyAtTerminal": True,
    }
    write_json(root / "jaeger-raw.json", raw)
    write_json(root / "traces-normalized.json", normalized)
    write_json(root / "capture-terminal.json", capture)
    correlation = witness.correlate(
        plan, rows, application_log, normalized, posture=posture,
        scenario=None, fault_receipt=None, raw=raw, capture_terminal=capture,
        unsupported_postures=runtime.posture_ceiling()["unsupportedPostures"],
    )
    write_json(root / "correlation.json", correlation)
    window_start_ns = int(workload.parse_iso(plan["barrierAt"], "barrierAt").timestamp() * 1_000_000_000)
    emissions = resources.parse_emissions("", window_start_ns, window_start_ns + 120_000_000_000)
    write_json(root / "emissions.json", emissions)
    identities = {f"{index:064x}": service for index, service in enumerate(resources.APPLICATION_SERVICES, 1)}
    cpu_rows = [
        {"service": service, "containerId": container, "cpuPercent": 10.0}
        for container, service in identities.items()
    ]
    cpu_samples = [
        {
            "capturedAtEpoch": 1_000.0 + offset,
            "capturedAtMonotonic": 1_000.0 + offset,
            "containers": cpu_rows,
            "applicationCpuPercent": 100.0,
        }
        for offset in range(0, 121, 10)
    ]
    cpu = {
        "schemaVersion": 1,
        "contract": resources.RESOURCE_CONTRACT,
        "project": contract["project"],
        "applicationServices": list(resources.APPLICATION_SERVICES),
        "containerIdentities": identities,
        "windowStartMonotonic": 1000.0,
        "windowEndMonotonic": 1120.0,
        "intervalSeconds": 10.0,
        "samples": cpu_samples,
        "captureComplete": True,
        "applicationCpuSeconds": 120.0,
    }
    # docker-stats CPU evidence exists only where the metric sampler is on.
    if posture in PILOT_SAMPLER_POSTURES:
        write_json(root / "cpu.json", cpu)
    _write_system_evidence(root, identities, barrier=1000.0, fault=None)
    write_json(root / "posture-proof.json", {
        "schemaVersion": 3,
        "requested": posture,
        "expectedSampleRatio": {service: "0" for service in terminal.APPLICATION_SERVICES},
        "services": {service: "0" for service in terminal.APPLICATION_SERVICES},
        "tracedServices": [],
        "logLevel": PILOT_LOG_LEVEL[posture],
        "metricSampler": posture in PILOT_SAMPLER_POSTURES,
        "sourceWorkDisabled": False,
        "classification": PILOT_CLASSIFICATION[posture],
    })
    source_sha = "2" * 64
    image_id = "sha256:" + "3" * 64
    patch_sha = hashlib.sha256((MODULE / "witness/hotel-candidate-witness.patch").read_bytes()).hexdigest()
    inputs_sha = hashlib.sha256((MODULE / "deployment/runtime-inputs.lock.json").read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256((MODULE / "witness/patch-manifest.json").read_bytes()).hexdigest()
    runtime_lock = json.loads((MODULE / "deployment/runtime-inputs.lock.json").read_text())
    write_json(root / "source-proof.json", {
        "upstreamCommit": "6ecb09706140f8730b5385c08f1386c654c3c526",
        "sourceCheckoutClean": True,
        "candidatePatchId": "hotel-lmt-pilot-witness-and-log-fatal-v1",
        "candidatePatchSha256": patch_sha,
        "patchManifestSha256": manifest_sha,
        "runtimeInputsSha256": inputs_sha,
        "runtimeImages": runtime_lock["images"],
        "materializedSourceSha256": source_sha,
    })
    write_json(root / "application-build-proof.json", {
        "schemaVersion": 1,
        "imageReference": "obsplacement/hotel-reservation-candidate:" + source_sha[:16],
        "imageId": image_id,
        "materializedSourceSha256": source_sha,
        "builderReference": runtime_lock["images"]["builder"],
        "runtimeInputsSha256": inputs_sha,
    })
    write_json(root / "images.json", {
        "schemaVersion": 1,
        "project": contract["project"],
        "materializedSourceSha256": source_sha,
        "applicationImageId": image_id,
        "applicationImageReference": "obsplacement/hotel-reservation-candidate:" + source_sha[:16],
        "runtimeInputsSha256": inputs_sha,
        "containers": [
            {"service": service, "containerId": f"{index:064x}", "project": contract["project"], "imageId": image_id}
            for index, service in enumerate(terminal.APPLICATION_SERVICES, 1)
        ],
    })
    lock = json.loads((MODULE / "deployment/runtime-inputs.lock.json").read_text())
    application_services = {
        "frontend", "search", "geo", "rate", "reservation", "profile",
        "user", "recommendation", "review", "attractions",
    }
    compose_services = {}
    for service in terminal.COMPOSE_SERVICES:
        if service in application_services:
            environment = {
                "JAEGER_SAMPLE_RATIO": "0",
                "JAEGER_DISABLED": "true",
                "TLS": "0",
                "GC": "100",
                "LOG_LEVEL": PILOT_LOG_LEVEL[posture],
            }
            if service in {"review", "attractions"}:
                environment["MEMC_TIMEOUT"] = "2"
            compose_services[service] = {
                "image": "obsplacement/hotel-reservation-candidate:" + source_sha[:16],
                "environment": environment,
            }
        elif service == "consul":
            compose_services[service] = {"image": lock["images"]["consul"]}
        elif service == "jaeger":
            compose_services[service] = {"image": lock["images"]["jaeger"]}
        elif service.startswith("memcached-"):
            compose_services[service] = {"image": lock["images"]["memcached"]}
        else:
            compose_services[service] = {"image": lock["images"]["mongo"]}
    compose_services["frontend"]["ports"] = [{
        "target": 5000, "published": "35005", "host_ip": "127.0.0.1",
        "protocol": "tcp",
    }]
    compose_services["jaeger"]["ports"] = [{
        "target": 16686, "published": "36685", "host_ip": "127.0.0.1",
        "protocol": "tcp",
    }]
    write_json(root / "compose-rendered.yml", {"services": compose_services})
    foreign_resources = {
        "containers": [str(index) * 64 for index in range(1, 6)],
        "networks": ["nuisance-network"], "volumes": [],
    }
    # ponytail: five rows, all running, matching foreignStateCounts {"running": 5}.
    # This fixture previously built six rows with index 1 labelled `created` while
    # asserting five running, so it encoded the pre- and post-re-pin worlds at once
    # and stayed green under either. A fixture that cannot fail is worse than none:
    # it is why the row-count pin survived a five-site sweep and aborted campaign #5.
    foreign_rows = [
        f"{str(index) * 64}|running|image-{index}|dps-{index}|labels"
        for index in range(1, 6)
    ]
    # Host condition v2 (2026-09-21): the cell records the verified ABSENCE of any
    # foreign Compose project or container, and carries the pooling boundary
    # against the 103 co-tenant cells inside the evidence itself.
    del foreign_rows, foreign_resources
    write_json(root / "nuisance.json", {
        "schemaVersion": 2,
        "kind": "hotel-srv4-cell-nuisance-v2",
        "factors": list(runtime.NUISANCE_FACTORS),
        "hostCondition": runtime.HOST_CONDITION_ID,
        "poolingBoundary": runtime.POOLING_BOUNDARY,
        "notPoolableWith": runtime.not_poolable_with(),
        "before": {
            "capturedAt": "2026-08-30T01:00:00Z", "loadAverage": [1.0, 2.0, 3.0],
            "foreignProject": None, "foreignRows": [],
        },
        "after": {
            "capturedAt": "2026-08-30T01:03:00Z", "loadAverage": [1.5, 2.5, 3.5],
            "foreignProject": None, "foreignRows": [],
        },
        "foreignMutationActions": [],
        "absoluteCostOrLatencyCanonical": False,
    })
    write_json(root / "cell-cleanup.json", {
        "schemaVersion": 1,
        "kind": "hotel-candidate-cell-cleanup-v1",
        "project": contract["project"],
        "unpauseAttempted": True,
        "composeDownReturnCode": 0,
        "ownedResourcesRemaining": {"containers": [], "networks": [], "volumes": []},
        "foreignResourcesMutated": False,
        "artifactDeletionAttempted": False,
    })
    terminal.write_manifest(root)
    return document, contract


@pytest.mark.parametrize("posture", ["none", "metrics"])
def test_empty_capture_terminal_proves_empty_acquisition_without_source_claim(
    tmp_path: Path, posture: str,
):
    root = tmp_path / "campaign" / "runs" / posture
    _document, contract = _empty_capture_cell(root, posture)
    result = terminal.validate_cell(root, contract)
    assert result["candidateCellValid"] is True
    assert result["emissions"]["eventCount"] == 0
    # docker-stats CPU is replayed only where the sampler ran; the always-on
    # cgroup cost is replayed in every posture.
    assert (result["cpu"] is not None) is (posture in PILOT_SAMPLER_POSTURES)
    assert result["system"]["systemSamples"] == 25
    assert result["system"]["dockerEvents"] == 10
    assert result["system"]["faultEventActions"] == []
    assert result["system"]["costContainersCpuSeconds"] == pytest.approx(25.0)
    assert result["system"]["costDaemonsCpuSeconds"] == pytest.approx(0.6)
    assert result["sourceCostComparisonState"] == "unsupported"
    assert result["unsupportedPostures"] == runtime.unsupported_posture_ids(runtime.posture_ceiling())
    assert result["nuisance"]["hostCondition"] == runtime.HOST_CONDITION_ID
    assert result["nuisance"]["poolingBoundary"] == runtime.POOLING_BOUNDARY
    assert result["canonical"] is False


def test_cell_manifest_watches_post_validation_tamper(tmp_path: Path):
    root = tmp_path / "campaign" / "runs" / "none"
    _document, contract = _empty_capture_cell(root, "none")
    path = root / "posture-proof.json"
    attacked = json.loads(path.read_text())
    attacked["sourceWorkDisabled"] = True
    write_json(path, attacked)
    with pytest.raises(terminal.TerminalError, match="manifest digest"):
        terminal.validate_cell(root, contract)


@pytest.mark.parametrize(
    ("posture", "artifact", "field", "value", "diagnostic"),
    [
        ("metrics", "cpu.json", "project", "foreign-project", "CPU evidence project"),
        ("none", "source-proof.json", "runtimeInputsSha256", "0" * 64, "transitively bound"),
        ("metrics", "traces-normalized.json", "spanCount", 1, "differs from raw"),
        # posture-proof v3: every collection switch is checked, the tracer per service.
        ("none", "posture-proof.json", "logLevel", "info", "posture proof differs"),
        ("metrics", "posture-proof.json", "logLevel", "fatal", "posture proof differs"),
        ("none", "posture-proof.json", "metricSampler", True, "posture proof differs"),
        ("metrics", "posture-proof.json", "metricSampler", False, "posture proof differs"),
        ("metrics", "posture-proof.json", "tracedServices", ["frontend"], "posture proof differs"),
        ("none", "posture-proof.json", "schemaVersion", 2, "posture proof differs"),
        ("none", "cost-cgroup.json", "windowSeconds", 110.0, "cost cgroup evidence"),
        ("none", "docker-events.json", "rows", 9, "docker events summary"),
    ],
)
def test_terminal_watchers_reject_semantic_defects_after_a_fresh_seal(
    tmp_path: Path, posture: str, artifact: str, field: str, value: object, diagnostic: str,
):
    root = tmp_path / "campaign" / "runs" / posture
    _document, contract = _empty_capture_cell(root, posture)
    path = root / artifact
    attacked = json.loads(path.read_text())
    attacked[field] = value
    write_json(path, attacked)
    (root / terminal.MANIFEST).unlink()
    terminal.write_manifest(root)
    with pytest.raises(terminal.TerminalError, match=diagnostic):
        terminal.validate_cell(root, contract)


@pytest.mark.parametrize("posture", ["none"])
def test_sampler_off_posture_that_retains_docker_stats_cpu_is_rejected(tmp_path: Path, posture: str):
    root = tmp_path / "campaign" / "runs" / posture
    _document, contract = _empty_capture_cell(root, posture)
    donor = tmp_path / "donor" / "runs" / "metrics"
    _empty_capture_cell(donor, "metrics")
    shutil.copyfile(donor / "cpu.json", root / "cpu.json")
    (root / terminal.MANIFEST).unlink()
    terminal.write_manifest(root)
    with pytest.raises(terminal.TerminalError, match="sampler-off posture retained"):
        terminal.validate_cell(root, contract)


def test_sampler_on_posture_without_docker_stats_cpu_is_missing_an_artifact(tmp_path: Path):
    root = tmp_path / "campaign" / "runs" / "metrics"
    _document, contract = _empty_capture_cell(root, "metrics")
    (root / "cpu.json").unlink()
    (root / terminal.MANIFEST).unlink()
    terminal.write_manifest(root)
    with pytest.raises(terminal.TerminalError, match=r"missing artifacts: \['cpu.json'\]"):
        terminal.validate_cell(root, contract)


@pytest.mark.parametrize(
    "missing", ["cost-cgroup.json", "system-samples.json", "tcp-snapshots.json",
                "docker-events.jsonl", "docker-events.json"],
)
def test_always_on_system_artifacts_are_required_in_every_posture(tmp_path: Path, missing: str):
    root = tmp_path / "campaign" / "runs" / "none"
    _document, contract = _empty_capture_cell(root, "none")
    (root / missing).unlink()
    (root / terminal.MANIFEST).unlink()
    terminal.write_manifest(root)
    with pytest.raises(terminal.TerminalError, match="missing artifacts"):
        terminal.validate_cell(root, contract)


def _system_case(tmp_path: Path, fault: str | None) -> tuple[Path, dict, dict, dict, dict]:
    root = tmp_path / "system"
    root.mkdir()
    identities = _pilot_identities()
    _write_system_evidence(root, identities, barrier=1000.0, fault=fault)
    images = {"containers": [
        {"service": service, "containerId": container} for container, service in identities.items()
    ]}
    return root, {"fault": fault}, {"barrierMonotonic": 1000.0}, images, identities


def _rewrite_events(root: Path, identities: dict, mutations: list[tuple[str, str]]) -> None:
    """Replace the stream with start events plus (service, action) mutations; keep the summary exact."""
    by_service = {service: container for container, service in identities.items()}
    events = [
        _docker_event(container, service, "start", 1) for container, service in sorted(identities.items())
    ] + [
        _docker_event(by_service[service], service, action, 45 + index)
        for index, (service, action) in enumerate(mutations)
    ]
    (root / "docker-events.jsonl").write_text(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events)
    )
    summary = json.loads((root / "docker-events.json").read_text())
    summary["rows"] = len(events)
    write_json(root / "docker-events.json", summary)


@pytest.mark.parametrize(
    "fault", [None, "search-pause", "reservation-pause", "profile-cpu-throttle", "rate-net-delay"],
)
def test_system_evidence_replays_the_admitted_fault_actions_for_every_regime(tmp_path: Path, fault):
    root, contract, plan, images, _identities = _system_case(tmp_path, fault)
    result = terminal._system(root, contract, plan, images)
    assert result["faultEventActions"] == PILOT_FAULT_EVENT_ACTIONS[fault]
    assert result["systemSamples"] == 25
    assert result["dockerEvents"] == 10 + len(PILOT_FAULT_EVENT_ACTIONS[fault])
    assert result["costContainersCpuSeconds"] == pytest.approx(25.0)


@pytest.mark.parametrize(
    ("fault", "mutations"),
    [
        ("search-pause", []),                                           # no fault recorded
        ("search-pause", [("search", "pause")]),                        # never unpaused
        ("search-pause", [("search", "unpause"), ("search", "pause")]),  # reordered
        ("search-pause", [("search", "pause"), ("search", "unpause"),
                          ("search", "pause"), ("search", "unpause")]),  # applied twice
        ("search-pause", [("search", "update"), ("search", "update")]),  # a throttle, not a pause
        ("reservation-pause", [("search", "pause"), ("search", "unpause")]),  # wrong target
        ("profile-cpu-throttle", [("profile", "update")]),              # never reverted
        ("rate-net-delay", [("rate", "pause"), ("rate", "unpause")]),   # a pause, not a delay
    ],
)
def test_system_rejects_fault_event_actions_other_than_the_admitted_ones(
    tmp_path: Path, fault: str, mutations: list,
):
    root, contract, plan, images, identities = _system_case(tmp_path, fault)
    _rewrite_events(root, identities, mutations)
    with pytest.raises(terminal.TerminalError, match="exactly the admitted fault actions"):
        terminal._system(root, contract, plan, images)


@pytest.mark.parametrize(
    ("fault", "mutations"),
    [
        # A cost cell admits no container mutation at all (costWindowContainsFault: false).
        (None, [("search", "pause"), ("search", "unpause")]),
        (None, [("profile", "update"), ("profile", "update")]),
        # A fault cell admits its own actions on its own target, and nothing else.
        ("search-pause", [("search", "pause"), ("geo", "pause"), ("geo", "unpause"),
                          ("search", "unpause")]),
        ("rate-net-delay", [("profile", "update"), ("profile", "update")]),
    ],
)
def test_system_rejects_container_mutations_outside_the_admitted_fault(
    tmp_path: Path, fault, mutations: list,
):
    root, contract, plan, images, identities = _system_case(tmp_path, fault)
    _rewrite_events(root, identities, mutations)
    with pytest.raises(terminal.TerminalError, match="exactly the admitted fault actions"):
        terminal._system(root, contract, plan, images)


def _drop_during_snapshot(root: Path) -> None:
    document = json.loads((root / "tcp-snapshots.json").read_text())
    document["snapshots"] = document["snapshots"][:1]
    write_json(root / "tcp-snapshots.json", document)


def _set_json(name: str, *path, value):
    def planted(root: Path) -> None:
        document = json.loads((root / name).read_text())
        target = document
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        write_json(root / name, document)
    return planted


def _truncate_samples(root: Path) -> None:
    document = json.loads((root / "system-samples.json").read_text())
    document["samples"] = document["samples"][:23]
    write_json(root / "system-samples.json", document)


@pytest.mark.parametrize(
    ("label", "plant", "diagnostic"),
    [
        ("cost windowSeconds 110", _set_json("cost-cgroup.json", "windowSeconds", value=110.0),
         "cost cgroup evidence"),
        ("cost start 2 s after the barrier",
         _set_json("cost-cgroup.json", "start", "monotonic", value=1002.0), "cost cgroup evidence"),
        ("negative daemon CPU",
         _set_json("cost-cgroup.json", "daemonsCpuSeconds", "docker.service", value=-0.1),
         "cost cgroup evidence"),
        ("missing during-fault TCP snapshot", _drop_during_snapshot, "TCP snapshots"),
        ("TCP snapshot labels swapped",
         _set_json("tcp-snapshots.json", "snapshots", 0, "label", value="during-fault"),
         "TCP snapshots"),
        ("23 system samples", _truncate_samples, "system samples"),
        ("events summary row count", _set_json("docker-events.json", "rows", value=11),
         "docker events summary"),
        ("app CPU zeroed against its own edges",
         _set_json("cost-cgroup.json", "containersCpuSeconds", "frontend", value=0.0),
         "differ from their own retained edges"),
        ("window seconds off its own edges by 0.5 s",
         _set_json("cost-cgroup.json", "windowSeconds", value=120.5),
         "differ from their own retained edges"),
    ],
)
def test_system_rejects_planted_always_on_defects(tmp_path: Path, label: str, plant, diagnostic: str):
    root, contract, plan, images, _identities = _system_case(tmp_path, "search-pause")
    terminal._system(root, contract, plan, images)
    plant(root)
    with pytest.raises(terminal.TerminalError, match=diagnostic):
        terminal._system(root, contract, plan, images)


def test_detached_launch_receipt_is_fully_admission_bound(monkeypatch):
    now = datetime(2026, 8, 30, 0, 0, 1, tzinfo=timezone.utc)
    campaign_id = "hotel-v1-20260830t010203z-deadbeef"
    document = admission(Path(runtime.TARGET["artifactParent"]) / campaign_id)
    document["bindings"].update({
        "artifactParent": runtime.TARGET["artifactParent"],
        "artifactRoot": runtime.TARGET["artifactParent"] + "/" + campaign_id,
        "leaseRoot": runtime.TARGET["leaseRoot"], "leasePath": runtime.TARGET["leasePath"],
        "deadline": "2026-08-30T05:00:01Z",
    })
    body = {key: value for key, value in document.items() if key != "admissionCanonicalSha256"}
    document["admissionCanonicalSha256"] = runtime.canonical_sha256(body)
    control = Path(runtime.TARGET["controlRoot"]) / campaign_id
    receipt = {
        "schemaVersion": 1, "kind": "hotel-srv4-detached-launch-v1",
        "campaignId": campaign_id, "pid": 4242,
        "admissionCanonicalSha256": document["admissionCanonicalSha256"],
        "argv": [
            "/usr/bin/python3", "-I", runtime.TARGET["checkoutRoot"] + "/modules/hotel-reservation/execution/candidate_runtime.py",
            "--supervise-admission", str(control / "runtime-admission.json"),
            "--execution-receipt", str(control / "execution-receipt.json"),
            "--campaign-abort", str(control / "campaign-abort.json"), "--lease-fd", "9",
        ],
    }
    controller = runtime.DetachedSshController()
    monkeypatch.setattr(controller, "_ssh", lambda *_args, **_kwargs: subprocess.CompletedProcess(
        [], 0, json.dumps(receipt), "",
    ))
    assert controller.launch(document, clock=lambda: now) == receipt
    receipt["admissionCanonicalSha256"] = "0" * 64
    with pytest.raises(runtime.GateError, match="launch receipt"):
        controller.launch(document, clock=lambda: now)


def test_lease_is_exclusive_and_never_stolen(monkeypatch, tmp_path: Path):
    document = admission(tmp_path / "campaign")
    lease = tmp_path / "lease"
    monkeypatch.setattr(cell, "_lease", lambda _admission: lease)
    monkeypatch.setattr(cell, "_deadline", lambda *_args, **_kwargs: None)
    assert cell.acquire_lease(document)["acquired"] is True
    with pytest.raises(cell.CellError, match="will not be stolen"):
        cell.acquire_lease(document)


def test_runtime_lock_rejects_mutable_image_reference():
    lock = json.loads((MODULE / "deployment/runtime-inputs.lock.json").read_text())
    materialize._verify_lock(lock)
    attacked = copy.deepcopy(lock)
    attacked["images"]["mongo"] = "mongo:5.0"
    with pytest.raises(materialize.MaterializationError, match="not digest pinned"):
        materialize._verify_lock(attacked)


def test_reviewed_patch_applies_to_exact_pinned_hotel_source(tmp_path: Path):
    source = Path(
        "/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/"
        "observability-placement/upstream/deathstarbench"
    )
    if not (source / "hotelReservation/tracing/mux.go").is_file():
        pytest.skip("initialized exact DeathStarBench checkout is unavailable")
    manifest = json.loads((MODULE / "witness/patch-manifest.json").read_text())
    patch = MODULE / "witness/hotel-candidate-witness.patch"
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == manifest["patchSha256"]
    # LMT+S pilot: the witness patch also adds the `disabled` log level.
    assert manifest["id"] == "hotel-lmt-pilot-witness-and-log-fatal-v1"
    assert [row["path"] for row in manifest["files"]] == [
        "Dockerfile", "tracing/mux.go", "tracing/tracer.go", "tune/setting.go",
    ]
    candidate = tmp_path / "hotelReservation"
    shutil.copytree(source / "hotelReservation", candidate)
    for row in manifest["files"]:
        assert hashlib.sha256((candidate / row["path"]).read_bytes()).hexdigest() == row["beforeSha256"]
    result = subprocess.run(
        ["git", "-C", str(candidate), "apply", "--check", "--unidiff-zero", "-p2", str(patch)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        ["git", "-C", str(candidate), "apply", "--unidiff-zero", "-p2", str(patch)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    for row in manifest["files"]:
        assert hashlib.sha256((candidate / row["path"]).read_bytes()).hexdigest() == row["afterSha256"]
    setting = (candidate / "tune/setting.go").read_text()
    assert "zerolog.SetGlobalLevel(zerolog.FatalLevel)" in setting
    # lmt1 (2026-09-28): under zerolog.Disabled every service exits 1 at
    # `log.Fatal().Msg(srv.Run().Error())`, because Fatal's callback runs before Run() is evaluated.
    assert "zerolog.Disabled" not in setting


FAULT_RECEIPT_FIXTURE = {
    "schemaVersion": 1,
    "faultKind": "pause",
    "scenario": "search-pause",
    "targetService": "search",
    "scheduledAtSeconds": 45,
    "requestedOutageSeconds": 15,
    "startedAt": "2026-08-30T01:00:45Z",
    "endedAt": "2026-08-30T01:01:01Z",
    "manifested": True,
    "outageObserved": True,
    "recovered": True,
    "successful": True,
    "preState": {"running": True, "paused": False},
    "preRouteAvailable": True,
    "duringState": {"running": True, "paused": True},
    "recoveryState": {"running": True, "paused": False},
    "startedMonotonic": 1045.0,
    "appliedMonotonic": 1045.2,
    "revertingMonotonic": 1059.9,
    "unpausedAtMonotonic": 1060.0,
    "readyAtMonotonic": 1060.5,
    "endedMonotonic": 1061.0,
    "commands": [
        {"action": "pause", "returnCode": 0, "stdout": "", "stderr": ""},
        {"action": "unpause", "returnCode": 0, "stdout": "", "stderr": ""},
    ],
    "error": None,
    "actualOutageSeconds": 15.0,
}

NORMAL_TRACE_SHAPE = [
    ("frontend", "HTTP GET /hotels", None),
    ("search", "/search.Search/Nearby", 0),
    ("geo", "/geo.Geo/Nearby", 1),
    ("rate", "/rate.Rate/GetRates", 1),
    ("reservation", "/reservation.Reservation/CheckAvailability", 0),
    ("profile", "/profile.Profile/GetProfiles", 0),
]

# What the paused `search` container actually leaves behind: the frontend root
# plus the frontend's own client span naming search, and nothing downstream.
TRUNCATED_TRACE_SHAPE = [
    ("frontend", "HTTP GET /hotels", None),
    ("frontend", "/search.Search/Nearby", 0),
]


def _witness_log(ledger: list[dict]) -> str:
    return "\n".join(
        "OBSPLACEMENT_WITNESS " + json.dumps({
            "schema": "hotel-application-request-witness-v1", "opaqueToken": row["opaqueToken"],
            "method": "GET", "routePattern": "/hotels", "statusCode": 200,
            "startedAtUnixNano": 1, "endedAtUnixNano": 2,
        }, separators=(",", ":")) for row in ledger
    ) + "\n"


def _trace_events(trace_id: str, token: str, shape: list) -> list[dict]:
    events = []
    for span_index, (service, operation, parent_index) in enumerate(shape, 1):
        events.append({
            "traceId": trace_id, "spanId": f"{span_index:016x}",
            "parentSpanId": None if parent_index is None else f"{parent_index + 1:016x}",
            "service": service,
            "parentService": None if parent_index is None else shape[parent_index][0],
            "operation": operation,
            "tags": {"obsplacement.opaque_token": token} if parent_index is None else {},
        })
    return events


def _fault_cell_capture(ledger: list[dict], receipt: dict) -> dict:
    """A search-pause full-posture capture: normal outside, truncated during."""
    events = []
    for trace_index, row in enumerate(ledger, 1):
        started = row["actualStartMonotonic"]
        during = receipt["startedMonotonic"] <= started < receipt["readyAtMonotonic"]
        events.extend(_trace_events(
            f"{trace_index:016x}", row["opaqueToken"],
            TRUNCATED_TRACE_SHAPE if during else NORMAL_TRACE_SHAPE,
        ))
    return {
        "schemaVersion": 1, "normalizer": "hotel-reservation-jaeger-v1",
        "queryLimitReached": False, "events": events,
    }


def _probe_trace(offset_seconds: float, url: str | None = None) -> list[dict]:
    """One untagged adapter route-probe trace, offset from the plan barrier."""
    barrier = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc).timestamp()
    return [{
        "traceId": "f" * 16, "spanId": "f" * 16, "parentSpanId": None,
        "service": "frontend", "parentService": None, "operation": "HTTP GET /hotels",
        "startTimeUs": int((barrier + offset_seconds) * 1_000_000),
        "tags": {
            "span.kind": "server",
            "http.url": workload.search_url("", 0) if url is None else url,
        },
    }]


def _correlate_fault(ledger: list[dict], normalized: dict, plan: dict, **kwargs):
    arguments = {
        "posture": "full", "scenario": "search-pause",
        "fault_receipt": FAULT_RECEIPT_FIXTURE, "raw": {}, "capture_terminal": {},
        "unsupported_postures": runtime.posture_ceiling()["unsupportedPostures"],
    }
    arguments.update(kwargs)
    return witness.correlate(
        plan, ledger, _witness_log(ledger), normalized, **arguments,
    )


def test_during_fault_traces_use_the_preregistered_fault_specific_path_truth(tmp_path):
    """The paused target's own truncation is the descriptor's ground truth, not loss."""
    plan = make_plan("search-pause-effect-b01-full-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    normalized = _fault_cell_capture(ledger, FAULT_RECEIPT_FIXTURE)
    result = _correlate_fault(ledger, normalized, plan)
    truth = result["faultPathTruth"]
    assert truth["groundTruthId"] == "hotel-search-search-pause-prefix-v1"
    assert truth["targetService"] == "search"
    assert truth["requiredAttemptedPrefix"] == ["frontend", "search"]
    # Every during row is reported and left numerically unqualified. `during`
    # now runs to readiness + POST_READINESS_SETTLE_SECONDS (Hotel #3, cell 24:
    # one request 20 ms after the probe lost its parent span in the thaw
    # burst), so the rows in that settle band carry this fixture's NORMAL
    # traces and are validated but not truncated; the physically paused band
    # (started .. ready) is truncated in full.
    receipt = FAULT_RECEIPT_FIXTURE
    during = [row for row in result["rows"] if row["phase"] == "during"]
    paused = [
        row for row in ledger
        if receipt["startedMonotonic"] <= row["actualStartMonotonic"] < receipt["readyAtMonotonic"]
    ]
    settle = [
        row for row in ledger
        if receipt["readyAtMonotonic"] <= row["actualStartMonotonic"]
        < receipt["readyAtMonotonic"] + witness.POST_READINESS_SETTLE_SECONDS
    ]
    assert settle, "fixture must exercise the settle band"
    assert len(during) == len(paused) + len(settle) == truth["duringTracesValidated"]
    assert truth["duringTracesTruncated"] == len(paused)
    assert during and all(
        row["state"] == "unsupported" and row["reconstructed"] is None for row in during
    )
    assert truth["adapterRouteProbeTraces"] == []
    assert truth["missingEdgeCounts"] == {
        edge: len(paused) for edge in truth["permittedMissingEdges"]
    }
    boundaries = result["faultReceipt"]["phaseBoundaries"] if "faultReceipt" in result else None
    if boundaries is not None:
        assert boundaries["duringSettleEndMonotonic"] == receipt["readyAtMonotonic"] + witness.POST_READINESS_SETTLE_SECONDS
    # Outside the fault window the normal path stays fully required.
    assert all(
        row["state"] == "supported" and row["reconstructed"] is True
        for row in result["rows"] if row["phase"] != "during"
    )


def test_fault_truncation_shape_still_blocks_outside_the_window_and_on_cost_cells(tmp_path):
    plan = make_plan("search-pause-effect-b01-full-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    # The same truncation in the pre phase is evidence loss, not the fault.
    early = _fault_cell_capture(ledger, {
        **FAULT_RECEIPT_FIXTURE, "startedMonotonic": 1005.0, "readyAtMonotonic": 1020.0,
    })
    with pytest.raises(witness.WitnessError, match="required same-trace service edge"):
        _correlate_fault(ledger, early, plan)
    # A cost cell has no fault to explain any truncation at all.
    cost_plan = make_plan("no-fault-cost-b01-full-a01")
    cost_ledger = make_ledger(cost_plan, tmp_path / "cost.jsonl")
    cost = _fault_cell_capture(cost_ledger, FAULT_RECEIPT_FIXTURE)
    with pytest.raises(witness.WitnessError, match="required same-trace service edge"):
        _correlate_fault(
            cost_ledger, cost, cost_plan, scenario=None, fault_receipt=None,
        )


DEGRADATION_RECEIPT_FIXTURE = {
    "schemaVersion": 1,
    "faultKind": "degradation",
    "scenario": "rate-net-delay",
    "targetService": "rate",
    "scheduledAtSeconds": 45,
    "requestedHoldSeconds": 15,
    "startedAt": "2026-08-30T01:00:45Z",
    "endedAt": "2026-08-30T01:01:01Z",
    "manifested": True,
    "reverted": True,
    "recovered": True,
    "successful": True,
    "preClean": True,
    "preRouteAvailable": True,
    "routeAvailableDuring": True,
    "startedMonotonic": 1045.0,
    "appliedMonotonic": 1045.1,
    "revertingMonotonic": 1060.1,
    "revertedAtMonotonic": 1060.2,
    "readyAtMonotonic": 1060.3,
    "endedMonotonic": 1060.4,
    "commands": [
        {"action": "apply", "returnCode": 0, "stdout": "", "stderr": ""},
        {"action": "revert", "returnCode": 0, "stdout": "", "stderr": ""},
    ],
    "error": None,
    "actualHoldSeconds": 15.0,
}


def test_during_a_degradation_the_normal_path_stays_required_and_scored(tmp_path):
    """A slowed service is not an absent one: no truncation is excused, every row is scored."""
    plan = make_plan("net-delay-effect-b01-full-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    normal = {
        "schemaVersion": 1, "normalizer": "hotel-reservation-jaeger-v1",
        "queryLimitReached": False,
        "events": [
            event for index, row in enumerate(ledger, 1)
            for event in _trace_events(f"{index:016x}", row["opaqueToken"], NORMAL_TRACE_SHAPE)
        ],
    }
    result = _correlate_fault(
        ledger, normal, plan, scenario="rate-net-delay", fault_receipt=DEGRADATION_RECEIPT_FIXTURE,
    )
    assert "faultPathTruth" not in result
    during = [row for row in result["rows"] if row["phase"] == "during"]
    assert during, "fixture must place requests inside the degradation"
    assert all(
        row["state"] == "supported" and row["reconstructed"] is True for row in result["rows"]
    )
    # The pause prefix truth does not apply: the truncated shape during a delay is loss.
    truncated = _fault_cell_capture(ledger, DEGRADATION_RECEIPT_FIXTURE)
    with pytest.raises(witness.WitnessError, match="required same-trace service edge"):
        _correlate_fault(
            ledger, truncated, plan, scenario="rate-net-delay",
            fault_receipt=DEGRADATION_RECEIPT_FIXTURE,
        )


def test_during_fault_trace_must_still_witness_the_attempted_prefix(tmp_path):
    plan = make_plan("search-pause-effect-b01-full-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    normalized = _fault_cell_capture(ledger, FAULT_RECEIPT_FIXTURE)
    # Drop the frontend's own client span naming search from one during trace:
    # nothing then witnesses that the attempt ever reached the paused service.
    planted = copy.deepcopy(normalized)
    victim = next(
        row["traceId"] for row in planted["events"]
        if row["service"] == "frontend" and row["operation"] == "/search.Search/Nearby"
    )
    planted["events"] = [
        row for row in planted["events"]
        if not (row["traceId"] == victim and row["parentSpanId"] is not None)
    ]
    with pytest.raises(witness.WitnessError, match="required attempted prefix"):
        _correlate_fault(ledger, planted, plan)


def test_during_fault_unreported_parent_is_only_admissible_below_the_target(tmp_path):
    plan = make_plan("search-pause-effect-b01-full-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    normalized = _fault_cell_capture(ledger, FAULT_RECEIPT_FIXTURE)
    victim = next(
        row["traceId"] for row in normalized["events"]
        if row["service"] == "frontend" and row["operation"] == "/search.Search/Nearby"
    )
    # geo hangs below the paused search, so its parent span can be unreported.
    admissible = copy.deepcopy(normalized)
    admissible["events"].append({
        "traceId": victim, "spanId": "a" * 16, "parentSpanId": "b" * 16,
        "service": "geo", "parentService": None, "operation": "/geo.Geo/Nearby", "tags": {},
    })
    result = _correlate_fault(ledger, admissible, plan)
    assert result["faultPathTruth"]["duringTracesWithUnreportedParent"] == 1
    # profile is never reached through search, so its parent cannot be excused.
    planted = copy.deepcopy(normalized)
    planted["events"].append({
        "traceId": victim, "spanId": "a" * 16, "parentSpanId": "b" * 16,
        "service": "profile", "parentService": None,
        "operation": "/profile.Profile/GetProfiles", "tags": {},
    })
    with pytest.raises(witness.WitnessError, match="missing from the same trace"):
        _correlate_fault(ledger, planted, plan)


def test_adapter_route_probe_traces_are_accounted_not_silently_ignored(tmp_path):
    plan = make_plan("search-pause-effect-b01-full-a01")
    ledger = make_ledger(plan, tmp_path / "ledger.jsonl")
    normalized = _fault_cell_capture(ledger, FAULT_RECEIPT_FIXTURE)
    admissible = copy.deepcopy(normalized)
    admissible["events"].extend(_probe_trace(50.0))
    result = _correlate_fault(ledger, admissible, plan)
    assert result["faultPathTruth"]["adapterRouteProbeTraces"] == ["f" * 16]
    unexplained = "zero or multiple opportunity tokens"
    # Same trace, but not on the adapter's probe route.
    other_route = copy.deepcopy(normalized)
    other_route["events"].extend(_probe_trace(50.0, url="/hotels?inDate=2015-04-11"))
    with pytest.raises(witness.WitnessError, match=unexplained):
        _correlate_fault(ledger, other_route, plan)
    # Same route, but outside the window the fault receipt itself brackets.
    outside = copy.deepcopy(normalized)
    outside["events"].extend(_probe_trace(100.0))
    with pytest.raises(witness.WitnessError, match=unexplained):
        _correlate_fault(ledger, outside, plan)
    # Same route and window, but a cost cell has no adapter to explain it.
    cost_plan = make_plan("no-fault-cost-b01-full-a01")
    cost_ledger = make_ledger(cost_plan, tmp_path / "cost.jsonl")
    cost = {
        "schemaVersion": 1, "normalizer": "hotel-reservation-jaeger-v1",
        "queryLimitReached": False,
        "events": [
            event for index, row in enumerate(cost_ledger, 1)
            for event in _trace_events(f"{index:016x}", row["opaqueToken"], NORMAL_TRACE_SHAPE)
        ] + _probe_trace(50.0),
    }
    with pytest.raises(witness.WitnessError, match=unexplained):
        _correlate_fault(
            cost_ledger, cost, cost_plan, scenario=None, fault_receipt=None,
        )


def test_co_tenant_state_pin_is_swept_everywhere_not_five_of_seven() -> None:
    """Every site holding the foreign dps_training_k state count agrees.

    2026-09-18: the pin was re-pinned {"created":1,"running":5} -> {"running":5}
    with the user's approval, and five executable sites were swept
    (candidate_cell.py:650, candidate_runtime.py:1019 :1258 :3857,
    candidate_terminal.py:371). Two declarative sites were missed:
    runtime-policy.json's readinessRequirements and the same string restated in
    candidate_runtime.TARGET. runtime-policy.json is consumed by the chain, not
    commentary, and its readinessRequirements are projected into the binding
    through TARGET_PROJECTION, so a stale one ships a false requirement to the
    host. "Fixed n-1 sites" is the shape that refused Hotel #5's setup three
    times; this test is the enumeration, kept executable.
    """
    sources = {
        rel: (ROOT / rel).read_text(encoding="utf-8")
        for rel in (
            "modules/hotel-reservation/execution/candidate_cell.py",
            "modules/hotel-reservation/execution/candidate_runtime.py",
            "modules/hotel-reservation/execution/runtime-policy.json",
            "modules/hotel-reservation/validation/candidate_terminal.py",
        )
    }
    # The five executable guards, and no sixth spelling of the old pin.
    # Comment lines are excluded: candidate_runtime.py:3850 records the re-pin
    # itself and legitimately names both the old and the new literal.
    def _code_lines(text: str) -> list[str]:
        return [line for line in text.splitlines() if not line.lstrip().startswith("#")]

    # 2026-09-21: host condition v2. The co-tenant is decommissioned, so the pin
    # survives in exactly two places, both retained for the 103 banked cells: the
    # terminal's v1 branch and the retired v1 record in runtime-policy.json. No
    # executable site on the v2 path may still carry it.
    per_source = {
        rel: sum(line.count('{"running": 5}') + line.count('{"running":5}') for line in _code_lines(text))
        for rel, text in sources.items()
    }
    assert per_source == {
        "modules/hotel-reservation/execution/candidate_cell.py": 0,
        "modules/hotel-reservation/execution/candidate_runtime.py": 0,
        # The JSON record is pretty-printed over three lines, so the one-line
        # literal count is 0 there; its content is asserted structurally below.
        "modules/hotel-reservation/execution/runtime-policy.json": 0,
        "modules/hotel-reservation/validation/candidate_terminal.py": 1,
    }, per_source
    retired = json.loads(sources["modules/hotel-reservation/execution/runtime-policy.json"])["retiredPostureCeilings"][0]
    assert retired["hostCondition"]["foreignStateCounts"] == {"running": 5}
    assert retired["hostCondition"]["foreignProject"] == "dps_training_k"
    for rel, text in sources.items():
        for stale in ('{"created": 1', '{"created":1', "created=1"):
            # The only admissible occurrences are the two comments that record
            # the re-pin itself; they are on lines beginning with '#'.
            for line in text.splitlines():
                if stale in line:
                    assert line.lstrip().startswith("#"), (rel, line)
    # The declarative string and the Python restatement of it must agree, and
    # must describe the guard that is actually enforced.
    policy = json.loads(
        (MODULE / "execution/runtime-policy.json").read_text(encoding="utf-8")
    )
    declared = policy["targetProjection"]["readinessRequirements"]
    assert declared == runtime.TARGET_PROJECTION["readinessRequirements"]
    nuisance = [row for row in declared if "no foreign Compose project present" in row]
    assert len(nuisance) == 1
    assert "states running=5 retained" not in nuisance[0]
    assert "decommissioned" in nuisance[0] and "must not be pooled" in nuisance[0]
    assert "created" not in nuisance[0]


# ---------------------------------------------------------------------------
# Target-binary spelling enumeration (2026-09-19)
#
# /usr/sbin/runuser exists only on fb14srv4; fb14srv5 and fb14srv6 carry
# /sbin/runuser (research/host-topology.json). Hotel baked /usr/sbin/runuser at
# 9 sites and /usr/bin/python3 at 13 and worked purely because it runs on the
# one host where the guess is right -- the same latent defect that killed OTel's
# first real launch on 2026-09-17. After the sweep the ONLY places any absolute
# spelling may appear as an executable constant are the candidate tuples.
# ---------------------------------------------------------------------------

TARGET_BINARY_SPELLINGS = frozenset({
    "/usr/sbin/runuser", "/sbin/runuser", "/usr/bin/python3", "/bin/python3",
})


def executable_spelling_sites(source: str, label: str) -> list[str]:
    """Every absolute target-binary spelling that is a CONSTANT of this program.

    AST, not grep: a comment or a docstring that names a path is prose, while a
    string constant is a thing the process will exec. Bare-string statements
    (module/function/class docstrings) are the one string kind excluded.
    """
    import ast as _ast

    tree = _ast.parse(source, filename=label)
    docstrings = {
        id(node.body[0].value)
        for node in _ast.walk(tree)
        if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef))
        and node.body
        and isinstance(node.body[0], _ast.Expr)
        and isinstance(node.body[0].value, _ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return sorted(
        node.value
        for node in _ast.walk(tree)
        if isinstance(node, _ast.Constant)
        and isinstance(node.value, str)
        and node.value in TARGET_BINARY_SPELLINGS
        and id(node) not in docstrings
    )


ALL_FOUR_SPELLINGS = sorted(TARGET_BINARY_SPELLINGS)


def test_the_spelling_extractor_actually_matches_something() -> None:
    """A green enumeration test whose extractor matches nothing is worse than none.

    Exactly that happened this week with a Hotel fixture that encoded two
    contradictory worlds and stayed green under both, so the extractor is
    exercised against a planted violation and against prose before it is
    trusted on the real module.
    """
    planted = (
        'import subprocess\n'
        'subprocess.run(["/usr/sbin/runuser", "--user", "fhuebscher", "--",\n'
        '                "/usr/bin/python3", "-I", "runner.py"])\n'
    )
    assert executable_spelling_sites(planted, "planted") == [
        "/usr/bin/python3", "/usr/sbin/runuser",
    ]
    prose = '"""A docstring naming /usr/sbin/runuser."""\n# and /usr/bin/python3\nx = 1\n'
    assert executable_spelling_sites(prose, "prose") == []
    # and it must find the four real ones in the module it is about to police
    source = (MODULE / "execution/candidate_runtime.py").read_text(encoding="utf-8")
    assert set(executable_spelling_sites(source, "candidate_runtime")) == TARGET_BINARY_SPELLINGS


def test_every_target_binary_spelling_lives_only_in_a_candidate_tuple() -> None:
    """The enumeration. A new hardcoded runuser or python3 fails here.

    The controller module and each embedded remote program are policed
    separately, because the remote programs are string constants executed by a
    second interpreter on the target and a sweep of the outer file alone leaves
    them open -- the "fixed n-1 of n sites" shape.
    """
    assert runtime.RUNUSER_CANDIDATES == ("/usr/sbin/runuser", "/sbin/runuser")
    assert runtime.TARGET_PYTHON_CANDIDATES == ("/usr/bin/python3", "/bin/python3")

    source = (MODULE / "execution/candidate_runtime.py").read_text(encoding="utf-8")
    # Exactly four constants, one per spelling: the two candidate tuples and
    # nothing else. Any additional occurrence is a new hardcoded site.
    assert executable_spelling_sites(source, "candidate_runtime") == ALL_FOUR_SPELLINGS

    # The embedded remote programs that build argv carry their own tuples; the
    # two that do not build argv must carry no spelling at all.
    for label, program, expected in (
        ("REMOTE_ONE_SHOT_INSTALL", runtime.REMOTE_ONE_SHOT_INSTALL, ALL_FOUR_SPELLINGS),
        ("REMOTE_DETACHED_LAUNCH", runtime.REMOTE_DETACHED_LAUNCH, ALL_FOUR_SPELLINGS),
        ("REMOTE_STATUS", runtime.REMOTE_STATUS, []),
        ("REMOTE_REFETCH_ARCHIVE", runtime.REMOTE_REFETCH_ARCHIVE, []),
    ):
        assert executable_spelling_sites(program, label) == expected, label
        if expected:
            assert 'RUNUSER_CANDIDATES=("/usr/sbin/runuser","/sbin/runuser")' in program
            assert 'PYTHON_CANDIDATES=("/usr/bin/python3","/bin/python3")' in program

    # The other Hotel modules never spelled a target binary and must not start.
    for relative in (
        "execution/candidate_cell.py",
        "execution/candidate_pilot.py",
        "validation/candidate_terminal.py",
        "execution/runtime-policy.json",
    ):
        text = (MODULE / relative).read_text(encoding="utf-8")
        assert not (TARGET_BINARY_SPELLINGS & set(text.split('"'))), relative


def test_process_local_resolution_is_strict_and_fails_closed(tmp_path: Path) -> None:
    """TeaStore's form: no PATH, root-owned regular executable, lstat not stat."""
    with pytest.raises(runtime.GateError, match="no root-owned runuser"):
        runtime._resolve_target_binary("runuser", ("/nonexistent/runuser",))
    plain = tmp_path / "not-executable"
    plain.write_text("", encoding="utf-8")
    with pytest.raises(runtime.GateError, match="no root-owned"):
        runtime._resolve_target_binary("python3", (str(plain),))
    link = tmp_path / "linked"
    link.symlink_to("/usr/bin/true")
    with pytest.raises(runtime.GateError, match="no root-owned"):
        runtime._resolve_target_binary("python3", (str(link),))
    # a root-owned regular executable resolves, and the first candidate wins
    assert runtime._resolve_target_binary("true", ("/usr/bin/true",)) == "/usr/bin/true"
    assert runtime._resolve_target_binary(
        "true", ("/nonexistent/a", "/usr/bin/true"),
    ) == "/usr/bin/true"


def test_over_ssh_resolution_walks_candidates_in_order_and_records_the_probe(
    monkeypatch,
) -> None:
    """OTel's form: ask the target, prove `test -x` at exactly the resolved path."""
    monkeypatch.setattr(runtime, "_SSH_BINARY_CACHE", {})
    monkeypatch.setattr(runtime, "_SSH_BINARY_PROBES", [])
    seen: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        seen.append(list(argv))
        # stand in for fb14srv5/fb14srv6: only /sbin/runuser exists
        code = 0 if argv[-1] == "/sbin/runuser" else 1
        return subprocess.CompletedProcess(argv, code, b"", b"")

    resolved = runtime.resolve_target_binary_over_ssh(
        "runuser", destination="root@fb14srv6", runner=fake_run,
    )
    assert resolved == "/sbin/runuser"
    # it tried fb14srv4's spelling first and proved the one it returned
    assert [argv[-3:] for argv in seen] == [
        ["test", "-x", "/usr/sbin/runuser"], ["test", "-x", "/sbin/runuser"],
    ]
    assert [probe["returnCode"] for probe in runtime._SSH_BINARY_PROBES] == [1, 0]
    assert runtime._SSH_BINARY_PROBES[-1]["candidate"] == resolved
    # cached: a second call spends the same token without a second probe
    assert runtime.resolve_target_binary_over_ssh(
        "runuser", destination="root@fb14srv6", runner=fake_run,
    ) == resolved
    assert len(seen) == 2

    def refusing_run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 1, b"", b"")

    with pytest.raises(runtime.GateError, match="no executable python3"):
        runtime.resolve_target_binary_over_ssh(
            "python3", destination="root@fb14srv6", runner=refusing_run,
        )


def test_readiness_replay_seams_admit_only_the_two_fixed_spellings() -> None:
    """Declared widening: these seams took one spelling, they now take two.

    Before this change `target-runner-executable-replay` accepted exactly
    /usr/sbin/runuser and /usr/bin/python3. It now accepts either member of the
    fixed absolute candidate list, so fb14srv5/fb14srv6 evidence stops being
    rejected for the only spelling those hosts have. Nothing else is admitted:
    a relative name, a PATH lookup or any path off the list still fails.
    """
    for spelling in runtime.RUNUSER_CANDIDATES:
        facts = {"argv": [spelling, "--user"]}
        assert runtime._replayed_spelling(facts, 0, "runuser", runtime.RUNUSER_CANDIDATES) == spelling
    for rejected in ("runuser", "/usr/local/bin/runuser", "", None, 7):
        facts = {"argv": [rejected, "--user"]}
        assert runtime._replayed_spelling(
            facts, 0, "runuser", runtime.RUNUSER_CANDIDATES,
        ) == runtime.RUNUSER_CANDIDATES[0]
    for malformed in ({}, {"argv": "not-a-list"}, {"argv": []}, "not-a-mapping", None):
        assert runtime._replayed_spelling(
            malformed, 0, "python3", runtime.TARGET_PYTHON_CANDIDATES,
        ) == runtime.TARGET_PYTHON_CANDIDATES[0]


def test_cpu_replay_sums_sequentially_independent_of_interpreter():
    """F-ADH-069: builtin sum() over floats is Neumaier-compensated on CPython >= 3.12
    (gh-100425) but a plain left fold on the 3.9 hosts. The collector and the validator
    must share one interpreter-independent formula, or an offline replay differs from
    the host-written applicationCpuSeconds by one ulp and the bit-exact cell terminal
    gate rejects a valid cell (33 of 103 banked Hotel cells under 3.13)."""
    values = [0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    # Literal pinned to the 3.9 left fold; compensated summation returns 0.6 exactly.
    assert resources._sequential_sum(values) == 0.6000000000000001
    identities = {f"{index:064x}": service for index, service in enumerate(resources.APPLICATION_SERVICES, 1)}

    def sample(at: float, percents):
        rows = [
            {"service": service, "containerId": container, "cpuPercent": percent}
            for (container, service), percent in zip(identities.items(), percents)
        ]
        return {
            "capturedAtEpoch": 100.0 + at,
            "capturedAtMonotonic": at,
            "containers": rows,
            "applicationCpuPercent": resources._sequential_sum(percents),
        }

    document = {
        "schemaVersion": 1,
        "contract": resources.RESOURCE_CONTRACT,
        "project": "hotel_candidate_v4_deadbeef_01",
        "applicationServices": list(resources.APPLICATION_SERVICES),
        "containerIdentities": identities,
        "windowStartMonotonic": 10.0,
        "windowEndMonotonic": 12.0,
        "intervalSeconds": 1.0,
        "samples": [sample(10.0, values), sample(11.0, values), sample(12.0, values)],
        "captureComplete": True,
    }
    # 0.6000000000000001 / 100 * 1.0 accumulated over two unit intervals, left to right.
    expected = 0.0
    for _ in range(2):
        expected += 0.6000000000000001 / 100.0 * 1.0
    assert resources.validate_cpu(document)["applicationCpuSeconds"] == expected
    assert repr(resources.validate_cpu(document)["applicationCpuSeconds"]) == "0.012000000000000002"


_HOTEL5_EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "observability-placement" / "tmp" / "hotel5-evidence" / "hotel-v1-20260918t020605z-658f9b6a"
)


@pytest.mark.skipif(not _HOTEL5_EVIDENCE.is_dir(), reason="retained Hotel campaign #5 tree is not on this machine")
def test_cpu_replay_reproduces_every_retained_hotel5_cell_bit_for_bit():
    """Regression for F-ADH-069 against the banked evidence itself: the replayed
    applicationCpuSeconds must equal the host-written value with ==, on any interpreter."""
    cells = sorted(_HOTEL5_EVIDENCE.glob("runs/**/cpu.json"))
    assert len(cells) == 24
    for cpu_path in cells:
        document = json.loads(cpu_path.read_bytes())
        terminal = json.loads((cpu_path.parent / "cell-terminal.json").read_bytes())
        replay = resources.validate_cpu(document)["applicationCpuSeconds"]
        assert replay == terminal["cpu"]["applicationCpuSeconds"], cpu_path
        assert replay == document["applicationCpuSeconds"], cpu_path


def test_not_poolable_with_names_the_retired_plan_digest_not_prose():
    """The pooling boundary must be checkable, not only explained.

    `poolingBoundary` is a sentence; a tool cannot act on it. `notPoolableWith`
    must carry the compiled-plan digest of every retired host condition, which is
    what a cell from the other condition actually carries.
    """
    policy = runtime._validate_policy(runtime._json_file(runtime.POLICY, "runtime policy"))
    current = policy["hostCondition"]["id"]
    retired = [
        row for row in policy["retiredPostureCeilings"]
        if row["hostCondition"]["id"] != current
    ]
    observed = runtime.not_poolable_with()
    assert observed == sorted(row["compiledPlanCanonicalSha256"] for row in retired)
    assert observed, "a retired host condition exists, so the list must not be empty"
    assert all(len(d) == 64 for d in observed)
    # and it must NOT contain the current plan: a cell is poolable with its own kind
    assert runtime._load_compiler().EXPECTED_PLAN_SHA256 not in observed


def test_nuisance_writer_and_validator_agree_on_the_v2_key_set():
    """The writer's nuisance keys must equal the validator's expected set.

    Both are source literals in different files. On 2026-09-22 a field was added to
    the writer and not the reader; the hand-written fixture tracked neither, so the
    divergence reached a host and stopped a campaign at cell 1. Comparing the two
    literals directly is what catches that class, rather than one more fixture that
    has to be remembered.
    """
    import ast

    def literal_keys(path: Path, marker: str) -> set[str]:
        tree = ast.parse(path.read_text())
        best: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = {k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                if marker in keys and len(keys) > len(best):
                    best = keys
            elif isinstance(node, ast.Set):
                keys = {e.value for e in node.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                if marker in keys and len(keys) > len(best):
                    best = keys
        assert best, f"no literal containing {marker!r} found in {path.name}"
        return best

    written = literal_keys(MODULE / "execution/candidate_cell.py", "poolingBoundary")
    expected = literal_keys(MODULE / "validation/candidate_terminal.py", "poolingBoundary")
    assert written == expected, (
        "nuisance v2 writer and validator disagree: "
        f"writer-only={sorted(written - expected)} validator-only={sorted(expected - written)}"
    )
    assert "notPoolableWith" in written
