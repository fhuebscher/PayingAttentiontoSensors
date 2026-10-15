"""Where Hotel's driver config, its shims and the shared library actually meet.

`tests/test_hotel_gate_driver_shims.py` proves the shims against the
orchestrator's validators; `tests/test_hotel_gate_driver_config.py` proves the
config object in isolation. Neither exercised a library flow *through* the
shims, which is how three mating faults survived both suites (a binding shape
the library did not read, a readiness timestamp field it did not know, and a
transport user the config stated but the orchestrator never used). Each test
here crosses that seam once.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from obsplacement.gate_driver.campaign_authorization import invariants_for, setup_campaign_text
from obsplacement.gate_driver.contract import campaign_identity
from obsplacement.gate_driver.freshness import parse

ROOT = Path(__file__).parents[1]
DRIVERS = ROOT / "modules/hotel-reservation/drivers"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


config_module = load("hotel_mating_config", DRIVERS / "gate_driver_config.py")
adapter = load(
    "hotel_mating_adapter",
    ROOT / "modules/hotel-reservation/execution/candidate_runtime_adapter.py",
)
runtime = adapter.runtime
CONFIG = config_module.CONFIG


def hotel_bindings():
    ceiling = runtime.posture_ceiling()
    return runtime.Bindings(
        framework_commit="a" * 40, framework_tree="b" * 40,
        descriptor_sha256="c" * 64, compiled_plan_sha256="d" * 64,
        runtime_policy_sha256="e" * 64,
        controller_sha256={key: "f" * 64 for key in runtime.CONTROLLER_PATHS},
        run_count=24,
        unsupported_postures=tuple(ceiling["unsupportedPostures"]),
        source_cost_comparison_state=ceiling["sourceCostComparisonState"],
    )


def test_setup_campaign_sentence_derives_from_hotel_bindings():
    """`propose-campaign` used to raise AttributeError here: the library read
    TeaStore's `plan_sha256` / `run_ids` off a Hotel `Bindings`."""
    bindings = hotel_bindings()
    identity = campaign_identity(bindings)
    assert (identity.descriptor_sha256, identity.plan_sha256, identity.run_count) == (
        "c" * 64, "d" * 64, 24,
    )
    sentence = setup_campaign_text(CONFIG, bindings, "2026-09-06T00:00:00Z")
    assert "plan=" + "d" * 64 in sentence and "runs=24" in sentence
    assert "transport-user=root execution-user=fhuebscher" in sentence
    assert invariants_for(CONFIG, bindings)["runs"] == 24


def test_config_transport_and_execution_users_are_the_orchestrators(tmp_path):
    """D10: the sentence must state the transport the orchestrator takes."""
    assert CONFIG.transport_user == runtime.TARGET["transportUser"] == "root"
    assert CONFIG.execution_user == runtime.TARGET["executionUser"] == "fhuebscher"
    assert runtime.TARGET["executionUid"] == 1007


def test_adapter_names_hotel_readiness_timestamp_and_the_library_can_parse_it():
    """Hotel stamps `observedAt` with microseconds; the library's freshness
    window is measured against exactly this value."""
    moment = datetime(2026, 9, 5, 12, 34, 56, 123456, tzinfo=timezone.utc)
    readiness = {"observedAt": moment.isoformat().replace("+00:00", "Z")}
    captured = adapter.preflight_captured_at(readiness)
    assert captured == "2026-09-05T12:34:56.123456Z"
    assert parse(captured) == moment
    with pytest.raises(runtime.GateError):
        adapter.preflight_captured_at({"capturedAt": "2026-09-05T12:34:56Z"})


def test_driver_scratch_lives_under_the_gitignored_local_tree():
    """Traces and dry-run probes beside the scripts would dirty the runtime
    worktree and trip `_verify_git` on the next derivation."""
    scratch = config_module.DRIVER_SCRATCH
    assert scratch.is_relative_to(CONFIG.root / ".local")
    for name in ("gate_setup.py", "gate_run.py", "campaign_setup.py"):
        text = (DRIVERS / name).read_text()
        assert 'Path(__file__).parent / "' not in text, f"{name} writes beside itself"


def test_run_authorization_carries_the_keys_the_gate_run_driver_prints():
    """gate_run.py reports Hotel's binding keys, not TeaStore's
    (runCount/authorizedRunIds/oneShot/authorizationDeadline)."""
    gate_run_text = (DRIVERS / "gate_run.py").read_text()
    for teastore_only in ("runCount", "authorizedRunIds", "oneShot", "authorizationDeadline"):
        assert teastore_only not in gate_run_text
    sample = {
        "campaignId": "hotel-v1-20260905t000000z-deadbeef",
        "compiledPlanCanonicalSha256": "d" * 64,
        "readinessCaptureId": "hotel-readiness-v1-20260905t000000z-deadbeef",
        "readinessObservedAt": "2026-09-05T00:00:00Z",
        "deadline": "2026-09-05T05:00:00Z",
    }
    for key in ("campaignId", "compiledPlanCanonicalSha256", "readinessCaptureId",
                "readinessObservedAt", "deadline"):
        assert f"authorization['{key}']" in gate_run_text
        assert key in sample
