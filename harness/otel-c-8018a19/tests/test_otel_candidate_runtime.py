from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load("otel_candidate_runtime_tests", "modules/otel-demo/execution/candidate_runtime.py")
pilot = _load("otel_candidate_runtime_pilot_tests", "modules/otel-demo/execution/candidate_pilot.py")
remote = _load("otel_candidate_remote_tests", "modules/otel-demo/execution/candidate_remote.py")
setup = _load("otel_candidate_setup_tests", "modules/otel-demo/execution/candidate_setup.py")
NOW = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
SETUP_STARTED = NOW - timedelta(minutes=4)
SETUP_COMPLETED = NOW - timedelta(minutes=3)
READINESS_NOW = NOW - timedelta(minutes=2)


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# The live tombstone readers, kept so one test can look at the repository's real
# admission state while every other test is pinned to the pre-admission world.
REAL_ADMITTED_STUDY_EPOCHS = runtime.admitted_study_epochs
REAL_SETUP_TOMBSTONE = setup.ADMITTED_STUDY_EPOCHS
REAL_REMOTE_TOMBSTONE = remote.ADMITTED_STUDY_EPOCHS


@pytest.fixture(autouse=True)
def not_admitted(monkeypatch):
    """Pin every test to the state before the governed admission edit: no study
    epoch admitted anywhere. The v2 descriptor realizes all three postures, so
    without this pin a repository whose tombstones name the v2 epoch would let
    the fake-runner tests below reach real transport code. Tests that need the
    admitted state override the three attributes explicitly."""
    monkeypatch.setattr(runtime, "admitted_study_epochs", lambda: ())
    monkeypatch.setattr(setup, "ADMITTED_STUDY_EPOCHS", ())
    monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", ())


def _admit(monkeypatch, *epochs: str) -> None:
    monkeypatch.setattr(runtime, "admitted_study_epochs", lambda: tuple(epochs))
    monkeypatch.setattr(setup, "ADMITTED_STUDY_EPOCHS", tuple(epochs))
    monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", tuple(epochs))


def test_repository_tombstones_agree_and_name_at_most_the_current_study_epoch():
    """Reads the real bytes, not the autouse pin: whichever state the repository
    is in (before or after the governed admission edit), the two target
    controllers must carry the same tuple, it may name only the current epoch,
    and the runtime must refuse exactly when that tuple does not name it."""
    admitted = REAL_ADMITTED_STUDY_EPOCHS()
    assert admitted == REAL_SETUP_TOMBSTONE == REAL_REMOTE_TOMBSTONE
    assert set(admitted) <= {runtime.STUDY_EPOCH}
    assert runtime.STUDY_EPOCH == pilot.EPOCH == "otel-demo-offpath-v1"
    # v3 and offpath have no OpenSpec change of their own; the change id stays v2's (recorded decision).
    assert runtime.CHANGE_ID == "admit-otel-demo-candidate-pilot-v2"
    assert runtime.UNSUPPORTED_STUDY_EPOCH == pilot.FROZEN_EPOCH == "otel-demo-candidate-pilot-v1"
    assert runtime.unsupported_postures() == []
    if runtime.STUDY_EPOCH in admitted:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(runtime, "admitted_study_epochs", REAL_ADMITTED_STUDY_EPOCHS)
            runtime.refuse_unsupported("probe")  # admitted: the descriptor check alone decides
    else:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(runtime, "admitted_study_epochs", REAL_ADMITTED_STUDY_EPOCHS)
            with pytest.raises(runtime.GateError, match="not admitted by the installed target controllers"):
                runtime.refuse_unsupported("probe")


def test_disagreeing_tombstones_are_a_gate_failure_not_a_partial_admission(monkeypatch):
    """The setup and Compose controllers must carry the same tuple; the runtime
    reads both live and refuses on any difference rather than trusting either."""
    import types  # noqa: PLC0415

    def planted(controller, name):
        admitted = {"remote-setup-controller": ("otel-demo-candidate-pilot-v2",), "remote-compose-controller": ()}
        return types.SimpleNamespace(ADMITTED_STUDY_EPOCHS=admitted[controller])

    monkeypatch.setattr(runtime, "_controller_module", planted)
    monkeypatch.setattr(runtime, "admitted_study_epochs", REAL_ADMITTED_STUDY_EPOCHS)
    with pytest.raises(runtime.GateError, match="disagree about admitted study epochs"):
        runtime.admitted_study_epochs()
    # Agreeing tuples are read back exactly; a malformed entry is refused.
    monkeypatch.setattr(runtime, "_controller_module", lambda controller, name: types.SimpleNamespace(ADMITTED_STUDY_EPOCHS=("otel-demo-candidate-pilot-v2",)))
    assert runtime.admitted_study_epochs() == ("otel-demo-candidate-pilot-v2",)
    monkeypatch.setattr(runtime, "_controller_module", lambda controller, name: types.SimpleNamespace(ADMITTED_STUDY_EPOCHS=("",)))
    with pytest.raises(runtime.GateError, match="non-empty strings"):
        runtime.admitted_study_epochs()


@pytest.fixture
def bindings(tmp_path: Path):
    campaign = tmp_path / "compiled"
    pilot.materialize(campaign)
    return runtime.inspect_compiled_plan(campaign)


def _binding(bindings):
    return runtime.operational_binding(
        bindings,
        framework_commit="a" * 40,
        campaign_id="otelcand-20260830-a",
        repository_bundle_sha256="b" * 64,
        upstream_bundle_sha256="c" * 64,
        expected_materialized_source_sha256="d" * 64,
    )


