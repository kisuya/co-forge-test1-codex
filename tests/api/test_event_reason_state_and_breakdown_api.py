from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.reasons import EventReason, event_reason_store
from apps.worker.detection import detect_price_event
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient


class EventReasonStateAndBreakdownApiTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        event_reason_store.clear()
        self.client = TestClient(app)
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_event_detail_exposes_verified_reason_state_and_breakdown_fields(self) -> None:
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
        self.assertEqual(body["event"]["reason_status"], "verified")
        self.assertIsNone(body["event"]["revision_hint"])
        self.assertIn("weights", body["event"]["confidence_breakdown"])
        self.assertIn("signals", body["event"]["confidence_breakdown"])
        self.assertIn("score_breakdown", body["event"]["confidence_breakdown"])
        self.assertAlmostEqual(
            body["event"]["confidence_breakdown"]["score_breakdown"]["total"],
            body["event"]["reasons"][0]["confidence_score"],
            places=3,
        )
        self.assertEqual(
            body["event"]["explanation_text"],
            body["event"]["reasons"][0]["explanation"]["explanation_text"],
        )

    def test_event_detail_reports_collecting_evidence_when_reason_missing(self) -> None:
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
        self.assertEqual(body["event"]["reason_status"], "collecting_evidence")
        self.assertEqual(body["event"]["confidence_breakdown"]["score_breakdown"]["total"], 0.0)
        self.assertTrue(body["event"]["explanation_text"])
        self.assertTrue(body["event"]["revision_hint"])

    def test_event_detail_uses_safe_defaults_for_partial_reason_explanation(self) -> None:
        event = detect_price_event(
            symbol="NVDA",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.detected_at,
        )
        assert event is not None

        event_reason_store.replace_event_reasons(
            event["id"],
            [
                EventReason(
                    id="reason-partial",
                    event_id=event["id"],
                    rank=1,
                    reason_type="news",
                    confidence_score=0.62,
                    summary="partial explanation payload",
                    source_url="https://news.example/nvda",
                    published_at=event["detected_at_utc"],
                    explanation={"score_breakdown": {"total": 0.62}},
                )
            ],
        )

        response = self.client.get(f"/v1/events/{event['id']}")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["event"]["reason_status"], "verified")
        self.assertIn("weights", body["event"]["confidence_breakdown"])
        self.assertIn("signals", body["event"]["confidence_breakdown"])
        self.assertIn("score_breakdown", body["event"]["confidence_breakdown"])
        self.assertIn("event_match", body["event"]["confidence_breakdown"]["weights"])
        self.assertIn("event_match", body["event"]["confidence_breakdown"]["signals"])
        self.assertIn("event_match", body["event"]["confidence_breakdown"]["score_breakdown"])
        self.assertTrue(body["event"]["explanation_text"])
        self.assertTrue(body["event"]["revision_hint"])


if __name__ == "__main__":
    unittest.main()
