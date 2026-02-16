from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from apps.domain.events import price_event_store
from apps.worker.detection import detect_price_event


class PriceEventDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        price_event_store.clear()
        self.now = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_creates_event_when_threshold_exceeded(self) -> None:
        event = detect_price_event(
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=103.2,
            window_minutes=5,
            detected_at_utc=self.now,
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["market"], "US")
        self.assertEqual(event["window_minutes"], 5)
        self.assertGreaterEqual(abs(event["change_pct"]), 3.0)

    def test_returns_none_when_threshold_not_met(self) -> None:
        event = detect_price_event(
            symbol="005930",
            market="KR",
            baseline_price=1000.0,
            current_price=1019.0,
            window_minutes=5,
            detected_at_utc=self.now,
        )
        self.assertIsNone(event)
        self.assertEqual(len(price_event_store.list_events()), 0)

    def test_debounce_blocks_duplicate_event_in_same_window(self) -> None:
        first = detect_price_event(
            symbol="TSLA",
            market="US",
            baseline_price=100.0,
            current_price=95.0,
            window_minutes=5,
            detected_at_utc=self.now,
        )
        second = detect_price_event(
            symbol="TSLA",
            market="US",
            baseline_price=100.0,
            current_price=94.0,
            window_minutes=5,
            detected_at_utc=self.now + timedelta(minutes=2),
        )
        third = detect_price_event(
            symbol="TSLA",
            market="US",
            baseline_price=100.0,
            current_price=93.0,
            window_minutes=5,
            detected_at_utc=self.now + timedelta(minutes=6),
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertIsNotNone(third)
        self.assertEqual(len(price_event_store.list_events()), 2)

    def test_saves_utc_timestamp_and_exchange_timezone(self) -> None:
        event = detect_price_event(
            symbol="005930",
            market="KR",
            baseline_price=100.0,
            current_price=95.0,
            window_minutes=1440,
            detected_at_utc="2026-02-16T03:00:00+09:00",
            session_label="regular",
        )

        assert event is not None
        self.assertEqual(event["detected_at_utc"], "2026-02-15T18:00:00Z")
        self.assertEqual(event["exchange_timezone"], "Asia/Seoul")
        self.assertEqual(event["session_label"], "regular")


if __name__ == "__main__":
    unittest.main()
