from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class WatchlistListApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="watchlist-list-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/watchlist_list.sqlite"
        os.environ["JWT_SECRET"] = "watchlist-list-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-watchlist-list-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

        self.user_a = self.client.post(
            "/v1/auth/signup",
            json={"email": "list-a@example.com", "password": "watchlist-list-password-a"},
        ).json()
        self.user_b = self.client.post(
            "/v1/auth/signup",
            json={"email": "list-b@example.com", "password": "watchlist-list-password-b"},
        ).json()

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_default_pagination_returns_user_scoped_items(self) -> None:
        self._create_item(self.user_a["access_token"], "AAPL")
        self._create_item(self.user_a["access_token"], "MSFT")
        self._create_item(self.user_a["access_token"], "TSLA")
        self._create_item(self.user_b["access_token"], "005930", market="KR")

        response = self.client.get(
            "/v1/watchlists/items",
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["size"], 20)
        self.assertEqual(body["total"], 3)
        self.assertEqual(len(body["items"]), 3)
        self.assertTrue(all(item["user_id"] == self.user_a["user_id"] for item in body["items"]))

    def test_pagination_applies_page_and_size(self) -> None:
        for symbol in ("AAPL", "MSFT", "TSLA", "NVDA", "META"):
            self._create_item(self.user_a["access_token"], symbol)

        response = self.client.get(
            "/v1/watchlists/items?page=2&size=2",
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["size"], 2)
        self.assertEqual(body["total"], 5)
        self.assertEqual(len(body["items"]), 2)

    def test_invalid_page_or_size_returns_400(self) -> None:
        invalid_page = self.client.get(
            "/v1/watchlists/items?page=0&size=20",
            headers=self._auth(self.user_a["access_token"]),
        )
        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(invalid_page.json()["code"], "invalid_input")

        invalid_size = self.client.get(
            "/v1/watchlists/items?page=1&size=101",
            headers=self._auth(self.user_a["access_token"]),
        )
        self.assertEqual(invalid_size.status_code, 400)
        self.assertEqual(invalid_size.json()["code"], "invalid_input")

    def _create_item(self, token: str, symbol: str, *, market: str = "US") -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": symbol, "market": market},
            headers=self._auth(token),
        )
        self.assertIn(response.status_code, {200, 201})

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
