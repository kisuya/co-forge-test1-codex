from __future__ import annotations

from datetime import datetime, timezone
import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.reasons import event_reason_store
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.detection import detect_price_event
from fastapi.testclient import TestClient


class EventDetailPortfolioImpactApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="event-detail-portfolio-impact-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/event-detail.sqlite"
        os.environ["JWT_SECRET"] = "event-detail-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-event-detail-portfolio")
        create_core_schema(self.runtime.engine)

        price_event_store.clear()
        event_reason_store.clear()

        self.client = TestClient(app)
        self.user = self.client.post(
            "/v1/auth/signup",
            json={"email": "impact@example.com", "password": "impact-password"},
        ).json()

    def tearDown(self) -> None:
        event_reason_store.clear()
        price_event_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_event_detail_returns_portfolio_impact_for_authenticated_holding(self) -> None:
        create = self.client.post(
            "/v1/portfolios/holdings",
            json={"symbol": "AAPL", "qty": 4, "avg_price": 100},
            headers=self._auth(self.user["access_token"]),
        )
        self.assertEqual(create.status_code, 201)

        event = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc),
        )
        assert event is not None

        response = self.client.get(
            f"/v1/events/{event['id']}",
            headers=self._auth(self.user["access_token"]),
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body["event"]["portfolio_impact"])
        self.assertEqual(body["event"]["portfolio_impact"]["symbol"], "AAPL")
        self.assertEqual(body["event"]["portfolio_impact"]["currency"], "USD")
        self.assertEqual(body["event"]["portfolio_impact"]["estimated_pnl_amount"], 16.0)

    def test_event_detail_keeps_portfolio_impact_null_without_auth(self) -> None:
        self.client.post(
            "/v1/portfolios/holdings",
            json={"symbol": "AAPL", "qty": 4, "avg_price": 100},
            headers=self._auth(self.user["access_token"]),
        )
        event = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc),
        )
        assert event is not None

        response = self.client.get(f"/v1/events/{event['id']}")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(body["event"]["portfolio_impact"])

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
