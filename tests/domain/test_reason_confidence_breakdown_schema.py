from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.domain.reasons import event_reason_store
from apps.worker.reasons import rank_event_reasons


def _build_valid_explanation() -> dict[str, object]:
    return {
        "weights": {
            "source_reliability": 0.45,
            "event_match": 0.35,
            "time_proximity": 0.20,
        },
        "signals": {
            "source_reliability": 0.9,
            "event_match": 0.8,
            "time_proximity": 0.7,
        },
        "score_breakdown": {
            "source_reliability": 0.405,
            "event_match": 0.28,
            "time_proximity": 0.14,
            "total": 0.825,
        },
        "explanation_text": "근거 신뢰도와 이벤트 일치도를 반영한 확률형 confidence 점수입니다.",
    }


class ReasonConfidenceBreakdownSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        event_reason_store.clear()
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_valid_breakdown_schema_is_saved(self) -> None:
        reason = event_reason_store.build_reason(
            event_id="evt-breakdown-1",
            rank=1,
            reason_type="news",
            confidence_score=0.825,
            summary="valid breakdown",
            source_url="https://news.example/acme",
            published_at="2026-02-16T11:50:00Z",
            explanation=_build_valid_explanation(),
        )

        payload = reason.to_dict()
        self.assertIn("explanation_text", payload["explanation"])
        self.assertIn("event_match", payload["explanation"]["weights"])
        self.assertIn("event_match", payload["explanation"]["signals"])
        self.assertIn("event_match", payload["explanation"]["score_breakdown"])

    def test_missing_breakdown_field_fails_validation(self) -> None:
        explanation = _build_valid_explanation()
        del explanation["signals"]["event_match"]

        with self.assertRaises(ValueError):
            event_reason_store.build_reason(
                event_id="evt-breakdown-2",
                rank=1,
                reason_type="news",
                confidence_score=0.825,
                summary="missing event_match signal",
                source_url="https://news.example/acme",
                published_at="2026-02-16T11:50:00Z",
                explanation=explanation,
            )

    def test_negative_breakdown_value_fails_validation(self) -> None:
        explanation = _build_valid_explanation()
        explanation["signals"]["time_proximity"] = -0.1

        with self.assertRaises(ValueError):
            event_reason_store.build_reason(
                event_id="evt-breakdown-3",
                rank=1,
                reason_type="news",
                confidence_score=0.825,
                summary="negative signal",
                source_url="https://news.example/acme",
                published_at="2026-02-16T11:50:00Z",
                explanation=explanation,
            )

    def test_sum_mismatch_fails_validation(self) -> None:
        explanation = _build_valid_explanation()
        explanation["score_breakdown"]["total"] = 0.7

        with self.assertRaises(ValueError):
            event_reason_store.build_reason(
                event_id="evt-breakdown-4",
                rank=1,
                reason_type="news",
                confidence_score=0.825,
                summary="sum mismatch",
                source_url="https://news.example/acme",
                published_at="2026-02-16T11:50:00Z",
                explanation=explanation,
            )

    def test_ranker_generates_required_breakdown_schema(self) -> None:
        reasons = rank_event_reasons(
            event_id="evt-breakdown-5",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "8-K filing",
                    "source_url": "https://sec.example/8k/acme",
                    "published_at": "2026-02-16T11:59:00Z",
                    "source_reliability": 0.9,
                    "topic_match_score": 0.8,
                }
            ],
        )

        self.assertEqual(len(reasons), 1)
        explanation = reasons[0]["explanation"]
        self.assertIn("event_match", explanation["weights"])
        self.assertIn("event_match", explanation["signals"])
        self.assertIn("event_match", explanation["score_breakdown"])
        self.assertIn("explanation_text", explanation)
        self.assertAlmostEqual(explanation["score_breakdown"]["total"], reasons[0]["confidence_score"], places=3)


if __name__ == "__main__":
    unittest.main()
