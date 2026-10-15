"""The posture-probe guard must DENY, not merely be patchable.

Making `require_probe_receipt` late-bound fixed its testability. That is not
the same as proving it still refuses, and an adversarial panel flagged exactly
that gap (eval_50bc7238...). This file is the negative suite: every predicate
the guard enforces gets a case that must raise.

The precedent is local: a guard hook shipped earlier the same day looked like
enforcement and could not deny, because its command ended in a pipe.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVERS = ROOT / "modules" / "otel-demo" / "drivers"


@pytest.fixture()
def setup_mod():
    sys.path.insert(0, str(DRIVERS))
    spec = importlib.util.spec_from_file_location("otel_campaign_setup_neg", DRIVERS / "campaign_setup.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def good(setup_mod):
    """A receipt that passes every predicate, so each case changes exactly one."""
    return {
        "kind": setup_mod.PROBE_RECEIPT_KIND,
        "result": "PROBE OK",
        "disabledOtlpConnections": 0,
        "enabledOtlpConnections": 43,
        "runtimeAuthorized": False,
        "probeScriptSha256": setup_mod._probe_script_sha256(),
        "upstreamCommit": "PLACEHOLDER",
    }


class _Adapter:
    class runtime:  # noqa: N801
        @staticmethod
        def target_allocation():
            return {"source": {"upstreamCommit": "PLACEHOLDER"}}


def _write(tmp_path, payload):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_absent_receipt_is_refused(setup_mod, tmp_path):
    with pytest.raises(setup_mod.GateDriverError, match="no posture-probe receipt"):
        setup_mod.require_probe_receipt(_Adapter(), tmp_path / "nothing.json")


def test_a_good_receipt_is_accepted(setup_mod, good, tmp_path):
    # The positive case matters: a guard that refuses everything also "denies".
    assert setup_mod.require_probe_receipt(_Adapter(), _write(tmp_path, good))


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "some-other-kind"),
        ("result", "PROBE FAILED"),
        ("disabledOtlpConnections", 1),      # the disabled posture must be silent
        ("enabledOtlpConnections", 0),       # the enabled posture must export
        ("enabledOtlpConnections", "43"),    # and the count must be an int
        ("runtimeAuthorized", True),         # a setup receipt never authorizes runtime
    ],
)
def test_a_dirty_receipt_is_refused(setup_mod, good, tmp_path, field, value):
    good[field] = value
    with pytest.raises(setup_mod.GateDriverError, match="not a clean two-posture pass"):
        setup_mod.require_probe_receipt(_Adapter(), _write(tmp_path, good))


def test_receipt_for_other_probe_script_bytes_is_refused(setup_mod, good, tmp_path):
    good["probeScriptSha256"] = "0" * 64
    with pytest.raises(setup_mod.GateDriverError, match="different probe-script bytes"):
        setup_mod.require_probe_receipt(_Adapter(), _write(tmp_path, good))


def test_receipt_for_other_upstream_pin_is_refused(setup_mod, good, tmp_path):
    good["upstreamCommit"] = "deadbeef" * 5
    with pytest.raises(setup_mod.GateDriverError, match="different upstream pin"):
        setup_mod.require_probe_receipt(_Adapter(), _write(tmp_path, good))
