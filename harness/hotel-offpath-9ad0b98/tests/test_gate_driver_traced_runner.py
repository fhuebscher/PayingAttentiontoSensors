from obsplacement.gate_driver.traced_runner import traced_runner


class Result:
    def __init__(self, returncode=0, stdout=b"out", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_traced_runner_returns_the_underlying_result_unchanged(tmp_path):
    def fake_runner(argv, data=None):
        return Result(returncode=0, stdout=b"hello")

    runner = traced_runner(fake_runner, tmp_path / "trace.log")
    result = runner(["cmd", "arg"])
    assert result.returncode == 0
    assert result.stdout == b"hello"


def test_traced_runner_writes_argv_and_return_code(tmp_path):
    def fake_runner(argv, data=None):
        return Result(returncode=7)

    runner = traced_runner(fake_runner, tmp_path / "trace.log")
    runner(["ssh", "root@host", "do-thing"])
    text = (tmp_path / "trace.log").read_text()
    assert "argv:" in text
    assert "root@host" in text
    assert "rc=7" in text


def test_traced_runner_decodes_and_records_both_streams(tmp_path):
    def fake_runner(argv, data=None):
        return Result(stdout=b"stdout line", stderr=b"stderr line")

    runner = traced_runner(fake_runner, tmp_path / "trace.log")
    runner(["cmd"])
    text = (tmp_path / "trace.log").read_text()
    assert "stdout line" in text
    assert "stderr line" in text


def test_traced_runner_appends_across_multiple_calls(tmp_path):
    def fake_runner(argv, data=None):
        return Result()

    runner = traced_runner(fake_runner, tmp_path / "trace.log")
    runner(["first"])
    runner(["second"])
    text = (tmp_path / "trace.log").read_text()
    assert "first" in text and "second" in text
    assert text.count("argv:") == 2


def test_traced_runner_truncates_streams_when_stream_limit_set(tmp_path):
    def fake_runner(argv, data=None):
        return Result(stdout=b"x" * 100)

    runner = traced_runner(fake_runner, tmp_path / "trace.log", stream_limit=10)
    runner(["cmd"])
    text = (tmp_path / "trace.log").read_text()
    assert "x" * 100 not in text
    assert "x" * 10 in text


def test_traced_runner_forwards_data_argument(tmp_path):
    received = {}

    def fake_runner(argv, data=None):
        received["data"] = data
        return Result()

    runner = traced_runner(fake_runner, tmp_path / "trace.log")
    runner(["cmd"], data=b"payload")
    assert received["data"] == b"payload"
