from __future__ import annotations

import unittest

from apps.api.main import app
from apps.domain.symbol_search import (
    SymbolRecord,
    SymbolSearchService,
    reset_symbol_search_service,
    set_symbol_search_service,
)
from apps.infra.redis_client import InMemoryRedisBackend, RedisClient, RedisConfig
from fastapi.testclient import TestClient


class _CountingCatalog:
    def __init__(self, records: list[SymbolRecord]) -> None:
        self.records = records
        self.calls = 0

    def search(self, *, query: str, market: str) -> list[SymbolRecord]:
        self.calls += 1
        normalized_query = query.upper()
        normalized_market = market.upper()
        matches: list[SymbolRecord] = []
        for record in self.records:
            if record.market != normalized_market:
                continue
            if normalized_query in record.ticker or normalized_query in record.name.upper():
                matches.append(record)
        return matches


class SymbolSearchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_symbol_search_service()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_symbol_search_service()

    def test_search_returns_results_and_uses_cache(self) -> None:
        catalog = _CountingCatalog(
            [SymbolRecord(ticker="AAPL", name="Apple Inc.", market="US")]
        )
        service = SymbolSearchService(
            redis_client=RedisClient(
                config=RedisConfig(redis_url="redis://localhost:6379/0", key_prefix="test-watch-004"),
                backend=InMemoryRedisBackend(),
            ),
            catalog=catalog,
            cache_ttl_seconds=120,
        )
        set_symbol_search_service(service)

        first = self.client.get("/v1/symbols/search?q=ap&market=US")
        second = self.client.get("/v1/symbols/search?q=ap&market=US")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["items"], second.json()["items"])
        self.assertEqual(first.json()["count"], 1)
        self.assertEqual(first.json()["items"][0]["ticker"], "AAPL")
        self.assertEqual(first.json()["items"][0]["name"], "Apple Inc.")
        self.assertEqual(first.json()["items"][0]["market"], "US")
        self.assertEqual(catalog.calls, 1)

    def test_empty_result_returns_200_with_empty_items(self) -> None:
        response = self.client.get("/v1/symbols/search?q=zz&market=KR")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["items"], [])
        self.assertEqual(body["count"], 0)

    def test_invalid_query_or_market_returns_400(self) -> None:
        short_query = self.client.get("/v1/symbols/search?q=A&market=US")
        invalid_market = self.client.get("/v1/symbols/search?q=AA&market=JP")

        self.assertEqual(short_query.status_code, 400)
        self.assertEqual(short_query.json()["code"], "invalid_input")
        self.assertEqual(invalid_market.status_code, 400)
        self.assertEqual(invalid_market.json()["code"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
