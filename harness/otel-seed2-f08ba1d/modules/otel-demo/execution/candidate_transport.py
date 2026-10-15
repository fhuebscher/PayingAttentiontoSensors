#!/usr/bin/env python3
"""OTel Demo's `TransportProtocol` surface, delegating into `candidate_runtime.py`.

`obsplacement.gate_driver.contract.TransportProtocol` names seven functions
and two constructible controllers. OTel's orchestrator already owns every
remote mechanic behind them -- one class, `ComposeSshAdapter`, which merges
what Hotel splits into an installer and a detached controller -- but exposes
none of them under those names, and two of the three read-only contract
points (`remote_output_exists`, `remote_status`) have no orchestrator
equivalent at all because `ComposeSshAdapter.status` requires a fully
gated `RuntimePackage` and therefore cannot answer for an identity whose
gate documents do not exist yet.

What this module deliberately does **not** do:

* It does not reimplement any remote program. Install, readiness capture and
  launch all go through `ComposeSshAdapter`, so the digest-pinned installed
  controllers stay the only remote code path, and `refuse_unsupported` stays
  the only thing standing between a driver and a target mutation.
* It does not retrofit tracing onto the orchestrator's own ssh/scp calls.
  `subprocess_runner` exists because the driver scripts wrap it in
  `traced_runner`; a trace produced through this module records what the
  *driver* ran. The orchestrator's own `_default_runner` is replaced by the
  traced runner where the flow layer supplies one, which is the one place
  the two do meet.
* It writes no gate document and derives no sentence.

The two read-only additions are ssh probes written here rather than
delegated, because there is nothing to delegate to. Both are `ssh ... test`
and `systemctl show`, both go through `candidate_runtime._ssh` so they are
quoted for root's zsh login shell exactly like every other remote word this
project sends, and neither can mutate the target.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "subprocess_runner", "build_release_bundle", "build_capture_spec",
    "build_runtime_package", "remote_output_exists", "remote_precheck",
    "remote_status", "BoundedSetupController", "BoundedCampaignController",
    "CAPTURE_SPEC_MEMBER", "UPSTREAM_BUNDLE_SUFFIX", "systemd_unit_for",
]

_RUNTIME_MODULE_NAME = "otel_candidate_runtime_orchestrator"
_SETUP_MODULE_NAME = "otel_candidate_setup_installer"


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
installer = _load(_SETUP_MODULE_NAME, "candidate_setup.py")

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM_SOURCE = ROOT / "upstream" / "opentelemetry-demo"

CAPTURE_SPEC_MEMBER = "capture-spec.json"
# `GatePaths.release_bundle` is one path; OTel installs from two Git bundles
# (the framework superproject and the pinned upstream submodule), so the
# second lives beside the first under this suffix rather than inventing a
# second GatePaths entry the shared library would have to learn about.
UPSTREAM_BUNDLE_SUFFIX = ".upstream"


def subprocess_runner(argv, data=None):
    """Run one command, capturing both streams, never raising on a non-zero exit.

    Exists solely so the driver scripts have something to hand
    `traced_runner`, and so that runner can be handed to `ComposeSshAdapter`
    (whose `CommandRunner` protocol is `(argv, *, input=None)`). `check=False`
    because a traced runner must record a failure, not lose it inside a
    raised exception before it reaches the trace.
    """
    return subprocess.run(
        [str(item) for item in argv], input=data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def _orchestrator_runner(runner):
    """Adapt a `traced_runner`-wrapped callable to `CommandRunner`'s keyword."""
    if runner is None:
        return runtime._default_runner

    def call(argv, *, input=None):  # noqa: A002 - the orchestrator's own name
        return runner(argv, input)

    return call


