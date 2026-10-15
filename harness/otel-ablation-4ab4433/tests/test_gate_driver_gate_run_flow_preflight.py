"""The preflight timestamp is SUT-named and consumed at derivation; the dry
run keys remote status the way the watcher does (spec sections 2.1 / 2.6).

Split out of test_gate_driver_gate_run_flow.py, whose
`bootstrap_through_readiness` fixture is reused here.
"""
import hashlib
from datetime import timedelta

import pytest

from obsplacement.gate_driver.errors import GateDriverError, PreflightExpired
from obsplacement.gate_driver.freshness import PREFLIGHT_MAX_AGE_SECONDS, now, stamp
from obsplacement.gate_driver.gate_run_flow import derive_run_authorization, run_dry_run
from obsplacement.gate_driver.json_io import read_json, write_json

from test_gate_driver_gate_run_flow import FRAMEWORK_COMMIT, bootstrap_through_readiness


def test_derive_records_the_preflight_timestamp_the_adapter_names(tmp_path):
    """Hotel's readiness has `observedAt`, not TeaStore's `capturedAt`; the
    adapter names its field and the receipt records that value."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    readiness = read_json(paths.fetched_readiness_document)
    readiness["observedAt"] = readiness.pop("capturedAt")
    write_json(paths.fetched_readiness_document, readiness)
    adapter.preflight_captured_at = lambda document: document["observedAt"]
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    receipt = read_json(paths.run_authorization_receipt)
    assert receipt["preflightCapturedAt"] == readiness["observedAt"]


def test_derive_fails_closed_when_readiness_carries_no_preflight_timestamp(tmp_path):
    """Previously the receipt recorded `None` and cmd_execute died with a
    TypeError from datetime arithmetic -- a crash, not a refusal."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    readiness = read_json(paths.fetched_readiness_document)
    del readiness["capturedAt"]
    write_json(paths.fetched_readiness_document, readiness)
    with pytest.raises(GateDriverError):
        derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    assert not paths.run_authorization.exists()


def test_derive_refuses_a_preflight_already_outside_the_window(tmp_path):
    """A stale readiness must not become a run authorization whose sentence
    is printed for typing (property #3 applies at derivation, not only at
    execution)."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    readiness = read_json(paths.fetched_readiness_document)
    readiness["capturedAt"] = stamp(now() - timedelta(seconds=PREFLIGHT_MAX_AGE_SECONDS + 60))
    write_json(paths.fetched_readiness_document, readiness)
    with pytest.raises(PreflightExpired):
        derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    assert not paths.run_authorization.exists()


def test_dry_run_keys_remote_status_on_the_digest_poll_once_uses(tmp_path):
    """`campaign_status_flow.poll_once` presents sha256(bytes of
    runtime-package.json as write_json wrote it); the dry run must present
    the same digest for the same document, not canonical_sha256's
    re-serialization (spec section 2.6)."""
    config, paths, adapter, transport = bootstrap_through_readiness(tmp_path)
    derive_run_authorization(config, adapter, paths, framework_commit=FRAMEWORK_COMMIT)
    seen = []

    def remote_status(remote_input, package_sha256):
        seen.append(package_sha256)
        return {"state": "unknown", "systemdState": {"activeState": "inactive"},
                "terminalExists": False, "abortExists": False}

    transport.remote_status = remote_status
    result = run_dry_run(config, adapter, transport, paths, framework_commit=FRAMEWORK_COMMIT,
                          scratch_dir=tmp_path / "dryrun")
    assert result.ok is True
    write_json(paths.runtime_package, result.remote_input)
    assert seen == [hashlib.sha256(paths.runtime_package.read_bytes()).hexdigest()]
