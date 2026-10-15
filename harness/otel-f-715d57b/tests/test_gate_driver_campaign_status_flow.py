from obsplacement.gate_driver.campaign_status_flow import poll_once
from obsplacement.gate_driver.gate_paths import GatePaths
from obsplacement.gate_driver.json_io import write_json

from gate_driver_fakes import FakeTransport, make_config


def test_poll_once_reports_non_terminal_while_running(tmp_path):
    config = make_config(tmp_path)
    paths = GatePaths(config.gates_dir)
    write_json(paths.runtime_package, {"campaignId": "fake", "setupId": "abc"})
    transport = FakeTransport(status_document={
        "state": "running", "systemdState": {"activeState": "active"},
        "terminalExists": False, "abortExists": False,
    })
    result = poll_once(config, transport, paths)
    assert result.terminal is False
    assert result.status["state"] == "running"


def test_poll_once_reports_terminal_on_abort_flag(tmp_path):
    config = make_config(tmp_path)
    paths = GatePaths(config.gates_dir)
    write_json(paths.runtime_package, {"campaignId": "fake", "setupId": "abc"})
    transport = FakeTransport(status_document={
        "state": "running", "systemdState": {"activeState": "active"},
        "terminalExists": False, "abortExists": True,
    })
    result = poll_once(config, transport, paths)
    assert result.terminal is True


def test_poll_once_hashes_the_exact_bytes_on_disk(tmp_path):
    """campaign_status.py hashes runtime-package.json's bytes directly
    (campaign_status.py:17), not a re-serialization -- the remote endpoint
    is keyed on that exact hash."""
    import hashlib

    config = make_config(tmp_path)
    paths = GatePaths(config.gates_dir)
    write_json(paths.runtime_package, {"campaignId": "fake", "setupId": "abc"})
    expected_sha = hashlib.sha256(paths.runtime_package.read_bytes()).hexdigest()

    seen = {}

    class RecordingTransport(FakeTransport):
        def remote_status(self, remote_input, package_sha256):
            seen["sha"] = package_sha256
            return super().remote_status(remote_input, package_sha256)

    poll_once(config, RecordingTransport(), paths)
    assert seen["sha"] == expected_sha
