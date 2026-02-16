from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.reasons import event_reason_store
from apps.worker.detection import detect_price_event
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient


class EventDetailExplanationsTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        event_reason_store.clear()
        self.client = TestClient(app)
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_event_detail_includes_reason_explanation_and_portfolio_slot(self) -> None:
        event = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.detected_at,
        )
        assert event is not None
        rank_event_reasons(
            event_id=event["id"],
            detected_at_utc=event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "8-K filed",
                    "source_url": "https://sec.example/8k",
                    "published_at": event["detected_at_utc"],
                }
            ],
        )

        response = self.client.get(f"/v1/events/{event['id']}")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["event"]["id"], event["id"])
        self.assertIn("explanation", body["event"]["reasons"][0])
        self.assertIsNone(body["event"]["portfolio_impact"])

    def test_portfolio_impact_slot_is_null_when_no_data(self) -> None:
        event = detect_price_event(
            symbol="MSFT",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.detected_at,
        )
        assert event is not None

        response = self.client.get(f"/v1/events/{event['id']}")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(body["event"]["portfolio_impact"])


if __name__ == "__main__":
    unittest.main()
