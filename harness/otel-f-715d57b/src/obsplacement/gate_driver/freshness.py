"""Time stamping and the preflight freshness window (non-negotiable property #3).

The runtime preflight is content-addressed and cannot be recaptured under an
existing setup-id -- a fresh preflight needs a new setup-id -- and it is only
valid for `PREFLIGHT_MAX_AGE_SECONDS` (900s / 15 minutes; gate_run.py:9,
gate_run.py:31 comment "the adapter refuses a first mutation with less than
29_100s remaining", gate_run.py:99 "the preflight must be under 15 minutes
old at execution"). A conversational round trip does not reliably fit in that
window -- that exact failure cost a launch attempt on 2026-09-04 (see
`10k_footview.md` row "Launch-path lesson"). `oneshot.run_oneshot` is the
structural fix; this module supplies the constant and the freshness check it
relies on.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .errors import GateDriverError, PreflightExpired

__all__ = [
    "PREFLIGHT_MAX_AGE_SECONDS",
    "TIMESTAMP_FORMAT",
    "now",
    "stamp",
    "parse",
    "age_seconds",
    "is_fresh",
    "require_fresh",
]

# gate_run.py's MAX_GATE_RUN_AGE_SECONDS, generalized. Both the typed
# GATE-RUN approval and the runtime preflight it is derived from must be
# under this age at execution time.
PREFLIGHT_MAX_AGE_SECONDS = 900

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: datetime) -> str:
    """Render a timestamp exactly as every canonical driver does (UTC, 'Z' suffix)."""
    return moment.strftime(TIMESTAMP_FORMAT)


def parse(value: str) -> datetime:
    """Inverse of `stamp`; always timezone-aware UTC.

    Also accepts any timezone-aware ISO-8601 string, with or without
    fractional seconds and with `Z` or an explicit offset -- Hotel's
    orchestrator stamps `observedAt` as `isoformat().replace("+00:00", "Z")`
    (microsecond precision), which `TIMESTAMP_FORMAT` alone rejects. Fails
    closed with `GateDriverError` on a non-string or a naive timestamp: a
    timestamp whose zone is unknown can never prove freshness.
    """
    if not isinstance(value, str):
        raise GateDriverError(f"timestamp must be a string, got {type(value).__name__}")
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise GateDriverError(f"timestamp is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GateDriverError(f"timestamp has no timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def age_seconds(captured_at, *, at: datetime | None = None) -> float:
    """Seconds elapsed since `captured_at` (a stamped string or a datetime)."""
    captured = parse(captured_at) if isinstance(captured_at, str) else captured_at
    reference = at if at is not None else now()
    return (reference - captured).total_seconds()


def is_fresh(captured_at, max_age_seconds: int = PREFLIGHT_MAX_AGE_SECONDS,
             *, at: datetime | None = None) -> bool:
    """True iff `captured_at` is strictly within `max_age_seconds` of `at` (now by default)."""
    return 0 <= age_seconds(captured_at, at=at) < max_age_seconds


def require_fresh(captured_at, max_age_seconds: int = PREFLIGHT_MAX_AGE_SECONDS,
                   *, at: datetime | None = None) -> None:
    """Fail closed with `PreflightExpired` unless `captured_at` is still fresh.

    Deliberately does not attempt to "recapture" anything -- per the
    content-addressing constraint, recapture under the same setup-id is not
    possible in the first place, so the correct response to staleness is
    always a fresh setup-id, never a retry loop here.
    """
    elapsed = age_seconds(captured_at, at=at)
    if not (0 <= elapsed < max_age_seconds):
        raise PreflightExpired(captured_at, max_age_seconds, elapsed)


def deadline_after(hours: int, *, at: datetime | None = None) -> str:
    """Stamp a deadline `hours` from `at` (now by default). Shared by every
    *-authorization-deadline computation across the four canonical drivers."""
    reference = at if at is not None else now()
    return stamp(reference + timedelta(hours=hours))
