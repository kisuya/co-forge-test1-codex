from __future__ import annotations

from datetime import datetime

from apps.domain.events import parse_utc_datetime, price_event_store

WINDOW_THRESHOLDS = {
    5: 3.0,
    1440: 5.0,
}
WINDOW_DEBOUNCE_MINUTES = {
    5: 5,
    1440: 1440,
}
MARKET_TIMEZONES = {
    "KR": "Asia/Seoul",
    "US": "America/New_York",
}


def detect_price_event(
    *,
    symbol: str,
    market: str,
    baseline_price: float,
    current_price: float,
    window_minutes: int,
    detected_at_utc: datetime | str,
    session_label: str = "regular",
) -> dict[str, object] | None:
    normalized_symbol = (symbol or "").strip().upper()
    normalized_market = (market or "").strip().upper()

    if normalized_market not in MARKET_TIMEZONES:
        raise ValueError("market must be KR or US")
    if window_minutes not in WINDOW_THRESHOLDS:
        raise ValueError("window_minutes must be one of 5 or 1440")
    if baseline_price <= 0:
        raise ValueError("baseline_price must be greater than 0")

    change_pct = ((current_price - baseline_price) / baseline_price) * 100
    threshold = WINDOW_THRESHOLDS[window_minutes]
    if abs(change_pct) < threshold:
        return None

    detected_at = parse_utc_datetime(detected_at_utc)
    direction = "up" if change_pct >= 0 else "down"
    debounce_minutes = WINDOW_DEBOUNCE_MINUTES[window_minutes]

    if price_event_store.should_debounce(
        symbol=normalized_symbol,
        market=normalized_market,
        window_minutes=window_minutes,
        direction=direction,
        detected_at=detected_at,
        debounce_minutes=debounce_minutes,
    ):
        return None

    event = price_event_store.new_event(
        symbol=normalized_symbol,
        market=normalized_market,
        change_pct=round(change_pct, 4),
        window_minutes=window_minutes,
        detected_at=detected_at,
        exchange_timezone=MARKET_TIMEZONES[normalized_market],
        session_label=session_label,
    )
    price_event_store.save(event, direction=direction)
    return event.to_dict()
