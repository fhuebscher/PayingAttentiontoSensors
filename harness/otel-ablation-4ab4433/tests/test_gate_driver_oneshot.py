from obsplacement.gate_driver.oneshot import run_oneshot


def test_happy_path_calls_refresh_dryrun_execute_in_order_with_typed_text():
    calls = []

    def refresh():
        calls.append("refresh")
        return 0

    def dryrun():
        calls.append("dryrun")
        return 0

    def execute(typed):
        calls.append(("execute", typed))
        return 0

    outcome = run_oneshot(refresh, dryrun, execute, prompt=lambda _: "  APPROVE GATE-RUN ...  ",
                           announce=None)
    assert outcome.returncode == 0
    assert outcome.stage == "execute"
    assert calls == ["refresh", "dryrun", ("execute", "APPROVE GATE-RUN ...")]


def test_refresh_failure_aborts_before_dryrun_or_prompt():
    calls = []

    def refresh():
        calls.append("refresh")
        return 1

    def dryrun():
        calls.append("dryrun")
        return 0

    def prompt(_):
        calls.append("prompt")
        return "typed"

    def execute(typed):
        calls.append("execute")
        return 0

    outcome = run_oneshot(refresh, dryrun, execute, prompt=prompt, announce=None)
    assert outcome.returncode == 1
    assert outcome.stage == "refresh"
    assert calls == ["refresh"]


def test_dryrun_failure_aborts_before_prompt_or_execute():
    calls = []
    refresh = lambda: (calls.append("refresh") or 0)
    dryrun = lambda: (calls.append("dryrun") or 1)

    def prompt(_):
        calls.append("prompt")
        return "typed"

    def execute(typed):
        calls.append("execute")
        return 0

    outcome = run_oneshot(refresh, dryrun, execute, prompt=prompt, announce=None)
    assert outcome.returncode == 1
    assert outcome.stage == "dryrun"
    assert calls == ["refresh", "dryrun"]


def test_empty_input_aborts_without_executing():
    executed = []
    outcome = run_oneshot(lambda: 0, lambda: 0, lambda typed: executed.append(typed) or 0,
                           prompt=lambda _: "   ", announce=None)
    assert outcome.returncode == 1
    assert outcome.stage == "aborted-empty-input"
    assert executed == []


def test_eof_on_prompt_aborts_without_executing():
    executed = []

    def prompt(_):
        raise EOFError()

    outcome = run_oneshot(lambda: 0, lambda: 0, lambda typed: executed.append(typed) or 0,
                           prompt=prompt, announce=None)
    assert outcome.returncode == 1
    assert outcome.stage == "aborted-no-input"
    assert executed == []


def test_keyboard_interrupt_on_prompt_aborts_without_executing():
    executed = []

    def prompt(_):
        raise KeyboardInterrupt()

    outcome = run_oneshot(lambda: 0, lambda: 0, lambda typed: executed.append(typed) or 0,
                           prompt=prompt, announce=None)
    assert outcome.returncode == 1
    assert outcome.stage == "aborted-no-input"
    assert executed == []


def test_execute_return_code_is_forwarded_unchanged():
    outcome = run_oneshot(lambda: 0, lambda: 0, lambda typed: 2, prompt=lambda _: "x", announce=None)
    assert outcome.returncode == 2
    assert outcome.stage == "execute"


def test_never_fabricates_the_typed_sentence():
    """run_oneshot must forward exactly what the operator typed, nothing else."""
    seen = {}

    def execute(typed):
        seen["typed"] = typed
        return 0

    run_oneshot(lambda: 0, lambda: 0, execute, prompt=lambda _: "EXACTLY THIS TEXT", announce=None)
    assert seen["typed"] == "EXACTLY THIS TEXT"
