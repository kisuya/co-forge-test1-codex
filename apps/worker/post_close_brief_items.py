from __future__ import annotations

from datetime import datetime
from numbers import Real
from typing import Any

from apps.domain.events import parse_utc_datetime, to_utc_iso
from apps.worker.brief_market_clock import MarketClock, normalize_market, to_market_local_iso


def build_post_close_items(
    *,
    daily_events: list[dict[str, Any]],
    watched_symbols: set[tuple[str, str]],
    market_clocks: dict[str, MarketClock],
    reason_revisions: list[dict[str, Any]],
    delta_notifications: list[dict[str, Any]],
) -> tuple[list[dict[str, object]], list[str]]:
    warnings: list[str] = []
    revisions_by_event = _aggregate_revisions(reason_revisions, warnings=warnings)
    deltas_by_event = _aggregate_deltas(delta_notifications, warnings=warnings)
    items = _aggregate_events(
        daily_events=daily_events,
        watched_symbols=watched_symbols,
        market_clocks=market_clocks,
        revisions_by_event=revisions_by_event,
        deltas_by_event=deltas_by_event,
        warnings=warnings,
    )
    return items, warnings


def _aggregate_revisions(
    revisions: list[dict[str, Any]],
    *,
    warnings: list[str],
) -> dict[str, dict[str, object]]:
    aggregated: dict[str, dict[str, object]] = {}
    for index, item in enumerate(revisions):
        event_id = str(item.get("event_id", "")).strip()
        if not event_id:
            warnings.append(f"revision[{index}] missing event_id")
            continue

        changed_at = _safe_parse_datetime(
            item.get("revised_at_utc") or item.get("changed_at_utc") or item.get("created_at_utc")
        )
        if changed_at is None:
            warnings.append(f"revision[{index}] invalid datetime")
            continue

        bucket = aggregated.setdefault(
            event_id,
            {"count": 0, "latest_status": None, "latest_changed_at": changed_at},
        )
        bucket["count"] = int(bucket["count"]) + 1
        latest_changed_at = bucket.get("latest_changed_at")
        if isinstance(latest_changed_at, datetime) and changed_at >= latest_changed_at:
            status = str(item.get("to_status") or item.get("status") or "").strip() or None
            bucket["latest_status"] = status
            bucket["latest_changed_at"] = changed_at
    return aggregated


def _aggregate_deltas(
    delta_notifications: list[dict[str, Any]],
    *,
    warnings: list[str],
) -> dict[str, dict[str, object]]:
    aggregated: dict[str, dict[str, object]] = {}
    for index, item in enumerate(delta_notifications):
        event_id = str(item.get("event_id", "")).strip()
        if not event_id:
            warnings.append(f"delta[{index}] missing event_id")
            continue

        confidence_value = item.get("confidence_delta", 0.0)
        if isinstance(confidence_value, bool) or not isinstance(confidence_value, Real):
            warnings.append(f"delta[{index}] invalid confidence_delta")
            continue

        reason_code = str(item.get("reason_code", "")).strip()
        bucket = aggregated.setdefault(event_id, {"confidence_delta": 0.0, "reason_codes": set()})
        bucket["confidence_delta"] = max(float(bucket["confidence_delta"]), abs(float(confidence_value)))
        if reason_code:
            reason_codes = bucket.get("reason_codes")
            if isinstance(reason_codes, set):
                reason_codes.add(reason_code)
    return aggregated


