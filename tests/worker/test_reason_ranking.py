from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.domain.reasons import event_reason_store
from apps.worker.reasons import rank_event_reasons


class ReasonRankingTests(unittest.TestCase):
    def setUp(self) -> None:
        event_reason_store.clear()
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_returns_ranked_reasons_up_to_three(self) -> None:
        reasons = rank_event_reasons(
            event_id="evt-1",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "10-Q update",
                    "source_url": "https://sec.example/10q",
                    "published_at": "2026-02-16T11:50:00Z",
                    "source_reliability": 0.95,
                    "topic_match_score": 0.9,
                },
                {
                    "reason_type": "news",
                    "summary": "CEO interview",
                    "source_url": "https://news.example/ceo",
                    "published_at": "2026-02-16T11:40:00Z",
                    "source_reliability": 0.8,
                    "topic_match_score": 0.7,
                },
                {
                    "reason_type": "macro",
                    "summary": "CPI release",
                    "source_url": "https://news.example/cpi",
                    "published_at": "2026-02-16T11:30:00Z",
                    "source_reliability": 0.7,
                    "topic_match_score": 0.65,
                },
                {
                    "reason_type": "community",
                    "summary": "forum rumor",
                    "source_url": "https://community.example/post",
                    "published_at": "2026-02-16T11:20:00Z",
                    "source_reliability": 0.3,
                    "topic_match_score": 0.2,
                },
            ],
        )

        self.assertEqual(len(reasons), 3)
        self.assertEqual([reason["rank"] for reason in reasons], [1, 2, 3])
        self.assertGreaterEqual(reasons[0]["confidence_score"], reasons[1]["confidence_score"])
        self.assertGreaterEqual(reasons[1]["confidence_score"], reasons[2]["confidence_score"])
        self.assertTrue(all(reason["source_url"] for reason in reasons))

    def test_excludes_candidates_without_source_url(self) -> None:
        reasons = rank_event_reasons(
            event_id="evt-2",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "missing source",
                    "source_url": "",
                    "published_at": "2026-02-16T11:40:00Z",
                },
                {
                    "reason_type": "filing",
                    "summary": "has source",
                    "source_url": "https://dart.example/disclosure",
                    "published_at": "2026-02-16T11:55:00Z",
                },
            ],
        )

        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0]["reason_type"], "filing")
        self.assertEqual(reasons[0]["rank"], 1)

    def test_saved_reasons_include_required_fields(self) -> None:
        rank_event_reasons(
            event_id="evt-3",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "headline",
                    "source_url": "https://news.example/a",
                    "published_at": "2026-02-16T11:45:00Z",
                }
            ],
        )
        saved = event_reason_store.list_by_event("evt-3")

        self.assertEqual(len(saved), 1)
        reason = saved[0].to_dict()
        self.assertIn("reason_type", reason)
        self.assertIn("confidence_score", reason)
        self.assertIn("source_url", reason)
        self.assertIn("published_at", reason)


if __name__ == "__main__":
    unittest.main()
