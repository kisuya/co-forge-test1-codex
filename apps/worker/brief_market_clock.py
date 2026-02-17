from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.domain.events import parse_utc_datetime, to_utc_iso

_MINUTES_PER_HOUR = 60


@dataclass(frozen=True)
class BriefMarketRule:
    timezone: str
    regular_open_minute: int
    regular_close_minute: int
    holiday_month_days: frozenset[tuple[int, int]]


@dataclass(frozen=True)
class MarketClock:
    market: str
    timezone: str
    local_now: datetime
    trade_date_local: date
    phase: str
    is_holiday: bool
    regular_open_utc: datetime
    regular_close_utc: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "timezone": self.timezone,
            "local_now": self.local_now.isoformat(),
            "trade_date_local": self.trade_date_local.isoformat(),
            "phase": self.phase,
            "is_holiday": self.is_holiday,
            "regular_open_utc": to_utc_iso(self.regular_open_utc),
            "regular_close_utc": to_utc_iso(self.regular_close_utc),
        }


_MARKET_RULES: dict[str, BriefMarketRule] = {
    "KR": BriefMarketRule(
        timezone="Asia/Seoul",
        regular_open_minute=9 * _MINUTES_PER_HOUR,
        regular_close_minute=15 * _MINUTES_PER_HOUR + 30,
        holiday_month_days=frozenset({(1, 1), (3, 1), (8, 15), (10, 3), (12, 25)}),
    ),
    "US": BriefMarketRule(
        timezone="America/New_York",
        regular_open_minute=9 * _MINUTES_PER_HOUR + 30,
        regular_close_minute=16 * _MINUTES_PER_HOUR,
        holiday_month_days=frozenset({(1, 1), (7, 4), (12, 25)}),
    ),
}


def normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in _MARKET_RULES:
        raise ValueError("market must be KR or US")
    return normalized


def resolve_market_clock(*, market: str, now_utc: datetime | str) -> MarketClock:
    normalized_market = normalize_market(market)
    rule = _MARKET_RULES[normalized_market]
    parsed_now = parse_utc_datetime(now_utc)

    try:
        local_now = parsed_now.astimezone(ZoneInfo(rule.timezone))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"timezone unavailable for market {normalized_market}") from exc

    trade_date_local = local_now.date()
    is_holiday = _is_holiday(local_date=trade_date_local, holiday_month_days=rule.holiday_month_days)
    phase = "closed" if is_holiday else _resolve_phase(local_now=local_now, rule=rule)

    regular_open_utc, regular_close_utc = build_market_window_utc(
        market=normalized_market,
        trade_date_local=trade_date_local,
    )
    return MarketClock(
        market=normalized_market,
        timezone=rule.timezone,
        local_now=local_now,
        trade_date_local=trade_date_local,
        phase=phase,
        is_holiday=is_holiday,
        regular_open_utc=regular_open_utc,
        regular_close_utc=regular_close_utc,
    )


def build_market_window_utc(
    *,
    market: str,
    trade_date_local: date | str,
) -> tuple[datetime, datetime]:
    normalized_market = normalize_market(market)
    rule = _MARKET_RULES[normalized_market]
    parsed_trade_date = _parse_trade_date(trade_date_local)

    try:
        timezone = ZoneInfo(rule.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"timezone unavailable for market {normalized_market}") from exc

    local_midnight = datetime.combine(parsed_trade_date, time(0, 0), tzinfo=timezone)
    open_local = local_midnight + timedelta(minutes=rule.regular_open_minute)
    close_local = local_midnight + timedelta(minutes=rule.regular_close_minute)
    return open_local.astimezone(ZoneInfo("UTC")), close_local.astimezone(ZoneInfo("UTC"))


def to_market_local_iso(*, market: str, timestamp_utc: datetime | str) -> str:
    normalized_market = normalize_market(market)
    rule = _MARKET_RULES[normalized_market]
    parsed_timestamp = parse_utc_datetime(timestamp_utc)
    try:
        local_dt = parsed_timestamp.astimezone(ZoneInfo(rule.timezone))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"timezone unavailable for market {normalized_market}") from exc
    return local_dt.isoformat()


def _parse_trade_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError("trade_date_local is required")
    return date.fromisoformat(normalized)


def _resolve_phase(*, local_now: datetime, rule: BriefMarketRule) -> str:
    minute_of_day = local_now.hour * _MINUTES_PER_HOUR + local_now.minute
    if minute_of_day < rule.regular_open_minute:
        return "pre"
    if minute_of_day <= rule.regular_close_minute:
        return "regular"
    return "after-hours"


def _is_holiday(*, local_date: date, holiday_month_days: frozenset[tuple[int, int]]) -> bool:
    if local_date.weekday() >= 5:
        return True
    return (local_date.month, local_date.day) in holiday_month_days
