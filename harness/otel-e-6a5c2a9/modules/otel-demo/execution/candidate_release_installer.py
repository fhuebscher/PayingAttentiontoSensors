#!/usr/bin/env python3
"""The installed framework's own `RELEASE_BINDING_KEYS` for OTel Demo.

`gate_setup_flow.cmd_readiness` and `campaign_setup_flow.cmd_auto` project a
release binding out of the install receipt with

    release_binding = {key: receipt[key] for key in binding_keys}

and `module_loader.load_binding_keys` insists those keys come from the
*installed* framework rather than from a literal typed into a driver (memory
note "scratchpad gate-driver binding-key drift": a hardcoded key list that
drifts from the receipt makes readiness fail closed on every install, and the
failure names a missing dictionary key rather than the drift).

So this module does not write a list down either. It derives the keys from
`candidate_runtime.installed_bindings`, which is the single function that
defines what a *setup receipt* projects into a *release identity* -- the same
projection the readiness document carries as `installedBindings` and the same
one `replay_runtime_from_files` re-checks before any launch. Adding a field
there automatically adds it here; a driver cannot fall behind.

The derivation is a call against a synthetic receipt whose values are the key
names themselves, so the result is exactly `installed_bindings`' key set with
no dependence on any real install. That is deliberately a *probe of the
function*, not a copy of its source: if `installed_bindings` ever computes a
key conditionally, this sees the real behaviour rather than a reading of it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

__all__ = ["RELEASE_BINDING_KEYS", "installed_binding_keys"]

_RUNTIME_MODULE_NAME = "otel_candidate_runtime_orchestrator"


def _load_runtime():
    existing = sys.modules.get(_RUNTIME_MODULE_NAME)
    if existing is not None:
        return existing
    path = Path(__file__).resolve().parent / "candidate_runtime.py"
    spec = importlib.util.spec_from_file_location(_RUNTIME_MODULE_NAME, path)
    if spec is None or spec.loader is None:  # pragma: no cover - real file
        raise ImportError(f"cannot load the OTel orchestrator from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RUNTIME_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


runtime = _load_runtime()

# Every field `installed_bindings` reads off a setup receipt, plus the digest
# it is handed. `setupReceiptSha256` is the one key that is an argument rather
# than a receipt field, and it *is* present on the transport receipt this
# project writes to install-receipt.json, so it stays in the set.
_PROBE_RECEIPT_FIELDS = (
    "frameworkCommit", "upstreamCommit", "targetContractSha256", "releaseRoot",
    "repositoryRoot", "remoteSourceRoot", "remoteArtifactRoot",
    "materializedSourceSha256", "imageIds", "installedControllerDigests",
)


def installed_binding_keys() -> tuple:
    """Probe `installed_bindings` for the key set it actually produces."""
    probe = {name: name for name in _PROBE_RECEIPT_FIELDS}
    return tuple(sorted(runtime.installed_bindings(probe, "setupReceiptSha256")))


RELEASE_BINDING_KEYS = installed_binding_keys()
