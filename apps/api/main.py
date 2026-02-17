from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response

from apps.api.b2b_guard import B2BRateLimitException
from apps.api.b2b_routes import register_b2b_routes
from apps.api.brief_routes import register_brief_routes
from apps.api.auth_watchlist_routes import register_auth_watchlist_routes
from apps.api.event_payloads import serialize_event as _serialize_event
from apps.api.feedback_routes import register_feedback_routes
from apps.api.notification_routes import register_notification_routes
from apps.api.portfolio_routes import register_portfolio_routes
from apps.api.push_token_routes import register_push_token_routes
from apps.api.symbol_routes import register_symbol_routes
from apps.api.threshold_routes import register_threshold_routes
from apps.domain.events import TransientStoreError, parse_utc_datetime, price_event_store
from apps.infra.observability import log_error, log_info
from apps.infra.postgres import (
    DatabaseConnectionError,
    get_database_runtime,
    initialize_database_runtime,
)

app = FastAPI(title="oh-my-stock API")
initialize_database_runtime(request_id="startup")
register_auth_watchlist_routes(app)
register_symbol_routes(app)
register_threshold_routes(app)
register_notification_routes(app)
register_brief_routes(app)
register_feedback_routes(app)
register_portfolio_routes(app)
register_push_token_routes(app)
register_b2b_routes(app)

_VALID_MARKETS = {"KR", "US"}
_VALID_SESSIONS = {"pre", "regular", "after-hours", "closed"}
_VALID_EVENT_SORTS = {"detected_at_desc", "detected_at_asc"}
_DEFAULT_EVENT_PAGE_SIZE = 20
_MAX_EVENT_PAGE_SIZE = 100


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def db_health(request: Request) -> dict[str, str]:
    request_id = request.request_id or "health-db"
    try:
        status = get_database_runtime().health(request_id=request_id)
    except DatabaseConnectionError as exc:
        raise HTTPException(
            status_code=503,
            code="db_unavailable",
            message="Database health check failed",
            details={"retryable": True, "reason": str(exc)},
        ) from exc
    log_info(
        feature="ops-003",
        event="db_health_ok",
        request_id=request_id,
        logger_name="oh_my_stock.api",
    )
    return {"status": status}


def _parse_optional_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        return parse_utc_datetime(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message=f"Invalid datetime format for '{field_name}'",
            details={"field": field_name, "value": value},
        ) from exc


@app.get("/v1/events")
def list_events(request: Request) -> dict[str, object]:
    query = request.query_params
    symbol = query.get("symbol", "").strip().upper() or None
    market = query.get("market", "").strip().upper() or None
    session_label = query.get("session", "").strip().lower() or None
    sort = query.get("sort", "detected_at_desc").strip().lower() or "detected_at_desc"
    size = _parse_event_page_size(query.get("size"))
    cursor = _parse_event_cursor(query.get("cursor"), sort=sort)

    if market and market not in _VALID_MARKETS:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="market must be KR or US",
            details={"market": market},
        )
    if session_label and session_label not in _VALID_SESSIONS:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="session must be one of pre, regular, after-hours, closed",
            details={"session": session_label},
        )
    if sort not in _VALID_EVENT_SORTS:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="sort must be detected_at_desc or detected_at_asc",
            details={"sort": sort},
        )

    from_utc = _parse_optional_datetime(query.get("from"), field_name="from")
    to_utc = _parse_optional_datetime(query.get("to"), field_name="to")
    now_utc = _parse_optional_datetime(query.get("now"), field_name="now")

    events = price_event_store.query_events(
        symbol=symbol,
        market=market,
        session_label=session_label,
        from_utc=from_utc,
        to_utc=to_utc,
        now_utc=now_utc,
        max_age_days=30,
        sort_desc=sort == "detected_at_desc",
    )
    serialized_events = [_serialize_event(event) for event in events]
    cursor_filtered = _apply_event_cursor(serialized_events, cursor=cursor, sort=sort)
    page_items = cursor_filtered[:size]
    has_next_page = len(cursor_filtered) > size
    next_cursor = _build_event_cursor(page_items[-1]) if has_next_page and page_items else None
    return {
        "items": page_items,
        "count": len(page_items),
        "next_cursor": next_cursor,
    }


