from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from apps.domain.notifications import notification_store
from apps.worker.notifications import dispatch_event_notifications


class NotificationDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        notification_store.clear()
        self.event = {
            "id": "evt-ntf-1",
            "symbol": "AAPL",
            "market": "US",
            "change_pct": 4.2,
            "window_minutes": 5,
        }
        self.reasons = [
            {
                "reason_type": "filing",
                "source_url": "https://sec.example/filing",
            }
        ]
        self.now = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)

    def test_dispatches_in_app_and_email(self) -> None:
        dispatched = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="u1",
            now_utc=self.now,
        )

        self.assertEqual(len(dispatched), 2)
        self.assertEqual({item["channel"] for item in dispatched}, {"in_app", "email"})
        self.assertTrue(all(item["sent_at_utc"].endswith("Z") for item in dispatched))

    def test_cooldown_blocks_repeated_notifications_within_30_minutes(self) -> None:
        first = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="u1",
            now_utc=self.now,
        )
        second = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="u1",
            now_utc=self.now + timedelta(minutes=20),
        )

        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(notification_store.list_notifications()), 2)

    def test_notifications_resume_after_cooldown(self) -> None:
        dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="u1",
            now_utc=self.now,
        )
        dispatched = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="u1",
            now_utc=self.now + timedelta(minutes=31),
        )

        self.assertEqual(len(dispatched), 2)
        self.assertEqual(len(notification_store.list_notifications()), 4)

    def test_message_is_fact_based_and_contains_source_url(self) -> None:
        dispatched = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="u1",
            now_utc=self.now,
        )
        message = dispatched[0]["message"].lower()

        self.assertIn("source: https://sec.example/filing", message)
        self.assertNotIn("buy", message)
        self.assertNotIn("sell", message)


if __name__ == "__main__":
    unittest.main()
