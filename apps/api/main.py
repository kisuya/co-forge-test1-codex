from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response

from apps.domain.events import TransientStoreError, parse_utc_datetime, price_event_store
from apps.domain.reasons import event_reason_store
from apps.domain.watchlists import watchlist_service
from apps.infra.postgres import (
    DatabaseConnectionError,
    get_database_runtime,
    initialize_database_runtime,
)

app = FastAPI(title="oh-my-stock API")
initialize_database_runtime(request_id="startup")


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
    return {"status": status}


@app.post("/v1/watchlists/items")
def create_watchlist_item(body: dict[str, str]) -> tuple[dict[str, object], int]:
    try:
        item, is_duplicate = watchlist_service.create_item(
            symbol=body.get("symbol", ""),
            market=body.get("market", ""),
            user_id=body.get("user_id"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="Invalid watchlist item payload",
            details={"error": str(exc)},
        ) from exc

    status_code = 200 if is_duplicate else 201
    return {
        "item": item.to_dict(),
        "is_duplicate": is_duplicate,
    }, status_code


@app.delete("/v1/watchlists/items/{item_id}")
def delete_watchlist_item(item_id: str) -> dict[str, object]:
    deleted = watchlist_service.delete_item(item_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            code="watchlist_item_not_found",
            message="Watchlist item not found",
            details={"item_id": item_id},
        )
    return {"deleted": True, "item_id": item_id}


def _serialize_event(event: object) -> dict[str, object]:
    event_payload = event.to_dict()
    reasons = [reason.to_dict() for reason in event_reason_store.list_by_event(event_payload["id"])]
    event_payload["reasons"] = reasons
    return event_payload


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

    if market and market not in {"KR", "US"}:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="market must be KR or US",
            details={"market": market},
        )

    from_utc = _parse_optional_datetime(query.get("from"), field_name="from")
    to_utc = _parse_optional_datetime(query.get("to"), field_name="to")
    now_utc = _parse_optional_datetime(query.get("now"), field_name="now")

    events = price_event_store.query_events(
        symbol=symbol,
        market=market,
        from_utc=from_utc,
        to_utc=to_utc,
        now_utc=now_utc,
        max_age_days=30,
    )
    items = [_serialize_event(event) for event in events]
    return {"items": items, "count": len(items)}


@app.get("/v1/events/{event_id}")
def get_event_detail(event_id: str) -> dict[str, object]:
    event = price_event_store.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            code="event_not_found",
            message="Event not found",
            details={"event_id": event_id},
        )
    return {"event": _serialize_event(event)}


@app.exception_handler(TransientStoreError)
def handle_transient_store_error(exc: TransientStoreError, request_id: str) -> Response:
    payload = {
        "code": "temporarily_unavailable",
        "message": "Temporary service issue. Please retry.",
        "details": {"retryable": True, "reason": str(exc)},
        "request_id": request_id,
    }
    return Response(status_code=503, payload=payload)


@app.exception_handler(HTTPException)
def handle_http_exception(exc: HTTPException, request_id: str) -> Response:
    payload = {
        "code": exc.code or "http_error",
        "message": exc.message or "Request failed",
        "details": exc.details,
        "request_id": request_id,
    }
    return Response(status_code=exc.status_code, payload=payload)
