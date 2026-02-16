from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.reasons import event_reason_store
from apps.worker.detection import detect_price_event
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient


class EventsHistoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        event_reason_store.clear()
        self.client = TestClient(app)
        self.now = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

        self.recent_us = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.now - timedelta(days=1),
        )
        self.recent_kr = detect_price_event(
            symbol="005930",
            market="KR",
            baseline_price=100.0,
            current_price=95.0,
            window_minutes=5,
            detected_at_utc=self.now - timedelta(days=2),
        )
        self.old_event = detect_price_event(
            symbol="OLD1",
            market="US",
            baseline_price=100.0,
            current_price=110.0,
            window_minutes=1440,
            detected_at_utc=self.now - timedelta(days=40),
        )

        for event in [self.recent_us, self.recent_kr, self.old_event]:
            assert event is not None
            rank_event_reasons(
                event_id=event["id"],
                detected_at_utc=event["detected_at_utc"],
                candidates=[
                    {
                        "reason_type": "news",
                        "summary": "headline",
                        "source_url": f"https://news.example/{event['symbol'].lower()}",
                        "published_at": event["detected_at_utc"],
                    }
                ],
            )

    def test_list_events_returns_recent_30_days(self) -> None:
        response = self.client.get("/v1/events?now=2026-02-16T12:00:00Z")
        body = response.json()

        symbols = [item["symbol"] for item in body["items"]]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 2)
        self.assertIn("AAPL", symbols)
        self.assertIn("005930", symbols)
        self.assertNotIn("OLD1", symbols)

    def test_list_events_supports_symbol_and_date_filters(self) -> None:
        response = self.client.get(
            "/v1/events?symbol=AAPL&from=2026-02-10T00:00:00Z&to=2026-02-16T00:00:00Z&now=2026-02-16T12:00:00Z"
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["symbol"], "AAPL")

    def test_event_detail_returns_reasons_with_source_url(self) -> None:
        assert self.recent_us is not None
        response = self.client.get(f"/v1/events/{self.recent_us['id']}")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["event"]["id"], self.recent_us["id"])
        self.assertGreaterEqual(len(body["event"]["reasons"]), 1)
        self.assertTrue(body["event"]["reasons"][0]["source_url"])

    def test_event_detail_missing_returns_standard_error(self) -> None:
        response = self.client.get("/v1/events/not-found")
        body = response.json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(body["code"], "event_not_found")
        self.assertIn("request_id", body)
        self.assertIn("message", body)


if __name__ == "__main__":
    unittest.main()
