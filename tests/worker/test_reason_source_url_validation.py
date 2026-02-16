from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from apps.domain.reasons import event_reason_store
from apps.worker.reasons import rank_event_reasons


class ReasonSourceUrlValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        event_reason_store.clear()
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_invalid_urls_are_excluded_from_ranked_candidates(self) -> None:
        reasons = rank_event_reasons(
            event_id="evt-url-1",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "bad scheme",
                    "source_url": "ftp://invalid.example/item",
                    "published_at": "2026-02-16T11:59:00Z",
                },
                {
                    "reason_type": "filing",
                    "summary": "valid source",
                    "source_url": "https://sec.example/8k",
                    "published_at": "2026-02-16T11:58:00Z",
                },
            ],
        )

        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0]["source_url"], "https://sec.example/8k")

    def test_fallback_message_is_returned_when_no_valid_source_urls(self) -> None:
        reasons = rank_event_reasons(
            event_id="evt-url-2",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "news",
                    "summary": "bad scheme",
                    "source_url": "javascript:alert(1)",
                    "published_at": "2026-02-16T11:59:00Z",
                },
                {
                    "reason_type": "filing",
                    "summary": "missing host",
                    "source_url": "https:///missing-host",
                    "published_at": "2026-02-16T11:58:00Z",
                },
            ],
        )

        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0]["reason_type"], "fallback")
        self.assertEqual(reasons[0]["summary"], "근거 수집 중")
        self.assertIsNone(reasons[0]["source_url"])

    def test_invalid_url_reason_is_logged(self) -> None:
        with patch("apps.worker.reasons.log_error") as mock_log_error:
            rank_event_reasons(
                event_id="evt-url-3",
                detected_at_utc=self.detected_at,
                candidates=[
                    {
                        "reason_type": "news",
                        "summary": "bad scheme",
                        "source_url": "file:///tmp/hack",
                        "published_at": "2026-02-16T11:59:00Z",
                    }
                ],
                request_id="req-url-validation",
            )

        self.assertTrue(mock_log_error.called)
        kwargs = mock_log_error.call_args.kwargs
        self.assertEqual(kwargs["feature"], "reason-004")
        self.assertEqual(kwargs["reason"], "invalid_scheme")


if __name__ == "__main__":
    unittest.main()
