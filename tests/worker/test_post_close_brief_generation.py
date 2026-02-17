from __future__ import annotations

import unittest

from apps.worker.post_close_brief_generation import generate_post_close_brief


class PostCloseBriefGenerationTests(unittest.TestCase):
    def test_generates_post_close_summary_with_deduped_events(self) -> None:
        brief = generate_post_close_brief(
            user_id="user-brief-close-1",
            watchlist_items=[{"symbol": "AAPL", "market": "US"}],
            daily_events=[
                {
                    "event_id": "evt-close-1",
                    "symbol": "AAPL",
                    "market": "US",
                    "change_pct": 4.2,
                    "detected_at_utc": "2026-02-17T19:00:00Z",
                    "source_url": "https://sec.example/aapl-10q",
                },
                {
                    "event_id": "evt-close-1",
                    "symbol": "AAPL",
                    "market": "US",
                    "change_pct": 3.8,
                    "detected_at_utc": "2026-02-17T18:00:00Z",
                    "source_url": "https://sec.example/aapl-old",
                },
            ],
            reason_revisions=[
                {
                    "event_id": "evt-close-1",
                    "to_status": "resolved",
                    "revised_at_utc": "2026-02-17T20:00:00Z",
                },
                {
                    "event_id": "evt-close-1",
                    "to_status": "reviewed",
                    "revised_at_utc": "2026-02-17T19:30:00Z",
                },
            ],
            delta_notifications=[
                {
                    "event_id": "evt-close-1",
                    "reason_code": "confidence_changed",
                    "confidence_delta": 0.11,
                }
            ],
            now_utc="2026-02-18T01:30:00Z",
        )

        self.assertEqual(brief["brief_type"], "post_close")
        self.assertIsNone(brief["fallback_reason"])
        self.assertEqual(len(brief["items"]), 1)
        item = brief["items"][0]
        self.assertEqual(item["event_id"], "evt-close-1")
        self.assertEqual(item["revision_count"], 2)
        self.assertEqual(item["final_status"], "resolved")
        self.assertEqual(item["delta_reason_codes"], ["confidence_changed"])
        self.assertEqual(item["detected_at_utc"], "2026-02-17T19:00:00Z")
        self.assertTrue(item["detected_at_local"].startswith("2026-02-17T14:00:00"))

    def test_returns_no_events_when_input_data_is_empty(self) -> None:
        brief = generate_post_close_brief(
            user_id="user-brief-close-2",
            watchlist_items=[{"symbol": "AAPL", "market": "US"}],
            daily_events=[],
            reason_revisions=[],
            delta_notifications=[],
            now_utc="2026-02-18T01:30:00Z",
        )

        self.assertEqual(brief["items"], [])
        self.assertEqual(brief["fallback_reason"], "no_events")
        self.assertEqual(brief["warnings"], [])

    def test_returns_partial_aggregation_with_warnings_when_all_rows_are_invalid(self) -> None:
        brief = generate_post_close_brief(
            user_id="user-brief-close-3",
            watchlist_items=[{"symbol": "AAPL", "market": "US"}],
            daily_events=[
                {
                    "event_id": "",
                    "symbol": "AAPL",
                    "market": "US",
                    "detected_at_utc": "not-a-datetime",
                }
            ],
            reason_revisions=[
                {
                    "event_id": "",
                    "revised_at_utc": "invalid-date",
                }
            ],
            delta_notifications=[
                {
                    "event_id": "",
                    "confidence_delta": "oops",
                }
            ],
            now_utc="2026-02-18T01:30:00Z",
        )

        self.assertEqual(brief["items"], [])
        self.assertEqual(brief["fallback_reason"], "partial_aggregation")
        self.assertGreaterEqual(len(brief["warnings"]), 2)

    def test_preserves_utc_and_local_date_boundary_on_items(self) -> None:
        brief = generate_post_close_brief(
            user_id="user-brief-close-4",
            watchlist_items=[{"symbol": "AAPL", "market": "US"}],
            daily_events=[
                {
                    "event_id": "evt-close-boundary",
                    "symbol": "AAPL",
                    "market": "US",
                    "change_pct": -2.1,
                    "detected_at_utc": "2026-02-18T00:30:00Z",
                    "source_url": "https://news.example/aapl-close",
                }
            ],
            reason_revisions=[],
            delta_notifications=[],
            now_utc="2026-02-18T02:00:00Z",
        )

        self.assertIsNone(brief["fallback_reason"])
        self.assertEqual(len(brief["items"]), 1)
        item = brief["items"][0]
        self.assertEqual(item["detected_at_utc"], "2026-02-18T00:30:00Z")
        self.assertTrue(item["detected_at_local"].startswith("2026-02-17T19:30:00"))
        self.assertEqual(item["trade_date_local"], "2026-02-17")


if __name__ == "__main__":
    unittest.main()
