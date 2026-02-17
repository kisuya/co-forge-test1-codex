from __future__ import annotations

from unittest.mock import patch
import unittest

from apps.worker.pre_market_brief_generation import generate_pre_market_brief


class PreMarketBriefGenerationTests(unittest.TestCase):
    def test_generates_prioritized_pre_market_items_with_links(self) -> None:
        brief = generate_pre_market_brief(
            user_id="user-brief-1",
            watchlist_items=[
                {"symbol": "AAPL", "market": "US"},
                {"symbol": "005930", "market": "KR"},
            ],
            scheduled_events=[
                {
                    "event_id": "evt-us-1",
                    "symbol": "AAPL",
                    "market": "US",
                    "event_type": "earnings",
                    "title": "AAPL Earnings Call",
                    "scheduled_at_utc": "2026-02-17T15:00:00Z",
                    "event_detail_url": "/events/evt-us-1",
                },
                {
                    "event_id": "evt-kr-1",
                    "symbol": "005930",
                    "market": "KR",
                    "event_type": "filing",
                    "title": "KR Filing",
                    "scheduled_at_utc": "2026-02-18T00:30:00Z",
                    "event_detail_url": "/events/evt-kr-1",
                    "source_url": "https://dart.example/filing",
                },
            ],
            recent_reason_cards=[
                {
                    "event_id": "evt-us-1",
                    "symbol": "AAPL",
                    "market": "US",
                    "summary": "실적 가이던스 조정 이슈로 개장 전 변동 가능성이 있습니다.",
                    "source_url": "https://sec.example/aapl-guidance",
                    "confidence_score": 0.82,
                    "published_at": "2026-02-17T13:10:00Z",
                },
                {
                    "event_id": "evt-kr-1",
                    "symbol": "005930",
                    "market": "KR",
                    "summary": "KR reference",
                    "source_url": "",
                    "confidence_score": 0.74,
                    "published_at": "2026-02-17T13:10:00Z",
                },
            ],
            now_utc="2026-02-17T13:40:00Z",
        )

        self.assertEqual(brief["brief_type"], "pre_market")
        self.assertIsNone(brief["fallback_reason"])
        self.assertEqual(brief["markets"], ["US"])
        self.assertEqual(len(brief["items"]), 1)
        item = brief["items"][0]
        self.assertEqual(item["symbol"], "AAPL")
        self.assertEqual(item["market"], "US")
        self.assertEqual(item["event_detail_url"], "/events/evt-us-1")
        self.assertEqual(item["source_url"], "https://sec.example/aapl-guidance")
        self.assertEqual(item["trade_date_local"], "2026-02-17")
        self.assertGreater(item["priority_score"], 0.0)
        self.assertEqual(len(item["checklist"]), 3)

    def test_returns_empty_brief_when_watchlist_is_missing(self) -> None:
        brief = generate_pre_market_brief(
            user_id="user-brief-2",
            watchlist_items=[],
            scheduled_events=[],
            recent_reason_cards=[],
            now_utc="2026-02-17T13:40:00Z",
        )

        self.assertEqual(brief["items"], [])
        self.assertEqual(brief["fallback_reason"], "insufficient_data")

    def test_returns_market_holiday_fallback_for_closed_market_day(self) -> None:
        brief = generate_pre_market_brief(
            user_id="user-brief-3",
            watchlist_items=[{"symbol": "AAPL", "market": "US"}],
            scheduled_events=[
                {
                    "event_id": "evt-us-holiday",
                    "symbol": "AAPL",
                    "market": "US",
                    "scheduled_at_utc": "2026-01-01T15:00:00Z",
                    "event_detail_url": "/events/evt-us-holiday",
                    "source_url": "https://sec.example/aapl-holiday",
                }
            ],
            recent_reason_cards=[],
            now_utc="2026-01-01T12:00:00Z",
        )

        self.assertEqual(brief["items"], [])
        self.assertEqual(brief["fallback_reason"], "market_holiday")

    def test_returns_timezone_error_when_market_clock_resolution_fails(self) -> None:
        with patch(
            "apps.worker.pre_market_brief_generation.resolve_market_clock",
            side_effect=ValueError("timezone unavailable"),
        ):
            brief = generate_pre_market_brief(
                user_id="user-brief-4",
                watchlist_items=[{"symbol": "AAPL", "market": "US"}],
                scheduled_events=[],
                recent_reason_cards=[],
                now_utc="2026-02-17T13:40:00Z",
            )

        self.assertEqual(brief["items"], [])
        self.assertEqual(brief["fallback_reason"], "timezone_error")


if __name__ == "__main__":
    unittest.main()
