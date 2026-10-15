"""The packet capture's start/stop lifecycle, exercised for real.

Defect twelve blocked cell 1 of the first OTel run: ``stop_capture`` sent SIGINT
to the ``sudo`` it held a handle on, which never reached the ``tcpdump``
grandchild, and then hung in ``communicate()`` because that surviving grandchild
still held the inherited stdout/stderr pipes open.  Nothing in the suite touched
``start_capture`` or ``stop_capture``, so a green suite said nothing about it.

These tests run a real process tree of the same shape -- a parent that outlives
a forked child, both in one process group, the child holding the inherited
output descriptors -- and assert the whole group is reaped.  The privileged half
(``sudo``, the drop to the ``tcpdump`` account) cannot be built on a developer
machine, so it is a stand-in for privilege, not for process structure: the
signal delivery, the group membership and the descriptor ownership are genuine.

The tree runs inside a driver subprocess placed in its own session, so that a
regression which makes ``stop_capture`` signal the wrong process group cannot
take the test runner down with it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "modules/otel-demo/execution/candidate_remote.py"


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


remote = _load("otel_capture_lifecycle_remote", REMOTE)


# The stand-in for `sudo tcpdump`.  The parent plays sudo: it ignores SIGINT and
# exits with its child's status.  The child plays tcpdump: it holds the
# inherited stdout/stderr open, records its pid, and exits 0 on SIGINT the way
# tcpdump does when it has flushed its savefile.  Signalling only the parent
# therefore leaves the child running -- which is exactly the failure being
# guarded against, and is what makes this test able to fail.
STAND_IN = r"""
import os, signal, sys, time
pid_path = sys.argv[1]
child = os.fork()
if child == 0:
    signal.signal(signal.SIGINT, lambda *_: (os.write(2, b"child caught SIGINT\n"), os._exit(0)))
    with open(pid_path, "w") as handle:
        handle.write(str(os.getpid()))
    os.write(2, b"child up\n")
    while True:
        time.sleep(3600)
signal.signal(signal.SIGINT, signal.SIG_IGN)
os.write(2, b"parent up\n")
_, status = os.waitpid(child, 0)
os._exit(os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else 0)
"""


# Runs in its own session.  Calls the real `start_capture`, substituting only
# the argv, so the kwargs under test -- start_new_session, the file-backed
# stdout, stderr redirected onto it -- are the ones production passes.
DRIVER = r"""
import importlib.util, json, os, subprocess, sys, time
from pathlib import Path

root, remote_rel, stand_in, pid_path, pcap_path, out_path = sys.argv[1:7]
spec = importlib.util.spec_from_file_location("driver_remote", Path(root) / remote_rel)
remote = importlib.util.module_from_spec(spec)
sys.modules["driver_remote"] = remote
spec.loader.exec_module(remote)

# Already a session leader: the test launched this driver with
# start_new_session=True, which is what keeps a misdirected killpg away from
# the test runner.  Assert it rather than calling setsid() again.
assert os.getsid(0) == os.getpid(), "driver is not isolated in its own session"

recorded = {}
real_popen = subprocess.Popen


class Recorder(real_popen):
    def __init__(self, argv, **kwargs):
        recorded["argv"] = list(argv)
        recorded["start_new_session"] = kwargs.get("start_new_session")
        recorded["stdout_is_pipe"] = kwargs.get("stdout") == subprocess.PIPE
        recorded["stdout_is_fd"] = isinstance(kwargs.get("stdout"), int) and kwargs.get("stdout") != subprocess.PIPE
        recorded["stderr_to_stdout"] = kwargs.get("stderr") == subprocess.STDOUT
        super().__init__([sys.executable, "-c", stand_in, pid_path], **kwargs)


subprocess.Popen = Recorder
try:
    capture = remote.start_capture(Path(pcap_path))
finally:
    subprocess.Popen = real_popen

deadline = time.time() + 10
while not os.path.exists(pid_path) and time.time() < deadline:
    time.sleep(0.05)
child_pid = int(Path(pid_path).read_text())

result = {"recorded": recorded, "child_pid": child_pid, "log": str(capture.log)}
started = time.time()
try:
    remote.stop_capture(capture)
    result["error"] = None
except Exception as exc:
    result["error"] = "%s: %s" % (type(exc).__name__, exc)
result["elapsed"] = round(time.time() - started, 2)
result["returncode"] = capture.process.poll()
result["log_removed"] = not os.path.exists(capture.log)

