from __future__ import annotations

from datetime import datetime, timezone
import os
import tempfile
import unittest

from apps.domain.notifications import notification_store
from apps.domain.push_tokens_db import push_tokens_db_service
from apps.infra.models import create_core_schema, drop_core_schema
from apps.infra.postgres import initialize_database_runtime, reset_database_runtime
from apps.worker.notifications import dispatch_event_notifications
from apps.worker.push_notifications import push_notification_queue


class PushNotificationOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="push-orchestration-")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmpdir.name}/push-orchestration.sqlite"

        reset_database_runtime()
        self.runtime = initialize_database_runtime(request_id="req-push-orchestration-setup")
        create_core_schema(self.runtime.engine)

        notification_store.clear()
        push_notification_queue.clear()
        self.now = datetime(2026, 2, 16, 12, 0, tzinfo=timezone.utc)
        self.event = {
            "id": "evt-push-1",
            "symbol": "AAPL",
            "market": "US",
            "change_pct": 4.2,
            "window_minutes": 5,
        }
        self.reasons = [{"reason_type": "filing", "source_url": "https://sec.example/filing"}]

    def tearDown(self) -> None:
        push_notification_queue.clear()
        notification_store.clear()
        drop_core_schema(self.runtime.engine)
        reset_database_runtime()
        self._tmpdir.cleanup()
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_push_token_opt_in_enqueues_push_queue(self) -> None:
        push_tokens_db_service.upsert_token(user_id="user-1", token="token-1", platform="ios")

        dispatched = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="user-1",
            channels=["in_app", "email", "push"],
            now_utc=self.now,
        )

        self.assertEqual({item["channel"] for item in dispatched}, {"in_app", "email", "push"})
        queued = push_notification_queue.list_messages()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].token, "token-1")

    def test_push_failure_does_not_break_in_app_or_email(self) -> None:
        push_tokens_db_service.upsert_token(user_id="user-1", token="token-2", platform="android")
        push_notification_queue.fail_next_enqueue(RuntimeError("push backend down"))

        dispatched = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="user-1",
            channels=["in_app", "email", "push"],
            now_utc=self.now,
        )

        self.assertEqual({item["channel"] for item in dispatched}, {"in_app", "email"})
        self.assertEqual(len(push_notification_queue.list_messages()), 0)

    def test_user_without_registered_token_skips_push(self) -> None:
        dispatched = dispatch_event_notifications(
            event=self.event,
            reasons=self.reasons,
            user_id="user-no-token",
            channels=["in_app", "email", "push"],
            now_utc=self.now,
        )

        self.assertEqual({item["channel"] for item in dispatched}, {"in_app", "email"})
        self.assertEqual(len(push_notification_queue.list_messages()), 0)


if __name__ == "__main__":
    unittest.main()
