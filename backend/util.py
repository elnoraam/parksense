"""Utilitas waktu: semua waktu memakai zona WIB (+07:00), format ISO 8601."""
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))


def now() -> datetime:
    return datetime.now(WIB)


def iso(dt: datetime) -> str:
    return dt.astimezone(WIB).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=WIB)
    return dt
