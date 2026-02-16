from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from fastapi.testclient import TestClient


class PortfolioHoldingsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="portfolio-holdings-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/portfolio.sqlite"
        os.environ["JWT_SECRET"] = "portfolio-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-portfolio-setup")
        create_core_schema(self.runtime.engine)
        self.client = TestClient(app)

        self.user_a = self.client.post(
            "/v1/auth/signup",
            json={"email": "portfolio-a@example.com", "password": "portfolio-password-a"},
        ).json()
        self.user_b = self.client.post(
            "/v1/auth/signup",
            json={"email": "portfolio-b@example.com", "password": "portfolio-password-b"},
        ).json()

    def tearDown(self) -> None:
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_upsert_same_symbol_updates_existing_holding(self) -> None:
        first = self.client.post(
            "/v1/portfolios/holdings",
            json={"symbol": "AAPL", "qty": 3, "avg_price": 150.5},
            headers=self._auth(self.user_a["access_token"]),
        )
        second = self.client.post(
            "/v1/portfolios/holdings",
            json={"symbol": "aapl", "qty": 5, "avg_price": 152.75},
            headers=self._auth(self.user_a["access_token"]),
        )
        listing = self.client.get(
            "/v1/portfolios/holdings",
            headers=self._auth(self.user_a["access_token"]),
        )

        first_body = first.json()
        second_body = second.json()
        list_body = listing.json()

        self.assertEqual(first.status_code, 201)
        self.assertTrue(first_body["created"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second_body["created"])
        self.assertEqual(first_body["holding"]["id"], second_body["holding"]["id"])

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(list_body["count"], 1)
        self.assertEqual(list_body["items"][0]["symbol"], "AAPL")
        self.assertEqual(list_body["items"][0]["qty"], 5.0)
        self.assertEqual(list_body["items"][0]["avg_price"], 152.75)

    def test_invalid_qty_or_avg_price_returns_400(self) -> None:
        invalid_payloads = [
            {"symbol": "AAPL", "qty": 0, "avg_price": 100},
            {"symbol": "AAPL", "qty": 1, "avg_price": -1},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/v1/portfolios/holdings",
                    json=payload,
                    headers=self._auth(self.user_a["access_token"]),
                )
                body = response.json()
                self.assertEqual(response.status_code, 400)
                self.assertEqual(body["code"], "invalid_input")

    def test_cross_user_delete_returns_404(self) -> None:
        create = self.client.post(
            "/v1/portfolios/holdings",
            json={"symbol": "MSFT", "qty": 2, "avg_price": 410.2},
            headers=self._auth(self.user_a["access_token"]),
        )
        holding_id = create.json()["holding"]["id"]

        blocked = self.client.delete(
            f"/v1/portfolios/holdings/{holding_id}",
            headers=self._auth(self.user_b["access_token"]),
        )
        owned = self.client.delete(
            f"/v1/portfolios/holdings/{holding_id}",
            headers=self._auth(self.user_a["access_token"]),
        )

        self.assertEqual(blocked.status_code, 404)
        self.assertEqual(blocked.json()["code"], "portfolio_holding_not_found")
        self.assertEqual(owned.status_code, 200)
        self.assertTrue(owned.json()["deleted"])

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
