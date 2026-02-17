from __future__ import annotations

import os
import unittest

from apps.worker.notification_delta_policy import (
    NotificationDeltaPolicyConfig,
    evaluate_notification_delta_policy,
)


class NotificationDeltaPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_confidence_delta_above_threshold_allows_realert(self) -> None:
        result = evaluate_notification_delta_policy(
            delta_payload={
                "added_sources": [],
                "removed_sources": [],
                "confidence_delta": 0.08,
            },
            cooldown_state=None,
            now_utc="2026-02-17T00:00:00Z",
            policy=NotificationDeltaPolicyConfig(
                min_confidence_delta=0.05,
                min_added_sources=2,
                min_removed_sources=2,
                cooldown_minutes=30,
            ),
        )

        self.assertTrue(result["should_send"])
        self.assertEqual(result["reason_code"], "confidence_changed")
        self.assertEqual(result["matched_reasons"], ["confidence_delta"])
        self.assertFalse(result["history_only"])

    def test_source_addition_threshold_allows_realert(self) -> None:
        result = evaluate_notification_delta_policy(
            delta_payload={
                "added_sources": ["https://news.example/a"],
                "removed_sources": [],
                "confidence_delta": 0.0,
            },
            cooldown_state=None,
            now_utc="2026-02-17T00:00:00Z",
            policy=NotificationDeltaPolicyConfig(
                min_confidence_delta=0.1,
                min_added_sources=1,
                min_removed_sources=1,
                cooldown_minutes=30,
            ),
        )

        self.assertTrue(result["should_send"])
        self.assertEqual(result["reason_code"], "source_added")
        self.assertIn("source_added", result["matched_reasons"])

    def test_cooldown_conflict_suppresses_realert(self) -> None:
        result = evaluate_notification_delta_policy(
            delta_payload={
                "added_sources": ["https://news.example/a"],
                "removed_sources": [],
                "confidence_delta": 0.2,
            },
            cooldown_state={
                "last_sent_at_utc": "2026-02-17T00:10:00Z",
            },
            now_utc="2026-02-17T00:20:00Z",
            policy=NotificationDeltaPolicyConfig(
                min_confidence_delta=0.05,
                min_added_sources=1,
                min_removed_sources=1,
                cooldown_minutes=30,
            ),
        )

        self.assertFalse(result["should_send"])
        self.assertEqual(result["reason_code"], "cooldown_active")
        self.assertTrue(result["history_only"])
        self.assertEqual(result["cooldown_until_utc"], "2026-02-17T00:40:00Z")

    def test_small_changes_below_threshold_are_suppressed(self) -> None:
        result = evaluate_notification_delta_policy(
            delta_payload={
                "added_sources": [],
                "removed_sources": [],
                "confidence_delta": 0.01,
            },
            cooldown_state=None,
            now_utc="2026-02-17T00:20:00Z",
            policy=NotificationDeltaPolicyConfig(
                min_confidence_delta=0.05,
                min_added_sources=1,
                min_removed_sources=1,
                cooldown_minutes=30,
            ),
        )

        self.assertFalse(result["should_send"])
        self.assertEqual(result["reason_code"], "delta_below_threshold")
        self.assertTrue(result["history_only"])

    def test_invalid_policy_configuration_from_env_is_suppressed(self) -> None:
        os.environ["NOTIFY_DELTA_CONFIDENCE_THRESHOLD"] = "invalid-number"

        result = evaluate_notification_delta_policy(
            delta_payload={
                "added_sources": ["https://news.example/a"],
                "removed_sources": [],
                "confidence_delta": 0.2,
            },
            cooldown_state=None,
            now_utc="2026-02-17T00:20:00Z",
            policy=None,
        )

        self.assertFalse(result["should_send"])
        self.assertEqual(result["reason_code"], "policy_missing")
        self.assertTrue(result["history_only"])


if __name__ == "__main__":
    unittest.main()
