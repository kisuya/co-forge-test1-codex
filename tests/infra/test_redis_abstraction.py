from __future__ import annotations

import unittest

from apps.infra.redis_client import InMemoryRedisBackend, RedisClient, RedisConfig, RetryableRedisError


class _FailingBackend:
    def get(self, key: str) -> str | None:
        raise ConnectionError("redis unreachable")

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        raise TimeoutError("redis timeout")

    def ttl(self, key: str) -> int | None:
        raise OSError("redis network failure")

    def acquire_lock(self, key: str, *, ttl_seconds: int) -> bool:
        raise ConnectionError("redis lock failure")

    def release_lock(self, key: str) -> None:
        raise ConnectionError("redis release failure")


class RedisAbstractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = InMemoryRedisBackend()
        self.client = RedisClient(
            config=RedisConfig(redis_url="redis://localhost:6379/0", key_prefix="test-prefix"),
            backend=self.backend,
        )

    def test_get_set_ttl_and_lock_work_with_prefixed_keys(self) -> None:
        self.client.set("sample", "value-1", ttl_seconds=3)
        value = self.client.get("sample")
        ttl = self.client.ttl("sample")

        self.assertEqual(value, "value-1")
        self.assertIsNotNone(ttl)
        assert ttl is not None
        self.assertGreaterEqual(ttl, 0)
        self.assertLessEqual(ttl, 3)
        self.assertEqual(self.backend.get("test-prefix:sample"), "value-1")

        first_lock = self.client.lock("work", ttl_seconds=2)
        second_lock = self.client.lock("work", ttl_seconds=2)
        self.client.release_lock("work")
        third_lock = self.client.lock("work", ttl_seconds=2)

        self.assertTrue(first_lock)
        self.assertFalse(second_lock)
        self.assertTrue(third_lock)

    def test_debounce_and_cooldown_helpers_block_duplicates(self) -> None:
        first_debounce = self.client.should_debounce(
            symbol="AAPL",
            window_seconds=300,
            direction="up",
            ttl_seconds=2,
        )
        second_debounce = self.client.should_debounce(
            symbol="AAPL",
            window_seconds=300,
            direction="up",
            ttl_seconds=2,
        )

        first_cooldown = self.client.in_cooldown(
            user_id="user-1",
            event_id="evt-1",
            channel="email",
            ttl_seconds=2,
        )
        second_cooldown = self.client.in_cooldown(
            user_id="user-1",
            event_id="evt-1",
            channel="email",
            ttl_seconds=2,
        )

        self.assertFalse(first_debounce)
        self.assertTrue(second_debounce)
        self.assertFalse(first_cooldown)
        self.assertTrue(second_cooldown)

    def test_ttl_minimum_boundary_is_enforced(self) -> None:
        with self.assertRaises(ValueError):
            self.client.set("invalid", "value", ttl_seconds=0)

        with self.assertRaises(ValueError):
            self.client.lock("invalid", ttl_seconds=0)

        with self.assertRaises(ValueError):
            self.client.should_debounce(
                symbol="TSLA",
                window_seconds=60,
                direction="down",
                ttl_seconds=0,
            )

    def test_connection_failures_are_wrapped_as_retryable_errors(self) -> None:
        failing_client = RedisClient(
            config=RedisConfig(redis_url="redis://localhost:6379/0", key_prefix="x"),
            backend=_FailingBackend(),
        )

        with self.assertRaises(RetryableRedisError):
            failing_client.get("k1")

        with self.assertRaises(RetryableRedisError):
            failing_client.set("k1", "v1", ttl_seconds=3)

        with self.assertRaises(RetryableRedisError):
            failing_client.ttl("k1")

        with self.assertRaises(RetryableRedisError):
            failing_client.lock("k1", ttl_seconds=3)

        with self.assertRaises(RetryableRedisError):
            failing_client.release_lock("k1")


if __name__ == "__main__":
    unittest.main()
