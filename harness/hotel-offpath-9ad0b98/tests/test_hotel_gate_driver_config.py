"""Structural tests for Hotel Reservation's gate-driver wiring
(modules/hotel-reservation/drivers/). These do not (and cannot) exercise a
real GATE-SETUP/GATE-RUN chain -- that needs a clean runtime worktree, a real
target host, and typed human approvals. What is tested:

  1. The per-SUT configuration itself (target host, users, posture ceiling,
     run window) is correct and enforces the posture ceiling.
  2. The four driver scripts are syntactically valid, import cleanly, and
     wire up the shared library's paths/flows correctly.
  3. A `SutConfig` whose adapter/transport modules are missing or incomplete
     fails closed with a clean, typed error (`ModuleLoadError` /
     `ContractViolation`) rather than an obscure crash three calls deep.
  4. Hotel's real adapter/transport shims -- which live in the runtime
     worktree named by `CONFIG.root`, not in this checkout -- satisfy the
     contract, and the gates directory they hardcode is the one this config
     declares. Those tests skip when that worktree is not present, since it
     is a sibling checkout rather than a dependency of this repository.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from obsplacement.gate_driver.contract import (
    SutConfig,
    check_adapter_contract,
    check_transport_contract,
)
from obsplacement.gate_driver.errors import ContractViolation, ModuleLoadError
from obsplacement.gate_driver.module_loader import load_sut_module

DRIVERS_DIR = Path(__file__).parents[1] / "modules/hotel-reservation/drivers"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, DRIVERS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def hotel_config():
    return load("hotel_gate_driver_config_under_test", "gate_driver_config.py").CONFIG


def runtime_worktree_or_skip():
    """The Hotel orchestrator worktree, or a skip if it is not checked out."""
    config = hotel_config()
    adapter_path = config.root / config.adapter_module
    if not adapter_path.is_file():
        pytest.skip(f"Hotel runtime worktree is not present at {config.root}")
    return config


def test_hotel_config_targets_the_correct_host_and_execution_user():
    config_module = load("hotel_gate_driver_config_under_test", "gate_driver_config.py")
    config = config_module.CONFIG
    assert config.target_host == "fb14srv4"
    assert config.execution_user == "fhuebscher"
    assert config.execution_user != "stig"  # explicit non-negotiable from the task brief


def test_hotel_config_posture_ceiling_admits_selected_and_excludes_source_off():
    config_module = load("hotel_gate_driver_config_under_test", "gate_driver_config.py")
    config = config_module.CONFIG
    assert config.supported_postures == frozenset({"none", "metrics", "selected", "full"})
    config.validate_postures(["none", "metrics", "selected", "full"])  # must not raise
    # The retired v1 rung and the LMT pilot's `logs` rung are not part of this ladder.
    for retired in ("sample-zero", "logs", "source-off"):
        with pytest.raises(ValueError):
            config.validate_postures([retired])


def test_hotel_config_is_a_single_thin_object_not_a_reimplementation():
    """The per-SUT file must configure, not reimplement, governance logic:
    no gate/sentence/campaign vocabulary should appear in it at all."""
    text = (DRIVERS_DIR / "gate_driver_config.py").read_text()
    forbidden_governance_terms = ("def cmd_", "def verify_", "typed.strip()", "SentenceMismatch")
    for term in forbidden_governance_terms:
        assert term not in text


@pytest.mark.parametrize("filename", [
    "gate_setup.py", "gate_run.py", "campaign_setup.py", "campaign_status.py",
])
def test_hotel_driver_script_imports_cleanly_and_exposes_main(filename):
    module = load(f"hotel_driver_under_test_{filename}", filename)
    assert callable(module.main)
    assert module.CONFIG.slug == "hotel-reservation"
    assert module.PATHS.gates_dir == module.CONFIG.gates_dir


def test_a_missing_adapter_or_transport_module_fails_closed(tmp_path):
    """A `SutConfig` pointing at a root with no SUT modules must raise a clean,
    typed `ModuleLoadError`, not an `AttributeError` three calls deep.

    This used to be asserted by calling a driver subcommand against Hotel's
    real config, back when the adapter/transport files genuinely did not
    exist. They exist now, so that route would load them and do real work
    (creating directories in the runtime worktree and shelling out to git);
    the guarantee is exercised against a throwaway root instead.
    """
    empty = tmp_path / "empty-runtime-root"
    empty.mkdir()
    for relative in ("modules/absent/adapter.py", "modules/absent/transport.py"):
        with pytest.raises(ModuleLoadError):
            load_sut_module(empty, relative, "absent_module_under_test")


def test_an_incomplete_adapter_or_transport_names_every_missing_member(tmp_path):
    """`ContractViolation` must name what is missing -- the whole reason the
    contract is probed up front rather than discovered mid-mutation."""
    module_dir = tmp_path / "modules/partial/execution"
    module_dir.mkdir(parents=True)
    (module_dir / "adapter.py").write_text("PLAN_KIND = 'partial-gate-plan-v1'\n")
    (module_dir / "transport.py").write_text("def subprocess_runner(argv, data=None): ...\n")
    adapter = load_sut_module(tmp_path, "modules/partial/execution/adapter.py", "partial_adapter")
    transport = load_sut_module(tmp_path, "modules/partial/execution/transport.py", "partial_transport")
    with pytest.raises(ContractViolation) as adapter_violation:
        check_adapter_contract(adapter, label="modules/partial/execution/adapter.py")
    with pytest.raises(ContractViolation) as transport_violation:
        check_transport_contract(transport, label="modules/partial/execution/transport.py")
    assert "SETUP_KIND" in adapter_violation.value.missing
    assert "inspect_campaign" in adapter_violation.value.missing
    assert "PLAN_KIND" not in adapter_violation.value.missing
    assert "BoundedCampaignController" in transport_violation.value.missing
    assert "subprocess_runner" not in transport_violation.value.missing


def test_hotel_config_run_window_is_five_hours_not_eleven():
    """`SutConfig.run_window_hours` defaults to 11, which is TeaStore's number.

    Hotel's runtime-policy.json bounds a GATE-RUN deadline to
    [17700, 18005] seconds; an 11-hour deadline is refused by
    `candidate_runtime.validate_gate_run` every time.
    """
    # The frozen epoch's window is 5 h; with a selector committed at ROOT it is that epoch's derived window:
    # the traffic sweep's 6 h (64 cells), the quiet calibration's 4 h (40 cells; decision 48), the off-path epoch's
    # 3 h (30 cells).
    selector = hotel_config().root / "modules/hotel-reservation/execution/study-epoch.json"
    epoch = json.loads(selector.read_text())["studyEpoch"] if selector.exists() else None
    assert hotel_config().run_window_hours == {
        None: 5, "hotel-traffic-sweep-v1": 6, "hotel-quiet-calibration-v1": 4, "hotel-offpath-v1": 3,
    }[epoch]
    assert SutConfig.__dataclass_fields__["run_window_hours"].default == 11


def test_validate_postures_rejects_unsupported_before_any_sentence(tmp_path):
    """An unsupported posture (source-off, or the retired `logs` rung) is refused
    before anything is written to the gates directory."""
    config = hotel_config()

    def gates_snapshot():
        # The gates directory legitimately holds documents once a real chain
        # has started (propose-campaign / prepare write there); what must
        # hold is that the refusal itself writes nothing, not that the
        # directory is empty.
        if not config.gates_dir.exists():
            return None
        return sorted((path.name, path.stat().st_mtime_ns) for path in config.gates_dir.iterdir())

    before = gates_snapshot()
    for posture in ("source-off", "logs"):
        with pytest.raises(ValueError, match="unsupported"):
            config.validate_postures({posture})
        with pytest.raises(ValueError, match="unsupported"):
            config.validate_postures({"full", posture})
    assert gates_snapshot() == before


def test_hotel_shims_satisfy_the_adapter_and_transport_contract():
    config = runtime_worktree_or_skip()
    adapter = load_sut_module(
        config.root, config.adapter_module, "hotel_candidate_runtime_adapter_under_test",
    )
    transport = load_sut_module(
        config.root, config.transport_module, "hotel_candidate_transport_under_test",
    )
    check_adapter_contract(adapter, label=config.adapter_module)
    check_transport_contract(transport, label=config.transport_module)


def test_hotel_adapter_gates_directory_matches_this_config():
    """The adapter shim hardcodes the gates directory (it cannot import this
    file across worktrees). A rebind of one without the other must fail a test
    rather than a campaign."""
    config = runtime_worktree_or_skip()
    adapter = load_sut_module(
        config.root, config.adapter_module, "hotel_candidate_runtime_adapter_under_test",
    )
    assert Path(adapter.GATES_DIR) == config.gates_dir
    assert adapter.EXECUTION_USER == config.execution_user


def test_hotel_installer_module_declares_release_binding_keys():
    """Property #2: the driver sources the key set from the installed module,
    so the module must actually declare one."""
    config = runtime_worktree_or_skip()
    from obsplacement.gate_driver.module_loader import load_binding_keys

    keys = load_binding_keys(config.root, config.installer_module)
    assert keys and len(set(keys)) == len(keys)
    assert "setupId" in keys


def test_hotel_driver_scripts_never_author_a_typed_sentence():
    """Static check on the seam: none of Hotel's driver scripts may construct
    an approval sentence themselves -- every 'expected'/'sentence' value must
    flow from the adapter or from obsplacement.gate_driver, never from a
    literal f-string assembled in the driver script itself."""
    for filename in ("gate_setup.py", "gate_run.py", "campaign_setup.py"):
        text = (DRIVERS_DIR / filename).read_text()
        # Human-readable prompts like "TO RE-APPROVE GATE-PLAN:" are fine --
        # what must never appear is an f-string that *builds* a sentence.
        assert 'f"APPROVE' not in text and "f'APPROVE" not in text, (
            f"{filename} must not construct sentence text itself"
        )
