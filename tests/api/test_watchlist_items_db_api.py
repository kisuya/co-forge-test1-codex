from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.infra.models import create_core_schema, drop_core_schema, fetch_all
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class WatchlistItemsDbApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="watchlist-db-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/watchlist.sqlite"
        os.environ["JWT_SECRET"] = "watchlist-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-watchlist-db-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

        self.user_a = self.client.post(
            "/v1/auth/signup",
            json={"email": "watch-a@example.com", "password": "watch-password-a"},
        ).json()
        self.user_b = self.client.post(
            "/v1/auth/signup",
            json={"email": "watch-b@example.com", "password": "watch-password-b"},
        ).json()

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_duplicate_registration_returns_200_with_existing_item(self) -> None:
        headers = self._auth(self.user_a["access_token"])
        first = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "AAPL", "market": "US", "user_id": self.user_b["user_id"]},
            headers=headers,
        )
        second = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "aapl", "market": "us"},
            headers=headers,
        )

        first_body = first.json()
        second_body = second.json()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first_body["is_duplicate"])
        self.assertTrue(second_body["is_duplicate"])
        self.assertEqual(first_body["item"]["id"], second_body["item"]["id"])
        self.assertEqual(second_body["item"]["user_id"], self.user_a["user_id"])

        rows = fetch_all(
            self.runtime.engine,
            """
            SELECT COUNT(*) FROM watchlist_items
            WHERE user_id = ? AND market = ? AND symbol = ?
            """,
            (self.user_a["user_id"], "US", "AAPL"),
        )
        self.assertEqual(rows[0][0], 1)

    def test_cross_user_delete_returns_404(self) -> None:
        create = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "005930", "market": "KR"},
            headers=self._auth(self.user_a["access_token"]),
        ).json()
        item_id = create["item"]["id"]

        blocked = self.client.delete(
            f"/v1/watchlists/items/{item_id}",
            headers=self._auth(self.user_b["access_token"]),
        )
        self.assertEqual(blocked.status_code, 404)
        self.assertEqual(blocked.json()["code"], "watchlist_item_not_found")

        owned = self.client.delete(
            f"/v1/watchlists/items/{item_id}",
            headers=self._auth(self.user_a["access_token"]),
        )
        self.assertEqual(owned.status_code, 200)
        self.assertTrue(owned.json()["deleted"])

    def test_create_response_includes_utc_timestamp(self) -> None:
        response = self.client.post(
            "/v1/watchlists/items",
            json={"symbol": "MSFT", "market": "US"},
            headers=self._auth(self.user_a["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(body["item"]["created_at_utc"].endswith("Z"))

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
