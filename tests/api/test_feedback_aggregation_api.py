from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.feedback import reason_feedback_store
from apps.domain.reasons import event_reason_store
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.detection import detect_price_event
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient


class FeedbackAggregationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="feedback-agg-api-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/feedback_agg.sqlite"
        os.environ["JWT_SECRET"] = "feedback-agg-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-feedback-agg-setup")
        create_core_schema(self.runtime.engine)

        price_event_store.clear()
        event_reason_store.clear()
        reason_feedback_store.clear()
        self.client = TestClient(app)
        self.user = self.client.post(
            "/v1/auth/signup",
            json={"email": "feedback-agg@example.com", "password": "feedback-agg-password"},
        ).json()
        self.headers = {"Authorization": f"Bearer {self.user['access_token']}"}

        aapl_event = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )
        msft_event = detect_price_event(
            symbol="MSFT",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:05:00Z",
        )
        assert aapl_event is not None
        assert msft_event is not None
        self.aapl_event_id = aapl_event["id"]
        self.msft_event_id = msft_event["id"]

        rank_event_reasons(
            event_id=self.aapl_event_id,
            detected_at_utc=aapl_event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "8-K",
                    "source_url": "https://sec.example/8k",
                    "published_at": aapl_event["detected_at_utc"],
                },
                {
                    "reason_type": "news",
                    "summary": "headline",
                    "source_url": "https://news.example/aapl",
                    "published_at": aapl_event["detected_at_utc"],
                },
            ],
        )
        rank_event_reasons(
            event_id=self.msft_event_id,
            detected_at_utc=msft_event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "10-Q",
                    "source_url": "https://sec.example/10q",
                    "published_at": msft_event["detected_at_utc"],
                }
            ],
        )

        aapl_reasons = event_reason_store.list_by_event(self.aapl_event_id)
        msft_reason = event_reason_store.list_by_event(self.msft_event_id)[0]
        self._submit_feedback(self.aapl_event_id, aapl_reasons[0].id, "helpful")
        self._submit_feedback(self.aapl_event_id, aapl_reasons[1].id, "not_helpful")
        self._submit_feedback(self.msft_event_id, msft_reason.id, "helpful")

    def tearDown(self) -> None:
        reason_feedback_store.clear()
        event_reason_store.clear()
        price_event_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_aggregation_returns_ratio_sample_count_and_low_confidence(self) -> None:
        response = self.client.get("/v1/feedback/aggregation?min_samples=2", headers=self.headers)
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 2)
        by_symbol = {item["symbol"]: item for item in body["items"]}
        self.assertEqual(by_symbol["AAPL"]["sample_count"], 2)
        self.assertEqual(by_symbol["AAPL"]["helpful_ratio"], 0.5)
        self.assertFalse(by_symbol["AAPL"]["low_confidence"])
        self.assertEqual(by_symbol["MSFT"]["sample_count"], 1)
        self.assertEqual(by_symbol["MSFT"]["helpful_ratio"], 1.0)
        self.assertTrue(by_symbol["MSFT"]["low_confidence"])

    def test_invalid_filters_return_400(self) -> None:
        invalid_min_samples = self.client.get("/v1/feedback/aggregation?min_samples=0", headers=self.headers)
        invalid_market = self.client.get("/v1/feedback/aggregation?market=JP", headers=self.headers)

        self.assertEqual(invalid_min_samples.status_code, 400)
        self.assertEqual(invalid_min_samples.json()["code"], "invalid_input")
        self.assertEqual(invalid_market.status_code, 400)
        self.assertEqual(invalid_market.json()["code"], "invalid_input")

    def _submit_feedback(self, event_id: str, reason_id: str, feedback: str) -> None:
        response = self.client.post(
            f"/v1/events/{event_id}/feedback",
            json={"reason_id": reason_id, "feedback": feedback},
            headers=self.headers,
        )
        self.assertIn(response.status_code, {200, 201})


if __name__ == "__main__":
    unittest.main()
