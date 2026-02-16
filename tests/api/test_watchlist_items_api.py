from __future__ import annotations

import unittest

from apps.api.main import app
from apps.domain.watchlists import watchlist_service
from fastapi.testclient import TestClient


class WatchlistItemsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        watchlist_service.clear()
        self.client = TestClient(app)

    def test_create_item_returns_201_for_new_symbol(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "005930", "market": "KR", "user_id": "u1"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertFalse(body["is_duplicate"])
        self.assertEqual(body["item"]["symbol"], "005930")
        self.assertEqual(body["item"]["market"], "KR")
        self.assertEqual(body["item"]["user_id"], "u1")
        self.assertTrue(body["item"]["created_at_utc"].endswith("Z"))

    def test_duplicate_create_returns_existing_item(self) -> None:
        first = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "AAPL", "market": "US", "user_id": "u1"},
        ).json()
        second_response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "aapl", "market": "us", "user_id": "u1"},
        )
        second = second_response.json()

        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second["is_duplicate"])
        self.assertEqual(first["item"]["id"], second["item"]["id"])

    def test_invalid_market_returns_standard_error(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "TSLA", "market": "JP"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "invalid_input")
        self.assertIn("request_id", body)
        self.assertIn("details", body)

    def test_delete_item_and_missing_item(self) -> None:
        create = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "MSFT", "market": "US"},
        ).json()
        item_id = create["item"]["id"]

        deleted = self.client.delete(f"/v1/watchlists/items/{item_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])

        missing = self.client.delete(f"/v1/watchlists/items/{item_id}")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["code"], "watchlist_item_not_found")


if __name__ == "__main__":
    unittest.main()
