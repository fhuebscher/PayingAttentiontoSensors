import subprocess

import pytest

from obsplacement.gate_driver.contract import (
    SutConfig,
    check_adapter_contract,
    check_transport_contract,
    git_head_commit,
)
from obsplacement.gate_driver.errors import ContractViolation

from gate_driver_fakes import FakeAdapter, FakeTransport, make_config


def test_fake_adapter_and_transport_satisfy_the_contract():
    check_adapter_contract(FakeAdapter())
    check_transport_contract(FakeTransport())


def test_check_adapter_contract_names_every_missing_member():
    class Incomplete:
        PLAN_KIND = "x"
        # everything else missing

    with pytest.raises(ContractViolation) as excinfo:
        check_adapter_contract(Incomplete(), label="incomplete adapter")
    assert "inspect_campaign" in excinfo.value.missing
    assert "canonical_sha256" in excinfo.value.missing
    assert "PLAN_KIND" not in excinfo.value.missing
    assert excinfo.value.module_label == "incomplete adapter"


def test_check_transport_contract_names_every_missing_member():
    class Incomplete:
        subprocess_runner = staticmethod(lambda argv, data=None: None)

    with pytest.raises(ContractViolation) as excinfo:
        check_transport_contract(Incomplete())
    assert "remote_precheck" in excinfo.value.missing
    assert "BoundedCampaignController" in excinfo.value.missing


def test_git_head_commit_reads_from_git(tmp_path):
    subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    subprocess.run(("git", "-C", str(tmp_path), "config", "user.email", "a@example.com"), check=True)
    subprocess.run(("git", "-C", str(tmp_path), "config", "user.name", "Test"), check=True)
    (tmp_path / "file.txt").write_text("hello\n")
    subprocess.run(("git", "-C", str(tmp_path), "add", "file.txt"), check=True)
    subprocess.run(("git", "-C", str(tmp_path), "commit", "-q", "-m", "init"), check=True)
    expected = subprocess.run(
        ("git", "-C", str(tmp_path), "rev-parse", "HEAD"), check=True, capture_output=True,
    ).stdout.decode("ascii").strip()
    assert git_head_commit(tmp_path) == expected


def test_sut_config_requires_non_empty_supported_postures(tmp_path):
    with pytest.raises(ValueError):
        make_config(tmp_path, supported_postures=frozenset())


def test_validate_postures_accepts_supported_subset(tmp_path):
    config = make_config(tmp_path, supported_postures=frozenset({"full", "sample-zero"}))
    config.validate_postures(["full"])
    config.validate_postures(["full", "sample-zero"])


def test_validate_postures_fails_closed_for_unsupported_posture(tmp_path):
    """Hotel's posture shape: only full/sample-zero are supported;
    none/selected are structurally unsupported (no upstream service-level
    source guard), not merely untested."""
    config = make_config(tmp_path, supported_postures=frozenset({"full", "sample-zero"}))
    with pytest.raises(ValueError) as excinfo:
        config.validate_postures(["full", "selected"])
    assert "selected" in str(excinfo.value)


def test_sut_config_is_frozen(tmp_path):
    config = make_config(tmp_path)
    with pytest.raises(Exception):
        config.target_host = "somewhere-else"


def test_campaign_identity_reads_the_teastore_binding_shape():
    from obsplacement.gate_driver.contract import campaign_identity
    from gate_driver_fakes import FakeBindings

    identity = campaign_identity(FakeBindings(framework_commit="c" * 40))
    assert identity.descriptor_sha256 == "desc" + "0" * 60
    assert identity.plan_sha256 == "plan" + "0" * 60
    assert identity.run_count == 3


def test_campaign_identity_reads_the_hotel_binding_shape():
    """Hotel's orchestrator `Bindings` spells the plan digest
    `compiled_plan_sha256` and carries an integer `run_count`, no run ids."""
    from dataclasses import dataclass

    from obsplacement.gate_driver.contract import campaign_identity

    @dataclass(frozen=True)
    class HotelShapedBindings:
        framework_commit: str
        descriptor_sha256: str
        compiled_plan_sha256: str
        run_count: int

    identity = campaign_identity(HotelShapedBindings("c" * 40, "d" * 64, "p" * 64, 24))
    assert identity == identity.__class__("d" * 64, "p" * 64, 24)


def test_campaign_identity_fails_closed_naming_what_is_missing():
    from obsplacement.gate_driver.contract import campaign_identity

    class Bare:
        descriptor_sha256 = "d" * 64

    with pytest.raises(ContractViolation) as excinfo:
        campaign_identity(Bare())
    assert "plan_sha256 | compiled_plan_sha256" in excinfo.value.missing
    assert "run_ids | run_count" in excinfo.value.missing
