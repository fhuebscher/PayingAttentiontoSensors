#!/usr/bin/env python3
"""Hotel's `TransportProtocol` surface, delegating into `candidate_runtime.py`.

`obsplacement.gate_driver.contract.TransportProtocol` names seven functions
and two constructible controllers. Hotel's orchestrator already owns every
remote mechanic behind them -- `build_setup_bundle`, `SshSetupInstaller`,
`DetachedSshController` -- but exposes none of them under those names. This
module is the translation layer.

What it deliberately does **not** do:

* It does not retrofit tracing onto the orchestrator's own ssh/scp calls.
  `subprocess_runner` exists because the driver scripts wrap
  `transport.subprocess_runner` in `traced_runner`; the orchestrator's
  internal `subprocess.run` call sites are untouched and keep their own
  error handling. A trace file produced through this module therefore records
  what the *driver* ran, not what the orchestrator ran internally -- see
  `BoundedSetupController.setup`'s note.
* It does not reimplement any remote program. Every remote effect goes
  through `SshSetupInstaller.install` or `DetachedSshController`, so the
  reviewed embedded programs and their `validate_embedded_remote_programs`
  guard remain the only remote code path.
* It writes no gate document and derives no sentence.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "SUBMODULE_SOURCE",
    "subprocess_runner", "build_release_bundle", "build_capture_spec",
    "build_runtime_package", "remote_output_exists", "remote_precheck",
    "remote_status", "BoundedSetupController", "BoundedCampaignController",
]

# Same module name the adapter shim uses, so the 4000-line orchestrator is
# executed exactly once per process even though `SutConfig` names two
# separate files that both load it.
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

# `build_setup_bundle` takes the DeathStarBench submodule checkout whose
# `hotelReservation` subtree becomes the installed application source. It
# re-verifies that the checkout is at the exact pinned upstream commit and is
# clean before archiving it, so naming the path here cannot substitute a
# different source.
SUBMODULE_SOURCE = ROOT / "upstream" / "deathstarbench"

CAPTURE_SPEC_MEMBER = "capture-spec.json"


def subprocess_runner(argv, data=None):
    """Run one command, capturing both streams, never raising on a non-zero exit.

    Exists solely so the driver scripts have something to hand
    `traced_runner`. Returns a `subprocess.CompletedProcess`, which carries
    the `.returncode` / `.stdout` / `.stderr` attributes `traced_runner`
    reads. `check=False` because a traced runner must record a failure, not
    lose it inside a raised exception before it is written to the trace.
    """
    return subprocess.run(
        [str(item) for item in argv], input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def build_release_bundle(bindings, *, bundle_path, manifest_path) -> dict[str, Any]:
    """Build the exact one-shot install payload and record its identity.

    Performs no remote action (the orchestrator's `build_setup_bundle` says
    so in its own docstring). The manifest written here carries the three
    fields `setup_binding` binds a GATE-SETUP to -- and the full install
    manifest alongside them, under a separate key, so a human can inspect
    what is in the bundle without those extra bytes reaching the binding
    (the adapter projects exactly the three).
    """
    info = runtime.build_setup_bundle(
        bindings.framework_commit, SUBMODULE_SOURCE, Path(bundle_path),
    )
    manifest = {
        "schemaVersion": 1,
        "kind": "hotel-srv4-release-manifest-v1",
        "frameworkCommit": bindings.framework_commit,
        "bundleSha256": info.bundle_sha256,
        "bundleSizeBytes": info.bundle_size_bytes,
        "manifestCanonicalSha256": info.manifest_canonical_sha256,
        "installManifest": info.manifest,
    }
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def build_capture_spec(bindings, release_binding, *, archive_path) -> str:
    """Record which installed release the readiness capture is allowed to address.

    Hotel's readiness capture is driven entirely by a setup identity over
    ssh; there is no archive the target consumes. The archive this writes is
    therefore a *local* record, not a payload: `admit_readiness` reads the
    setup identity back out of it and refuses to capture unless it matches
    the release binding it was handed, so the identity that reaches the
    target has been written down and re-read rather than passed straight
    through one call frame.
    """
    setup_id = _release_setup_id(release_binding)
    spec = {
        "schemaVersion": 1,
        "kind": "hotel-srv4-readiness-capture-spec-v1",
        "frameworkCommit": bindings.framework_commit,
        "setupId": setup_id,
        "releaseBinding": dict(release_binding),
    }
    payload = runtime.canonical_bytes(spec) + b"\n"
    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="w", format=tarfile.PAX_FORMAT) as bundle:
        info = tarfile.TarInfo(CAPTURE_SPEC_MEMBER)
        info.size = len(payload)
        info.mode = 0o600
        info.mtime = 0
        bundle.addfile(info, io.BytesIO(payload))
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def _release_setup_id(release_binding) -> str:
    if not isinstance(release_binding, Mapping):
        raise runtime.GateError("release binding is not an object")
    setup_id = str(release_binding.get("setupId"))
    if runtime.SETUP_ID.fullmatch(setup_id) is None:
        raise runtime.GateError("release binding setup identity is not allowed")
    return setup_id


def _read_capture_spec(archive_path) -> dict[str, Any]:
    with tarfile.open(Path(archive_path), mode="r:") as bundle:
        names = bundle.getnames()
        if names != [CAPTURE_SPEC_MEMBER]:
            raise runtime.GateError("readiness capture spec archive members differ")
        handle = bundle.extractfile(CAPTURE_SPEC_MEMBER)
        if handle is None:  # pragma: no cover - a regular member always extracts
            raise runtime.GateError("readiness capture spec is unreadable")
        return runtime.strict_json(handle.read(), "readiness capture spec")


def _admission_document(package) -> dict[str, Any]:
    """The admission dict, whether handed the adapter's wrapper or a bare dict."""
    document = getattr(package, "document", package)
    if not isinstance(document, dict) or "bindings" not in document:
        raise runtime.GateError("runtime package does not carry a runtime admission")
    return document


