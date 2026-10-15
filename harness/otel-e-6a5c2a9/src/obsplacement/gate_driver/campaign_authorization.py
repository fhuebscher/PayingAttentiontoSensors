"""SETUP-CAMPAIGN: one typed sentence authorizing repeated *setup* attempts.

Generalizes campaign_setup.py's `campaign_text`, `invariants`, and
`require_campaign` (campaign_setup.py:106-157). A SETUP-CAMPAIGN
authorization deliberately never authorizes runtime -- `runtimeAuthorized` is
always `False` and `experimentalCellsAuthorized` is always `0` in its
invariants -- and it pins campaign identity (descriptor, compiled plan, run
count, target, transport user, execution user) while explicitly allowing the
framework commit to advance underneath it. GATE-RUN always requires its own
fresh typed sentence regardless of what SETUP-CAMPAIGN authorization is live
(see gate_run.py's module docstring, gate_run.py:1-16, and this module's
`campaign_authorization` deliberately has no `run_*` functions at all).
"""
from __future__ import annotations

from .contract import SutConfig, campaign_identity
from .errors import CampaignDrift, CampaignExpired
from .freshness import deadline_after, now, parse, stamp
from .sentence import verify_typed_sentence

__all__ = [
    "invariants_for",
    "setup_campaign_text",
    "build_pending_document",
    "build_campaign_record",
    "verify_live_invariants",
]


def invariants_for(config: SutConfig, bindings) -> dict:
    """Everything that must not drift while a SETUP-CAMPAIGN authorization is live.

    Generalizes campaign_setup.py's `invariants()` (campaign_setup.py:
    117-130): every value here previously came from a module-level constant
    (`STUDY`, `CHANGE`, `"fb14srv5"`, `"root"`, `"stig"`) and now comes from
    `config`.
    """
    identity = campaign_identity(bindings)
    return {
        "study": config.study,
        "change": config.change,
        "descriptorCanonicalSha256": identity.descriptor_sha256,
        "compiledPlanCanonicalSha256": identity.plan_sha256,
        "runs": identity.run_count,
        "target": config.target_host,
        "transportUser": config.transport_user,
        "executionUser": config.execution_user,
        "experimentalCellsAuthorized": 0,
        "runtimeAuthorized": False,
    }


def setup_campaign_text(config: SutConfig, bindings, deadline: str) -> str:
    """The exact SETUP-CAMPAIGN sentence grammar, parameterized by `config`.

    Byte-identical to campaign_setup.py's `campaign_text()`
    (campaign_setup.py:106-114) when given TeaStore's own values -- pinned by
    `tests/test_campaign_authorization.py::test_setup_campaign_text_matches_teastore_wording`.
    The wording itself (word order, literal tokens like
    "zero-experimental-cells", "framework-may-advance",
    "runtime-not-authorized") is the universal *grammar* of this governance
    gate; only the bound values are per-SUT.
    """
    identity = campaign_identity(bindings)
    return (
        f"APPROVE SETUP-CAMPAIGN study={config.study} change={config.change} "
        f"descriptor={identity.descriptor_sha256} plan={identity.plan_sha256} "
        f"runs={identity.run_count} target={config.target_host} "
        f"transport-user={config.transport_user} "
        f"execution-user={config.execution_user} zero-experimental-cells "
        f"framework-may-advance runtime-not-authorized deadline={deadline}"
    )


def build_pending_document(config: SutConfig, bindings, *, framework_commit: str,
                            at=None) -> dict:
    """The PENDING document written before a SETUP-CAMPAIGN sentence is typed.

    Generalizes campaign_setup.py's `cmd_propose` body (campaign_setup.py:
    160-180). Deliberately carries `expectedText` (the sentence to be typed,
    never authored by anyone but this derivation) alongside the invariants it
    was derived from and the deadline it commits to.
    """
    moment = at if at is not None else now()
    deadline = deadline_after(config.setup_campaign_window_hours, at=moment)
    return {
        "expectedText": setup_campaign_text(config, bindings, deadline),
        "invariants": invariants_for(config, bindings),
        "deadline": deadline,
        "proposedAt": stamp(moment),
        "frameworkCommitAtProposal": framework_commit,
    }


def build_campaign_record(pending: dict, typed: str, *, approved_by: str,
                           at=None) -> dict:
    """Verify `typed` against `pending["expectedText"]` and build the campaign record.

    Raises `sentence.SentenceMismatch` on any divergence -- never coerces.
    Generalizes campaign_setup.py's `cmd_authorize` (campaign_setup.py:
    183-216) up to (not including) writing the record to disk and appending
    the audit line, both of which are the flow layer's job.
    """
    expected = verify_typed_sentence(typed, pending["expectedText"])
    moment = at if at is not None else now()
    return {
        "schemaVersion": 1,
        "kind": "candidate-setup-campaign-authorization-v1",
        "typedApproval": expected,
        "approvedBy": approved_by,
        "approvedAt": stamp(moment),
        "deadline": pending["deadline"],
        "invariants": pending["invariants"],
        "runtimeAuthorized": False,
        "promotionAuthorized": False,
    }


def verify_live_invariants(record: dict, config: SutConfig, bindings, *, at=None) -> None:
    """Fail closed unless `record` is a live, undrifted SETUP-CAMPAIGN authorization.

    Generalizes the body of campaign_setup.py's `require_campaign()`
    (campaign_setup.py:141-157) that runs once the record file is known to
    exist -- file-existence itself (`NoLiveCampaign`) is the flow layer's
    concern, since it depends on where the SUT keeps its gates directory.
    """
    observed = invariants_for(config, bindings)
    recorded = record.get("invariants", {})
    if recorded != observed:
        drift = {key: (recorded.get(key), observed[key])
                  for key in observed if recorded.get(key) != observed[key]}
        raise CampaignDrift(drift)
    moment = at if at is not None else now()
    if moment >= parse(record["deadline"]):
        raise CampaignExpired(record["deadline"])
