#!/usr/bin/env python3
"""The one authoritative declaration of Hotel's release binding key set.

`obsplacement.gate_driver.module_loader.load_binding_keys` is the only
function in the driver library permitted to read `RELEASE_BINDING_KEYS`, and
it always reads it from *this* module rather than from a literal repeated in
a driver script (non-negotiable property #2). The reason is a named incident
recorded in that module's docstring: a seventh hand-transcribed copy of
TeaStore's key list drifted from the six in-repo declarations, so the binding
digest the driver computed stopped matching the one the target computed and
readiness refused every install.

Hotel's install receipt is produced by the embedded one-shot installer
program in `candidate_runtime.py` (`REMOTE_ONE_SHOT_INSTALL`), which prints a
`hotel-srv4-install-receipt-v1` document. The keys below are the subset of
that receipt that *identifies the installed release* -- the setup identity it
was installed under, the exact bundle bytes, the manifest those bytes were
verified against, the digest of the payload as it landed on the target, and
the GATE-SETUP document that authorized the install. Everything else in the
receipt (foreign-project inventory, port observations, timestamps) is
evidence about the target at install time, not identity of the release, and
deliberately does not participate in the release binding.

This module holds no logic: it exists so there is exactly one place the key
set is written down, in the same directory as the runtime it describes.
"""
from __future__ import annotations

__all__ = ["RELEASE_BINDING_KEYS"]

RELEASE_BINDING_KEYS = (
    "setupId",
    "bundleSha256",
    "bundleSizeBytes",
    "manifestCanonicalSha256",
    "installedEntriesSha256",
    "gateSetupCanonicalSha256",
)
