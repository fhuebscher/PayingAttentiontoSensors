import os

import pytest

from obsplacement.gate_driver.errors import ConcurrentRunError, PathAlreadyExists
from obsplacement.gate_driver.fs_guards import SingleFlightLock, archive_live_documents, refuse_existing


def test_refuse_existing_passes_for_a_new_path(tmp_path):
    refuse_existing(tmp_path / "does-not-exist.json")  # must not raise


def test_refuse_existing_raises_for_a_file(tmp_path):
    target = tmp_path / "gate-plan.json"
    target.write_text("{}")
    with pytest.raises(PathAlreadyExists) as excinfo:
        refuse_existing(target)
    assert excinfo.value.path == target


def test_refuse_existing_raises_for_a_directory(tmp_path):
    target = tmp_path / "fetched-readiness"
    target.mkdir()
    with pytest.raises(PathAlreadyExists):
        refuse_existing(target)


def test_refuse_existing_raises_for_a_dangling_symlink(tmp_path):
    target = tmp_path / "linked.json"
    target.symlink_to(tmp_path / "nowhere")
    with pytest.raises(PathAlreadyExists):
        refuse_existing(target)


def test_single_flight_lock_writes_pid_and_timestamp(tmp_path):
    lock_path = tmp_path / ".auto.lock"
    with SingleFlightLock(lock_path) as lock:
        assert lock.lock_path == lock_path
        body = lock_path.read_text()
        assert f"pid={os.getpid()}" in body
        assert "at=" in body
    assert not lock_path.exists()  # released on clean exit


def test_single_flight_lock_releases_on_exception(tmp_path):
    lock_path = tmp_path / ".auto.lock"
    with pytest.raises(RuntimeError):
        with SingleFlightLock(lock_path):
            raise RuntimeError("boom")
    assert not lock_path.exists()  # released even when the body raised


def test_single_flight_lock_refuses_a_second_concurrent_holder(tmp_path):
    """Reproduces the 2026-09-01 incident: two overlapping `auto` runs let the
    second steal the first's gate-plan.json mid-flight. The second attempt
    must fail immediately, before doing any work, not merely warn."""
    lock_path = tmp_path / ".auto.lock"
    with SingleFlightLock(lock_path):
        with pytest.raises(ConcurrentRunError) as excinfo:
            with SingleFlightLock(lock_path):
                pytest.fail("must not enter the body while another holder is active")
        assert excinfo.value.lock_path == lock_path
    assert not lock_path.exists()


def test_archive_live_documents_returns_none_when_nothing_present(tmp_path):
    assert archive_live_documents(tmp_path, ("gate-plan.json",), commit="deadbeef") is None


def test_archive_live_documents_moves_files_and_dirs_preserving_content(tmp_path):
    (tmp_path / "gate-plan.json").write_text('{"a": 1}')
    (tmp_path / "install-receipt.json").write_text('{"b": 2}')
    readiness_dir = tmp_path / "fetched-readiness"
    readiness_dir.mkdir()
    (readiness_dir / "readiness.json").write_text('{"c": 3}')

    destination = archive_live_documents(
        tmp_path, ("gate-plan.json", "install-receipt.json", "capture-spec.tar"),
        commit="e29e6664e3647e17646c979100964f317ac51551",
        extra_dirs=("fetched-readiness",),
    )

    assert destination is not None
    assert destination.name.startswith("attempt-")
    assert destination.name.endswith("-e29e6664")
    assert (destination / "gate-plan.json").read_text() == '{"a": 1}'
    assert (destination / "install-receipt.json").read_text() == '{"b": 2}'
    assert (destination / "fetched-readiness" / "readiness.json").read_text() == '{"c": 3}'
    # Originals are gone (moved, not copied) -- the point is "preserved
    # elsewhere," not "still silently present at the old path."
    assert not (tmp_path / "gate-plan.json").exists()
    assert not readiness_dir.exists()
    # A name that was never live is simply absent from the archive, not an error.
    assert not (destination / "capture-spec.tar").exists()
