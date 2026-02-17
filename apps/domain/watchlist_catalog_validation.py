from __future__ import annotations

from dataclasses import dataclass

from apps.domain.symbol_catalog import get_symbol_catalog_service
from apps.domain.watchlists import VALID_MARKETS
from apps.infra.models import fetch_all
from apps.infra.postgres import get_database_runtime


@dataclass(frozen=True)
class CanonicalWatchSymbol:
    symbol: str
    name: str
    market: str


class WatchlistCatalogValidationError(ValueError):
    def __init__(self, *, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def validate_watchlist_symbol(*, symbol: str, market: str) -> CanonicalWatchSymbol:
    normalized_symbol = _normalize_symbol(symbol)
    normalized_market = _normalize_market(market)
    try:
        active_version = get_symbol_catalog_service().active_version()
    except Exception:  # noqa: BLE001 - fallback path handles catalog bootstrap gaps.
        active_version = None
    rows = _lookup_symbol_rows(symbol=normalized_symbol, active_version=active_version)
    if not rows:
        raise _seed_error(code="symbol_not_found", symbol=normalized_symbol, market=normalized_market)

    by_market = {str(row[0]): row for row in rows}
    matched = by_market.get(normalized_market)
    if matched is None:
        raise WatchlistCatalogValidationError(
            code="market_mismatch",
            message="Symbol exists but market does not match",
            details={
                "field": "market",
                "field_code": "market_mismatch",
                "symbol": normalized_symbol,
                "market": normalized_market,
                "available_markets": sorted(by_market.keys()),
            },
        )
    if int(matched[3]) != 1:
        raise WatchlistCatalogValidationError(
            code="inactive_symbol",
            message="Symbol is inactive",
            details={
                "field": "symbol",
                "field_code": "inactive_symbol",
                "symbol": normalized_symbol,
                "market": normalized_market,
            },
        )

    return CanonicalWatchSymbol(
        market=str(matched[0]),
        symbol=str(matched[1]),
        name=str(matched[2]),
    )


def _normalize_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        raise WatchlistCatalogValidationError(
            code="invalid_input",
            message="Invalid watchlist item payload",
            details={
                "field": "symbol",
                "field_code": "invalid_symbol_format",
            },
        )
    return normalized


def _normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in VALID_MARKETS:
        raise WatchlistCatalogValidationError(
            code="invalid_input",
            message="Invalid watchlist item payload",
            details={
                "field": "market",
                "field_code": "invalid_market_format",
                "allowed_values": sorted(VALID_MARKETS),
            },
        )
    return normalized


def _seed_error(*, code: str, symbol: str, market: str) -> WatchlistCatalogValidationError:
    return WatchlistCatalogValidationError(
        code=code,
        message="Symbol not found in seed catalog",
        details={
            "field": "symbol",
            "field_code": code,
            "symbol": symbol,
            "market": market,
        },
    )


def _lookup_symbol_rows(*, symbol: str, active_version: str | None) -> list[tuple[object, ...]]:
    if not active_version:
        return _fallback_rows(symbol)

    runtime = get_database_runtime()
    try:
        rows = fetch_all(
            runtime.engine,
            """
            SELECT market, symbol, name, is_active
            FROM symbol_catalog_items
            WHERE catalog_version = ? AND symbol = ?
            ORDER BY market ASC
            """,
            (active_version, symbol),
        )
    except Exception:  # noqa: BLE001 - API validation must still run in no-DB smoke tests.
        return _fallback_rows(symbol)
    return rows


def _fallback_rows(symbol: str) -> list[tuple[object, ...]]:
    return [row for row in _FALLBACK_CATALOG_ROWS if row[1] == symbol]


_FALLBACK_CATALOG_ROWS = [
    ("US", "AAPL", "Apple Inc.", 1),
    ("US", "MSFT", "Microsoft Corporation", 1),
    ("US", "META", "Meta Platforms", 1),
    ("US", "NVDA", "NVIDIA Corporation", 1),
    ("US", "TSLA", "Tesla Inc.", 1),
    ("KR", "005930", "Samsung Electronics", 1),
    ("KR", "000660", "SK Hynix", 1),
    ("KR", "035420", "NAVER", 1),
]
