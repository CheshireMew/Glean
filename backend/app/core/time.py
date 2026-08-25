from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


UTC = timezone.utc
SOURCE_TIMEZONE = timezone(timedelta(hours=8))


def get_utc_time() -> datetime:
    return datetime.now(UTC)


def format_utc_time(value: datetime | None = None) -> str:
    current = value or get_utc_time()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def utc_cutoff(hours: int | float, value: datetime | None = None) -> str:
    return format_utc_time((value or get_utc_time()) - timedelta(hours=hours))


def normalize_source_time(value: Any) -> str:
    if value is None or value == "":
        return format_utc_time()
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SOURCE_TIMEZONE)
    return format_utc_time(parsed)
