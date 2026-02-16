from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.user_thresholds import user_threshold_store


def register_threshold_routes(app: FastAPI) -> None:
    @app.post("/v1/thresholds")
    def upsert_user_threshold(request: Request, body: dict[str, object]) -> dict[str, object]:
        user = require_authenticated_user(request)
        window_minutes = _parse_window_minutes(body.get("window_minutes"))
        threshold_pct = _parse_threshold_pct(body.get("threshold_pct"))
        try:
            threshold = user_threshold_store.set_threshold(
                user_id=user.user_id,
                window_minutes=window_minutes,
                threshold_pct=threshold_pct,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid threshold payload",
                details={"error": str(exc)},
            ) from exc
        return {"threshold": threshold.to_dict()}

    @app.get("/v1/thresholds")
    def list_user_thresholds(request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        items = [item.to_dict() for item in user_threshold_store.list_thresholds(user_id=user.user_id)]
        return {"items": items, "count": len(items)}


def _parse_window_minutes(raw: object) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="window_minutes must be an integer",
            details={"window_minutes": raw},
        ) from exc


def _parse_threshold_pct(raw: object) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message="threshold_pct must be numeric",
            details={"threshold_pct": raw},
        ) from exc
