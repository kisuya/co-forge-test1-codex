from __future__ import annotations

import os
import tempfile
import unittest

from apps.api.main import app
from apps.domain.user_thresholds import user_threshold_store
from apps.infra.models import create_core_schema, drop_core_schema, fetch_all
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.infra.redis_client import InMemoryRedisBackend, RedisClient, RedisConfig
from apps.worker.detection_persistence import (
    detect_price_event_to_db,
    detection_retry_queue,
    reset_detection_redis_client,
    set_detection_redis_client,
)
from fastapi.testclient import TestClient


class UserThresholdDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="user-threshold-detect-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/user_threshold.sqlite"
        os.environ["JWT_SECRET"] = "user-threshold-secret"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-user-threshold-setup")
        create_core_schema(self.runtime.engine)
        user_threshold_store.clear()
        detection_retry_queue.clear()
        set_detection_redis_client(
            RedisClient(
                config=RedisConfig(
                    redis_url="redis://localhost:6379/0",
                    key_prefix="test-detect-004",
                ),
                backend=InMemoryRedisBackend(),
            )
        )

        self.client = TestClient(app)
        self.user = self.client.post(
            "/v1/auth/signup",
            json={"email": "threshold@example.com", "password": "threshold-password"},
        ).json()

    def tearDown(self) -> None:
        user_threshold_store.clear()
        detection_retry_queue.clear()
        reset_detection_redis_client()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_detection_uses_default_threshold_when_user_setting_missing(self) -> None:
        result = detect_price_event_to_db(
            user_id=self.user["user_id"],
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=102.2,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )

        self.assertIsNone(result)
        rows = fetch_all(self.runtime.engine, "SELECT COUNT(*) FROM price_events")
        self.assertEqual(rows[0][0], 0)

    def test_detection_applies_user_threshold_after_api_update(self) -> None:
        set_threshold = self.client.post(
            "/v1/thresholds",
            json={"window_minutes": 5, "threshold_pct": 2.0},
            headers=self._auth(self.user["access_token"]),
        )
        self.assertEqual(set_threshold.status_code, 200)
        self.assertEqual(set_threshold.json()["threshold"]["threshold_pct"], 2.0)

        result = detect_price_event_to_db(
            user_id=self.user["user_id"],
            symbol="MSFT",
            market="US",
            baseline_price=100.0,
            current_price=102.2,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )

        assert result is not None
        self.assertTrue(result["saved"])
        rows = fetch_all(self.runtime.engine, "SELECT COUNT(*) FROM price_events")
        self.assertEqual(rows[0][0], 1)

    def test_threshold_validation_rejects_out_of_range_values(self) -> None:
        zero = self.client.post(
            "/v1/thresholds",
            json={"window_minutes": 5, "threshold_pct": 0},
            headers=self._auth(self.user["access_token"]),
        )
        too_high = self.client.post(
            "/v1/thresholds",
            json={"window_minutes": 5, "threshold_pct": 50.1},
            headers=self._auth(self.user["access_token"]),
        )

        self.assertEqual(zero.status_code, 400)
        self.assertEqual(zero.json()["code"], "invalid_input")
        self.assertEqual(too_high.status_code, 400)
        self.assertEqual(too_high.json()["code"], "invalid_input")

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
