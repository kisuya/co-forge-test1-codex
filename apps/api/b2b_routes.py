from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request

from apps.api.b2b_guard import require_b2b_context
from apps.domain.events import parse_utc_datetime, price_event_store
from apps.infra.observability import log_info

_MAX_SUMMARY_LIMIT = 100


def register_b2b_routes(app: FastAPI) -> None:
    @app.get("/v1/b2b/ping")
    def b2b_ping(request: Request) -> dict[str, object]:
        context = require_b2b_context(request)
        return {
            "ok": True,
            "tenant_id": context.tenant_id,
            "key_id": context.key_id,
        }

    @app.get("/v1/b2b/events/summary")
    def b2b_event_summary(request: Request) -> dict[str, object]:
        context = require_b2b_context(request)
        from_utc, to_utc = _parse_time_window(request)
        limit = _parse_limit(request)
        requested_symbols = _parse_symbols_param(request.query_params.get("symbols"))
        effective_symbols = requested_symbols

        if context.allowed_symbols:
            allowed = set(context.allowed_symbols)
            if requested_symbols:
                effective_symbols = [symbol for symbol in requested_symbols if symbol in allowed]
                removed = [symbol for symbol in requested_symbols if symbol not in allowed]
                if removed:
                    log_info(
                        feature="b2b-002",
                        event="b2b_summary_filtered_symbols",
                        request_id=request.request_id,
                        logger_name="oh_my_stock.api",
                        tenant_id=context.tenant_id,
                        key_id=context.key_id,
                        removed_symbols=removed,
                    )
            else:
                effective_symbols = list(context.allowed_symbols)

        events = price_event_store.query_events(
            from_utc=from_utc,
            to_utc=to_utc,
            now_utc=to_utc,
            max_age_days=3650,
            sort_desc=True,
        )

        if effective_symbols:
            allowed_symbols = set(effective_symbols)
            events = [event for event in events if event.symbol in allowed_symbols]

        items = [_to_summary_item(event.to_dict()) for event in events[:limit]]
        return {
            "items": items,
            "count": len(items),
            "window": {
                "from": _to_utc_iso(from_utc),
                "to": _to_utc_iso(to_utc),
            },
        }


def _parse_time_window(request: Request) -> tuple[datetime, datetime]:
    query = request.query_params
    now_raw = query.get("now")
    to_raw = query.get("to")
    from_raw = query.get("from")

    now_utc = parse_utc_datetime(now_raw) if now_raw else datetime.now(timezone.utc)
    to_utc = parse_utc_datetime(to_raw) if to_raw else now_utc
    from_utc = parse_utc_datetime(from_raw) if from_raw else (to_utc - timedelta(hours=24))

    if from_utc > to_utc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="from must be <= to",
            details={"from": from_raw, "to": to_raw},
        )
    return from_utc, to_utc


def _parse_limit(request: Request) -> int:
    raw = (request.query_params.get("limit") or str(_MAX_SUMMARY_LIMIT)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="limit must be an integer",
            details={"limit": raw},
        ) from exc
    if parsed < 1 or parsed > _MAX_SUMMARY_LIMIT:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message=f"limit must be between 1 and {_MAX_SUMMARY_LIMIT}",
            details={"limit": parsed},
        )
    return parsed


def _parse_symbols_param(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized: list[str] = []
    for token in raw.split(","):
        symbol = token.strip().upper()
        if not symbol or symbol in normalized:
            continue
        normalized.append(symbol)
    return normalized


def _to_summary_item(event_payload: dict[str, object]) -> dict[str, object]:
    return {
        "id": event_payload["id"],
        "symbol": event_payload["symbol"],
        "market": event_payload["market"],
        "change_pct": event_payload["change_pct"],
        "detected_at_utc": event_payload["detected_at_utc"],
        "session_label": event_payload["session_label"],
    }


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