@app.get("/v1/events/{event_id}")
def get_event_detail(event_id: str, request: Request) -> dict[str, object]:
    event = price_event_store.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            code="event_not_found",
            message="Event not found",
            details={"event_id": event_id},
        )
    return {"event": _serialize_event(event, request=request, include_reason_state=True)}


@app.exception_handler(TransientStoreError)
def handle_transient_store_error(exc: TransientStoreError, request_id: str) -> Response:
    log_error(
        feature="ops-003",
        event="api_transient_error",
        request_id=request_id,
        logger_name="oh_my_stock.api",
        error=str(exc),
    )
    payload = {
        "code": "temporarily_unavailable",
        "message": "Temporary service issue. Please retry.",
        "details": {"retryable": True, "reason": str(exc)},
        "request_id": request_id,
        "retryable": True,
    }
    return Response(status_code=503, payload=payload)


@app.exception_handler(B2BRateLimitException)
def handle_b2b_rate_limit(exc: B2BRateLimitException, request_id: str) -> Response:
    payload = {
        "code": "rate_limit_exceeded",
        "message": "Rate limit exceeded",
        "details": {"retry_after_seconds": exc.retry_after_seconds},
        "request_id": request_id,
        "retryable": True,
    }
    return Response(
        status_code=429,
        payload=payload,
        headers={"retry-after": str(exc.retry_after_seconds)},
    )


@app.exception_handler(HTTPException)
def handle_http_exception(exc: HTTPException, request_id: str) -> Response:
    log_error(
        feature="ops-003",
        event="api_http_error",
        request_id=request_id,
        logger_name="oh_my_stock.api",
        code=exc.code or "http_error",
        status_code=exc.status_code,
        details=exc.details,
    )
    retryable = bool(exc.details.get("retryable")) if isinstance(exc.details, dict) else False
    payload = {
        "code": exc.code or "http_error",
        "message": exc.message or "Request failed",
        "details": exc.details,
        "request_id": request_id,
        "retryable": retryable,
    }
    return Response(status_code=exc.status_code, payload=payload)


def _parse_event_page_size(size_text: str | None) -> int:
    raw = (size_text or str(_DEFAULT_EVENT_PAGE_SIZE)).strip()
    try:
        size = int(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="size must be an integer",
            details={"size": raw},
        ) from exc
    if size < 1 or size > _MAX_EVENT_PAGE_SIZE:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message=f"size must be between 1 and {_MAX_EVENT_PAGE_SIZE}",
            details={"size": size},
        )
    return size


def _parse_event_cursor(
    cursor_text: str | None,
    *,
    sort: str,
) -> tuple[datetime, str] | None:
    if not cursor_text:
        return None
    parsed_time, separator, parsed_id = cursor_text.rpartition("|")
    if separator != "|" or not parsed_time or not parsed_id.strip():
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="Invalid cursor format",
            details={"cursor": cursor_text, "sort": sort},
        )
    try:
        cursor_time = parse_utc_datetime(parsed_time)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="Invalid cursor format",
            details={"cursor": cursor_text, "sort": sort},
        ) from exc
    return cursor_time, parsed_id.strip()


def _apply_event_cursor(
    items: list[dict[str, object]],
    *,
    cursor: tuple[datetime, str] | None,
    sort: str,
) -> list[dict[str, object]]:
    if cursor is None:
        return items
    cursor_time, cursor_id = cursor
    filtered: list[dict[str, object]] = []
    for item in items:
        item_id = str(item["id"])
        item_time = parse_utc_datetime(str(item["detected_at_utc"]))
        item_key = (item_time, item_id)
        cursor_key = (cursor_time, cursor_id)
        if sort == "detected_at_desc" and item_key < cursor_key:
            filtered.append(item)
        if sort == "detected_at_asc" and item_key > cursor_key:
            filtered.append(item)
    return filtered


def _build_event_cursor(item: dict[str, object]) -> str:
    return f"{item['detected_at_utc']}|{item['id']}"
