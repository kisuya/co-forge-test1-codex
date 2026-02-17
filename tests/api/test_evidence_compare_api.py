from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.api.main import app
from apps.domain.events import price_event_store
from apps.domain.reasons import EventReason, event_reason_store
from apps.worker.detection import detect_price_event
from apps.worker.reasons import rank_event_reasons
from fastapi.testclient import TestClient


class EvidenceCompareApiTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        event_reason_store.clear()
        self.client = TestClient(app)
        self.detected_at = datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc)

    def test_returns_compare_payload_with_classification_and_source_meta(self) -> None:
        event = self._create_event("AAPL")
        rank_event_reasons(
            event_id=event["id"],
            detected_at_utc=event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "Earnings beat expectations and guidance raised",
                    "source_url": "https://news.example/positive",
                    "published_at": "2026-02-18T00:02:00Z",
                },
                {
                    "reason_type": "news",
                    "summary": "Regulator investigation and guidance cut",
                    "source_url": "https://news.example/negative",
                    "published_at": "2026-02-18T00:01:00Z",
                },
            ],
        )

        response = self.client.get(f"/v1/events/{event['id']}/evidence-compare")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "ready")
        self.assertTrue(body["compare_ready"])
        self.assertIsNone(body["fallback_reason"])
        self.assertEqual(body["axis_counts"]["positive"], 1)
        self.assertEqual(body["axis_counts"]["negative"], 1)
        self.assertEqual(len(body["sources"]), 2)
        self.assertTrue(all(item["source_url"].startswith("https://") for item in body["sources"]))
        self.assertNotIn("conclusion", body)

    def test_returns_compare_unavailable_when_only_one_axis_exists(self) -> None:
        event = self._create_event("MSFT")
        rank_event_reasons(
            event_id=event["id"],
            detected_at_utc=event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "Record demand and earnings beat",
                    "source_url": "https://news.example/p1",
                    "published_at": "2026-02-18T00:02:00Z",
                },
                {
                    "reason_type": "news",
                    "summary": "Guidance raised after strong demand",
                    "source_url": "https://news.example/p2",
                    "published_at": "2026-02-18T00:01:00Z",
                },
            ],
        )

        response = self.client.get(f"/v1/events/{event['id']}/evidence-compare")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "compare_unavailable")
        self.assertEqual(body["fallback_reason"], "axis_imbalance")
        self.assertFalse(body["compare_ready"])

    def test_returns_compare_unavailable_when_source_metadata_is_missing(self) -> None:
        event = self._create_event("NVDA")
        event_reason_store.replace_event_reasons(
            event["id"],
            [
                EventReason(
                    id="reason-missing-source",
                    event_id=event["id"],
                    rank=1,
                    reason_type="news",
                    confidence_score=0.73,
                    summary="Earnings beat expectations",
                    source_url="",
                    published_at="2026-02-18T00:03:00Z",
                    explanation={},
                ),
                EventReason(
                    id="reason-valid",
                    event_id=event["id"],
                    rank=2,
                    reason_type="news",
                    confidence_score=0.62,
                    summary="Guidance cut due to demand slowdown",
                    source_url="https://news.example/nvda-negative",
                    published_at="2026-02-18T00:02:00Z",
                    explanation={},
                ),
            ],
        )

        response = self.client.get(f"/v1/events/{event['id']}/evidence-compare")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "compare_unavailable")
        self.assertEqual(body["fallback_reason"], "missing_source_metadata")
        self.assertEqual(body["sources"], [])

    def test_returns_compare_unavailable_for_invalid_permission_token(self) -> None:
        event = self._create_event("TSLA")
        rank_event_reasons(
            event_id=event["id"],
            detected_at_utc=event["detected_at_utc"],
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "Earnings beat expectations",
                    "source_url": "https://news.example/tsla-positive",
                    "published_at": "2026-02-18T00:02:00Z",
                },
                {
                    "reason_type": "news",
                    "summary": "Investigation risk remains",
                    "source_url": "https://news.example/tsla-negative",
                    "published_at": "2026-02-18T00:01:00Z",
                },
            ],
        )

        response = self.client.get(
            f"/v1/events/{event['id']}/evidence-compare",
            headers={"Authorization": "Bearer invalid-token"},
        )
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "compare_unavailable")
        self.assertEqual(body["fallback_reason"], "permission_denied")
        self.assertEqual(body["sources"], [])

    def test_returns_404_when_event_is_missing(self) -> None:
        response = self.client.get("/v1/events/missing-event/evidence-compare")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "event_not_found")

    def _create_event(self, symbol: str) -> dict[str, object]:
        event = detect_price_event(
            symbol=symbol,
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc=self.detected_at,
        )
        assert event is not None
        return event


if __name__ == "__main__":
    unittest.main()
