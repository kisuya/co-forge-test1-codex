from __future__ import annotations

from datetime import datetime
from numbers import Real
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.worker.brief_market_clock import (
    MarketClock,
    normalize_market,
    resolve_market_clock,
    to_market_local_iso,
)

_MINUTES_PER_DAY = 24 * 60


def generate_pre_market_brief(
    *,
    user_id: str,
    watchlist_items: list[dict[str, Any]],
    scheduled_events: list[dict[str, Any]],
    recent_reason_cards: list[dict[str, Any]],
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
            fallback_reason="insufficient_data",
            markets=[],
        )

    market_clocks = _build_market_clocks(markets=watched_markets, now_utc=generated_at)
    if market_clocks is None:
        return _empty_brief(
            user_id=normalized_user_id,
            generated_at=generated_at,
            fallback_reason="timezone_error",
            markets=sorted(watched_markets),
        )

    pre_open_clocks = {market: clock for market, clock in market_clocks.items() if clock.phase == "pre"}
    if not pre_open_clocks:
        is_holiday = all(clock.is_holiday for clock in market_clocks.values())
        return _empty_brief(
            user_id=normalized_user_id,
            generated_at=generated_at,
            fallback_reason="market_holiday" if is_holiday else "outside_pre_market_window",
            markets=sorted(watched_markets),
        )

    reason_index = _build_reason_index(recent_reason_cards)
    items = _build_brief_items(
        scheduled_events=scheduled_events,
        watched_symbols=watched_symbols,
        reason_index=reason_index,
        market_clocks=pre_open_clocks,
        now_utc=generated_at,
    )
    if not items:
        return _empty_brief(
            user_id=normalized_user_id,
            generated_at=generated_at,
            fallback_reason="insufficient_data",
            markets=sorted(pre_open_clocks),
        )

    return {
        "brief_type": "pre_market",
        "user_id": normalized_user_id,
        "generated_at_utc": to_utc_iso(generated_at),
        "markets": sorted(pre_open_clocks),
        "fallback_reason": None,
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


def _build_reason_index(reason_cards: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for card in reason_cards:
        try:
            market = normalize_market(str(card.get("market", "")))
        except ValueError:
            continue
        symbol = str(card.get("symbol", "")).strip().upper()
        if not symbol:
            continue

        source_url = str(card.get("source_url", "")).strip()
        if not source_url:
            continue

        candidate_time = _safe_parse_datetime(card.get("published_at") or card.get("detected_at_utc"))
        key = (market, symbol)
        current = indexed.get(key)
        current_time = _safe_parse_datetime(current.get("_sort_time")) if current else None
        should_replace = current is None or (
            candidate_time is not None and (current_time is None or candidate_time > current_time)
        )
        if should_replace:
            indexed[key] = {
                "summary": str(card.get("summary", "")).strip(),
                "source_url": source_url,
                "confidence_score": _normalize_score(card.get("confidence_score")),
                "_sort_time": to_utc_iso(candidate_time) if candidate_time else "",
            }
    return indexed


def _build_brief_items(
    *,
    scheduled_events: list[dict[str, Any]],
    watched_symbols: set[tuple[str, str]],
    reason_index: dict[tuple[str, str], dict[str, Any]],
    market_clocks: dict[str, MarketClock],
    now_utc: datetime,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for event in scheduled_events:
        market_value = str(event.get("market", ""))
        symbol = str(event.get("symbol", "")).strip().upper()
        try:
            market = normalize_market(market_value)
        except ValueError:
            continue
        if (market, symbol) not in watched_symbols:
            continue

        clock = market_clocks.get(market)
        if clock is None:
            continue

        scheduled_at = _safe_parse_datetime(
            event.get("scheduled_at_utc")
            or event.get("event_time_utc")
            or event.get("starts_at_utc")
            or event.get("expected_at_utc")
        )
        if scheduled_at is None:
            continue
        scheduled_local_iso = to_market_local_iso(market=market, timestamp_utc=scheduled_at)
        if datetime.fromisoformat(scheduled_local_iso).date() != clock.trade_date_local:
            continue

        reason = reason_index.get((market, symbol), {})
        source_url = str(reason.get("source_url") or event.get("source_url") or "").strip()
        if not source_url:
            continue

        event_id = str(event.get("event_id") or event.get("id") or "").strip()
        event_detail_url = str(event.get("event_detail_url") or event.get("event_url") or "").strip()
        if not event_detail_url and event_id:
            event_detail_url = f"/events/{event_id}"
        if not event_detail_url:
            continue

        confidence_score = _normalize_score(reason.get("confidence_score"))
        priority_score = _priority_score(
            now_utc=now_utc,
            scheduled_at_utc=scheduled_at,
            confidence_score=confidence_score,
        )
        risk_level = _risk_level(priority_score)
        summary = _summary_text(
            event=event,
            reason_summary=str(reason.get("summary", "")).strip(),
            risk_level=risk_level,
        )
        items.append(
            {
                "event_id": event_id,
                "symbol": symbol,
                "market": market,
                "event_type": str(event.get("event_type", "scheduled_event")).strip() or "scheduled_event",
                "title": str(event.get("title", "")).strip() or f"{symbol} 사전 점검",
                "scheduled_at_utc": to_utc_iso(scheduled_at),
                "scheduled_at_local": scheduled_local_iso,
                "trade_date_local": clock.trade_date_local.isoformat(),
                "priority_score": priority_score,
                "risk_level": risk_level,
                "summary": summary,
                "checklist": _build_checklist(summary=summary, risk_level=risk_level),
                "source_url": source_url,
                "event_detail_url": event_detail_url,
            }
        )

    items.sort(key=lambda item: (-float(item["priority_score"]), str(item["scheduled_at_utc"]), str(item["symbol"])))
    return items


def _priority_score(*, now_utc: datetime, scheduled_at_utc: datetime, confidence_score: float) -> float:
    minutes_until_event = max(0.0, (scheduled_at_utc - now_utc).total_seconds() / 60.0)
    urgency = max(0.0, 1.0 - min(minutes_until_event, _MINUTES_PER_DAY) / _MINUTES_PER_DAY)
    score = urgency * 0.6 + confidence_score * 0.4
    return round(score, 4)


def _risk_level(priority_score: float) -> str:
    if priority_score >= 0.7:
        return "high"
    if priority_score >= 0.4:
        return "medium"
    return "low"


def _summary_text(*, event: dict[str, Any], reason_summary: str, risk_level: str) -> str:
    if reason_summary:
        return reason_summary
    event_label = str(event.get("title", "")).strip() or str(event.get("event_type", "일정")).strip() or "일정"
    if risk_level == "high":
        return f"{event_label} 전 변동성 리스크가 높아 사전 확인이 필요합니다."
    if risk_level == "medium":
        return f"{event_label} 관련 핵심 체크포인트를 개장 전에 확인하세요."
    return f"{event_label} 관련 주요 일정을 개장 전에 확인하세요."


def _build_checklist(*, summary: str, risk_level: str) -> list[str]:
    first = "근거 링크 원문을 확인해 사실 여부를 검증하세요."
    second = "이벤트 상세에서 최근 confidence 변화를 함께 점검하세요."
    if risk_level == "high":
        third = "시가 직후 변동 확대 가능성을 염두에 두고 알림 임계값을 재점검하세요."
    elif risk_level == "medium":
        third = "장 시작 전 핵심 일정 시각과 상태를 재확인하세요."
    else:
        third = "필수 일정만 빠르게 스캔하고 상세가 필요할 때 이벤트 화면으로 이동하세요."
    return [first, second, third]


def _normalize_score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        return 0.0
    score = float(value)
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return round(score, 4)


def _safe_parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return parse_utc_datetime(raw)
    except ValueError:
        return None


def _empty_brief(
    *,
    user_id: str,
    generated_at: datetime,
    fallback_reason: str,
    markets: list[str],
) -> dict[str, object]:
    return {
        "brief_type": "pre_market",
        "user_id": user_id,
        "generated_at_utc": to_utc_iso(generated_at),
        "markets": markets,
        "fallback_reason": fallback_reason,
        "items": [],
    }
