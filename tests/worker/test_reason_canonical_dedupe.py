from __future__ import annotations

from datetime import datetime, timezone
import unittest

from apps.domain.reasons import event_reason_store
from apps.worker.reason_canonical_dedupe import canonicalize_and_dedupe_reason_candidates
from apps.worker.reasons import rank_event_reasons


class ReasonCanonicalDedupeTests(unittest.TestCase):
    def setUp(self) -> None:
        event_reason_store.clear()
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_merges_candidates_with_same_canonical_url_title_and_near_published_at(self) -> None:
        first_source = "https://news.example/story/acme/?utm_source=x&a=1&b=2#section"
        second_source = "https://news.example/story/acme?a=1&b=2&utm_medium=social"

        deduped = canonicalize_and_dedupe_reason_candidates(
            candidates=[
                {
                    "reason_type": "news",
                    "title": "  ACME beats earnings  ",
                    "summary": "ACME beats earnings",
                    "source_url": first_source,
                    "published_at": "2026-02-16T11:58:00Z",
                },
                {
                    "reason_type": "news",
                    "title": "acme beats earnings",
                    "summary": "same story",
                    "source_url": second_source,
                    "published_at": "2026-02-16T11:55:30Z",
                },
            ]
        )

        self.assertEqual(len(deduped), 1)
        candidate = deduped[0]
        self.assertEqual(candidate["source_url"], "https://news.example/story/acme?a=1&b=2")
        self.assertEqual(candidate["canonical_source_url"], "https://news.example/story/acme?a=1&b=2")
        self.assertEqual(candidate["source_variants"], [first_source, second_source])
        self.assertEqual(candidate["published_at"], "2026-02-16T11:55:30Z")

    def test_does_not_merge_when_title_is_missing(self) -> None:
        deduped = canonicalize_and_dedupe_reason_candidates(
            candidates=[
                {
                    "reason_type": "news",
                    "source_url": "https://news.example/story/acme?a=1",
                    "published_at": "2026-02-16T11:58:00Z",
                },
                {
                    "reason_type": "news",
                    "title": "ACME beats earnings",
                    "source_url": "https://news.example/story/acme?a=1&utm_source=x",
                    "published_at": "2026-02-16T11:58:20Z",
                },
            ]
        )

        self.assertEqual(len(deduped), 2)

    def test_does_not_merge_when_published_at_gap_exceeds_tolerance(self) -> None:
        deduped = canonicalize_and_dedupe_reason_candidates(
            candidates=[
                {
                    "reason_type": "news",
                    "title": "ACME beats earnings",
                    "source_url": "https://news.example/story/acme",
                    "published_at": "2026-02-16T11:58:00Z",
                },
                {
                    "reason_type": "news",
                    "title": "ACME beats earnings",
                    "source_url": "https://news.example/story/acme/",
                    "published_at": "2026-02-16T11:47:59Z",
                },
            ]
        )

        self.assertEqual(len(deduped), 2)

    def test_does_not_merge_when_canonicalization_fails(self) -> None:
        bad_source = "https://news.example:bad-port/story?a=1"

        deduped = canonicalize_and_dedupe_reason_candidates(
            candidates=[
                {
                    "reason_type": "news",
                    "title": "ACME beats earnings",
                    "source_url": bad_source,
                    "published_at": "2026-02-16T11:58:00Z",
                },
                {
                    "reason_type": "news",
                    "title": "ACME beats earnings",
                    "source_url": bad_source,
                    "published_at": "2026-02-16T11:58:10Z",
                },
            ]
        )

        self.assertEqual(len(deduped), 2)

    def test_does_not_merge_different_hosts_even_with_same_title_and_time(self) -> None:
        deduped = canonicalize_and_dedupe_reason_candidates(
            candidates=[
                {
                    "reason_type": "news",
                    "title": "ACME beats earnings",
                    "source_url": "https://news.example/story/acme",
                    "published_at": "2026-02-16T11:58:00Z",
                },
                {
                    "reason_type": "filing",
                    "title": "ACME beats earnings",
                    "source_url": "https://sec.example/story/acme",
                    "published_at": "2026-02-16T11:58:00Z",
                },
            ]
        )

        self.assertEqual(len(deduped), 2)

    def test_ranker_uses_deduped_candidates_before_scoring(self) -> None:
        reasons = rank_event_reasons(
            event_id="evt-dedupe-1",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "news",
                    "title": "ACME beats earnings",
                    "summary": "ACME beats earnings",
                    "source_url": "https://news.example/story/acme?utm_source=newsletter&a=1&b=2",
                    "published_at": "2026-02-16T11:57:00Z",
                    "source_reliability": 0.8,
                    "topic_match_score": 0.8,
                },
                {
                    "reason_type": "news",
                    "title": "acme beats earnings",
                    "summary": "duplicate",
                    "source_url": "https://news.example/story/acme?a=1&b=2&utm_medium=social",
                    "published_at": "2026-02-16T11:56:30Z",
                    "source_reliability": 0.75,
                    "topic_match_score": 0.75,
                },
                {
                    "reason_type": "filing",
                    "title": "8-K filing",
                    "summary": "8-K filing",
                    "source_url": "https://sec.example/8k/acme",
                    "published_at": "2026-02-16T11:55:00Z",
                    "source_reliability": 0.95,
                    "topic_match_score": 0.9,
                },
            ],
        )

        self.assertEqual(len(reasons), 2)
        source_urls = {reason["source_url"] for reason in reasons}
        self.assertIn("https://news.example/story/acme?a=1&b=2", source_urls)
        self.assertIn("https://sec.example/8k/acme", source_urls)


if __name__ == "__main__":
    unittest.main()
