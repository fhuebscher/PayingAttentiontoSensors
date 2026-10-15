import pytest

from obsplacement.gate_driver.terminal_status import is_terminal


def status(state="running", active="active", terminal_exists=False, abort_exists=False):
    return {
        "state": state,
        "systemdState": {"activeState": active},
        "terminalExists": terminal_exists,
        "abortExists": abort_exists,
    }


def test_running_and_active_is_not_terminal():
    assert is_terminal(status()) is False


def test_starting_and_activating_is_not_terminal():
    assert is_terminal(status(state="starting", active="activating")) is False


@pytest.mark.parametrize("state", ["stopped", "failed", "exited", "unknown"])
def test_state_outside_running_vocabulary_is_terminal(state):
    assert is_terminal(status(state=state)) is True


def test_state_comparison_is_case_insensitive():
    assert is_terminal(status(state="RUNNING")) is False
    assert is_terminal(status(state="STOPPED")) is True


def test_terminal_exists_flag_is_terminal_even_if_state_says_running():
    assert is_terminal(status(state="running", terminal_exists=True)) is True


def test_abort_exists_flag_is_terminal_even_if_state_says_running():
    assert is_terminal(status(state="running", abort_exists=True)) is True


def test_systemd_active_state_outside_vocabulary_is_terminal():
    assert is_terminal(status(state="running", active="failed")) is True


def test_missing_systemd_state_defaults_to_unknown_and_is_terminal():
    assert is_terminal({"state": "running"}) is True


def test_missing_state_defaults_to_unknown_and_is_terminal():
    assert is_terminal({}) is True
