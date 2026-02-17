from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.symbol_catalog import (
    CatalogRecord,
    CatalogSnapshot,
    SymbolCatalogService,
    reset_symbol_catalog_service,
    set_symbol_catalog_service,
)
from apps.domain.watchlists import watchlist_service
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class _SingleSnapshotSource:
    def __init__(self, snapshot: CatalogSnapshot) -> None:
        self._snapshot = snapshot

    def fetch(self, *, since_version: str | None) -> CatalogSnapshot:
        return self._snapshot


class WatchlistSeedCatalogValidationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="watchlist-seed-catalog-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/watchlist.sqlite"
        os.environ["JWT_SECRET"] = "watch-seed-secret"

        reset_database_runtime()
        reset_symbol_catalog_service()
        watchlist_service.clear()

        self.runtime = initialize_database_runtime(request_id="req-watch-006-setup")
        create_core_schema(self.runtime.engine)

        self.catalog_service = SymbolCatalogService(
            bootstrap_records=[
                CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US"),
                CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR"),
            ]
        )
        self.catalog_service.sync_from_source(
            source=_SingleSnapshotSource(
                CatalogSnapshot(
                    version="watch-006-v1",
                    mode="full",
                    records=[
                        CatalogRecord(symbol="AAPL", name="Apple Inc.", market="US", is_active=True),
                        CatalogRecord(symbol="INTC", name="Intel Corporation", market="US", is_active=False),
                        CatalogRecord(symbol="005930", name="Samsung Electronics", market="KR", is_active=True),
                    ],
                )
            )
        )
        set_symbol_catalog_service(self.catalog_service)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_symbol_catalog_service()
        watchlist_service.clear()
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_create_item_returns_canonical_symbol_and_name(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "aapl", "market": "us", "user_id": "user-1"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["item"]["symbol"], "AAPL")
        self.assertEqual(body["item"]["market"], "US")
        self.assertEqual(body["item"]["symbol_name"], "Apple Inc.")
        self.assertFalse(body["is_duplicate"])

    def test_symbol_not_found_returns_symbol_not_found_code(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "ZZZZ", "market": "US", "user_id": "user-1"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "symbol_not_found")
        self.assertEqual(body["details"]["field_code"], "symbol_not_found")

    def test_market_mismatch_returns_market_mismatch_code(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "005930", "market": "US", "user_id": "user-1"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "market_mismatch")
        self.assertEqual(body["details"]["field_code"], "market_mismatch")
        self.assertEqual(body["details"]["available_markets"], ["KR"])

    def test_inactive_symbol_returns_inactive_symbol_code(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "INTC", "market": "US", "user_id": "user-1"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "inactive_symbol")
        self.assertEqual(body["details"]["field_code"], "inactive_symbol")

    def test_invalid_format_returns_invalid_input_with_field_code(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "AAPL", "market": "JP", "user_id": "user-1"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "invalid_input")
        self.assertEqual(body["details"]["field"], "market")
        self.assertEqual(body["details"]["field_code"], "invalid_market_format")

    def test_authenticated_create_also_uses_seed_validation(self) -> None:
        signup = self.client.post(
            "/v1/auth/signup",
            json={"email": "seed-user@example.com", "password": "seed-password"},
        ).json()
        headers = {"Authorization": f"Bearer {signup['access_token']}"}

        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "AAPL", "market": "US", "user_id": "ignored-user"},
            headers=headers,
        )
        body = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["item"]["symbol"], "AAPL")
        self.assertEqual(body["item"]["user_id"], signup["user_id"])
        self.assertEqual(body["item"]["symbol_name"], "Apple Inc.")


if __name__ == "__main__":
    unittest.main()
