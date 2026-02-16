from __future__ import annotations

import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from fastapi.testclient import TestClient


class EventsErrorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        price_event_store.set_failure_mode(None)

    def test_transient_store_error_returns_503_retryable_true(self) -> None:
        price_event_store.set_failure_mode("transient")

        response = self.client.get("/v1/events", headers={"X-Request-ID": "req-events-503"})
        body = response.json()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["code"], "temporarily_unavailable")
        self.assertTrue(body["retryable"])
        self.assertTrue(body["details"]["retryable"])
        self.assertEqual(body["request_id"], "req-events-503")

    def test_validation_error_returns_400_retryable_false(self) -> None:
        response = self.client.get("/v1/events?cursor=invalid-cursor-format")
        body = response.json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "invalid_input")
        self.assertFalse(body["retryable"])
        self.assertIn("request_id", body)


if __name__ == "__main__":
    unittest.main()
