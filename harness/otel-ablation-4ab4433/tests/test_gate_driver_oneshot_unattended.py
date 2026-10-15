"""The unattended oneshot route: the harness derives the sentence, nobody types."""
from obsplacement.gate_driver.oneshot import OneshotOutcome, run_oneshot_unattended


def test_unattended_executes_with_the_derived_sentence_after_refresh_and_dryrun():
    calls = []
    outcome = run_oneshot_unattended(
        lambda: calls.append("refresh") or 0,
        lambda: calls.append("dryrun") or 0,
        lambda: "  APPROVE GATE-RUN derived  ",
        lambda typed: calls.append(("execute", typed)) or 0,
        announce=None,
    )
    assert outcome == OneshotOutcome(0, "execute")
    assert calls == ["refresh", "dryrun", ("execute", "APPROVE GATE-RUN derived")]


def test_unattended_aborts_before_deriving_when_refresh_or_dryrun_fails():
    def never():
        raise AssertionError("must not derive or execute")

    assert run_oneshot_unattended(lambda: 1, lambda: 0, never, never, announce=None).stage == "refresh"
    assert run_oneshot_unattended(lambda: 0, lambda: 1, never, never, announce=None).stage == "dryrun"


def test_unattended_aborts_on_an_empty_derivation():
    outcome = run_oneshot_unattended(lambda: 0, lambda: 0, lambda: "   ",
                                      lambda typed: 0, announce=None)
    assert outcome == OneshotOutcome(1, "aborted-empty-input")
