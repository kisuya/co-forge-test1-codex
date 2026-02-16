from __future__ import annotations

from fastapi import HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.portfolio_holdings_db import portfolio_holdings_db_service
from apps.domain.portfolio_impact import estimate_portfolio_event_impact
from apps.domain.reasons import event_reason_store


def serialize_event(event: object, *, request: Request | None = None) -> dict[str, object]:
    event_payload = event.to_dict()
    reasons = [reason.to_dict() for reason in event_reason_store.list_by_event(event_payload["id"])]
    event_payload["reasons"] = reasons
    event_payload["portfolio_impact"] = build_portfolio_impact(event_payload, request=request)
    return event_payload


def build_portfolio_impact(
    event_payload: dict[str, object],
    *,
    request: Request | None,
) -> dict[str, object] | None:
    if request is None:
        return None
    if not request.headers.get("authorization", "").strip():
        return None

    try:
        user = require_authenticated_user(request)
    except HTTPException:
        return None

    holding = portfolio_holdings_db_service.get_by_symbol(
        user_id=user.user_id,
        symbol=str(event_payload["symbol"]),
    )
    if holding is None:
        return None

    try:
        impact = estimate_portfolio_event_impact(
            market=str(event_payload["market"]),
            qty=holding.qty,
            avg_price=holding.avg_price,
            change_pct=float(event_payload["change_pct"]),
        )
    except ValueError:
        return None
    impact["symbol"] = holding.symbol
    return impact
