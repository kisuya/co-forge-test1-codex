from __future__ import annotations

import json
import os
import tempfile
import unittest

from apps.api.main import app
from apps.infra.postgres import (
    DatabaseConnectionError,
    get_database_runtime,
    initialize_database_runtime,
    reset_database_runtime,
)
from fastapi.testclient import TestClient


class PostgresSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        reset_database_runtime()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        reset_database_runtime()

    def test_initialize_uses_env_pool_settings_and_builds_session_factory(self) -> None:
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["DB_POOL_SIZE"] = "11"
        os.environ["DB_POOL_TIMEOUT"] = "9"

        runtime = initialize_database_runtime(request_id="req-db-init")

        self.assertEqual(runtime.settings.database_url, "sqlite:///:memory:")
        self.assertEqual(runtime.settings.pool_size, 11)
        self.assertEqual(runtime.settings.pool_timeout_seconds, 9)
        self.assertEqual(runtime.health(request_id="req-db-health"), "ok")

        session = runtime.session_factory()
        self.assertTrue(hasattr(session, "close"))
        session.close()

    def test_db_health_endpoint_returns_ok(self) -> None:
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        initialize_database_runtime(request_id="startup")

        client = TestClient(app)
        response = client.get("/health/db", headers={"X-Request-ID": "req-health-db"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers.get("x-request-id"), "req-health-db")

    def test_connection_failure_logs_request_id_and_raises(self) -> None:
        missing_dir = tempfile.mkdtemp(prefix="postgres-fail-")
        bad_path = os.path.join(missing_dir, "nested", "db.sqlite")
        os.environ["DATABASE_URL"] = f"sqlite:///{bad_path}"

        with self.assertLogs("oh_my_stock.infra.postgres", level="ERROR") as captured:
            with self.assertRaises(DatabaseConnectionError):
                initialize_database_runtime(request_id="req-db-fail")

        payload = json.loads(captured.records[-1].getMessage())
        self.assertEqual(payload["event"], "database_connection_failed")
        self.assertEqual(payload["feature"], "infra-002")
        self.assertEqual(payload["request_id"], "req-db-fail")
        self.assertEqual(payload["level"], "error")

    def test_get_database_runtime_fail_fast_when_startup_validation_fails(self) -> None:
        os.environ["DATABASE_URL"] = "postgresql://user:password@localhost:5432/oh_my_stock"

        with self.assertLogs("oh_my_stock.infra.postgres", level="ERROR") as captured:
            with self.assertRaises(DatabaseConnectionError):
                get_database_runtime()

        payload = json.loads(captured.records[-1].getMessage())
        self.assertEqual(payload["request_id"], "startup")


if __name__ == "__main__":
    unittest.main()
