from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_COMMIT = "a" * 40
FRAMEWORK_TREE = "b" * 40
NOW = datetime(2026, 8, 30, 2, 0, tzinfo=timezone.utc)


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(
    "teastore_runtime_successor_adapter",
    "modules/teastore/execution/candidate_runtime_adapter.py",
)
orchestrator = _load(
    "teastore_runtime_successor_orchestrator",
    "modules/teastore/execution/candidate_orchestrator.py",
)
readiness_checker = _load(
    "teastore_runtime_successor_readiness",
    "modules/teastore/validation/candidate_readiness.py",
)
transport = _load(
    "teastore_runtime_successor_transport",
    "modules/teastore/execution/candidate_transport.py",
)
installer = _load(
    "teastore_runtime_successor_installer",
    "modules/teastore/execution/candidate_release_installer.py",
)
terminal = _load(
    "teastore_runtime_successor_terminal",
    "modules/teastore/validation/candidate_terminal.py",
)
remote = _load(
    "teastore_runtime_successor_remote",
    "modules/teastore/execution/candidate_remote_controller.py",
)
performance = _load(
    "teastore_runtime_successor_cell_producer",
    "modules/teastore/execution/performance_campaign.py",
)
cell_entry = _load(
    "teastore_runtime_successor_cell_entry",
    "modules/teastore/execution/candidate_cell_executor.py",
)


def _write(path: Path, document: object) -> bytes:
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _git_state():
    return runtime.GitRepositoryState(
        commit=FRAMEWORK_COMMIT,
        head_tree=FRAMEWORK_TREE,
        commit_tree=FRAMEWORK_TREE,
        tracked_dirty=False,
        status=b"",
        concealment_config=b"",
        index_concealment=(),
    )


@pytest.fixture
def bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runtime, "_git_repository_state", _git_state)
    campaign = tmp_path / "campaign"
    orchestrator.materialize_campaign(campaign)
    return runtime.inspect_campaign(campaign, FRAMEWORK_COMMIT)


def _images() -> dict[str, str]:
    repositories = {
        **{
            service: image.rsplit(":", 1)[0]
            if ":" in image.rsplit("/", 1)[-1] else image
            for service, image in runtime.DECLARED_RUNTIME_IMAGES.items()
        },
        **runtime.PATCHED_IMAGE_REPOSITORIES,
    }
    return {
        service: f"{repositories[service]}@sha256:{index:x}" + (f"{index:x}" * 63)
        for index, service in enumerate(runtime.IMAGE_SERVICES, 1)
    }


def _systemd_status(
    campaign_id: str, setup_id: str, package_sha256: str, *, running: bool,
) -> dict:
    return {
        # Deliberately the installer's own derivation. This fixture stands in
        # for the remote producer, so the transport has to be checked against
        # what the target actually emits rather than a local restatement of it.
        "unitName": installer._campaign_unit_name(
            campaign_id, setup_id, package_sha256,
        ),
        "loadState": "loaded",
        "activeState": "active" if running else "inactive",
        "subState": "running" if running else "dead",
        "result": "success",
        "execMainStatus": 0,
        "rawSha256": "9" * 64,
    }


def _image_build_receipt(
    bindings, *, setup_id: str, images: dict[str, str],
) -> dict:
    services = {}
    for service, declared in runtime.DECLARED_RUNTIME_IMAGES.items():
        patched = service in runtime.PATCHED_IMAGE_REPOSITORIES
        services[service] = {
            "mode": "patched-build" if patched else "exact-inspection",
            "declaredImage": declared,
            "imageConfigId": images[service].split("@", 1)[1],
            "localContentReference": images[service],
            "architecture": "amd64", "operatingSystem": "linux",
            "repoDigests": [],
            "artifactSha256": "6" * 64 if patched else None,
            "dockerfileSha256": "7" * 64 if patched else None,
            "labels": {
                "org.opencontainers.image.revision": runtime.SOURCE_COMMIT,
                "org.observability-placement.patch.sha256": runtime.PATCH_SHA256,
                "org.observability-placement.service": service,
            } if patched else {},
        }
    return {
        "schemaVersion": 1, "kind": runtime.IMAGE_BUILD_KIND,
        "setupId": setup_id, "target": runtime.TARGET,
        "executionUser": runtime.EXECUTION_USER,
        "executionUid": runtime.EXECUTION_UID,
        "executionGid": runtime.EXECUTION_GID,
        "frameworkCommit": bindings.framework_commit,
        "sourceCommit": runtime.SOURCE_COMMIT,
        "patchSha256": runtime.PATCH_SHA256,
        "inputContractSha256": hashlib.sha256((
            ROOT / "modules/teastore/images/patched-image-inputs.json"
        ).read_bytes()).hexdigest(),
        "mavenCommand": list(runtime.MAVEN_COMMAND),
        "mavenStdoutSha256": "4" * 64,
        "mavenStderrSha256": "5" * 64,
        "services": services, "imageDigests": copy.deepcopy(images),
        "buildStartedAt": (NOW - timedelta(minutes=2)).isoformat(),
        "completedAt": (NOW - timedelta(minutes=1, seconds=30)).isoformat(),
        "cellsRun": 0, "containersStarted": 0,
        "temporaryContainersRemoved": True, "ready": True,
        "priorDeclaredImageConfigIds": {
            service: None for service in runtime.PATCHED_IMAGE_REPOSITORIES
        },
        "uniqueBuildTags": {
            service: f"{repository}:candidate-{setup_id}"
            for service, repository in runtime.PATCHED_IMAGE_REPOSITORIES.items()
        },
        "promotionAuthorized": False,
    }


def _input(
    seam: str, bindings, images: dict[str, str], facts: dict,
) -> dict:
    validator = "modules/teastore/validation/candidate_readiness.py"
    context = {
        "frameworkCommit": bindings.framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "imageDigests": copy.deepcopy(images),
    }
    raw = {
        "checker": f"candidate-readiness-v2:{seam}",
        "argv": ["/usr/bin/python3", "-I", validator, "probe", seam],
        "exitCode": 0,
        "stdout": json.dumps({"facts": facts}, sort_keys=True) + "\n",
        "stderr": "",
        "inputSha256": readiness_checker.canonical_sha256(context),
    }
    return {
        "schemaVersion": 1,
        "kind": readiness_checker.INPUT_KIND,
        "seam": seam,
        "target": "fb14srv5",
        "frameworkCommit": bindings.framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "imageDigests": copy.deepcopy(images),
        "capturedAt": "2026-08-30T01:55:00Z",
        "rawObservations": raw,
    }


def _retained_pairs() -> list[dict]:
    document = json.loads(
        (ROOT / "tests/fixtures/teastore-candidate-readiness-pairs.json").read_text()
    )
    assert document["schemaVersion"] == 1
    return document["pairs"]


