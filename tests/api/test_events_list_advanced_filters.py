from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.reasons import event_reason_store
from apps.worker.detection import detect_price_event
from fastapi.testclient import TestClient


class EventsListAdvancedFiltersTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        event_reason_store.clear()
        self.client = TestClient(app)
        self.now = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

        detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.now - timedelta(hours=1),
            session_label="regular",
        )
        detect_price_event(
            symbol="MSFT",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.now - timedelta(hours=2),
            session_label="regular",
        )
        detect_price_event(
            symbol="TSLA",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.now - timedelta(hours=3),
            session_label="pre",
        )
        detect_price_event(
            symbol="NVDA",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.now - timedelta(hours=4),
            session_label="regular",
        )

    def test_session_filter_sort_and_cursor_pagination(self) -> None:
        first = self.client.get(
            "/v1/events?session=regular&sort=detected_at_desc&size=2&now=2026-02-16T12:00:00Z"
        )
        first_body = first.json()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first_body["count"], 2)
        self.assertTrue(first_body["next_cursor"])
        self.assertTrue(all(item["session_label"] == "regular" for item in first_body["items"]))
        self.assertEqual([item["symbol"] for item in first_body["items"]], ["AAPL", "MSFT"])

        second = self.client.get(
            f"/v1/events?session=regular&sort=detected_at_desc&size=2&cursor={first_body['next_cursor']}&now=2026-02-16T12:00:00Z"
        )
        second_body = second.json()

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second_body["count"], 1)
        self.assertEqual(second_body["items"][0]["symbol"], "NVDA")
        self.assertIsNone(second_body["next_cursor"])

    def test_invalid_date_or_cursor_returns_400(self) -> None:
        invalid_date = self.client.get("/v1/events?from=not-a-date")
        invalid_cursor = self.client.get("/v1/events?cursor=bad-cursor")

        self.assertEqual(invalid_date.status_code, 400)
        self.assertEqual(invalid_date.json()["code"], "invalid_input")
        self.assertEqual(invalid_cursor.status_code, 400)
        self.assertEqual(invalid_cursor.json()["code"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
