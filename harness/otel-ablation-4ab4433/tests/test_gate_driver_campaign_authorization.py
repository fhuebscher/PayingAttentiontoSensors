from datetime import datetime, timezone

import pytest

from obsplacement.gate_driver.campaign_authorization import (
    build_campaign_record,
    build_pending_document,
    invariants_for,
    setup_campaign_text,
    verify_live_invariants,
)
from obsplacement.gate_driver.errors import CampaignDrift, CampaignExpired
from obsplacement.gate_driver.sentence import SentenceMismatch

from gate_driver_fakes import FakeBindings, make_config


def teastore_like_config(tmp_path):
    """Config whose bound values reproduce TeaStore's campaign_setup.py constants."""
    return make_config(
        tmp_path, slug="teastore",
        study="teastore-candidate-pilot-v1",
        change="admit-teastore-candidate-runtime",
        target_host="fb14srv5", transport_user="root", execution_user="stig",
    )


def test_setup_campaign_text_matches_teastore_wording_byte_for_byte(tmp_path):
    """Regression pin against campaign_setup.py's `campaign_text()`
    (campaign_setup.py:106-114) -- the parameterized version must reproduce
    the exact battle-tested string when given TeaStore's own bound values."""
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(
        framework_commit="e29e6664e3647e17646c979100964f317ac51551",
        run_ids=tuple(
            f"b{block:02d}-{posture}-a{rep:02d}"
            for block in range(1, 4)
            for posture in ("selected", "none", "full")
            for rep in range(1, 4)
        ),
        descriptor_sha256="5dcb633fabc",
        plan_sha256="de436f23def",
    )
    deadline = "2026-09-04T14:28:16Z"
    text = setup_campaign_text(config, bindings, deadline)
    assert text == (
        "APPROVE SETUP-CAMPAIGN study=teastore-candidate-pilot-v1 "
        "change=admit-teastore-candidate-runtime "
        "descriptor=5dcb633fabc plan=de436f23def "
        "runs=27 target=fb14srv5 transport-user=root "
        "execution-user=stig zero-experimental-cells framework-may-advance "
        "runtime-not-authorized deadline=2026-09-04T14:28:16Z"
    )


def test_setup_campaign_text_uses_hotel_values_when_given_a_hotel_config(tmp_path):
    """Same grammar, different bound values -- proves the parameterization
    actually varies with `config`, not just TeaStore's."""
    config = make_config(
        tmp_path, slug="hotel-reservation",
        study="hotel-reservation-candidate-pilot-v1",
        change="admit-hotel-reservation-candidate-runtime",
        target_host="fb14srv4", transport_user="root", execution_user="fhuebscher",
        supported_postures=frozenset({"full", "sample-zero"}),
    )
    bindings = FakeBindings(framework_commit="90b9989", run_ids=("full-a01", "sample-zero-a01"))
    text = setup_campaign_text(config, bindings, "2026-09-05T00:00:00Z")
    assert "target=fb14srv4" in text
    assert "transport-user=root" in text
    assert "execution-user=fhuebscher" in text
    assert "execution-user=stig" not in text
    assert "study=hotel-reservation-candidate-pilot-v1" in text
    assert "runs=2" in text


def test_invariants_pin_zero_experimental_cells_and_runtime_not_authorized(tmp_path):
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(framework_commit="abc123")
    invariants = invariants_for(config, bindings)
    assert invariants["experimentalCellsAuthorized"] == 0
    assert invariants["runtimeAuthorized"] is False


def test_build_pending_document_carries_the_derived_sentence(tmp_path):
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(framework_commit="abc123")
    at = datetime(2026, 9, 4, 3, 0, 0, tzinfo=timezone.utc)
    pending = build_pending_document(config, bindings, framework_commit="abc123", at=at)
    assert pending["expectedText"] == setup_campaign_text(config, bindings, pending["deadline"])
    assert pending["deadline"] == "2026-09-11T03:00:00Z"  # + setup_campaign_window_hours (168, D22)
    assert pending["frameworkCommitAtProposal"] == "abc123"


def test_build_campaign_record_fails_closed_on_sentence_mismatch(tmp_path):
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(framework_commit="abc123")
    pending = build_pending_document(config, bindings, framework_commit="abc123")
    with pytest.raises(SentenceMismatch):
        build_campaign_record(pending, "not the right sentence at all", approved_by=config.approved_by)


def test_build_campaign_record_succeeds_on_exact_match(tmp_path):
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(framework_commit="abc123")
    pending = build_pending_document(config, bindings, framework_commit="abc123")
    record = build_campaign_record(pending, pending["expectedText"], approved_by=config.approved_by)
    assert record["runtimeAuthorized"] is False
    assert record["promotionAuthorized"] is False
    assert record["invariants"] == pending["invariants"]


def test_verify_live_invariants_raises_campaign_drift_on_any_change(tmp_path):
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(framework_commit="abc123", descriptor_sha256="original-desc")
    record = {"invariants": invariants_for(config, bindings),
              "deadline": "2099-01-01T00:00:00Z"}
    drifted_bindings = FakeBindings(framework_commit="abc123", descriptor_sha256="different-desc")
    with pytest.raises(CampaignDrift) as excinfo:
        verify_live_invariants(record, config, drifted_bindings)
    assert "descriptorCanonicalSha256" in excinfo.value.drift


def test_verify_live_invariants_raises_campaign_expired_past_deadline(tmp_path):
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(framework_commit="abc123")
    record = {"invariants": invariants_for(config, bindings), "deadline": "2020-01-01T00:00:00Z"}
    with pytest.raises(CampaignExpired):
        verify_live_invariants(record, config, bindings)


def test_verify_live_invariants_passes_when_matching_and_live(tmp_path):
    config = teastore_like_config(tmp_path)
    bindings = FakeBindings(framework_commit="abc123")
    record = {"invariants": invariants_for(config, bindings), "deadline": "2099-01-01T00:00:00Z"}
    verify_live_invariants(record, config, bindings)  # must not raise


def test_verify_live_invariants_allows_framework_commit_to_advance(tmp_path):
    """SETUP-CAMPAIGN explicitly permits the framework commit to advance
    underneath it -- framework_commit is not itself part of invariants_for,
    only descriptor/plan/run-count/target/users are."""
    config = teastore_like_config(tmp_path)
    bindings_v1 = FakeBindings(framework_commit="commit-v1")
    record = {"invariants": invariants_for(config, bindings_v1), "deadline": "2099-01-01T00:00:00Z"}
    bindings_v2 = FakeBindings(framework_commit="commit-v2")  # same descriptor/plan/runs
    verify_live_invariants(record, config, bindings_v2)  # must not raise
