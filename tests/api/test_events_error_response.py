from __future__ import annotations

import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from fastapi.testclient import TestClient


class EventsErrorResponseTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        price_event_store.set_failure_mode(None)

    def test_list_events_returns_retryable_standard_error(self) -> None:
        price_event_store.set_failure_mode("transient")
        response = self.client.get("/v1/events", headers={"X-Request-ID": "req-events-list"})
        body = response.json()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["code"], "temporarily_unavailable")
        self.assertIn("retry", body["message"].lower())
        self.assertTrue(body["details"]["retryable"])
        self.assertEqual(body["request_id"], "req-events-list")

    def test_event_detail_returns_retryable_standard_error(self) -> None:
        price_event_store.set_failure_mode("transient")
        response = self.client.get("/v1/events/evt-unknown")
        body = response.json()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["code"], "temporarily_unavailable")
        self.assertTrue(body["details"]["retryable"])
        self.assertIn("request_id", body)


if __name__ == "__main__":
    unittest.main()
