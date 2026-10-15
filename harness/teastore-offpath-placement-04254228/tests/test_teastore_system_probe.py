import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("teastore_system_probe", ROOT / "modules/teastore/collectors/system_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

CID = "a" * 64


def _scope(root: Path, cid: str, usage: int) -> Path:
    scope = root / "system.slice" / ("docker-%s.scope" % cid)
    scope.mkdir(parents=True, exist_ok=True)
    (scope / "cpu.stat").write_text("usage_usec %d\nuser_usec 1\n" % usage)
    (scope / "memory.current").write_text("4096\n")
    (scope / "io.stat").write_text("8:0 rbytes=10 wbytes=20 rios=1 wios=2\n8:16 rbytes=1 wbytes=2\n")
    (scope / "cpu.pressure").write_text("some avg10=0.00 avg60=0.00 avg300=0.00 total=77\nfull avg10=0 total=5\n")
    return scope


def _daemons(root: Path) -> None:
    for unit in probe.DAEMON_UNITS:
        (root / "system.slice" / unit).mkdir(parents=True)
        (root / "system.slice" / unit / "cpu.stat").write_text("usage_usec 500\n")


def test_reads_counters_and_marks_missing_psi_as_none(tmp_path):
    _scope(tmp_path, CID, 1000)
    row = probe.read_scope(tmp_path / "system.slice" / ("docker-%s.scope" % CID))
    assert row == {"cpuUsageUsec": 1000, "memoryCurrent": 4096, "rbytes": 11, "wbytes": 22,
                   "psiCpuSomeTotalUsec": 77, "psiMemorySomeTotalUsec": None, "psiIoSomeTotalUsec": None}


def test_stopped_container_is_null_not_zero_and_restart_is_retained(tmp_path):
    """persistence-crash: the scope disappears while stopped and returns with reset counters."""
    _daemons(tmp_path)
    scope = _scope(tmp_path, CID, 9000)
    ticks = iter([0.0, 5.0, 10.0])

    def clock():
        return now[0]

    now = [0.0]

    def sleep(seconds):
        now[0] += seconds
        t = next(ticks, None)
        if t == 5.0:        # stopped between the first and second sample
            for f in scope.iterdir():
                f.unlink()
            scope.rmdir()
        if t == 10.0:       # restarted, counter reset
            _scope(tmp_path, CID, 40)

    samples = probe.run(tmp_path, {"persistence": CID}, 0.0, 10.0, 5.0, clock=clock, sleep=sleep)
    assert [s["services"]["persistence"] and s["services"]["persistence"]["cpuUsageUsec"] for s in samples] == [9000, None, 40]
    assert all(s["daemons"] == {"docker.service": 500, "containerd.service": 500} for s in samples)
    assert len(samples) == 3 and samples[1]["services"]["persistence"] is None


def test_sample_count_covers_both_window_edges(tmp_path):
    _daemons(tmp_path)
    _scope(tmp_path, CID, 1)
    now = [100.0]
    samples = probe.run(tmp_path, {"auth": CID}, 100.0, 600.0, 5.0, clock=lambda: now[0],
                        sleep=lambda s: now.__setitem__(0, now[0] + s))
    assert len(samples) == 121 and samples[0]["epoch"] == 100.0 and samples[-1]["epoch"] == 700.0
