from __future__ import annotations

from datetime import datetime
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.worker.brief_market_clock import MarketClock, normalize_market, resolve_market_clock
from apps.worker.post_close_brief_items import build_post_close_items


def generate_post_close_brief(
    *,
    user_id: str,
    watchlist_items: list[dict[str, Any]],
    daily_events: list[dict[str, Any]],
    reason_revisions: list[dict[str, Any]],
    delta_notifications: list[dict[str, Any]],
    now_utc: datetime | str,
) -> dict[str, object]:
    normalized_user_id = (user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("user_id is required")

    generated_at = parse_utc_datetime(now_utc)
    watched_symbols, watched_markets = _normalize_watchlist(watchlist_items)
    if not watched_symbols:
        return _empty_brief(
            user_id=normalized_user_id,
            generated_at=generated_at,
            fallback_reason="no_events",
            markets=[],
            warnings=[],
        )

    market_clocks = _build_market_clocks(markets=watched_markets, now_utc=generated_at)
    if market_clocks is None:
        return _empty_brief(
            user_id=normalized_user_id,
            generated_at=generated_at,
            fallback_reason="timezone_error",
            markets=sorted(watched_markets),
            warnings=[],
        )

    post_close_clocks = {
        market: clock
        for market, clock in market_clocks.items()
        if clock.phase in {"after-hours", "closed"}
    }
    if not post_close_clocks:
        return _empty_brief(
            user_id=normalized_user_id,
            generated_at=generated_at,
            fallback_reason="outside_post_close_window",
            markets=sorted(watched_markets),
            warnings=[],
        )

    all_holiday = all(clock.is_holiday for clock in post_close_clocks.values())

    items, warnings = build_post_close_items(
        daily_events=daily_events,
        watched_symbols=watched_symbols,
        market_clocks=post_close_clocks,
        reason_revisions=reason_revisions,
        delta_notifications=delta_notifications,
    )

    if not items:
        fallback_reason = "market_holiday" if all_holiday else "partial_aggregation" if warnings else "no_events"
        return _empty_brief(
            user_id=normalized_user_id,
            generated_at=generated_at,
            fallback_reason=fallback_reason,
            markets=sorted(post_close_clocks),
            warnings=warnings,
        )

    return {
        "brief_type": "post_close",
        "user_id": normalized_user_id,
        "generated_at_utc": to_utc_iso(generated_at),
        "markets": sorted(post_close_clocks),
        "fallback_reason": None,
        "warnings": warnings,
        "items": items,
    }


def _normalize_watchlist(watchlist_items: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], set[str]]:
    symbols: set[tuple[str, str]] = set()
    markets: set[str] = set()
    for item in watchlist_items:
        try:
            market = normalize_market(str(item.get("market", "")))
        except ValueError:
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        symbols.add((market, symbol))
        markets.add(market)
    return symbols, markets


def _build_market_clocks(*, markets: set[str], now_utc: datetime) -> dict[str, MarketClock] | None:
    clocks: dict[str, MarketClock] = {}
    try:
        for market in sorted(markets):
            clocks[market] = resolve_market_clock(market=market, now_utc=now_utc)
    except ValueError:
        return None
    return clocks


def _empty_brief(
    *,
    user_id: str,
    generated_at: datetime,
    fallback_reason: str,
    markets: list[str],
    warnings: list[str],
) -> dict[str, object]:
    return {
        "brief_type": "post_close",
        "user_id": user_id,
        "generated_at_utc": to_utc_iso(generated_at),
        "markets": markets,
        "fallback_reason": fallback_reason,
        "warnings": warnings,
        "items": [],
    }
