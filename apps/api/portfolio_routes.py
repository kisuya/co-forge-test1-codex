from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.api.auth_guard import require_authenticated_user
from apps.domain.portfolio_holdings_db import portfolio_holdings_db_service


def register_portfolio_routes(app: FastAPI) -> None:
    @app.post("/v1/portfolios/holdings")
    @app.post("/v1/portfolio/holdings")
    def upsert_portfolio_holding(request: Request, body: dict[str, object]) -> tuple[dict[str, object], int]:
        user = require_authenticated_user(request)
        symbol = str(body.get("symbol", ""))
        qty = _parse_numeric(body.get("qty"), field_name="qty")
        avg_price = _parse_numeric(body.get("avg_price"), field_name="avg_price")
        try:
            holding, created = portfolio_holdings_db_service.upsert_holding(
                user_id=user.user_id,
                symbol=symbol,
                qty=qty,
                avg_price=avg_price,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid portfolio holding payload",
                details={"error": str(exc)},
            ) from exc
        status_code = 201 if created else 200
        return {"holding": holding.to_dict(), "created": created}, status_code

    @app.get("/v1/portfolios/holdings")
    @app.get("/v1/portfolio/holdings")
    def list_portfolio_holdings(request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        holdings = portfolio_holdings_db_service.list_holdings(user_id=user.user_id)
        items = [item.to_dict() for item in holdings]
        return {"items": items, "count": len(items)}

    @app.delete("/v1/portfolios/holdings/{holding_id}")
    @app.delete("/v1/portfolio/holdings/{holding_id}")
    def delete_portfolio_holding(holding_id: str, request: Request) -> dict[str, object]:
        user = require_authenticated_user(request)
        deleted = portfolio_holdings_db_service.delete_holding(
            holding_id=holding_id,
            user_id=user.user_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=404,
                code="portfolio_holding_not_found",
                message="Portfolio holding not found",
                details={"holding_id": holding_id},
            )
        return {"deleted": True, "holding_id": holding_id}


def _parse_numeric(raw: object, *, field_name: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            code="invalid_input",
            message=f"{field_name} must be numeric",
            details={field_name: raw},
        ) from exc
