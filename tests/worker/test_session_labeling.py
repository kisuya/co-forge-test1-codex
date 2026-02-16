from __future__ import annotations

import os
import tempfile
import unittest

from apps.domain.session_labeling import classify_market_session
from apps.infra.models import create_core_schema, drop_core_schema, execute_statement, fetch_all
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.infra.redis_client import InMemoryRedisBackend, RedisClient, RedisConfig
from apps.worker.detection_persistence import (
    detect_price_event_to_db,
    reset_detection_redis_client,
    set_detection_redis_client,
)


class SessionLabelingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="session-label-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/session_label.sqlite"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-session-label-setup")
        create_core_schema(self.runtime.engine)
        execute_statement(
            self.runtime.engine,
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("session-user", "session-user@example.com", "hash"),
        )
        set_detection_redis_client(
            RedisClient(
                config=RedisConfig(
                    redis_url="redis://localhost:6379/0",
                    key_prefix="test-detect-005",
                ),
                backend=InMemoryRedisBackend(),
            )
        )

    def tearDown(self) -> None:
        reset_detection_redis_client()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_us_session_boundary_minutes(self) -> None:
        self.assertEqual(classify_market_session(market="US", detected_at_utc="2026-02-17T14:29:00Z"), "pre")
        self.assertEqual(classify_market_session(market="US", detected_at_utc="2026-02-17T14:30:00Z"), "regular")
        self.assertEqual(classify_market_session(market="US", detected_at_utc="2026-02-17T21:00:00Z"), "regular")
        self.assertEqual(classify_market_session(market="US", detected_at_utc="2026-02-17T21:01:00Z"), "after-hours")

    def test_kr_session_boundary_minutes(self) -> None:
        self.assertEqual(classify_market_session(market="KR", detected_at_utc="2026-02-17T23:59:00Z"), "pre")
        self.assertEqual(classify_market_session(market="KR", detected_at_utc="2026-02-18T00:00:00Z"), "regular")
        self.assertEqual(classify_market_session(market="KR", detected_at_utc="2026-02-18T06:30:00Z"), "regular")
        self.assertEqual(classify_market_session(market="KR", detected_at_utc="2026-02-18T06:31:00Z"), "after-hours")

    def test_closed_label_on_holiday_and_weekend(self) -> None:
        self.assertEqual(classify_market_session(market="US", detected_at_utc="2026-01-01T15:00:00Z"), "closed")
        self.assertEqual(classify_market_session(market="US", detected_at_utc="2026-02-14T15:00:00Z"), "closed")

    def test_detected_event_persists_with_computed_session_label(self) -> None:
        result = detect_price_event_to_db(
            user_id="session-user",
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=104.0,
            window_minutes=5,
            detected_at_utc="2026-02-17T14:00:00Z",
        )

        assert result is not None
        rows = fetch_all(
            self.runtime.engine,
            "SELECT session_label FROM price_events WHERE id = ?",
            (result["event_id"],),
        )
        self.assertEqual(rows[0][0], "pre")


if __name__ == "__main__":
    unittest.main()