def _setup_documents(bindings) -> tuple[dict, dict, dict, dict, dict, dict]:
    plan = _plan(bindings)
    target = {
        "schemaVersion": 1, "kind": runtime.TARGET_PROOF_KIND,
        "target": runtime.TARGET,
        "capturedAt": (NOW - timedelta(minutes=4)).isoformat(),
        "probeSha256": bindings.controller_sha256["candidate-release-installer"],
        "hostIdentity": {
            "hostname": runtime.TARGET,
            "fqdn": runtime.TARGET_HOSTNAME,
            "machineIdSha256": runtime.TARGET_MACHINE_ID_SHA256,
        },
        "pythonRuntime": {
            "executable": "/usr/bin/python3", "version": [3, 9, 2],
            "requiredLanguageVersion": [3, 9], "observedTargetPatch": [3, 9, 2],
        },
        "transport": {"user": "root", "uid": 0, "gid": 0},
        "executionCapabilities": {
            "root": {"uid": 0, "gid": 0, "supplementaryGids": [0],
                     "home": "/root", "executionMethod": "direct",
                     "dockerAccess": True, "dockerProbeExitCode": 0},
            "stig": {"uid": 1015, "gid": 1015,
                     "supplementaryGids": [999, 1015], "home": "/home/stig",
                     "executionMethod": "runuser", "dockerAccess": True,
                     "dockerProbeExitCode": 0},
        },
        "dockerSocket": {"path": "/var/run/docker.sock", "ownerUid": 0,
                         "ownerGid": 999, "mode": "0660"},
        "legacyRoots": [
            {"path": "/home/stig/observability-placement-runs", "exists": True,
             "ownerUid": 0, "ownerGid": 0, "mode": "0700",
             "accessibleByStig": False},
            {"path": "/home/stig/observability-placement-results", "exists": True,
             "ownerUid": 0, "ownerGid": 0, "mode": "0700",
             "accessibleByStig": False},
        ],
        "candidateV4Root": {"path": runtime.CANDIDATE_V4_ROOT, "exists": False},
    }
    release = {
        "schemaVersion": 1, "kind": runtime.RELEASE_MANIFEST_KIND,
        "frameworkCommit": bindings.framework_commit,
        "frameworkTree": bindings.framework_tree,
        "bundleFormat": "candidate-v4-tar-v1", "bundleSha256": "c" * 64,
        "bundleBytes": 4096,
        "bundleMembers": {
            "superproject.bundle": {"sha256": "d" * 64, "bytes": 2048,
                                    "commit": bindings.framework_commit,
                                    "tree": bindings.framework_tree},
            "upstream-teastore.bundle": {"sha256": "e" * 64, "bytes": 1024,
                                         "commit": "34b37f7e7be433ce72d5f9455e66922a13116749",
                                         "tree": "f" * 40},
        },
        "controllerDigests": copy.deepcopy(bindings.controller_sha256),
        "submoduleCommits": {
            "upstream/teastore": "34b37f7e7be433ce72d5f9455e66922a13116749"
        },
        "setupSourceBuildAllowed": True, "campaignSourceBuildAllowed": False,
    }
    authorization = runtime.setup_authorization(
        bindings, runtime.canonical_sha256(plan), target, release,
        setup_id="1" * 32, execution_user="stig",
        not_before=(NOW - timedelta(minutes=3)).isoformat(),
        authorization_deadline=(NOW + timedelta(hours=10)).isoformat(),
    )
    setup = {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-exact-setup-only",
        "typedApproval": runtime.expected_gate_setup_text(authorization),
        "approvedBy": "human-fixture",
        "approvedAt": (NOW - timedelta(minutes=2)).isoformat(),
        "authorization": authorization, "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }
    image_build = _image_build_receipt(
        bindings, setup_id=authorization["setupId"], images=_images(),
    )
    receipt = {
        "schemaVersion": 1, "kind": runtime.RELEASE_INSTALL_KIND,
        "state": "installed", "setupId": authorization["setupId"],
        "target": runtime.TARGET, "transportUser": "root",
        "executionUser": "stig", "executionUid": 1015, "executionGid": 1015,
        "executionMethod": "runuser", "frameworkCommit": bindings.framework_commit,
        "frameworkTree": bindings.framework_tree,
        "bundleSha256": release["bundleSha256"],
        "releaseManifestSha256": runtime.canonical_sha256(release),
        "gateSetupSha256": runtime.canonical_sha256(setup),
        "releaseRoot": authorization["releaseRoot"],
        "resultsRoot": authorization["resultsRoot"],
        "exclusiveLeasePath": runtime.LEASE_PATH,
        "controllerDigests": copy.deepcopy(bindings.controller_sha256),
        "imageBuildReceiptSha256": runtime.canonical_sha256(image_build),
        "imageBuild": image_build,
        "activationCompile": transport.expected_activation_compile(),
        "installedAt": (NOW - timedelta(minutes=1)).isoformat(),
        "runtimeExecuted": False, "promotionAuthorized": False,
    }
    summary = {key: value for key, value in receipt.items() if key not in {
        "schemaVersion", "kind", "state", "runtimeExecuted", "promotionAuthorized"
    }}
    return plan, target, release, setup, receipt, summary


def _semantic_readiness(tmp_path: Path, bindings) -> dict:
    root = tmp_path / "runtime-readiness-artifacts"
    root.mkdir(parents=True)
    plan, target, release_manifest, gate_setup, install, release_summary = (
        _setup_documents(bindings)
    )
    setup_artifacts = {}
    for camel, stem, document in (
        ("gatePlan", "gate-plan", plan),
        ("targetProof", "target-proof", target),
        ("releaseManifest", "release-manifest", release_manifest),
        ("gateSetup", "gate-setup", gate_setup),
        ("releaseInstall", "release-install", install),
    ):
        relative = f"setup/{stem}.json"
        payload = _write(root / relative, document)
        setup_artifacts[f"{camel}Path"] = relative
        setup_artifacts[f"{camel}BytesSha256"] = hashlib.sha256(payload).hexdigest()
    images = _images()
    validator_sha = bindings.controller_sha256["candidate-readiness-checker"]
    seams: dict[str, dict] = {}
    for row in _retained_pairs():
        seam = row["seam"]
        assert row["facts"] == readiness_checker.SEAM_EXPECTED_VALUES[seam]
        positive = _input(seam, bindings, images, row["facts"])
        defect = copy.deepcopy(positive)
        plant = row["plantedDefect"]
        planted_facts = copy.deepcopy(row["facts"])
        planted_facts[plant["field"]] = plant["value"]
        defect["rawObservations"]["stdout"] = (
            json.dumps({"facts": planted_facts}, sort_keys=True) + "\n"
        )
        positive_report = readiness_checker.check_input(
            positive,
            seam=seam,
            framework_commit=bindings.framework_commit,
            descriptor_sha256=bindings.descriptor_sha256,
            plan_sha256=bindings.plan_sha256,
            image_digests=images,
        )
        defect_report = readiness_checker.check_input(
            defect,
            seam=seam,
            framework_commit=bindings.framework_commit,
            descriptor_sha256=bindings.descriptor_sha256,
            plan_sha256=bindings.plan_sha256,
            image_digests=images,
        )
        assert positive_report["verdict"] == "pass"
        assert defect_report["verdict"] == "blocked"
        prefix = seam
        paths = {
            "positiveInput": f"pairs/{prefix}.positive.input.json",
            "positiveReport": f"pairs/{prefix}.positive.report.json",
            "defectInput": f"pairs/{prefix}.defect.input.json",
            "defectReport": f"pairs/{prefix}.defect.report.json",
        }
        payloads = {
            "positiveInput": _write(root / paths["positiveInput"], positive),
            "positiveReport": _write(root / paths["positiveReport"], positive_report),
            "defectInput": _write(root / paths["defectInput"], defect),
            "defectReport": _write(root / paths["defectReport"], defect_report),
        }
        evidence = {
            "schemaVersion": 1,
            "kind": runtime.READINESS_EVIDENCE_KIND,
            "seam": seam,
            "status": "pass",
            "validatorSha256": validator_sha,
            "observations": {
                "inputPath": paths["positiveInput"],
                "inputSha256": hashlib.sha256(payloads["positiveInput"]).hexdigest(),
                "reportPath": paths["positiveReport"],
                "reportSha256": hashlib.sha256(payloads["positiveReport"]).hexdigest(),
            },
        }
        witness = {
            "schemaVersion": 1,
            "kind": runtime.FAILURE_WITNESS_KIND,
            "seam": seam,
            "status": "detected",
            "plantedDefect": f"{plant['field']}={plant['value']!r}",
            "checkerExitCode": 2,
            "validatorSha256": validator_sha,
            "observations": {
                "inputPath": paths["defectInput"],
                "inputSha256": hashlib.sha256(payloads["defectInput"]).hexdigest(),
                "reportPath": paths["defectReport"],
                "reportSha256": hashlib.sha256(payloads["defectReport"]).hexdigest(),
            },
        }
        evidence_path = f"receipts/{prefix}.positive.json"
        witness_path = f"receipts/{prefix}.defect.json"
        evidence_bytes = _write(root / evidence_path, evidence)
        witness_bytes = _write(root / witness_path, witness)
        seams[seam] = {
            "status": "pass",
            "evidencePath": evidence_path,
            "evidenceSha256": hashlib.sha256(evidence_bytes).hexdigest(),
            "failureWitnessPath": witness_path,
            "failureWitnessSha256": hashlib.sha256(witness_bytes).hexdigest(),
        }
    implementation_path = "transport/candidate_transport.py"
    implementation = (
        ROOT / "modules/teastore/execution/candidate_transport.py"
    ).read_bytes()
    destination = root / implementation_path
    destination.parent.mkdir()
    destination.write_bytes(implementation)
    readiness = {
        "schemaVersion": 2,
        "kind": runtime.READINESS_KIND,
        "studyEpoch": runtime.STUDY_EPOCH,
        "frameworkCommit": bindings.framework_commit,
        "descriptorCanonicalSha256": bindings.descriptor_sha256,
        "compiledPlanCanonicalSha256": bindings.plan_sha256,
        "target": "fb14srv5",
        "runCount": 27,
        "artifactRoot": root.name,
        "controllerDigests": copy.deepcopy(bindings.controller_sha256),
        "imageDigests": images,
        "patchedServices": list(runtime.PATCHED_SERVICES),
        "setupArtifacts": setup_artifacts,
        "release": release_summary,
        "ingressArchiveSha256": "8" * 64,
        "captureTreeSha256": None,
        "captureManifestPath": "capture-manifest.json",
        "captureManifestSha256": None,
        "runtimePreflight": {
            "schemaVersion": 1,
            "kind": runtime.RUNTIME_PREFLIGHT_KIND,
            "target": runtime.TARGET,
            "capturedAt": (NOW - timedelta(seconds=30)).isoformat(),
            "executionIdentity": {
                "user": "stig", "uid": 1015, "gid": 1015,
                "supplementaryGids": [999, 1015],
                "executionMethod": "runuser",
            },
            "docker": {
                "serverVersion": "29.6.1", "socketOwnerUid": 0,
                "socketOwnerGid": 999, "socketMode": "0660",
                "accessAsExecutionUser": True,
            },
            "resourceInventory": {
                "projectPrefix": "teastore_candidate_",
                "reservedPorts": [3306, 5672, 8080, 8082, 15672],
                "composeProjects": [{
                    "name": "docker", "status": "exited(5)",
                    "configFiles": "/home/stig/teastore/examples/docker/docker-compose_monitoring_linux.yaml",
                    "active": False, "candidateNamespace": False,
                }],
                "reservedPortListeners": [],
            },
            "blockers": [], "ready": True, "experimentalCellsExecuted": 0,
            "mutationPerformed": False,
        },
        "seams": seams,
        "transport": {
            "schemaVersion": 1,
            "contract": runtime.TRANSPORT_CONTRACT,
            "target": "fb14srv5",
            "transportUser": "root",
            "executionUser": "stig",
            "executionMethod": "runuser",
            "releaseRoot": release_summary["releaseRoot"],
            "resultsRoot": release_summary["resultsRoot"],
            "evidenceLabel": "candidate-evidence",
            "outerLeasePath": runtime.LEASE_PATH,
            "outerLeaseScope": "entire-27-cell-one-shot",
            "deadlineEnforced": True,
            "cleanupEnforced": True,
            "candidateDescriptorAccepted": True,
            "controllerDigests": copy.deepcopy(bindings.controller_sha256),
            "implementationPath": implementation_path,
            "implementationSha256": hashlib.sha256(implementation).hexdigest(),
        },
        "runtimeReady": True,
        "candidateEvidenceAuthorized": False,
        "promotionAuthorized": False,
    }
    entries = []
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        payload = path.read_bytes()
        entries.append({"path": path.relative_to(root).as_posix(), "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()})
    manifest = {"schemaVersion": 1, "kind": "teastore-candidate-root-capture-manifest-v2",
                "ingressArchiveSha256": readiness["ingressArchiveSha256"],
                "entries": entries,
                "entriesCanonicalSha256": runtime.canonical_sha256(entries)}
    manifest_payload = _write(tmp_path / "capture-manifest.json", manifest)
    readiness["captureTreeSha256"] = runtime.canonical_sha256(manifest)
    readiness["captureManifestSha256"] = hashlib.sha256(manifest_payload).hexdigest()
    return readiness


def _plan(bindings) -> dict:
    return {
        "schemaVersion": 1,
        "kind": runtime.PLAN_KIND,
        "gate": "GATE-PLAN",
        "decision": "approve-exact-plan",
        "typedApproval": runtime.expected_gate_plan_text(bindings),
        "approvedBy": "human-fixture",
        "approvedAt": (NOW - timedelta(minutes=5)).isoformat(),
        "bindings": runtime.plan_binding(bindings),
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }


def _run(bindings, plan: dict, readiness: dict) -> dict:
    authorization = runtime.run_authorization(
        bindings,
        runtime.canonical_sha256(plan),
        runtime.canonical_sha256(readiness),
        readiness=readiness,
        campaign_id="teastore-candidate-20260830",
        not_before=(NOW - timedelta(minutes=1)).isoformat(),
        authorization_deadline=(NOW + timedelta(hours=9)).isoformat(),
    )
    return {
        "schemaVersion": 1,
        "kind": runtime.RUN_KIND,
        "gate": "GATE-RUN",
        "decision": "authorize-one-shot-exact-run",
        "typedApproval": runtime.expected_gate_run_text(authorization),
        "approvedBy": "human-fixture",
        "approvedAt": NOW.isoformat(),
        "authorization": authorization,
        "promotionAuthorized": False,
    }


def _package(tmp_path: Path, bindings):
    readiness = _semantic_readiness(tmp_path, bindings)
    assert runtime.validate_readiness(
        readiness, bindings, readiness_parent=tmp_path,
    ) == runtime.canonical_sha256(readiness)
    plan = _plan(bindings)
    run = _run(bindings, plan, readiness)
    return runtime.RuntimePackage(
        bindings=bindings,
        gate_plan=plan,
        gate_plan_sha256=runtime.canonical_sha256(plan),
        readiness=readiness,
        readiness_sha256=runtime.canonical_sha256(readiness),
        gate_run=run,
        gate_run_sha256=runtime.canonical_sha256(run),
        validated_at=NOW,
    )


def test_all_retained_readiness_pairs_are_replayed_positive_and_watched_failing(
    tmp_path: Path, bindings,
) -> None:
    readiness = _semantic_readiness(tmp_path, bindings)
    assert set(readiness["seams"]) == set(runtime.READINESS_SEAMS)
    assert runtime.validate_readiness(
        readiness, bindings, readiness_parent=tmp_path,
    ) == runtime.canonical_sha256(readiness)


@pytest.mark.parametrize("plant", ("active-foreign", "candidate-collision", "port"))
def test_installed_preflight_preserves_stopped_foreign_but_rejects_conflicts(
    tmp_path: Path, bindings, plant: str,
) -> None:
    readiness = _semantic_readiness(tmp_path, bindings)
    inventory = readiness["runtimePreflight"]["resourceInventory"]
    if plant == "active-foreign":
        inventory["composeProjects"][0]["active"] = True
        inventory["composeProjects"][0]["status"] = "running(1)"
    elif plant == "candidate-collision":
        inventory["composeProjects"][0]["name"] = "teastore_candidate_stale"
        inventory["composeProjects"][0]["candidateNamespace"] = True
    else:
        inventory["reservedPortListeners"] = [{
            "port": 8080, "endpointSha256": "7" * 64,
        }]
    with pytest.raises(runtime.GateError, match="preflight"):
        runtime.validate_readiness(readiness, bindings, readiness_parent=tmp_path)


@pytest.mark.parametrize("row", _retained_pairs(), ids=lambda row: row["seam"])
def test_each_retained_planted_defect_is_observed_blocked(row: dict, bindings) -> None:
    images = _images()
    document = _input(row["seam"], bindings, images, row["facts"])
    plant = row["plantedDefect"]
    planted_facts = copy.deepcopy(row["facts"])
    planted_facts[plant["field"]] = plant["value"]
    document["rawObservations"]["stdout"] = (
        json.dumps({"facts": planted_facts}, sort_keys=True) + "\n"
    )
    report = readiness_checker.check_input(
        document,
        seam=row["seam"],
        framework_commit=bindings.framework_commit,
        descriptor_sha256=bindings.descriptor_sha256,
        plan_sha256=bindings.plan_sha256,
        image_digests=images,
    )
    assert report["verdict"] == "blocked"
    assert report["blockers"]


def test_readiness_checker_rejects_boolean_integer_coercion(bindings) -> None:
    images = _images()
    facts = copy.deepcopy(
        readiness_checker.SEAM_EXPECTED_VALUES["application-witness-finalization"]
    )
    facts["authMarkerPresent"] = 1
    report = readiness_checker.check_input(
        _input("application-witness-finalization", bindings, images, facts),
        seam="application-witness-finalization",
        framework_commit=bindings.framework_commit,
        descriptor_sha256=bindings.descriptor_sha256,
        plan_sha256=bindings.plan_sha256,
        image_digests=images,
    )
    assert report["verdict"] == "blocked"


def test_readiness_checker_rejects_malformed_utc_capture_time(bindings) -> None:
    images = _images()
    seam = "application-witness-finalization"
    document = _input(
        seam, bindings, images, readiness_checker.SEAM_EXPECTED_VALUES[seam],
    )
    document["capturedAt"] = "not-a-timeZ"
    report = readiness_checker.check_input(
        document,
        seam=seam,
        framework_commit=bindings.framework_commit,
        descriptor_sha256=bindings.descriptor_sha256,
        plan_sha256=bindings.plan_sha256,
        image_digests=images,
    )
    assert report["verdict"] == "blocked"


def test_target_allocation_freezes_root_transport_and_exact_stig_identity() -> None:
    allocation = json.loads(
        (ROOT / "modules/teastore/execution/candidate-target-v4.json").read_text()
    )
    assert allocation["host"] == "fb14srv5"
    assert allocation["transportUsers"] == ["root"]
    assert allocation["setupUsers"] == ["root"]
    assert allocation["executionIdentities"] == [{
        "user": "stig", "uid": 1015, "gid": 1015,
        "supplementalGids": [999],
    }]
    assert allocation["releaseParent"] == runtime.RELEASES_ROOT
    assert allocation["artifactParent"] == runtime.RESULTS_ROOT
    assert allocation["leasePath"] == runtime.LEASE_PATH
    assert allocation["runtimeEnabledByDefault"] is False


@pytest.mark.parametrize(
    "plant",
    ("alias-user", "legacy-access", "stig-uid", "docker-group", "socket-mode", "machine-id", "python-version"),
)
def test_target_probe_plants_fail_before_setup(bindings, plant: str) -> None:
    _, proof, _, _, _, _ = _setup_documents(bindings)
    if plant == "alias-user":
        proof["transport"]["user"] = "stig"
    elif plant == "legacy-access":
        proof["legacyRoots"][0]["accessibleByStig"] = True
    elif plant == "stig-uid":
        proof["executionCapabilities"]["stig"]["uid"] = 0
    elif plant == "docker-group":
        proof["executionCapabilities"]["stig"]["supplementaryGids"] = [1015]
    elif plant == "socket-mode":
        proof["dockerSocket"]["mode"] = "0666"
    elif plant == "machine-id":
        proof["hostIdentity"]["machineIdSha256"] = "0" * 64
    elif plant == "python-version":
        proof["pythonRuntime"]["version"] = [3, 8, 18]
    with pytest.raises(runtime.GateError):
        runtime.validate_target_proof(proof, bindings)


def test_target_installed_python39_closure_imports_directly() -> None:
    """The exact target interpreter must evaluate every installed module."""
    modules = (
        "modules/teastore/execution/candidate_release_installer.py",
        "modules/teastore/execution/candidate_remote_controller.py",
        "modules/teastore/execution/candidate_runtime_adapter.py",
        "modules/teastore/execution/candidate_transport.py",
        "modules/teastore/execution/performance_campaign.py",
        "modules/teastore/validation/candidate_readiness.py",
        "modules/teastore/validation/candidate_pilot.py",
        "modules/teastore/validation/candidate_terminal.py",
    )
    for relative in modules:
        result = subprocess.run(
            ["/usr/bin/python3", "-I", "-c",
             "import runpy,sys; runpy.run_path(sys.argv[1],run_name='target_import')",
             str(ROOT / relative)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        assert result.returncode == 0, (relative, result.stderr.decode())


@pytest.mark.parametrize("partial", (False, True), ids=("final-collision", "partial-install"))
def test_release_install_path_collisions_are_distinct_and_fail_closed(
    tmp_path: Path, partial: bool,
) -> None:
    final = tmp_path / "release"
    pending = tmp_path / ".pending-setup"
    (pending if partial else final).mkdir()
    expected = "partial" if partial else "collision"
    with pytest.raises(installer.InstallError, match=expected):
        installer._reject_install_collision(final, pending)


def _setup_input_files(tmp_path: Path, bindings) -> tuple[dict[str, Path], dict]:
    plan, target, release, _, _, _ = _setup_documents(bindings)
    bundle = b"candidate-v4-bundle-fixture" * 200
    release["bundleSha256"] = hashlib.sha256(bundle).hexdigest()
    release["bundleBytes"] = len(bundle)
    authorization = runtime.setup_authorization(
        bindings, runtime.canonical_sha256(plan), target, release,
        setup_id="2" * 32, execution_user="stig",
        not_before=(NOW - timedelta(minutes=1)).isoformat(),
        authorization_deadline=(NOW + timedelta(hours=1)).isoformat(),
    )
    setup = {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-exact-setup-only",
        "typedApproval": runtime.expected_gate_setup_text(authorization),
        "approvedBy": "human-fixture", "approvedAt": NOW.isoformat(),
        "authorization": authorization, "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }
    paths = {}
    for name, document in (
        ("gate_plan", plan), ("target_proof", target),
        ("release_manifest", release), ("gate_setup", setup),
    ):
        path = tmp_path / f"{name}.json"
        _write(path, document)
        paths[name] = path
    paths["bundle"] = tmp_path / "release.tar"
    paths["bundle"].write_bytes(bundle)
    return paths, setup


def test_setup_uses_explicit_root_transport_and_cleans_partial_staging(
    tmp_path: Path, bindings,
) -> None:
    paths, _ = _setup_input_files(tmp_path, bindings)
    calls: list[tuple[str, ...]] = []
    scp_count = 0

    def runner(argv, _data):
        nonlocal scp_count
        calls.append(tuple(argv))
        if argv[0] == "scp":
            scp_count += 1
            return transport.CommandResult(1 if scp_count == 3 else 0, b"", b"")
        if "cleanup-staging" in argv:
            return transport.CommandResult(0, b'{"state":"clean"}', b"")
        raise AssertionError(argv)

    controller = transport.BoundedSrv5SetupController(
        bindings=bindings, runner=runner, clock=lambda: NOW,
    )
    with pytest.raises(transport.TransportError, match="staging failed"):
        controller.setup(
            gate_plan_path=paths["gate_plan"],
            target_proof_path=paths["target_proof"],
            release_manifest_path=paths["release_manifest"],
            gate_setup_path=paths["gate_setup"], bundle_path=paths["bundle"],
        )
    transfers = [call for call in calls if call[0] == "scp"]
    assert transfers
    assert all(call[-1].startswith("root@fb14srv5:/root/") for call in transfers)
    assert "cleanup-staging" in calls[-1]


def test_setup_failure_accepts_exact_installer_cleanup_receipt_without_relaunch(
    tmp_path: Path, bindings,
) -> None:
    paths, setup = _setup_input_files(tmp_path, bindings)
    setup_id = setup["authorization"]["setupId"]
    calls: list[tuple[str, ...]] = []

    def runner(argv, _data):
        calls.append(tuple(argv))
        if argv[0] == "scp":
            return transport.CommandResult(0, b"", b"")
        if " setup " in f" {' '.join(argv)} ":
            blocked = {
                "state": "blocked",
                "error": "InstallError: planted incomplete release",
                "stagingCleanup": {
                    "schemaVersion": 1,
                    # Must stay byte-identical to the literal the installer
                    # actually emits; see test_staging_cleanup_kind_does_not_drift.
                    "kind": "teastore-candidate-setup-staging-cleanup-v1",
                    "state": "clean",
                    "setupId": setup_id,
                },
            }
            return transport.CommandResult(
                2, json.dumps(blocked).encode() + b"\n", b"",
            )
        raise AssertionError(argv)

    controller = transport.BoundedSrv5SetupController(
        bindings=bindings, runner=runner, clock=lambda: NOW,
    )
    with pytest.raises(transport.TransportError, match="installation failed"):
        controller.setup(
            gate_plan_path=paths["gate_plan"],
            target_proof_path=paths["target_proof"],
            release_manifest_path=paths["release_manifest"],
            gate_setup_path=paths["gate_setup"], bundle_path=paths["bundle"],
        )
    assert sum("cleanup-staging" in call for call in calls) == 0


def test_staging_cleanup_kind_does_not_drift() -> None:
    """The installer produces this literal and the transport consumes it.

    They live in separate files and only meet on the wire during a real remote
    setup, so a mismatch is invisible to any test that mocks one side. A
    divergence makes the transport relaunch a cleanup the installer already
    completed, which fails and masks the installer's real diagnosis.
    """

    emitted = (
        ROOT / "modules/teastore/execution/candidate_release_installer.py"
    ).read_text()
    consumed = (
        ROOT / "modules/teastore/execution/candidate_transport.py"
    ).read_text()
    kind = "teastore-candidate-setup-staging-cleanup-v1"
    assert f'"kind": "{kind}"' in emitted
    assert kind in consumed
    # The pre-fix consumer literal must not reappear on either side.
    stale = "teastore-candidate-staging-cleanup-v1"
    assert f'"{stale}"' not in emitted
    assert f'"{stale}"' not in consumed


def test_git_cleanliness_survives_a_stale_stat_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A freshly installed release has a stale stat cache and must read clean.

    git diff-index --quiet short-circuits on a stat mismatch instead of reading
    content, so extract + chown + seal made every tracked file look modified
    even though each byte matched HEAD. The harness also sets
    GIT_OPTIONAL_LOCKS=0, so its own git status never refreshed the cache on
    the way past. Readiness could therefore never pass on a fresh install.
    """

    repository = tmp_path / "repo"
    repository.mkdir()

    def run(*arguments: str) -> None:
        subprocess.run(
            ("git", "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "-C", str(repository), *arguments),
            check=True, capture_output=True,
        )

    run("init", "-q", "-b", "main")
    (repository / "tracked.txt").write_text("exact bytes\n")
    (repository / "script.sh").write_text("#!/bin/sh\n")
    (repository / "script.sh").chmod(0o755)
    run("add", "-A")
    run("commit", "-q", "-m", "initial")
    monkeypatch.setattr(runtime, "ROOT", repository)

    # Stale stat cache, byte-identical content: must read clean.
    for name in ("tracked.txt", "script.sh"):
        path = repository / name
        mode = path.stat().st_mode
        path.write_text(path.read_text())
        path.chmod(mode)
        os.utime(path, (0, 0))
    state = runtime._git_repository_state()
    assert not state.tracked_dirty, "stale stat cache misreported as tracked dirt"
    assert not state.status

    # A genuine content change must still be reported.
    (repository / "tracked.txt").write_text("different bytes\n")
    changed = runtime._git_repository_state()
    assert changed.tracked_dirty or changed.status


def test_release_seal_preserves_executability_so_the_worktree_stays_clean() -> None:
    """Sealing must remove write access without rewriting tracked file modes.

    Git records the owner execute bit. Sealing every file to 0444 turned tracked
    100755 blobs into 100644, so the installed superproject reported three
    modified .sh files and the upstream/teastore submodule pointer reported
    -dirty. Readiness verifies the Git binding and requires a clean worktree, so
    setup and readiness could not both succeed against the same tree.
    """

    # An executable file stays executable, and loses every write bit.
    for mode in (0o755, 0o775, 0o700, 0o555):
        sealed = installer._sealed_file_mode(mode)
        assert sealed == 0o555
        assert sealed & 0o111, "git would see 100755 become 100644"
        assert not sealed & 0o222

    # A non-executable file stays non-executable, and loses every write bit.
    for mode in (0o644, 0o664, 0o600, 0o444):
        sealed = installer._sealed_file_mode(mode)
        assert sealed == 0o444
        assert not sealed & 0o111
        assert not sealed & 0o222


def test_runtime_package_lease_field_name_does_not_drift() -> None:
    """The package spells it outerLeasePath; only receipts say exclusiveLeasePath.

    build_runtime_package emits outerLeasePath and the remote controller reads
    package["outerLeasePath"], but launch_campaign read the receipt spelling out
    of the package. That comparison was always None != str(LEASE_PATH), so every
    launch was refused with "runtime package release, output, or identity
    differs" -- and the two names meet only during a real remote launch.
    """

    import ast

    source = (
        ROOT / "modules/teastore/execution/candidate_release_installer.py"
    ).read_text()
    tree = ast.parse(source)
    launch = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "launch_campaign"
    )
    body = ast.get_source_segment(source, launch) or ""
    assert 'package.get("outerLeasePath")' in body
    assert 'package.get("exclusiveLeasePath")' not in body

    # The producer must still emit the name the consumer now reads.
    transport_source = (
        ROOT / "modules/teastore/execution/candidate_transport.py"
    ).read_text()
    assert '"outerLeasePath": authorization["exclusiveLeasePath"]' in transport_source


def test_capture_spec_producer_is_accepted_by_the_installed_reader(
    tmp_path: Path, bindings,
) -> None:
    """The transport builds the readiness ingress; the installer reads it.

    They meet only on the wire during a real remote admission. The previous
    builder emitted a capture/ evidence tree, which the installed reader
    forbids outright, so the readiness path could never have completed -- and
    no test caught it because the admission test passed opaque bytes instead
    of the builder's actual output.
    """

    release_binding = {"setupId": "1" * 32, "frameworkCommit": bindings.framework_commit}
    archive = tmp_path / "capture-spec.tar"
    archive_sha = transport.build_capture_spec(
        bindings, release_binding, archive_path=archive,
    )
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == archive_sha

    # The real consumer must accept it and return the single member's bytes.
    spec_bytes = installer._read_capture_spec(payload)
    spec = json.loads(spec_bytes)
    assert set(spec) == {
        "schemaVersion", "kind", "seams", "descriptorCanonicalSha256",
        "compiledPlanCanonicalSha256", "releaseBindingSha256",
    }
    assert spec["schemaVersion"] == 1
    assert spec["kind"] == "teastore-candidate-readiness-capture-spec-v2"
    assert spec["seams"] == list(runtime.READINESS_SEAMS)
    assert spec["descriptorCanonicalSha256"] == bindings.descriptor_sha256
    assert spec["compiledPlanCanonicalSha256"] == bindings.plan_sha256
    assert spec["releaseBindingSha256"] == runtime.canonical_sha256(release_binding)


def test_staged_context_validator_does_not_derive_paths_from_its_own_location() -> None:
    """install_release runs from /root/...installer.pending, not the checkout.

    Path(__file__).resolve().parents[3] is the release root only for the
    installed copy. From the root staging path it raises IndexError, so any
    helper install_release calls must take its root as an argument instead.
    """

    import ast

    source = (
        ROOT / "modules/teastore/execution/candidate_release_installer.py"
    ).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_validate_image_build_receipt"
        ):
            # Inspect the parsed body, not the text: a comment naming
            # __file__ is documentation, a Name node is the defect.
            assert not [
                child for child in ast.walk(node)
                if isinstance(child, ast.Name) and child.id == "__file__"
            ]
            assert any(
                isinstance(child, ast.arg) and child.arg == "release_root"
                for child in ast.walk(node)
            )
            break
    else:  # pragma: no cover - the function must exist
        raise AssertionError("_validate_image_build_receipt not found")


def test_release_bundle_byte_mismatch_stops_before_any_remote_write(
    tmp_path: Path, bindings,
) -> None:
    paths, _ = _setup_input_files(tmp_path, bindings)
    paths["bundle"].write_bytes(paths["bundle"].read_bytes() + b"planted")
    calls = []
    controller = transport.BoundedSrv5SetupController(
        bindings=bindings,
        runner=lambda argv, data: calls.append((argv, data)),
        clock=lambda: NOW,
    )
    with pytest.raises(transport.TransportError, match="bundle bytes differ"):
        controller.setup(
            gate_plan_path=paths["gate_plan"],
            target_proof_path=paths["target_proof"],
            release_manifest_path=paths["release_manifest"],
            gate_setup_path=paths["gate_setup"], bundle_path=paths["bundle"],
        )
    assert calls == []


def test_release_manifest_commit_mismatch_is_rejected(bindings) -> None:
    _, _, release, _, _, _ = _setup_documents(bindings)
    release["frameworkCommit"] = "0" * 40
    with pytest.raises(runtime.GateError, match="release manifest identity"):
        runtime.validate_release_manifest(release, bindings)


def test_target_image_build_receipt_watches_substituted_image_id(bindings) -> None:
    images = _images()
    receipt = _image_build_receipt(
        bindings, setup_id="1" * 32, images=images,
    )
    assert runtime.validate_image_build_receipt(
        receipt, setup_id="1" * 32, framework_commit=bindings.framework_commit,
    )["imageDigests"] == images
    assert installer._validate_image_build_receipt(
        receipt, setup_id="1" * 32, framework_commit=bindings.framework_commit,
        release_root=ROOT,
    )["imageDigests"] == images
    defect = copy.deepcopy(receipt)
    defect["services"]["auth"]["imageConfigId"] = "sha256:" + "0" * 64
    with pytest.raises(runtime.GateError, match="service identity differs: auth"):
        runtime.validate_image_build_receipt(
            defect, setup_id="1" * 32,
            framework_commit=bindings.framework_commit,
        )
    with pytest.raises(installer.InstallError, match="service identity differs: auth"):
        installer._validate_image_build_receipt(
            defect, setup_id="1" * 32,
            framework_commit=bindings.framework_commit, release_root=ROOT,
        )


def test_readiness_watches_image_map_substituted_after_target_build(
    tmp_path: Path, bindings,
) -> None:
    readiness = _semantic_readiness(tmp_path, bindings)
    readiness["imageDigests"]["auth"] = (
        "observability-placement/teastore-auth-witness@sha256:" + "0" * 64
    )
    with pytest.raises(runtime.GateError, match="target build inspection"):
        runtime.validate_readiness(readiness, bindings, readiness_parent=tmp_path)


def test_readiness_ingress_rejects_completely_fabricated_legacy_archive(tmp_path):
    archive_path = tmp_path / "legacy.tar"
    fabricated = json.dumps({
        "runtimeReady": True,
        "rawObservations": {"everything": "pass"},
        "nestedSeal": {"sha256": "0" * 64},
    }).encode()
    with tarfile.open(archive_path, "w") as archive:
        for name in ("capture/readiness.json", "capture/nested-seal.json"):
            member = tarfile.TarInfo(name)
            member.size = len(fabricated)
            archive.addfile(member, io.BytesIO(fabricated))
    with pytest.raises(installer.InstallError, match="caller-authored observations"):
        installer._read_capture_spec(archive_path.read_bytes())


@pytest.mark.parametrize("layer", ("artifact", "manifest-bytes", "tree-digest", "entry-shape"))
def test_readiness_enclosing_digests_watch_every_nesting_layer(
    tmp_path: Path, bindings, layer: str,
) -> None:
    readiness = _semantic_readiness(tmp_path, bindings)
    manifest_path = tmp_path / readiness["captureManifestPath"]
    manifest = json.loads(manifest_path.read_text())
    if layer == "artifact":
        target = tmp_path / readiness["artifactRoot"] / manifest["entries"][0]["path"]
        target.write_bytes(target.read_bytes() + b"planted")
    elif layer == "manifest-bytes":
        manifest["entriesCanonicalSha256"] = "0" * 64
        _write(manifest_path, manifest)
    elif layer == "tree-digest":
        readiness["captureTreeSha256"] = "0" * 64
    else:
        manifest["entries"][0]["bytes"] += 1
        manifest["entriesCanonicalSha256"] = runtime.canonical_sha256(manifest["entries"])
        payload = _write(manifest_path, manifest)
        readiness["captureManifestSha256"] = hashlib.sha256(payload).hexdigest()
        readiness["captureTreeSha256"] = runtime.canonical_sha256(manifest)
    with pytest.raises(runtime.GateError, match="capture"):
        runtime.validate_readiness(readiness, bindings, readiness_parent=tmp_path)


def test_readiness_rejects_ingress_and_generated_tree_digest_alias(
    tmp_path: Path, bindings,
) -> None:
    readiness = _semantic_readiness(tmp_path, bindings)
    readiness["ingressArchiveSha256"] = readiness["captureTreeSha256"]
    with pytest.raises(runtime.GateError, match="ingress archive and capture tree"):
        runtime.validate_readiness(readiness, bindings, readiness_parent=tmp_path)


def test_probe_rejects_empty_image_population_before_any_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        readiness_checker.subprocess, "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with pytest.raises(readiness_checker.ReadinessError, match="image context"):
        readiness_checker.probe(
            "candidate-terminal-validation",
            {
                "frameworkCommit": FRAMEWORK_COMMIT,
                "descriptorCanonicalSha256": "1" * 64,
                "compiledPlanCanonicalSha256": "2" * 64,
                "imageDigests": {},
            },
        )
    assert calls == []


@pytest.mark.parametrize(
    "seam",
    (
        "patched-sut-images",
        "application-witness-finalization",
        "parameter-logging-disabled",
        "native-token-correlation",
        "cross-message-parent-and-service-attribution",
        "none-selected-full-materialization",
        "candidate-cell-validation",
        "candidate-terminal-validation",
        "bounded-transport",
        "outer-lease-deadline-and-cleanup",
    ),
)
def test_operational_readiness_probes_derive_installed_results(
    bindings, monkeypatch: pytest.MonkeyPatch, seam: str,
) -> None:
    images = _images()

    def run(argv, **_kwargs):
        if argv[:4] == ["git", "-C", str(ROOT), "rev-parse"]:
            return subprocess.CompletedProcess(argv, 0, (FRAMEWORK_COMMIT + "\n").encode(), b"")
        if argv[:3] == ["docker", "image", "inspect"]:
            # Model what a real daemon can actually resolve. Docker cannot look
            # up "repository@<config id>": that form is a repo digest, which
            # locally built images do not have at all. Only the bare config ID
            # resolves, and it reports the repositories it is tagged under.
            reference = argv[-1]
            assert "@" not in reference, (
                f"docker cannot resolve a repo-digest reference: {reference}"
            )
            repository = {
                value.partition("@")[2]: value.partition("@")[0]
                for value in images.values()
            }.get(reference)
            tags = json.dumps([f"{repository}:latest"] if repository else [])
            return subprocess.CompletedProcess(
                argv, 0, f"{reference}\t{tags}\n".encode(), b"",
            )
        if any(str(item).endswith("patched_images.py") for item in argv):
            return subprocess.CompletedProcess(argv, 0, json.dumps({
                "outcome": "pass", "platform": "linux/amd64",
                "services": ["auth", "persistence", "webui"],
                "runtimeReady": False,
            }).encode(), b"")
        if any(str(item).endswith("kieker_native.py") for item in argv):
            return subprocess.CompletedProcess(argv, 0, (
                b"SELF-CHECK PASSED: 4/4 records, eoi/ess parent tree correct, "
                b"field round-trip exact, unified schema valid (real trace ids), "
                b"malformed frames handled.\n"
            ), b"")
        return subprocess.CompletedProcess(argv, 0, b"{}\n", b"")

    monkeypatch.setattr(readiness_checker.subprocess, "run", run)
    result = readiness_checker.probe(
        seam,
        {
            "frameworkCommit": FRAMEWORK_COMMIT,
            "descriptorCanonicalSha256": bindings.descriptor_sha256,
            "compiledPlanCanonicalSha256": bindings.plan_sha256,
            "imageDigests": images,
        },
    )
    assert result["facts"] == readiness_checker.SEAM_EXPECTED_VALUES[seam]


@pytest.mark.parametrize("plant", ("validator-escape", "shell-call"))
def test_operational_readiness_probes_watch_real_checker_defects(
    bindings, monkeypatch: pytest.MonkeyPatch, plant: str,
) -> None:
    images = _images()

    def run(argv, **_kwargs):
        if argv[:4] == ["git", "-C", str(ROOT), "rev-parse"]:
            return subprocess.CompletedProcess(argv, 0, (FRAMEWORK_COMMIT + "\n").encode(), b"")
        if argv[:3] == ["docker", "image", "inspect"]:
            # Model what a real daemon can actually resolve. Docker cannot look
            # up "repository@<config id>": that form is a repo digest, which
            # locally built images do not have at all. Only the bare config ID
            # resolves, and it reports the repositories it is tagged under.
            reference = argv[-1]
            assert "@" not in reference, (
                f"docker cannot resolve a repo-digest reference: {reference}"
            )
            repository = {
                value.partition("@")[2]: value.partition("@")[0]
                for value in images.values()
            }.get(reference)
            tags = json.dumps([f"{repository}:latest"] if repository else [])
            return subprocess.CompletedProcess(
                argv, 0, f"{reference}\t{tags}\n".encode(), b"",
            )
        return subprocess.CompletedProcess(argv, 0, b"{}\n", b"")

    monkeypatch.setattr(readiness_checker.subprocess, "run", run)
    seam = "candidate-cell-validation"
    if plant == "validator-escape":
        monkeypatch.setattr(readiness_checker, "_validator_rejects_empty", lambda *_: False)
    else:
        seam = "bounded-transport"
        monkeypatch.setattr(readiness_checker, "_subprocess_calls_are_argv_only", lambda *_: False)
    with pytest.raises(readiness_checker.ReadinessError, match="operational probe blocked"):
        readiness_checker.probe(
            seam,
            {
                "frameworkCommit": FRAMEWORK_COMMIT,
                "descriptorCanonicalSha256": bindings.descriptor_sha256,
                "compiledPlanCanonicalSha256": bindings.plan_sha256,
                "imageDigests": images,
            },
        )


def test_patched_image_probe_watches_malformed_report() -> None:
    with pytest.raises(readiness_checker.ReadinessError, match="invalid JSON"):
        readiness_checker._patched_image_facts(b"{not-json")


def test_witness_probe_watches_patch_digest_mismatch() -> None:
    manifest_path = ROOT / "modules/teastore/witness/patch-manifest-v3.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["patch"]["sha256"] = "0" * 64
    facts = readiness_checker._witness_facts(
        ROOT, json.dumps(manifest).encode(),
    )
    with pytest.raises(readiness_checker.ReadinessError, match="operational probe blocked"):
        readiness_checker._enforce_expected_facts(
            "application-witness-finalization", facts,
        )


def test_parameter_probe_watches_log_parameters_injection() -> None:
    compose = (
        ROOT / "modules/teastore/deployment/compose/docker-compose_kieker.yaml"
    ).read_bytes() + b"\n# planted\nLOG_PARAMETERS: true\n"
    facts = readiness_checker._parameter_contract_facts(compose)
    with pytest.raises(readiness_checker.ReadinessError, match="operational probe blocked"):
        readiness_checker._enforce_expected_facts("parameter-logging-disabled", facts)


def test_correlation_probe_watches_missing_validation_entry_point() -> None:
    payload = (
        ROOT / "modules/teastore/validation/native_token_correlation.py"
    ).read_bytes().replace(b"def validate_retained", b"def planted_removed_entry")
    facts = readiness_checker._correlation_facts(payload)
    with pytest.raises(readiness_checker.ReadinessError, match="operational probe blocked"):
        readiness_checker._enforce_expected_facts("native-token-correlation", facts)


def test_cross_message_probe_watches_malformed_self_check_stdout() -> None:
    facts = readiness_checker._cross_message_facts(b"SELF-CHECK PASSED\n")
    with pytest.raises(readiness_checker.ReadinessError, match="operational probe blocked"):
        readiness_checker._enforce_expected_facts(
            "cross-message-parent-and-service-attribution", facts,
        )


def test_target_identity_distinguishes_short_hostname_from_resolved_fqdn(bindings):
    _, proof, _, _, _, _ = _setup_documents(bindings)
    assert runtime.validate_target_proof(proof, bindings)
    short_as_fqdn = copy.deepcopy(proof)
    short_as_fqdn["hostIdentity"]["fqdn"] = runtime.TARGET
    with pytest.raises(runtime.GateError, match="host identity"):
        runtime.validate_target_proof(short_as_fqdn, bindings)
    fqdn_as_short = copy.deepcopy(proof)
    fqdn_as_short["hostIdentity"]["hostname"] = runtime.TARGET_HOSTNAME
    with pytest.raises(runtime.GateError, match="host identity"):
        runtime.validate_target_proof(fqdn_as_short, bindings)


@pytest.mark.parametrize("receipt_plant", (None, "legacy-field", "tree-alias"))
def test_installed_readiness_admission_is_remote_then_locally_replayed(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch,
    receipt_plant: str | None,
) -> None:
    admitted = _package(tmp_path / "admission", bindings)
    release = admitted.readiness["release"]
    archive = tmp_path / "readiness.tar"
    archive.write_bytes(b"sealed-readiness-capture")
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    release_sha = runtime.canonical_sha256(release)
    readiness_sha = "9" * 64
    preflight = admitted.readiness["runtimePreflight"]
    remote_root = (
        "/var/lib/observability-placement/candidate-v4/teastore/readiness/"
        f"{release['setupId']}/{archive_sha[:16]}"
    )
    receipt = {
        "schemaVersion": 1,
        "kind": "teastore-candidate-installed-readiness-v1",
        "setupId": release["setupId"],
        "frameworkCommit": bindings.framework_commit,
        "releaseBindingSha256": release_sha,
        "ingressArchiveSha256": archive_sha,
        "captureTreeSha256": admitted.readiness["captureTreeSha256"],
        "readinessCanonicalSha256": readiness_sha,
        "runtimePreflightSha256": runtime.canonical_sha256(preflight),
        "runtimePreflightCapturedAt": preflight["capturedAt"],
        "readinessRoot": remote_root,
        "validatedAt": NOW.isoformat(),
        "experimentalCellsExecuted": 0,
        "runtimeReady": True,
        "promotionAuthorized": False,
    }
    if receipt_plant == "legacy-field":
        receipt["archiveSha256"] = receipt.pop("ingressArchiveSha256")
    elif receipt_plant == "tree-alias":
        receipt["captureTreeSha256"] = archive_sha
    calls: list[tuple[str, ...]] = []

    def runner(argv, data):
        calls.append(tuple(argv))
        if argv[0] == "ssh":
            assert "admit-readiness" in argv
            assert data == archive.read_bytes()
            return transport.CommandResult(0, json.dumps(receipt).encode(), b"")
        pending = Path(argv[-1])
        pending.mkdir()
        _write(pending / "readiness-admission.json", receipt)
        _write(pending / "readiness.json", {
            "fixture": True, "runtimePreflight": preflight,
            "ingressArchiveSha256": archive_sha,
            "captureTreeSha256": admitted.readiness["captureTreeSha256"],
        })
        return transport.CommandResult(0, b"", b"")

    class Adapter:
        @staticmethod
        def validate_readiness(document, observed, *, readiness_parent):
            assert document == {
                "fixture": True, "runtimePreflight": preflight,
                "ingressArchiveSha256": archive_sha,
                "captureTreeSha256": admitted.readiness["captureTreeSha256"],
            }
            assert observed is bindings
            assert readiness_parent.name == "fetched-readiness"
            return readiness_sha

    monkeypatch.setattr(transport, "_adapter_module", lambda: Adapter)
    controller = transport.BoundedSrv5SetupController(
        bindings=bindings, runner=runner, clock=lambda: NOW,
    )
    if receipt_plant is not None:
        with pytest.raises(transport.TransportError, match="readiness receipt differs"):
            controller.admit_readiness(
                archive_path=archive, release_binding=release,
                local_output=tmp_path / "fetched-readiness",
            )
        assert [call[0] for call in calls] == ["ssh"]
        return
    assert controller.admit_readiness(
        archive_path=archive, release_binding=release,
        local_output=tmp_path / "fetched-readiness",
    ) == receipt
    assert [call[0] for call in calls] == ["ssh", "scp"]


def _frozen_clock(moment: datetime):
    """A ``datetime`` whose ``now()`` is ``moment``, for real-clock authority checks."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment if tz is None else moment.astimezone(tz)

    return Frozen


def _local_admission_fixture(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch, plant: str,
) -> tuple[Path, str, BaseException]:
    _, _, _, gate_setup, install, release = _setup_documents(bindings)
    archive_payload = b"identity-only-capture-spec"
    archive_sha = hashlib.sha256(archive_payload).hexdigest()
    namespace = tmp_path / "root-control"
    namespace.mkdir(mode=0o700)
    # admit_readiness_capture compares the retained GATE-SETUP deadline against
    # the real clock, and this fixture's authorization expires at
    # NOW + 10h == 2026-08-30T12:00Z. Without pinning the installer's clock to
    # the fixture's own NOW, every plant below stopped being reached after that
    # instant and the whole parametrisation failed on an expired authorization
    # instead of on its planted defect. The `expired-authorization` plant is the
    # deliberate opposite and moves the clock past the deadline.
    moment = NOW + timedelta(hours=11) if plant == "expired-authorization" else NOW
    monkeypatch.setattr(installer, "datetime", _frozen_clock(moment))
    monkeypatch.setattr(installer, "_require_root_transport", lambda: None)
    monkeypatch.setattr(installer, "_read_capture_spec", lambda _payload: b"{}")
    monkeypatch.setattr(installer, "_root_readiness_namespace", lambda _setup: namespace)
    monkeypatch.setattr(installer.os, "chown", lambda *_args: None)
    monkeypatch.setattr(installer.os, "chmod", lambda *_args: None)
    monkeypatch.setattr(installer.os, "fchown", lambda *_args: None)
    original_json_file = installer._json_file

    def json_file(path, where):
        if where == "release install":
            return copy.deepcopy(install), b"install"
        if where == "retained GATE-SETUP":
            return copy.deepcopy(gate_setup), b"setup"
        return original_json_file(path, where)

    monkeypatch.setattr(installer, "_json_file", json_file)
    preflight = {
        "capturedAt": NOW.isoformat(), "ready": True,
        "experimentalCellsExecuted": 0,
    }
    monkeypatch.setattr(installer, "runtime_preflight", lambda: copy.deepcopy(preflight))

    def generate(**kwargs):
        if plant == "probe-failure":
            raise installer.InstallError("planted operational probe failure")
        pending = kwargs["pending"]
        (pending / "artifacts/campaign").mkdir(parents=True)
        readiness = {
            "ingressArchiveSha256": archive_sha,
            "captureTreeSha256": "7" * 64,
        }
        _write(pending / "readiness.json", readiness)
        return readiness

    monkeypatch.setattr(installer, "_generate_installed_readiness", generate)

    class Adapter:
        @staticmethod
        def inspect_campaign(_root, _commit):
            return bindings

        @staticmethod
        def validate_readiness(_document, _bindings, *, readiness_parent):
            assert readiness_parent.name.startswith(".pending-")
            if plant == "reseal-failure":
                raise installer.InstallError("planted reseal failure")
            return "9" * 64

    monkeypatch.setattr(installer, "_installed_adapter", lambda: Adapter)
    namespace_identity = (namespace.lstat().st_dev, namespace.lstat().st_ino)
    assertion_calls = 0

    def assert_namespace(_path, identity):
        nonlocal assertion_calls
        assertion_calls += 1
        assert identity == namespace_identity
        if plant in {"ancestor-replacement", "inode-drift"}:
            raise installer.InstallError(f"planted {plant}")

    monkeypatch.setattr(installer, "_assert_root_namespace", assert_namespace)
    pending = namespace / f".pending-{archive_sha[:16]}"
    final = namespace / archive_sha[:16]
    abort = namespace / f"abort-{archive_sha[:16]}.json"
    if plant == "pending-collision":
        pending.mkdir()
    elif plant == "final-collision":
        final.mkdir()
    elif plant == "precreated-abort":
        _write(abort, {
            "schemaVersion": 1,
            "kind": "teastore-candidate-readiness-capture-abort-v2",
            "setupId": install["setupId"], "frameworkCommit": FRAMEWORK_COMMIT,
            "ingressArchiveSha256": archive_sha, "captureTreeSha256": None,
            "runtimeReady": False, "experimentalCellsExecuted": 0,
            "experimentalState": "ABSTAINED", "errorType": "PriorFailure",
            "error": "retained", "recordedAt": NOW.isoformat(),
            "promotionAuthorized": False,
        })
    if plant == "mkdir-failure":
        original_mkdir = Path.mkdir

        def mkdir(path, *args, **kwargs):
            if path == pending:
                raise OSError("planted mkdir failure")
            return original_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", mkdir)
    elif plant == "chown-failure":
        monkeypatch.setattr(installer.os, "chown", lambda *_: (_ for _ in ()).throw(OSError("planted chown failure")))
    elif plant == "file-fsync-failure":
        original_fsync = installer.os.fsync
        failed = False

        def fsync(descriptor):
            nonlocal failed
            if not failed:
                failed = True
                raise OSError("planted file fsync failure")
            return original_fsync(descriptor)

        monkeypatch.setattr(installer.os, "fsync", fsync)
    elif plant == "directory-fsync-failure":
        original_fsync = installer._fsync_directory
        failed = False

        def fsync(path):
            nonlocal failed
            if path == pending and not failed:
                failed = True
                raise OSError("planted directory fsync failure")
            return original_fsync(path)

        monkeypatch.setattr(installer, "_fsync_directory", fsync)
    with pytest.raises(Exception) as raised:
        installer.admit_readiness_capture(
            archive_payload=archive_payload, expected_archive_sha256=archive_sha,
            setup_id=install["setupId"], framework_commit=FRAMEWORK_COMMIT,
            release_binding_sha256=runtime.canonical_sha256(release),
        )
    return namespace, archive_sha, raised.value


# Plants that fail before the publication transaction opens, so no abort document
# is owed: the namespace identity is already wrong, or the authority has expired.
_NO_ABORT_PLANTS = frozenset({
    "ancestor-replacement", "inode-drift", "expired-authorization",
})


@pytest.mark.parametrize(
    "plant",
    (
        "ancestor-replacement", "inode-drift", "pending-collision",
        "final-collision", "precreated-abort", "mkdir-failure", "chown-failure",
        "probe-failure", "reseal-failure", "file-fsync-failure",
        "directory-fsync-failure", "expired-authorization",
    ),
)
def test_readiness_publication_watches_transaction_and_namespace_defects(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch, plant: str,
) -> None:
    namespace, archive_sha, error = _local_admission_fixture(
        tmp_path, bindings, monkeypatch, plant,
    )
    abort = namespace / f"abort-{archive_sha[:16]}.json"
    if plant == "expired-authorization":
        assert isinstance(error, installer.InstallError)
        assert "outside the exact installed setup authority" in str(error)
    if plant in _NO_ABORT_PLANTS:
        assert not abort.exists()
        assert not (namespace / archive_sha[:16]).exists()
    else:
        retained = json.loads(abort.read_text())
        assert retained["experimentalState"] == "ABSTAINED"
        assert retained["runtimeReady"] is False
        assert retained["experimentalCellsExecuted"] == 0
        assert retained["promotionAuthorized"] is False
        assert retained["recordedAt"] == NOW.isoformat()


def test_runtime_package_consumes_all_27_contracts_without_reordering(
    tmp_path: Path, bindings,
) -> None:
    package = _package(tmp_path, bindings)
    document = transport.build_runtime_package(package)
    replayed = transport.validate_runtime_package(document)
    assert [cell["runId"] for cell in replayed["cells"]] == list(bindings.run_ids)
    assert [cell["ordinalPosition"] for cell in replayed["cells"]] == [
        cell["ordinalPosition"] for cell in bindings.cells
    ]
    assert replayed["promotionAuthorized"] is False


@pytest.mark.parametrize(
    "plant",
    (
        "reorder", "retry", "bool-run-count", "campaign-bytes", "campaign-contract",
        "gate-run", "timestamps",
    ),
)
def test_runtime_package_planted_defects_fail_before_transport(
    tmp_path: Path, bindings, plant: str,
) -> None:
    package = _package(tmp_path, bindings)
    document = transport.build_runtime_package(package)
    if plant == "reorder":
        document["cells"][:2] = reversed(document["cells"][:2])
    elif plant == "retry":
        document["retryAllowed"] = True
    elif plant == "bool-run-count":
        document["runCount"] = True
    elif plant == "campaign-bytes":
        raw = bytearray(base64.b64decode(document["campaignManifestBase64"]))
        raw[-2] ^= 1
        document["campaignManifestBase64"] = base64.b64encode(raw).decode()
    elif plant == "campaign-contract":
        campaign = json.loads(base64.b64decode(document["campaignManifestBase64"]))
        campaign["maximumEvidenceLabel"] = "canonical-evidence"
        payload = (json.dumps(campaign, indent=2, sort_keys=True) + "\n").encode()
        document["campaignManifestBase64"] = base64.b64encode(payload).decode()
        document["campaignSha256"] = hashlib.sha256(payload).hexdigest()
        for cell in document["cells"]:
            cell["campaignSha256"] = document["campaignSha256"]
    elif plant == "gate-run":
        document["cells"][0]["gateRunSha256"] = "0" * 64
    elif plant == "timestamps":
        document["notBefore"] = "2026-08-30T01:00:00"
    with pytest.raises(transport.TransportError):
        transport.validate_runtime_package(document)


def test_bounded_transport_rechecks_full_window_before_first_remote_write(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = _package(tmp_path / "admission", bindings)
    document = transport.build_runtime_package(admitted)
    package_path = tmp_path / "runtime-package.json"
    payload = _write(package_path, document)
    calls: list[tuple[str, ...]] = []

    def runner(argv, _data):
        calls.append(tuple(argv))
        if argv[0] == "scp":
            Path(argv[-1]).mkdir()
            return transport.CommandResult(0, b"", b"")
        if "campaign-status" in argv:
            status = {
                "schemaVersion": 1,
                "kind": "teastore-candidate-remote-status-v1",
                "setupId": document["setupId"],
                "campaignId": document["campaignId"],
                "packageSha256": hashlib.sha256(payload).hexdigest(),
                "state": "complete", "leaseHeld": False,
                "hostLeaseHeld": False,
                "resultExists": True, "journalRows": 27,
                "terminalExists": True, "abortExists": False,
                "systemdState": _systemd_status(
                    document["campaignId"], document["setupId"],
                    hashlib.sha256(payload).hexdigest(), running=False,
                ),
                "leaseReceiptSha256": "8" * 64,
                "promotionAuthorized": False,
            }
            return transport.CommandResult(0, json.dumps(status).encode(), b"")
        receipt = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-remote-launch-v1",
            "campaignId": document["campaignId"],
            "frameworkCommit": bindings.framework_commit,
            "packageSha256": hashlib.sha256(payload).hexdigest(),
            "runCount": 27,
            "state": "complete",
            "promotionAuthorized": False,
        }
        return transport.CommandResult(0, json.dumps(receipt).encode(), b"")

    monkeypatch.setattr(
        transport, "replay_fetched_campaign",
        lambda _root, _package: {"verdict": "pass", "runCount": 27},
    )
    controller = transport.BoundedSrv5CampaignController(
        framework_commit=bindings.framework_commit,
        release_binding=admitted.readiness["release"],
        runner=runner,
        clock=lambda: NOW,
    )
    assert controller.launch(package_path, local_output=tmp_path / "fetched")["state"] == "complete"
    assert [call[0] for call in calls] == ["ssh", "ssh", "scp"]

    calls.clear()
    expired = transport.BoundedSrv5CampaignController(
        framework_commit=bindings.framework_commit,
        release_binding=admitted.readiness["release"],
        runner=runner,
        clock=lambda: NOW + timedelta(hours=1, minutes=1),
    )
    with pytest.raises(transport.TransportError, match="before transfer"):
        expired.launch(package_path, local_output=tmp_path / "expired")
    assert calls == []


def test_disconnect_reports_running_then_refetches_without_second_launch(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = _package(tmp_path / "admission", bindings)
    document = transport.build_runtime_package(admitted)
    package_path = tmp_path / "runtime-package.json"
    payload = _write(package_path, document)
    package_sha = hashlib.sha256(payload).hexdigest()
    state = {"value": "running"}
    calls: list[tuple[str, ...]] = []

    def runner(argv, _data):
        calls.append(tuple(argv))
        if argv[0] == "scp":
            Path(argv[-1]).mkdir()
            return transport.CommandResult(0, b"", b"")
        if "campaign-status" in argv:
            complete = state["value"] == "complete"
            status = {
                "schemaVersion": 1,
                "kind": "teastore-candidate-remote-status-v1",
                "setupId": document["setupId"], "campaignId": document["campaignId"],
                "packageSha256": package_sha, "state": state["value"],
                "leaseHeld": not complete, "resultExists": True,
                "hostLeaseHeld": not complete,
                "journalRows": 27 if complete else 4,
                "terminalExists": complete, "abortExists": False,
                "systemdState": _systemd_status(
                    document["campaignId"], document["setupId"], package_sha,
                    running=not complete,
                ),
                "leaseReceiptSha256": "8" * 64,
                "promotionAuthorized": False,
            }
            return transport.CommandResult(0, json.dumps(status).encode(), b"")
        assert "launch-campaign" in argv
        return transport.CommandResult(255, b"", b"connection lost")

    monkeypatch.setattr(
        transport, "replay_fetched_campaign",
        lambda _root, _package: {"verdict": "pass", "runCount": 27},
    )
    controller = transport.BoundedSrv5CampaignController(
        framework_commit=bindings.framework_commit,
        release_binding=admitted.readiness["release"], runner=runner,
        clock=lambda: NOW,
    )
    with pytest.raises(transport.TransportError, match="still running"):
        controller.launch(package_path, local_output=tmp_path / "too-early")
    assert [call for call in calls if "launch-campaign" in call]
    assert not [call for call in calls if call[0] == "scp"]
    state["value"] = "complete"
    replay = controller.refetch(package_path, local_output=tmp_path / "recovered")
    assert replay["status"]["state"] == "complete"
    assert replay["localReplay"]["verdict"] == "pass"
    assert len([call for call in calls if "launch-campaign" in call]) == 1


def test_target_launch_is_detached_before_ssh_returns() -> None:
    package = {
        "campaignId": "candidate-001",
        "setupId": "a" * 32,
        "releaseRoot": "/home/stig/release",
        "packagePath": "/home/stig/results/.packages/candidate-001.json",
        "authorizationDeadline": (NOW + timedelta(hours=1)).isoformat(),
    }
    command, unit = installer._detached_controller_command(
        package,
        controller=Path("/home/stig/release/modules/teastore/execution/candidate_remote_controller.py"),
        output=Path("/home/stig/results/candidate-001"),
        framework_commit=FRAMEWORK_COMMIT,
        package_sha256="c" * 64,
        log_path=Path("/home/stig/results/.controller-logs/candidate-001.log"),
    )
    assert command[0] == installer.SYSTEMD_RUN
    assert "--collect" not in command
    assert "--property=Type=exec" in command
    assert "--property=KillMode=control-group" in command
    assert any(item.startswith("--property=RuntimeMaxSec=") for item in command)
    assert any(item.startswith("--property=StandardOutput=append:") for item in command)
    separator = command.index("--")
    assert command[separator + 1 : separator + 5] == [
        installer.TARGET_PYTHON, "-I",
        "/home/stig/release/modules/teastore/execution/candidate_release_installer.py",
        "supervise",
    ]
    assert unit.startswith("teastore-candidate-v4-")
    remote_source = (
        ROOT / "modules/teastore/execution/candidate_remote_controller.py"
    ).read_text(encoding="utf-8")
    assert "signal.signal(signal.SIGHUP, signal.SIG_IGN)" in remote_source


def test_supervisor_watches_controller_handoff_failure_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "release"
    controller = release / installer.REMOTE_CONTROLLER
    controller.parent.mkdir(parents=True)
    controller.write_text("# planted controller\n")
    results = tmp_path / "results"
    packages = results / ".packages"
    packages.mkdir(parents=True)
    output = results / "candidate-001"
    package = {
        "campaignId": "candidate-001", "setupId": "1" * 32,
        "frameworkCommit": FRAMEWORK_COMMIT,
        "campaignSha256": "a" * 64,
        "releaseRoot": str(release), "resultsRoot": str(results),
    }
    payload = (json.dumps(package, sort_keys=True) + "\n").encode()
    package_path = packages / "candidate-001.json"
    package_path.write_bytes(payload)
    monkeypatch.setattr(installer, "_require_root_transport", lambda: None)
    monkeypatch.setattr(installer.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(
        installer, "_mkdir_checked",
        lambda path, **_kwargs: path.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(
        installer, "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 127, b"", b"plant"),
    )
    with pytest.raises(installer.InstallError, match="controller exited 127"):
        installer.supervise_campaign(
            controller=controller, package_path=package_path, output=output,
            framework_commit=FRAMEWORK_COMMIT,
            package_sha256=hashlib.sha256(payload).hexdigest(),
        )
    abort = json.loads((output / "campaign-abort.json").read_text())
    assert abort["stage"] == "supervisor-controller-handoff"
    assert abort["experimentalState"] == "ABSTAINED"
    terminal = json.loads(
        (results / ".supervisor/candidate-001.json").read_text()
    )
    assert terminal["returnCode"] == 127
    assert terminal["state"] == "abstained"


@pytest.mark.parametrize(
    ("plant", "expected"),
    (
        ("duplicate", "systemd state"),
        ("absent-but-active", "reports live state"),
        ("absent-but-failed", "reports live state"),
        ("non-numeric", "systemd state"),
    ),
)
def test_systemd_status_replay_watches_raw_terminal_defects(
    plant: str, expected: str,
) -> None:
    rows = [
        "LoadState=loaded", "ActiveState=inactive", "SubState=dead",
        "Result=success", "ExecMainStatus=0",
    ]
    if plant == "duplicate":
        rows.append("Result=success")
    elif plant == "absent-but-active":
        rows[0], rows[1], rows[2] = "LoadState=not-found", "ActiveState=active", "SubState=running"
    elif plant == "absent-but-failed":
        rows[0], rows[3], rows[4] = "LoadState=not-found", "Result=exit-code", "ExecMainStatus=2"
    else:
        rows[-1] = "ExecMainStatus=zero"
    with pytest.raises(installer.InstallError, match=expected):
        installer._parse_systemd_state(
            ("\n".join(rows) + "\n").encode(), unit_name="unit",
        )


def test_absent_transient_unit_parses_as_the_never_started_reading() -> None:
    """LoadState=not-found is the honest reading for a staged, unlaunched
    campaign, and campaign-status has to stay answerable there -- it is the
    exact state launch tells the operator to go and inspect."""

    state = installer._parse_systemd_state(
        b"LoadState=not-found\nActiveState=inactive\nSubState=dead\n"
        b"Result=success\nExecMainStatus=0\n",
        unit_name="unit",
    )
    assert state["loadState"] == "not-found"
    assert state["activeState"] == "inactive"


@pytest.mark.parametrize(
    ("report", "expected"),
    (
        ({"jsonschema": None, "pika": None, "yaml": None}, None),
        (
            {"jsonschema": None, "pika": "resolved to an empty namespace package",
             "yaml": None},
            "cannot use required Python modules",
        ),
        (
            {"jsonschema": None, "pika": "import failed: ModuleNotFoundError: pika",
             "yaml": None},
            "cannot use required Python modules",
        ),
        ({"jsonschema": None, "pika": None}, "wrong modules"),
    ),
)
def test_preflight_proves_the_execution_user_can_use_the_runtime_modules(
    monkeypatch: pytest.MonkeyPatch, report: dict, expected: str | None,
) -> None:
    """Every dist-package on this target was installed root-only, and Python
    degrades an unreadable package directory to an empty namespace package --
    so `import pika` succeeded as root-invisible nonsense and only
    pika.ConnectionParameters failed, fifteen minutes into a cell."""

    monkeypatch.setattr(
        installer, "_run_as_execution_user",
        lambda _argv: subprocess.CompletedProcess(
            _argv, 0, json.dumps(report).encode(), b"",
        ),
    )
    # The probe is only worth anything if the preflight actually runs it, and
    # the preflight itself needs a real target to exercise end to end.
    source = (
        ROOT / "modules/teastore/execution/candidate_release_installer.py"
    ).read_text(encoding="utf-8")
    preflight = source.split("def runtime_preflight(")[1].split("\ndef ")[0]
    assert "_prove_execution_user_can_import_runtime_modules()" in preflight

    if expected is None:
        installer._prove_execution_user_can_import_runtime_modules()
        return
    with pytest.raises(installer.InstallError, match=expected):
        installer._prove_execution_user_can_import_runtime_modules()


@pytest.mark.parametrize(
    ("plant", "expected"),
    (
        ("namespace-package", "empty namespace package"),
        ("absent", "import failed"),
    ),
)
def test_the_import_probe_script_itself_detects_an_unreadable_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plant: str, expected: str,
) -> None:
    """Runs the embedded probe for real against a planted namespace package.

    The parametrized test above feeds the installer a canned report, so it only
    exercises the consumer half -- exactly the producer/consumer split that
    produced most of the defects in this ledger. This one executes the probe
    script the target actually runs.
    """

    # A directory with no __init__.py is what an unreadable package looks like
    # to the import system: it resolves, and its __file__ is None. The name has
    # to be one nothing really provides -- a namespace portion loses to a real
    # package found later on sys.path, so shadowing "pika" would prove nothing.
    planted = "teastore_unreadable_package_fixture"
    if plant == "namespace-package":
        (tmp_path / planted).mkdir()
    monkeypatch.setattr(installer, "RUNTIME_PYTHON_MODULES", (planted,))

    def local_runner(argv):
        assert argv[1] == "-I" and argv[2] == "-c"
        return subprocess.run(
            [sys.executable, "-c", argv[3]], cwd=tmp_path,
            capture_output=True,
        )

    monkeypatch.setattr(installer, "_run_as_execution_user", local_runner)
    with pytest.raises(installer.InstallError, match=expected):
        installer._prove_execution_user_can_import_runtime_modules()


def test_cell_failure_detail_keeps_the_end_of_the_diagnosis() -> None:
    """The old [:300] head slice landed inside the docker argv and truncated
    two separate diagnoses before the cause. Tracebacks and blocker lists both
    put the answer last."""

    source = (
        ROOT / "modules/teastore/execution/candidate_remote_controller.py"
    ).read_text(encoding="utf-8")
    assert '[:300]' not in source
    assert 'text[-4000:]' in source


def test_release_binding_key_set_does_not_drift_between_target_and_host() -> None:
    """The binding digest is computed from this key set on both sides. It used
    to be a literal repeated at six sites, so a new field had to be hand-edited
    into all six or the digest silently stopped matching."""

    assert installer.RELEASE_BINDING_KEYS == runtime.RELEASE_BINDING_KEYS
    assert "activationCompile" in installer.RELEASE_BINDING_KEYS


def test_installer_compiles_the_aop_the_selected_posture_bind_mounts(
    tmp_path: Path,
) -> None:
    """compiled-selected.override.yaml binds .local/compiled/teastore/aop.xml
    into five services. It is a build product, so it cannot be in the Git
    bundle the release is built from, and Docker turns a missing bind source
    into a *directory* -- which is why the omission survived GATE-SETUP and
    only surfaced as "not a directory" once the first cell started."""

    release = tmp_path / "release"
    for relative in (
        installer.ACTIVATION_COMPILER, installer.ACTIVATION_CATALOG,
        installer.ACTIVATION_GOAL,
    ):
        destination = release / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())

    produced = installer.compile_activation_artifacts(
        release, uid=os.getuid(), gid=os.getgid(),
    )
    compiled_dir = release / installer.ACTIVATION_OUTPUT_DIR
    # F-ADH-072: all three postures are rendered here, so `full` and `none`
    # stop falling back to the stock in-image aop.xml, whose ~100 exclusions
    # made `full` weave a *different* join-point set than `selected`.
    for posture, (_, manifest_name, aop_name) in installer.ACTIVATION_OUTPUTS.items():
        aop = compiled_dir / aop_name
        manifest = compiled_dir / manifest_name
        assert aop.is_file() and not aop.is_symlink(), aop_name
        assert manifest.is_file() and not manifest.is_symlink(), manifest_name
        entry = produced["postures"][posture]
        assert hashlib.sha256(aop.read_bytes()).hexdigest() == entry["aopSha256"]
        assert hashlib.sha256(manifest.read_bytes()).hexdigest() == entry["manifestSha256"]
    # The rendered postures must nest: `selected`'s groups are a strict subset
    # of `full`'s, and `none` activates nothing at all.
    assert produced["postures"]["none"]["selectedActivationGroups"] == []
    assert set(produced["postures"]["selected"]["selectedActivationGroups"]) < set(
        produced["postures"]["full"]["selectedActivationGroups"]
    )
    # The host validates the target's receipt against its own derivation, so
    # the two computations have to agree exactly.
    assert produced == transport.expected_activation_compile()


def test_every_compose_bind_source_the_selected_posture_needs_is_produced() -> None:
    """Ties the override's host paths to what the installer actually writes.
    Nothing checked this, so the release could be certified without them."""

    overrides = (
        "modules/teastore/deployment/compose/compiled-selected.override.yaml",
        "modules/teastore/deployment/compose/compiled-full.override.yaml",
        "modules/teastore/postures/none.override.yaml",
    )
    produced = {
        f"{installer.ACTIVATION_OUTPUT_DIR}/{name}"
        for _, manifest_name, aop_name in installer.ACTIVATION_OUTPUTS.values()
        for name in (manifest_name, aop_name)
    }
    for relative in overrides:
        override = (ROOT / relative).read_text(encoding="utf-8")
        sources = {
            line.split(":", 1)[0].strip().lstrip("- ")
            for line in override.splitlines() if "/usr/local/tomcat/lib/" in line
        }
        assert sources, f"{relative} no longer declares any bind mount"
        for source in sources:
            # The override is read relative to the compose file, four levels down.
            normalized = source.replace("../../../../", "")
            assert normalized in produced, f"{normalized} is bind-mounted but never built"


def test_transient_unit_name_is_scoped_to_the_attempt_not_the_campaign() -> None:
    """systemd keeps a failed transient unit loaded and `systemd-run --unit=`
    refuses a loaded name, so a name derived from the constant campaignId let
    one failed launch block every later launch of this study permanently.
    --collect is deliberately absent because the terminal unit is evidence
    campaign-status reads, so the name itself has to separate attempts."""

    base = ("teastore-candidate-pilot-v1", "a" * 32, "c" * 64)
    first = installer._campaign_unit_name(*base)
    assert first.startswith("teastore-candidate-v4-")
    assert len(first) == len("teastore-candidate-v4-") + 32
    assert first != installer._campaign_unit_name(base[0], "b" * 32, base[2])
    assert first != installer._campaign_unit_name(base[0], base[1], "d" * 64)
    # The transport validates the name the target reports, so its copy of the
    # derivation must stay byte-identical to the installer's.
    assert transport.campaign_unit_name(*base) == first


def test_successful_detached_start_returns_before_terminal_fetch(
    tmp_path: Path, bindings,
) -> None:
    admitted = _package(tmp_path / "admission", bindings)
    document = transport.build_runtime_package(admitted)
    package_path = tmp_path / "runtime-package.json"
    payload = _write(package_path, document)
    package_sha = hashlib.sha256(payload).hexdigest()
    calls: list[tuple[str, ...]] = []

    def runner(argv, _data):
        calls.append(tuple(argv))
        if "campaign-status" in argv:
            status = {
                "schemaVersion": 1,
                "kind": "teastore-candidate-remote-status-v1",
                "setupId": document["setupId"],
                "campaignId": document["campaignId"],
                "packageSha256": package_sha,
                "state": "running", "leaseHeld": True,
                "hostLeaseHeld": True,
                "resultExists": True, "journalRows": 0,
                "terminalExists": False, "abortExists": False,
                "systemdState": _systemd_status(
                    document["campaignId"], document["setupId"], package_sha,
                    running=True,
                ),
                "leaseReceiptSha256": "8" * 64,
                "promotionAuthorized": False,
            }
            return transport.CommandResult(0, json.dumps(status).encode(), b"")
        start = {
            "schemaVersion": 1,
            "kind": "teastore-candidate-remote-start-v1",
            "campaignId": document["campaignId"],
            "frameworkCommit": bindings.framework_commit,
            "packageSha256": package_sha,
            "unitName": "teastore-candidate-v4-" + "d" * 32,
            "state": "started", "promotionAuthorized": False,
        }
        return transport.CommandResult(0, json.dumps(start).encode(), b"")

    controller = transport.BoundedSrv5CampaignController(
        framework_commit=bindings.framework_commit,
        release_binding=admitted.readiness["release"], runner=runner,
        clock=lambda: NOW,
    )
    receipt = controller.launch(package_path, local_output=tmp_path / "not-fetched")
    assert receipt["state"] == "started"
    assert [call[0] for call in calls] == ["ssh", "ssh"]
    assert not (tmp_path / "not-fetched").exists()


@pytest.mark.parametrize(
    "plant",
    ("workload", "path-truth", "controller-digest", "posture-proof", "bool-window"),
)
def test_cell_producer_watches_nested_contract_drift_before_runtime(
    tmp_path: Path, bindings, plant: str,
) -> None:
    cell = transport.build_runtime_package(_package(tmp_path, bindings))["cells"][0]
    assert performance._validate_candidate_contract(cell) == cell
    defect = copy.deepcopy(cell)
    if plant == "workload":
        defect["workload"]["population"] = "convenient-smaller-population"
    elif plant == "path-truth":
        defect["pathGroundTruth"]["missingState"] = "observed-zero"
    elif plant == "controller-digest":
        defect["runtimeInputs"]["controllerDigests"]["candidate-validator"] = "0" * 64
    elif plant == "posture-proof":
        defect["posture"]["proofRequirements"] = []
    elif plant == "bool-window":
        defect["window"]["resourceProjectionAllowed"] = 1
    with pytest.raises(RuntimeError):
        performance._validate_candidate_contract(defect)


def test_cell_entry_accepts_only_the_frozen_campaign_output_path(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = transport.build_runtime_package(_package(tmp_path / "admission", bindings))[
        "cells"
    ][0]
    contract_path = tmp_path / "contract.json"
    _write(contract_path, contract)
    key = contract["runKey"]
    output = tmp_path / "campaign" / "runs" / key["regime"] / (
        f"b{key['block']:02d}-{contract['ordinalPosition']:02d}-{key['posture']}"
    )
    observed: list[Path] = []

    def producer(value, destination):
        assert value == contract
        observed.append(destination)
        return {"state": "fixture-only"}

    monkeypatch.setattr(cell_entry, "_producer_module", lambda: producer)
    assert cell_entry.execute(contract_path, output) == {"state": "fixture-only"}
    assert observed == [output]
    with pytest.raises(cell_entry.CellExecutionError, match="frozen campaign identity"):
        cell_entry.execute(contract_path, output.with_name("attempt-01"))


def _manifest(root: Path, required: set[str]) -> str:
    rows = []
    for name in sorted(required - {"content-manifest.json"}):
        payload = (root / name).read_bytes()
        rows.append({
            "path": name, "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    payload = _write(root / "content-manifest.json", {
        "schemaVersion": 1, "algorithm": "sha256", "files": rows,
    })
    return hashlib.sha256(payload).hexdigest()


def _terminal_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_key = {
        "studyEpoch": "teastore-candidate-pilot-v1",
        "regime": "no-fault-cost", "block": 1, "posture": "selected", "attempt": 1,
    }
    root = tmp_path / "cell"
    root.mkdir()
    required = terminal._required_for(run_key)
    report = {"verdict": "pass", "runKey": run_key}
    for name in required - {"content-manifest.json"}:
        if name == "candidate-validation.json":
            _write(root / name, report)
        elif name == "receipt.json":
            _write(root / name, {"run": {"runId": "cell-001"}})
        elif name == "cell-cleanup.json":
            _write(root / name, {
                "schemaVersion": 1,
                "kind": "teastore-candidate-cell-cleanup-v1",
                "runId": "cell-001",
                "outerLeaseHeld": True,
                "deadlineControllerSettled": True,
                "ownedResourcesClean": True,
                "safeToContinue": True,
            })
        else:
            (root / name).write_bytes(f"fixture:{name}\n".encode())

    class Validator:
        @staticmethod
        def validate_operational_proofs(_root, posture=None):
            assert posture == "selected"
            return {
                "zeroConsumerPurge": True,
                "emptySingleCollectorBarrier": True,
                "terminalDrain": True,
            }

        @staticmethod
        def validate_run(_root, expected=None):
            assert expected == run_key
            return report

    monkeypatch.setattr(terminal, "_candidate_validator", lambda: Validator)
    digest = _manifest(root, required)
    return root, run_key, digest


def test_candidate_terminal_cell_replays_closed_manifest_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, run_key, digest = _terminal_cell(tmp_path, monkeypatch)
    report = terminal.validate_candidate_cell(
        root, expected_run_key=run_key, expected_manifest_sha256=digest,
    )
    assert report["verdict"] == "pass"


@pytest.mark.parametrize("plant", ("missing", "extra", "tamper", "hardlink"))
def test_candidate_terminal_cell_watches_closed_root_defects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plant: str,
) -> None:
    root, run_key, digest = _terminal_cell(tmp_path, monkeypatch)
    victim = root / "auth.log"
    if plant == "missing":
        victim.unlink()
    elif plant == "extra":
        (root / "unreviewed.txt").write_text("extra\n")
    elif plant == "tamper":
        victim.write_bytes(victim.read_bytes() + b"tamper\n")
    elif plant == "hardlink":
        os.link(victim, tmp_path / "alias.log")
    report = terminal.validate_candidate_cell(
        root, expected_run_key=run_key, expected_manifest_sha256=digest,
    )
    assert report["verdict"] == "blocked"
    assert report["blockers"]


def _producer_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, dict, dict]:
    root, run_key, _ = _terminal_cell(tmp_path, monkeypatch)
    (root / "content-manifest.json").unlink()
    (root / "cell-cleanup.json").unlink()
    monkeypatch.setattr(remote, "_terminal_module", lambda: terminal)
    contract = {
        "runId": "cell-001",
        "runKey": run_key,
        "requiredArtifacts": sorted(terminal._required_for(run_key)),
    }
    production = {
        "schemaVersion": 1,
        "kind": "teastore-candidate-cell-production-v1",
        "runId": "cell-001",
        "runKey": copy.deepcopy(run_key),
        "state": "validated",
        "safeToContinue": True,
        "ownedResourcesClean": True,
        "candidateValidationSha256": hashlib.sha256(
            (root / "candidate-validation.json").read_bytes()
        ).hexdigest(),
        "reason": None,
        "promotionAuthorized": False,
    }
    return root, contract, production


def test_remote_controller_truthfully_closes_and_replays_one_produced_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, contract, production = _producer_cell(tmp_path, monkeypatch)
    outcome = remote._finalize_candidate_cell(contract, root, production)
    assert outcome == {
        "schemaVersion": 1,
        "kind": "teastore-candidate-cell-execution-v1",
        "runId": "cell-001",
        "runKey": contract["runKey"],
        "state": "valid",
        "safeToContinue": True,
        "manifestSha256": hashlib.sha256(
            (root / "content-manifest.json").read_bytes()
        ).hexdigest(),
        "reason": None,
    }
    cleanup = json.loads((root / "cell-cleanup.json").read_text())
    assert cleanup["outerLeaseHeld"] is True
    assert cleanup["deadlineControllerSettled"] is True
    assert cleanup["ownedResourcesClean"] is True
    assert terminal.validate_candidate_cell(
        root,
        expected_run_key=contract["runKey"],
        expected_manifest_sha256=outcome["manifestSha256"],
    )["verdict"] == "pass"


@pytest.mark.parametrize("plant", ("bad-anchor", "extra-file", "unsafe-producer"))
def test_remote_controller_watches_producer_boundary_defects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plant: str,
) -> None:
    root, contract, production = _producer_cell(tmp_path, monkeypatch)
    if plant == "bad-anchor":
        production["candidateValidationSha256"] = "0" * 64
    elif plant == "extra-file":
        (root / "undeclared.txt").write_text("plant\n")
    elif plant == "unsafe-producer":
        production["ownedResourcesClean"] = False
    with pytest.raises(remote.ControllerError):
        remote._finalize_candidate_cell(contract, root, production)


def test_remote_controller_consumes_exact_order_once_under_terminal_gate(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path / "admission", bindings)
    document = transport.build_runtime_package(package)
    result_parent = tmp_path / "results"
    result_parent.mkdir()
    (result_parent / ".lease-receipts").mkdir()
    output = result_parent / document["campaignId"]
    lease = tmp_path / "outer.lock"
    document["outerLeasePath"] = str(lease)
    document["resultsRoot"] = str(result_parent)

    class TransportContract:
        @staticmethod
        def validate_runtime_package(value):
            return copy.deepcopy(value)

    monkeypatch.setattr(remote, "_transport_module", lambda: TransportContract)
    monkeypatch.setattr(remote.os, "geteuid", lambda: 1015)
    monkeypatch.setattr(remote.os, "getegid", lambda: 1015)
    monkeypatch.setattr(
        remote.pwd, "getpwuid", lambda _uid: type("Account", (), {"pw_name": "stig"})(),
    )
    calls: list[str] = []

    def cell_executor(contract, artifact_root: Path, timeout: float):
        assert timeout > 0
        artifact_root.mkdir()
        calls.append(contract["runId"])
        return {
            "schemaVersion": 1,
            "kind": "teastore-candidate-cell-execution-v1",
            "runId": contract["runId"],
            "runKey": copy.deepcopy(contract["runKey"]),
            "state": "valid",
            "safeToContinue": True,
            "manifestSha256": hashlib.sha256(contract["runId"].encode()).hexdigest(),
            "reason": None,
        }

    def terminal_gate(_root, **kwargs):
        assert set(kwargs["manifest_anchors"]) == set(bindings.run_ids)
        return {"verdict": "pass", "runCount": 27}

    receipt = remote.execute_package(
        document,
        output,
        cell_executor=cell_executor,
        clock=lambda: NOW.timestamp(),
        terminal_validator=terminal_gate,
    )
    assert calls == list(bindings.run_ids)
    assert receipt["state"] == "complete"
    assert receipt["runCount"] == 27
    assert receipt["promotionAuthorized"] is False
    assert len((output / "runtime-journal.jsonl").read_text().splitlines()) == 27
    lease_receipt = json.loads((
        result_parent / ".lease-receipts" / f"{document['campaignId']}.json"
    ).read_text())
    assert lease_receipt["state"] == "released"
    assert lease_receipt["releaseObserved"] is True
    assert lease_receipt["successorMayAcquire"] is True
    with pytest.raises(remote.ControllerError, match="already exists"):
        remote.execute_package(
            document,
            output,
            cell_executor=cell_executor,
            clock=lambda: NOW.timestamp(),
            terminal_validator=terminal_gate,
        )
    assert calls == list(bindings.run_ids)


def test_remote_controller_retains_pre_output_lease_abort_as_abstained(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path / "admission", bindings)
    document = transport.build_runtime_package(package)
    result_parent = tmp_path / "results"
    result_parent.mkdir()
    output = result_parent / document["campaignId"]
    document["outerLeasePath"] = str(tmp_path / "outer.lock")
    document["resultsRoot"] = str(result_parent)
    package_sha256 = "9" * 64

    class TransportContract:
        @staticmethod
        def validate_runtime_package(value):
            return copy.deepcopy(value)

    monkeypatch.setattr(remote, "_transport_module", lambda: TransportContract)
    monkeypatch.setattr(remote.os, "geteuid", lambda: 1015)
    monkeypatch.setattr(remote.os, "getegid", lambda: 1015)
    monkeypatch.setattr(
        remote.pwd, "getpwuid", lambda _uid: type("Account", (), {"pw_name": "stig"})(),
    )
    real_flock = remote.fcntl.flock

    def held_lease(descriptor: int, operation: int):
        if operation & remote.fcntl.LOCK_NB:
            raise BlockingIOError("planted held lease")
        return real_flock(descriptor, operation)

    monkeypatch.setattr(remote.fcntl, "flock", held_lease)
    with pytest.raises(remote.ControllerError, match="already held"):
        remote.execute_package(
            document, output, clock=lambda: NOW.timestamp(),
            package_sha256=package_sha256,
        )
    abort = transport.validate_fetched_abort(
        output, document, package_sha256=package_sha256,
    )
    assert abort["stage"] == "outer-lease-acquisition"
    assert abort["experimentalState"] == "ABSTAINED"
    assert abort["journalRows"] == abort["validCells"] == 0
    assert not (output / "campaign.json").exists()
    assert not (output / "runtime-journal.jsonl").exists()


@pytest.mark.parametrize("cleanup_clean", (True, False), ids=("recovered", "cleanup-defect"))
def test_remote_controller_stops_after_cell_failure_and_watches_cleanup(
    tmp_path: Path, bindings, monkeypatch: pytest.MonkeyPatch, cleanup_clean: bool,
) -> None:
    package = _package(tmp_path / "admission", bindings)
    document = transport.build_runtime_package(package)
    result_parent = tmp_path / "results"
    result_parent.mkdir()
    (result_parent / ".lease-receipts").mkdir()
    output = result_parent / document["campaignId"]
    document["outerLeasePath"] = str(tmp_path / "outer.lock")
    document["resultsRoot"] = str(result_parent)

    class TransportContract:
        @staticmethod
        def validate_runtime_package(value):
            return copy.deepcopy(value)

    monkeypatch.setattr(remote, "_transport_module", lambda: TransportContract)
    monkeypatch.setattr(remote.os, "geteuid", lambda: 1015)
    monkeypatch.setattr(remote.os, "getegid", lambda: 1015)
    monkeypatch.setattr(
        remote.pwd, "getpwuid", lambda _uid: type("Account", (), {"pw_name": "stig"})(),
    )
    attempted: list[str] = []
    cleanups: list[str] = []

    def fail_cell(contract, artifact_root: Path, _timeout: float):
        attempted.append(contract["runId"])
        artifact_root.mkdir()
        raise RuntimeError("planted mid-cell failure")

    def cleanup(contract, _timeout: float):
        cleanups.append(contract["runId"])
        return {
            "kind": "teastore-candidate-emergency-cleanup-v1",
            "composeProject": remote._compose_project(contract),
            "ownedResourcesClean": cleanup_clean,
        }

    expected_error = RuntimeError if cleanup_clean else remote.ControllerError
    with pytest.raises(expected_error):
        remote.execute_package(
            document,
            output,
            cell_executor=fail_cell,
            cleanup_executor=cleanup,
            clock=lambda: NOW.timestamp(),
        )
    assert attempted == [bindings.run_ids[0]]
    assert cleanups == [bindings.run_ids[0]]
    journal = [json.loads(line) for line in (
        output / "runtime-journal.jsonl"
    ).read_text().splitlines()]
    assert len(journal) == 1
    assert journal[0]["state"] == "stopped"
    assert "planted mid-cell failure" in journal[0]["reason"]
    assert ("emergency cleanup failed" in journal[0]["reason"]) is (not cleanup_clean)