def build_runtime_package(package) -> dict[str, Any]:
    """The document written to `runtime-package.json` and handed to the launcher.

    The admission is carried verbatim under `admission`: `validate_launch_admission`
    recomputes `admissionCanonicalSha256` over every key except that digest,
    so the admission cannot be wrapped in extra keys of its own. The campaign
    identity is lifted to the top level because the shared flow layer checks
    `remote_input["campaignId"]` is a safe slug before any launch, and
    `campaign_status_flow.poll_once` reads it back from this file.
    """
    admission = _admission_document(package)
    binding = admission["bindings"]
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-runtime-package-v1",
        "campaignId": binding["campaignId"],
        "admissionCanonicalSha256": admission["admissionCanonicalSha256"],
        "admission": admission,
    }


def _campaign_id(remote_input) -> str:
    if not isinstance(remote_input, Mapping):
        raise runtime.GateError("runtime package is not an object")
    campaign_id = str(remote_input.get("campaignId"))
    if runtime.CAMPAIGN_ID.fullmatch(campaign_id) is None:
        raise runtime.GateError("runtime package campaign identity is not allowed")
    return campaign_id


def remote_output_exists(remote_input) -> bool:
    """Read-only: has anything already been produced for this campaign identity?

    A freshly minted campaign identity has no control directory, no launch
    attempt, no receipt and no abort. Any of them present means this identity
    has already been used and a launch under it would not be a one-shot.
    """
    status = runtime.DetachedSshController().status(_campaign_id(remote_input))
    return bool(
        status["launchPresent"]
        or status["executionReceiptPresent"]
        or status["campaignAbortPresent"]
        or status["controllerLogPresent"]
    )


