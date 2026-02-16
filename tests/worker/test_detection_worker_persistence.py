from __future__ import annotations

import os
import tempfile
import unittest

from apps.infra.models import create_core_schema, drop_core_schema, execute_statement, fetch_all
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.detection_persistence import detect_price_event_to_db, detection_retry_queue


class DetectionWorkerPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="detect-worker-db-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/detect_worker.sqlite"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-detect-worker-setup")
        create_core_schema(self.runtime.engine)
        detection_retry_queue.clear()

    def tearDown(self) -> None:
        detection_retry_queue.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_persists_price_event_and_returns_saved_id(self) -> None:
        self._seed_user("worker-user-1")

        result = detect_price_event_to_db(
            user_id="worker-user-1",
            symbol="AAPL",
            market="US",
            baseline_price=100.0,
            current_price=103.5,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )

        assert result is not None
        self.assertTrue(result["saved"])
        self.assertFalse(result["queued_for_retry"])
        event_id = str(result["event_id"])

        rows = fetch_all(
            self.runtime.engine,
            """
            SELECT id, user_id, symbol, market, change_pct, window_minutes, detected_at_utc, session_label
            FROM price_events
            WHERE id = ?
            """,
            (event_id,),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], event_id)
        self.assertEqual(rows[0][1], "worker-user-1")
        self.assertEqual(rows[0][2], "AAPL")
        self.assertEqual(rows[0][3], "US")
        self.assertEqual(rows[0][5], 5)
        self.assertEqual(rows[0][6], "2026-02-16T12:00:00Z")
        self.assertEqual(rows[0][7], "pre")

    def test_returns_none_when_threshold_not_met(self) -> None:
        self._seed_user("worker-user-2")

        result = detect_price_event_to_db(
            user_id="worker-user-2",
            symbol="005930",
            market="KR",
            baseline_price=1000.0,
            current_price=1015.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )

        self.assertIsNone(result)
        rows = fetch_all(self.runtime.engine, "SELECT COUNT(*) FROM price_events")
        self.assertEqual(rows[0][0], 0)
        self.assertEqual(len(detection_retry_queue.list_tasks()), 0)

    def test_persistence_failure_enqueues_retry_task(self) -> None:
        result = detect_price_event_to_db(
            user_id="missing-user",
            symbol="MSFT",
            market="US",
            baseline_price=100.0,
            current_price=96.0,
            window_minutes=5,
            detected_at_utc="2026-02-16T12:00:00Z",
        )

        assert result is not None
        self.assertFalse(result["saved"])
        self.assertTrue(result["queued_for_retry"])
        self.assertIn("retry_task", result)
        task = result["retry_task"]
        self.assertEqual(task["user_id"], "missing-user")
        self.assertEqual(task["symbol"], "MSFT")
        self.assertEqual(task["market"], "US")
        self.assertTrue(task["error"])
        self.assertEqual(len(detection_retry_queue.list_tasks()), 1)

        rows = fetch_all(self.runtime.engine, "SELECT COUNT(*) FROM price_events")
        self.assertEqual(rows[0][0], 0)

    def _seed_user(self, user_id: str) -> None:
        execute_statement(
            self.runtime.engine,
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, f"{user_id}@example.com", "hash"),
        )


if __name__ == "__main__":
    unittest.main()
