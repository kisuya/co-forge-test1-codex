from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.events import parse_utc_datetime
from apps.domain.feedback import reason_feedback_store

_VALID_MARKETS = {"KR", "US"}


def register_feedback_routes(app: FastAPI) -> None:
    @app.post("/v1/events/{event_id}/feedback")
    def submit_reason_feedback(event_id: str, request: Request, body: dict[str, object]) -> tuple[dict[str, object], int]:
        user = require_authenticated_user(request)
        reason_id = str(body.get("reason_id", ""))
        feedback_value = str(body.get("feedback", ""))
        try:
            feedback, overwritten = reason_feedback_store.submit(
                user_id=user.user_id,
                event_id=event_id,
                reason_id=reason_id,
                feedback=feedback_value,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid feedback payload",
                details={"error": str(exc)},
            ) from exc
        status_code = 200 if overwritten else 201
        return {"feedback": feedback.to_dict(), "overwritten": overwritten}, status_code

    @app.get("/v1/feedback/aggregation")
    def aggregate_feedback(request: Request) -> dict[str, object]:
        require_authenticated_user(request)
        query = request.query_params
        from_utc = _parse_optional_datetime(query.get("from"), field_name="from")
        to_utc = _parse_optional_datetime(query.get("to"), field_name="to")
        if from_utc and to_utc and from_utc > to_utc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="from must be <= to",
                details={"from": query.get("from"), "to": query.get("to")},
            )

        market = (query.get("market") or "").strip().upper() or None
        if market and market not in _VALID_MARKETS:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="market must be KR or US",
                details={"market": market},
            )
        min_samples = _parse_min_samples(query.get("min_samples"))
        symbol = (query.get("symbol") or "").strip().upper() or None

        try:
            items = reason_feedback_store.aggregate(
                from_utc=from_utc,
                to_utc=to_utc,
                symbol=symbol,
                market=market,
                min_samples=min_samples,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid aggregation filters",
                details={"error": str(exc)},
            ) from exc
        return {"items": items, "count": len(items)}


def _parse_optional_datetime(value: str | None, *, field_name: str):
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


def _parse_min_samples(value: str | None) -> int:
    raw = (value or "3").strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="min_samples must be an integer",
            details={"min_samples": raw},
        ) from exc
    if parsed < 1:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="min_samples must be >= 1",
            details={"min_samples": parsed},
        )
    return parsed