def _gate_plan(bindings):
    binding = _binding(bindings)
    return {
        "schemaVersion": 1,
        "kind": runtime.PLAN_KIND,
        "gate": "GATE-PLAN",
        "decision": "approve-exact-plan",
        "typedApproval": runtime.expected_gate_plan_text(binding),
        "approvedBy": "external-human-reviewer",
        "approvedAt": (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "binding": binding,
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }


def _gate_setup(bindings, plan):
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    binding = runtime.setup_binding(checked, plan_sha)
    return {
        "schemaVersion": 1, "kind": runtime.SETUP_KIND, "gate": "GATE-SETUP",
        "decision": "authorize-one-shot-exact-setup",
        "typedApproval": runtime.expected_gate_setup_text(binding),
        "approvedBy": "external-human-reviewer",
        "approvedAt": (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "binding": binding, "runtimeAuthorized": False, "promotionAuthorized": False,
    }


def _setup_receipt(bindings, plan, gate_setup):
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    setup_sha = runtime.validate_gate_setup(gate_setup, checked, plan_sha, now=NOW)
    binding = checked["binding"]
    images = {service: "sha256:" + "e" * 64 for service in runtime.posture_catalog()["applicationServices"]}
    exited = [{"name": "caching_server_action_runner", "status": "exited(1)", "configFiles": "/opt/github_actions/caching_server_action_runner/docker-compose.yml"}]
    inventory = {"composeProjects": exited, "runningContainers": [], "volumes": ["foreign-volume-a"]}
    return {
        "schemaVersion": 1, "kind": "otel-demo-candidate-setup-receipt-v1",
        "campaignId": binding["campaignId"],
        "target": {"host": "fb14srv6", "transportUser": "root", "setupUser": "root"},
        "executionIdentity": copy.deepcopy(binding["target"]["executionIdentity"]),
        "frameworkCommit": binding["frameworkCommit"], "upstreamCommit": binding["upstreamCommit"],
        "gatePlanSha256": plan_sha, "gateSetupSha256": setup_sha,
        "targetContractSha256": binding["targetContractSha256"],
        "repositoryBundleSha256": binding["repositoryBundleSha256"],
        "upstreamBundleSha256": binding["upstreamBundleSha256"],
        "releaseRoot": binding["releaseRoot"], "repositoryRoot": binding["repositoryRoot"],
        "remoteSourceRoot": binding["remoteSourceRoot"], "remoteArtifactRoot": binding["remoteArtifactRoot"],
        "leasePath": binding["exclusiveLeasePath"], "composeProject": binding["compose"]["project"],
        "ports": copy.deepcopy(binding["compose"]["ports"]),
        "materializedSourceSha256": binding["expectedMaterializedSourceSha256"],
        "imageIds": images, "installedControllerDigests": copy.deepcopy(binding["controllerDigests"]),
        "dockerVersion": "29.6.1", "dockerGid": 998,
        "foreignInventoryBefore": copy.deepcopy(inventory), "foreignInventoryAfter": copy.deepcopy(inventory),
        "foreignVolumesPreserved": True, "activeForeignResourcesAbsent": True,
        "containersStarted": False, "cellsRun": 0, "runtimeAuthorized": False,
        "promotionAuthorized": False,
        "startedAt": SETUP_STARTED.isoformat().replace("+00:00", "Z"),
        "completedAt": SETUP_COMPLETED.isoformat().replace("+00:00", "Z"),
    }


def _observations(plan, receipt, receipt_sha):
    binding = plan["binding"]
    catalog = runtime.posture_catalog()
    token = "opq-1234567890abcdef12345678"
    trace_id = "1" * 32
    observations = {
        "target-contract-projection": {
            "targetContractSha256": binding["targetContractSha256"],
            "projection": copy.deepcopy(binding["targetContractProjection"]),
        },
        "target-identity": {
            "host": binding["target"]["host"], "transportUser": "root", "setupUser": "root",
            "executionUser": "stig", "uid": 1016, "gid": 1016, "supplementalGids": [998],
            "architecture": "x86_64", "kernel": "Linux 6.8",
            "observedAt": READINESS_NOW.isoformat().replace("+00:00", "Z"),
        },
        "target-root-and-host-isolation": {
            "target": copy.deepcopy(binding["target"]),
            "releaseRoot": binding["releaseRoot"], "repositoryRoot": binding["repositoryRoot"],
            "remoteSourceRoot": binding["remoteSourceRoot"],
            "sourceRootOwner": "root",
            "sourceRootWritableByExecutionUser": False,
            "sourceRootIsSymlink": False,
            "remoteArtifactParent": "/home/stig/observability-placement-candidate-v4-runs",
            "artifactParentOwner": "root",
            "artifactParentTraversableByExecutionUser": True,
            "remoteArtifactRoot": binding["remoteArtifactRoot"],
            "artifactRootOwner": "stig", "artifactRootWritableByExecutionUser": True,
            "exclusiveLeasePath": binding["exclusiveLeasePath"],
            "leaseOwner": "root", "leaseGroup": 1016, "leaseMode": "0660",
            "observedAt": READINESS_NOW.isoformat().replace("+00:00", "Z"),
        },
        "toolchain-pins": {
            "dockerVersion": "29.6.1", "composeVersion": "5.3.1",
            "pythonVersion": "3.11.11", "tcpdumpVersion": "4.99.4",
            "tsharkVersion": "4.2.5", "tcpdumpNonInteractive": True,
            "availableCommands": [
                "docker", "flock", "python3", "runuser", "sha256sum", "sudo",
                "systemctl", "systemd-run", "tcpdump", "tshark",
            ],
        },
        "source-image-bindings": {
            "upstreamCommit": "2d4661e4897aa7b2d2ddbb5ef8c4824ca8a1b88d",
            "materializedSourceSha256": receipt["materializedSourceSha256"],
            "imageIds": copy.deepcopy(receipt["imageIds"]),
            "controllerDigests": copy.deepcopy(binding["controllerDigests"]),
        },
        "installed-release-bindings": {
            "frameworkCommit": binding["frameworkCommit"], "releaseRoot": binding["releaseRoot"],
            "repositoryRoot": binding["repositoryRoot"], "remoteSourceRoot": binding["remoteSourceRoot"],
            "installedControllerDigests": copy.deepcopy(binding["controllerDigests"]),
            "sourceTreeImmutable": True, "sourceTreeSymlinks": [], "setupReceiptSha256": receipt_sha,
        },
        "foreign-inventory-preservation": {
            "runningContainers": [], "activeComposeProjects": [],
            "exitedComposeProjectsBefore": copy.deepcopy(receipt["foreignInventoryBefore"]["composeProjects"]),
            "exitedComposeProjectsAfter": copy.deepcopy(receipt["foreignInventoryAfter"]["composeProjects"]),
            "foreignVolumesBefore": ["foreign-volume-a"], "foreignVolumesAfter": ["foreign-volume-a"],
            "deletedForeignResources": [],
        },
        "project-port-lease-isolation": {
            "composeProject": binding["compose"]["project"],
            "ports": copy.deepcopy(binding["compose"]["ports"]),
            "preexistingResources": {"containers": [], "networks": [], "volumes": []},
            "occupiedPorts": [], "leaseAvailable": True,
            "controllerRootPresent": True, "candidateResultEntries": [],
        },
        "application-request-witness": {
            "requestToken": token, "injectedTraceId": trace_id,
            "applicationWitnessToken": token,
            "applicationWitnessTraceparent": f"00-{trace_id}-{'2'*16}-01",
            "applicationWitnessCount": 1,
        },
        "request-token-original-trace-correlation": {
            "requestToken": token, "injectedTraceId": trace_id,
            "observedOriginalTraceIds": [trace_id],
            "matchingSpanServices": list(pilot.OFFPATH_SYNC_PATH),
            "oneToOne": True, "crossTraceAssembly": False,
        },
        "cumulative-application-cpu": {
            "counter": "docker-engine-cpu_stats.cpu_usage.total_usage",
            "applicationServices": catalog["costApplicationServices"],
            "beforeNanoseconds": 1_000_000_000, "afterNanoseconds": 2_000_000_000,
            "monotonic": True, "cpuSeconds": 1.0,
        },
        "emitted-and-on-wire-telemetry-bytes": {
            "captureTool": "tshark", "filter": "tcp dst port 4317 or tcp dst port 4318",
            "calibrationPayloadBytes": 128, "measuredPayloadBytes": 128,
            "calibrationWireBytes": 256, "measuredWireBytes": 256,
            "retransmissionsExcludedFromPayload": True,
        },
        "frontend-fault-manifestation-recovery": {
            "scenario": "frontend-pause", "service": "frontend",
            "sameContainer": True, "preRunning": True, "duringPaused": True,
            "outageObserved": True, "postRunning": True, "postPaused": False,
            "readyAfter": True,
        },
        "owned-cleanup-and-deadline": {
            "leaseScope": "shared-srv6-host-exclusive-otel-then-online-boutique", "deadlineEnforced": True,
            "cleanupEnforced": True,
            "remainingResources": {"containers": [], "networks": [], "volumes": []},
        },
        "candidate-terminal-validation": {
            "expectedCells": 36, "validFixtureVerdict": "pass",
            "plantedDefectVerdict": "fail", "promotionAuthorized": False,
        },
    }
    for posture in ("none", "selected", "async", "full"):
        active = catalog["postures"][posture]["activeApplicationServices"]
        observations[f"{posture}-posture"] = {
            "posture": posture, "activeApplicationServices": active,
            "sourceInstrumentationLoadedServices": active,
            "renderedComposeActiveServices": active,
            "instrumentationLoadStates": runtime.expected_load_states(posture),
            "postureConfigSha256": runtime.posture_config_sha256_for_binding(binding, posture),
            "sourceDigestObservedEveryPatchedImage": True,
            "zeroStartupApplicationSignals": True if posture == "none" else None,
        }
    return observations


def _readiness(bindings, plan, gate_setup, receipt):
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    setup_sha = runtime.validate_gate_setup(gate_setup, checked, plan_sha, now=NOW)
    checked_receipt, receipt_sha = runtime.validate_setup_receipt(receipt, checked, plan_sha, setup_sha)
    return runtime.make_readiness(
        checked, plan_sha, setup_sha, checked_receipt, receipt_sha,
        _observations(checked, checked_receipt, receipt_sha),
        observed_at=READINESS_NOW.isoformat().replace("+00:00", "Z"),
    )


def _gate_run(plan, readiness):
    plan_sha = runtime.canonical_sha256(plan)
    readiness_sha = runtime.canonical_sha256(readiness)
    binding = runtime.run_binding(
        plan, plan_sha, readiness, readiness_sha,
        not_before=(NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        authorization_deadline=(NOW + timedelta(hours=11)).isoformat().replace("+00:00", "Z"),
    )
    return {
        "schemaVersion": 1, "kind": runtime.RUN_KIND, "gate": "GATE-RUN",
        "decision": "authorize-one-shot-exact-run",
        "typedApproval": runtime.expected_gate_run_text(binding),
        "approvedBy": "external-human-reviewer",
        "approvedAt": (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "binding": binding, "promotionAuthorized": False,
    }


def _package(tmp_path: Path, bindings):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    readiness = _readiness(bindings, plan, gate_setup, receipt)
    run = _gate_run(plan, readiness)
    for name, value in (("plan.json", plan), ("setup.json", gate_setup), ("setup-receipt.json", receipt), ("readiness.json", readiness), ("run.json", run)):
        _write(tmp_path / name, value)
    return runtime.authorize_from_files(
        bindings.root, tmp_path / "plan.json", tmp_path / "setup.json",
        tmp_path / "setup-receipt.json", tmp_path / "readiness.json",
        tmp_path / "run.json", clock=lambda: NOW,
    )


def test_plan_consumes_exact_24_cell_compiler_and_keeps_authority_separate(bindings):
    plan = _gate_plan(bindings)
    checked, digest = runtime.validate_gate_plan(plan, bindings)
    assert len(checked["binding"]["authorizedRunIds"]) == 36
    assert checked["runtimeAuthorized"] is False
    assert checked["promotionAuthorized"] is False
    assert len(digest) == 64


@pytest.mark.parametrize("plant", ("typed", "identity", "cells", "probe", "self-authorize", "stale"))
def test_gate_setup_checker_is_watched_failing(bindings, plant):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    if plant == "typed": gate_setup["typedApproval"] += " drift"
    elif plant == "identity": gate_setup["binding"]["executionIdentity"]["uid"] = 0
    elif plant == "cells": gate_setup["binding"]["cellsAuthorized"] = 1
    elif plant == "probe": gate_setup["binding"]["readinessProbeAuthorized"] = False
    elif plant == "self-authorize": gate_setup["runtimeAuthorized"] = True
    else: gate_setup["approvedAt"] = (NOW - timedelta(minutes=16)).isoformat().replace("+00:00", "Z")
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_setup(gate_setup, checked, plan_sha, now=NOW)


@pytest.mark.parametrize("plant", ("source", "image", "controller", "volume", "identity", "cell"))
def test_setup_receipt_checker_is_watched_failing(bindings, plant):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    if plant == "source": receipt["materializedSourceSha256"] = "0" * 64
    elif plant == "image": receipt["imageIds"][next(iter(receipt["imageIds"]))] = "not-an-image-id"
    elif plant == "controller": receipt["installedControllerDigests"]["runtime-admission"] = "0" * 64
    elif plant == "volume": receipt["foreignInventoryAfter"]["volumes"] = []
    elif plant == "identity": receipt["executionIdentity"]["uid"] = 0
    else: receipt["cellsRun"] = 1
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    setup_sha = runtime.validate_gate_setup(gate_setup, checked, plan_sha, now=NOW)
    with pytest.raises(runtime.GateError):
        runtime.validate_setup_receipt(receipt, checked, plan_sha, setup_sha)


def test_remote_setup_package_is_exact_and_watches_authority_tamper(bindings):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    setup_sha = runtime.validate_gate_setup(gate_setup, checked, plan_sha, now=NOW)
    package = runtime.SetupPackage(bindings, checked, plan_sha, gate_setup, setup_sha, NOW)
    document = runtime.setup_execution_package(package)
    checked_document = setup.validate_package(document, Path(document["setupStagingRoot"]))
    assert checked_document["runtimeAuthorized"] is False
    planted = copy.deepcopy(document)
    planted["runtimeAuthorized"] = True
    with pytest.raises(setup.SetupFailure):
        setup.validate_package(planted, Path(document["setupStagingRoot"]))


@pytest.mark.parametrize("field,value", (("host", "fb14srv5"), ("transportUsers", ["stig"]), ("reservedPorts", [1, 2, 3, 4, 5])))
def test_reviewed_target_projection_tamper_fails_gate_plan(bindings, field, value):
    plan = _gate_plan(bindings)
    plan["binding"]["targetContractProjection"][field] = value
    plan["typedApproval"] = runtime.expected_gate_plan_text(plan["binding"])
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_plan(plan, bindings)


def test_remote_controller_watches_wrong_host_fail_before_mutation():
    assert remote.validate_local_target(
        remote.EXPECTED_TARGET, observed_host="fb14srv6", observed_user="stig",
        # Linux getgroups() includes the primary gid (cab00b8): [998, 1016].
        observed_uid=1016, observed_gid=1016, observed_groups=[998, 1016],
    )["executionUser"] == "stig"
    with pytest.raises(remote.RuntimeFailure, match="wrong target"):
        remote.validate_local_target(
            remote.EXPECTED_TARGET, observed_host="fb14srv6", observed_user="root",
            observed_uid=0, observed_gid=0, observed_groups=[0],
        )
    with pytest.raises(remote.RuntimeFailure, match="wrong target"):
        remote.validate_local_target(
            remote.EXPECTED_TARGET, observed_host="fb14srv6", observed_user="stig",
            observed_uid=1016, observed_gid=1016, observed_groups=[27, 998],
        )


def test_setup_docker_commands_use_exact_runuser_groups(monkeypatch, tmp_path):
    """The identity stays exact; only its spelling changed.

    This used to pin `--group 1016 --supp-group 998`. util-linux 2.36.1, which
    is what all three hosts run, rejects a numeric --group with "group 1016
    does not exist" even when that gid is in /etc/group -- measured on fb14srv6
    2026-09-15. So the old pin fixed an invocation that could never run, and
    the test passed because it asserted against a fake `command` rather than a
    host. The gids remain the contract: they are resolved through `grp`, so a
    gid with no group entry fails closed rather than silently running as
    someone else.
    """
    observed = []
    def fake_command(argv, **kwargs):
        observed.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(setup, "command", fake_command)
    monkeypatch.setattr(setup, "_group_name", lambda gid, what: {1016: "stig", 998: "docker"}[gid])
    setup.run_as_stig(["docker", "version"], cwd=tmp_path)
    assert observed == [[
        "runuser", "--user", "stig", "--group", "stig",
        "--supp-group", "docker", "--", "docker", "version",
    ]]


def test_group_name_fails_closed_when_a_gid_has_no_group(monkeypatch):
    """A gid that resolves to nothing must stop the run, not fall back."""
    import grp as _grp
    def boom(_gid):
        raise KeyError("no such group")
    monkeypatch.setattr(_grp, "getgrgid", boom)
    with pytest.raises(setup.SetupFailure, match="has no group entry"):
        setup._group_name(1016, "execution")


def test_root_transport_and_stig_execution_are_separate_and_exact(bindings):
    allocation = runtime.target_allocation()
    assert allocation["transportUsers"] == allocation["setupUsers"] == ["root"]
    assert allocation["executionIdentities"] == [{"user": "stig", "uid": 1016, "gid": 1016, "supplementalGids": [998]}]
    assert allocation["leasePath"].endswith(".srv6-runtime.lock")
    assert set(_binding(bindings)["targetContractProjection"]) == {
        "host", "transportUsers", "setupUsers", "executionIdentities", "releaseParent",
        "artifactParent", "leasePath", "projectPrefix", "reservedPorts",
        "freshReadinessAfter", "readinessRequirements",
    }


def test_readiness_replays_every_positive_and_planted_defect_witness(bindings):
    plan = _gate_plan(bindings)
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    readiness = _readiness(bindings, plan, gate_setup, receipt)
    assert runtime.validate_readiness(
        readiness, checked, plan_sha, now=NOW
    ) == runtime.canonical_sha256(readiness)
    assert set(readiness["seams"]) == set(runtime.READINESS_SEAMS)
    assert all(row["checkerExitCode"] == 2 for row in readiness["seams"].values())


@pytest.mark.parametrize("plant", ("positive-drift", "planted-drift", "missing-seam", "scope-drift", "self-promote"))
def test_readiness_witness_defects_fail_closed(bindings, plant):
    plan = _gate_plan(bindings)
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    readiness = _readiness(bindings, plan, gate_setup, receipt)
    seam = runtime.READINESS_SEAMS[0]
    if plant == "positive-drift": readiness["seams"][seam]["positiveWitness"]["projection"]["host"] = "other"
    elif plant == "planted-drift": readiness["seams"][seam]["plantedDefectWitness"]["projection"]["host"] = "another"
    elif plant == "missing-seam": readiness["seams"].pop(seam)
    elif plant == "scope-drift": readiness["seams"][seam]["scope"] = "harness-contract-replay"
    else: readiness["promotionAuthorized"] = True
    with pytest.raises(runtime.GateError):
        runtime.validate_readiness(readiness, checked, plan_sha, now=NOW)


def test_exact_posture_environment_disables_or_enables_every_catalog_service():
    catalog = runtime.posture_catalog()
    for posture, expected in catalog["postures"].items():
        environment = runtime.posture_environment(posture, "/bound/source")
        active = set(expected["activeApplicationServices"])
        for service in catalog["applicationServices"]:
            key = service.replace("-", "_").upper()
            assert environment[f"OTEL_CANDIDATE_{key}_DISABLED"] == ("false" if service in active else "true")
            assert environment[f"OTEL_CANDIDATE_{key}_EXPORTER"] == ("otlp" if service in active else "none")


UNCONDITIONAL_RECOMMENDATION_ENTRYPOINT = (
    'ENTRYPOINT [ "opentelemetry-instrument", "python", "recommendation_server.py" ]\n'
)
GUARDED_RECOMMENDATION_ENTRYPOINT = (
    'ENTRYPOINT if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec python '
    "recommendation_server.py; else exec opentelemetry-instrument python "
    "recommendation_server.py; fi\n"
)


def test_resolve_recommendation_entrypoint_program_selects_by_posture():
    dockerfile_text = f"FROM base\n{GUARDED_RECOMMENDATION_ENTRYPOINT}"
    assert runtime.resolve_recommendation_entrypoint_program(dockerfile_text, "false") == "python"
    assert (
        runtime.resolve_recommendation_entrypoint_program(dockerfile_text, "true")
        == "opentelemetry-instrument"
    )
    # Unset OTEL_PLACEMENT_ENABLED must default to enabled, matching the framework's
    # existing default (materialize.py's manual-logging guard: `... , 'true') != 'false'`).
    dockerfile_text_default = f"FROM base\n{GUARDED_RECOMMENDATION_ENTRYPOINT}"
    assert (
        runtime.resolve_recommendation_entrypoint_program(dockerfile_text_default, "")
        == "opentelemetry-instrument"
    )


def test_resolve_recommendation_entrypoint_program_fails_closed_on_the_original_defect():
    # This is the exact upstream ENTRYPOINT shape (recommendationservice/Dockerfile:43)
    # that the audit flagged: unconditional, so OTEL_SDK_DISABLED=true would suppress
    # export without ever skipping the auto-instrumentation agent's load. The proof
    # must reject it outright rather than silently reporting a posture match.
    dockerfile_text = f"FROM base\n{UNCONDITIONAL_RECOMMENDATION_ENTRYPOINT}"
    with pytest.raises(runtime.GateError, match="exec-form"):
        runtime.resolve_recommendation_entrypoint_program(dockerfile_text, "false")


@pytest.mark.parametrize(
    "always_instrumented",
    [
        # A typo'd comparison: the conditional exists but its "then" branch is
        # unreachable for every value the framework ever sets.
        'ENTRYPOINT if [ "$OTEL_PLACEMENT_ENABLED" = "unreachable" ]; then exec python '
        "recommendation_server.py; else exec opentelemetry-instrument python "
        "recommendation_server.py; fi\n",
        # Both branches exec the wrapper: shell form, genuinely conditional-looking,
        # and mentions the plain interpreter -- a text/pattern check would pass it.
        'ENTRYPOINT if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec '
        "opentelemetry-instrument python recommendation_server.py; else exec "
        "opentelemetry-instrument python recommendation_server.py; fi\n",
        # Inverted branches: disabled gets the wrapper, enabled gets the plain
        # interpreter -- exactly backwards, and every substring a matcher would look
        # for is present.
        'ENTRYPOINT if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec '
        "opentelemetry-instrument python recommendation_server.py; else exec python "
        "recommendation_server.py; fi\n",
    ],
)
def test_entrypoint_proof_rejects_a_conditional_that_never_selects_the_plain_path(
    always_instrumented,
):
    # The whole point of executing the entrypoint rather than pattern-matching it: a
    # conditional whose plain-interpreter branch is never selected (or is selected for
    # the wrong posture) must not be able to fake a pass. Each variant below contains
    # every literal a text matcher would grep for.
    dockerfile_text = f"FROM base\n{always_instrumented}"
    with pytest.raises(runtime.GateError):
        runtime.prove_recommendation_source_instrumentation_posture(dockerfile_text)


def test_entrypoint_proof_rejects_a_command_that_only_prints_the_marker():
    # The behavioral half alone would accept this (the stub markers appear on stdout
    # without anything being exec'd); the exported-constant half rejects it.
    faked = (
        'ENTRYPOINT if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then '
        "echo INVOKED:python; else echo INVOKED:opentelemetry-instrument; fi\n"
    )
    assert (
        runtime.resolve_recommendation_entrypoint_program(f"FROM base\n{faked}", "false")
        == "python"
    )
    with pytest.raises(runtime.GateError, match="does not match the exported constant"):
        runtime.prove_recommendation_source_instrumentation_posture(f"FROM base\n{faked}")


def test_exported_entrypoint_constant_is_what_the_materializer_actually_renders():
    # The runtime declares EXPECTED_RECOMMENDATION_ENTRYPOINT_TEXT independently of
    # materialize.py; this is the comparison that keeps the two from drifting apart.
    assert (
        runtime.rendered_recommendation_entrypoint_command()
        == runtime.EXPECTED_RECOMMENDATION_ENTRYPOINT_TEXT
    )
    assert GUARDED_RECOMMENDATION_ENTRYPOINT == (
        "ENTRYPOINT " + runtime.EXPECTED_RECOMMENDATION_ENTRYPOINT_TEXT + "\n"
    )


def test_plan_time_proof_executes_the_real_materialized_guard():
    runtime.prove_materialized_recommendation_entrypoint.cache_clear()
    assert (
        runtime.prove_materialized_recommendation_entrypoint()
        == runtime.EXPECTED_RECOMMENDATION_ENTRYPOINT_TEXT
    )


def test_plan_inspection_enforces_the_real_entrypoint_proof(tmp_path: Path, monkeypatch):
    runtime.prove_materialized_recommendation_entrypoint.cache_clear()
    runtime.prove_materialized_source_guards.cache_clear()

    def regressed(dockerfile_text, otel_placement_enabled):
        # Simulate the original defect surviving materialize.py's guard: every
        # posture resolves to the instrumented program.
        return "opentelemetry-instrument"

    monkeypatch.setattr(runtime, "resolve_recommendation_entrypoint_program", regressed)
    campaign = tmp_path / "compiled"
    pilot.materialize(campaign)
    with pytest.raises(runtime.GateError, match="not a true zero baseline"):
        runtime.inspect_compiled_plan(campaign)
    monkeypatch.undo()
    runtime.prove_materialized_recommendation_entrypoint.cache_clear()
    runtime.prove_materialized_source_guards.cache_clear()


GUARDED_LAUNCH_CASES = (
    ("accountingservice", "dotnet AccountingService.dll", "instrument.sh dotnet AccountingService.dll"),
    ("paymentservice", "node index.js", "node --require ./opentelemetry.js index.js"),
    ("recommendationservice", "python recommendation_server.py", "opentelemetry-instrument python recommendation_server.py"),
)


@pytest.mark.parametrize("service,plain,instrumented", GUARDED_LAUNCH_CASES)
def test_every_entrypoint_guard_execs_the_plain_program_only_when_disabled(service, plain, instrumented):
    statement = runtime.EXPECTED_ENTRYPOINT_GUARDS[service]
    assert runtime.resolve_entrypoint_launch(statement, "false") == plain
    assert runtime.resolve_entrypoint_launch(statement, "true") == instrumented
    # Unset defaults to enabled, matching the framework's existing default.
    assert runtime.resolve_entrypoint_launch(statement, "") == instrumented
    assert runtime.prove_entrypoint_guard(service, statement) == statement


@pytest.mark.parametrize(
    "service,planted,diagnostic",
    (
        # Inverted branches on the .NET shim.
        (
            "accountingservice",
            'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec ./instrument.sh dotnet '
            "AccountingService.dll; else exec dotnet AccountingService.dll; fi",
            "not a true zero baseline",
        ),
        # Both branches carry the Node preload: every literal a matcher greps for is present.
        (
            "paymentservice",
            'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec node --require ./opentelemetry.js '
            "index.js; else exec node --require ./opentelemetry.js index.js; fi",
            "not a true zero baseline",
        ),
        # The enabled branch silently drops the preload: under-instrumented full posture.
        (
            "paymentservice",
            'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec node index.js; '
            "else exec node index.js; fi",
            "under-instrument",
        ),
        # The enabled branch goes through npm (upstream's ENTRYPOINT) rather than the exact
        # start script: a different process tree, so the two postures would not differ only
        # by the agent.
        (
            "paymentservice",
            'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec node index.js; '
            "else exec npm run start; fi",
            "under-instrument",
        ),
        # Behaviourally right but not the exported constant (an echo, not an exec).
        (
            "accountingservice",
            'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then echo INVOKED:dotnet AccountingService.dll; '
            "else echo INVOKED:instrument.sh dotnet AccountingService.dll; fi",
            "exported constant",
        ),
    ),
)
def test_entrypoint_guard_proof_rejects_planted_launch_defects(service, planted, diagnostic):
    with pytest.raises(runtime.GateError, match=diagnostic):
        runtime.prove_entrypoint_guard(service, planted)


def test_stdlib_overlay_parser_agrees_with_pyyaml_and_fails_closed_on_shape_drift():
    # The target runs /usr/bin/python3 -I where PyYAML is not guaranteed, so the
    # runtime parses its own overlay with the standard library; the dev venv has
    # PyYAML, so the two readings are compared here.
    yaml = pytest.importorskip("yaml")
    text = (ROOT / runtime.COMPOSE_OVERLAYS[1]).read_text(encoding="utf-8")
    assert runtime._overlay_document() == yaml.safe_load(text)
    for planted in (
        text.replace("  flagd:\n", "  flagd:\n    ports:\n      - 1\n"),  # unsupported section
        text.replace("    environment:\n", "    environment: {}\n", 1),  # flow mapping
        text + "volumes:\n  x: {}\n",  # second top-level key
        text.replace("      - /bin/sh\n", "      /bin/sh\n", 1),  # list item without dash
    ):
        with pytest.raises(runtime.GateError):
            runtime._parse_overlay(hashlib.sha256(planted.encode()).hexdigest(), planted)


def test_overlay_entrypoints_are_the_exported_guards_after_compose_unescaping():
    entrypoints = runtime.overlay_service_entrypoints()
    assert set(entrypoints) == {"accountingservice", "paymentservice"}
    for service, statement in entrypoints.items():
        assert statement == runtime.EXPECTED_ENTRYPOINT_GUARDS[service]
        assert "$$" not in statement and "$OTEL_PLACEMENT_ENABLED" in statement
    overlay_text = (ROOT / runtime.COMPOSE_OVERLAYS[1]).read_text(encoding="utf-8")
    # Compose interpolates $VAR at config time; the overlay must escape the shell variable.
    assert overlay_text.count('"$$OTEL_PLACEMENT_ENABLED"') == 2
    assert '"$OTEL_PLACEMENT_ENABLED"' not in overlay_text


@pytest.mark.parametrize(
    "plant",
    ("entrypoint-drift", "agent-variable-unbound", "flagd-unbound", "nginx-unmounted"),
)
def test_overlay_wiring_check_fails_closed_on_planted_drift(monkeypatch, plant):
    if plant == "entrypoint-drift":
        monkeypatch.setattr(runtime, "overlay_service_entrypoints", lambda: {"paymentservice": "exec node index.js"})
    elif plant == "agent-variable-unbound":
        original = runtime.overlay_service_environment
        monkeypatch.setattr(
            runtime, "overlay_service_environment",
            lambda service: {k: v for k, v in original(service).items() if k != "JAVA_TOOL_OPTIONS"},
        )
    elif plant == "flagd-unbound":
        original = runtime.overlay_service_environment
        monkeypatch.setattr(
            runtime, "overlay_service_environment",
            lambda service: {k: v for k, v in original(service).items() if k != "FLAGD_METRICS_EXPORTER"},
        )
    else:
        original = runtime.overlay_service_volumes
        monkeypatch.setattr(
            runtime, "overlay_service_volumes",
            lambda service: [] if service == "imageprovider" else original(service),
        )
    with pytest.raises(runtime.GateError):
        runtime.verify_overlay_posture_controls()


def test_agent_environment_and_flagd_pins_match_the_pinned_upstream_checkout():
    runtime.prove_materialized_source_guards.cache_clear()
    proven = runtime.prove_materialized_source_guards()
    assert proven["adservice"] == {"JAVA_TOOL_OPTIONS": "-javaagent:/usr/src/app/opentelemetry-javaagent.jar"}
    assert proven["frauddetectionservice"] == {"JAVA_TOOL_OPTIONS": "-javaagent:/app/opentelemetry-javaagent.jar"}
    assert proven["kafka"] == {
        "KAFKA_OPTS": "-javaagent:/tmp/opentelemetry-javaagent.jar -Dotel.jmx.target.system=kafka-broker"
    }
    assert proven["flagd"]["enabled"] == {"FLAGD_OTEL_COLLECTOR_URI": "otelcol:4317", "FLAGD_METRICS_EXPORTER": "otel"}
    assert proven["flagd"]["disabled"] == {"FLAGD_OTEL_COLLECTOR_URI": "", "FLAGD_METRICS_EXPORTER": ""}
    assert len(proven["imageprovider"]["disabledTemplateSha256"]) == 64
    env_text = (ROOT / "upstream/opentelemetry-demo/.env").read_text(encoding="utf-8")
    assert "OTEL_COLLECTOR_HOST=otelcol\n" in env_text and "OTEL_COLLECTOR_PORT_GRPC=4317\n" in env_text


def test_source_guard_proof_fails_closed_when_an_exported_agent_constant_drifts(monkeypatch):
    runtime.prove_materialized_source_guards.cache_clear()
    drifted = dict(runtime.EXPECTED_AGENT_ENVIRONMENT)
    drifted["adservice"] = ("JAVA_TOOL_OPTIONS", "-javaagent:/elsewhere/agent.jar")
    monkeypatch.setattr(runtime, "EXPECTED_AGENT_ENVIRONMENT", drifted)
    with pytest.raises(runtime.GateError, match="materializer agent environment differs"):
        runtime.prove_materialized_source_guards()
    monkeypatch.undo()
    runtime.prove_materialized_source_guards.cache_clear()


def test_posture_environment_clears_every_agent_variable_when_disabled():
    none = runtime.posture_environment("none", "/src")
    full = runtime.posture_environment("full", "/src")
    selected = runtime.posture_environment("selected", "/src")
    async_ = runtime.posture_environment("async", "/src")
    for key in (
        "OTEL_CANDIDATE_ADSERVICE_JAVA_TOOL_OPTIONS",
        "OTEL_CANDIDATE_FRAUDDETECTIONSERVICE_JAVA_TOOL_OPTIONS",
        "OTEL_CANDIDATE_KAFKA_KAFKA_OPTS",
    ):
        assert none[key] == "" and selected[key] == ""
        assert full[key] != ""
    # offpath selected is the synchronous checkout path, flagd included: flagd's
    # exporter is on from selected up, off only under none.
    for key in ("OTEL_CANDIDATE_FLAGD_OTEL_COLLECTOR_URI", "OTEL_CANDIDATE_FLAGD_METRICS_EXPORTER"):
        assert none[key] == ""
        assert selected[key] == async_[key] == full[key] != ""
    # async adds the orders topic's broker and consumers (fraud detection, kafka
    # agents; accounting) and nothing else.
    assert async_["OTEL_CANDIDATE_FRAUDDETECTIONSERVICE_JAVA_TOOL_OPTIONS"] == full["OTEL_CANDIDATE_FRAUDDETECTIONSERVICE_JAVA_TOOL_OPTIONS"] != ""
    assert async_["OTEL_CANDIDATE_KAFKA_KAFKA_OPTS"] == full["OTEL_CANDIDATE_KAFKA_KAFKA_OPTS"] != ""
    assert async_["OTEL_CANDIDATE_ADSERVICE_JAVA_TOOL_OPTIONS"] == ""
    for service in (
        "ACCOUNTINGSERVICE", "CHECKOUTSERVICE", "FRONTEND", "CARTSERVICE", "CURRENCYSERVICE",
        "PAYMENTSERVICE", "SHIPPINGSERVICE", "QUOTESERVICE", "EMAILSERVICE", "PRODUCTCATALOGSERVICE",
    ):
        assert async_[f"OTEL_CANDIDATE_{service}_ENABLED"] == "true"
    for service in ("ACCOUNTINGSERVICE", "FRAUDDETECTIONSERVICE", "KAFKA", "RECOMMENDATIONSERVICE", "ADSERVICE"):
        assert selected[f"OTEL_CANDIDATE_{service}_ENABLED"] == "false"
    for service in ("RECOMMENDATIONSERVICE", "ADSERVICE", "IMAGEPROVIDER"):
        assert async_[f"OTEL_CANDIDATE_{service}_ENABLED"] == "false"
    assert full["OTEL_CANDIDATE_FLAGD_METRICS_EXPORTER"] == "otel"  # flagd rejects "otlp"
    assert none["OTEL_CANDIDATE_IMAGEPROVIDER_NGINX_TEMPLATE"].endswith("nginx.no-otel.conf.template")
    assert full["OTEL_CANDIDATE_IMAGEPROVIDER_NGINX_TEMPLATE"].endswith("/src/imageprovider/nginx.conf.template")
    assert selected["OTEL_CANDIDATE_IMAGEPROVIDER_NGINX_TEMPLATE"].endswith("nginx.no-otel.conf.template")


def test_install_side_compose_environment_is_the_full_posture_environment(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "candidate-posture-contract.json").write_bytes((ROOT / runtime.POSTURE_CATALOG).read_bytes())
    installed = setup.compose_environment(source, "f" * 64)
    full = runtime.posture_environment("full", str(source))
    for key, value in full.items():
        assert installed[key] == value, key
    assert setup.FIXED_CONTROLLER_PATHS == runtime.CONTROLLER_PATHS


def _catalog_with_an_emailservice_blocker(catalog: dict) -> dict:
    """A catalog in which one service really is ``loaded-exporting``.

    emailservice is one of the four services with no source guard, so relabelling
    it does not trip the guarded-set cross-check first; the realization formula is
    what has to see it. Its realization rows are recomputed the way
    ``_expected_realization`` would after D13: blocking, therefore unrealized.
    Under the offpath closures emailservice is active from selected up, so only
    ``none`` disables it and only ``none`` becomes unrealizable.
    """
    planted = copy.deepcopy(dict(catalog))
    planted["serviceInstrumentation"]["emailservice"].update({
        "disabledLoadState": "loaded-exporting",
        "disabledControl": "none-available",
        "disabledControlSite": None,
    })
    planted["postureRealization"]["none"].update({
        "status": "not-structurally-realizable",
        "blockingServices": ["emailservice"],
        "silencedButLoadedServices": ["flagd", "flagd-ui", "loadgenerator"],
    })
    return planted


def test_a_real_loaded_exporting_blocker_still_makes_a_posture_unrealizable(tmp_path: Path, monkeypatch):
    """D13 relaxed ``loaded-silenced``, not ``loaded-exporting``.

    A service that emits telemetry in every posture is still the thing that makes
    a disabled posture structurally unrealizable, and the catalog may not claim
    otherwise: the realization formula is derived, not declared.
    """
    catalog = json.loads((ROOT / runtime.POSTURE_CATALOG).read_text(encoding="utf-8"))
    path = tmp_path / "catalog.json"
    monkeypatch.setattr(runtime, "POSTURE_CATALOG", path)

    blocked = _catalog_with_an_emailservice_blocker(catalog)
    path.write_text(json.dumps(blocked), encoding="utf-8")
    realization = runtime.posture_catalog()["postureRealization"]["none"]
    assert realization["status"] == "not-structurally-realizable"
    assert realization["blockingServices"] == ["emailservice"]
    assert realization["silencedButLoadedServices"] == ["flagd", "flagd-ui", "loadgenerator"]
    assert realization["claimBoundary"] == runtime.CLAIM_BOUNDARY_LABEL

    # Planted: the same real blocker, but the catalog declares the posture
    # realized anyway. The derived formula must contradict the declaration.
    lying = copy.deepcopy(blocked)
    lying["postureRealization"]["none"].update({"status": "implemented", "blockingServices": []})
    path.write_text(json.dumps(lying), encoding="utf-8")
    with pytest.raises(runtime.GateError, match="realization differs from the per-service classification"):
        runtime.posture_catalog()

    # Planted the other way: no blocker, but the catalog calls the posture
    # unrealized because four services are merely silenced. That is the pre-D13
    # rule and it is now equally a drift from the formula.
    pre_d13 = copy.deepcopy(catalog)
    pre_d13["postureRealization"]["none"]["status"] = "not-structurally-realizable"
    path.write_text(json.dumps(pre_d13), encoding="utf-8")
    with pytest.raises(runtime.GateError, match="realization differs from the per-service classification"):
        runtime.posture_catalog()

    # Planted: a service may still not be declared not-loaded without a guard.
    forged = copy.deepcopy(catalog)
    for row in forged["serviceInstrumentation"].values():
        if row["disabledLoadState"] != "not-loaded":
            row["disabledLoadState"] = "not-loaded"
            row["disabledControl"] = "compose-entrypoint-guard"
            row["disabledControlSite"] = "planted"
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(runtime.GateError, match="instrumentation classification differs"):
        runtime.posture_catalog()


def test_refusal_is_two_independent_facts_descriptor_then_tombstone(tmp_path: Path, monkeypatch):
    # The offpath descriptor realizes all four postures and the catalog agrees, so
    # the descriptor half of the refusal is lifted...
    assert runtime.unsupported_postures() == []
    # ...and the tombstone half still refuses until the governed edit admits v3.
    with pytest.raises(runtime.GateError, match="not admitted by the installed target controllers"):
        runtime.refuse_unsupported("probe")
    # The superseded v1 shape (a descriptor with unrealized postures) still
    # refuses with the UNSUPPORTED ledger's identity, before the tombstone is read.
    monkeypatch.setattr(runtime, "frozen_descriptor", lambda: runtime._pilot_module().load_descriptor(runtime.UNSUPPORTED_DESCRIPTOR))
    assert runtime.unsupported_postures() == ["none", "selected"]
    with pytest.raises(runtime.GateError, match="otel-demo-candidate-pilot-v1 is UNSUPPORTED.*none and selected"):
        runtime.refuse_unsupported("probe")
    monkeypatch.undo()
    monkeypatch.setattr(setup, "ADMITTED_STUDY_EPOCHS", ()); monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", ())
    # Admitting the epoch (data in the two controllers, not code here) lifts it.
    _admit(monkeypatch, runtime.STUDY_EPOCH)
    runtime.refuse_unsupported("probe")  # no raise
    # Admitting a different epoch does not.
    _admit(monkeypatch, "otel-demo-candidate-pilot-v1")
    with pytest.raises(runtime.GateError, match="not admitted"):
        runtime.refuse_unsupported("probe")
    # A descriptor claiming a posture the per-service table cannot realize is
    # still the gate failure: catalog realization is necessary for the claim.
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(_catalog_with_an_emailservice_blocker(
            json.loads((ROOT / runtime.POSTURE_CATALOG).read_text(encoding="utf-8"))
        )),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "POSTURE_CATALOG", path)
    with pytest.raises(runtime.GateError, match="descriptor says 'implemented' but the catalog realization says"):
        runtime.unsupported_postures()


def test_none_means_no_telemetry_emitted_with_four_services_named_as_the_claim_boundary():
    """D13 (user, 2026-09-06), the "emitted" reading.

    The five in-code-SDK source guards close every ``loaded-exporting`` blocker,
    so ``none`` and ``selected`` are now ``implemented``: nothing is emitted.
    emailservice, flagd, flagd-ui and loadgenerator remain ``loaded-silenced`` --
    their instrumentation is still compiled/imported and still costs -- and that
    is carried in the evidence as an explicit, named claim boundary rather than
    as a blocker. The proof therefore cannot be read as "no instrumentation
    loaded": ``silencedButLoadedServices`` and ``notLoadedServices`` are separate
    lists and the four are in the former.

    What still refuses is the frozen v1 descriptor, i.e. a new study epoch.
    """
    catalog = runtime.posture_catalog()
    rule = catalog["proofRule"]
    assert rule["disabledLoadStateRequired"] == "not-exporting"
    assert rule["noneSemantics"] == runtime.NONE_SEMANTICS == "no-telemetry-emitted"
    assert rule["loadedButSilencedIsClaimBoundaryNotBlocker"] is True
    assert rule["zeroStartupApplicationSignalsRequiredForNone"] is True
    guarded = (
        "cartservice", "checkoutservice", "currencyservice",
        "productcatalogservice", "shippingservice",
    )
    for service in guarded:
        row = catalog["serviceInstrumentation"][service]
        assert row["disabledLoadState"] == "not-loaded"
        assert row["disabledControl"] == "materialized-source-guard"
        assert row["runtimeProbe"] == {
            "kind": "container-env", "variable": "OTEL_PLACEMENT_ENABLED",
            "loadedWhenEquals": "true", "notLoadedWhenEquals": "false",
        }
    # offpath: selected and async activate emailservice and flagd, so their
    # silenced set is the D13 four minus the closure.
    boundaries = {
        "none": ["emailservice", "flagd", "flagd-ui", "loadgenerator"],
        "selected": ["flagd-ui", "loadgenerator"],
        "async": ["flagd-ui", "loadgenerator"],
    }
    for posture, boundary in boundaries.items():
        realization = catalog["postureRealization"][posture]
        assert realization["status"] == "implemented"
        assert realization["blockingServices"] == []
        assert realization["silencedButLoadedServices"] == boundary
        assert realization["disabledSetSemantics"] == "no-telemetry-emitted"
        assert realization["claimBoundary"] == runtime.CLAIM_BOUNDARY_LABEL
        # The boundary is not silently folded into "not loaded".
        assert not set(boundary) & set(realization["notLoadedServices"])
        for service in boundary:
            assert catalog["serviceInstrumentation"][service]["disabledLoadState"] == "loaded-silenced"
    assert catalog["postureRealization"]["full"]["claimBoundary"] is None
    # The v2 descriptor writes the same reading into the frozen design and
    # names the same four services; the runtime cross-checks the two.
    assert runtime.descriptor_posture_statuses() == {
        "none": "implemented", "selected": "implemented", "async": "implemented", "full": "implemented",
    }
    descriptor = runtime.frozen_descriptor()
    for posture, boundary in boundaries.items():
        assert descriptor["postureRealization"][posture]["claimBoundary"]["loadedButSilencedServices"] == boundary
    runtime.verify_descriptor_bindings(descriptor, catalog)
    drifted = copy.deepcopy(descriptor)
    drifted["postureRealization"]["none"]["claimBoundary"]["loadedButSilencedServices"] = boundary[:-1]
    with pytest.raises(runtime.GateError, match="claim boundary differs from the catalog"):
        runtime.verify_descriptor_bindings(drifted, catalog)
    # Planted (offpath): a descriptor closure the catalog does not install.
    drifted = copy.deepcopy(descriptor)
    drifted["postureRealization"]["selected"]["closure"] = sorted(
        drifted["postureRealization"]["selected"]["closure"] + ["recommendationservice"]
    )
    with pytest.raises(runtime.GateError, match="selected posture: descriptor closure differs"):
        runtime.verify_descriptor_bindings(drifted, catalog)
    drifted = copy.deepcopy(descriptor)
    drifted["target"]["executionUser"] = "fhuebscher"
    with pytest.raises(runtime.GateError, match="target identity differs from the reviewed srv6 allocation"):
        runtime.verify_descriptor_bindings(drifted, catalog)
    # Admitting the epoch on the target is still a separate governed step.
    with pytest.raises(runtime.GateError, match="not admitted"):
        runtime.refuse_unsupported("probe")


def test_cell_contract_and_setup_package_carry_the_study_epoch(tmp_path: Path, bindings, monkeypatch):
    package = _package(tmp_path, bindings)
    contract = runtime.build_cell_contract(package, bindings.cells[0])
    assert contract["studyEpoch"] == runtime.STUDY_EPOCH == pilot.EPOCH
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    setup_sha = runtime.validate_gate_setup(gate_setup, checked, plan_sha, now=NOW)
    document = runtime.setup_execution_package(runtime.SetupPackage(bindings, checked, plan_sha, gate_setup, setup_sha, NOW))
    assert document["studyEpoch"] == runtime.STUDY_EPOCH == "otel-demo-offpath-v1"
    # With no epoch admitted both target controllers refuse before mutation.
    with pytest.raises(setup.SetupFailure, match="UNSUPPORTED"):
        setup.refuse_unsupported("probe", runtime.STUDY_EPOCH)
    with pytest.raises(remote.RuntimeFailure, match="UNSUPPORTED"):
        remote.refuse_unsupported("probe", runtime.STUDY_EPOCH)
    unknown = copy.deepcopy(runtime.execution_package(package))
    unknown["studyEpoch"] = "otel-demo-candidate-pilot-v9"
    with pytest.raises(remote.RuntimeFailure, match="unknown study epoch"):
        remote.validate_package(unknown, clock=lambda: NOW)
    # Once the governed edit names v3, the same package's epoch passes both
    # tombstones while the superseded v1 epoch still does not.
    monkeypatch.setattr(setup, "ADMITTED_STUDY_EPOCHS", (runtime.STUDY_EPOCH,))
    monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (runtime.STUDY_EPOCH,))
    setup.refuse_unsupported("probe", runtime.STUDY_EPOCH)
    remote.refuse_unsupported("probe", runtime.STUDY_EPOCH)
    with pytest.raises(setup.SetupFailure, match="otel-demo-candidate-pilot-v1 is UNSUPPORTED"):
        setup.refuse_unsupported("probe", "otel-demo-candidate-pilot-v1")
    with pytest.raises(remote.RuntimeFailure, match="otel-demo-candidate-pilot-v1 is UNSUPPORTED"):
        remote.refuse_unsupported("probe", "otel-demo-candidate-pilot-v1")


def test_posture_config_digest_is_shared_between_producer_and_validator(tmp_path: Path, bindings):
    package = _package(tmp_path, bindings)
    seen = {}
    for cell in bindings.cells:
        contract = runtime.build_cell_contract(package, cell)
        assert remote.posture_config_document(contract) == runtime.posture_config_document(contract)
        digest = runtime.posture_config_sha256(contract)
        assert digest == runtime.posture_config_sha256_for_binding(package.gate_plan["binding"], contract["posture"]["id"])
        seen.setdefault(contract["posture"]["id"], set()).add(digest)
    assert all(len(values) == 1 for values in seen.values())
    assert len({next(iter(v)) for v in seen.values()}) == 4


def _fake_docker(responses):
    def run(argv, **kwargs):
        key = tuple(argv[:2])
        stdout, code = responses.get(key, ("", 1))
        return subprocess.CompletedProcess(argv, code, stdout, "" if code == 0 else "unavailable")
    return run


@pytest.mark.parametrize(
    "probe,responses,env,expected",
    (
        ({"kind": "container-env", "variable": "JAVA_TOOL_OPTIONS", "loadedWhenContains": "-javaagent:", "notLoadedWhenEquals": ""}, {}, {"JAVA_TOOL_OPTIONS": ""}, "disabled"),
        ({"kind": "container-env", "variable": "JAVA_TOOL_OPTIONS", "loadedWhenContains": "-javaagent:", "notLoadedWhenEquals": ""}, {}, {"JAVA_TOOL_OPTIONS": "-javaagent:/x.jar"}, "enabled"),
        ({"kind": "container-env", "variable": "JAVA_TOOL_OPTIONS", "loadedWhenContains": "-javaagent:", "notLoadedWhenEquals": ""}, {}, {}, "indeterminate"),
        ({"kind": "pid1-environ", "variable": "PYTHONPATH", "loadedWhenContains": "auto_instrumentation"}, {("docker", "exec"): ("HOME=/root\0PYTHONPATH=/usr/lib/opentelemetry/instrumentation/auto_instrumentation\0", 0)}, {}, "enabled"),
        ({"kind": "pid1-environ", "variable": "PYTHONPATH", "loadedWhenContains": "auto_instrumentation"}, {("docker", "exec"): ("HOME=/root\0", 0)}, {}, "disabled"),
        ({"kind": "pid1-environ", "variable": "CORECLR_ENABLE_PROFILING", "loadedWhenEquals": "1"}, {}, {}, "indeterminate"),
        ({"kind": "process-args", "loadedWhenContains": "-javaagent:"}, {("docker", "top"): ("PID ARGS\n12 java -javaagent:/tmp/agent.jar kafka.Kafka\n", 0)}, {}, "enabled"),
        ({"kind": "process-args", "loadedWhenContains": "--require ./opentelemetry.js"}, {("docker", "top"): ("PID ARGS\n7 node index.js\n", 0)}, {}, "disabled"),
        ({"kind": "container-file", "path": "/etc/nginx/nginx.conf", "loadedWhenContains": "load_module modules/ngx_otel_module.so;"}, {("docker", "exec"): ("events {}\nhttp {}\n", 0)}, {}, "disabled"),
        ({"kind": "container-file", "path": "/etc/nginx/nginx.conf", "loadedWhenContains": "load_module modules/ngx_otel_module.so;"}, {("docker", "exec"): ("load_module modules/ngx_otel_module.so;\n", 0)}, {}, "enabled"),
    ),
)
def test_remote_instrumentation_probes_decide_from_observed_bytes(monkeypatch, probe, responses, env, expected):
    monkeypatch.setattr(remote, "command", _fake_docker(responses))
    inspected = {"Config": {"Env": [f"{k}={v}" for k, v in env.items()], "Entrypoint": ["x"], "Cmd": None}}
    observed = remote.probe_instrumentation_control("cid", inspected, probe)
    assert observed["observedControl"] == expected
    assert observed["evidence"]["entrypoint"] == ["x"]
    assert remote.probe_instrumentation_control("cid", inspected, None)["observedControl"] == "not-probed"


def test_remote_posture_proof_v2_records_per_service_load_states(tmp_path: Path, bindings, monkeypatch):
    package = _package(tmp_path, bindings)
    cell = next(c for c in bindings.cells if c["runKey"]["posture"] == "none")
    contract = runtime.build_cell_contract(package, cell)
    source = tmp_path / "source"
    source.mkdir()
    (source / "candidate-posture-contract.json").write_bytes((ROOT / runtime.POSTURE_CATALOG).read_bytes())
    contract["remoteSourceRoot"] = str(source)
    catalog = runtime.posture_catalog()
    image = "sha256:" + "e" * 64

    def fake_command(argv, **kwargs):
        if argv[:2] == ["docker", "inspect"]:
            service = argv[2].removeprefix("cid-")
            env = [f"{k}={v}" for k, v in contract["posture"]["environment"].items()]
            env += ["OTEL_SDK_DISABLED=true", "OTEL_TRACES_EXPORTER=none", "OTEL_PLACEMENT_ENABLED=false",
                    "JAVA_TOOL_OPTIONS=", "KAFKA_OPTS=", "FLAGD_OTEL_COLLECTOR_URI=", "OTEL_PHP_AUTOLOAD_ENABLED=false"]
            return subprocess.CompletedProcess(argv, 0, json.dumps([{"Image": image, "Config": {"Env": env, "Entrypoint": None, "Cmd": None}}]), "")
        if argv[:2] == ["docker", "exec"]:
            return subprocess.CompletedProcess(argv, 0, "HOME=/x\0" if argv[-1] == "/proc/1/environ" else "events {}\n", "")
        if argv[:2] == ["docker", "top"]:
            return subprocess.CompletedProcess(argv, 0, "PID ARGS\n1 java kafka.Kafka\n", "")
        raise AssertionError(argv)

    monkeypatch.setattr(remote, "command", fake_command)
    monkeypatch.setattr(remote, "container_id", lambda cell, service, environment: f"cid-{service}")
    contract["imageIds"] = {service: image for service in catalog["applicationServices"]}
    proof = remote.posture_proof(contract, {}, "no signals\n", "c" * 64)
    assert proof["schemaVersion"] == 2 and proof["exact"] is True and proof["loadedServices"] == []
    assert proof["postureConfigSha256"] == runtime.posture_config_sha256(contract)
    for service, row in proof["services"].items():
        expected = runtime.expected_service_control(catalog, "none", service)
        assert row["instrumentation"]["expectedLoadState"] == expected["expectedLoadState"]
        if expected["probe"] is None:
            assert row["instrumentation"]["observedControl"] == "not-probed"
        else:
            assert row["instrumentation"]["observedControl"] == "disabled"
            assert row["instrumentation"]["observedLoadState"] == expected["expectedLoadState"]
    # A javaagent that survived into the none posture is caught behaviourally, not by text.
    def leaking(argv, **kwargs):
        if argv[:2] == ["docker", "top"]:
            return subprocess.CompletedProcess(argv, 0, "PID ARGS\n1 java -javaagent:/tmp/opentelemetry-javaagent.jar kafka.Kafka\n", "")
        return fake_command(argv, **kwargs)
    monkeypatch.setattr(remote, "command", leaking)
    leaked = remote.posture_proof(contract, {}, "no signals\n", "c" * 64)
    assert leaked["exact"] is False and leaked["loadedServices"] == ["kafka"]


def test_shipped_target_modules_defer_annotations_for_python39() -> None:
    # py_compile is blind to `X | None` in a signature: it is valid 3.9 grammar and
    # raises TypeError only when the def executes on the host. Every module that
    # ships to the 3.9 target must defer annotation evaluation.
    shipped = (
        "modules/otel-demo/execution/candidate_setup.py",
        "modules/otel-demo/execution/candidate_runtime.py",
        "modules/otel-demo/execution/candidate_remote.py",
        "modules/otel-demo/execution/candidate_pilot.py",
        "modules/otel-demo/materialize.py",
        "modules/otel-demo/workload.py",
        "modules/otel-demo/validation/candidate_terminal.py",
        "modules/otel-demo/validation/candidate_unsupported.py",
    )
    for relative in shipped:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative, feature_version=(3, 9))
        defers = any(
            isinstance(node, ast.ImportFrom) and node.module == "__future__"
            and any(alias.name == "annotations" for alias in node.names)
            for node in tree.body
        )
        assert defers, f"{relative} must `from __future__ import annotations` for the 3.9 target"
        for node in ast.walk(tree):
            # No 3.10+ syntax that ast.parse(feature_version=(3, 9)) would already reject
            # slips through; also forbid parenthesised context managers and match by name.
            assert not isinstance(node, getattr(ast, "Match", ())), f"{relative} uses match"


def test_posture_catalog_does_not_require_the_upstream_checkout(tmp_path: Path, monkeypatch):
    # Simulate a reaped worktree: the upstream submodule is gone, but retained evidence
    # still has to replay. posture_catalog() is on the terminal-replay path, so it must
    # re-check the plan-time-proven constant rather than re-executing the entrypoint.
    runtime.prove_materialized_recommendation_entrypoint.cache_clear()
    monkeypatch.setattr(
        runtime, "UPSTREAM_RECOMMENDATION_DOCKERFILE", tmp_path / "absent/Dockerfile"
    )
    assert runtime.posture_catalog()["postures"]["none"]["sourceInstrumentationLoadedServices"] == []
    # ... while the plan-time proof still fails closed on the missing checkout.
    with pytest.raises(runtime.GateError):
        runtime.prove_materialized_recommendation_entrypoint()
    monkeypatch.undo()
    runtime.prove_materialized_recommendation_entrypoint.cache_clear()


def test_posture_catalog_rejects_a_drifted_materializer(monkeypatch):
    monkeypatch.setattr(
        runtime, "rendered_recommendation_entrypoint_command",
        lambda: 'if [ "$OTEL_PLACEMENT_ENABLED" = "false" ]; then exec python x.py; fi',
    )
    with pytest.raises(runtime.GateError, match="does not match the exported constant"):
        runtime.posture_catalog()


def test_cell_contracts_keep_cost_and_fault_windows_separate(tmp_path: Path, bindings):
    package = _package(tmp_path, bindings)
    contracts = [runtime.build_cell_contract(package, cell) for cell in bindings.cells]
    assert len(contracts) == 36
    assert [row["runId"] for row in contracts] == list(bindings.run_ids)
    cost = [row for row in contracts if row["window"]["kind"] == "cost"]
    effect = [row for row in contracts if row["window"]["kind"] == "effect"]
    assert len(cost) == 12 and len(effect) == 24
    # Fault parameters come from the descriptor's faultDesign (declared defaults).
    assert {(row["fault"]["scenario"], row["fault"]["service"], row["fault"]["action"]) for row in effect} == {
        ("fraud-pause", "frauddetectionservice", "pause"), ("frontend-pause", "frontend", "pause"),
    }
    assert {(row["fault"]["onsetSeconds"], row["fault"]["holdSeconds"]) for row in effect} == {(45, 15)}
    # Exactly one cell gates the campaign: the first no-fault full cell, before every fault cell.
    gates = [index for index, row in enumerate(contracts) if row["workloadPathCheck"]["gatesCampaign"]]
    assert len(gates) == 1 and contracts[gates[0]]["runKey"]["posture"] == "full"
    assert contracts[gates[0]]["runKey"]["regime"] == "no-fault-cost"
    assert gates[0] < min(index for index, row in enumerate(contracts) if row["fault"]["scenario"] is not None)
    assert all(row["workload"]["urlPath"] == "/api/checkout?currencyCode=USD" for row in contracts)
    assert all("resources.json" in row["requiredArtifacts"] and "intervention.json" not in row["requiredArtifacts"] for row in cost)
    assert all("intervention.json" in row["requiredArtifacts"] and "effect-resources.json" in row["requiredArtifacts"] and "resources.json" not in row["requiredArtifacts"] for row in effect)
    assert all(row["workload"]["offeredRequests"] == 600 for row in contracts)
    assert all(row["measurement"]["applicationCpu"] == "docker-engine-cumulative-nanoseconds" for row in contracts)
    assert all(row["promotionAuthorized"] is False for row in contracts)


@pytest.mark.parametrize("plant", ("retry", "reorder", "stale", "short-window", "promote"))
def test_gate_run_defects_fail_before_transport(tmp_path: Path, bindings, plant):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    readiness = _readiness(bindings, plan, gate_setup, receipt)
    run = _gate_run(plan, readiness)
    if plant == "retry": run["binding"]["retryAllowed"] = True
    elif plant == "reorder": run["binding"]["authorizedRunIds"][:2] = reversed(run["binding"]["authorizedRunIds"][:2])
    elif plant == "stale": run["approvedAt"] = (NOW - timedelta(minutes=16)).isoformat().replace("+00:00", "Z")
    elif plant == "short-window":
        run["binding"]["authorizationDeadline"] = (NOW + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        run["typedApproval"] = runtime.expected_gate_run_text(run["binding"])
    else: run["promotionAuthorized"] = True
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    readiness_sha = runtime.validate_readiness(readiness, checked, plan_sha, now=NOW)
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_run(run, checked, plan_sha, readiness, readiness_sha, now=NOW)


def test_execution_package_preserves_order_target_lease_ports_and_no_retry(tmp_path: Path, bindings):
    package = _package(tmp_path, bindings)
    document = runtime.execution_package(package)
    assert document["runCount"] == 36
    assert document["target"]["transportUser"] == "root"
    assert document["target"]["executionIdentity"] == {"user": "stig", "uid": 1016, "gid": 1016, "supplementalGids": [998]}
    assert [cell["runId"] for cell in document["cells"]] == list(bindings.run_ids)
    assert document["exclusiveLeasePath"].endswith(".srv6-runtime.lock")
    assert document["cells"][0]["compose"]["ports"]["frontend"] == 18080
    assert all(cell["attemptPolicy"]["retryAllowed"] is False for cell in document["cells"])
    assert document["promotionAuthorized"] is False
    cells, root, lease, project, deadline = remote.validate_package(
        document, clock=lambda: NOW,
    )
    assert [cell["runId"] for cell in cells] == document["authorizedRunIds"]
    assert str(root) == document["remoteArtifactRoot"]
    assert str(lease) == document["exclusiveLeasePath"]
    assert project == document["composeProject"]
    assert deadline.tzinfo == timezone.utc


@pytest.mark.parametrize("plant", ("reorder", "path-escape", "retry", "self-promote"))
def test_remote_replay_rejects_tampered_execution_package(tmp_path: Path, bindings, plant):
    document = runtime.execution_package(_package(tmp_path, bindings))
    if plant == "reorder":
        document["cells"][:2] = reversed(document["cells"][:2])
    elif plant == "path-escape":
        document["cells"][0]["remoteArtifactRoot"] = "/tmp/escaped"
    elif plant == "retry":
        document["cells"][0]["attemptPolicy"]["retryAllowed"] = True
    else:
        document["cells"][0]["promotionAuthorized"] = True
    with pytest.raises(remote.RuntimeFailure):
        remote.validate_package(document)


def test_missing_or_invalid_gate_never_calls_transport_runner(tmp_path: Path, bindings):
    package = _package(tmp_path, bindings)
    stale = copy.deepcopy(package.gate_run)
    stale["approvedAt"] = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat().replace("+00:00", "Z")
    stale_package = runtime.RuntimePackage(**{**package.__dict__, "gate_run": stale})
    calls = []

    def runner(argv, *, input=None):
        calls.append((argv, input))
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.ComposeSshAdapter(runner).launch(stale_package, tmp_path / "never")
    assert calls == []
    assert not (tmp_path / "never").exists()


def test_workload_identity_is_deterministic_and_original_trace_is_injected():
    workload = _load("otel_candidate_workload_tests", "modules/otel-demo/workload.py")
    first = workload.request_identity("run-a", 7)
    assert first == workload.request_identity("run-a", 7)
    assert first != workload.request_identity("run-a", 8)
    token, trace_id = first
    assert token.startswith("opq-") and len(trace_id) == 32


def test_candidate_cell_refuses_before_any_fault_or_artifact_mutation(
    tmp_path: Path, bindings
):
    package = _package(tmp_path, bindings)
    source_cell = next(
        cell
        for cell in package.bindings.cells
        if cell["runKey"]["regime"] == "frontend-pause-effect"
    )
    cell = runtime.build_cell_contract(package, source_cell)
    artifact_root = tmp_path / "failed-fault-cell"
    cell["remoteArtifactRoot"] = str(artifact_root)
    cell["remoteSourceRoot"] = str(tmp_path / "materialized-source")

    with pytest.raises(remote.RuntimeFailure, match="UNSUPPORTED"):
        remote.run_cell(cell, datetime.now(timezone.utc) + timedelta(hours=1))
    assert not artifact_root.exists()


def test_target_producer_refuses_before_observer_or_target_access(bindings):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)

    called = False

    def observed(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("target observer must be unreachable")

    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.produce_target_readiness(
            plan, gate_setup, receipt, clock=lambda: READINESS_NOW,
            target_observer=observed,
        )
    assert called is False


def test_all_target_entrypoints_parse_under_pinned_python39() -> None:
    target_files = (
        "modules/otel-demo/execution/candidate_setup.py",
        "modules/otel-demo/execution/candidate_runtime.py",
        "modules/otel-demo/execution/candidate_remote.py",
        "modules/otel-demo/execution/candidate_pilot.py",
        "modules/otel-demo/materialize.py",
        "modules/otel-demo/workload.py",
        "modules/otel-demo/validation/candidate_terminal.py",
        "modules/otel-demo/validation/candidate_unsupported.py",
    )
    for relative in target_files:
        ast.parse(
            (ROOT / relative).read_text(encoding="utf-8"),
            filename=relative,
            feature_version=(3, 9),
        )


def test_target_producer_denial_precedes_planted_post_setup_result(bindings):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)

    def planted(checked_plan, checked_receipt, receipt_sha, *, observed_at):
        rows = _observations(checked_plan, checked_receipt, receipt_sha)
        for seam in ("target-identity", "target-root-and-host-isolation"):
            rows[seam]["observedAt"] = observed_at
        rows["project-port-lease-isolation"]["candidateResultEntries"] = ["planted-cell"]
        return {
            seam: rows[seam] for seam in runtime.TARGET_OBSERVATION_SEAMS
        }

    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.produce_target_readiness(
            plan, gate_setup, receipt, clock=lambda: READINESS_NOW,
            target_observer=planted,
        )


def test_setup_gate_freshness_is_consumed_once_then_runtime_uses_fresh_readiness(
    tmp_path: Path, bindings
):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    later = NOW + timedelta(minutes=20)
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    _, setup_sha = runtime.validate_gate_setup_reference(gate_setup, checked, plan_sha)
    checked_receipt, receipt_sha = runtime.validate_setup_receipt(
        receipt, checked, plan_sha, setup_sha
    )
    observations = _observations(checked, checked_receipt, receipt_sha)
    observed_at = (later - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    for seam in ("target-identity", "target-root-and-host-isolation"):
        observations[seam]["observedAt"] = observed_at
    readiness = runtime.make_readiness(
        checked, plan_sha, setup_sha, checked_receipt, receipt_sha,
        observations, observed_at=observed_at,
    )
    readiness_sha = runtime.canonical_sha256(readiness)
    run_binding = runtime.run_binding(
        checked, plan_sha, readiness, readiness_sha,
        not_before=(later - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        authorization_deadline=(later + timedelta(hours=11)).isoformat().replace("+00:00", "Z"),
    )
    gate_run = {
        "schemaVersion": 1, "kind": runtime.RUN_KIND, "gate": "GATE-RUN",
        "decision": "authorize-one-shot-exact-run",
        "typedApproval": runtime.expected_gate_run_text(run_binding),
        "approvedBy": "external-human-reviewer",
        "approvedAt": (later - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "binding": run_binding, "promotionAuthorized": False,
    }
    for name, value in (
        ("plan.json", plan), ("setup.json", gate_setup),
        ("setup-receipt.json", receipt), ("readiness.json", readiness),
        ("run.json", gate_run),
    ):
        _write(tmp_path / name, value)
    package = runtime.authorize_from_files(
        bindings.root, tmp_path / "plan.json", tmp_path / "setup.json",
        tmp_path / "setup-receipt.json", tmp_path / "readiness.json",
        tmp_path / "run.json", clock=lambda: later,
    )
    assert package.gate_setup_sha256 == setup_sha
    assert later - runtime._timestamp(gate_setup["approvedAt"], "test") > timedelta(minutes=15)


def test_setup_consumption_timestamp_defect_fails(bindings):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    receipt["startedAt"] = (
        runtime._timestamp(gate_setup["approvedAt"], "test")
        + timedelta(minutes=16)
    ).isoformat().replace("+00:00", "Z")
    receipt["completedAt"] = receipt["startedAt"]
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    _, setup_sha = runtime.validate_gate_setup_reference(gate_setup, checked, plan_sha)
    checked_receipt, _ = runtime.validate_setup_receipt(
        receipt, checked, plan_sha, setup_sha
    )
    with pytest.raises(runtime.GateError, match="not fresh when setup began"):
        runtime.validate_consumed_gate_setup(gate_setup, checked_receipt)


def test_readiness_freshness_and_gate_run_order_are_watched(bindings):
    plan = _gate_plan(bindings)
    checked, plan_sha = runtime.validate_gate_plan(plan, bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    readiness = _readiness(bindings, plan, gate_setup, receipt)
    with pytest.raises(runtime.GateError, match="readiness is not fresh"):
        runtime.validate_readiness(
            readiness, checked, plan_sha,
            now=READINESS_NOW + timedelta(minutes=16),
        )
    run = _gate_run(plan, readiness)
    run["approvedAt"] = (READINESS_NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    with pytest.raises(runtime.GateError, match="does not follow target readiness"):
        runtime.validate_gate_run(
            run, checked, plan_sha, readiness,
            runtime.canonical_sha256(readiness), now=NOW,
        )


def test_capture_readiness_invokes_exact_installed_zero_cell_producer(
    tmp_path: Path, bindings
):
    plan = _gate_plan(bindings)
    gate_setup = _gate_setup(bindings, plan)
    receipt = _setup_receipt(bindings, plan, gate_setup)
    readiness = _readiness(bindings, plan, gate_setup, receipt)
    controls = tmp_path / "controls"
    controls.mkdir()
    for name, value in (
        ("plan.json", plan), ("setup.json", gate_setup),
        ("setup-receipt.json", receipt),
    ):
        _write(controls / name, value)
    request = runtime.authorize_readiness_from_files(
        bindings.root, controls / "plan.json", controls / "setup.json",
        controls / "setup-receipt.json",
    )
    calls = []

    def runner(argv, *, input=None):
        calls.append(list(argv))
        if argv[0] == "ssh" and "sha256sum" in argv:
            digest = plan["binding"]["controllerDigests"]["runtime-admission"]
            return subprocess.CompletedProcess(
                argv, 0, f"{digest}  producer\n".encode(), b""
            )
        if argv[0] == "scp" and str(argv[-2]).endswith("/.controller/readiness.json"):
            _write(Path(argv[-1]), readiness)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.ComposeSshAdapter(runner).capture_readiness(
            request, controls, clock=lambda: NOW
        )
    assert calls == []
    assert not (controls / "target-readiness-gate-plan.json").exists()
    assert not (controls / "readiness.json").exists()


def test_launch_uses_isolated_pinned_python_on_target(
    tmp_path: Path, bindings, monkeypatch,
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    package = _package(package_root, bindings)
    calls = []

    def runner(argv, *, input=None):
        calls.append(list(argv))
        if "sha256sum" in argv:
            digest = package.gate_plan["binding"]["controllerDigests"][
                "remote-compose-controller"
            ]
            return subprocess.CompletedProcess(argv, 0, f"{digest}  controller\n".encode(), b"")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(runtime, "validate_readiness", lambda *_args, **_kwargs: "a" * 64)
    monkeypatch.setattr(runtime, "validate_gate_run", lambda *_args, **_kwargs: "b" * 64)
    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.ComposeSshAdapter(runner).launch(package, tmp_path / "launch")
    assert calls == []
    assert not (tmp_path / "launch").exists()


@pytest.mark.parametrize("completion", ("remote-terminal.json", "campaign-abort.json"))
def test_status_discovers_retained_completion_after_collected_unit_vanishes(
    tmp_path: Path, bindings, completion
):
    package = _package(tmp_path, bindings)
    calls = []

    def runner(argv, *, input=None):
        calls.append(list(argv))
        if "systemctl" in argv:
            return subprocess.CompletedProcess(argv, 1, b"", b"unit not found")
        candidate = argv[-1].rsplit("/", 1)[-1]
        return subprocess.CompletedProcess(
            argv, 0 if candidate == completion else 1, b"", b""
        )

    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.ComposeSshAdapter(runner).status(package)
    assert calls == []


def test_read_only_replay_survives_expired_run_gate_but_cannot_reauthorize_execution(
    tmp_path: Path, bindings
):
    _package(tmp_path, bindings)
    later = NOW + timedelta(hours=6)
    paths = (
        bindings.root, tmp_path / "plan.json", tmp_path / "setup.json",
        tmp_path / "setup-receipt.json", tmp_path / "readiness.json",
        tmp_path / "run.json",
    )
    with pytest.raises(runtime.GateError, match="not fresh"):
        runtime.authorize_from_files(*paths, clock=lambda: later)
    replayed = runtime.replay_runtime_from_files(*paths, clock=lambda: later)
    assert replayed.validated_at == later
    assert replayed.gate_run_sha256 == runtime.canonical_sha256(replayed.gate_run)


def test_remote_early_failure_retains_abort_artifact(tmp_path: Path, monkeypatch):
    campaign_id = "otelcand-20260830-a"
    root = tmp_path / campaign_id
    (root / ".controller").mkdir(parents=True)
    monkeypatch.setattr(remote, "EXPECTED_ARTIFACT_PARENT", str(tmp_path))
    document = {
        "campaignId": campaign_id,
        "target": copy.deepcopy(remote.EXPECTED_TARGET),
        "composeProject": "otel_candidate_v4_test",
        "remoteArtifactRoot": str(root),
        "systemdUnit": "otel_candidate_v4_test.service",
    }
    validated = ([], root, tmp_path / "lease", "project", NOW)
    monkeypatch.setattr(remote, "validate_package", lambda *_: validated)

    def fail(_document):
        raise remote.RuntimeFailure("planted early controller failure")

    monkeypatch.setattr(remote, "_run_campaign", fail)
    with pytest.raises(remote.RuntimeFailure, match="UNSUPPORTED"):
        remote.run_campaign(document)
    assert not (root / "campaign-abort.json").exists()


def test_remote_package_validation_failure_retains_abort_artifact(
    tmp_path: Path, monkeypatch,
):
    campaign_id = "otelcand-20260830-a"
    root = tmp_path / campaign_id
    (root / ".controller").mkdir(parents=True)
    monkeypatch.setattr(remote, "EXPECTED_ARTIFACT_PARENT", str(tmp_path))
    document = {
        "campaignId": campaign_id,
        "composeProject": "otel_candidate_v4_test",
        "remoteArtifactRoot": str(root),
        "systemdUnit": "otel_candidate_v4_test.service",
    }
    with pytest.raises(remote.RuntimeFailure, match="UNSUPPORTED"):
        remote.run_campaign(document)
    assert not (root / "campaign-abort.json").exists()


def test_remote_controller_rechecks_full_budget_at_actual_start(
    tmp_path: Path, bindings,
):
    package_root = tmp_path / "package"
    package_root.mkdir()
    package = _package(package_root, bindings)
    document = runtime.execution_package(package)
    assert document["cleanupReserveSeconds"] == 600
    assert document["minimumRemainingAtFirstMutationSeconds"] == 36_000
    deadline = datetime.fromisoformat(
        document["authorizationDeadline"].removesuffix("Z") + "+00:00"
    )
    with pytest.raises(remote.RuntimeFailure, match="too little time"):
        remote.validate_package(
            document,
            clock=lambda: deadline - timedelta(seconds=21_599),
        )


@pytest.mark.parametrize(
    "retained_kind,expected_state",
    (("abort", "retained-abort"), ("partial", "partial-retained")),
)
def test_fetch_retains_abort_or_partial_without_false_terminal_validation(
    tmp_path: Path, bindings, retained_kind, expected_state
):
    package_root = tmp_path / "package"
    package_root.mkdir()
    package = _package(package_root, bindings)
    staging = tmp_path / "fetch"

    def runner(argv, *, input=None):
        retained = Path(argv[-1])
        retained.mkdir(parents=True)
        if retained_kind == "abort":
            _write(retained / "campaign-abort.json", {
                "schemaVersion": 1,
                "kind": "otel-demo-candidate-campaign-abort-v1",
                "campaignId": package.gate_plan["binding"]["campaignId"],
                "target": package.gate_plan["binding"]["target"],
                "systemdUnit": runtime.execution_package(package)["systemdUnit"],
                "errorType": "RuntimeFailure", "error": "planted abort",
                "completedAt": NOW.isoformat().replace("+00:00", "Z"),
                "promotionAuthorized": False,
            })
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.ComposeSshAdapter(runner).fetch(package, staging)
    assert not staging.exists()


def test_exact_unsupported_evidence_binds_frozen_design_target_and_all_18_cells():
    evidence = runtime.unsupported_evidence()
    assert (evidence["executionDisposition"], evidence["empiricalResultState"]) == (
        "unsupported", "UNSUPPORTED",
    )
    assert evidence["frozenDesign"]["cellCount"] == 18
    assert evidence["frozenDesign"]["postures"] == ["none", "selected", "full"]
    assert evidence["targetBinding"] == {
        "allocationPath": "modules/otel-demo/execution/candidate-target-allocation.json",
        "allocationByteSha256": runtime.file_sha256(runtime.TARGET_ALLOCATION),
        "preservedAsProvenanceOnly": True,
        "runtimeAuthority": False,
        "externalMutationAllowed": False,
    }
    ledger = evidence["cellLedger"]
    assert len(ledger) == len({row["runId"] for row in ledger}) == 18
    assert {row["runKey"]["posture"] for row in ledger} == {
        "none", "selected", "full",
    }
    assert all(row["empiricalResultState"] == "UNSUPPORTED" for row in ledger)
    assert all(row["externalAttempt"] is False for row in ledger)
    assert all(row["numericResults"] is None for row in ledger)
    assert evidence["comparativePolicy"]["fullOnlyExecutionAllowed"] is False
    assert set(evidence["gateStates"].values()) == {"not-requested"}
    assert set(evidence["permissions"].values()) == {False}
    # Re-scoped: the ledger is v1's terminal result and names v2 as its successor.
    assert evidence["studyEpoch"] == runtime.UNSUPPORTED_STUDY_EPOCH == "otel-demo-candidate-pilot-v1"
    assert evidence["changeId"] == runtime.UNSUPPORTED_CHANGE_ID
    assert evidence["frozenDesign"]["descriptorPath"] == "pipelines/campaigns/otel-demo-candidate-pilot-v1.json"
    assert evidence["frozenDesign"]["descriptorByteSha256"] == "fb43212b38ce0cd53538ee654b825574ee415dc4624fc2cc32bcc6d82504cbaa"
    assert evidence["scope"]["appliesToStudyEpochs"] == ["otel-demo-candidate-pilot-v1"]
    # v3 does not rewrite v1's ledger: its recorded successor stays v2.
    assert evidence["scope"]["supersededBy"] == {
        "studyEpoch": "otel-demo-candidate-pilot-v2", "changeId": "admit-otel-demo-candidate-pilot-v2",
        "descriptorPath": "pipelines/campaigns/otel-demo-candidate-pilot-v2.json",
    }
    assert runtime.UNSUPPORTED_SUCCESSOR_EPOCH == "otel-demo-candidate-pilot-v2"
    assert all(row["runKey"]["studyEpoch"] == "otel-demo-candidate-pilot-v1" for row in ledger)


@pytest.mark.parametrize(
    "plant",
    ("full-only", "cell-state", "attempt", "run-id", "target", "gate", "scope-epoch", "scope-successor"),
)
def test_unsupported_evidence_checker_is_watched_failing_on_planted_defects(plant):
    evidence = runtime.unsupported_evidence()
    if plant == "scope-epoch":
        evidence["scope"]["appliesToStudyEpochs"] = ["otel-demo-candidate-pilot-v1", "otel-demo-candidate-pilot-v2"]
    elif plant == "scope-successor":
        evidence["scope"]["supersededBy"]["studyEpoch"] = "otel-demo-candidate-pilot-v3"
    elif plant == "full-only":
        evidence["comparativePolicy"]["fullOnlyExecutionAllowed"] = True
    elif plant == "cell-state":
        evidence["cellLedger"][0]["empiricalResultState"] = "NOT RUN"
    elif plant == "attempt":
        evidence["cellLedger"][0]["externalAttempt"] = True
    elif plant == "run-id":
        evidence["cellLedger"][0]["runId"] = "0" * 24
    elif plant == "target":
        evidence["targetBinding"]["runtimeAuthority"] = True
    else:
        evidence["gateStates"]["GATE-RUN"] = "pending"
    with pytest.raises(runtime.GateError):
        runtime.validate_unsupported_evidence(evidence)


def test_all_transport_and_target_mutation_surfaces_refuse_before_side_effects(
    tmp_path: Path,
):
    calls = []

    def runner(argv, *, input=None):
        calls.append((argv, input))
        raise AssertionError("external runner must be unreachable")

    adapter = runtime.ComposeSshAdapter(runner)
    staging = tmp_path / "must-not-exist"
    operations = (
        lambda: adapter.setup(object(), Path("missing-a"), Path("missing-b"), staging),
        lambda: adapter.capture_readiness(object(), staging),
        lambda: adapter.launch(object(), staging),
        lambda: adapter.status(object()),
        lambda: adapter.fetch(object(), staging),
        lambda: runtime.target_observations({}, {}, "0" * 64, observed_at="never"),
        lambda: runtime.produce_target_readiness({}, {}, {}),
        lambda: runtime.write_target_readiness(staging, {}),
    )
    for operation in operations:
        with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
            operation()
    assert calls == []
    assert not staging.exists()


def test_copied_target_controllers_and_clis_refuse_before_package_or_mutation(
    tmp_path: Path,
):
    absent = tmp_path / "absent-package.json"
    with pytest.raises(setup.SetupFailure, match="UNSUPPORTED"):
        setup.install({}, tmp_path / "setup")
    with pytest.raises(setup.SetupFailure, match="UNSUPPORTED"):
        setup.main(["install", "--package", str(absent)])
    for operation in (
        lambda: remote.run_cell({}, datetime.now(timezone.utc) + timedelta(hours=1)),
        lambda: remote.run_campaign({}),
        lambda: remote.cleanup({}),
        lambda: remote.main(["run", "--package", str(absent)]),
    ):
        with pytest.raises(remote.RuntimeFailure, match="UNSUPPORTED"):
            operation()
    with pytest.raises(runtime.GateError, match="UNSUPPORTED"):
        runtime.main([
            "target-readiness",
            "--gate-plan", str(absent),
            "--gate-setup", str(absent),
            "--setup-receipt", str(absent),
            "--output", str(tmp_path / "readiness.json"),
        ])
    assert not absent.exists()
    assert not (tmp_path / "setup").exists()
    assert not (tmp_path / "readiness.json").exists()


# ---------------------------------------------------------------------------
# 2026-09-18, instance nine: the launch argv's host-specific spellings.
# These tests EXECUTE the resolution and verification helpers rather than
# reading the source, because a guard that exercises a different code path
# than the thing it guards is not a guard.
# ---------------------------------------------------------------------------

def _fake_target(*, runuser="/sbin/runuser", unit_states=("active",), gid_lines=None):
    """A fake fb14srv6: runuser in /sbin, named groups, a unit that reaches a state."""
    paths = {"runuser": runuser, "flock": "/usr/bin/flock", "python3": "/usr/bin/python3"}
    lines = gid_lines if gid_lines is not None else {
        "1016": "stig:x:1016:", "998": "docker:x:998:stig",
    }
    seen = []
    states = list(unit_states)

    def runner(argv, *, input=None):
        seen.append(list(argv))
        remote_words = argv[-1].split() if argv[0] == "ssh" else list(argv)
        if remote_words[:2] == ["command", "-v"]:
            resolved = paths.get(remote_words[2])
            if resolved is None:
                return subprocess.CompletedProcess(argv, 1, b"", b"")
            return subprocess.CompletedProcess(argv, 0, f"{resolved}\n".encode(), b"")
        if remote_words[0] == "test" and remote_words[1] == "-x":
            present = remote_words[2] in set(paths.values())
            return subprocess.CompletedProcess(argv, 0 if present else 1, b"", b"")
        if remote_words[:2] == ["getent", "group"]:
            line = lines.get(remote_words[2])
            if line is None:
                return subprocess.CompletedProcess(argv, 2, b"", b"")
            return subprocess.CompletedProcess(argv, 0, f"{line}\n".encode(), b"")
        if remote_words[:2] == ["systemctl", "show"]:
            state = states.pop(0) if states else "inactive"
            load = "loaded" if state in {"active", "activating", "failed"} else "not-found"
            body = (
                f"LoadState={load}\nActiveState={state}\nSubState=running\n"
                f"Result=success\nExecMainStatus=0\nExecMainPID=4242\n"
            )
            return subprocess.CompletedProcess(argv, 0, body.encode(), b"")
        if remote_words[0] == "journalctl":
            return subprocess.CompletedProcess(argv, 0, b"planted journal tail\n", b"")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    return runner, seen


def test_launch_tokens_resolve_on_the_target_not_from_a_hardcoded_path():
    runner, seen = _fake_target()
    adapter = runtime.ComposeSshAdapter(runner)
    tools, groups, receipts = adapter._resolve_launch_tokens(
        "root@fb14srv6", runtime.LAUNCH_ARGV_BINARIES, runtime.LAUNCH_ARGV_GIDS,
    )
    assert tools["runuser"] == "/sbin/runuser"
    assert groups == {1016: "stig", 998: "docker"}
    # every resolved path was proven executable at exactly the resolved spelling
    proven = {a[-1].split()[-1] for a in seen if a[-1].startswith("test -x")}
    assert proven == set(tools.values())
    assert len(receipts) == 2 * len(runtime.LAUNCH_ARGV_BINARIES) + len(runtime.LAUNCH_ARGV_GIDS)


def test_launch_token_resolution_fails_closed_when_a_binary_is_absent():
    runner, _ = _fake_target(runuser=None)
    adapter = runtime.ComposeSshAdapter(runner)
    with pytest.raises(runtime.GateError, match="does not resolve on the target"):
        adapter._resolve_launch_tokens("root@fb14srv6", ("runuser",), ())


def test_launch_token_resolution_fails_closed_when_a_gid_has_no_group():
    runner, _ = _fake_target(gid_lines={"1016": "stig:x:1016:"})
    adapter = runtime.ComposeSshAdapter(runner)
    with pytest.raises(runtime.GateError, match="names no group on the target"):
        adapter._resolve_launch_tokens("root@fb14srv6", (), (1016, 998))


def test_unit_verification_accepts_an_active_unit_and_reports_its_state():
    runner, _ = _fake_target(unit_states=("activating", "active"))
    adapter = runtime.ComposeSshAdapter(runner)
    fields, receipts = adapter._verify_unit_active("root@fb14srv6", "otel.service")
    assert fields["ActiveState"] == "active" and fields["LoadState"] == "loaded"
    assert len(receipts) == 2


def test_unit_verification_refuses_a_unit_that_was_accepted_and_died(monkeypatch):
    """The 2026-09-17 failure exactly: systemd-run returned 0, --collect then
    unloaded the dead unit, and the launch was reported as successful."""
    monkeypatch.setattr(runtime.time, "sleep", lambda _seconds: None)
    runner, _ = _fake_target(unit_states=("inactive",))
    adapter = runtime.ComposeSshAdapter(runner)
    with pytest.raises(runtime.GateError, match="accepted the unit but it is not running"):
        adapter._verify_unit_active("root@fb14srv6", "otel.service")


def test_docker_gid_is_one_per_host_fact_written_down_consistently() -> None:
    """Every OTel site holding fb14srv6's docker gid agrees on 998.

    The docker gid reads like one fact and is not: Debian allocates the docker
    group from the descending system-GID range at install time, so fb14srv5 is
    999 while fb14srv4 and fb14srv6 are 998. Three SUTs each hardcode "the"
    docker gid and two of the three values differ; that is three correct
    per-host answers, not a contradiction, and research/host-topology.json now
    records it per host with provenance. What was missing is anything that
    makes a WITHIN-SUT drift fail, which is the shape that leaves a sixth site
    open after a five-site sweep. This is that enumeration, kept executable.

    fb14srv6 = 998 is observed, not merely declared: the retained setup receipt
    .local/candidate-v4/otel-demo/gates/archived-install-staging-20260918T131608Z/
    setup-receipt.json carries dockerGid = 998 from grp.getgrnam("docker") run
    on the host.
    """
    gid = setup.DOCKER_GID
    assert gid == 998
    # The launch argv resolves this gid's SPELLING on the target and re-asserts
    # the number against getent's third field; the number itself stays here.
    assert gid in runtime.LAUNCH_ARGV_GIDS
    assert runtime.LAUNCH_ARGV_GIDS == (setup.EXECUTION_GID, gid)
    assert pilot.SRV6_TARGET["dockerGid"] == gid
    assert pilot.SRV6_TARGET["executionUid"] == setup.EXECUTION_UID
    assert pilot.SRV6_TARGET["executionGid"] == setup.EXECUTION_GID
    allocation = json.loads(
        (ROOT / "modules/otel-demo/execution/candidate-target-allocation.json").read_text(
            encoding="utf-8",
        )
    )
    assert allocation["docker"]["expectedGid"] == gid
    identity = allocation["executionIdentities"][0]
    assert identity["supplementalGids"] == [gid]
    assert (identity["user"], identity["uid"], identity["gid"]) == (
        setup.EXECUTION_USER, setup.EXECUTION_UID, setup.EXECUTION_GID,
    )
    assert remote.EXPECTED_TARGET["executionIdentity"] == {
        "user": setup.EXECUTION_USER, "uid": setup.EXECUTION_UID,
        "gid": setup.EXECUTION_GID, "supplementalGids": [gid],
    }
    # No site in the module may hold a DIFFERENT docker gid. 999 is fb14srv5's
    # and must never appear here; the reverse mistake is what this catches.
    for rel in (
        "modules/otel-demo/execution/candidate_runtime.py",
        "modules/otel-demo/execution/candidate_setup.py",
        "modules/otel-demo/execution/candidate_remote.py",
        "modules/otel-demo/execution/candidate_pilot.py",
        "modules/otel-demo/execution/candidate-target-allocation.json",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            assert "999" not in line, (rel, line)


# --- OTel run-2 fix 1a.5: the attempt is a launcher parameter, not a literal ---


@pytest.fixture
def attempt_two_bindings(tmp_path: Path):
    campaign = tmp_path / "compiled-attempt-2"
    pilot.materialize(campaign, attempt=2)
    return runtime.inspect_compiled_plan(campaign)


def test_attempt_two_flows_from_the_plan_into_every_gate_sentence_and_cell(tmp_path: Path, attempt_two_bindings, bindings):
    assert (bindings.attempt, attempt_two_bindings.attempt) == (1, 2)
    # New identities, same design: run IDs disjoint from attempt 1, descriptor unchanged.
    assert not set(bindings.run_ids) & set(attempt_two_bindings.run_ids)
    assert len(set(attempt_two_bindings.run_ids)) == 36
    assert attempt_two_bindings.descriptor_sha256 == bindings.descriptor_sha256
    assert attempt_two_bindings.plan_sha256 != bindings.plan_sha256
    plan = _gate_plan(attempt_two_bindings)
    assert plan["binding"]["attempt"] == 2
    assert " attempt=2 " in plan["typedApproval"] and "attempt=1" not in plan["typedApproval"]
    package = _package(tmp_path, attempt_two_bindings)
    assert package.gate_run["binding"]["attempt"] == 2
    assert " attempt=2 " in package.gate_run["typedApproval"]
    document = runtime.execution_package(package)
    assert {cell["runKey"]["attempt"] for cell in document["cells"]} == {2}
    assert {cell["attemptPolicy"]["attempt"] for cell in document["cells"]} == {2}
    cells, *_ = remote.validate_package(document, clock=lambda: NOW)
    assert [cell["runId"] for cell in cells] == list(attempt_two_bindings.run_ids)


@pytest.mark.parametrize("plant", ("mixed-run-key", "policy-disagrees", "zero", "boolean"))
def test_remote_refuses_an_execution_package_without_one_positive_attempt(tmp_path: Path, attempt_two_bindings, plant):
    document = runtime.execution_package(_package(tmp_path, attempt_two_bindings))
    if plant == "mixed-run-key":
        document["cells"][3]["runKey"]["attempt"] = 3
    elif plant == "policy-disagrees":
        document["cells"][0]["attemptPolicy"]["attempt"] = 1
    elif plant == "zero":
        for cell in document["cells"]:
            cell["runKey"]["attempt"] = cell["attemptPolicy"]["attempt"] = 0
    else:
        for cell in document["cells"]:
            cell["runKey"]["attempt"] = cell["attemptPolicy"]["attempt"] = True
    with pytest.raises(remote.RuntimeFailure, match="attempt"):
        remote.validate_package(document, clock=lambda: NOW)


def test_a_gate_plan_typed_for_attempt_one_does_not_authorize_attempt_two(attempt_two_bindings, bindings):
    stale = _gate_plan(bindings)
    with pytest.raises(runtime.GateError):
        runtime.validate_gate_plan(stale, attempt_two_bindings)


# --- v3 (2026-09-30): the async posture's closure is a pinned literal ---


@pytest.mark.parametrize(
    "plant,diagnostic",
    (
        ("async-adds-a-service-outside-its-closure", "async posture closure differs"),
        ("async-drops-an-order-path-service", "async posture closure differs"),
        ("async-realization-not-derived", "async posture realization differs from the per-service classification"),
        ("posture-set-without-async", "posture catalog identity differs"),
        ("postures-out-of-lattice-order", "posture catalog identity differs"),
    ),
)
def test_async_posture_with_a_service_outside_its_closure_is_refused(tmp_path: Path, monkeypatch, plant, diagnostic):
    """Planted defects against the v3 catalog: posture_catalog() must refuse an
    async closure that is not exactly selected + accountingservice,
    checkoutservice, frauddetectionservice, kafka, and a catalog whose posture
    set or order is not none < selected < async < full."""
    catalog = json.loads((ROOT / runtime.POSTURE_CATALOG).read_text(encoding="utf-8"))
    assert catalog["postures"]["async"]["activeApplicationServices"] == list(runtime.ASYNC_CLOSURE)
    planted = copy.deepcopy(catalog)
    row = planted["postures"]["async"]
    if plant == "async-adds-a-service-outside-its-closure":
        for key in ("activeApplicationServices", "sourceInstrumentationLoadedServices"):
            row[key] = sorted(row[key] + ["adservice"])
    elif plant == "async-drops-an-order-path-service":
        for key in ("activeApplicationServices", "sourceInstrumentationLoadedServices"):
            row[key] = [service for service in row[key] if service != "kafka"]
    elif plant == "async-realization-not-derived":
        planted["postureRealization"]["async"]["notLoadedServices"].append("kafka")
    elif plant == "posture-set-without-async":
        planted["postures"].pop("async")
    else:
        planted["postures"] = {key: planted["postures"][key] for key in ("none", "async", "selected", "full")}
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(planted), encoding="utf-8")
    monkeypatch.setattr(runtime, "POSTURE_CATALOG", path)
    with pytest.raises(runtime.GateError, match=diagnostic):
        runtime.posture_catalog()


# --- offpath target-side code, executed (not monkeypatched away) ---------------


def _offpath_workload() -> dict:
    return {
        "urlPath": "/api/checkout?currencyCode=USD", "cartPath": "/api/cart",
        "productId": "OLJCESPC7Z", "stepTimeoutSeconds": 15,
        "requestsPerSecond": 1, "concurrency": 32,
    }


@pytest.mark.parametrize("cart_status, order_status", ((200, 200), (503, None), (200, 500)))
def test_journey_runs_cart_then_order_with_one_trace_and_one_witness_token(monkeypatch, cart_status, order_status):
    calls = []

    def fake_post(url, body, headers, timeout):
        calls.append((url, body, dict(headers)))
        status = cart_status if url.endswith("/api/cart") else order_status
        return {"status": status, "bytes": 10, "startedAtEpoch": 1.0, "endedAtEpoch": 1.1,
                "error": None if status == 200 else f"HTTP {status}"}

    monkeypatch.setattr(remote, "post_json", fake_post)
    token, trace_id, traceparent = remote.request_identity("run-x", 3)
    row = remote.one_journey("http://127.0.0.1:18080", _offpath_workload(), 0.0, token, trace_id, traceparent)
    assert calls[0][0] == "http://127.0.0.1:18080/api/cart"
    assert calls[0][1] == {"item": {"productId": "OLJCESPC7Z", "quantity": 1}, "userId": token}
    # The cart step carries the journey token and the ledger traceparent: the witness.
    assert calls[0][2] == {"traceparent": traceparent, "x-obsplacement-request-token": token}
    if cart_status != 200:
        assert len(calls) == 1 and [step["name"] for step in row["steps"]] == ["add-to-cart"]
        assert row["error"] == "add-to-cart: HTTP 503" and row["status"] == 503
        return
    url, body, headers = calls[1]
    assert url == "http://127.0.0.1:18080/api/checkout?currencyCode=USD"
    assert body["userId"] == token and body["email"] == "larry_sergei@example.com"
    assert headers["x-obsplacement-request-token"] == f"{token}-order"
    version, order_trace, order_span, flags = headers["traceparent"].split("-")
    assert (version, order_trace, flags) == ("00", trace_id, "01") and order_span != traceparent.split("-")[2]
    assert [step["name"] for step in row["steps"]] == ["add-to-cart", "place-order"]
    assert row["status"] == order_status
    assert (row["error"] is None) == (order_status == 200)


@pytest.mark.parametrize(
    "scenario, service, action, route_up, during",
    (
        ("fraud-pause", "frauddetectionservice", "pause", True, {"Running": True, "Paused": True}),
        ("frontend-pause", "frontend", "pause", False, {"Running": True, "Paused": True}),
        ("email-stop", "emailservice", "stop", True, {"Running": False, "Paused": False}),
        # Planted: an entry-point fault whose route stayed up did not manifest.
        ("frontend-pause", "frontend", "pause", True, {"Running": True, "Paused": True}),
        # Planted: a pause that left the container unpaused did not manifest.
        ("fraud-pause", "frauddetectionservice", "pause", True, {"Running": True, "Paused": False}),
    ),
)
def test_inject_fault_receipt_carries_the_detection_window(monkeypatch, scenario, service, action, route_up, during):
    issued = []
    states = iter([{"Running": True, "Paused": False}, during, {"Running": True, "Paused": False}])

    def fake_command(argv, **_):
        issued.append(list(argv))
        if argv[:2] == ["docker", "inspect"]:
            state = next(states)
            payload = {"Image": "sha256:" + "e" * 64, "State": state}
            return subprocess.CompletedProcess(argv, 0, json.dumps([payload]), "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(remote, "command", fake_command)
    monkeypatch.setattr(remote, "container_id", lambda cell, name, env: f"cid-{name}")
    monkeypatch.setattr(remote, "route_available", lambda url, timeout=5.0: route_up)
    monkeypatch.setattr(remote, "wait_ready", lambda *args, **kwargs: None)
    must_fail_route = scenario == "frontend-pause"
    cell = {
        "fault": {"scenario": scenario, "service": service, "action": action,
                  "entryRouteDuringFault": "must-be-unavailable" if must_fail_route else "recorded-not-required",
                  "onsetSeconds": 0, "holdSeconds": 0},
        "workload": _offpath_workload(), "remoteSourceRoot": "/src",
        "compose": {"project": "otel_candidate_v4_x"},
    }
    output: dict = {}
    import time as _time  # noqa: PLC0415
    barrier = _time.monotonic()
    remote.inject_fault(cell, {}, "http://127.0.0.1:18080", barrier, output)
    apply, revert = remote.FAULT_ACTIONS[action]
    compose_verbs = [argv[-2] for argv in issued if argv[:2] == ["docker", "compose"]]
    assert compose_verbs == [apply, revert]
    assert all(argv[-1] == service for argv in issued if argv[:2] == ["docker", "compose"])
    expected_manifest = (
        (during.get("Paused") if action == "pause" else not during.get("Running"))
        and (not route_up if must_fail_route else True)
    )
    assert output["manifested"] is bool(expected_manifest)
    assert output["successful"] is bool(expected_manifest)
    assert output["error"] is None
    assert output["scenario"] == scenario and output["service"] == service
    assert output["duringRouteAvailable"] is route_up
    assert output["barrierMonotonic"] == barrier
    assert abs(output["appliedMonotonic"] - barrier - output["appliedMonotonicOffsetSeconds"]) < 1e-9
    assert (
        output["actualOnsetMonotonicOffsetSeconds"] <= output["appliedMonotonicOffsetSeconds"]
        <= output["revertingMonotonicOffsetSeconds"] <= output["actualOffsetMonotonicOffsetSeconds"]
    )


def test_target_refuses_a_package_whose_path_check_does_not_precede_every_fault(tmp_path: Path, bindings):
    document = runtime.execution_package(_package(tmp_path, bindings))
    cells = document["cells"]
    gate = remote.require_path_check_before_faults(cells)
    assert cells[gate]["runKey"]["posture"] == "full" and cells[gate]["runKey"]["regime"] == "no-fault-cost"
    assert all(cell["fault"]["scenario"] is None for cell in cells[: gate + 1])
    # Planted: the gating cell moved after a fault cell.
    moved = copy.deepcopy(cells)
    first_fault = next(index for index, cell in enumerate(moved) if cell["fault"]["scenario"] is not None)
    moved.insert(0, moved.pop(first_fault))  # the gate now follows a fault cell
    with pytest.raises(remote.RuntimeFailure, match="before every fault cell"):
        remote.require_path_check_before_faults(moved)
    # Planted: two gating cells, or none.
    doubled = copy.deepcopy(cells)
    other = next(index for index, cell in enumerate(doubled) if index != gate and cell["runKey"]["posture"] == "full")
    doubled[other]["workloadPathCheck"]["gatesCampaign"] = True
    with pytest.raises(remote.RuntimeFailure, match="exactly one"):
        remote.require_path_check_before_faults(doubled)
    none = copy.deepcopy(cells)
    none[gate]["workloadPathCheck"]["gatesCampaign"] = False
    with pytest.raises(remote.RuntimeFailure, match="exactly one"):
        remote.require_path_check_before_faults(none)
    # Planted: the literal on the gate differs from the controller's own.
    drifted = copy.deepcopy(cells)
    drifted[gate]["workloadPathCheck"]["synchronousPath"].remove("flagd")
    with pytest.raises(remote.RuntimeFailure, match="before every fault cell"):
        remote.require_path_check_before_faults(drifted)


def test_a_failed_path_check_stops_the_campaign_before_any_fault_cell(tmp_path: Path, bindings, monkeypatch):
    """_run_campaign's own loop: after the gating cell, a failing check breaks
    before the first fault cell runs and is retained at the campaign root."""
    document = runtime.execution_package(_package(tmp_path, bindings))
    root = tmp_path / document["campaignId"]
    (root / ".controller").mkdir(parents=True)
    ran = []
    monkeypatch.setattr(remote, "ADMITTED_STUDY_EPOCHS", (document["studyEpoch"],))
    monkeypatch.setattr(remote, "validate_package", lambda doc: (doc["cells"], root, tmp_path / "lease", doc["composeProject"], NOW))
    monkeypatch.setattr(remote, "validate_local_target", lambda target: {"host": "fb14srv6"})
    monkeypatch.setattr(remote, "inherited_lease_fd", lambda path: 5)
    monkeypatch.setattr(remote, "project_resources", lambda project: {"containers": [], "networks": [], "volumes": []})

    (tmp_path / "lease").write_text("")
    # The inherited lease is "held": a second non-blocking lock would block.
    monkeypatch.setattr(remote.fcntl, "flock", lambda fd, op: (_ for _ in ()).throw(BlockingIOError()))

    def fake_cell(cell, deadline):
        ran.append(cell["runKey"])
        return {"state": "valid", "runId": cell["runId"]}

    monkeypatch.setattr(remote, "run_cell", fake_cell)
    monkeypatch.setattr(remote, "workload_path_check", lambda cell, cell_root, receipt: {"verdict": "fail", "runId": cell["runId"]})
    terminal = remote._run_campaign(document)
    assert terminal["stopped"] is True
    assert ran[-1]["posture"] == "full" and all(key["regime"] == "no-fault-cost" for key in ran)
    assert json.loads((root / "workload-path-check.json").read_text())["verdict"] == "fail"


@pytest.mark.parametrize(
    "posture, change",
    (("selected", "drop-flagd"), ("selected", "add-recommendation"), ("async", "drop-kafka")),
)
def test_catalog_closure_violations_are_refused(tmp_path: Path, monkeypatch, posture, change):
    """Planted: the installed catalog's offpath closure differs from the literal."""
    catalog = json.loads((ROOT / runtime.POSTURE_CATALOG).read_text(encoding="utf-8"))
    row = catalog["postures"][posture]
    for key in ("activeApplicationServices", "sourceInstrumentationLoadedServices"):
        services = set(row[key])
        if change == "drop-flagd":
            services.discard("flagd")
        elif change == "drop-kafka":
            services.discard("kafka")
        else:
            services.add("recommendationservice")
        row[key] = sorted(services)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(runtime, "POSTURE_CATALOG", path)
    with pytest.raises(runtime.GateError, match=f"{posture} posture closure differs"):
        runtime.posture_catalog()
