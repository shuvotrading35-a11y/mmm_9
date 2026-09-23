"""
Time Utils — timezone-aware datetime helpers.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def fmt_datetime(dt: Optional[datetime]) -> str:
    if not dt:
        return "N/A"
    return dt.strftime("%b %d, %Y %H:%M UTC")


def fmt_date(dt: Optional[datetime]) -> str:
    if not dt:
        return "N/A"
    return dt.strftime("%b %d, %Y")


def humanize_timedelta(delta: timedelta) -> str:
    """Convert timedelta to human readable: '2 days 14 hours'"""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "Expired"
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes and not days:
        parts.append(f"{minutes} min")
    return " ".join(parts) if parts else "< 1 min"


def time_until(dt: Optional[datetime]) -> str:
    if not dt:
        return "No expiry"
    delta = dt - now_utc()
    return humanize_timedelta(delta)