def _aggregate_events(
    *,
    daily_events: list[dict[str, Any]],
    watched_symbols: set[tuple[str, str]],
    market_clocks: dict[str, MarketClock],
    revisions_by_event: dict[str, dict[str, object]],
    deltas_by_event: dict[str, dict[str, object]],
    warnings: list[str],
) -> list[dict[str, object]]:
    deduped: dict[str, tuple[datetime, dict[str, object]]] = {}
    for index, event in enumerate(daily_events):
        event_id = str(event.get("event_id") or event.get("id") or "").strip()
        if not event_id:
            warnings.append(f"event[{index}] missing event_id")
            continue

        symbol = str(event.get("symbol", "")).strip().upper()
        try:
            market = normalize_market(str(event.get("market", "")))
        except ValueError:
            warnings.append(f"event[{index}] invalid market")
            continue

        if (market, symbol) not in watched_symbols:
            continue
        clock = market_clocks.get(market)
        if clock is None:
            continue

        detected_at = _safe_parse_datetime(event.get("detected_at_utc") or event.get("event_time_utc"))
        if detected_at is None:
            warnings.append(f"event[{index}] invalid detected_at_utc")
            continue

        detected_local_iso = to_market_local_iso(market=market, timestamp_utc=detected_at)
        detected_local_dt = datetime.fromisoformat(detected_local_iso)
        if detected_local_dt.date() != clock.trade_date_local:
            continue

        source_url = _extract_source_url(event)
        if not source_url:
            warnings.append(f"event[{index}] missing source_url")
            continue

        event_detail_url = str(event.get("event_detail_url") or event.get("event_url") or "").strip()
        if not event_detail_url:
            event_detail_url = f"/events/{event_id}"

        change_pct = _normalize_change_pct(event.get("change_pct"))
        revision_bucket = revisions_by_event.get(event_id, {})
        delta_bucket = deltas_by_event.get(event_id, {})
        revision_count = int(revision_bucket.get("count", 0))
        confidence_delta = round(float(delta_bucket.get("confidence_delta", 0.0)), 4)
        reason_codes = sorted(delta_bucket.get("reason_codes", set()))

        item = {
            "event_id": event_id,
            "symbol": symbol,
            "market": market,
            "detected_at_utc": to_utc_iso(detected_at),
            "detected_at_local": detected_local_iso,
            "trade_date_local": clock.trade_date_local.isoformat(),
            "change_pct": change_pct,
            "final_status": str(revision_bucket.get("latest_status") or event.get("reason_status") or "verified").strip(),
            "revision_count": revision_count,
            "delta_reason_codes": reason_codes,
            "confidence_delta": confidence_delta,
            "summary": _summary_text(
                change_pct=change_pct,
                revision_count=revision_count,
                confidence_delta=confidence_delta,
            ),
            "event_detail_url": event_detail_url,
            "source_url": source_url,
            "priority_score": _priority_score(
                change_pct=change_pct,
                revision_count=revision_count,
                confidence_delta=confidence_delta,
            ),
        }

        existing = deduped.get(event_id)
        if existing is None or detected_at > existing[0]:
            deduped[event_id] = (detected_at, item)

    items = [value[1] for value in deduped.values()]
    items.sort(key=lambda item: (-float(item["priority_score"]), str(item["detected_at_utc"]), str(item["event_id"])))
    return items


def _extract_source_url(event: dict[str, Any]) -> str:
    source_url = str(event.get("source_url", "")).strip()
    if source_url:
        return source_url
    reasons = event.get("reasons", [])
    if isinstance(reasons, list):
        for reason in reasons:
            if not isinstance(reason, dict):
                continue
            url = str(reason.get("source_url", "")).strip()
            if url:
                return url
    return ""


def _normalize_change_pct(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        return 0.0
    return round(float(value), 4)


def _priority_score(*, change_pct: float, revision_count: int, confidence_delta: float) -> float:
    score = min(abs(change_pct) / 10.0, 1.0) * 0.6
    score += min(revision_count, 4) / 4.0 * 0.2
    score += min(abs(confidence_delta), 1.0) * 0.2
    return round(score, 4)


def _summary_text(*, change_pct: float, revision_count: int, confidence_delta: float) -> str:
    fragments = [f"종가 기준 변동 {change_pct:+.2f}%"]
    if revision_count > 0:
        fragments.append(f"원인 정정 {revision_count}건")
    if confidence_delta > 0:
        fragments.append(f"confidence 변화 {confidence_delta:+.2f}")
    return ", ".join(fragments)


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
