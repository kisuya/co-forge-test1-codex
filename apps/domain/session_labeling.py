from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from apps.domain.events import parse_utc_datetime

_MINUTES_PER_HOUR = 60
_SESSION_LABELS = {"pre", "regular", "after-hours", "closed"}


@dataclass(frozen=True)
class SessionRule:
    timezone: str
    pre_start_minute: int
    regular_start_minute: int
    regular_end_minute: int
    after_end_minute: int
    holiday_month_days: set[tuple[int, int]]


_SESSION_RULES = {
    "KR": SessionRule(
        timezone="Asia/Seoul",
        pre_start_minute=8 * _MINUTES_PER_HOUR,
        regular_start_minute=9 * _MINUTES_PER_HOUR,
        regular_end_minute=15 * _MINUTES_PER_HOUR + 30,
        after_end_minute=18 * _MINUTES_PER_HOUR,
        holiday_month_days={(1, 1), (3, 1), (8, 15), (10, 3), (12, 25)},
    ),
    "US": SessionRule(
        timezone="America/New_York",
        pre_start_minute=4 * _MINUTES_PER_HOUR,
        regular_start_minute=9 * _MINUTES_PER_HOUR + 30,
        regular_end_minute=16 * _MINUTES_PER_HOUR,
        after_end_minute=20 * _MINUTES_PER_HOUR,
        holiday_month_days={(1, 1), (7, 4), (12, 25)},
    ),
}


def classify_market_session(*, market: str, detected_at_utc: datetime | str) -> str:
    normalized_market = _normalize_market(market)
    rule = _SESSION_RULES[normalized_market]
    local_dt = parse_utc_datetime(detected_at_utc).astimezone(ZoneInfo(rule.timezone))

    if _is_closed_day(local_dt.date(), holiday_month_days=rule.holiday_month_days):
        return "closed"

    minute_of_day = local_dt.hour * _MINUTES_PER_HOUR + local_dt.minute
    if rule.pre_start_minute <= minute_of_day < rule.regular_start_minute:
        return "pre"
    if rule.regular_start_minute <= minute_of_day <= rule.regular_end_minute:
        return "regular"
    if rule.regular_end_minute < minute_of_day <= rule.after_end_minute:
        return "after-hours"
    return "closed"


def normalize_session_label(session_label: str | None) -> str | None:
    if session_label is None:
        return None
    normalized = session_label.strip().lower()
    if not normalized:
        return None
    if normalized not in _SESSION_LABELS:
        raise ValueError("session_label must be pre, regular, after-hours, or closed")
    return normalized


def _normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in _SESSION_RULES:
        raise ValueError("market must be KR or US")
    return normalized


def _is_closed_day(local_date: date, *, holiday_month_days: set[tuple[int, int]]) -> bool:
    if local_date.weekday() >= 5:
        return True
    return (local_date.month, local_date.day) in holiday_month_days
