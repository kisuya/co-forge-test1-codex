from __future__ import annotations

import os
import tempfile
import unittest

from apps.infra.models import create_core_schema, drop_core_schema, execute_statement, fetch_all
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.infra.redis_client import RedisClient, RedisConfig
from apps.worker.detection_persistence import (
    detect_price_event_to_db,
    detection_retry_queue,
    reset_detection_redis_client,
    set_detection_redis_client,
)


class _ManualClockRedisBackend:
    def __init__(self) -> None:
        self.now = 0
        self._store: dict[str, tuple[str, int]] = {}

    def advance(self, seconds: int) -> None:
        self.now += seconds

    def get(self, key: str) -> str | None:
        record = self._store.get(key)
        if record is None:
            return None
        value, expires_at = record
        if expires_at <= self.now:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self._store[key] = (value, self.now + ttl_seconds)

    def ttl(self, key: str) -> int | None:
        record = self._store.get(key)
        if record is None:
            return None
        _, expires_at = record
        remaining = expires_at - self.now
        if remaining <= 0:
            self._store.pop(key, None)
            return None
        return remaining

    def acquire_lock(self, key: str, *, ttl_seconds: int) -> bool:
        del key, ttl_seconds
        return True

    def release_lock(self, key: str) -> None:
        del key


class DetectionRedisDebounceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="detect-debounce-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/detect_debounce.sqlite"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-detect-debounce-setup")
        create_core_schema(self.runtime.engine)
        execute_statement(
            self.runtime.engine,
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("debounce-user", "debounce-user@example.com", "hash"),
        )

        self.backend = _ManualClockRedisBackend()
        set_detection_redis_client(
            RedisClient(
                config=RedisConfig(
                    redis_url="redis://localhost:6379/0",
                    key_prefix="test-detect-003",
                ),
                backend=self.backend,
            )
        )
        detection_retry_queue.clear()

    def tearDown(self) -> None:
        detection_retry_queue.clear()
        reset_detection_redis_client()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_duplicate_event_is_suppressed_within_ttl(self) -> None:
        first = self._detect(current_price=95.0)
        second = self._detect(current_price=94.0)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        rows = fetch_all(self.runtime.engine, "SELECT COUNT(*) FROM price_events")
        self.assertEqual(rows[0][0], 1)

    def test_detection_is_allowed_after_ttl_boundary(self) -> None:
        first = self._detect(current_price=95.0)
        self.backend.advance(301)
        second = self._detect(current_price=94.0)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        rows = fetch_all(self.runtime.engine, "SELECT COUNT(*) FROM price_events")
        self.assertEqual(rows[0][0], 2)

    def test_debounce_key_is_direction_sensitive(self) -> None:
        up_event = self._detect(current_price=104.0)
        down_event = self._detect(current_price=95.0)

        self.assertIsNotNone(up_event)
        self.assertIsNotNone(down_event)
        rows = fetch_all(self.runtime.engine, "SELECT COUNT(*) FROM price_events")
        self.assertEqual(rows[0][0], 2)

    def _detect(self, *, current_price: float) -> dict[str, object] | None:
        return detect_price_event_to_db(
            user_id="debounce-user",
            symbol="TSLA",
            market="US",
            baseline_price=100.0,
            current_price=current_price,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )


if __name__ == "__main__":
    unittest.main()
