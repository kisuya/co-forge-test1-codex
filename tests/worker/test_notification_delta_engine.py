from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.worker.notification_delta_engine import compute_notification_delta


class NotificationDeltaEngineTests(unittest.TestCase):
    def test_computes_added_removed_sources_and_confidence_delta(self) -> None:
        payload = compute_notification_delta(
            event_id="evt-delta-1",
            previous_snapshot={
                "event_id": "evt-delta-1",
                "source_urls": [
                    "https://news.example/a",
                    "https://sec.example/8k",
                ],
                "confidence_score": 0.51,
                "snapshot_at_utc": "2026-02-17T09:00:00+09:00",
            },
            latest_reasons=[
                {"source_url": "https://sec.example/8k", "confidence_score": 0.61},
                {"source_url": "https://reuters.example/b", "confidence_score": 0.57},
            ],
            now_utc="2026-02-17T12:00:00+09:00",
        )

        self.assertEqual(payload["added_sources"], ["https://reuters.example/b"])
        self.assertEqual(payload["removed_sources"], ["https://news.example/a"])
        self.assertEqual(payload["confidence_before"], 0.51)
        self.assertEqual(payload["confidence_after"], 0.61)
        self.assertEqual(payload["confidence_delta"], 0.1)
        self.assertTrue(payload["has_changes"])
        self.assertIsNone(payload["fallback_reason"])
        self.assertEqual(payload["previous_snapshot_at_utc"], "2026-02-17T00:00:00Z")
        self.assertEqual(payload["compared_at_utc"], "2026-02-17T03:00:00Z")

    def test_missing_previous_snapshot_uses_current_as_baseline(self) -> None:
        payload = compute_notification_delta(
            event_id="evt-delta-2",
            previous_snapshot=None,
            latest_reasons=[
                {"source_url": "https://news.example/1", "confidence_score": 0.32},
                {"source_url": "https://news.example/2", "confidence_score": 0.44},
            ],
            now_utc=datetime(2026, 2, 17, 3, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(
            payload["added_sources"],
            ["https://news.example/1", "https://news.example/2"],
        )
        self.assertEqual(payload["removed_sources"], [])
        self.assertEqual(payload["confidence_before"], 0.44)
        self.assertEqual(payload["confidence_after"], 0.44)
        self.assertEqual(payload["confidence_delta"], 0.0)
        self.assertEqual(payload["fallback_reason"], "missing_previous_snapshot")
        self.assertIn("초기 스냅샷", payload["summary_line"])

    def test_handles_additions_only_without_removed_sources(self) -> None:
        payload = compute_notification_delta(
            event_id="evt-delta-3",
            previous_snapshot={
                "event_id": "evt-delta-3",
                "source_urls": ["https://news.example/original"],
                "confidence_score": 0.4,
            },
            latest_reasons=[
                {"source_url": "https://news.example/original", "confidence_score": 0.4},
                {"source_url": "https://news.example/new", "confidence_score": 0.4},
            ],
        )

        self.assertEqual(payload["added_sources"], ["https://news.example/new"])
        self.assertEqual(payload["removed_sources"], [])
        self.assertTrue(payload["has_changes"])

    def test_zero_confidence_delta_applies_unchanged_fallback(self) -> None:
        payload = compute_notification_delta(
            event_id="evt-delta-4",
            previous_snapshot={
                "event_id": "evt-delta-4",
                "source_urls": ["https://news.example/a"],
                "confidence_score": 0.75,
            },
            latest_reasons=[
                {"source_url": "https://news.example/a", "confidence_score": 0.75},
            ],
        )

        self.assertEqual(payload["added_sources"], [])
        self.assertEqual(payload["removed_sources"], [])
        self.assertEqual(payload["confidence_delta"], 0.0)
        self.assertFalse(payload["has_changes"])
        self.assertEqual(payload["fallback_reason"], "confidence_unchanged")
        self.assertIn("이력만", payload["summary_line"])

    def test_snapshot_event_id_mismatch_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            compute_notification_delta(
                event_id="evt-delta-5",
                previous_snapshot={
                    "event_id": "evt-delta-X",
                    "source_urls": ["https://news.example/a"],
                    "confidence_score": 0.4,
                },
                latest_reasons=[{"source_url": "https://news.example/a", "confidence_score": 0.4}],
            )


if __name__ == "__main__":
    unittest.main()
