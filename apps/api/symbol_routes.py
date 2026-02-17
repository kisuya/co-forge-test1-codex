from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from apps.domain.symbol_search import get_symbol_search_service
from apps.infra.observability import log_info


def register_symbol_routes(app: FastAPI) -> None:
    @app.get("/v1/symbols/search")
    def search_symbols(request: Request) -> dict[str, object]:
        query = (request.query_params.get("q") or "").strip()
        market = (request.query_params.get("market") or "").strip()
        service = get_symbol_search_service()
        try:
            records = service.search(query=query, market=market)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                code="invalid_input",
                message="Invalid symbol search query",
                details={"error": str(exc), "q": query, "market": market},
            ) from exc

        items = [record.to_dict() for record in records]
        log_info(
            feature="watch-004",
            event="symbol_search_succeeded",
            request_id=request.request_id,
            logger_name="oh_my_stock.api",
            query=query,
            market=market,
            count=len(items),
        )
        metadata = service.catalog_metadata()
        return {
            "items": items,
            "count": len(items),
            "catalog_version": metadata["catalog_version"],
            "catalog_refreshed_at_utc": metadata["catalog_refreshed_at_utc"],
        }