def remote_precheck(package, remote_input) -> dict[str, Any]:
    """Replay, locally and without launching, what the launcher will enforce.

    `DetachedSshController.launch` runs exactly two checks before it emits
    anything: `validate_embedded_remote_programs` (the reviewed remote safety
    seams are intact) and `validate_launch_admission` (freshness and a full
    runtime budget, consumed independently of admission time). Both are pure
    local computation, so a dry run can run them verbatim -- this is a replay
    of the launcher's own guard, not a second implementation of it.

    Never raises for an expected failure: the flow layer accumulates reasons.
    """
    try:
        admission = _admission_document(package)
        carried = remote_input["admission"] if isinstance(remote_input, Mapping) else None
        if runtime.canonical_bytes(carried) != runtime.canonical_bytes(admission):
            raise runtime.GateError(
                "runtime package admission differs from the admitted document"
            )
        if remote_input["campaignId"] != admission["bindings"]["campaignId"]:
            raise runtime.GateError("runtime package campaign identity differs from the admission")
        runtime.validate_embedded_remote_programs()
        runtime.validate_launch_admission(admission)
    except Exception as exc:  # noqa: BLE001 - surfaced as a dry-run reason
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "detail": "embedded remote programs and launch admission accepted"}


def remote_status(remote_input, package_sha256: str) -> dict[str, Any]:
    """One read-only status poll, projected into the shared watcher vocabulary.

    `package_sha256` is accepted and unused: Hotel's detached status endpoint
    is keyed on the campaign identity alone (the control directory is created
    by the launch itself and named after it), so there is no package digest
    for the remote to compare against. Accepting and ignoring it is honest
    here -- the alternative would be to send a digest the remote does not
    check, which would look like a binding and be none.

    `terminal_status.is_terminal` reads `state`, `systemdState.activeState`,
    `terminalExists` and `abortExists`. Hotel's campaign runs as a detached
    ssh-launched process rather than a systemd unit, so the supervisor fields
    project that process's liveness into the same vocabulary; the unprojected
    receipt is kept verbatim under `detachedStatus`. The projection is
    deliberately conservative: anything other than "the supervisor is alive
    and no completion artifact exists" reports as terminal, because
    over-reporting terminal only stops a watcher, while under-reporting it
    would keep a watcher polling a campaign that has already ended.
    """
    status = runtime.DetachedSshController().status(_campaign_id(remote_input))
    running = bool(status["running"])
    return {
        "schemaVersion": 1,
        "kind": "hotel-candidate-campaign-status-projection-v1",
        "campaignId": status["campaignId"],
        "state": "running" if running else ("stopped" if status["terminal"] else "unknown"),
        "systemdState": {
            "activeState": "active" if running else "inactive",
            "subState": "running" if running else "dead",
            "result": status["completionArtifact"] or "?",
        },
        "terminalExists": bool(status["executionReceiptPresent"]),
        "abortExists": bool(status["campaignAbortPresent"]),
        "leaseHeld": bool(status["leaseLockedByCampaign"]),
        "detachedStatus": status,
    }


