from __future__ import annotations

import unittest

from apps.domain.evidence_compare import build_evidence_compare_payload


class ConflictingEvidenceClassifierTests(unittest.TestCase):
    def test_builds_positive_negative_uncertain_axes_with_source_and_time(self) -> None:
        payload = build_evidence_compare_payload(
            event_id="evt-compare-1",
            evidences=[
                {
                    "id": "r-pos",
                    "reason_type": "news",
                    "summary": "Earnings beat expectations and guidance raised",
                    "source_url": "https://news.example/positive",
                    "published_at": "2026-02-18T08:20:00+09:00",
                    "confidence_score": 0.81,
                },
                {
                    "id": "r-neg",
                    "reason_type": "news",
                    "summary": "Regulator opens investigation into accounting",
                    "source_url": "https://news.example/negative",
                    "published_at": "2026-02-18T08:19:00+09:00",
                    "confidence_score": 0.72,
                },
                {
                    "id": "r-uncertain",
                    "reason_type": "news",
                    "summary": "Mixed analyst commentary after earnings call",
                    "source_url": "https://news.example/uncertain",
                    "published_at": "2026-02-18T08:18:00+09:00",
                    "confidence_score": 0.5,
                },
            ],
            generated_at_utc="2026-02-18T08:30:00+09:00",
        )

        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["compare_ready"])
        self.assertIsNone(payload["fallback_reason"])
        self.assertEqual(payload["axis_counts"]["positive"], 1)
        self.assertEqual(payload["axis_counts"]["negative"], 1)
        self.assertEqual(payload["axis_counts"]["uncertain"], 1)
        self.assertGreaterEqual(payload["comparable_axis_count"], 2)
        self.assertEqual(payload["generated_at_utc"], "2026-02-17T23:30:00Z")
        self.assertIn("단일 결론", payload["bias_warning"])

        for axis in ("positive", "negative", "uncertain"):
            for item in payload["axes"][axis]:
                self.assertTrue(item["source_url"])
                self.assertTrue(item["published_at"])

    def test_falls_back_when_evidence_is_insufficient(self) -> None:
        payload = build_evidence_compare_payload(
            event_id="evt-compare-2",
            evidences=[
                {
                    "summary": "Earnings beat expectations",
                    "source_url": "https://news.example/only-one",
                    "published_at": "2026-02-18T00:00:00Z",
                }
            ],
        )

        self.assertEqual(payload["status"], "compare_unavailable")
        self.assertFalse(payload["compare_ready"])
        self.assertEqual(payload["fallback_reason"], "insufficient_evidence")
        self.assertEqual(payload["axes"]["positive"], [])
        self.assertEqual(payload["axes"]["negative"], [])
        self.assertEqual(len(payload["axes"]["uncertain"]), 1)

    def test_falls_back_to_uncertain_when_axes_are_imbalanced(self) -> None:
        payload = build_evidence_compare_payload(
            event_id="evt-compare-3",
            evidences=[
                {
                    "summary": "Record sales beat estimate",
                    "source_url": "https://news.example/p1",
                    "published_at": "2026-02-18T00:00:00Z",
                },
                {
                    "summary": "Strong demand and guidance raised",
                    "source_url": "https://news.example/p2",
                    "published_at": "2026-02-18T00:01:00Z",
                },
            ],
        )

        self.assertEqual(payload["status"], "compare_unavailable")
        self.assertEqual(payload["fallback_reason"], "axis_imbalance")
        self.assertEqual(payload["axes"]["positive"], [])
        self.assertEqual(payload["axes"]["negative"], [])
        self.assertEqual(len(payload["axes"]["uncertain"]), 2)

    def test_falls_back_to_uncertain_when_all_evidence_is_ambiguous(self) -> None:
        payload = build_evidence_compare_payload(
            event_id="evt-compare-4",
            evidences=[
                {
                    "summary": "Management shared additional color during conference call",
                    "source_url": "https://news.example/a1",
                    "published_at": "2026-02-18T00:00:00Z",
                },
                {
                    "summary": "Analysts discussed multiple scenarios without conclusion",
                    "source_url": "https://news.example/a2",
                    "published_at": "2026-02-18T00:01:00Z",
                },
            ],
        )

        self.assertEqual(payload["status"], "compare_unavailable")
        self.assertEqual(payload["fallback_reason"], "ambiguous_classification")
        self.assertEqual(payload["axes"]["positive"], [])
        self.assertEqual(payload["axes"]["negative"], [])
        self.assertEqual(len(payload["axes"]["uncertain"]), 2)

    def test_drops_evidence_missing_source_or_published_at(self) -> None:
        payload = build_evidence_compare_payload(
            event_id="evt-compare-5",
            evidences=[
                {
                    "summary": "Beat estimate",
                    "source_url": "",
                    "published_at": "2026-02-18T00:00:00Z",
                },
                {
                    "summary": "Guidance cut",
                    "source_url": "https://news.example/invalid-time",
                    "published_at": "invalid",
                },
                {
                    "summary": "Earnings beat estimates",
                    "source_url": "https://news.example/p",
                    "published_at": "2026-02-18T00:02:00Z",
                },
                {
                    "summary": "Guidance cut after weak demand",
                    "source_url": "https://news.example/n",
                    "published_at": "2026-02-18T00:01:00Z",
                },
            ],
        )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["dropped_missing_metadata_count"], 2)
        self.assertEqual(payload["axis_counts"]["positive"], 1)
        self.assertEqual(payload["axis_counts"]["negative"], 1)
        self.assertEqual(payload["axis_counts"]["uncertain"], 0)


if __name__ == "__main__":
    unittest.main()
