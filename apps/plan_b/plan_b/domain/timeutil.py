"""Scenario time helpers.

All stored and transported timestamps are UTC ISO 8601 strings ending in ``Z`` with whole
minutes. The named event timezone (``America/New_York``) is used only for display. Browser wall
time never enters correctness decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

DISPLAY_TIMEZONE = "America/New_York"


def to_utc(value: datetime) -> datetime:
    """Normalize an aware datetime to UTC. Naive datetimes are rejected."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamps must carry an explicit UTC offset")
    try:
        return value.astimezone(UTC)
    except OverflowError as exc:  # e.g. 9999-12-31T23:59-05:00 has no UTC representation
        raise ValueError("timestamp is out of range") from exc


def parse_ts(text: str) -> datetime:
    """Parse an ISO 8601 timestamp with an explicit offset and return it in UTC."""
    normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
    return to_utc(datetime.fromisoformat(normalized))


def fmt_ts(value: datetime) -> str:
    """Canonical storage/transport form: ``YYYY-MM-DDTHH:MM:SSZ`` in UTC."""
    return to_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_label(value: datetime, tz: str = DISPLAY_TIMEZONE) -> str:
    """Human-readable local time, e.g. ``17:25``, in the event timezone."""
    return to_utc(value).astimezone(ZoneInfo(tz)).strftime("%H:%M")


def minutes(n: int) -> timedelta:
    return timedelta(minutes=n)


def minutes_between(start: datetime, end: datetime) -> int:
    delta = to_utc(end) - to_utc(start)
    return int(delta.total_seconds() // 60)


def is_minute_aligned(value: datetime) -> bool:
    return value.second == 0 and value.microsecond == 0
