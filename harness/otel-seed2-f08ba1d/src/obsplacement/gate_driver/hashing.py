"""Deterministic content hashing for gate documents.

Every canonical driver calls `adapter.canonical_sha256(obj)` to hash bindings,
target proofs, and authorization documents (e.g. gate_setup.py:76, :122,
:229; gate_run.py:78; campaign_setup.py's `authorizationSha256`). That
function lives in the SUT's own adapter module in the canonical scripts (it
is not present in this repository checkout -- the TeaStore candidate-v4
runtime code lives only in the separate runtime worktree), so it is not
literally regression-pinned here.

This module ships a reference implementation SUT adapters are free to
re-export as their own `canonical_sha256` (reducing four-times duplication to
one), and it is what the flow layer in this library uses internally wherever
a hash is needed for the library's own bookkeeping (e.g. locking, contract
identity) rather than a SUT-authored document. It is deliberately
"whatever is deterministic," not "byte-identical to TeaStore's private
choice of separators" -- the property this library actually relies on is
determinism and key-order independence, not a specific digest.
"""
from __future__ import annotations

import hashlib
import json

__all__ = ["canonical_sha256"]


def canonical_sha256(document) -> str:
    """SHA-256 of `document`'s canonical JSON form (sorted keys, compact,
    NaN forbidden). Two calls with the same content but different key order
    or different float/int representation of an equal value hash identically
    only for the former, never the latter -- like every gate document's own
    JSON, this is a content hash, not a structural-equality hash.
    """
    payload = json.dumps(document, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
