from __future__ import annotations

import unittest

from apps.worker.reason_source_adapters import (
    DartSourceAdapter,
    NewsSourceAdapter,
    RetryableReasonSourceError,
    SecSourceAdapter,
    collect_reason_candidates,
)


class _FailingAdapter:
    def __init__(self, source_name: str, exc: Exception) -> None:
        self.source_name = source_name
        self._exc = exc

    def fetch_by_symbol(self, *, symbol: str, time_window: tuple[str, str]) -> list[dict[str, object]]:
        del symbol, time_window
        raise self._exc


class ReasonSourceAdapterTests(unittest.TestCase):
    def test_collects_candidates_from_all_sources(self) -> None:
        sec = SecSourceAdapter(
            {
                "AAPL": [
                    {"reason_type": "filing", "summary": "8-K filed", "source_url": "https://sec.example/8k"}
                ]
            }
        )
        dart = DartSourceAdapter(
            {
                "AAPL": [
                    {
                        "reason_type": "disclosure",
                        "summary": "DART filing",
                        "source_url": "https://dart.example/notice",
                    }
                ]
            }
        )
        news = NewsSourceAdapter(
            {
                "AAPL": [
                    {"reason_type": "news", "summary": "Breaking news", "source_url": "https://news.example/aapl"}
                ]
            }
        )

        collected = collect_reason_candidates(
            symbol="aapl",
            time_window=("2026-02-16T11:00:00Z", "2026-02-16T12:00:00Z"),
            adapters=[sec, dart, news],
        )

        self.assertEqual(len(collected["candidates"]), 3)
        self.assertEqual(collected["errors"], [])
        sources = {item["source"] for item in collected["candidates"]}
        self.assertEqual(sources, {"sec", "dart", "news"})

    def test_partial_failures_keep_successful_results(self) -> None:
        sec = SecSourceAdapter(
            {"AAPL": [{"reason_type": "filing", "summary": "10-Q", "source_url": "https://sec.example/10q"}]}
        )
        failing_news = _FailingAdapter("news", RuntimeError("temporary upstream issue"))

        collected = collect_reason_candidates(
            symbol="AAPL",
            time_window=("2026-02-16T11:00:00Z", "2026-02-16T12:00:00Z"),
            adapters=[sec, failing_news],
        )

        self.assertEqual(len(collected["candidates"]), 1)
        self.assertEqual(collected["candidates"][0]["source"], "sec")
        self.assertEqual(len(collected["errors"]), 1)
        self.assertEqual(collected["errors"][0]["source"], "news")
        self.assertFalse(collected["errors"][0]["retryable"])

    def test_timeout_and_429_are_standardized_as_retryable(self) -> None:
        timeout_adapter = _FailingAdapter("sec", TimeoutError("source timeout"))
        rate_limit_adapter = _FailingAdapter("dart", RuntimeError("429 too many requests"))
        explicit_retryable = _FailingAdapter(
            "news",
            RetryableReasonSourceError("news", "adapter-level retryable error"),
        )

        collected = collect_reason_candidates(
            symbol="AAPL",
            time_window=("2026-02-16T11:00:00Z", "2026-02-16T12:00:00Z"),
            adapters=[timeout_adapter, rate_limit_adapter, explicit_retryable],
        )

        self.assertEqual(collected["candidates"], [])
        self.assertEqual(len(collected["errors"]), 3)
        self.assertTrue(all(error["retryable"] for error in collected["errors"]))


if __name__ == "__main__":
    unittest.main()
