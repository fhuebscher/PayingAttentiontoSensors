from datetime import datetime, timedelta, timezone

import pytest

from obsplacement.gate_driver.errors import PreflightExpired
from obsplacement.gate_driver.freshness import (
    PREFLIGHT_MAX_AGE_SECONDS,
    age_seconds,
    deadline_after,
    is_fresh,
    now,
    parse,
    require_fresh,
    stamp,
)


def test_preflight_window_is_900_seconds():
    assert PREFLIGHT_MAX_AGE_SECONDS == 900


def test_stamp_and_parse_round_trip():
    moment = datetime(2026, 9, 4, 3, 41, 0, tzinfo=timezone.utc)
    assert parse(stamp(moment)) == moment


def test_is_fresh_true_within_window():
    reference = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    captured = stamp(reference - timedelta(seconds=899))
    assert is_fresh(captured, at=reference) is True


def test_is_fresh_false_at_and_after_boundary():
    reference = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    at_boundary = stamp(reference - timedelta(seconds=900))
    past_boundary = stamp(reference - timedelta(seconds=901))
    assert is_fresh(at_boundary, at=reference) is False
    assert is_fresh(past_boundary, at=reference) is False


def test_is_fresh_false_for_a_future_capture_timestamp():
    """A captured_at in the future (clock skew, or a bug upstream) must not
    be treated as fresh -- fail closed rather than silently accept it."""
    reference = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    captured = stamp(reference + timedelta(seconds=5))
    assert is_fresh(captured, at=reference) is False


def test_require_fresh_raises_preflight_expired_when_stale():
    reference = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    stale = stamp(reference - timedelta(seconds=901))
    with pytest.raises(PreflightExpired) as excinfo:
        require_fresh(stale, at=reference)
    assert excinfo.value.max_age_seconds == PREFLIGHT_MAX_AGE_SECONDS


def test_require_fresh_passes_silently_when_fresh():
    reference = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
    fresh = stamp(reference - timedelta(seconds=1))
    require_fresh(fresh, at=reference)  # must not raise


def test_deadline_after_adds_hours():
    reference = datetime(2026, 9, 4, 3, 41, 0, tzinfo=timezone.utc)
    assert deadline_after(6, at=reference) == "2026-09-04T09:41:00Z"


def test_now_is_timezone_aware_utc():
    moment = now()
    assert moment.tzinfo is not None
    assert moment.utcoffset() == timedelta(0)


def test_parse_accepts_hotel_isoformat_with_microseconds_and_z():
    """Hotel stamps `observedAt` as `isoformat().replace("+00:00", "Z")`."""
    from datetime import timezone

    from obsplacement.gate_driver import freshness

    parsed = freshness.parse("2026-09-05T12:34:56.123456Z")
    assert parsed.tzinfo is not None
    assert parsed.astimezone(timezone.utc).microsecond == 123456
    assert freshness.parse("2026-09-05T12:34:56+00:00") == freshness.parse("2026-09-05T12:34:56Z")


def test_parse_fails_closed_on_naive_or_non_string_timestamps():
    from obsplacement.gate_driver import freshness
    from obsplacement.gate_driver.errors import GateDriverError

    with pytest.raises(GateDriverError):
        freshness.parse("2026-09-05T12:34:56")
    with pytest.raises(GateDriverError):
        freshness.parse(None)
