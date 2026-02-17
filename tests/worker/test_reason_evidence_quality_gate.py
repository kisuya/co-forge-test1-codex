from __future__ import annotations

from datetime import datetime, timezone
import socket
import unittest

from apps.domain.reasons import event_reason_store
from apps.worker.reason_evidence_quality_gate import apply_reason_evidence_quality_gate
from apps.worker.reasons import rank_event_reasons


class _StubLinkChecker:
    def __init__(self, outcomes: dict[str, bool | Exception]) -> None:
        self._outcomes = outcomes

    def __call__(self, url: str) -> bool:
        outcome = self._outcomes.get(url, True)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ReasonEvidenceQualityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        event_reason_store.clear()
        self.detected_at = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_filters_with_scheme_domain_and_link_activity(self) -> None:
        checker = _StubLinkChecker(
            {
                "https://sec.example/8k": True,
                "https://news.example/stale": False,
            }
        )
        result = apply_reason_evidence_quality_gate(
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "valid",
                    "source_url": "https://sec.example/8k",
                    "published_at": "2026-02-16T11:58:00Z",
                },
                {
                    "reason_type": "news",
                    "summary": "bad scheme",
                    "source_url": "ftp://sec.example/raw",
                    "published_at": "2026-02-16T11:57:00Z",
                },
                {
                    "reason_type": "news",
                    "summary": "bad domain",
                    "source_url": "https://blocked.example/item",
                    "published_at": "2026-02-16T11:56:00Z",
                },
                {
                    "reason_type": "news",
                    "summary": "inactive",
                    "source_url": "https://news.example/stale",
                    "published_at": "2026-02-16T11:55:00Z",
                },
            ],
            allowed_domains={"sec.example", "news.example"},
            link_checker=checker,
        )

        self.assertEqual(len(result["accepted_candidates"]), 1)
        self.assertEqual(result["accepted_candidates"][0]["source_url"], "https://sec.example/8k")
        excluded_reasons = {item["reason"] for item in result["excluded_candidates"]}
        self.assertEqual(excluded_reasons, {"invalid_scheme", "domain_not_allowed", "inactive_link"})
        self.assertEqual(result["reason_status"], "verified")
        self.assertEqual(result["retryable_excluded_count"], 0)
        self.assertIsNone(result["retry_after_seconds"])

    def test_standardizes_timeout_429_and_unresolvable_as_retryable(self) -> None:
        checker = _StubLinkChecker(
            {
                "https://sec.example/timeout": TimeoutError("source timeout"),
                "https://news.example/limited": RuntimeError("429 too many requests"),
                "https://dart.example/missing": socket.gaierror(-2, "Name or service not known"),
            }
        )
        result = apply_reason_evidence_quality_gate(
            candidates=[
                {"source_url": "https://sec.example/timeout", "published_at": "2026-02-16T11:58:00Z"},
                {"source_url": "https://news.example/limited", "published_at": "2026-02-16T11:57:00Z"},
                {"source_url": "https://dart.example/missing", "published_at": "2026-02-16T11:56:00Z"},
            ],
            allowed_domains={"sec.example", "news.example", "dart.example"},
            link_checker=checker,
        )

        self.assertEqual(result["accepted_candidates"], [])
        self.assertEqual(result["reason_status"], "collecting_evidence")
        self.assertEqual(result["retryable_excluded_count"], 3)
        self.assertEqual(result["retry_after_seconds"], 300)
        excluded_reasons = {item["reason"] for item in result["excluded_candidates"]}
        self.assertEqual(excluded_reasons, {"link_check_timeout", "link_check_rate_limited", "link_unresolvable"})
        self.assertTrue(all(item["retryable"] for item in result["excluded_candidates"]))
        self.assertTrue(all(item["temporary_excluded"] for item in result["excluded_candidates"]))

    def test_ranker_returns_collecting_evidence_fallback_with_retry_hint(self) -> None:
        checker = _StubLinkChecker({"https://sec.example/8k": TimeoutError("source timeout")})

        reasons = rank_event_reasons(
            event_id="evt-quality-1",
            detected_at_utc=self.detected_at,
            candidates=[
                {
                    "reason_type": "filing",
                    "summary": "8-K",
                    "source_url": "https://sec.example/8k",
                    "published_at": "2026-02-16T11:58:00Z",
                }
            ],
            evidence_link_checker=checker,
        )

        self.assertEqual(len(reasons), 1)
        self.assertEqual(reasons[0]["reason_type"], "fallback")
        self.assertEqual(reasons[0]["summary"], "근거 수집 중")
        self.assertEqual(reasons[0]["reason_status"], "collecting_evidence")
        self.assertEqual(reasons[0]["retry_after_seconds"], 300)
        self.assertIsNone(reasons[0]["source_url"])


if __name__ == "__main__":
    unittest.main()
