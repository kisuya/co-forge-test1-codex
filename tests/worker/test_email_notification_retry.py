from __future__ import annotations

import unittest

from apps.infra.redis_client import InMemoryRedisBackend, RedisClient, RedisConfig
from apps.worker.email_notifications import (
    EmailDeliveryAdapter,
    EmailRetryConfig,
    email_dead_letter_queue,
    send_email_with_retry,
)


class _FlakyEmailAdapter(EmailDeliveryAdapter):
    def __init__(self, failures: list[Exception]) -> None:
        self._failures = failures
        self.calls = 0

    def send(self, *, user_id: str, event_id: str, message: str) -> None:
        del user_id, event_id, message
        self.calls += 1
        if self.calls <= len(self._failures):
            raise self._failures[self.calls - 1]


class EmailNotificationRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        email_dead_letter_queue.clear()
        self.redis = RedisClient(
            config=RedisConfig(redis_url="redis://localhost:6379/0", key_prefix="test-notify-003"),
            backend=InMemoryRedisBackend(),
        )

    def tearDown(self) -> None:
        email_dead_letter_queue.clear()

    def test_temporary_failures_transition_to_retrying_then_sent(self) -> None:
        adapter = _FlakyEmailAdapter([TimeoutError("timeout"), ConnectionError("temporary network error")])

        result = send_email_with_retry(
            user_id="u1",
            event_id="evt-1",
            message="hello",
            adapter=adapter,
            redis_client=self.redis,
            retry_config=EmailRetryConfig(max_attempts=4, base_delay_seconds=3),
        )

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(len(result["attempt_states"]), 2)
        self.assertEqual(result["attempt_states"][0]["status"], "retrying")
        self.assertEqual(result["attempt_states"][0]["next_delay_seconds"], 3)
        self.assertEqual(result["attempt_states"][1]["next_delay_seconds"], 6)
        self.assertEqual(len(email_dead_letter_queue.list_entries()), 0)

    def test_final_failure_moves_message_to_dead_letter_queue(self) -> None:
        adapter = _FlakyEmailAdapter(
            [TimeoutError("timeout"), TimeoutError("timeout"), TimeoutError("timeout")]
        )

        result = send_email_with_retry(
            user_id="u1",
            event_id="evt-2",
            message="hello",
            adapter=adapter,
            redis_client=self.redis,
            retry_config=EmailRetryConfig(max_attempts=3, base_delay_seconds=2),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["attempts"], 3)
        self.assertTrue(result["dead_letter_id"])
        entries = email_dead_letter_queue.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].id, result["dead_letter_id"])

    def test_cooldown_persistence_skips_duplicate_send(self) -> None:
        adapter = _FlakyEmailAdapter([])

        first = send_email_with_retry(
            user_id="u1",
            event_id="evt-3",
            message="hello",
            adapter=adapter,
            redis_client=self.redis,
            retry_config=EmailRetryConfig(max_attempts=2, base_delay_seconds=1),
            cooldown_ttl_seconds=120,
        )
        second = send_email_with_retry(
            user_id="u1",
            event_id="evt-3",
            message="hello again",
            adapter=adapter,
            redis_client=self.redis,
            retry_config=EmailRetryConfig(max_attempts=2, base_delay_seconds=1),
            cooldown_ttl_seconds=120,
        )

        self.assertEqual(first["status"], "sent")
        self.assertEqual(second["status"], "cooldown")
        self.assertEqual(second["attempts"], 0)
        self.assertEqual(adapter.calls, 1)

    def test_non_retryable_failure_fails_immediately(self) -> None:
        adapter = _FlakyEmailAdapter([RuntimeError("invalid recipient address")])

        result = send_email_with_retry(
            user_id="u1",
            event_id="evt-4",
            message="hello",
            adapter=adapter,
            redis_client=self.redis,
            retry_config=EmailRetryConfig(max_attempts=5, base_delay_seconds=2),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["attempt_states"], [])


if __name__ == "__main__":
    unittest.main()
