from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.domain.reasons import event_reason_store
from apps.worker.reasons import rank_event_reasons


class ReasonExplainabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        event_reason_store.clear()
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_ranked_reason_includes_explanation_fields(self) -> None:
        reasons = rank_event_reasons(
            event_id="evt-exp-1",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "8-K filed",
                    "source_url": "https://sec.example/8k",
                    "published_at": "2026-02-16T11:50:00Z",
                    "source_reliability": 0.9,
                    "topic_match_score": 0.8,
                }
            ],
        )

        self.assertEqual(len(reasons), 1)
        explanation = reasons[0]["explanation"]
        self.assertIn("weights", explanation)
        self.assertIn("signals", explanation)
        self.assertIn("score_breakdown", explanation)
        self.assertIn("total", explanation["score_breakdown"])

    def test_explanation_is_stored_and_retrievable(self) -> None:
        rank_event_reasons(
            event_id="evt-exp-2",
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
        stored = event_reason_store.list_by_event("evt-exp-2")

        self.assertEqual(len(stored), 1)
        payload = stored[0].to_dict()
        self.assertIn("explanation", payload)
        self.assertIn("total", payload["explanation"]["score_breakdown"])

    def test_missing_explanation_section_fails_schema_validation(self) -> None:
        with self.assertRaises(ValueError):
            event_reason_store.build_reason(
                event_id="evt-exp-3",
                rank=1,
                reason_type="news",
                confidence_score=0.5,
                summary="missing explanation fields",
                source_url="https://news.example/x",
                published_at="2026-02-16T11:45:00Z",
                explanation={"weights": {}},
            )


if __name__ == "__main__":
    unittest.main()
