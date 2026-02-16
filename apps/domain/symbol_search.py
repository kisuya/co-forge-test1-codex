from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

from apps.domain.watchlists import VALID_MARKETS
from apps.infra.redis_client import RedisClient, RetryableRedisError

_MIN_QUERY_LENGTH = 2
_DEFAULT_CACHE_TTL_SECONDS = 300
_CACHE_KEY_PREFIX = "symbols:search"


@dataclass(frozen=True)
class SymbolRecord:
    ticker: str
    name: str
    market: str

    def to_dict(self) -> dict[str, str]:
        return {"ticker": self.ticker, "name": self.name, "market": self.market}


class SymbolCatalog(Protocol):
    def search(self, *, query: str, market: str) -> list[SymbolRecord]: ...


class StaticSymbolCatalog:
    def __init__(self, records: list[SymbolRecord]) -> None:
        self._records = list(records)

    def search(self, *, query: str, market: str) -> list[SymbolRecord]:
        normalized_query = query.upper()
        normalized_market = market.upper()
        matches: list[SymbolRecord] = []
        for record in self._records:
            if record.market != normalized_market:
                continue
            if normalized_query in record.ticker or normalized_query in record.name.upper():
                matches.append(record)
        return matches


class SymbolSearchService:
    def __init__(
        self,
        *,
        redis_client: RedisClient | None = None,
        catalog: SymbolCatalog | None = None,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        if cache_ttl_seconds < 1:
            raise ValueError("cache_ttl_seconds must be at least 1")
        self._redis_client = redis_client or RedisClient()
        self._catalog = catalog or StaticSymbolCatalog(_DEFAULT_SYMBOLS)
        self._cache_ttl_seconds = cache_ttl_seconds

    def search(self, *, query: str, market: str) -> list[SymbolRecord]:
        normalized_query = _normalize_query(query)
        normalized_market = _normalize_market(market)
        cache_key = _cache_key(normalized_query, normalized_market)

        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        results = self._catalog.search(query=normalized_query, market=normalized_market)
        self._write_cache(cache_key, results)
        return results

    def _read_cache(self, key: str) -> list[SymbolRecord] | None:
        try:
            payload = self._redis_client.get(key)
        except RetryableRedisError:
            return None
        if payload is None:
            return None
        return _deserialize_records(payload)

    def _write_cache(self, key: str, records: list[SymbolRecord]) -> None:
        payload = _serialize_records(records)
        try:
            self._redis_client.set(key, payload, ttl_seconds=self._cache_ttl_seconds)
        except RetryableRedisError:
            return


def _normalize_query(query: str) -> str:
    normalized = (query or "").strip()
    if len(normalized) < _MIN_QUERY_LENGTH:
        raise ValueError("q must be at least 2 characters")
    return normalized.upper()


def _normalize_market(market: str) -> str:
    normalized = (market or "").strip().upper()
    if normalized not in VALID_MARKETS:
        raise ValueError("market must be KR or US")
    return normalized


def _cache_key(query: str, market: str) -> str:
    return f"{_CACHE_KEY_PREFIX}:{market}:{query}"


def _serialize_records(records: list[SymbolRecord]) -> str:
    payload = [record.to_dict() for record in records]
    return json.dumps(payload, sort_keys=True)


def _deserialize_records(payload: str) -> list[SymbolRecord] | None:
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list):
        return None

    records: list[SymbolRecord] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        ticker = item.get("ticker")
        name = item.get("name")
        market = item.get("market")
        if not isinstance(ticker, str) or not isinstance(name, str) or not isinstance(market, str):
            return None
        records.append(SymbolRecord(ticker=ticker, name=name, market=market))
    return records


_DEFAULT_SYMBOLS = [
    SymbolRecord(ticker="AAPL", name="Apple Inc.", market="US"),
    SymbolRecord(ticker="MSFT", name="Microsoft Corporation", market="US"),
    SymbolRecord(ticker="NVDA", name="NVIDIA Corporation", market="US"),
    SymbolRecord(ticker="TSLA", name="Tesla Inc.", market="US"),
    SymbolRecord(ticker="005930", name="Samsung Electronics", market="KR"),
    SymbolRecord(ticker="000660", name="SK Hynix", market="KR"),
    SymbolRecord(ticker="035420", name="NAVER", market="KR"),
]

_symbol_search_service: SymbolSearchService | None = None


def get_symbol_search_service() -> SymbolSearchService:
    global _symbol_search_service
    if _symbol_search_service is None:
        _symbol_search_service = SymbolSearchService()
    return _symbol_search_service


def set_symbol_search_service(service: SymbolSearchService) -> None:
    global _symbol_search_service
    _symbol_search_service = service


def reset_symbol_search_service() -> None:
    global _symbol_search_service
    _symbol_search_service = None