def _git(*argv: str) -> bytes:
    result = subprocess.run(
        ["git", *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise runtime.GateError(
            f"git {' '.join(argv[:3])} failed: {result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def _projected_materialized_source_sha256() -> str:
    """The digest the target's own install is required to reproduce.

    `candidate_setup.install` runs `materialize.py --out <source>` on the
    target and refuses unless `frozen_source_tree_sha256(source)` equals the
    value the GATE-PLAN carries. Computing it here means running the *same*
    materializer over the *same* pinned upstream checkout and projecting file
    modes the same way -- `frozen_source_tree_sha256` maps every mode to 0555
    or 0444, so the local umask cannot move it.

    This is the one number in the GATE-PLAN that is a prediction about the
    target rather than a fact about a local file, and it is the natural place
    for a workstation/target divergence (line endings, a tool that renders
    differently) to surface. It surfaces as a refused install, not as a bad
    campaign.
    """
    materializer = ROOT / "modules/otel-demo/materialize.py"
    with tempfile.TemporaryDirectory(prefix="otel-materialize-") as scratch:
        out = Path(scratch) / "source"
        result = subprocess.run(
            [sys.executable, "-I", str(materializer), "--out", str(out)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode != 0:
            raise runtime.GateError(
                "local materialization failed: "
                + result.stderr.decode("utf-8", "replace").strip()[-2000:]
            )
        return installer.frozen_source_tree_sha256(out)


def build_release_bundle(bindings, *, bundle_path, manifest_path) -> dict:
    """Build the exact one-shot install payload and record its identity.

    Performs no remote action. Produces three things and binds all three onto
    `bindings` (see `candidate_runtime_adapter`'s module docstring, seam 1):
    the framework Git bundle, the pinned upstream Git bundle, and the
    projected materialized-source digest.

    Both bundles are re-verified with `git bundle verify` and the framework
    bundle is required to actually contain the commit the GATE-PLAN names --
    `candidate_setup.install` clones and then `checkout --detach`es that
    commit, so a bundle that omits it would fail on the target after the
    transport has already run.
    """
    bundle_path = Path(bundle_path)
    upstream_bundle_path = bundle_path.with_name(bundle_path.name + UPSTREAM_BUNDLE_SUFFIX)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    for path in (bundle_path, upstream_bundle_path):
        if path.exists() or path.is_symlink():
            path.unlink()

    commit = bindings.framework_commit
    _git("-C", str(ROOT), "bundle", "create", str(bundle_path), commit, "HEAD")
    _git("-C", str(ROOT), "bundle", "verify", str(bundle_path))
    contained = _git("-C", str(ROOT), "bundle", "list-heads", str(bundle_path)).decode()
    if commit not in contained:
        raise runtime.GateError(
            "framework bundle does not carry the commit the GATE-PLAN names"
        )

    upstream_commit = runtime.target_allocation()["source"]["upstreamCommit"]
    observed_upstream = _git(
        "-C", str(UPSTREAM_SOURCE), "rev-parse", "HEAD",
    ).decode("ascii").strip()
    if observed_upstream != upstream_commit:
        raise runtime.GateError(
            f"upstream checkout is at {observed_upstream}, not the pinned {upstream_commit}"
        )
    _git("-C", str(UPSTREAM_SOURCE), "bundle", "create",
         str(upstream_bundle_path), upstream_commit, "HEAD")
    _git("-C", str(UPSTREAM_SOURCE), "bundle", "verify", str(upstream_bundle_path))

    repository_sha = runtime.file_sha256(bundle_path)
    upstream_sha = runtime.file_sha256(upstream_bundle_path)
    source_sha = _projected_materialized_source_sha256()
    bindings.bind_release(
        repository_bundle_sha256=repository_sha,
        upstream_bundle_sha256=upstream_sha,
        expected_materialized_source_sha256=source_sha,
    )

    manifest = {
        "schemaVersion": 1,
        "kind": "otel-srv6-release-manifest-v1",
        "frameworkCommit": commit,
        "upstreamCommit": upstream_commit,
        "bundleSha256": repository_sha,
        "bundleSizeBytes": bundle_path.stat().st_size,
        "upstreamBundlePath": str(upstream_bundle_path),
        "upstreamBundleSha256": upstream_sha,
        "upstreamBundleSizeBytes": upstream_bundle_path.stat().st_size,
        "expectedMaterializedSourceSha256": source_sha,
        "controllerDigests": runtime.controller_digests(),
    }
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(
        json.dumps(manifest, allow_nan=False, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def build_capture_spec(bindings, release_binding, *, archive_path) -> str:
    """Record which installed release the readiness capture may address.

    OTel's readiness capture is driven entirely by gate documents over ssh;
    there is no archive the target consumes. This archive is therefore a
    *local* record, not a payload: `admit_readiness` reads the installed
    binding back out of it and refuses to capture unless it matches the one
    it was handed, so the identity that reaches the target has been written
    down and re-read rather than passed straight through a call frame.
    """
    spec = {
        "schemaVersion": 1,
        "kind": "otel-srv6-readiness-capture-spec-v1",
        "frameworkCommit": bindings.framework_commit,
        "campaignId": bindings.campaign_id,
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


def _read_capture_spec(archive_path) -> dict:
    with tarfile.open(Path(archive_path), mode="r:") as bundle:
        if bundle.getnames() != [CAPTURE_SPEC_MEMBER]:
            raise runtime.GateError("readiness capture spec archive members differ")
        handle = bundle.extractfile(CAPTURE_SPEC_MEMBER)
        if handle is None:  # pragma: no cover - a regular member always extracts
            raise runtime.GateError("readiness capture spec is unreadable")
        return runtime.strict_json_bytes(handle.read(), "readiness capture spec")


def systemd_unit_for(campaign_id: str, package_sha256: str) -> str:
    """The unit name `execution_package` derives, recomputed for a read-only probe.

    `ComposeSshAdapter.status` gets this from `execution_package(package)`,
    which needs a fully validated `RuntimePackage`. A watcher polling before
    (or after) that package exists has only what `runtime-package.json`
    carries, so the same name is derived from the same two inputs here.
    """
    return f"otel-candidate-v4-{package_sha256}" if package_sha256 else (
        f"otel-candidate-v4-{campaign_id}"
    )


def build_runtime_package(package) -> dict:
    """The document written to `runtime-package.json` and handed to the launcher.

    The orchestrator's `execution_package` output is carried verbatim under
    `executionPackage`; the campaign identity and the derived systemd unit are
    lifted to the top level because the shared flow layer checks
    `remote_input["campaignId"]` is a safe slug before any launch, and
    `campaign_status_flow.poll_once` reads both back from this file long
    after the `RuntimePackage` object is gone.
    """
    document = runtime.execution_package(package)
    binding = package.gate_plan["binding"]
    return {
        "schemaVersion": 1,
        "kind": "otel-candidate-runtime-package-v1",
        "campaignId": binding["campaignId"],
        "systemdUnit": document["systemdUnit"],
        "remoteArtifactRoot": binding["remoteArtifactRoot"],
        "target": copy.deepcopy(binding["target"]),
        "executionPackageCanonicalSha256": runtime.canonical_sha256(document),
        "admissionCanonicalSha256": runtime.canonical_sha256(document),
        "executionPackage": document,
    }


def _remote_input(remote_input) -> dict:
    if not isinstance(remote_input, Mapping):
        raise runtime.GateError("runtime package is not an object")
    campaign_id = str(remote_input.get("campaignId"))
    if runtime.SAFE_NAME.fullmatch(campaign_id) is None:
        raise runtime.GateError("runtime package campaign identity is not allowed")
    artifact_root = str(remote_input.get("remoteArtifactRoot") or "")
    runtime._safe_posix(artifact_root, "remote artifact root", absolute=True)
    unit = str(remote_input.get("systemdUnit") or "")
    if not unit or any(character.isspace() for character in unit):
        raise runtime.GateError("runtime package systemd unit is not allowed")
    target = remote_input.get("target") or {}
    host = str(target.get("host") or "")
    user = str(target.get("transportUser") or "")
    if runtime.SAFE_HOST.fullmatch(host) is None or runtime.SAFE_USER.fullmatch(user) is None:
        raise runtime.GateError("runtime package target identity is not allowed")
    return {
        "campaignId": campaign_id, "artifactRoot": artifact_root,
        "unit": unit, "destination": f"{user}@{host}",
    }


def _ssh_probe(destination: str, tokens, *, runner=None):
    argv = runtime._ssh(destination, tokens)
    return (runner or subprocess_runner)(argv), argv


def remote_output_exists(remote_input, *, runner=None) -> bool:
    """Read-only: has anything already been produced for this campaign identity?

    A freshly minted campaign identity has no artifact root, so `test -e`
    answers 1 and this answers False. Any of the four one-shot outputs
    present means the identity has already been used and a launch under it
    would not be a one shot.

    ssh failure is NOT "nothing exists": a transport error raises, so the
    dry run records it as a reason instead of reading a network outage as a
    clean target. (Hotel's `campaign_status.py` deliberately treats ssh
    failure as transient for a *watcher*; that is the opposite decision for
    a one-shot precondition, and §2.9 of the plan is the record of what
    conflating the two cost.)
    """
    checked = _remote_input(remote_input)
    root = checked["artifactRoot"]
    names = ("remote-terminal.json", "campaign-abort.json",
             ".controller/execution-package.json", "runs")
    for name in names:
        result, argv = _ssh_probe(
            checked["destination"], ["test", "-e", f"{root}/{name}"], runner=runner,
        )
        if result.returncode == 0:
            return True
        if result.returncode != 1:
            raise runtime.GateError(
                f"read-only remote probe failed ({result.returncode}): {' '.join(argv)}"
            )
    return False


def remote_precheck(package, remote_input) -> dict:
    """Replay, locally and without launching, what the launcher will enforce.

    `ComposeSshAdapter.launch` runs exactly three checks before it emits
    anything: `refuse_unsupported`, a fresh `validate_readiness`, and a fresh
    `validate_gate_run`. All three are pure local computation over documents
    already in hand, so a dry run can run them verbatim -- this is a replay
    of the launcher's own guard, not a second implementation of it.

    Never raises for an expected failure: the flow layer accumulates reasons.
    """
    try:
        document = runtime.execution_package(package)
        carried = remote_input.get("executionPackage") if isinstance(remote_input, Mapping) else None
        if runtime.canonical_bytes(carried) != runtime.canonical_bytes(document):
            raise runtime.GateError(
                "runtime package execution document differs from the admitted one"
            )
        if remote_input["systemdUnit"] != document["systemdUnit"]:
            raise runtime.GateError("runtime package unit differs from the admitted one")
        now = runtime.datetime.now(runtime.timezone.utc)
        runtime.refuse_unsupported("candidate launch")
        runtime.validate_readiness(
            package.readiness, package.gate_plan, package.gate_plan_sha256, now=now,
        )
        runtime.validate_gate_run(
            package.gate_run, package.gate_plan, package.gate_plan_sha256,
            package.readiness, package.readiness_sha256, now=now,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a dry-run reason
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "detail": "launch admission and posture refusal boundary accepted"}


def remote_status(remote_input, package_sha256: str, *, runner=None) -> dict:
    """One read-only status poll, projected into the shared watcher vocabulary.

    Written here rather than delegated to `ComposeSshAdapter.status` for two
    reasons, both of which are Hotel lesson 5 ("the status program must answer
    for a not-yet-launched identity"):

    * `ComposeSshAdapter.status` takes a `RuntimePackage`, which
      `replay_runtime_from_files` can only build once all five gate documents
      exist. Before a launch they do not, so on Hotel the equivalent path
      exited 3 -- "terminal" -- for every campaign that had not started yet,
      and the dry run refused. A fresh identity here answers
      `state=not-launched`, `terminalExists=False`, `abortExists=False`.
    * `ComposeSshAdapter.status` never reads the ssh return code: a total
      transport failure yields empty fields, an absent `ActiveState`, and a
      plausible-looking "not terminal". Here `transportOk` is explicit and a
      failed poll reports `state=unknown` with `terminal` false, so a watcher
      keeps polling rather than stopping on a network blip.

    `LoadState` is what separates the two inactive cases: `not-found` for a
    unit that never existed, `loaded` for one that ran and was collected.
    """
    checked = _remote_input(remote_input)
    destination = checked["destination"]
    unit = checked["unit"]
    result, _ = _ssh_probe(
        destination,
        ["systemctl", "show", unit, "--no-pager",
         "--property=LoadState", "--property=ActiveState",
         "--property=SubState", "--property=Result", "--property=ExecMainStatus"],
        runner=runner,
    )
    transport_ok = result.returncode == 0
    fields: dict = {}
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value

    terminal_exists = abort_exists = False
    probes = []
    active = fields.get("ActiveState")
    if transport_ok and active not in {"active", "activating", "reloading"}:
        for name, flag in (("remote-terminal.json", "terminal"),
                           ("campaign-abort.json", "abort")):
            probe, argv = _ssh_probe(
                destination, ["test", "-f", f"{checked['artifactRoot']}/{name}"],
                runner=runner,
            )
            probes.append({"argv": argv, "returnCode": probe.returncode})
            if probe.returncode == 0:
                if flag == "terminal":
                    terminal_exists = True
                else:
                    abort_exists = True

    if not transport_ok:
        state = "unknown"
    elif active in {"active", "activating", "reloading"}:
        state = "running"
    elif terminal_exists or abort_exists:
        state = "stopped"
    elif fields.get("LoadState") == "not-found":
        state = "not-launched"
    else:
        state = "stopped-without-artifact"

    return {
        "schemaVersion": 1,
        "kind": "otel-candidate-campaign-status-projection-v1",
        "campaignId": checked["campaignId"],
        "systemdUnit": unit,
        "packageSha256": package_sha256,
        "transportOk": transport_ok,
        "transportReturnCode": result.returncode,
        "state": state,
        "systemdState": {
            "activeState": fields.get("ActiveState", "unknown"),
            "subState": fields.get("SubState", "unknown"),
            "result": fields.get("Result", "?"),
            "loadState": fields.get("LoadState", "unknown"),
        },
        "journalRows": fields.get("ExecMainStatus", "?"),
        "terminalExists": terminal_exists,
        "abortExists": abort_exists,
        "leaseHeld": "unprobed",
        "completionProbes": probes,
    }


class BoundedSetupController:
    """`probe()` / `setup(...)` / `admit_readiness(...)` over `ComposeSshAdapter`."""

    def __init__(self, bindings=None, runner=None):
        self.bindings = bindings
        self.runner = runner

    def probe(self) -> dict:
        """The declared operational target, recorded before anything is built.

        Deliberately **not** remote evidence, and it says so in the document
        it returns. OTel pins its operational target as a reviewed, digested
        file (`candidate-target-allocation.json`, whose sha256 the GATE-PLAN
        carries as `targetContractSha256`), and every fact in it is verified
        *on the target itself* -- at install time by
        `candidate_setup.validate_local_identity` (uid/gid/docker group) and
        at readiness time by `target_observations` (hostname, euid, docker
        gid and version, foreign inventory, ports, lease, traversability).
        A local ssh probe here would produce a weaker claim, unbound to the
        install, that a reader could mistake for that verification.
        """
        allocation = runtime.target_allocation()
        proof = {
            "schemaVersion": 1,
            "kind": "otel-srv6-declared-target-contract-v1",
            "remoteObservation": False,
            "verifiedOnTargetAt": "install-and-readiness",
            "capturedAt": runtime.datetime.now(runtime.timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "targetContractSha256": runtime.file_sha256(runtime.TARGET_ALLOCATION),
            "operationalTarget": copy.deepcopy(allocation),
        }
        proof["declarationCanonicalSha256"] = runtime.canonical_sha256(proof)
        return proof

    def setup(self, *, gate_plan_path, target_proof_path, release_manifest_path,
              gate_setup_path, bundle_path) -> dict:
        """The one setup mutation: upload and install two exact reviewed bundles.

        `target_proof_path` and `release_manifest_path` are unused: the
        installer binds to the GATE-PLAN's own `binding`, which already
        carries both bundle digests, the target contract digest and the
        projected source digest, and `ComposeSshAdapter.setup` re-verifies
        the local bundle bytes against them before uploading. Re-reading the
        manifest here would add a second source for facts the gate document
        has already fixed.

        The staging root must be absent (`ComposeSshAdapter.setup` refuses an
        existing one, which is how a second install under one GATE-SETUP is
        prevented), so a prior staging tree is archived aside rather than
        deleted -- the local half of "archive gate state after an abort".
        """
        plan_dir = self.bindings.plan_dir
        package = runtime.authorize_setup_from_files(
            plan_dir, Path(gate_plan_path), Path(gate_setup_path),
        )
        bundle_path = Path(bundle_path)
        upstream_bundle_path = bundle_path.with_name(
            bundle_path.name + UPSTREAM_BUNDLE_SUFFIX
        )
        staging = Path(gate_plan_path).parent / "install-staging"
        _archive_aside(staging, "install-staging")
        adapter = runtime.ComposeSshAdapter(_orchestrator_runner(self.runner))
        transport_receipt = adapter.setup(
            package, bundle_path, upstream_bundle_path, staging,
        )
        # The flow layer writes whatever this returns to `install-receipt.json`
        # and `gate_setup_flow.cmd_readiness` then projects RELEASE_BINDING_KEYS
        # out of it. `ComposeSshAdapter.setup` returns its *transport* receipt,
        # whose `installedBindings` is the target's own receipt projection, so
        # the binding keys are lifted to the top level here and the transport
        # receipt is kept whole beside them.
        receipt = dict(transport_receipt["installedBindings"])
        receipt["transportReceipt"] = transport_receipt
        receipt["setupReceiptPath"] = str(staging / "setup-receipt.json")
        return receipt

    def admit_readiness(self, *, archive_path, release_binding, local_output) -> dict:
        """Run the installed target readiness producer and fetch its exact bytes.

        The installed binding is read back out of the capture spec archive and
        must agree with the one handed in; a disagreement means the two were
        derived from different installs and raises.
        """
        spec = _read_capture_spec(archive_path)
        if runtime.canonical_bytes(spec.get("releaseBinding")) != runtime.canonical_bytes(
            dict(release_binding)
        ):
            raise runtime.GateError(
                "readiness capture spec release binding differs from the install receipt"
            )
        gates = Path(archive_path).parent
        request = runtime.authorize_readiness_from_files(
            self.bindings.plan_dir, gates / "gate-plan.json", gates / "gate-setup.json",
            Path(_setup_receipt_path(gates)),
        )
        local_output = Path(local_output)
        local_output.mkdir(parents=True, exist_ok=True)
        adapter = runtime.ComposeSshAdapter(_orchestrator_runner(self.runner))
        admission = adapter.capture_readiness(request, local_output)
        admission = dict(admission)
        admission["readinessCanonicalSha256"] = admission["runtimeReadinessSha256"]
        return admission


class BoundedCampaignController:
    """`launch(...)` over `ComposeSshAdapter`."""

    def __init__(self, framework_commit=None, release_binding=None, runner=None):
        self.framework_commit = framework_commit
        self.release_binding = release_binding
        self.runner = runner

    def launch(self, package_path, *, local_output) -> dict:
        """Launch the one-shot campaign, once, from the package already on disk.

        Reads the package back from disk rather than taking it in memory, so
        what is launched is exactly what `cmd_execute` recorded, and replays
        the whole gate chain from the same gates directory before launching.
        The launch receipt is retained beside the campaign result directory.
        """
        package_path = Path(package_path)
        remote_input = json.loads(package_path.read_text(encoding="utf-8"))
        gates = package_path.parent
        plan_dir = getattr(self, "plan_dir", None) or _plan_dir_from_gates(gates)
        runtime_package = runtime.authorize_from_files(
            plan_dir, gates / "gate-plan.json", gates / "gate-setup.json",
            Path(_setup_receipt_path(gates)), gates / "fetched-readiness/readiness.json",
            gates / "gate-run.json",
        )
        document = runtime.execution_package(runtime_package)
        if runtime.canonical_bytes(remote_input.get("executionPackage")) != \
                runtime.canonical_bytes(document):
            raise runtime.GateError(
                "runtime package on disk differs from the replayed execution package"
            )
        local_output = Path(local_output)
        local_output.mkdir(parents=True, exist_ok=True)
        staging = local_output / "launch-staging"
        _archive_aside(staging, "launch-staging")
        adapter = runtime.ComposeSshAdapter(_orchestrator_runner(self.runner))
        receipt = adapter.launch(runtime_package, staging)
        (local_output / "launch-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt


def _setup_receipt_path(gates: Path) -> Path:
    """Where the target's own setup receipt landed.

    `BoundedSetupController.setup` records it in `install-receipt.json`; the
    fallback is the conventional staging location, so a receipt written by a
    manual `gate_setup.py install` is still found.
    """
    install_receipt = gates / "install-receipt.json"
    if install_receipt.is_file():
        recorded = json.loads(install_receipt.read_text(encoding="utf-8"))
        candidate = recorded.get("setupReceiptPath")
        if isinstance(candidate, str) and Path(candidate).is_file():
            return Path(candidate)
    return gates / "install-staging/setup-receipt.json"


def _plan_dir_from_gates(gates: Path) -> Path:
    """`.../otel-demo/gates` -> `.../otel-demo/plan`, the driver's own layout."""
    return gates.parent / "plan"


def _archive_aside(path: Path, label: str) -> None:
    """Move a staging tree aside instead of deleting it.

    Hotel lesson 9: after an aborted run, local gate state that the next
    attempt refuses to overwrite has to go *somewhere*, and deleting it
    destroys the only local record of the attempt that failed. Hotel spent an
    attempt discovering this with `gate-run.json`.
    """
    if not path.exists() and not path.is_symlink():
        return
    stamp = runtime.datetime.now(runtime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = path.with_name(f"archived-{label}-{stamp}")
    if archive.exists():  # pragma: no cover - same-second collision
        shutil.rmtree(archive)
    path.rename(archive)