class BoundedSetupController:
    """`probe()` / `setup(...)` / `admit_readiness(...)` over Hotel's installer."""

    def __init__(self, bindings=None, runner=None):
        self.bindings = bindings
        self.runner = runner

    def probe(self) -> dict[str, Any]:
        """The declared operational target, recorded before anything is built.

        This is deliberately **not** remote evidence, and says so in the
        document it returns. Hotel pins its operational target as declared
        policy (`candidate_runtime.TARGET` and the runtime policy's
        `allowedTransports`), and every fact in it is re-verified *on the
        target itself* at install time (the embedded installer refuses a
        target whose uid/gid/docker group/foreign inventory differ) and again
        at readiness time. A local ssh probe here would produce a weaker
        claim, unbound to the install, that a reader could mistake for that
        verification.
        """
        policy = runtime._validate_policy(
            runtime._json_file(runtime.POLICY, "runtime policy")
        )
        transport = policy["allowedTransports"]["ssh-compose"]
        proof = {
            "schemaVersion": 1,
            "kind": "hotel-srv4-declared-target-contract-v1",
            "remoteObservation": False,
            "verifiedOnTargetAt": "install-and-readiness",
            "capturedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "operationalTarget": dict(transport),
            "targetProjection": runtime.TARGET_PROJECTION,
        }
        proof["declarationCanonicalSha256"] = runtime.canonical_sha256(proof)
        return proof

    def setup(self, *, gate_plan_path, target_proof_path, release_manifest_path,
              gate_setup_path, bundle_path) -> dict[str, Any]:
        """The one setup mutation: upload and install one exact reviewed tar.

        `target_proof_path` and `release_manifest_path` are unused: the
        installer binds to the GATE-SETUP document's own `bindings`, which
        already carry the bundle digest, size and manifest digest, and
        re-verifies the local bundle's bytes against them before uploading.
        Re-reading the manifest file here would add a second source for facts
        the gate document already fixes.

        The traced `runner` is unused for the same structural reason
        `subprocess_runner`'s docstring gives: `SshSetupInstaller.install`
        owns its own scp/ssh invocations and their receipt validation.
        Routing them through a generic runner would mean reimplementing that
        validation outside the reviewed installer.
        """
        return runtime.SshSetupInstaller().install(
            Path(bundle_path),
            runtime._json_file(Path(gate_setup_path), "GATE-SETUP"),
            bindings=self.bindings,
            gate_plan=runtime._json_file(Path(gate_plan_path), "GATE-PLAN"),
        )

    def admit_readiness(self, *, archive_path, release_binding, local_output) -> dict[str, Any]:
        """Run the installed target readiness producer and fetch its exact bytes.

        The setup identity is read back out of the capture spec archive and
        must agree with the release binding; a disagreement means the two
        were derived from different installs and raises.

        After the capture, a byte-identical copy of the retained readiness
        document is written at the shared library's conventional path
        (`<local_output>/readiness.json`) so the flow layer can read it where
        it expects to. The retained document under
        `<local_output>/readiness-<captureId>/` stays the one an admission
        binds to -- see `candidate_runtime_adapter.authorize_from_files`,
        which refuses to admit unless the two are byte-identical.
        """
        setup_id = _release_setup_id(release_binding)
        spec = _read_capture_spec(archive_path)
        if spec.get("setupId") != setup_id:
            raise runtime.GateError(
                "readiness capture spec setup identity differs from the release binding"
            )
        local_output = Path(local_output)
        admission = runtime.DetachedSshController().capture_readiness(setup_id, local_output)
        retained = Path(admission["readinessPath"])
        convenience = local_output / "readiness.json"
        payload = runtime._file(retained, "retained target-produced readiness")
        descriptor = os.open(
            convenience,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            if os.write(descriptor, payload) != len(payload):
                raise runtime.GateError("short write to the fetched-readiness copy")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return admission


class BoundedCampaignController:
    """`launch(...)` over Hotel's detached ssh controller."""

    def __init__(self, framework_commit=None, release_binding=None, runner=None):
        self.framework_commit = framework_commit
        self.release_binding = release_binding
        self.runner = runner
        if release_binding is not None:
            _release_setup_id(release_binding)

    def launch(self, package_path, *, local_output) -> dict[str, Any]:
        """Launch the one-shot campaign, once, from the package already on disk.

        Reads the package back from disk rather than taking it in memory, so
        what is launched is exactly what `cmd_execute` recorded. The launch
        receipt is retained beside the campaign result directory with
        exclusive creation: a second launch under the same package cannot
        overwrite the first one's receipt.
        """
        package = runtime._json_file(Path(package_path), "runtime package")
        admission = package.get("admission")
        if not isinstance(admission, dict):
            raise runtime.GateError("runtime package does not carry a runtime admission")
        if (
            package.get("campaignId") != admission.get("bindings", {}).get("campaignId")
            or package.get("admissionCanonicalSha256")
            != admission.get("admissionCanonicalSha256")
        ):
            raise runtime.GateError("runtime package identity differs from its admission")
        receipt = runtime.DetachedSshController().launch(admission)
        local_output = Path(local_output)
        local_output.mkdir(parents=True, exist_ok=True)
        runtime._write_exclusive_json(local_output / "detached-launch.json", receipt)
        return receipt