time.sleep(0.3)
try:
    os.kill(child_pid, 0)
    result["child_alive"] = True
except ProcessLookupError:
    result["child_alive"] = False
except PermissionError:
    result["child_alive"] = True

Path(out_path).write_text(json.dumps(result))
"""


@pytest.fixture(scope="module")
def lifecycle(tmp_path_factory) -> dict:
    """Run the real start/stop pair against a real process tree, once."""
    workdir = tmp_path_factory.mktemp("capture-lifecycle")
    pid_path = workdir / "child.pid"
    pcap_path = workdir / "telemetry.pcap"
    out_path = workdir / "result.json"
    completed = subprocess.run(
        [
            sys.executable, "-c", DRIVER, str(ROOT), REMOTE, STAND_IN,
            str(pid_path), str(pcap_path), str(out_path),
        ],
        capture_output=True, text=True, timeout=180, start_new_session=True,
    )
    assert out_path.exists(), (
        "capture lifecycle driver produced no result\n"
        f"stdout: {completed.stdout}\nstderr: {completed.stderr}"
    )
    result = json.loads(out_path.read_text())
    result["_pcap_parent"] = str(workdir)
    return result


def test_stop_capture_reaps_the_whole_process_group(lifecycle: dict) -> None:
    """The child that outlives its parent must not outlive the capture.

    This is the defect itself.  Signalling only ``capture.process`` leaves the
    child running, and this assertion is what catches that.
    """
    assert lifecycle["child_alive"] is False, (
        "the privilege-dropped grandchild survived stop_capture; on the target "
        "it would keep writing to the pcap and could not be signalled, because "
        "/proc is hidepid=invisible"
    )


def test_stop_capture_does_not_hang_and_reports_a_clean_stop(lifecycle: dict) -> None:
    """A clean SIGINT stop, not a SIGKILL escalation.

    A stop that had to escalate would take at least 30 s and truncate the
    savefile, so the elapsed bound and the exit status are both load-bearing.
    """
    assert lifecycle["error"] is None, lifecycle["error"]
    assert lifecycle["returncode"] == 0, lifecycle["returncode"]
    assert lifecycle["elapsed"] < 20, (
        f"stop_capture took {lifecycle['elapsed']}s, so SIGINT did not reach the "
        "capturing process and the SIGKILL escalation ran"
    )


def test_capture_output_never_goes_to_a_pipe(lifecycle: dict) -> None:
    """The other half of the defect: pipe ownership.

    ``communicate()`` waits for EOF on the inherited descriptors.  A surviving
    grandchild holds the write end open forever, so a pipe makes the hang
    possible at all.  A file has no such owner.
    """
    recorded = lifecycle["recorded"]
    assert recorded["stdout_is_pipe"] is False, "tcpdump stdout is a pipe again"
    assert recorded["stdout_is_fd"] is True, "tcpdump stdout is not a file descriptor"
    assert recorded["stderr_to_stdout"] is True, "tcpdump stderr is not folded onto stdout"


def test_capture_runs_in_its_own_process_group(lifecycle: dict) -> None:
    """Without a session of its own there is no group safe to signal."""
    assert lifecycle["recorded"]["start_new_session"] is True


def test_capture_drops_to_the_invoking_user_so_the_pcap_can_be_read_back(lifecycle: dict) -> None:
    """``-Z`` decides who owns the pcap.

    Without it tcpdump drops to its packaged ``tcpdump`` account and writes the
    capture 0600 ``tcpdump:tcpdump``.  ``telemetry_bytes`` then cannot sha256 it
    and ``tshark`` cannot read it, which fails the cell after the measurement
    window has already been spent.
    """
    import pwd

    argv = lifecycle["recorded"]["argv"]
    assert "-Z" in argv, "tcpdump is not told which user to drop to"
    assert argv[argv.index("-Z") + 1] == pwd.getpwuid(os.geteuid()).pw_name
    assert argv[:3] == ["sudo", "-n", "tcpdump"]
    assert "-w" in argv and argv[argv.index("-w") + 1].endswith("telemetry.pcap")


def test_capture_log_is_not_emitted_into_the_cell_artifact_root(lifecycle: dict) -> None:
    """What a cell emits is preregistered; a debug log is not on that list."""
    assert Path(lifecycle["log"]).parent != Path(lifecycle["_pcap_parent"])
    assert lifecycle["log_removed"] is True, "the tcpdump log was left behind"
